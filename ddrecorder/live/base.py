from __future__ import annotations

import abc
import datetime as dt
from dataclasses import dataclass
from typing import Dict, List

import requests
from requests.adapters import HTTPAdapter


DEFAULT_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.6,en;q=0.4,zh-TW;q=0.2",
    "Connection": "keep-alive",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0 Safari/537.36",
}


@dataclass
class RoomInfo:
    title: str
    host: str
    is_live: bool
    room_id: str


class LiveRoom(abc.ABC):
    def __init__(self, room_id: str, headers: Dict[str, str] | None = None) -> None:
        self.room_id = str(room_id)
        self.headers = {**DEFAULT_HEADERS, **(headers or {})}
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=3))
        self.session.mount("http://", HTTPAdapter(max_retries=3))
        self._info = RoomInfo(title="", host="", is_live=False, room_id=self.room_id)
        self._last_refresh = dt.datetime.min

    def refresh(self) -> RoomInfo:
        self._info = self._fetch_room_info()
        self._last_refresh = dt.datetime.now()
        return self._info

    @property
    def last_refresh(self) -> dt.datetime:
        return self._last_refresh

    @property
    def is_live(self) -> bool:
        return self._info.is_live

    @property
    def room_title(self) -> str:
        return self._info.title

    @property
    def host_name(self) -> str:
        return self._info.host

    @abc.abstractmethod
    def _fetch_room_info(self) -> RoomInfo:
        raise NotImplementedError

    @abc.abstractmethod
    def fetch_stream_urls(self) -> List[str]:
        raise NotImplementedError
