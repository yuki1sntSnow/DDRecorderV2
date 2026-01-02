from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from contextlib import contextmanager
import re
from pathlib import Path
from typing import Iterable, Tuple

import requests
import websocket
from biliup.Danmaku.bilibili import Bilibili  # type: ignore[import]
from biliup.plugins import wbi  # type: ignore[import]

from .logging import get_stage_logger

_BILIBILI_HEADER_LOCK = threading.Lock()
_EMOJI_PATTERN = re.compile(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF]")


def refresh_wbi_key(cookie: str | None = None, logger: logging.Logger | None = None) -> None:
    """Ensure biliup's global wbi key is up-to-date."""
    logger = logger or logging.getLogger("ddrecorder.wbi")
    last_update = getattr(wbi, "last_update", 0)
    if wbi.key and int(time.time()) - last_update < wbi.UPDATE_INTERVAL - 5:
        return
    headers = dict(Bilibili.headers)
    if cookie:
        headers["Cookie"] = cookie
    try:
        resp = requests.get(
            "https://api.bilibili.com/x/web-interface/nav",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
    except Exception:
        logger.error("拉取 WBI key 失败", exc_info=True)
        raise
    wbi_img = data.get("wbi_img") or {}
    img_key = _extract_key_from_url(wbi_img.get("img_url"))
    sub_key = _extract_key_from_url(wbi_img.get("sub_url"))
    if not img_key or not sub_key:
        raise RuntimeError(f"WBI key 缺失: {wbi_img}")
    wbi.update_key(img_key, sub_key)


def _extract_key_from_url(url: str | None) -> str | None:
    if not url:
        return None
    slash = url.rfind("/")
    dot = url.find(".", slash)
    if slash == -1 or dot == -1:
        return None
    return url[slash + 1 : dot]


def _extract_uid_from_cookie(cookie: str | None) -> int:
    if not cookie:
        return 0
    parts = [segment.strip() for segment in cookie.split(";") if segment.strip()]
    kv = {}
    for part in parts:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        kv[key.strip()] = value.strip()
    try:
        return int(kv.get("DedeUserID", "0"))
    except ValueError:
        return 0


class DanmuRecorder(threading.Thread):
    """Wrapper around biliup's danmaku client logic to persist JSON lines."""

    def __init__(
        self,
        room_id: str,
        slug: str,
        headers: dict | None,
        output_dir: Path,
        logger=None,
        debug_payloads: bool = False,
    ) -> None:
        super().__init__(name=f"Danmu-{slug}", daemon=True)
        self.room_id = str(room_id)
        self.slug = slug
        self.room_url = f"https://live.bilibili.com/{self.room_id}"
        self.headers = headers or {}
        self.cookie = self._extract_cookie()
        self.uid = _extract_uid_from_cookie(self.cookie)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.stop_event = threading.Event()
        self.logger = logger or get_stage_logger("record", self.slug)
        self._file_path = self.output_dir / "danmu.jsonl"
        self._file = self._file_path.open("a", encoding="utf-8")
        self.debug_payloads = debug_payloads
        self._patched_headers = self._build_ws_headers()

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        try:
            while not self.stop_event.is_set():
                try:
                    refresh_wbi_key(self.cookie, self.logger)
                    ws_url, payloads = self._prepare_ws_payload()
                except Exception:
                    self.logger.error("获取弹幕服务器信息失败，5 秒后重试", exc_info=True)
                    self.stop_event.wait(5)
                    continue

                header_list = self._format_headers(self._patched_headers)
                origin = self._patched_headers.get("origin", "https://live.bilibili.com")
                try:
                    ws = websocket.create_connection(
                        ws_url,
                        header=header_list,
                        origin=origin,
                        timeout=10,
                    )
                except Exception:
                    self.logger.warning("连接弹幕服务器失败，5 秒后重试", exc_info=True)
                    self.stop_event.wait(5)
                    continue

                self.logger.info("弹幕连接成功 room=%s host=%s", self.room_id, ws_url)
                try:
                    for payload in payloads:
                        if isinstance(payload, bytes):
                            ws.send(payload, opcode=websocket.ABNF.OPCODE_BINARY)
                        else:
                            ws.send(payload)
                    self._consume_loop(ws)
                finally:
                    ws.close()
                    # 避免频繁重连
                    self.stop_event.wait(1)
        finally:
            self._file.close()

    def _prepare_ws_payload(self) -> Tuple[str, Iterable[bytes | str]]:
        cookie_str = self.cookie
        content = {
            "room_id": int(self.room_id),
            "uid": self.uid,
            "cookie": cookie_str,
        }
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            with _temporary_bilibili_headers(self._patched_headers):
                return loop.run_until_complete(Bilibili.get_ws_info(self.room_url, content))
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    def _consume_loop(self, ws: websocket.WebSocket) -> None:
        last_heartbeat = 0.0
        while not self.stop_event.is_set():
            now = time.time()
            if now - last_heartbeat >= Bilibili.heartbeatInterval:
                try:
                    ws.send(Bilibili.heartbeat, opcode=websocket.ABNF.OPCODE_BINARY)
                    last_heartbeat = now
                except Exception:
                    break
            ws.settimeout(1)
            try:
                message = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                break
            if not isinstance(message, (bytes, bytearray)):
                continue
            if self.debug_payloads:
                self.logger.info(
                    "RAW_PACKET len=%s sample=%s", len(message), message[:64].hex()
                )
                print(
                    f"[RAW len={len(message)}] {bytes(message)[:64].hex()}",
                    flush=True,
                )
            self._handle_payload(bytes(message))

    def _handle_payload(self, payload: bytes) -> None:
        try:
            messages = Bilibili.decode_msg(payload)
        except Exception:
            self.logger.debug("弹幕解码失败", exc_info=True)
            return
        now_ms = int(time.time() * 1000)
        for msg in messages:
            if msg.get("msg_type") != "danmaku":
                continue
            text = msg.get("content", "")
            if _EMOJI_PATTERN.search(text):
                continue
            uid = str(msg.get("uid", ""))
            uname = msg.get("name", "")
            extracted_uid, extracted_name = self._extract_user_from_raw(msg)
            if extracted_uid:
                uid = extracted_uid
            if extracted_name:
                uname = extracted_name
            record = {
                "type": "danmaku",
                "text": text,
                "time": now_ms,
                "uid": uid,
                "uname": uname,
            }
            self._write_record(record)

    def _write_record(self, record: dict) -> None:
        try:
            self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._file.flush()
        except Exception:
            self.logger.debug("写入弹幕记录失败: %s", record, exc_info=True)

    def join(self, timeout: float | None = None) -> None:  # type: ignore[override]
        super().join(timeout)

    def _extract_cookie(self) -> str:
        for key in ("Cookie", "cookie"):
            cookie = self.headers.get(key)  # type: ignore[assignment]
            if cookie:
                return str(cookie)
        return ""

    def _extract_user_from_raw(self, msg: dict) -> tuple[str | None, str | None]:
        raw_blob = msg.get("raw_data")
        if not raw_blob:
            return None, None
        try:
            payload = json.loads(raw_blob)
            body = payload.get("body", payload)
            if isinstance(body, str):
                body = json.loads(body)
            info = body.get("info") if isinstance(body, dict) else None
            if not isinstance(info, list) or len(info) < 3:
                return None, None
            user_info = info[2] or []
            uid = str(user_info[0]) if len(user_info) > 0 else None
            uname = user_info[1] if len(user_info) > 1 else None
            return uid, uname
        except Exception:
            self.logger.debug("解析 raw_data 失败", exc_info=True)
            return None, None

    def _ensure_wbi_key(self) -> None:
        refresh_wbi_key(self.cookie, self.logger)

    @staticmethod
    def _format_headers(headers: dict) -> list[str]:
        return [f"{k}: {v}" for k, v in headers.items()]

    def _build_ws_headers(self) -> dict:
        headers = dict(Bilibili.headers)
        headers["referer"] = self.room_url
        headers["origin"] = "https://live.bilibili.com"
        if self.cookie:
            headers["cookie"] = self.cookie
        return headers


@contextmanager
def _temporary_bilibili_headers(new_headers: dict) -> Iterable[dict]:
    with _BILIBILI_HEADER_LOCK:
        original = Bilibili.headers.copy()
        try:
            Bilibili.headers.clear()
            Bilibili.headers.update(new_headers)
            yield Bilibili.headers
        finally:
            Bilibili.headers.clear()
            Bilibili.headers.update(original)
