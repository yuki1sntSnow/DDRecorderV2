from pathlib import Path

import logging

from ddrecorder import logging as logging_module
from ddrecorder.config import LoggerConfig


def test_stage_logs_and_ffmpeg_path(tmp_path):
    cfg = LoggerConfig(path=tmp_path / "log", level="INFO")
    logging_module.configure_logging(cfg)

    detect_logger = logging_module.get_stage_logger("detect")
    detect_logger.info("info message")
    detect_logger.error("error message")

    stage_files = sorted((tmp_path / "log").glob("detect_*.log"))
    info_files = sorted((tmp_path / "log").glob("detect_*_info.log"))
    error_files = sorted((tmp_path / "log").glob("detect_*_error.log"))

    assert stage_files  # stage loggers created per stage
    assert info_files and error_files

    ffmpeg_log = logging_module.get_ffmpeg_log_path()
    assert ffmpeg_log.exists()
    assert ffmpeg_log.parent.name == "ffmpeg"
