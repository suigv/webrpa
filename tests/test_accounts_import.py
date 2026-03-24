import sqlite3
from pathlib import Path
from typing import cast

import pytest
import yaml
from _pytest.monkeypatch import MonkeyPatch
from fastapi.testclient import TestClient

from api.server import app
from core.account_parser import parse_accounts_text
from core.account_store import AccountStore


@pytest.fixture()
def isolated_account_store(tmp_path: Path, monkeypatch: MonkeyPatch) -> AccountStore:
    monkeypatch.setattr("core.app_config.config_dir", lambda: tmp_path)
    store = AccountStore(tmp_path / "accounts.db")
    monkeypatch.setattr("core.account_service._account_store", store)
    return store


def test_parse_accounts_text_supports_space_comma_tab_and_header():
    parsed = parse_accounts_text(
        """
账号 密码 2fa
alice@example.com pass1 123456
bob@example.com,pass2,OTP-SECRET
carol@example.com\tpass3\t
invalid_only_one_column
        """
    )
    accounts = cast(list[dict[str, object]], parsed["accounts"])
    assert parsed["valid"] == 3
    assert parsed["invalid"] == 1
    assert accounts[0]["account"] == "alice@example.com"
    assert accounts[0]["password"] == "pass1"
    assert accounts[0]["twofa"] == "123456"


def test_accounts_import_api_and_parsed_view_roundtrip(isolated_account_store: AccountStore):
    client = TestClient(app)
    assert isolated_account_store.count_accounts() == 0

    backup = client.get("/api/data/accounts")
    assert backup.status_code == 200
    backup_text = str(cast(dict[str, object], backup.json()).get("data", ""))

    try:
        resp = client.post(
            "/api/data/accounts/import",
            json={
                "overwrite": True,
                "content": """
account password 2fa
u1 p1 111111
u2,p2,
                """,
            },
        )
        assert resp.status_code == 200
        payload = cast(dict[str, object], resp.json())
        assert payload["status"] == "ok"
        assert payload["valid"] == 2
        assert payload["invalid"] == 0
        assert payload["stored"] == 2

        parsed = client.get("/api/data/accounts/parsed")
        assert parsed.status_code == 200
        accounts = cast(
            list[dict[str, object]],
            cast(dict[str, object], parsed.json()).get("accounts", []),
        )
        assert len(accounts) == 2
        assert accounts[0]["account"] == "u1"
        assert accounts[0]["password"] == "p1"
        assert accounts[0]["twofa"] == "111111"
        assert accounts[1]["twofa"] == ""
    finally:
        _ = client.put("/api/data/accounts", json={"content": backup_text})


def test_accounts_parsed_view_can_filter_by_app_id(isolated_account_store: AccountStore):
    client = TestClient(app)
    assert isolated_account_store.count_accounts() == 0

    first = client.post(
        "/api/data/accounts/import",
        json={
            "overwrite": True,
            "app_id": "wechat",
            "content": "account password\nwx_user wx_pass\n",
        },
    )
    second = client.post(
        "/api/data/accounts/import",
        json={
            "overwrite": False,
            "app_id": "telegram",
            "content": "account password\ntg_user tg_pass\n",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200

    filtered = client.get("/api/data/accounts/parsed", params={"app_id": "wechat"})
    assert filtered.status_code == 200
    accounts = cast(dict[str, list[dict[str, object]]], filtered.json())["accounts"]
    assert len(accounts) == 1
    assert accounts[0]["account"] == "wx_user"
    assert accounts[0]["app_id"] == "wechat"


def test_accounts_pop_honors_app_id_then_falls_back_to_global_default(
    isolated_account_store: AccountStore,
):
    client = TestClient(app)
    assert isolated_account_store.count_accounts() == 0

    global_import = client.post(
        "/api/data/accounts/import",
        json={
            "overwrite": True,
            "app_id": "default",
            "content": "account password\nglobal_user global_pass\n",
        },
    )
    app_import = client.post(
        "/api/data/accounts/import",
        json={
            "overwrite": False,
            "app_id": "wechat",
            "content": "account password\nwx_user wx_pass\n",
        },
    )
    assert global_import.status_code == 200
    assert app_import.status_code == 200

    scoped = client.post("/api/data/accounts/pop", json={"app_id": "wechat"})
    assert scoped.status_code == 200
    scoped_payload = cast(dict[str, dict[str, object]], scoped.json())
    assert scoped_payload["account"]["account"] == "wx_user"
    assert scoped_payload["account"]["app_id"] == "wechat"

    fallback = client.post("/api/data/accounts/pop", json={"app_id": "telegram"})
    assert fallback.status_code == 200
    fallback_payload = cast(dict[str, dict[str, object]], fallback.json())
    assert fallback_payload["account"]["account"] == "global_user"
    assert fallback_payload["account"]["app_id"] == "default"


def test_accounts_pop_without_app_id_preserves_global_behavior(
    isolated_account_store: AccountStore,
):
    client = TestClient(app)
    assert isolated_account_store.count_accounts() == 0

    imported = client.post(
        "/api/data/accounts/import",
        json={
            "overwrite": True,
            "app_id": "default",
            "content": "account password\nfirst_user first_pass\nsecond_user second_pass\n",
        },
    )
    assert imported.status_code == 200

    popped = client.post("/api/data/accounts/pop")

    assert popped.status_code == 200
    popped_payload = cast(dict[str, dict[str, object]], popped.json())
    assert popped_payload["account"]["account"] == "first_user"


def test_account_store_migrates_app_id_out_of_metadata_json(tmp_path: Path):
    db_path = tmp_path / "accounts-legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE accounts (
                account TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                twofa TEXT,
                email TEXT,
                email_password TEXT,
                token TEXT,
                email_token TEXT,
                status TEXT NOT NULL DEFAULT 'ready',
                last_used TEXT,
                error_msg TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO accounts (
                account, password, status, created_at, updated_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "wx_user",
                "wx_pass",
                "ready",
                "2026-03-23T00:00:00+00:00",
                "2026-03-23T00:00:00+00:00",
                '{"app_id":"wechat","note":"legacy"}',
            ),
        )
        conn.commit()

    store = AccountStore(db_path)
    account = cast(dict[str, object], store.get_account("wx_user"))

    assert account["app_id"] == "wechat"
    assert account["note"] == "legacy"

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT app_id FROM accounts WHERE account = ?", ("wx_user",)).fetchone()
    assert row == ("wechat",)


def test_accounts_import_bootstraps_new_app_config(
    isolated_account_store: AccountStore,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
):
    monkeypatch.setattr("core.app_config.config_dir", lambda: tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/data/accounts/import",
        json={
            "overwrite": True,
            "app_id": "twitter_cn",
            "app_display_name": "Twitter 中文",
            "package_name": "com.twitter.cn",
            "content": "account password\ncn_user cn_pass\n",
        },
    )

    assert response.status_code == 200
    payload = cast(dict[str, object], response.json())
    resolved_app = cast(dict[str, object], payload["resolved_app"])
    assert resolved_app["app_id"] == "twitter_cn"
    assert resolved_app["display_name"] == "Twitter 中文"
    assert resolved_app["package_name"] == "com.twitter.cn"
    assert resolved_app["created"] is True

    document = yaml.safe_load((tmp_path / "apps" / "twitter_cn.yaml").read_text(encoding="utf-8"))
    assert document["app_id"] == "twitter_cn"
    assert document["display_name"] == "Twitter 中文"
    assert document["package_name"] == "com.twitter.cn"
