from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from ddrecorder.danmaku_ass import jsonl_to_ass
from ddrecorder.config import DanmuAssConfig


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_jsonl_to_ass_generates_dialogue(tmp_path: Path) -> None:
    jsonl = tmp_path / "danmu.jsonl"
    start_time = dt.datetime(2024, 1, 1, 0, 0, 0)
    start_ms = int(start_time.timestamp() * 1000)
    write_jsonl(
        jsonl,
        [
            {"type": "danmaku", "text": "Hello", "time": start_ms + 1000},
            {"type": "other", "text": "ignored", "time": start_ms},
        ],
    )
    ass_path = tmp_path / "out.ass"
    assert jsonl_to_ass(jsonl, ass_path, start_time, DanmuAssConfig()) is True
    content = ass_path.read_text(encoding="utf-8")
    assert "Dialogue" in content
    assert "Hello" in content


def test_jsonl_to_ass_returns_false_when_empty(tmp_path: Path) -> None:
    jsonl = tmp_path / "danmu.jsonl"
    write_jsonl(jsonl, [{"type": "other", "text": "noop", "time": 0}])
    ass_path = tmp_path / "out.ass"
    result = jsonl_to_ass(jsonl, ass_path, dt.datetime.utcnow(), DanmuAssConfig())
    assert result is False
    assert not ass_path.exists()


def test_danmu_ass_config_customization(tmp_path: Path) -> None:
    jsonl = tmp_path / "danmu.jsonl"
    start_time = dt.datetime(2024, 1, 1, 0, 0, 0)
    ts = int(start_time.timestamp() * 1000)
    write_jsonl(jsonl, [{"type": "danmaku", "text": "Test", "time": ts}])
    ass_path = tmp_path / "out.ass"
    cfg = DanmuAssConfig(font="SimHei", font_size=24, duration=3, row_count=5, play_res_x=1280, scroll_end=-100)
    assert jsonl_to_ass(jsonl, ass_path, start_time, cfg)
    content = ass_path.read_text(encoding="utf-8")
    assert "Style: Danmaku,SimHei,24" in content
    assert "\\move(1280" in content
