from __future__ import annotations

import datetime as dt
import logging
import threading
from typing import List

from .config import AppConfig, RoomConfig
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
        self.room = BiliLiveRoom(room_config.room_id, headers=app_config.root.request_header)
        self.state = RunnerState.IDLE
        self.state_since = dt.datetime.now()
        self.last_error: str | None = None
        self._stop_event = threading.Event()
        self.detect_logger = get_stage_logger("detect")
        self.record_logger = get_stage_logger("record")
        self.merge_logger = get_stage_logger("merge")
        self.split_logger = get_stage_logger("split")
        self.upload_logger = get_stage_logger("upload")

    def stop(self) -> None:
        self._stop_event.set()

    def set_state(self, state: RunnerState) -> None:
        self.state = state
        self.state_since = dt.datetime.now()
        logging.info("房间 %s 状态 -> %s", self.room_config.room_id, state.value)

    def sleep_with_stop(self, seconds: int) -> None:
        self._stop_event.wait(seconds)

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.room.refresh()
                self.detect_logger.info("刷新房间 %s，live=%s", self.room_config.room_id, self.room.is_live)
            except Exception:
                self.last_error = "刷新房间状态失败"
                self.detect_logger.error("刷新房间 %s 状态失败", self.room_config.room_id, exc_info=True)
                self.sleep_with_stop(self.app_config.root.check_interval)
                continue

            if not self.room.is_live:
                self.set_state(RunnerState.IDLE)
                self.sleep_with_stop(self.app_config.root.check_interval)
                continue

            session_start = dt.datetime.now()
            paths = RecordingPaths(self.app_config.root.data_path, self.room_config.room_id, session_start)
            recorder = LiveRecorder(self.room, paths, self.room_config.recorder, self.app_config.root)
            self.set_state(RunnerState.RECORDING)
            self.record_logger.info("房间 %s 开始录制，输出目录 %s", self.room_config.room_id, recorder.paths.records_dir)
            record_result = recorder.record()
            if not record_result:
                self.set_state(RunnerState.ERROR)
                self.record_logger.error("房间 %s 录制失败，无有效片段", self.room_config.room_id)
                continue

            processor = RecordingProcessor(paths, self.room_config.recorder)
            self.set_state(RunnerState.PROCESSING)
            self.merge_logger.info("房间 %s 进入处理阶段", self.room_config.room_id)
            process_result = processor.run()
            if not process_result:
                self.set_state(RunnerState.ERROR)
                self.merge_logger.error("房间 %s 处理录制文件失败", self.room_config.room_id)
                continue

            record_cfg = self.room_config.uploader.record
            if not record_cfg.upload_record:
                self.set_state(RunnerState.IDLE)
                self.upload_logger.info("房间 %s 配置为不上传，处理完成后回到待命", self.room_config.room_id)
                continue

            splits = processor.split(record_cfg.split_interval)
            if not splits:
                self.set_state(RunnerState.ERROR)
                self.split_logger.error("房间 %s 切分录播失败", self.room_config.room_id)
                continue

            try:
                uploader = BiliUploader(self.app_config, self.room_config, self.room)
            except Exception:
                self.upload_logger.error("初始化上传器失败 room=%s", self.room_config.room_id, exc_info=True)
                self.set_state(RunnerState.ERROR)
                continue
            self.set_state(RunnerState.UPLOADING)
            self.upload_logger.info("房间 %s 开始上传，分段数量 %s", self.room_config.room_id, len(splits))
            upload_success = False
            try:
                upload_ret = uploader.upload_record(session_start, splits)
                upload_success = upload_ret is not None
                if upload_success and not record_cfg.keep_record_after_upload:
                    self._cleanup_splits(processor)
                    self.upload_logger.info("房间 %s 上传成功，已按配置清理分段", self.room_config.room_id)
            except Exception:
                self.upload_logger.error("上传失败 room=%s", self.room_config.room_id, exc_info=True)
                upload_success = False
            finally:
                uploader.close()
            if upload_success:
                clear_upload_failed(processor.paths.splits_dir)
            else:
                mark_upload_failed(processor.paths.splits_dir, "upload_failed")
            self.set_state(RunnerState.IDLE if upload_success else RunnerState.ERROR)

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
        header = "DDRecorder  当前时间：{} 正在工作线程数：{}".format(now, threading.active_count())
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
                    tid=tid, plat=platform, room=room_id, live=live_flag, state=state, since=since
                )
            )
        rows.append(border)
        return "\n".join([header, ""] + rows)
