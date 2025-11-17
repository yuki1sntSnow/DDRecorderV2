#!/usr/bin/env python3
"""Run ddrecorder for a fixed duration to validate recording + danmu capture."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from ddrecorder.config import load_config
from ddrecorder.logging import configure_logging
from ddrecorder.runner import RunnerController


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="快速跑一遍 ddrecorder 验证链路")
    parser.add_argument(
        "-c",
        "--config",
        default="config/test_config.json",
        help="配置文件 (默认: config/test_config.json)",
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=int,
        default=30,
        help="持续运行秒数 (默认: 30s)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    duration = max(args.duration, 1)

    config_path = Path(args.config).resolve()
    if not config_path.exists():
        raise SystemExit(f"配置文件不存在: {config_path}")

    app_config = load_config(config_path)
    for room in app_config.rooms:
        room.recorder.enable_danmu = True

    configure_logging(app_config.root.logger)

    controller = RunnerController(app_config)
    controller.start()
    print(f"[INFO] 运行中，{duration}s 后自动退出 (config={config_path})")
    try:
        time.sleep(duration)
    except KeyboardInterrupt:
        print("[INFO] 捕获 Ctrl+C，准备退出")
    finally:
        controller.stop()
        print("[INFO] 已停止，可在 data/ 与 log/ 下查看输出")


if __name__ == "__main__":
    main()
