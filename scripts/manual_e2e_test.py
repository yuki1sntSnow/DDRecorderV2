#!/usr/bin/env python3
"""Record a short session and run process/split/upload to validate the full pipeline."""

from __future__ import annotations

import argparse
import datetime as dt
import requests
import sys
from pathlib import Path

# Ensure project root is importable when running as a script
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ddrecorder.config import load_config, RoomConfig
from ddrecorder.logging import configure_logging
from ddrecorder.danmurecorder import DanmuRecorder
from ddrecorder.live.bilibili import BiliLiveRoom
from ddrecorder.paths import RecordingPaths
from ddrecorder.processor import RecordingProcessor
from ddrecorder.recorder import LiveRecorder, RecordingResult
from ddrecorder.runner import build_danmu_headers
from ddrecorder.uploader import BiliUploader


class LimitedLiveRoom(BiliLiveRoom):
    """Wrap BiliLiveRoom with a time limit so recording stops after duration seconds."""

    def __init__(self, room_id: str, headers: dict[str, str] | None, stop_at: dt.datetime) -> None:
        super().__init__(room_id, headers=headers)
        self._stop_at = stop_at

    @property
    def is_live(self) -> bool:  # type: ignore[override]
        return super().is_live and dt.datetime.now() < self._stop_at


class TimedRecorder(LiveRecorder):
    """LiveRecorder that stops after a deadline."""

    def __init__(self, room, paths, recorder_cfg, root_cfg, stop_at: dt.datetime) -> None:
        super().__init__(room, paths, recorder_cfg, root_cfg)
        self._stop_at = stop_at

    def record(self):
        self.paths.ensure_session_dirs()
        fragments: list[Path] = []
        max_secs = max(1, int((self._stop_at - dt.datetime.now()).total_seconds()))
        self.logger.info("开始录制房间 %s，最长 %ss", self.room.room_id, max_secs)
        while self.room.is_live and dt.datetime.now() < self._stop_at:
            stream_urls = self.room.fetch_stream_urls()
            if not stream_urls:
                self.logger.warning("未获取到直播流地址，稍后重试")
                break
            target_path = self.paths.fragment_path()
            if self._download_timed(stream_urls[0], target_path):
                fragments.append(target_path)
                self.logger.info("完成片段 %s", target_path.name)
            self.room.refresh()
        if not fragments:
            self.logger.error("本次录制未生成有效片段")
            return None
        return RecordingResult(start=self.paths.start, record_dir=self.paths.records_dir, fragments=fragments)

    def _download_timed(self, url: str, target_path: Path) -> bool:
        try:
            with requests.get(
                url, stream=True, timeout=(10, self.root_cfg.check_interval)
            ) as resp:
                resp.raise_for_status()
                with open(target_path, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=256 * 1024):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        if dt.datetime.now() >= self._stop_at:
                            self.logger.info("达到录制时长上限，截断当前片段")
                            break
            return True
        except requests.HTTPError as exc:
            self.logger.warning("拉流返回 HTTP %s，url=%s", exc.response.status_code if exc.response else "?", url)
        except requests.RequestException:
            self.logger.warning("录制时网络异常，稍后重试", exc_info=True)
        except OSError:
            self.logger.error("写入录播文件失败: %s", target_path, exc_info=True)
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="手动跑通录制->处理->分段->上传链路（限时录制）")
    parser.add_argument(
        "-c",
        "--config",
        default="config/test_config.json",
        help="配置文件 (默认: config/test_config.json)",
    )
    parser.add_argument(
        "--room-id",
        help="指定配置中的房间号；缺省取配置里的第一个房间",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="录制时长秒数 (默认: 60)",
    )
    return parser.parse_args()


def _select_room(app_config, room_id: str | None) -> RoomConfig:
    if room_id is None and app_config.rooms:
        return app_config.rooms[0]
    for room in app_config.rooms:
        if str(room.room_id) == str(room_id):
            return room
    raise SystemExit(f"配置中未找到房间 {room_id}")


def main() -> None:
    args = parse_args()
    duration = max(5, args.duration)

    config_path = Path(args.config).resolve()
    if not config_path.exists():
        raise SystemExit(f"配置文件不存在: {config_path}")

    app_config = load_config(config_path)
    room_cfg = _select_room(app_config, args.room_id)
    # 强制上传开启，便于验证上传链路
    room_cfg.uploader.record.upload_record = True

    configure_logging(app_config.root.logger)
    print(f"[INFO] 配置读取完成，房间={room_cfg.room_id}，录制时长上限={duration}s")

    start_time = dt.datetime.now()
    stop_at = start_time + dt.timedelta(seconds=duration)
    room = LimitedLiveRoom(room_cfg.room_id, headers=app_config.root.request_header, stop_at=stop_at)
    info = room.refresh()
    if not info.is_live:
        raise SystemExit(f"房间 {room_cfg.room_id} 未开播，无法录制")

    paths = RecordingPaths(app_config.root.data_path, room_cfg.room_id, start_time)
    recorder = TimedRecorder(room, paths, room_cfg.recorder, app_config.root, stop_at)
    danmu_recorder: DanmuRecorder | None = None
    if room_cfg.recorder.enable_danmu:
        danmu_headers = build_danmu_headers(app_config.root.request_header, room_cfg.uploader.account)
        danmu_recorder = DanmuRecorder(
            room_id=room_cfg.room_id,
            slug=paths.slug,
            headers=danmu_headers,
            output_dir=paths.danmu_dir,
        )
        danmu_recorder.start()
        print(f"[INFO] 弹幕录制已启动，输出目录 {paths.danmu_dir}")

    print(f"[INFO] 开始录制房间 {room_cfg.room_id}，最长 {duration}s ...")
    record_result = recorder.record()
    if danmu_recorder:
        danmu_recorder.stop()
        danmu_recorder.join(timeout=5)
        print("[INFO] 弹幕录制已停止")
    if not record_result:
        raise SystemExit("录制失败，未生成片段")
    print(f"[INFO] 录制完成，开始处理: {record_result.record_dir}")

    processor = RecordingProcessor(
        paths,
        room_cfg.recorder,
        app_config.root.danmu_ass,
        app_config.root.ffmpeg_path,
        app_config.root.ffprobe_path,
    )
    uploader: BiliUploader | None = None
    try:
        print("[INFO] 处理/合并开始 ...")
        process_result = processor.run()
        if not process_result:
            raise SystemExit("处理阶段失败")

        print("[INFO] 分段开始 ...")
        splits = processor.split(room_cfg.uploader.record.split_interval)
        if not splits:
            raise SystemExit("切分失败，未生成分段")

        print(f"[INFO] 上传开始，分段数={len(splits)} ...")
        uploader = BiliUploader(app_config, room_cfg, room)
        upload_ret = uploader.upload_record(start_time, splits)
        if not upload_ret:
            raise SystemExit("上传失败，接口返回空结果")
    finally:
        if uploader:
            uploader.close()
        processor.close()

    print(f"[INFO] 上传成功 bvid={upload_ret.get('bvid')} 分段={len(splits)} 输出目录={paths.splits_dir}")


if __name__ == "__main__":
    main()
