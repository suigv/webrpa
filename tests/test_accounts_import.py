from fastapi.testclient import TestClient

from api.server import app
from core.account_parser import parse_accounts_text


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
    assert parsed["valid"] == 3
    assert parsed["invalid"] == 1
    assert parsed["accounts"][0]["account"] == "alice@example.com"
    assert parsed["accounts"][0]["password"] == "pass1"
    assert parsed["accounts"][0]["twofa"] == "123456"


def test_accounts_import_api_and_parsed_view_roundtrip():
    client = TestClient(app)

    backup = client.get("/api/data/accounts")
    assert backup.status_code == 200
    backup_text = backup.json().get("data", "")

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
        payload = resp.json()
        assert payload["status"] == "ok"
        assert payload["valid"] == 2
        assert payload["invalid"] == 0
        assert payload["stored"] == 2

        parsed = client.get("/api/data/accounts/parsed")
        assert parsed.status_code == 200
        accounts = parsed.json().get("accounts", [])
        assert len(accounts) == 2
        assert accounts[0]["account"] == "u1"
        assert accounts[0]["password"] == "p1"
        assert accounts[0]["twofa"] == "111111"
        assert accounts[1]["twofa"] == ""
    finally:
        _ = client.put("/api/data/accounts", json={"content": backup_text})
