import json
from pathlib import Path

import pytest

from core.credentials_loader import load_credentials_from_ref


def test_x_login_credentials_loader_happy_path(tmp_path: Path, monkeypatch):
    cred_file = tmp_path / "x_credentials.json"
    cred_file.write_text(
        json.dumps({"username_or_email": "demo@example.com", "password": "secret"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MYT_CREDENTIAL_ALLOWLIST", str(tmp_path))

    creds = load_credentials_from_ref(str(cred_file))
    assert creds.username_or_email == "demo@example.com"
    assert creds.password == "secret"


def test_x_login_credentials_loader_rejects_path_outside_allowlist(tmp_path: Path, monkeypatch):
    allowed_root = tmp_path / "allowed"
    blocked_root = tmp_path / "blocked"
    allowed_root.mkdir()
    blocked_root.mkdir()
    cred_file = blocked_root / "x_credentials.json"
    cred_file.write_text(
        json.dumps({"username_or_email": "demo@example.com", "password": "secret"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MYT_CREDENTIAL_ALLOWLIST", str(allowed_root))

    with pytest.raises(ValueError, match="outside allowlist"):
        load_credentials_from_ref(str(cred_file))


def test_x_login_credentials_loader_rejects_symlink(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps({"username_or_email": "demo@example.com", "password": "secret"}),
        encoding="utf-8",
    )
    link = tmp_path / "link.json"
    link.symlink_to(source)
    monkeypatch.setenv("MYT_CREDENTIAL_ALLOWLIST", str(tmp_path))

    with pytest.raises(ValueError, match="symlink"):
        load_credentials_from_ref(str(link))
