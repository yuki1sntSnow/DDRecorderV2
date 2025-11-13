from __future__ import annotations

import datetime as dt
import logging
import sys
from pathlib import Path

from .config import LoggerConfig

_STAGE_NAMES = ["detect", "record", "merge", "split", "upload"]
_stage_loggers: dict[str, logging.Logger] = {}
_ffmpeg_log_path: Path | None = None
_timestamp: str = ""


def _resolve_level(level_name: str) -> int:
    try:
        return getattr(logging, level_name.upper())
    except AttributeError:
        return logging.INFO


class MaxLevelFilter(logging.Filter):
    def __init__(self, max_level: int) -> None:
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        return record.levelno <= self.max_level


class MinLevelFilter(logging.Filter):
    def __init__(self, min_level: int) -> None:
        super().__init__()
        self.min_level = min_level

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        return record.levelno >= self.min_level


def configure_logging(logger_cfg: LoggerConfig) -> Path:
    global _ffmpeg_log_path, _timestamp
    logger_cfg.path.mkdir(parents=True, exist_ok=True)
    _timestamp = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = logger_cfg.path / f"DDRecorder_{_timestamp}.log"
    logging.basicConfig(
        level=_resolve_level(logger_cfg.level),
        format="%(asctime)s %(threadName)s %(filename)s:%(lineno)d %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
        force=True,
    )
    _setup_stage_loggers(logger_cfg.path)
    ffmpeg_dir = logger_cfg.path / "ffmpeg"
    ffmpeg_dir.mkdir(parents=True, exist_ok=True)
    _ffmpeg_log_path = ffmpeg_dir / f"ffmpeg_{_timestamp}.log"
    _ffmpeg_log_path.touch(exist_ok=True)
    return log_file


def _setup_stage_loggers(base_path: Path) -> None:
    for stage in _STAGE_NAMES:
        logger = logging.getLogger(f"ddrecorder.{stage}")
        logger.setLevel(logging.DEBUG)
        logger.handlers = []
        logger.propagate = False

        info_handler = logging.FileHandler(base_path / f"{stage}_{_timestamp}_info.log", encoding="utf-8")
        info_handler.setLevel(logging.DEBUG)
        info_handler.addFilter(MaxLevelFilter(logging.INFO))

        error_handler = logging.FileHandler(base_path / f"{stage}_{_timestamp}_error.log", encoding="utf-8")
        error_handler.setLevel(logging.WARNING)
        error_handler.addFilter(MinLevelFilter(logging.WARNING))

        logger.addHandler(info_handler)
        logger.addHandler(error_handler)
        _stage_loggers[stage] = logger


def get_stage_logger(stage: str) -> logging.Logger:
    if stage not in _stage_loggers:
        logger = logging.getLogger(f"ddrecorder.{stage}")
        logger.setLevel(logging.DEBUG)
        return logger
    return _stage_loggers[stage]


def get_ffmpeg_log_path() -> Path:
    if _ffmpeg_log_path is None:
        raise RuntimeError("FFmpeg log path not initialized. Call configure_logging() first.")
    return _ffmpeg_log_path
