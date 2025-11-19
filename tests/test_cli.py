import datetime as dt
import json

from pathlib import Path

from ddrecorder import cli
from ddrecorder.config import (
    AccountConfig,
    AppConfig,
    DanmuAssConfig,
    LoggerConfig,
    RecorderConfig,
    RecordUploadConfig,
    RootConfig,
    RootUploaderConfig,
    RoomConfig,
    SpecUploaderConfig,
)


def build_app_config(tmp_path: Path) -> tuple[AppConfig, RoomConfig]:
    logger_cfg = LoggerConfig(path=tmp_path / "log", level="INFO")
    root_cfg = RootConfig(
        check_interval=1,
        print_interval=1,
        data_path=tmp_path,
        logger=logger_cfg,
        request_header={},
        uploader=RootUploaderConfig(lines="AUTO"),
        accounts={},
        danmu_ass=DanmuAssConfig(),
    )
    room_cfg = RoomConfig(
        room_id="123",
        recorder=RecorderConfig(keep_raw_record=True),
        uploader=SpecUploaderConfig(
            copyright=2,
            account=AccountConfig(cookies={"SESSDATA": "sess"}),
            record=RecordUploadConfig(upload_record=True),
        ),
    )
    app_config = AppConfig(root=root_cfg, rooms=[room_cfg], config_path=tmp_path / "config.json")
    return app_config, room_cfg


def test_select_room_config_infers_from_directory(monkeypatch, tmp_path):
    app_config, room_cfg = build_app_config(tmp_path)
    directory = tmp_path / "123_2024-01-01_00-00-00"
    directory.mkdir()

    selected = cli._select_room_config(app_config, directory, None)
    assert selected.room_id == room_cfg.room_id


def test_manual_upload_invokes_uploader(monkeypatch, tmp_path):
    app_config, room_cfg = build_app_config(tmp_path)
    media_dir = tmp_path / "123_2024-01-01_00-00-00"
    media_dir.mkdir()
    for idx in range(2):
        file_path = media_dir / f"part_{idx}.mp4"
        file_path.write_bytes(b"a" * 2_000_000)

    class DummyRoom:
        def __init__(self, room_id, headers=None):
            self.room_id = room_id
            self.room_title = "Dummy"

    uploads = {}

    class DummyUploader:
        def __init__(self, app_cfg, room_cfg, room):
            uploads["init"] = True

        def upload_record(self, start, splits):
            uploads["start"] = start
            uploads["count"] = len(splits)
            return {"bvid": "BVtest"}

        def close(self):
            uploads["closed"] = True

    monkeypatch.setattr(cli, "BiliLiveRoom", DummyRoom)
    monkeypatch.setattr(cli, "BiliUploader", DummyUploader)
    cleared = {}
    marked = {}
    monkeypatch.setattr(cli, "clear_upload_failed", lambda path: cleared.setdefault("path", path))
    monkeypatch.setattr(cli, "mark_upload_failed", lambda path, reason="": marked.setdefault("path", path))

    assert cli._manual_upload(app_config, room_cfg, media_dir)
    assert uploads.get("count") == 2
    assert uploads.get("closed") is True
    assert isinstance(uploads.get("start"), dt.datetime)
    assert "path" in cleared
    assert "path" not in marked


def test_manual_split_invokes_processor(monkeypatch, tmp_path):
    config = {
        "root": {
            "check_interval": 1,
            "print_interval": 1,
            "data_path": str(tmp_path),
            "logger": {"log_path": str(tmp_path / "log"), "log_level": "INFO"},
            "request_header": {},
            "uploader": {"lines": "AUTO"},
            "account": {},
        },
        "spec": [
            {
                "room_id": "123",
                "recorder": {},
                "uploader": {"record": {"upload_record": True, "split_interval": 777}},
            }
        ],
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")
    slug = "123_2024-01-01_00-00-00"
    merged_dir = tmp_path / "data" / "merged"
    merged_dir.mkdir(parents=True)
    merged_file = merged_dir / f"{slug}_merged.mp4"
    merged_file.write_bytes(b"00")

    calls = {}

    class DummyProcessor:
        def __init__(self, paths, recorder_cfg, danmu_cfg):
            calls["paths"] = paths

        def split(self, interval, merged_override=None, splits_dir=None):
            calls["interval"] = interval
            calls["merged_override"] = merged_override
            calls["splits_dir"] = splits_dir
            return [splits_dir / "part_0000.mp4"]

        def close(self):
            calls["closed"] = True

    monkeypatch.setattr(cli, "RecordingProcessor", DummyProcessor)

    cli.manual_split_from_cli(cfg_path, merged_file)

    assert calls["interval"] == 777
    assert calls["merged_override"] == merged_file
    assert calls["splits_dir"] == tmp_path / "data" / "splits" / slug
    assert calls["closed"] is True
