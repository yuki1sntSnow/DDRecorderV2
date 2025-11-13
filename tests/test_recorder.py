import datetime as dt
import types

from ddrecorder.config import LoggerConfig, RecorderConfig, RootConfig, RootUploaderConfig
from ddrecorder.paths import RecordingPaths
from ddrecorder.recorder import LiveRecorder


class DummyRoom:
    def __init__(self):
        self.room_id = "123"
        self.room_title = "Test Room"
        self._states = [True, False]
        self.current_state = False

    def refresh(self):
        if self._states:
            self.current_state = self._states.pop(0)

    @property
    def is_live(self):
        return self.current_state

    def fetch_stream_urls(self):
        return ["http://example.com/fake.flv"]


def test_live_recorder_creates_fragments(tmp_path):
    start = dt.datetime(2024, 1, 1, 0, 0, 0)
    paths = RecordingPaths(tmp_path, "123", start)
    root_cfg = RootConfig(
        check_interval=30,
        print_interval=30,
        data_path=tmp_path,
        logger=LoggerConfig(path=tmp_path / "log", level="INFO"),
        request_header={},
        uploader=RootUploaderConfig(lines="AUTO"),
        accounts={},
    )
    recorder_cfg = RecorderConfig(keep_raw_record=True)
    room = DummyRoom()
    room.current_state = True
    recorder = LiveRecorder(room, paths, recorder_cfg, root_cfg)

    def fake_download(self, url, target_path):
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("fragment", encoding="utf-8")
        return True

    recorder._download = types.MethodType(fake_download, recorder)

    result = recorder.record()

    assert result is not None
    assert len(result.fragments) >= 1
    assert result.fragments[0].exists()
