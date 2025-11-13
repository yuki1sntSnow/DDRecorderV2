from __future__ import annotations

import logging
from typing import List

import requests

from .base import LiveRoom, RoomInfo


class BiliLiveRoom(LiveRoom):
    ROOM_INFO_URL = "https://api.live.bilibili.com/room/v1/Room/get_info"
    USER_INFO_URL = (
        "https://api.live.bilibili.com/live_user/v1/UserInfo/get_anchor_in_room"
    )
    STREAM_URL = "https://api.live.bilibili.com/room/v1/Room/playUrl"

    def _fetch_room_info(self) -> RoomInfo:
        try:
            room_resp = self.session.get(
                self.ROOM_INFO_URL,
                headers=self.headers,
                params={"room_id": self.room_id},
                timeout=(10, 30),
            )
            room_resp.raise_for_status()
            room_json = room_resp.json()
        except requests.RequestException as exc:
            logging.error("获取房间信息失败: %s", exc)
            return self._info

        if room_json.get("msg") != "ok":
            logging.warning("房间 API 返回异常: %s", room_json.get("msg"))
            return self._info

        data = room_json.get("data", {})
        room_id = str(data.get("room_id", self.room_id))
        title = data.get("title", "")
        is_live = data.get("live_status") == 1
        host = self._info.host

        try:
            user_resp = self.session.get(
                self.USER_INFO_URL,
                headers=self.headers,
                params={"roomid": room_id},
                timeout=(10, 30),
            )
            user_resp.raise_for_status()
            user_json = user_resp.json()
            host = user_json.get("data", {}).get("info", {}).get("uname", host)
        except requests.RequestException:
            logging.debug("获取主播昵称失败", exc_info=True)

        self.room_id = room_id
        return RoomInfo(title=title, host=host, is_live=is_live, room_id=room_id)

    def fetch_stream_urls(self) -> List[str]:
        params = {
            "cid": self.room_id,
            "otype": "json",
            "quality": 0,
            "platform": "web",
        }
        try:
            quality_resp = self.session.get(
                self.STREAM_URL, headers=self.headers, params=params, timeout=(10, 30)
            )
            quality_resp.raise_for_status()
            data = quality_resp.json().get("data", {})
            accept = data.get("accept_quality", [])
            best_quality = accept[0] if accept else 0
        except requests.RequestException:
            logging.error("获取直播画质失败", exc_info=True)
            best_quality = 0

        params["quality"] = best_quality
        try:
            stream_resp = self.session.get(
                self.STREAM_URL, headers=self.headers, params=params, timeout=(10, 30)
            )
            stream_resp.raise_for_status()
            json_data = stream_resp.json()
        except requests.RequestException as exc:
            logging.error("获取直播流地址失败: %s", exc)
            return []

        urls = []
        for item in json_data.get("data", {}).get("durl", []):
            url = item.get("url")
            if url:
                urls.append(url)
        return urls
