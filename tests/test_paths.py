import datetime as dt

from ddrecorder.paths import RecordingPaths


def test_recording_paths_creates_directories(tmp_path):
    start = dt.datetime(2024, 1, 2, 3, 4, 5)
    paths = RecordingPaths(tmp_path, "9876", start)

    paths.ensure_session_dirs()

    assert paths.records_dir.exists()
    assert paths.outputs_dir.exists()
    assert paths.splits_dir.exists()
    assert paths.merge_conf_path.parent.exists()
    assert paths.merged_file.parent.exists()
    assert paths.slug == "9876_2024-01-02_03-04-05"


def test_fragment_path_uses_current_time(tmp_path):
    start = dt.datetime.now()
    paths = RecordingPaths(tmp_path, "1", start)
    fragment = paths.fragment_path(start)
    assert fragment.parent == paths.records_dir
    assert fragment.name.startswith("1_")
