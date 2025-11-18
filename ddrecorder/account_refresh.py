from __future__ import annotations

import asyncio
import importlib
import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, Optional

if TYPE_CHECKING:
    from .config import AccountConfig

REQUIRED_COOKIES = {"SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5", "sid"}
DEFAULT_COOKIES_FILE = "cookies.json"


def ensure_account_credentials(
    raw_config: Dict, config_path: Path, fetcher: Optional[Callable[[dict], Optional[dict]]] = None
) -> bool:
    """
    Ensure every account dict inside config has complete cookies/tokens.
    When data is missing, invoke the provided fetcher (default: BiliAuth) to refresh.
    """
    fetcher = fetcher or _default_fetcher
    changed = False

    root_accounts = raw_config.get("root", {}).get("account", {})
    for name, entry in list(root_accounts.items()):
        if isinstance(entry, dict) and _needs_refresh(entry):
            logging.info("账号 %s 信息缺失，尝试通过 BiliAuth 自动更新", name)
            changed |= _refresh_entry(entry, fetcher)

    for idx, spec in enumerate(raw_config.get("spec", [])):
        account_entry = spec.get("uploader", {}).get("account")
        if isinstance(account_entry, dict) and _needs_refresh(account_entry):
            logging.info("spec[%s] 的账号信息缺失，尝试自动更新", idx)
            changed |= _refresh_entry(account_entry, fetcher)

    if changed:
        config_path.write_text(
            json.dumps(raw_config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return changed


def _needs_refresh(entry: dict) -> bool:
    if not entry:
        return True
    if not entry.get("cookies"):
        return True
    cookies = entry.get("cookies") or {}
    if not all(cookies.get(key) for key in REQUIRED_COOKIES):
        return True
    if not entry.get("access_token") or not entry.get("refresh_token"):
        return True
    return False


def _refresh_entry(entry: dict, fetcher: Callable[[dict], Optional[dict]]) -> bool:
    creds = fetch_credentials(entry, fetcher=fetcher)
    if not creds:
        logging.warning("账号 %s 自动更新失败，仍将使用旧凭据", entry.get("username"))
        return False
    entry["access_token"] = creds.get("access_token", entry.get("access_token", ""))
    entry["refresh_token"] = creds.get("refresh_token", entry.get("refresh_token", ""))
    entry["cookies"] = creds.get("cookies", entry.get("cookies", {}))
    return True


def fetch_credentials(entry: dict, fetcher: Optional[Callable[[dict], Optional[dict]]] = None) -> Optional[dict]:
    fetcher = fetcher or _default_fetcher
    return fetcher(entry)


def dump_credentials(
    config_path: Path,
    account_name: Optional[str] = None,
    fetcher: Optional[Callable[[dict], Optional[dict]]] = None,
) -> Path:
    """
    Login via BiliAuth (or provided fetcher) and persist tokens/cookies to a JSON file.
    If account_name is provided, only dump that root account; otherwise dump the first root account.
    """
    output: Dict[str, dict] = {}
    with open(config_path, encoding="utf-8") as f:
        raw = json.load(f)

    root_accounts: Dict[str, dict] = (raw.get("root", {}).get("account", {}) or {})
    targets: Dict[str, dict] = {}
    if account_name:
        if account_name not in root_accounts:
            raise ValueError(f"account '{account_name}' not found in root.account")
        targets[account_name] = root_accounts[account_name]
    else:
        if not root_accounts:
            raise ValueError("no root.account entries to dump")
        first_name = next(iter(root_accounts))
        targets[first_name] = root_accounts[first_name]

    for name, entry in targets.items():
        creds = fetch_credentials(entry, fetcher=fetcher)
        if not creds:
            logging.error("获取账号 %s 凭据失败", name)
            continue
        output[name] = {
            "username": entry.get("username", ""),
            "region": entry.get("region", "86"),
            "access_token": creds.get("access_token", ""),
            "refresh_token": creds.get("refresh_token", ""),
            "cookies": creds.get("cookies", {}),
        }

    out_path = config_path.parent / DEFAULT_COOKIES_FILE
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _default_fetcher(entry: dict) -> Optional[dict]:
    username = entry.get("username")
    password = entry.get("password")
    if not username or not password:
        logging.warning("账号缺少用户名或密码，无法自动刷新")
        return None
    region = str(entry.get("region") or "86")
    try:
        BiliAuth = _load_biliauth()
    except ImportError:
        logging.error("未找到 BiliAuth 模块，无法自动刷新账号信息")
        return None

    async def _login():
        auth = BiliAuth()
        auth.set(username, password, region)
        return await auth.acquire(is_print=False, fallback_sms=False)

    try:
        response = asyncio.run(_login())
    except RuntimeError as exc:
        logging.error("调用 BiliAuth 获取凭据失败: %s", exc)
        return None
    if not response or response.get("code") != 0:
        logging.error("BiliAuth 登录失败: %s", response)
        return None
    cookies_dict = _parse_cookie_string(response.get("cookies", ""))
    return {
        "access_token": response.get("access_token", ""),
        "refresh_token": response.get("refresh_token", ""),
        "cookies": cookies_dict,
    }


def _parse_cookie_string(cookie_str: str) -> Dict[str, str]:
    cookies: Dict[str, str] = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies[name] = value
    return cookies


def _load_biliauth():
    try:
        module = importlib.import_module("BiliAuth")
        return getattr(module, "BiliAuth")
    except ImportError:
        pass

    candidate_dir = Path(__file__).resolve().parents[2] / "BiliAuth.py"
    candidate_file = candidate_dir / "BiliAuth.py"
    if candidate_file.exists():
        if str(candidate_dir) not in sys.path:
            sys.path.append(str(candidate_dir))
        module = importlib.import_module("BiliAuth")
        return getattr(module, "BiliAuth")
    raise ImportError("BiliAuth module not found")


def persist_account_credentials(
    config_path: Path,
    room_id: str,
    account_ref: Optional[str],
    account_data: "AccountConfig",
) -> bool:
    account_dict = _account_to_dict(account_data)
    with open(config_path, encoding="utf-8") as f:
        raw = json.load(f)
    updated = False
    if account_ref:
        entry = (raw.get("root", {}).get("account", {}) or {}).get(account_ref)
        if isinstance(entry, dict):
            entry.update(account_dict)
            updated = True
    else:
        for spec in raw.get("spec", []):
            if str(spec.get("room_id")) == str(room_id):
                account_entry = spec.get("uploader", {}).get("account")
                if isinstance(account_entry, dict):
                    account_entry.update(account_dict)
                    updated = True
                break
    if updated:
        config_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return updated


def _account_to_dict(account: "AccountConfig") -> Dict[str, str]:
    return {
        "username": getattr(account, "username", ""),
        "password": getattr(account, "password", ""),
        "region": getattr(account, "region", "86"),
        "access_token": getattr(account, "access_token", ""),
        "refresh_token": getattr(account, "refresh_token", ""),
        "cookies": getattr(account, "cookies", {}) or {},
    }
