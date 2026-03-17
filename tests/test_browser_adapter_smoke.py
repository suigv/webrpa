import types

import hardware_adapters.browser_client as browser_client_module
from hardware_adapters.browser_client import BrowserClient


def test_browser_adapter_import_and_state():
    client = BrowserClient()
    assert isinstance(client.available, bool)
    assert isinstance(client.error, str)


def test_browser_adapter_missing_dependency_error_code(monkeypatch):
    def _fake_import(name: str):
        if name == "DrissionGet":
            raise ModuleNotFoundError("No module named 'DrissionGet'")
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(browser_client_module.importlib, "import_module", _fake_import)
    monkeypatch.setattr(
        browser_client_module, "_detect_browser_binary", lambda: "/usr/bin/chromium"
    )

    client = BrowserClient()
    assert client.available is False
    assert client.error_code == "missing_dependency"
    assert "DrissionGet" in client.error


def test_browser_adapter_missing_browser_binary_error_code(monkeypatch):
    fake_dp = types.SimpleNamespace(WebPage=object, ChromiumOptions=object)

    def _fake_import(name: str):
        if name == "DrissionGet":
            return object()
        if name == "DrissionPage":
            return fake_dp
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(browser_client_module.importlib, "import_module", _fake_import)
    monkeypatch.setattr(browser_client_module, "_detect_browser_binary", lambda: None)

    client = BrowserClient()
    assert client.available is False
    assert client.error_code == "browser_not_found"
    assert "binary" in client.error


def test_browser_adapter_available_when_dependencies_and_binary_present(monkeypatch):
    fake_dp = types.SimpleNamespace(WebPage=object, ChromiumOptions=object)

    def _fake_import(name: str):
        if name == "DrissionGet":
            return object()
        if name == "DrissionPage":
            return fake_dp
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(browser_client_module.importlib, "import_module", _fake_import)
    monkeypatch.setattr(
        browser_client_module, "_detect_browser_binary", lambda: "/usr/bin/chromium"
    )

    client = BrowserClient()
    assert client.available is True
    assert client.error_code == ""
    assert client.browser_binary == "/usr/bin/chromium"
