from __future__ import annotations

import datetime as dt
import logging
import os
import threading
import time
from pathlib import Path
from typing import Tuple

from .config import AppConfig, load_config
from .utils import UPLOAD_FAILED_MARK, has_upload_failed_marker


def cleanup_directories(app_config: AppConfig, retention_days: int = 7, now: float | None = None) -> None:
    now = now or time.time()
    threshold = now - retention_days * 86400
    log_dir = app_config.root.logger.path
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "clean.log"

    targets = _build_targets(app_config)
    logging.info("开始清理本地文件，保留 %s 天", retention_days)
    with log_file.open("a", encoding="utf-8") as log:
        log.write(f"Start {dt.datetime.now():%Y-%m-%d %H:%M:%S}\n")
        for target in targets:
            if not target.exists():
                log.write(f"Skip {target}\n")
                logging.debug("清理跳过不存在的目录 %s", target)
                continue
            files_removed, dirs_removed = _purge_path(target, threshold)
            log.write(
                f"Cleaned {target} (files removed: {files_removed}, dirs removed: {dirs_removed})\n"
            )
            logging.info("目录 %s 清理完成，删除文件 %s，删除目录 %s", target, files_removed, dirs_removed)
        log.write(f"Done {dt.datetime.now():%Y-%m-%d %H:%M:%S}\n")
    logging.info("本次清理完成")


def _build_targets(app_config: AppConfig) -> list[Path]:
    base = app_config.root.data_path / "data"
    log_dir = app_config.root.logger.path
    return [
        base / "cred",
        base / "danmu",
        base / "merge_confs",
        base / "merged",
        base / "outputs",
        base / "records",
        base / "splits",
        log_dir,
    ]


def _purge_path(target: Path, threshold: float) -> Tuple[int, int]:
    files_removed = 0
    dirs_removed = 0
    for root, dirs, files in os.walk(target, topdown=False):
        root_path = Path(root)
        if has_upload_failed_marker(root_path):
            logging.debug("检测到上传失败标记，跳过目录 %s", root_path)
            continue
        for filename in files:
            if filename == UPLOAD_FAILED_MARK:
                continue
            file_path = root_path / filename
            try:
                if file_path.stat().st_mtime < threshold:
                    file_path.unlink()
                    files_removed += 1
            except FileNotFoundError:
                continue
        for dirname in dirs:
            dir_path = root_path / dirname
            try:
                if has_upload_failed_marker(dir_path):
                    logging.debug("跳过带失败标记的子目录 %s", dir_path)
                    continue
                if not any(dir_path.iterdir()) and dir_path.stat().st_mtime < threshold:
                    dir_path.rmdir()
                    dirs_removed += 1
            except (FileNotFoundError, PermissionError):
                continue
    return files_removed, dirs_removed


class CleanupScheduler(threading.Thread):
    def __init__(self, app_config: AppConfig, retention_days: int = 7, interval_hours: float = 24.0):
        super().__init__(name="CleanupScheduler", daemon=True)
        self.app_config = app_config
        self.retention_days = retention_days
        self.interval_seconds = max(interval_hours, 0.1) * 3600
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            cleanup_directories(self.app_config, self.retention_days)


def perform_cleanup(config_path: Path, retention_days: int = 7) -> None:
    app_config = load_config(config_path)
    cleanup_directories(app_config, retention_days)
