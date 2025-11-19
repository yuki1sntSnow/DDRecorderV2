from __future__ import annotations

import argparse
import logging
import re
import signal
import sys
import time
from pathlib import Path

from .cleanup import CleanupScheduler, perform_cleanup
from .config import AppConfig, RoomConfig, load_config
from .logging import configure_logging
from .paths import RecordingPaths
from .processor import RecordingProcessor
from .runner import RunnerController
from .uploader import BiliUploader
from .live.bilibili import BiliLiveRoom
from .utils import clear_upload_failed, mark_upload_failed

import datetime as dt

_SLUG_TS_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DDRecorderV2 - B 站直播录播工具")
    parser.add_argument(
        "-c",
        "--config",
        default="config/config.json",
        help="配置文件路径 (默认: config/config.json)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="只执行一次清理任务后退出",
    )
    parser.add_argument(
        "--cleanup-interval",
        type=float,
        default=24.0,
        help="后台定期清理的间隔（小时），0 表示不启用",
    )
    parser.add_argument(
        "--cleanup-retention",
        type=int,
        default=7,
        help="保留录制/日志的天数，清理任务会删除更早的文件",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="运行项目附带的 pytest 测试后退出",
    )
    parser.add_argument(
        "--upload-path",
        help="手动上传指定目录下的 mp4 分段（路径为 splits 目录）",
    )
    parser.add_argument(
        "--split-path",
        help="手动切分已合并的 mp4 文件（路径为 *_merged.mp4 或包含该文件的目录）",
    )
    parser.add_argument(
        "--split-interval",
        type=int,
        help="配合 --split-path 指定分段长度（秒），缺省读取配置文件",
    )
    parser.add_argument(
        "--room-id",
        help="配合 --upload-path/--split-path 指定房间号；缺省尝试从路径推断",
    )
    parser.add_argument(
        "--dump-credentials",
        action="store_true",
        help="登录并输出账号 Token/Cookies 到 config 目录下的 cookies.json 后退出（使用 root.account）",
    )
    parser.add_argument(
        "--account",
        help="配合 --dump-credentials 指定 root.account 下的名称，缺省取第一个",
    )
    return parser.parse_args(argv)


def run(config_path: str, cleanup_interval: float = 0.0, cleanup_retention: int = 7) -> None:
    cfg_path = Path(config_path).resolve()
    logging.info("Loading config from %s", cfg_path)
    app_config = load_config(cfg_path)
    configure_logging(app_config.root.logger)
    controller = RunnerController(app_config)
    controller.start()
    logging.info("Started %s room runners", len(controller.runners))
    scheduler = None
    if cleanup_interval > 0:
        scheduler = CleanupScheduler(app_config, cleanup_retention, cleanup_interval)
        scheduler.start()
        logging.info(
            "Cleanup scheduler started (interval=%sh, retention=%s days)",
            cleanup_interval,
            cleanup_retention,
        )

    def handle_signal(signum, frame):
        controller.stop()
        if scheduler:
            scheduler.stop()
        sys.exit(0)

    for sig in (signal.SIGINT, getattr(signal, "SIGTERM", signal.SIGINT)):
        try:
            signal.signal(sig, handle_signal)
        except (AttributeError, OSError, ValueError):
            pass

    try:
        logging.info("DDRecorder started. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        controller.stop()
        if scheduler:
            scheduler.stop()
        logging.info("Shutdown complete")


def main() -> None:
    args = parse_args()
    cfg_path = Path(args.config).resolve()
    if args.run_tests:
        run_tests()
        return
    if args.dump_credentials:
        dump_and_exit(cfg_path, args.account)
        return
    if args.split_path:
        manual_split_from_cli(
            cfg_path, Path(args.split_path), room_id=args.room_id, split_interval=args.split_interval
        )
        return
    if args.upload_path:
        manual_upload_from_cli(cfg_path, Path(args.upload_path), room_id=args.room_id)
        return
    if args.clean:
        perform_cleanup(cfg_path, args.cleanup_retention)
        return
    run(str(cfg_path), cleanup_interval=args.cleanup_interval, cleanup_retention=args.cleanup_retention)


def run_tests() -> None:
    import subprocess
    import sys

    cmd = [sys.executable, "-m", "pytest"]
    subprocess.run(cmd, check=True)


def dump_and_exit(config_path: Path, account: str | None) -> None:
    from .account_refresh import dump_credentials

    out_path = dump_credentials(config_path, account_name=account)
    logging.info("账户凭据已输出到 %s", out_path)
    print(f"[INFO] 凭据已保存到 {out_path}")


def manual_split_from_cli(
    config_path: Path, target_path: Path, room_id: str | None = None, split_interval: int | None = None
) -> None:
    logging.info("Manual split start: config=%s target=%s", config_path, target_path)
    if not target_path.exists():
        raise SystemExit(f"指定的合并文件或目录不存在: {target_path}")
    merged_file = _locate_merged_file(target_path)
    slug = _strip_merged_suffix(merged_file.stem)
    inferred_room_id = room_id or _infer_room_id_from_slug(slug)

    app_config = load_config(config_path)
    configure_logging(app_config.root.logger)

    if not inferred_room_id:
        raise SystemExit("无法从路径推断房间号，请使用 --room-id 指定")
    room_config = _get_room_config(app_config, inferred_room_id)
    start_time = _infer_start_time_from_slug(slug, merged_file)
    interval = split_interval or room_config.uploader.record.split_interval

    paths = RecordingPaths(app_config.root.data_path, room_config.room_id, start_time)
    processor = RecordingProcessor(paths, room_config.recorder, app_config.root.danmu_ass)
    try:
        splits = processor.split(interval, merged_override=merged_file, splits_dir=paths.splits_dir)
    finally:
        processor.close()
    if not splits:
        raise SystemExit("手动切分失败，未生成任何分段")
    logging.info("手动切分完成，输出目录 %s，分段数量 %s", paths.splits_dir, len(splits))
    print(f"[INFO] 已生成 {len(splits)} 个分段 -> {paths.splits_dir}")


def manual_upload_from_cli(config_path: Path, media_path: Path, room_id: str | None = None) -> None:
    logging.info("Manual upload start: config=%s media=%s", config_path, media_path)
    if not media_path.exists():
        raise SystemExit(f"指定的上传路径不存在: {media_path}")
    app_config = load_config(config_path)
    configure_logging(app_config.root.logger)
    room_config = _select_room_config(app_config, media_path, room_id)
    success = _manual_upload(app_config, room_config, media_path)
    if not success:
        raise SystemExit("手动上传失败")
    logging.info("Manual upload finished successfully")


def _select_room_config(app_config: AppConfig, media_path: Path, room_id: str | None) -> RoomConfig:
    rid = room_id or _infer_room_id_from_path(media_path)
    if not rid:
        raise SystemExit("无法从路径推断房间号，请使用 --room-id 指定")
    for room in app_config.rooms:
        if str(room.room_id) == str(rid):
            return room
    raise SystemExit(f"配置中未找到房间号 {rid}")


def _infer_room_id_from_path(media_path: Path) -> str | None:
    directory = media_path if media_path.is_dir() else media_path.parent
    name = directory.name
    candidate = name.split("_")[0]
    if candidate.isdigit():
        return candidate
    parent_name = directory.parent.name
    if parent_name.isdigit():
        return parent_name
    return None


def _infer_start_time(directory: Path, splits: list[Path]) -> dt.datetime:
    parts = directory.name.split("_")
    if len(parts) >= 3:
        try:
            return dt.datetime.strptime("_".join(parts[1:3]), "%Y-%m-%d_%H-%M-%S")
        except ValueError:
            pass
    if splits:
        earliest = min(p.stat().st_mtime for p in splits)
        return dt.datetime.fromtimestamp(earliest)
    return dt.datetime.now()


def _get_room_config(app_config: AppConfig, room_id: str) -> RoomConfig:
    for room in app_config.rooms:
        if str(room.room_id) == str(room_id):
            return room
    raise SystemExit(f"配置中未找到房间号 {room_id}")


def _locate_merged_file(target_path: Path) -> Path:
    if target_path.is_file():
        return target_path
    candidates = sorted(p for p in target_path.glob("*_merged.mp4") if p.is_file())
    if not candidates:
        raise SystemExit(f"目录 {target_path} 中未找到 *_merged.mp4 文件")
    return candidates[-1]


def _strip_merged_suffix(stem: str) -> str:
    if stem.endswith("_merged"):
        return stem[: -len("_merged")]
    return stem


def _infer_start_time_from_slug(slug: str, fallback_file: Path) -> dt.datetime:
    match = _SLUG_TS_PATTERN.search(slug)
    if match:
        try:
            return dt.datetime.strptime(match.group(0), "%Y-%m-%d_%H-%M-%S")
        except ValueError:
            pass
    return dt.datetime.fromtimestamp(fallback_file.stat().st_mtime)


def _infer_room_id_from_slug(slug: str) -> str | None:
    prefix = slug.split("_")[0]
    return prefix if prefix.isdigit() else None


def _manual_upload(app_config: AppConfig, room_config: RoomConfig, media_path: Path) -> bool:
    media_dir = media_path if media_path.is_dir() else media_path.parent
    splits = sorted(p for p in media_dir.glob("*.mp4"))
    if not splits:
        logging.error("目录 %s 中没有可上传的 mp4 文件", media_dir)
        return False
    logging.info("准备上传目录 %s 内的 %s 个分段", media_dir, len(splits))
    room = BiliLiveRoom(room_config.room_id, headers=app_config.root.request_header)
    uploader = BiliUploader(app_config, room_config, room)
    start_time = _infer_start_time(media_dir, splits)
    try:
        result = uploader.upload_record(start_time, splits)
        if result:
            logging.info("上传成功 bvid=%s", result.get("bvid"))
            clear_upload_failed(media_dir)
            return True
        logging.error("上传接口返回空结果")
        mark_upload_failed(media_dir, "manual_upload_failed")
        return False
    except Exception:
        logging.error("手动上传过程中出现异常", exc_info=True)
        mark_upload_failed(media_dir, "manual_upload_exception")
        return False
    finally:
        uploader.close()


if __name__ == "__main__":
    main()
