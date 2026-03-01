from new.plugins.x_auto_login import run


class FakeBrowser:
    def __init__(self, html: str = "", url_ok: bool = True, success_exists: bool = True):
        self.available = True
        self.error = ""
        self._html = html
        self._url_ok = url_ok
        self._success_exists = success_exists

    def open(self, url: str, headless: bool = True) -> bool:
        return True

    def input(self, selector: str, value: str) -> bool:
        return True

    def click(self, selector: str) -> bool:
        return True

    def html(self) -> str:
        return self._html

    def exists(self, selector: str) -> bool:
        return self._success_exists

    def wait_url_contains(self, fragment: str, timeout_seconds: int) -> bool:
        return self._url_ok

    def close(self) -> None:
        return None


def _loader(_: str):
    class Creds:
        username_or_email = "u"
        password = "p"

    return Creds()


def test_x_login_plugin_contract_completed():
    result = run(
        {
            "payload": {"task": "x_auto_login", "credentials_ref": "/etc/myt/x_credentials.json"},
            "credential_loader": _loader,
            "browser_factory": lambda: FakeBrowser(html="home", url_ok=True, success_exists=True),
        }
    )
    assert result["status"] == "completed"
    assert result["checkpoint"] == "verify_success"


def test_x_login_2fa_branch_missing_code():
    result = run(
        {
            "payload": {"task": "x_auto_login", "credentials_ref": "/etc/myt/x_credentials.json"},
            "credential_loader": _loader,
            "browser_factory": lambda: FakeBrowser(html="two-factor verification code", url_ok=False, success_exists=False),
        }
    )
    assert result["status"] == "failed_2fa_required"
    assert result["checkpoint"] == "two_factor"


def test_x_login_2fa_branch_invalid_code():
    result = run(
        {
            "payload": {
                "task": "x_auto_login",
                "credentials_ref": "/etc/myt/x_credentials.json",
                "two_factor_code": "111111",
            },
            "credential_loader": _loader,
            "browser_factory": lambda: FakeBrowser(html="two-factor verification code", url_ok=False, success_exists=False),
        }
    )
    assert result["status"] == "failed_2fa_invalid"
    assert result["checkpoint"] == "two_factor"


def test_x_login_adapter_unavailable():
    class UnavailableBrowser:
        available = False
        error = "DrissionPage unavailable"

        def close(self) -> None:
            return None

    result = run(
        {
            "payload": {"task": "x_auto_login", "credentials_ref": "/etc/myt/x_credentials.json"},
            "credential_loader": _loader,
            "browser_factory": UnavailableBrowser,
        }
    )
    assert result["status"] == "failed_adapter_unavailable"


def test_x_login_rejects_untrusted_login_url():
    result = run(
        {
            "payload": {
                "task": "x_auto_login",
                "credentials_ref": "/etc/myt/x_credentials.json",
                "login_url": "https://evil.example.com/login",
            },
            "credential_loader": _loader,
            "browser_factory": lambda: FakeBrowser(),
        }
    )
    assert result["status"] == "failed_config_error"
    assert result["checkpoint"] == "contract"
