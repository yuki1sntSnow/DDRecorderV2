from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

import ffmpeg

from .config import RecorderConfig
from .paths import RecordingPaths


@dataclass
class ProcessResult:
    merged_file: Path
    splits_dir: Path


class RecordingProcessor:
    def __init__(
        self,
        paths: RecordingPaths,
        recorder_cfg: RecorderConfig,
    ) -> None:
        self.paths = paths
        self.recorder_cfg = recorder_cfg

    def run(self) -> ProcessResult | None:
        logging.info("开始处理录制片段，目录 %s", self.paths.records_dir)
        ts_files = self._transmux_fragments()
        if not ts_files:
            return None
        if not self._concat(ts_files):
            return None
        self._cleanup_ts(ts_files)
        if not self.recorder_cfg.keep_raw_record:
            self._cleanup_fragments()
        return ProcessResult(merged_file=self.paths.merged_file, splits_dir=self.paths.splits_dir)

    def split(self, split_interval: int) -> List[Path]:
        logging.info("开始切分合并后的视频，间隔 %ss", split_interval)
        self.paths.splits_dir.mkdir(parents=True, exist_ok=True)
        if split_interval <= 0:
            target = self.paths.splits_dir / f"{self.paths.slug}_0000.mp4"
            shutil.copy2(self.paths.merged_file, target)
            return [target]

        try:
            duration = float(ffmpeg.probe(str(self.paths.merged_file))["format"]["duration"])
        except ffmpeg.Error:
            logging.error("无法读取合并后文件的时长", exc_info=True)
            return []
        num_splits = int(duration // split_interval) + 1
        outputs: List[Path] = []
        for index in range(num_splits):
            output = self.paths.splits_dir / f"{self.paths.slug}_{index:04}.mp4"
            start = index * split_interval
            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                str(start),
                "-t",
                str(split_interval),
                "-accurate_seek",
                "-i",
                str(self.paths.merged_file),
                "-c",
                "copy",
                "-avoid_negative_ts",
                "1",
                str(output),
            ]
            if self._run_cmd(cmd):
                outputs.append(output)
        return outputs

    def _transmux_fragments(self) -> List[Path]:
        fragment_paths = sorted(self.paths.records_dir.glob("*.flv"))
        ts_files: List[Path] = []
        if not fragment_paths:
            logging.error("记录目录 %s 中没有可用的 FLV 片段", self.paths.records_dir)
            return []
        with self.paths.merge_conf_path.open("w", encoding="utf-8") as merge_file:
            for fragment in fragment_paths:
                if fragment.stat().st_size < 1_048_576:
                    continue
                ts_path = fragment.with_suffix(".ts")
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-fflags",
                    "+discardcorrupt",
                    "-i",
                    str(fragment),
                    "-c",
                    "copy",
                    "-bsf:v",
                    "h264_mp4toannexb",
                    "-acodec",
                    "aac",
                    "-f",
                    "mpegts",
                    str(ts_path),
                ]
                if self._run_cmd(cmd):
                    ts_files.append(ts_path)
                    merge_file.write(f"file '{ts_path.resolve()}'\n")
        if not ts_files:
            logging.error("未能生成任何 TS 片段")
        return ts_files

    def _concat(self, ts_files: List[Path]) -> bool:
        if not ts_files:
            return False
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(self.paths.merge_conf_path),
            "-c",
            "copy",
            "-fflags",
            "+igndts",
            "-avoid_negative_ts",
            "make_zero",
            str(self.paths.merged_file),
        ]
        return self._run_cmd(cmd)

    def _cleanup_fragments(self) -> None:
        for fragment in self.paths.records_dir.glob("*"):
            try:
                os.remove(fragment)
            except OSError:
                logging.debug("删除临时片段失败: %s", fragment, exc_info=True)
        try:
            self.paths.records_dir.rmdir()
        except OSError:
            logging.debug("删除片段目录失败: %s", self.paths.records_dir, exc_info=True)

    @staticmethod
    def _cleanup_ts(ts_files: List[Path]) -> None:
        for ts_file in ts_files:
            try:
                ts_file.unlink()
            except OSError:
                logging.debug("删除 TS 片段失败: %s", ts_file, exc_info=True)

    @staticmethod
    def _run_cmd(cmd: List[str]) -> bool:
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="ignore") if exc.stderr else ""
            logging.error("FFmpeg 命令失败: %s\n%s", " ".join(cmd), stderr)
            return False
