from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

import ffmpeg

from .config import RecorderConfig, DanmuAssConfig
from .danmaku_ass import jsonl_to_ass
from .logging import get_ffmpeg_log_path, get_stage_logger
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
        danmu_ass: DanmuAssConfig,
    ) -> None:
        self.paths = paths
        self.recorder_cfg = recorder_cfg
        self.danmu_ass = danmu_ass
        slug = self.paths.slug
        self.process_logger = get_stage_logger("process", slug)
        self.ffmpeg_logfile_hander = open(get_ffmpeg_log_path(slug), mode="a", encoding="utf-8")

    def run(self) -> ProcessResult | None:
        self.process_logger.info("开始处理录制片段，目录 %s", self.paths.records_dir)
        try:
            for attempt in range(1, 4):
                ts_files = self._transmux_fragments()
                if not ts_files:
                    self.process_logger.error("第 %s 次处理失败：没有可用的录制片段", attempt)
                    continue
                if not self._concat(ts_files):
                    self.process_logger.error("第 %s 次 FFmpeg concat 失败", attempt)
                    continue
                self._cleanup_ts(ts_files)
                self._apply_subtitles()
                if not self.recorder_cfg.keep_raw_record:
                    self._cleanup_fragments()
                return ProcessResult(merged_file=self.paths.merged_file, splits_dir=self.paths.splits_dir)
            self.process_logger.error("多次重试后仍无法完成处理，将跳过本次任务")
            return None
        finally:
            try:
                self.ffmpeg_logfile_hander.close()
            except Exception:
                self.process_logger.debug("关闭 FFmpeg 日志失败", exc_info=True)

    def split(self, split_interval: int) -> List[Path]:
        self.process_logger.info("开始切分合并后的视频，间隔 %ss", split_interval)
        self.paths.splits_dir.mkdir(parents=True, exist_ok=True)
        if split_interval <= 0:
            target = self.paths.splits_dir / f"{self.paths.slug}_0000.mp4"
            shutil.copy2(self.paths.merged_file, target)
            return [target]

        try:
            duration = float(ffmpeg.probe(str(self.paths.merged_file))["format"]["duration"])
        except ffmpeg.Error:
            self.process_logger.error("无法读取合并后文件的时长", exc_info=True)
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
            self.process_logger.error("记录目录 %s 中没有可用的 FLV 片段", self.paths.records_dir)
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
            self.process_logger.error("未能生成任何 TS 片段")
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
                self.process_logger.debug("删除临时片段失败: %s", fragment, exc_info=True)
        try:
            self.paths.records_dir.rmdir()
        except OSError:
            self.process_logger.debug("删除片段目录失败: %s", self.paths.records_dir, exc_info=True)

    def _cleanup_ts(self, ts_files: List[Path]) -> None:
        for ts_file in ts_files:
            try:
                ts_file.unlink()
            except OSError:
                self.process_logger.debug("删除 TS 片段失败: %s", ts_file, exc_info=True)

    def _run_cmd(self, cmd: List[str]) -> bool:
        """
        Run FFmpeg command with compact logging by default.
        Set env DDRECORDER_FFMPEG_VERBOSE=1 to enable detailed debug output.
        """
        verbose = os.environ.get("DDRECORDER_FFMPEG_VERBOSE") == "1"
        patched_cmd = cmd
        if "-loglevel" not in cmd:
            loglevel = "level+debug" if verbose else "error"
            patched_cmd = [cmd[0], "-hide_banner", "-nostdin", "-loglevel", loglevel]
            if verbose:
                patched_cmd += ["-stats", "-stats_period", "1"]
            patched_cmd += cmd[1:]
        try:
            subprocess.run(
                patched_cmd,
                check=True,
                stdout=self.ffmpeg_logfile_hander,
                stderr=subprocess.STDOUT,
            )
            self.ffmpeg_logfile_hander.flush()
            return True
        except subprocess.CalledProcessError:
            self.ffmpeg_logfile_hander.flush()
            self.process_logger.error(
                "FFmpeg 命令失败: %s，详见 %s", " ".join(patched_cmd), self.ffmpeg_logfile_hander.name
            )
            return False

    def _apply_subtitles(self) -> None:
        jsonl_path = self.paths.danmu_json_path
        if not jsonl_path.exists():
            return
        ass_path = self.paths.danmu_ass_path
        if not jsonl_to_ass(jsonl_path, ass_path, self.paths.start, self.danmu_ass):
            return
        temp_file = self.paths.merged_file.with_suffix(".nosub.mp4")
        try:
            if temp_file.exists():
                temp_file.unlink()
            self.paths.merged_file.replace(temp_file)
        except OSError:
            self.process_logger.warning("无法准备字幕压制临时文件，跳过字幕压制")
            return
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(temp_file),
            "-vf",
            f"ass={ass_path}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "copy",
            str(self.paths.merged_file),
        ]
        if self._run_cmd(cmd):
            temp_file.unlink(missing_ok=True)
            self.process_logger.info("已将弹幕压制到合并文件中")
        else:
            self.process_logger.warning("字幕压制失败，回退到无字幕版本")
            temp_file.replace(self.paths.merged_file)
