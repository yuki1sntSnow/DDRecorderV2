import datetime as dt

from scripts import process_session


def test_parse_slug_time_allows_suffix():
    slug = "22508985_2025-11-13_18-01-54_retry"
    parsed = process_session._parse_slug_time(slug)
    assert parsed == dt.datetime(2025, 11, 13, 18, 1, 54)


def test_parse_slug_time_invalid():
    try:
        process_session._parse_slug_time("invalid_slug")
    except ValueError as exc:
        assert "无法从 slug" in str(exc)
    else:
        raise AssertionError("expected ValueError")
