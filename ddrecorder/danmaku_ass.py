from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .config import DanmuAssConfig


def jsonl_to_ass(
    jsonl_path: Path,
    ass_path: Path,
    session_start: dt.datetime,
    style: DanmuAssConfig,
) -> bool:
    if not jsonl_path.exists():
        return False
    try:
        session_ms = int(session_start.timestamp() * 1000)
    except OSError:
        session_ms = 0

    records: list[tuple[float, str]] = []
    with jsonl_path.open("r", encoding="utf-8") as src:
        for line in src:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("type") != "danmaku":
                continue
            text = str(payload.get("text", "")).strip()
            if not text:
                continue
            timestamp = payload.get("time")
            if not isinstance(timestamp, (int, float)):
                continue
            offset = (timestamp - session_ms) / 1000
            if offset < 0:
                offset = 0
            records.append((offset, text))

    if not records:
        return False

    records.sort(key=lambda item: item[0])
    ass_path.parent.mkdir(parents=True, exist_ok=True)
    header = _build_header(style)
    with ass_path.open("w", encoding="utf-8") as dst:
        dst.write(header)
        for idx, (start, text) in enumerate(records):
            end = start + style.duration
            row = idx % max(style.row_count, 1)
            y = style.margin_top + row * style.line_height
            start_str = _format_ts(start)
            end_str = _format_ts(end)
            safe_text = _escape(text)
            move_effect = f"\\move({style.play_res_x},{y},{style.scroll_end},{y})"
            dialogue = f"Dialogue: 0,{start_str},{end_str},Danmaku,,0,0,0,,{{\\bord1.2\\shad0{move_effect}}}{safe_text}\n"
            dst.write(dialogue)
    return True


def _build_header(style: DanmuAssConfig) -> str:
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {style.play_res_x}\n"
        f"PlayResY: {style.play_res_y}\n"
        "Collisions: Normal\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
        "YCbCr Matrix: TV.601\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Danmaku,{style.font},{style.font_size},&H00FFFFFF,&H00FFFFFF,&H64000000,&H96000000,-1,0,0,0,"
        "100,100,0,0,1,1.5,0,2,30,30,20,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def _format_ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _escape(text: str) -> str:
    return text.replace("{", "（").replace("}", "）")
