from new.hardware_adapters.browser_client import BrowserClient


def test_browser_adapter_import_and_state():
    client = BrowserClient()
    assert isinstance(client.available, bool)
    assert isinstance(client.error, str)
