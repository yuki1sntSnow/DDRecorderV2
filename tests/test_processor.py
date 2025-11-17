import datetime as dt
from pathlib import Path

import ffmpeg
import pytest

from ddrecorder.config import RecorderConfig, DanmuAssConfig
from ddrecorder.paths import RecordingPaths
from ddrecorder.processor import RecordingProcessor


@pytest.fixture
def recording_paths(tmp_path):
    start = dt.datetime(2024, 1, 1, 0, 0, 0)
    paths = RecordingPaths(tmp_path, "555", start)
    paths.ensure_session_dirs()
    return paths


def test_processor_run_and_split(monkeypatch, recording_paths):
    fragment = recording_paths.records_dir / "555_2024-01-01_00-00-00.flv"
    fragment.write_bytes(b"0" * (1_048_576 + 10))

    created_files = []

    def fake_run_cmd(cmd):
        target = Path(cmd[-1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"data")
        created_files.append(target)
        return True

    monkeypatch.setattr(RecordingProcessor, "_run_cmd", staticmethod(fake_run_cmd))
    monkeypatch.setattr(
        ffmpeg, "probe", lambda *_args, **_kwargs: {"format": {"duration": 120}}
    )

    processor = RecordingProcessor(
        recording_paths, RecorderConfig(keep_raw_record=False), DanmuAssConfig()
    )
    result = processor.run()

    assert result is not None
    assert recording_paths.merged_file.exists()

    splits = processor.split(60)
    assert len(splits) == 3
    for split_file in splits:
        assert split_file.exists()
