import json
from pathlib import Path

import pytest

import ddrecorder.config as config_module
from ddrecorder.config import AppConfig, load_config


@pytest.fixture(autouse=True)
def disable_account_refresh(monkeypatch):
    monkeypatch.setattr(config_module, "ensure_account_credentials", lambda *args, **kwargs: False)


def write_config(tmp_path: Path, content: dict) -> Path:
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(content), encoding="utf-8")
    return cfg_path


def test_load_config_resolves_relative_paths(tmp_path):
    (tmp_path / "log").mkdir()
    data_dir = tmp_path / "data_root"
    data_dir.mkdir()
    config_content = {
        "root": {
            "check_interval": 30,
            "print_interval": 45,
            "data_path": "./data_root",
            "logger": {"log_path": "./log", "log_level": "DEBUG"},
            "request_header": {"X-Test": "1"},
            "uploader": {"lines": "qn"},
        },
        "spec": [
            {
                "room_id": "123",
                "recorder": {"keep_raw_record": False},
                "uploader": {
                    "account": {
                        "access_token": "token",
                        "refresh_token": "refresh",
                        "cookies": {
                            "SESSDATA": "sess",
                            "bili_jct": "jct",
                            "DedeUserID": "1",
                            "DedeUserID__ckMd5": "md5",
                            "sid": "sid",
                        },
                    },
                    "record": {"upload_record": True, "title": "{date}", "desc": "demo"},
                },
            }
        ],
    }
    cfg_path = write_config(tmp_path, config_content)

    app_config: AppConfig = load_config(cfg_path)

    assert app_config.root.data_path == (cfg_path.parent / "data_root").resolve()
    assert app_config.root.logger.path == (cfg_path.parent / "log").resolve()
    assert app_config.root.request_header["X-Test"] == "1"
    assert app_config.root.uploader.lines == "qn"
    assert app_config.rooms[0].recorder.keep_raw_record is False


def test_load_config_supports_account_file(tmp_path):
    cookie_content = {
        "cookie_info": {
            "cookies": [
                {"name": "SESSDATA", "value": "abc"},
                {"name": "bili_jct", "value": "def"},
            ]
        },
        "token_info": {"access_token": "token123"},
    }
    cookie_path = tmp_path / "account.json"
    cookie_path.write_text(json.dumps(cookie_content), encoding="utf-8")

    config_content = {
        "root": {
            "account": {"default": str(cookie_path.relative_to(tmp_path))},
        },
        "spec": [
            {
                "room_id": "1",
                "uploader": {
                    "account": "default",
                },
            }
        ],
    }
    cfg_path = write_config(tmp_path, config_content)

    app_config = load_config(cfg_path)
    account = app_config.rooms[0].uploader.account

    assert account.access_token == "token123"
    assert account.cookies["SESSDATA"] == "abc"


def test_room_config_records_account_reference(tmp_path):
    config_content = {
        "root": {
            "account": {
                "main": {
                    "username": "u",
                    "password": "p",
                    "cookies": {},
                }
            }
        },
        "spec": [
            {
                "room_id": "1",
                "uploader": {
                    "account": "main",
                },
            }
        ],
    }
    cfg_path = write_config(tmp_path, config_content)
    app_config = load_config(cfg_path)
    uploader_cfg = app_config.rooms[0].uploader
    assert uploader_cfg.account_ref == "main"


def test_paths_relative_to_project_root_when_config_in_config_dir(tmp_path):
    project_root = tmp_path / "proj"
    config_dir = project_root / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.json"
    config_content = {
        "root": {
            "data_path": "./",
            "logger": {"log_path": "./log"},
        },
        "spec": [],
    }
    config_path.write_text(json.dumps(config_content), encoding="utf-8")

    app_config = load_config(config_path)
    assert app_config.root.data_path == project_root.resolve()
    assert app_config.root.logger.path == (project_root / "log").resolve()


def test_root_account_default_reuse(tmp_path):
    config_content = {
        "root": {
            "account": {
                "default": {
                    "username": "u",
                    "password": "p",
                    "cookies": {"SESSDATA": "sess"}
                }
            }
        },
        "spec": [
            {"room_id": "1", "uploader": {"account": "default"}}
        ],
    }
    cfg_path = write_config(tmp_path, config_content)
    app_config = load_config(cfg_path)
    uploader_cfg = app_config.rooms[0].uploader
    assert uploader_cfg.account.username == "u"
    assert uploader_cfg.account.cookies["SESSDATA"] == "sess"


def test_ensure_base_dirs_includes_danmu(tmp_path):
    config_content = {
        "root": {
            "data_path": str(tmp_path),
        },
        "spec": [],
    }
    cfg_path = write_config(tmp_path, config_content)
    app_config = load_config(cfg_path)
    danmu_dir = tmp_path / "data" / "danmu"
    assert danmu_dir.exists()


def test_recorder_enable_danmu_flag(tmp_path):
    config_content = {
        "spec": [
            {
                "room_id": "1",
                "recorder": {"keep_raw_record": False, "enable_danmu": True},
            }
        ]
    }
    cfg_path = write_config(tmp_path, config_content)
    app_config = load_config(cfg_path)
    assert app_config.rooms[0].recorder.enable_danmu is True


def test_danmu_ass_config_override(tmp_path):
    config_content = {
        "root": {
            "danmu_ass": {
                "font": "SimHei",
                "duration": 8,
                "row_count": 5,
            }
        },
        "spec": [],
    }
    cfg_path = write_config(tmp_path, config_content)
    app_config = load_config(cfg_path)
    assert app_config.root.danmu_ass.font == "SimHei"
    assert app_config.root.danmu_ass.duration == 8
    assert app_config.root.danmu_ass.row_count == 5
