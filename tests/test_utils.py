import datetime as dt

from ddrecorder.utils import (
    rough_time,
    session_tokens,
    mark_upload_failed,
    clear_upload_failed,
    has_upload_failed_marker,
)


def test_rough_time_ranges():
    assert rough_time(1) == "凌晨"
    assert rough_time(7) == "上午"
    assert rough_time(13) == "下午"
    assert rough_time(20) == "晚上"


def test_session_tokens_format():
    start = dt.datetime(2023, 5, 6, 7, 8, 9)
    tokens = session_tokens(start, "DemoRoom")
    assert tokens["date"] == "2023年05月06日"
    assert tokens["rough_time"] == "上午"
    assert tokens["room_name"] == "DemoRoom"


def test_upload_failed_marker(tmp_path):
    assert not has_upload_failed_marker(tmp_path)
    mark_upload_failed(tmp_path, "test")
    assert has_upload_failed_marker(tmp_path)
    clear_upload_failed(tmp_path)
    assert not has_upload_failed_marker(tmp_path)
