from __future__ import annotations

import datetime as dt
import time
from pathlib import Path
from typing import Dict, List

from biliup.plugins.bili_webup import BiliBili, Data

from .account_refresh import fetch_credentials, persist_account_credentials
from .config import AppConfig, RoomConfig
from .live.bilibili import BiliLiveRoom
from .logging import get_stage_logger
from .utils import session_tokens


class BiliUploader:
    def __init__(
        self, app_config: AppConfig, room_config: RoomConfig, room: BiliLiveRoom
    ) -> None:
        self.app_config = app_config
        self.room_config = room_config
        self.room = room
        self.client = BiliBili(Data())
        self.logger = get_stage_logger("upload", self.room_config.room_id)
        self._login()

    def _login(self) -> None:
        attempts = 0
        while attempts < 2:
            cookies = self.room_config.uploader.account.cookies
            if not cookies and not self._refresh_account_credentials():
                raise ValueError("缺少上传账号 cookies 配置")
            cookie_payload = {
                "cookie_info": {
                    "cookies": [{"name": k, "value": v} for k, v in cookies.items()]
                }
            }
            try:
                self.client.login_by_cookies(cookie_payload)
                return
            except Exception:
                self.logger.warning("Cookie 登录失败，尝试重新获取凭据", exc_info=True)
                if not self._refresh_account_credentials():
                    break
                attempts += 1
        raise RuntimeError("登录 B 站上传接口失败")

    def _refresh_account_credentials(self) -> bool:
        account = self.room_config.uploader.account
        self.logger.info("尝试刷新账号 %s 凭据", account.username or "unknown")
        entry = {
            "username": account.username,
            "password": account.password,
            "region": account.region,
            "access_token": account.access_token,
            "refresh_token": account.refresh_token,
            "cookies": account.cookies,
        }
        creds = fetch_credentials(entry)
        if not creds:
            self.logger.error("刷新账号 %s 凭据失败", account.username or "unknown")
            return False
        account.access_token = creds.get("access_token", "")
        account.refresh_token = creds.get("refresh_token", "")
        account.cookies = creds.get("cookies", {}) or {}
        persist_account_credentials(
            self.app_config.config_path,
            self.room_config.room_id,
            self.room_config.uploader.account_ref,
            account,
        )
        self.logger.info("账号 %s 凭据已更新", account.username or "unknown")
        return True

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            self.logger.debug("关闭上传客户端失败", exc_info=True)

    def _upload_file_with_retry(self, file_path: str, max_retries: int = 10) -> Dict:
        """上传单个文件，遇到临时性错误时自动重试"""
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return self.client.upload_file(
                    file_path, lines=self.app_config.root.uploader.lines
                )
            except (KeyError, ConnectionError, TimeoutError) as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = (
                        attempt + 1
                    ) * 5  # 5, 10, 15, 20, 25, 30, 35, 40, 45, 50 秒
                    self.logger.warning(
                        "上传 %s 失败 (%s: %s)，%d秒后重试 (%d/%d)",
                        file_path,
                        type(e).__name__,
                        e,
                        wait_time,
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(wait_time)
                else:
                    self.logger.error("上传 %s 失败，已达最大重试次数", file_path)
        raise last_error  # type: ignore[misc]

    def upload_record(self, start: dt.datetime, splits: List[Path]) -> Dict | None:
        record_cfg = self.room_config.uploader.record
        if not record_cfg.upload_record:
            return None
        tokens = session_tokens(start, self.room.room_title or self.room.room_id)
        uploader = Data()
        uploader.copyright = self.room_config.uploader.copyright
        uploader.title = record_cfg.title.format(**tokens)
        uploader.desc = record_cfg.desc.format(**tokens)
        uploader.source = f"https://live.bilibili.com/{self.room.room_id}"
        uploader.tid = record_cfg.tid
        uploader.set_tag(record_cfg.tags)

        self.client.video = uploader

        uploaded = 0
        for split in sorted(splits):
            if split.stat().st_size < 1_048_576:
                continue
            part = self._upload_file_with_retry(str(split.resolve()))
            part["title"] = split.stem.split("_")[-1]
            part["desc"] = uploader.desc
            uploader.append(part)
            uploaded += 1
        if uploaded == 0:
            self.logger.warning("没有可上传的分段")
            self.client.video = None
            return None

        if record_cfg.cover:
            cover_path = Path(record_cfg.cover)
            if not cover_path.is_absolute():
                cover_path = (self.app_config.config_path.parent / cover_path).resolve()
            if cover_path.exists():
                uploader.cover = self.client.cover_up(str(cover_path))
            else:
                self.logger.warning("封面文件不存在: %s", cover_path)

        resp = self.client.submit()
        if resp.get("code") == 0 and resp.get("data"):
            self.logger.info("上传成功 bvid=%s", resp["data"]["bvid"])
            return {"avid": resp["data"]["aid"], "bvid": resp["data"]["bvid"]}
        self.logger.error("上传失败: %s", resp)
        return None
