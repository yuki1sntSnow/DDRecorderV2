# Provide a lightweight stub of biliup before importing the uploader module.
import sys
import types
import datetime as dt

fake_bili_module = types.ModuleType("biliup.plugins.bili_webup")


class FakeData(list):
    def __init__(self):
        super().__init__()
        self.desc = ""
        self.title = ""
        self.tid = 0
        self.tags = []

    def set_tag(self, tags):
        self.tags = list(tags)


class FakeBiliBili:
    def __init__(self, _):
        self.video = None
        self.uploaded = []
        self.cover_path = None
        self.cookie_payload = None
        self.closed = False

    def login_by_cookies(self, payload):
        self.cookie_payload = payload

    def upload_file(self, path, lines="AUTO"):
        self.uploaded.append((path, lines))
        return {"path": path}

    def cover_up(self, cover_path):
        self.cover_path = cover_path
        return "COVER_ID"

    def submit(self):
        return {"code": 0, "data": {"aid": 42, "bvid": "BVfake"}}

    def close(self):
        self.closed = True


fake_bili_module.Data = FakeData
fake_bili_module.BiliBili = FakeBiliBili
sys.modules.setdefault("biliup", types.ModuleType("biliup"))
sys.modules.setdefault("biliup.plugins", types.ModuleType("biliup.plugins"))
sys.modules["biliup.plugins.bili_webup"] = fake_bili_module

from ddrecorder.config import (
    AccountConfig,
    AppConfig,
    LoggerConfig,
    RecorderConfig,
    RecordUploadConfig,
    RootConfig,
    RootUploaderConfig,
    RoomConfig,
    SpecUploaderConfig,
)
from ddrecorder.uploader import BiliUploader


def build_configs(tmp_path):
    logger_cfg = LoggerConfig(path=tmp_path / "log", level="INFO")
    root_cfg = RootConfig(
        check_interval=30,
        print_interval=30,
        data_path=tmp_path,
        logger=logger_cfg,
        request_header={},
        uploader=RootUploaderConfig(lines="AUTO"),
        accounts={},
    )
    account_cfg = AccountConfig(cookies={"SESSDATA": "sess"})
    record_cfg = RecordUploadConfig(
        upload_record=True,
        keep_record_after_upload=True,
        split_interval=3600,
        title="{room_name}-{date}",
        tid=27,
        tags=["tag"],
        desc="{date}",
        cover="cover.png",
    )
    room_cfg = RoomConfig(
        room_id="1",
        recorder=RecorderConfig(keep_raw_record=True),
        uploader=SpecUploaderConfig(
            copyright=2,
            account=account_cfg,
            record=record_cfg,
        ),
    )
    config_dir = tmp_path / "config_dir"
    config_dir.mkdir()
    cover_path = config_dir / "cover.png"
    cover_path.write_text("cover", encoding="utf-8")
    app_config = AppConfig(root=root_cfg, rooms=[room_cfg], config_path=config_dir / "config.json")
    return app_config, room_cfg


class DummyRoom:
    def __init__(self):
        self.room_id = "1"
        self.room_title = "Room"


def test_upload_record_success(tmp_path):
    app_config, room_cfg = build_configs(tmp_path)
    splits_dir = tmp_path / "splits"
    splits_dir.mkdir()
    split_files = []
    for idx in range(2):
        file_path = splits_dir / f"split_{idx}.mp4"
        file_path.write_bytes(b"1" * (1_048_576 + 10))
        split_files.append(file_path)

    uploader = BiliUploader(app_config, room_cfg, DummyRoom())
    result = uploader.upload_record(dt.datetime.now(), split_files)

    assert result == {"avid": 42, "bvid": "BVfake"}
    assert len(uploader.client.uploaded) == 2
    assert uploader.client.cover_path is not None
