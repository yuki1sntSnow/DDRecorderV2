from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import List
import time

import requests

from .config import RecorderConfig, RootConfig
from .logging import get_stage_logger
from .live.bilibili import BiliLiveRoom
from .paths import RecordingPaths


@dataclass
class RecordingResult:
    start: dt.datetime
    record_dir: Path
    fragments: List[Path] = field(default_factory=list)


class LiveRecorder:
    def __init__(
        self,
        room: BiliLiveRoom,
        paths: RecordingPaths,
        recorder_cfg: RecorderConfig,
        root_cfg: RootConfig,
    ) -> None:
        self.room = room
        self.paths = paths
        self.recorder_cfg = recorder_cfg
        self.root_cfg = root_cfg
        self.logger = get_stage_logger("record", self.paths.slug)

    def record(self, max_duration: int | None = None) -> RecordingResult | None:
        self.paths.ensure_session_dirs()
        fragments: List[Path] = []
        self.logger.info("开始录制房间 %s", self.room.room_id)
        end_at: float | None = None
        if max_duration and max_duration > 0:
            end_at = time.time() + max_duration
        retry_wait = max(5, self.root_cfg.check_interval)
        while self.room.is_live:
            if end_at and time.time() >= end_at:
                self.logger.info("达到指定录制时长 %ss，停止录制", max_duration)
                break
            stream_urls = self.room.fetch_stream_urls()
            if not stream_urls:
                self.logger.warning("未获取到直播流地址，%s 秒后重试", retry_wait)
                time.sleep(retry_wait)
                self.room.refresh()
                continue
            target_path = self.paths.fragment_path()
            try:
                if self._download(stream_urls[0], target_path, stop_at=end_at):
                    fragments.append(target_path)
                    self.logger.info("完成片段 %s", target_path.name)
            except OSError:
                self.logger.critical("录制时发生致命读写错误，终止录制")
                fragments.clear()
                break
            self.room.refresh()
        if not fragments:
            self.logger.error("本次录制未生成有效片段")
            # 保留会话目录用于排查问题（例如部分下载的片段/日志）
            return None
        return RecordingResult(start=self.paths.start, record_dir=self.paths.records_dir, fragments=fragments)

    def _download(self, url: str, target_path: Path, stop_at: float | None = None) -> bool:
        try:
            with requests.get(
                url, stream=True, timeout=(10, self.root_cfg.check_interval)
            ) as resp:
                resp.raise_for_status()
                written = 0
                stopped_for_duration = False
                with open(target_path, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=256 * 1024):
                        if not chunk:
                            continue
                        if stop_at and time.time() >= stop_at:
                            stopped_for_duration = True
                            break
                        fh.write(chunk)
                        written += len(chunk)
            if stopped_for_duration:
                self.logger.info("达到指定录制时长，提前结束片段 %s", target_path.name)
            if written == 0:
                self.logger.warning("片段为空，可能未成功拉流: %s", target_path)
            return written > 0 or stopped_for_duration
        except requests.HTTPError as exc:
            # 常见为 403 CDN 拒绝，高码率或签名过期，可忽略单次重试
            self.logger.warning("拉流返回 HTTP %s，url=%s", exc.response.status_code if exc.response else "?", url)
        except requests.RequestException:
            self.logger.warning("录制时网络异常，稍后重试", exc_info=True)
        except OSError:
            self.logger.error("写入录播文件失败: %s", target_path, exc_info=True)
            raise
        return False
