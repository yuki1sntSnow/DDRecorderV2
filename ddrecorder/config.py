from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .account_refresh import ensure_account_credentials


def _ensure_path(path_like: str, base: Path) -> Path:
    """Resolve a user supplied path relative to the config file directory."""
    path = Path(path_like)
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


@dataclass
class LoggerConfig:
    path: Path
    level: str = "INFO"

    @classmethod
    def from_dict(cls, data: Dict, base: Path) -> "LoggerConfig":
        log_path = data.get("log_path", "./log")
        return cls(path=_ensure_path(log_path, base), level=data.get("log_level", "INFO"))


@dataclass
class RootUploaderConfig:
    lines: str = "AUTO"

    @classmethod
    def from_dict(cls, data: Dict) -> "RootUploaderConfig":
        return cls(lines=data.get("lines", "AUTO"))


@dataclass
class AccountConfig:
    username: str = ""
    password: str = ""
    region: str = "86"
    access_token: str = ""
    refresh_token: str = ""
    cookies: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict) -> "AccountConfig":
        if not data:
            data = {}
        return cls(
            username=data.get("username", ""),
            password=data.get("password", ""),
            region=str(data.get("region", "86")),
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token", ""),
            cookies=data.get("cookies", {}) or {},
        )


def _account_from_raw(entry, base: Path) -> AccountConfig:
    if isinstance(entry, str):
        cookie_path = _ensure_path(entry, base)
        with open(cookie_path, encoding="utf-8") as cookie_file:
            cookie_json = json.load(cookie_file)
        cookies = {
            item["name"]: item["value"]
            for item in cookie_json.get("cookie_info", {}).get("cookies", [])
        }
        access_token = cookie_json.get("token_info", {}).get("access_token", "")
        return AccountConfig(access_token=access_token, cookies=cookies)
    if isinstance(entry, dict):
        return AccountConfig.from_dict(entry)
    return AccountConfig()


@dataclass
class DanmuAssConfig:
    play_res_x: int = 1920
    play_res_y: int = 1080
    font: str = "Microsoft YaHei"
    font_size: int = 45
    duration: float = 6.0
    row_count: int = 12
    line_height: int = 40
    margin_top: int = 60
    scroll_end: int = -200

    @classmethod
    def from_dict(cls, data: Dict) -> "DanmuAssConfig":
        data = data or {}
        return cls(
            play_res_x=int(data.get("play_res_x", 1920)),
            play_res_y=int(data.get("play_res_y", 1080)),
            font=data.get("font", "Microsoft YaHei"),
            font_size=int(data.get("font_size", 45)),
            duration=float(data.get("duration", 6.0)),
            row_count=int(data.get("row_count", 12)),
            line_height=int(data.get("line_height", 40)),
            margin_top=int(data.get("margin_top", 60)),
            scroll_end=int(data.get("scroll_end", -200)),
        )


@dataclass
class RecordUploadConfig:
    upload_record: bool = False
    keep_record_after_upload: bool = True
    split_interval: int = 3600
    title: str = ""
    tid: int = 27
    tags: List[str] = field(default_factory=list)
    desc: str = ""
    cover: str = ""

    @classmethod
    def from_dict(cls, data: Dict) -> "RecordUploadConfig":
        if not data:
            data = {}
        return cls(
            upload_record=data.get("upload_record", False),
            keep_record_after_upload=data.get("keep_record_after_upload", True),
            split_interval=data.get("split_interval", 3600),
            title=data.get("title", ""),
            tid=data.get("tid", 27),
            tags=data.get("tags", []) or [],
            desc=data.get("desc", ""),
            cover=data.get("cover", ""),
        )


@dataclass
class RecorderConfig:
    keep_raw_record: bool = True
    enable_danmu: bool = False

    @classmethod
    def from_dict(cls, data: Dict) -> "RecorderConfig":
        if not data:
            data = {}
        return cls(
            keep_raw_record=data.get("keep_raw_record", True),
            enable_danmu=data.get("enable_danmu", False),
        )


@dataclass
class SpecUploaderConfig:
    copyright: int = 2
    account: AccountConfig = field(default_factory=AccountConfig)
    record: RecordUploadConfig = field(default_factory=RecordUploadConfig)
    account_ref: Optional[str] = None

    @classmethod
    def from_dict(
        cls, data: Dict, root_accounts: Dict[str, AccountConfig]
    ) -> "SpecUploaderConfig":
        if not data:
            data = {}
        account_raw = data.get("account", "default")
        account_ref = None
        if isinstance(account_raw, str):
            account = root_accounts.get(account_raw, AccountConfig())
            account_ref = account_raw
        else:
            account = AccountConfig.from_dict(account_raw)
        return cls(
            copyright=data.get("copyright", 2),
            account=account,
            record=RecordUploadConfig.from_dict(data.get("record", {})),
            account_ref=account_ref,
        )


@dataclass
class RoomConfig:
    room_id: str
    recorder: RecorderConfig
    uploader: SpecUploaderConfig

    @classmethod
    def from_dict(cls, data: Dict, root_accounts: Dict[str, AccountConfig]) -> "RoomConfig":
        room_id = str(data["room_id"])
        recorder = RecorderConfig.from_dict(data.get("recorder", {}))
        uploader = SpecUploaderConfig.from_dict(data.get("uploader", {}), root_accounts)
        return cls(room_id=room_id, recorder=recorder, uploader=uploader)


@dataclass
class RootConfig:
    check_interval: int
    print_interval: int
    data_path: Path
    logger: LoggerConfig
    request_header: Dict[str, str]
    uploader: RootUploaderConfig
    accounts: Dict[str, AccountConfig]
    danmu_ass: DanmuAssConfig

    @classmethod
    def from_dict(cls, data: Dict, base: Path) -> "RootConfig":
        data = data or {}
        accounts = {
            name: _account_from_raw(entry, base)
            for name, entry in (data.get("account", {}) or {}).items()
        }
        data_path = _ensure_path(data.get("data_path", "./"), base)
        return cls(
            check_interval=int(data.get("check_interval", 60)),
            print_interval=int(data.get("print_interval", 60)),
            data_path=data_path,
            logger=LoggerConfig.from_dict(data.get("logger", {}), base),
            request_header=data.get("request_header", {}) or {},
            uploader=RootUploaderConfig.from_dict(data.get("uploader", {})),
            accounts=accounts,
            danmu_ass=DanmuAssConfig.from_dict(data.get("danmu_ass", {})),
        )


@dataclass
class AppConfig:
    root: RootConfig
    rooms: List[RoomConfig]
    config_path: Path

    def ensure_base_dirs(self) -> None:
        for sub in ("records", "merged", "merge_confs", "outputs", "splits", "danmu"):
            path = self.root.data_path / "data" / sub
            path.mkdir(parents=True, exist_ok=True)
        self.root.logger.path.mkdir(parents=True, exist_ok=True)


def _resolve_base_dir(config_path: Path) -> Path:
    base = config_path.parent
    if base.name.lower() == "config":
        return base.parent
    return base


def load_config(path: Path, *, refresh_credentials: bool = True) -> AppConfig:
    with open(path, encoding="utf-8") as f:
        raw_config = json.load(f)
    if refresh_credentials:
        ensure_account_credentials(raw_config, path)
    base_dir = _resolve_base_dir(path)
    root = RootConfig.from_dict(raw_config.get("root", {}), base_dir)
    rooms = [
        RoomConfig.from_dict(spec, root.accounts)
        for spec in raw_config.get("spec", [])
        if spec.get("room_id")
    ]
    config = AppConfig(root=root, rooms=rooms, config_path=path)
    config.ensure_base_dirs()
    return config
