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
    stage_file = stage_dir / "detect.log"

    assert stage_file.exists()
    text = stage_file.read_text(encoding="utf-8")
    assert "info message" in text
    assert "error message" in text

    ffmpeg_log = logging_module.get_ffmpeg_log_path("room1")
    assert ffmpeg_log.exists()
    assert ffmpeg_log.parent.name == "ffmpeg"
