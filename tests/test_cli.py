import datetime as dt

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
