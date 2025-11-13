from __future__ import annotations

import datetime as dt
from pathlib import Path


def rough_time(hour: int) -> str:
    if 0 <= hour < 6:
        return "凌晨"
    if 6 <= hour < 12:
        return "上午"
    if 12 <= hour < 18:
        return "下午"
    return "晚上"


def session_tokens(start: dt.datetime, room_name: str) -> dict:
    return {
        "date": start.strftime("%Y年%m月%d日"),
        "year": start.year,
        "month": start.month,
        "day": start.day,
        "hour": start.hour,
        "minute": start.minute,
        "second": start.second,
        "rough_time": rough_time(start.hour),
        "room_name": room_name,
    }


UPLOAD_FAILED_MARK = ".upload_failed"


def mark_upload_failed(directory: Path | str, reason: str = "") -> None:
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    marker = path / UPLOAD_FAILED_MARK
    content = f"failed_at={dt.datetime.now():%Y-%m-%d %H:%M:%S} reason={reason}"
    marker.write_text(content, encoding="utf-8")


def clear_upload_failed(directory: Path | str) -> None:
    marker = Path(directory) / UPLOAD_FAILED_MARK
    if marker.exists():
        marker.unlink()


def has_upload_failed_marker(directory: Path | str) -> bool:
    return (Path(directory) / UPLOAD_FAILED_MARK).exists()
