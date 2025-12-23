#!/usr/bin/env python3
"""Process a recorded session: mux fragments, burn danmaku ASS, and split."""

from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

from ddrecorder.config import load_config
from ddrecorder.logging import configure_logging
from ddrecorder.paths import RecordingPaths
from ddrecorder.processor import RecordingProcessor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="对指定会话执行合并/字幕/分段")
    parser.add_argument(
        "-c",
        "--config",
        default="config/test_config.json",
        help="配置文件 (默认: config/test_config.json)",
    )
    parser.add_argument(
        "--room",
        required=True,
        help="房间号，对应 data/records/<room>_*",
    )
    parser.add_argument(
        "--slug",
        help="可选：指定会话目录名（默认为 data/records/<room>_* 中最新的）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config).resolve()
    if not config_path.exists():
        raise SystemExit(f"配置文件不存在: {config_path}")

    app_config = load_config(config_path)
    configure_logging(app_config.root.logger)
    room_cfg = next((room for room in app_config.rooms if room.room_id == args.room), None)
    if room_cfg is None:
        raise SystemExit(f"配置中未找到房间 {args.room}")

    slug = args.slug or _find_latest_slug(app_config.root.data_path, args.room)
    if not slug:
        raise SystemExit(f"data/records/ 下没有 {args.room}_* 会话")
    start_dt = _parse_slug_time(slug)
    paths = RecordingPaths(app_config.root.data_path, args.room, start_dt)

    processor = RecordingProcessor(
        paths,
        room_cfg.recorder,
        app_config.root.danmu_ass,
        app_config.root.ffmpeg_path,
        app_config.root.ffprobe_path,
    )
    try:
        result = processor.run()
        if not result:
            print("[WARN] 合并失败")
            return
        splits = processor.split(room_cfg.uploader.record.split_interval)
    finally:
        processor.close()
    print(f"[INFO] 合并已完成: {result.merged_file}")
    print(f"[INFO] 分段数量: {len(splits)} -> {paths.splits_dir}")


_SLUG_TS_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}")


def _find_latest_slug(data_root: Path, room_id: str) -> str | None:
    base = data_root / "data" / "records"
    candidates = sorted(path for path in base.glob(f"{room_id}_*") if path.is_dir())
    if not candidates:
        return None
    return candidates[-1].name


def _parse_slug_time(slug: str) -> dt.datetime:
    match = _SLUG_TS_PATTERN.search(slug)
    if not match:
        raise ValueError(f"无法从 slug `{slug}` 解析时间戳，需包含 YYYY-MM-DD_HH-MM-SS")
    ts = match.group(0)
    return dt.datetime.strptime(ts, "%Y-%m-%d_%H-%M-%S")


if __name__ == "__main__":
    main()
