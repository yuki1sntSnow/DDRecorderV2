from __future__ import annotations

import datetime as dt
import logging
import sys
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler

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
    logger.setLevel(logging.INFO)
    logger.handlers = []
    logger.propagate = False

    base_path = _log_base_path or Path(".")
    stage_dir = base_path / stage
    stage_dir.mkdir(parents=True, exist_ok=True)

    stage_path = stage_dir / f"{stage}.log"
    base_name = stage_path.name
    formatter = logging.Formatter(
        fmt="%(asctime)s %(threadName)s %(filename)s:%(lineno)d %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = TimedRotatingFileHandler(
        stage_path,
        when="midnight",
        interval=1,
        backupCount=0,  # cleanup task will handle old files
        encoding="utf-8",
        delay=True,
    )
    handler.suffix = "%Y-%m-%d"

    def _namer(default_name: str, *, base=base_name, prefix=stage) -> str:
        """
        Rename rotated file from 'detect.log.2025-11-23' to 'detect.2025-11-23.log'
        so the timestamp sits before the .log suffix.
        """
        path = Path(default_name)
        timestamp = path.name.removeprefix(f"{base}.")
        if not timestamp:
            return default_name
        return str(path.with_name(f"{prefix}.{timestamp}.log"))

    handler.namer = _namer
    handler.setLevel(logging.INFO)
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    _stage_loggers[stage] = logger
    return logger


def get_ffmpeg_log_path(room_id: str) -> Path:
    if _ffmpeg_log_base is None:
        raise RuntimeError("FFmpeg log path not initialized. Call configure_logging() first.")
    log_path = _ffmpeg_log_base / f"ffmpeg_{room_id}_{_timestamp}.log"
    log_path.touch(exist_ok=True)
    return log_path
