import os
import time

from ddrecorder.cleanup import cleanup_directories
from ddrecorder.utils import UPLOAD_FAILED_MARK
from ddrecorder.config import AppConfig, LoggerConfig, RootConfig, RootUploaderConfig


def make_app_config(tmp_path):
    log_dir = tmp_path / "logs"
    root_cfg = RootConfig(
        check_interval=60,
        print_interval=60,
        data_path=tmp_path,
        logger=LoggerConfig(path=log_dir, level="INFO"),
        request_header={},
        uploader=RootUploaderConfig(lines="AUTO"),
        accounts={},
    )
    return AppConfig(root=root_cfg, rooms=[], config_path=tmp_path / "config.json")


def touch(path, mtime):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("data", encoding="utf-8")
    os.utime(path, (mtime, mtime))


def test_cleanup_removes_old_files(tmp_path):
    app_config = make_app_config(tmp_path)
    data_dir = tmp_path / "data" / "records"
    old_file = data_dir / "old.mp4"
    new_file = data_dir / "new.mp4"
    now = time.time()
    seven_days = 7 * 86400
    touch(old_file, now - seven_days - 100)
    touch(new_file, now - seven_days + 100)

    cleanup_directories(app_config, retention_days=7, now=now)

    assert not old_file.exists()
    assert new_file.exists()
    log_file = (tmp_path / "logs" / "clean.log")
    assert log_file.exists()


def test_cleanup_skips_failed_upload(tmp_path):
    app_config = make_app_config(tmp_path)
    data_dir = tmp_path / "data" / "records"
    data_dir.mkdir(parents=True, exist_ok=True)
    protected_dir = data_dir / "123_2024"
    protected_dir.mkdir()
    old_file = protected_dir / "old.mp4"
    now = time.time()
    touch(old_file, now - (7 * 86400) - 100)
    (protected_dir / UPLOAD_FAILED_MARK).write_text("fail", encoding="utf-8")

    cleanup_directories(app_config, retention_days=7, now=now)

    assert old_file.exists()
