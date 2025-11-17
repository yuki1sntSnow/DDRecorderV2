from pathlib import Path

import logging

from ddrecorder import logging as logging_module
from ddrecorder.config import LoggerConfig


def test_stage_logs_and_ffmpeg_path(tmp_path):
    cfg = LoggerConfig(path=tmp_path / "log", level="INFO")
    logging_module.configure_logging(cfg)

    detect_logger = logging_module.get_stage_logger("detect", "room1")
    detect_logger.info("info message")
    detect_logger.error("error message")

    stage_dir = tmp_path / "log" / "detect"
    info_file = stage_dir / "info.log"
    error_file = stage_dir / "error.log"

    assert info_file.exists()
    assert error_file.exists()
    assert "info message" in info_file.read_text(encoding="utf-8")
    assert "error message" in error_file.read_text(encoding="utf-8")

    ffmpeg_log = logging_module.get_ffmpeg_log_path("room1")
    assert ffmpeg_log.exists()
    assert ffmpeg_log.parent.name == "ffmpeg"
