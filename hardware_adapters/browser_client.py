from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path
from typing import Any


def _vendor_root() -> Path:
    return Path(__file__).resolve().parents[1] / "vendor"


def _ensure_vendor_path() -> None:
    root = _vendor_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


class BrowserClient:
    def __init__(self) -> None:
        self._available = False
        self._error = ""
        self._page: Any = None
        self._web_page_cls: Any = None
        self._chromium_options_cls: Any = None
        self._load()

    def _load(self) -> None:
        _ensure_vendor_path()
        try:
            dp = importlib.import_module("DrissionPage")
            self._web_page_cls = getattr(dp, "WebPage", None)
            self._chromium_options_cls = getattr(dp, "ChromiumOptions", None)
            self._available = self._web_page_cls is not None
            if not self._available:
                self._error = "DrissionPage classes not found"
        except Exception as exc:
            self._available = False
            self._error = str(exc)

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str:
        return self._error

    def open(self, url: str, headless: bool = True) -> bool:
        if not self._available:
            return False
        try:
            options = None
            if self._chromium_options_cls is not None:
                options = self._chromium_options_cls()
                if hasattr(options, "headless"):
                    options.headless(on_off=headless)
            self._page = self._web_page_cls(chromium_options=options) if options else self._web_page_cls()
            self._page.get(url)
            return True
        except Exception as exc:
            self._error = str(exc)
            return False

    def html(self) -> str:
        if self._page is None:
            return ""
        try:
            return str(getattr(self._page, "html", ""))
        except Exception:
            return ""

    def _get_element(self, selector: str):
        if self._page is None:
            return None
        try:
            if hasattr(self._page, "ele"):
                return self._page.ele(selector)
        except Exception:
            return None
        return None

    def exists(self, selector: str) -> bool:
        return self._get_element(selector) is not None

    def input(self, selector: str, text: str) -> bool:
        element = self._get_element(selector)
        if element is None:
            return False
        try:
            if hasattr(element, "clear"):
                element.clear()
            if hasattr(element, "input"):
                element.input(text)
                return True
            if hasattr(element, "type"):
                element.type(text)
                return True
            if hasattr(element, "send_keys"):
                element.send_keys(text)
                return True
        except Exception as exc:
            self._error = str(exc)
            return False
        return False

    def click(self, selector: str) -> bool:
        element = self._get_element(selector)
        if element is None:
            return False
        try:
            if hasattr(element, "click"):
                element.click()
                return True
        except Exception as exc:
            self._error = str(exc)
            return False
        return False

    def current_url(self) -> str:
        if self._page is None:
            return ""
        try:
            return str(getattr(self._page, "url", ""))
        except Exception:
            return ""

    def wait_url_contains(self, fragment: str, timeout_seconds: int) -> bool:
        timeout = max(1, int(timeout_seconds))
        start = time.time()
        while time.time() - start <= timeout:
            if fragment in self.current_url():
                return True
            time.sleep(0.2)
        return False

    def close(self) -> None:
        if self._page is None:
            return
        try:
            if hasattr(self._page, "close"):
                self._page.close()
            elif hasattr(self._page, "quit"):
                self._page.quit()
        except Exception:
            pass
        self._page = None
