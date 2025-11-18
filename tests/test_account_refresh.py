import json
from pathlib import Path

from ddrecorder.account_refresh import ensure_account_credentials, persist_account_credentials
from ddrecorder.config import AccountConfig
from ddrecorder.account_refresh import dump_credentials


def write_config(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def complete_creds():
    return {
        "access_token": "a",
        "refresh_token": "r",
        "cookies": {
            "SESSDATA": "sess",
            "bili_jct": "jct",
            "DedeUserID": "1",
            "DedeUserID__ckMd5": "2",
            "sid": "3",
        },
    }


def test_ensure_account_credentials_updates_missing(tmp_path):
    raw = {
        "root": {
            "account": {
                "main": {
                    "username": "user",
                    "password": "pass",
                    "cookies": {"SESSDATA": "only"},
                }
            }
        },
        "spec": [],
    }
    config_path = write_config(tmp_path, raw)

    def fake_fetch(entry):
        return complete_creds()

    changed = ensure_account_credentials(raw, config_path, fetcher=fake_fetch)
    assert changed is True
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["root"]["account"]["main"]["access_token"] == "a"
    assert data["root"]["account"]["main"]["cookies"]["bili_jct"] == "jct"


def test_ensure_account_credentials_no_change_when_complete(tmp_path):
    raw = {
        "root": {"account": {"main": {**complete_creds(), "username": "user"}}},
        "spec": [],
    }
    config_path = write_config(tmp_path, raw)

    changed = ensure_account_credentials(raw, config_path, fetcher=lambda e: None)
    assert changed is False
    # file should remain untouched (still contains old data)
    stored = json.loads(config_path.read_text(encoding="utf-8"))
    assert stored["root"]["account"]["main"]["access_token"] == "a"


def test_persist_account_updates_spec(tmp_path):
    raw = {
        "root": {},
        "spec": [
            {
                "room_id": "1",
                "uploader": {
                    "account": {
                        "username": "u",
                        "password": "p",
                    }
                },
            }
        ],
    }
    config_path = write_config(tmp_path, raw)
    account = AccountConfig(
        username="u",
        password="p",
        region="86",
        access_token="new_access",
        refresh_token="new_refresh",
        cookies={"SESSDATA": "sess"},
    )
    persist_account_credentials(config_path, "1", None, account)
    stored = json.loads(config_path.read_text(encoding="utf-8"))
    account_entry = stored["spec"][0]["uploader"]["account"]
    assert account_entry["access_token"] == "new_access"
    assert account_entry["cookies"]["SESSDATA"] == "sess"


def test_persist_account_updates_root_entry(tmp_path):
    raw = {
        "root": {
            "account": {
                "main": {
                    "username": "u",
                    "password": "p",
                }
            }
        },
        "spec": [
            {
                "room_id": "1",
                "uploader": {
                    "account": "main",
                },
            }
        ],
    }
    config_path = write_config(tmp_path, raw)
    account = AccountConfig(
        username="u",
        password="p",
        region="86",
        access_token="new_access",
        refresh_token="new_refresh",
        cookies={"SESSDATA": "sess"},
    )
    persist_account_credentials(config_path, "1", "main", account)
    stored = json.loads(config_path.read_text(encoding="utf-8"))
    entry = stored["root"]["account"]["main"]
    assert entry["access_token"] == "new_access"
    assert entry["cookies"]["SESSDATA"] == "sess"


def test_dump_credentials(tmp_path):
    raw = {
        "root": {
            "account": {
                "main": {
                    "username": "u",
                    "password": "p",
                    "region": "86",
                }
            }
        },
        "spec": [],
    }
    config_path = write_config(tmp_path, raw)

    def fake_fetch(entry):
        return complete_creds()

    out = dump_credentials(config_path, account_name="main", fetcher=fake_fetch)
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["main"]["access_token"] == "a"
    assert data["main"]["cookies"]["SESSDATA"] == "sess"
