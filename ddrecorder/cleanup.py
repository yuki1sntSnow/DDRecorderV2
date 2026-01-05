from __future__ import annotations

import datetime as dt
import logging
import os
import threading
import time
from pathlib import Path
from typing import Tuple, List

from .config import AppConfig, load_config
from .utils import UPLOAD_FAILED_MARK, has_upload_failed_marker

DANMU_RETENTION_DAYS = 30


def cleanup_directories(
    app_config: AppConfig, retention_days: int = 7, now: float | None = None
) -> None:
    now = now or time.time()
    log_dir = app_config.root.logger.path
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "clean.log"

    targets = _build_targets(app_config, retention_days)
    logging.info("开始清理本地文件，保留 %s 天", retention_days)
    with log_file.open("a", encoding="utf-8") as log:
        writer = _make_log_writer(log)
        writer(f"Start cleanup (retention={retention_days}d)")
        total_files_removed = 0
        total_dirs_removed = 0
        for target, keep_days in targets:
            if not target.exists():
                writer(f"Skip {target} (not exists)")
                logging.debug("清理跳过不存在的目录 %s", target)
                continue
            threshold = now - keep_days * 86400
            before_files, before_dirs = _count_entries(target)
            files_removed, dirs_removed = _purge_path(target, threshold, writer)
            after_files, after_dirs = _count_entries(target)
            total_files_removed += files_removed
            total_dirs_removed += dirs_removed
            writer(
                f"Cleaned {target} (retention={keep_days}d, removed files={files_removed}, removed dirs={dirs_removed}, remaining files={after_files}, remaining dirs={after_dirs})"
            )
            logging.info(
                "目录 %s 清理完成，删除文件 %s，删除目录 %s",
                target,
                files_removed,
                dirs_removed,
            )
        writer(
            f"Done cleanup, total removed files={total_files_removed}, dirs={total_dirs_removed}"
        )
    logging.info("本次清理完成")


def _build_targets(
    app_config: AppConfig, default_retention: int
) -> List[tuple[Path, int]]:
    base = app_config.root.data_path / "data"
    log_dir = app_config.root.logger.path
    return [
        (base / "danmu", max(default_retention, DANMU_RETENTION_DAYS)),
        (base / "merge_confs", default_retention),
        (base / "merged", default_retention),
        (base / "outputs", default_retention),
        (base / "records", default_retention),
        (base / "splits", default_retention),
        (log_dir, default_retention),
    ]


def _purge_path(target: Path, threshold: float, writer) -> Tuple[int, int]:
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
                    writer(f"Removed file {file_path}")
            except FileNotFoundError:
                continue
        for dirname in dirs:
            dir_path = root_path / dirname
            try:
                if has_upload_failed_marker(dir_path):
                    logging.debug("跳过带失败标记的子目录 %s", dir_path)
                    continue
                if not any(dir_path.iterdir()):
                    dir_path.rmdir()
                    dirs_removed += 1
                    writer(f"Removed dir {dir_path}")
            except (FileNotFoundError, PermissionError):
                continue
    return files_removed, dirs_removed


def _count_entries(target: Path) -> Tuple[int, int]:
    files = 0
    dirs = 0
    if not target.exists():
        return files, dirs
    for _, dirnames, filenames in os.walk(target):
        files += len(filenames)
        dirs += len(dirnames)
    return files, dirs


def _make_log_writer(log) -> callable:
    def _writer(message: str) -> None:
        log.write(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")
        log.flush()

    return _writer


class CleanupScheduler(threading.Thread):
    def __init__(
        self,
        app_config: AppConfig,
        retention_days: int = 7,
        interval_hours: float = 24.0,
    ):
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
