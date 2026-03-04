# pyright: reportMissingImports=false
from fastapi.testclient import TestClient
from typing import Any, ClassVar

from new.api.server import app
from new.hardware_adapters.browser_client import BrowserClient
from new.models.humanized import HumanizedWrapperConfig
import new.core.config_loader as config_loader


class _FakeRect:
    def __init__(self) -> None:
        self.location = (10, 20)
        self.size = (80, 40)


class _FakeElement:
    def __init__(self) -> None:
        self.rect = _FakeRect()
        self.cleared = 0
        self.raw_clicks = 0
        self.raw_inputs = []

    def clear(self) -> None:
        self.cleared += 1

    def click(self) -> None:
        self.raw_clicks += 1

    def input(self, text: str) -> None:
        self.raw_inputs.append(text)


class _FakeActionsFull:
    def __init__(self) -> None:
        self.curr_x = 0
        self.curr_y = 0
        self.moves = []
        self.clicks = 0
        self.types = []

    def move_to(self, location, duration=0.0):
        self.curr_x, self.curr_y = location
        self.moves.append((location, duration))
        return self

    def click(self, hold=None):
        self.clicks += 1
        return self

    def type(self, text: str):
        self.types.append(text)
        return self


class _FakeActionsWithoutTypeOrMove:
    def __init__(self) -> None:
        self.curr_x = 0
        self.curr_y = 0


class _FakeChromiumOptions:
    def __init__(self) -> None:
        self.headless_value = None

    def headless(self, on_off=True) -> None:
        self.headless_value = bool(on_off)


class _FakeWebPage:
    last_instance = None
    next_actions_factory: ClassVar[Any] = staticmethod(lambda: _FakeActionsFull())
    next_element_factory: ClassVar[Any] = staticmethod(lambda: _FakeElement())

    def __init__(self, chromium_options=None) -> None:
        self.chromium_options = chromium_options
        self.actions = self.__class__.next_actions_factory()
        self._element = self.__class__.next_element_factory()
        self.url = ""
        self.got_urls = []
        self.html = "<html>ok</html>"
        self.closed = False
        self.__class__.last_instance = self

    def get(self, url: str) -> None:
        self.url = url
        self.got_urls.append(url)

    def ele(self, selector: str):
        if selector in {"#input", "#btn", "#exists"}:
            return self._element
        return None

    def close(self) -> None:
        self.closed = True


def _patch_browser_client_load(monkeypatch) -> None:
    def _fake_load(self):
        self._available = True
        self._error = ""
        self._web_page_cls = _FakeWebPage
        self._chromium_options_cls = _FakeChromiumOptions

    monkeypatch.setattr(BrowserClient, "_load", _fake_load)


def _zero_delay_humanized_config(enabled: bool) -> HumanizedWrapperConfig:
    return HumanizedWrapperConfig(
        enabled=enabled,
        random_seed=7,
        typing_delay_min=0,
        typing_delay_max=0,
        typo_probability=0,
        typo_delay_min=0,
        typo_delay_max=0,
        backspace_delay_min=0,
        backspace_delay_max=0,
        move_duration_min=0,
        move_duration_max=0,
        move_steps_min=1,
        move_steps_max=1,
        pre_hover_enabled=False,
        pre_click_pause_min=0,
        pre_click_pause_max=0,
        click_hold_min=0,
        click_hold_max=0,
        post_click_pause_min=0,
        post_click_pause_max=0,
    )


def test_config_route_returns_humanized_section():
    client = TestClient(app)
    resp = client.get("/api/config/")
    assert resp.status_code == 200
    payload = resp.json()
    assert "humanized" in payload
    assert isinstance(payload["humanized"], dict)
    assert "typo_probability" in payload["humanized"]


def test_config_route_rejects_invalid_humanized_probability():
    client = TestClient(app)
    resp = client.put("/api/config/", json={"humanized": {"typo_probability": 1.5}})
    assert resp.status_code == 422


def test_browser_client_loads_runtime_humanized_config():
    backup = config_loader.ConfigLoader._config
    try:
        config_loader.ConfigLoader._config = {
            "host_ip": "127.0.0.1",
            "device_ips": {},
            "total_devices": 1,
            "cloud_machines_per_device": 10,
            "sdk_port": 8000,
            "humanized": {
                "enabled": True,
                "typing_delay_min": 0.1,
                "typing_delay_max": 0.2,
                "typo_probability": 0.2,
                "typo_delay_min": 0.05,
                "typo_delay_max": 0.10,
                "backspace_delay_min": 0.01,
                "backspace_delay_max": 0.02,
                "click_offset_x_min": -2,
                "click_offset_x_max": 2,
                "click_offset_y_min": -3,
                "click_offset_y_max": 3,
                "move_duration_min": 0.3,
                "move_duration_max": 0.6,
                "move_steps_min": 4,
                "move_steps_max": 8,
                "random_seed": 7,
            },
        }

        client = BrowserClient()
        cfg = client._humanized_config
        assert isinstance(cfg, HumanizedWrapperConfig)
        assert cfg.enabled is True
        assert cfg.typo_probability == 0.2
        assert cfg.move_steps_min == 4
        assert cfg.random_seed == 7
    finally:
        config_loader.ConfigLoader._config = backup


def test_browser_client_enabled_uses_humanized_page_path(monkeypatch):
    _patch_browser_client_load(monkeypatch)
    _FakeWebPage.next_actions_factory = lambda: _FakeActionsFull()
    _FakeWebPage.next_element_factory = lambda: _FakeElement()

    client = BrowserClient(humanized_config=_zero_delay_humanized_config(enabled=True))

    assert client.open("https://example.com", headless=True) is True
    page = _FakeWebPage.last_instance
    assert page is not None
    assert page.chromium_options.headless_value is True
    assert page.got_urls == ["https://example.com"]
    assert client.exists("#exists") is True

    assert client.click("#btn") is True
    assert page.actions.clicks == 1
    assert page._element.raw_clicks == 0

    assert client.input("#input", "ok") is True
    assert page.actions.types == ["o", "k"]
    assert page._element.raw_inputs == []


def test_browser_client_disabled_uses_raw_legacy_element_methods(monkeypatch):
    _patch_browser_client_load(monkeypatch)
    _FakeWebPage.next_actions_factory = lambda: _FakeActionsFull()
    _FakeWebPage.next_element_factory = lambda: _FakeElement()

    client = BrowserClient(humanized_config=_zero_delay_humanized_config(enabled=False))

    assert client.open("https://example.com", headless=False) is True
    page = _FakeWebPage.last_instance
    assert page is not None
    assert page.chromium_options.headless_value is False

    assert client.input("#input", "legacy") is True
    assert client.click("#btn") is True
    assert page.actions.types == []
    assert page.actions.clicks == 0
    assert page._element.raw_inputs == ["legacy"]
    assert page._element.raw_clicks == 1


def test_browser_client_enabled_fallbacks_when_humanized_capabilities_missing(monkeypatch):
    _patch_browser_client_load(monkeypatch)
    _FakeWebPage.next_actions_factory = lambda: _FakeActionsWithoutTypeOrMove()
    _FakeWebPage.next_element_factory = lambda: _FakeElement()

    client = BrowserClient(humanized_config=_zero_delay_humanized_config(enabled=True))

    assert client.open("https://example.com") is True
    page = _FakeWebPage.last_instance
    assert page is not None

    # Missing actions.type/move_to should degrade to raw element fallback without crashing.
    assert client.input("#input", "fallback") is True
    assert client.click("#btn") is True
    assert client.exists("#exists") is True
    assert page._element.raw_inputs == ["fallback"]
    assert page._element.raw_clicks == 1

    client.close()
    assert page.closed is True


def test_browser_client_normalizes_humanized_config_bounds_and_defaults():
    backup = config_loader.ConfigLoader._config
    try:
        config_loader.ConfigLoader._config = {
            "host_ip": "127.0.0.1",
            "device_ips": {},
            "total_devices": 1,
            "cloud_machines_per_device": 10,
            "sdk_port": 8000,
            "humanized": {
                "enabled": "yes",
                "target_strategy": "not-a-strategy",
                "fallback_policy": "unknown",
                "typo_probability": 3.5,
                "movement_jitter_probability": -1,
                "move_steps_min": 0,
                "move_steps_max": -8,
                "click_offset_x_min": 20,
                "click_offset_x_max": -20,
                "random_seed": "bad-seed",
            },
        }

        cfg = BrowserClient()._humanized_config
        assert isinstance(cfg, HumanizedWrapperConfig)
        assert cfg.enabled is True
        assert cfg.target_strategy == "center_bias"
        assert cfg.fallback_policy == "raw"
        assert cfg.typo_probability == 1.0
        assert cfg.movement_jitter_probability == 0.0
        assert cfg.move_steps_min == 1
        assert cfg.move_steps_max == 1
        assert cfg.click_offset_x_min == 20
        assert cfg.click_offset_x_max == 20
        assert cfg.random_seed == 0
    finally:
        config_loader.ConfigLoader._config = backup


def test_browser_client_uses_legacy_humanization_fields_when_humanized_missing():
    backup = config_loader.ConfigLoader._config
    try:
        config_loader.ConfigLoader._config = {
            "host_ip": "127.0.0.1",
            "device_ips": {},
            "total_devices": 1,
            "cloud_machines_per_device": 10,
            "sdk_port": 8000,
            "humanization_enabled": True,
            "humanization_seed": 99,
        }

        cfg = BrowserClient()._humanized_config
        assert isinstance(cfg, HumanizedWrapperConfig)
        assert cfg.enabled is True
        assert cfg.random_seed == 99
        assert cfg.target_strategy == "center_bias"
        assert cfg.fallback_policy == "raw"
    finally:
        config_loader.ConfigLoader._config = backup
