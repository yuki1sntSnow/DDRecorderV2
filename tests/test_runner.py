import datetime as dt
import threading
import time

import pytest

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
from ddrecorder import runner as runner_module
from ddrecorder.state import RunnerState


class FakeRoom:
    def __init__(self, room_id, headers=None):
        self.room_id = room_id
        self.room_title = "Room"
        self.states = [True, False]
        self.current_state = False

    def refresh(self):
        if self.states:
            self.current_state = self.states.pop(0)

    @property
    def is_live(self):
        return self.current_state


class FakeRecorder:
    def __init__(self, room, paths, recorder_cfg, root_cfg):
        self.paths = paths

    def record(self):
        return object()


class FakeProcessor:
    def __init__(self, paths, recorder_cfg):
        self.paths = paths
        self.recorder_cfg = recorder_cfg

    def run(self):
        self.paths.splits_dir.mkdir(parents=True, exist_ok=True)
        return object()

    def split(self, split_interval):
        file_path = self.paths.splits_dir / "fake_0000.mp4"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(b"1" * (1_048_576 + 10))
        return [file_path]


class FakeUploader:
    def __init__(self, *args, **kwargs):
        self.closed = False

    def upload_record(self, start, splits):
        return {"bvid": "BVfake"}

    def close(self):
        self.closed = True


@pytest.fixture
def app_and_room(tmp_path):
    root_cfg = RootConfig(
        check_interval=1,
        print_interval=1,
        data_path=tmp_path,
        logger=LoggerConfig(path=tmp_path / "log", level="INFO"),
        request_header={},
        uploader=RootUploaderConfig(lines="AUTO"),
        accounts={},
    )
    account_cfg = AccountConfig(cookies={"SESSDATA": "sess"})
    record_cfg = RecordUploadConfig(upload_record=True, keep_record_after_upload=True)
    room_cfg = RoomConfig(
        room_id="1",
        recorder=RecorderConfig(keep_raw_record=True),
        uploader=SpecUploaderConfig(account=account_cfg, record=record_cfg),
    )
    app_config = AppConfig(root=root_cfg, rooms=[room_cfg], config_path=tmp_path / "config.json")
    return app_config, room_cfg


def test_room_runner_lifecycle(monkeypatch, app_and_room):
    app_config, room_cfg = app_and_room
    monkeypatch.setattr(runner_module, "BiliLiveRoom", FakeRoom)
    monkeypatch.setattr(runner_module, "LiveRecorder", FakeRecorder)
    monkeypatch.setattr(runner_module, "RecordingProcessor", FakeProcessor)
    monkeypatch.setattr(runner_module, "BiliUploader", FakeUploader)
    monkeypatch.setattr(runner_module.RoomRunner, "sleep_with_stop", lambda self, seconds: None)
    cleared = {}
    marked = {}
    monkeypatch.setattr(runner_module, "clear_upload_failed", lambda path: cleared.setdefault("path", path))
    monkeypatch.setattr(runner_module, "mark_upload_failed", lambda path, reason="": marked.setdefault("path", path))

    runner = runner_module.RoomRunner(app_config, room_cfg)
    runner.start()
    time.sleep(0.2)
    runner.stop()
    runner.join(timeout=1)

    assert runner.state in (RunnerState.IDLE, RunnerState.ERROR)
    assert "path" in cleared
    assert "path" not in marked


def test_room_runner_marks_failure(monkeypatch, app_and_room):
    app_config, room_cfg = app_and_room
    monkeypatch.setattr(runner_module, "BiliLiveRoom", FakeRoom)
    monkeypatch.setattr(runner_module, "LiveRecorder", FakeRecorder)
    monkeypatch.setattr(runner_module, "RecordingProcessor", FakeProcessor)

    class FailingUploader(FakeUploader):
        def upload_record(self, start, splits):
            return None

    monkeypatch.setattr(runner_module, "BiliUploader", FailingUploader)
    monkeypatch.setattr(runner_module.RoomRunner, "sleep_with_stop", lambda self, seconds: None)
    cleared = {}
    marked = {}
    monkeypatch.setattr(runner_module, "clear_upload_failed", lambda path: cleared.setdefault("path", path))
    monkeypatch.setattr(runner_module, "mark_upload_failed", lambda path, reason="": marked.setdefault("path", path))

    runner = runner_module.RoomRunner(app_config, room_cfg)
    runner.start()
    time.sleep(0.2)
    runner.stop()
    runner.join(timeout=1)

    assert "path" in marked
