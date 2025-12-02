from __future__ import annotations

import datetime as dt
import logging
import threading
import time
from pathlib import Path
from typing import List

from .config import AppConfig, RoomConfig, AccountConfig
from .danmurecorder import DanmuRecorder
from .live.bilibili import BiliLiveRoom
from .logging import get_stage_logger
from .paths import RecordingPaths
from .processor import RecordingProcessor
from .recorder import LiveRecorder
from .state import RunnerState
from .uploader import BiliUploader
from .utils import clear_upload_failed, mark_upload_failed


class RoomRunner(threading.Thread):
    def __init__(self, app_config: AppConfig, room_config: RoomConfig) -> None:
        super().__init__(name=f"Room-{room_config.room_id}", daemon=True)
        self.app_config = app_config
        self.room_config = room_config
        self.room = BiliLiveRoom(
            room_config.room_id, headers=app_config.root.request_header
        )
        self.state = RunnerState.IDLE
        self.state_since = dt.datetime.now()
        self.last_error: str | None = None
        self._stop_event = threading.Event()
        self.detect_logger = get_stage_logger("detect")
        self.record_logger = get_stage_logger("record")
        self.process_logger = get_stage_logger("process")
        self.upload_logger = get_stage_logger("upload")

    def stop(self) -> None:
        self._stop_event.set()

    def set_state(self, state: RunnerState) -> None:
        if self.state == state:
            return
        self.state = state
        self.state_since = dt.datetime.now()
        logging.info("房间 %s 状态 -> %s", self.room_config.room_id, state.value)

    def sleep_with_stop(self, seconds: int) -> None:
        self._stop_event.wait(seconds)

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.room.refresh()
                self.detect_logger.debug(
                    "刷新房间 %s，live=%s", self.room_config.room_id, self.room.is_live
                )
            except Exception:
                self.last_error = "刷新房间状态失败"
                self.detect_logger.warning(
                    "刷新房间 %s 状态失败", self.room_config.room_id, exc_info=True
                )
                self.sleep_with_stop(self.app_config.root.check_interval)
                continue

            if not self.room.is_live:
                self.set_state(RunnerState.IDLE)
                self.sleep_with_stop(self.app_config.root.check_interval)
                continue

            session_start = dt.datetime.now()
            paths = RecordingPaths(
                self.app_config.root.data_path, self.room_config.room_id, session_start
            )
            recorder = LiveRecorder(
                self.room, paths, self.room_config.recorder, self.app_config.root
            )
            danmu_recorder = None
            if self.room_config.recorder.enable_danmu:
                try:
                    danmu_headers = build_danmu_headers(
                        self.app_config.root.request_header,
                        self.room_config.uploader.account,
                    )
                    danmu_recorder = DanmuRecorder(
                        room_id=self.room_config.room_id,
                        slug=paths.slug,
                        headers=danmu_headers,
                        output_dir=paths.danmu_dir,
                        logger=self.record_logger,
                    )
                    danmu_recorder.start()
                except Exception:
                    danmu_recorder = None
                    self.record_logger.error(
                        "弹幕录制器启动失败 room=%s",
                        self.room_config.room_id,
                        exc_info=True,
                    )
            else:
                danmu_recorder = None
            self.set_state(RunnerState.RECORDING)
            self.record_logger.info(
                "房间 %s 开始录制，输出目录 %s",
                self.room_config.room_id,
                recorder.paths.records_dir,
            )
            record_result = recorder.record()
            if danmu_recorder:
                danmu_recorder.stop()
                danmu_recorder.join(timeout=5)
            if not record_result:
                self.set_state(RunnerState.ERROR)
                self.record_logger.error(
                    "房间 %s 录制失败，无有效片段", self.room_config.room_id
                )
                continue

            processor = RecordingProcessor(
                paths, self.room_config.recorder, self.app_config.root.danmu_ass
            )
            try:
                self.set_state(RunnerState.PROCESSING)
                self.process_logger.info(
                    "房间 %s 进入处理阶段", self.room_config.room_id
                )
                process_result = processor.run()
                if not process_result:
                    self.set_state(RunnerState.ERROR)
                    self.process_logger.error(
                        "房间 %s 处理录制文件失败", self.room_config.room_id
                    )
                    continue

                record_cfg = self.room_config.uploader.record
                if not record_cfg.upload_record:
                    self.set_state(RunnerState.IDLE)
                    self.upload_logger.info(
                        "房间 %s 配置为不上传，处理完成后回到待命",
                        self.room_config.room_id,
                    )
                    continue

                try:
                    splits = processor.split(record_cfg.split_interval)
                except Exception:
                    self.set_state(RunnerState.ERROR)
                    self.process_logger.error(
                        "房间 %s 切分录播异常", self.room_config.room_id, exc_info=True
                    )
                    continue
                if not splits:
                    self.set_state(RunnerState.ERROR)
                    self.process_logger.error(
                        "房间 %s 切分录播失败", self.room_config.room_id
                    )
                    continue

                upload_success = self._upload_with_retry(
                    session_start,
                    splits,
                    record_cfg.keep_record_after_upload,
                    processor,
                )
                self.set_state(
                    RunnerState.IDLE if upload_success else RunnerState.ERROR
                )
            finally:
                processor.close()

    def _do_upload(
        self,
        session_start: dt.datetime,
        splits: List[Path],
        cleanup_on_success: bool,
        processor: RecordingProcessor,
    ) -> bool:
        """执行一次上传尝试，返回是否成功"""
        try:
            uploader = BiliUploader(self.app_config, self.room_config, self.room)
        except Exception:
            self.upload_logger.error(
                "初始化上传器失败 room=%s", self.room_config.room_id, exc_info=True
            )
            return False
        try:
            upload_ret = uploader.upload_record(session_start, splits)
            if upload_ret is not None:
                if cleanup_on_success:
                    self._cleanup_splits(processor)
                    self.upload_logger.info(
                        "房间 %s 上传成功，已按配置清理分段", self.room_config.room_id
                    )
                return True
            return False
        except Exception:
            self.upload_logger.error(
                "上传失败 room=%s", self.room_config.room_id, exc_info=True
            )
            return False
        finally:
            uploader.close()

    def _upload_with_retry(
        self,
        session_start: dt.datetime,
        splits: List[Path],
        cleanup_on_success: bool,
        processor: RecordingProcessor,
        retry_delay: int = 3600,
    ) -> bool:
        """上传并在失败时重试一次，重试间隔默认60分钟"""
        self.set_state(RunnerState.UPLOADING)
        self.upload_logger.info(
            "房间 %s 开始上传，分段数量 %s", self.room_config.room_id, len(splits)
        )

        if self._do_upload(session_start, splits, cleanup_on_success, processor):
            clear_upload_failed(processor.paths.splits_dir)
            return True

        # 首次失败，等待后重试
        self.upload_logger.warning(
            "房间 %s 上传失败，将在 %s 分钟后重试",
            self.room_config.room_id,
            retry_delay // 60,
        )
        self.set_state(RunnerState.IDLE)
        time.sleep(retry_delay)

        # 重试上传
        self.set_state(RunnerState.UPLOADING)
        self.upload_logger.info("房间 %s 开始重试上传", self.room_config.room_id)
        if self._do_upload(session_start, splits, cleanup_on_success, processor):
            clear_upload_failed(processor.paths.splits_dir)
            return True

        # 重试也失败，标记失败
        self.upload_logger.error(
            "房间 %s 重试上传仍失败，标记为上传失败", self.room_config.room_id
        )
        mark_upload_failed(processor.paths.splits_dir, "upload_failed_after_retry")
        return False

    def _cleanup_splits(self, processor: RecordingProcessor) -> None:
        for item in processor.paths.splits_dir.glob("*"):
            try:
                item.unlink()
            except OSError:
                logging.debug("删除分段失败: %s", item, exc_info=True)
        try:
            processor.paths.splits_dir.rmdir()
        except OSError:
            logging.debug("删除分段目录失败")


def build_danmu_headers(
    base_headers: dict[str, str] | None, account: AccountConfig | None
) -> dict[str, str]:
    headers: dict[str, str] = dict(base_headers or {})
    cookie = headers.get("Cookie") or headers.get("cookie")
    if not cookie and account and account.cookies:
        cookie = "; ".join(f"{key}={value}" for key, value in account.cookies.items())
        if cookie:
            headers["Cookie"] = cookie
    return headers


class RunnerController:
    def __init__(self, app_config: AppConfig) -> None:
        self.app_config = app_config
        self.runners: List[RoomRunner] = [
            RoomRunner(app_config, room_config) for room_config in app_config.rooms
        ]
        self._printer_thread = threading.Thread(
            target=self._print_loop, name="StatusPrinter", daemon=True
        )
        self._stop_event = threading.Event()

    def start(self) -> None:
        if not self.runners:
            logging.warning("配置中没有任何直播间")
            return
        for runner in self.runners:
            runner.start()
        self._printer_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        for runner in self.runners:
            runner.stop()
        for runner in self.runners:
            runner.join(timeout=5)

    def _print_loop(self) -> None:
        while not self._stop_event.wait(self.app_config.root.print_interval):
            table = self._build_status_table()
            print(table, flush=True)

    def _build_status_table(self) -> str:
        now = dt.datetime.now()
        header = "DDRecorder  当前时间：{} 正在工作线程数：{}".format(
            now, threading.active_count()
        )
        border = "+-------+----------+----------+----------+----------+---------------------+"
        title = "|  TID  |   平台   |  房间号  | 直播状态 | 程序状态 |     状态变化时间     |"
        rows = [border, title, border]
        for runner in self.runners:
            tid = runner.native_id or runner.ident or "-"
            platform = "BiliBili"
            room_id = runner.room_config.room_id
            live_flag = "是" if runner.room.is_live else "否"
            state = runner.state.value
            since = runner.state_since.strftime("%Y-%m-%d %H:%M:%S")
            rows.append(
                "| {tid:^5} | {plat:^8} | {room:^8} | {live:^8} | {state:^8} | {since:^19} |".format(
                    tid=tid,
                    plat=platform,
                    room=room_id,
                    live=live_flag,
                    state=state,
                    since=since,
                )
            )
        rows.append(border)
        return "\n".join([header, ""] + rows)
