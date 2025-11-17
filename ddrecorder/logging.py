from __future__ import annotations

import datetime as dt
import logging
import sys
from pathlib import Path

from .config import LoggerConfig

_STAGE_NAMES = ["detect", "record", "process", "upload"]
_stage_loggers: dict[str, logging.Logger] = {}
_ffmpeg_log_base: Path | None = None
_log_base_path: Path | None = None
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
    global _ffmpeg_log_base, _timestamp, _log_base_path
    logger_cfg.path.mkdir(parents=True, exist_ok=True)
    _timestamp = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    _log_base_path = logger_cfg.path
    log_file = logger_cfg.path / f"DDRecorder_{_timestamp}.log"
    formatter = logging.Formatter(
        fmt="%(asctime)s %(threadName)s %(filename)s:%(lineno)d %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.basicConfig(
        level=_resolve_level(logger_cfg.level),
        format=formatter._fmt,
        datefmt=formatter.datefmt,
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )
    for handler in logging.getLogger().handlers:
        handler.setFormatter(formatter)
    _setup_stage_directories(logger_cfg.path)
    _ffmpeg_log_base = (logger_cfg.path / "ffmpeg").resolve()
    _ffmpeg_log_base.mkdir(parents=True, exist_ok=True)
    return log_file


def _setup_stage_directories(base_path: Path) -> None:
    for stage in _STAGE_NAMES:
        (base_path / stage).mkdir(parents=True, exist_ok=True)


def get_stage_logger(stage: str, _: str | None = None) -> logging.Logger:
    if stage in _stage_loggers:
        return _stage_loggers[stage]

    logger = logging.getLogger(f"ddrecorder.{stage}")
    logger.setLevel(logging.DEBUG)
    logger.handlers = []
    logger.propagate = False

    base_path = _log_base_path or Path(".")
    stage_dir = base_path / stage
    stage_dir.mkdir(parents=True, exist_ok=True)

    info_path = stage_dir / "info.log"
    error_path = stage_dir / "error.log"
    formatter = logging.Formatter(
        fmt="%(asctime)s %(threadName)s %(filename)s:%(lineno)d %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    info_handler = logging.FileHandler(info_path, encoding="utf-8", delay=True)
    info_handler.setLevel(logging.DEBUG)
    info_handler.addFilter(MaxLevelFilter(logging.INFO))
    info_handler.setFormatter(formatter)

    error_handler = logging.FileHandler(error_path, encoding="utf-8", delay=True)
    error_handler.setLevel(logging.WARNING)
    error_handler.addFilter(MinLevelFilter(logging.WARNING))
    error_handler.setFormatter(formatter)

    logger.addHandler(info_handler)
    logger.addHandler(error_handler)
    _stage_loggers[stage] = logger
    return logger


def get_ffmpeg_log_path(room_id: str) -> Path:
    if _ffmpeg_log_base is None:
        raise RuntimeError("FFmpeg log path not initialized. Call configure_logging() first.")
    log_path = _ffmpeg_log_base / f"ffmpeg_{room_id}_{_timestamp}.log"
    log_path.touch(exist_ok=True)
    return log_path
