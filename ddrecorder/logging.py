from __future__ import annotations

import datetime as dt
import logging
import sys
from pathlib import Path

from .config import LoggerConfig


def _resolve_level(level_name: str) -> int:
    try:
        return getattr(logging, level_name.upper())
    except AttributeError:
        return logging.INFO


def configure_logging(logger_cfg: LoggerConfig) -> Path:
    logger_cfg.path.mkdir(parents=True, exist_ok=True)
    log_file = logger_cfg.path / f"DDRecorder_{dt.datetime.now():%Y-%m-%d_%H-%M-%S}.log"
    logging.basicConfig(
        level=_resolve_level(logger_cfg.level),
        format="%(asctime)s %(threadName)s %(filename)s:%(lineno)d %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )
    return log_file
