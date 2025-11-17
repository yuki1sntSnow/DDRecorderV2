from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path


def _session_slug(room_id: str, start: dt.datetime) -> str:
    return f"{room_id}_{start.strftime('%Y-%m-%d_%H-%M-%S')}"


@dataclass
class RecordingPaths:
    data_root: Path
    room_id: str
    start: dt.datetime

    def __post_init__(self) -> None:
        self.slug = _session_slug(self.room_id, self.start)

    @property
    def records_dir(self) -> Path:
        return self.data_root / "data" / "records" / self.slug

    @property
    def merged_dir(self) -> Path:
        return self.data_root / "data" / "merged"

    @property
    def outputs_dir(self) -> Path:
        return self.data_root / "data" / "outputs" / self.slug

    @property
    def splits_dir(self) -> Path:
        return self.data_root / "data" / "splits" / self.slug

    @property
    def merge_conf_path(self) -> Path:
        return self.data_root / "data" / "merge_confs" / f"{self.slug}_merge_conf.txt"

    @property
    def merged_file(self) -> Path:
        return self.merged_dir / f"{self.slug}_merged.mp4"

    @property
    def danmu_dir(self) -> Path:
        return self.data_root / "data" / "danmu" / self.slug

    @property
    def danmu_json_path(self) -> Path:
        return self.danmu_dir / "danmu.jsonl"

    @property
    def danmu_ass_path(self) -> Path:
        return self.danmu_dir / f"{self.slug}.ass"

    def ensure_session_dirs(self) -> None:
        self.records_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self.splits_dir.mkdir(parents=True, exist_ok=True)
        self.merged_dir.mkdir(parents=True, exist_ok=True)
        self.merge_conf_path.parent.mkdir(parents=True, exist_ok=True)
        self.danmu_dir.mkdir(parents=True, exist_ok=True)

    def fragment_path(self, timestamp: dt.datetime | None = None) -> Path:
        ts = timestamp or dt.datetime.now()
        filename = f"{self.room_id}_{ts.strftime('%Y-%m-%d_%H-%M-%S')}.flv"
        return self.records_dir / filename
