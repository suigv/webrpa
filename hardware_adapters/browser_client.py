from __future__ import annotations

import importlib
import random
import string
import sys
import time
from pathlib import Path
from typing import Any, Optional

from core.config_loader import get_humanized_wrapper_config
from models.humanized import HumanizedWrapperConfig


def _vendor_root() -> Path:
    return Path(__file__).resolve().parents[1] / "vendor"


def _ensure_vendor_on_path() -> None:
    vendor_path = _vendor_root()
    if vendor_path.exists():
        vendor_text = str(vendor_path)
        if vendor_text not in sys.path:
            sys.path.insert(0, vendor_text)


def _detect_browser_binary() -> str | None:
    try:
        from DrissionPage._functions.browser import get_binary

        return get_binary() or None
    except Exception:
        return None


def _to_point(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (tuple, list)) or len(value) < 2:
        return None
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None


def _element_bounds(raw_element: Any) -> tuple[float, float, float, float] | None:
    rect = getattr(raw_element, "rect", None)
    if rect is None:
        return None
    location = _to_point(getattr(rect, "location", None))
    size = _to_point(getattr(rect, "size", None))
    if location is None or size is None:
        return None
    left, top = location
    width, height = size
    if width <= 0 or height <= 0:
        return None
    right = left + width - 1
    bottom = top + height - 1
    return left, top, right, bottom


def _viewport_bounds(page: Any) -> tuple[int, int, int, int] | None:
    viewport = getattr(page, "viewport_size", None)
    if not isinstance(viewport, (tuple, list)) or len(viewport) < 2:
        return None
    try:
        width = int(viewport[0])
        height = int(viewport[1])
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return 0, 0, width - 1, height - 1


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return min(max(value, min_value), max_value)


def _clamp_point(
    x: float,
    y: float,
    bounds: tuple[float, float, float, float],
    viewport: tuple[int, int, int, int] | None,
) -> tuple[float, float]:
    left, top, right, bottom = bounds
    x = _clamp(x, left, right)
    y = _clamp(y, top, bottom)
    if viewport is None:
        return x, y
    v_left, v_top, v_right, v_bottom = viewport
    x = _clamp(x, v_left, v_right)
    y = _clamp(y, v_top, v_bottom)
    return x, y


def _is_word_boundary(char: str) -> bool:
    return char.isspace() or char in string.punctuation


def _pick_typo_char(rng: random.Random, original: str) -> str:
    pool = string.ascii_lowercase + string.digits
    if not pool:
        return "x"
    if original and original in pool and len(pool) > 1:
        pool = pool.replace(original, "")
    return rng.choice(pool)


class HumanizedElement:
    def __init__(
        self,
        raw_element: Any,
        page: Any,
        config: HumanizedWrapperConfig,
        rng: random.Random,
    ) -> None:
        self._raw = raw_element
        self._page = page
        self._config = config
        self._rng = rng

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw, name)

    def _fallback_input(self, text: str, reason: str) -> None:
        policy = self._config.fallback_policy
        if policy == "skip":
            return
        if policy == "raise":
            raise RuntimeError(reason)
        if hasattr(self._raw, "input"):
            self._raw.input(text)

    def _fallback_click(self, reason: str) -> None:
        policy = self._config.fallback_policy
        if policy == "skip":
            return
        if policy == "raise":
            raise RuntimeError(reason)
        if hasattr(self._raw, "click"):
            self._raw.click()

    def input(self, text: str) -> None:
        if not self._config.enabled:
            if hasattr(self._raw, "input"):
                self._raw.input(text)
            return

        actions = getattr(self._page, "actions", None)
        if actions is None or not hasattr(actions, "type"):
            self._fallback_input(text, "actions.type missing")
            return

        enable_typo = bool(getattr(self._config, "enable_typo_simulation", False))

        for char in text:
            delay = self._rng.uniform(self._config.typing_delay_min, self._config.typing_delay_max)
            if delay > 0:
                time.sleep(delay)

            if enable_typo and self._rng.random() < self._config.typo_probability:
                wrong_char = _pick_typo_char(self._rng, char)
                actions.type(wrong_char)
                typo_delay = self._rng.uniform(self._config.typo_delay_min, self._config.typo_delay_max)
                if typo_delay > 0:
                    time.sleep(typo_delay)
                actions.type("\b")
                backspace_delay = self._rng.uniform(self._config.backspace_delay_min, self._config.backspace_delay_max)
                if backspace_delay > 0:
                    time.sleep(backspace_delay)

            actions.type(char)

            if _is_word_boundary(char) and self._rng.random() < self._config.word_pause_probability:
                pause = self._rng.uniform(self._config.word_pause_min, self._config.word_pause_max)
                if pause > 0:
                    time.sleep(pause)

    def _select_target(self, bounds: tuple[float, float, float, float]) -> tuple[float, float]:
        left, top, right, bottom = bounds
        width = max(1.0, right - left + 1)
        height = max(1.0, bottom - top + 1)

        strategy = self._config.target_strategy
        if strategy == "center":
            target_x = left + width / 2
            target_y = top + height / 2
        elif strategy == "random_inside":
            target_x = self._rng.randint(int(left), int(right))
            target_y = self._rng.randint(int(top), int(bottom))
        else:
            if self._rng.random() < self._config.target_center_bias_probability:
                target_x = left + width / 2
                target_y = top + height / 2
            else:
                target_x = self._rng.randint(int(left), int(right))
                target_y = self._rng.randint(int(top), int(bottom))

        offset_x = self._rng.randint(self._config.click_offset_x_min, self._config.click_offset_x_max)
        offset_y = self._rng.randint(self._config.click_offset_y_min, self._config.click_offset_y_max)
        target_x += offset_x
        target_y += offset_y

        viewport = _viewport_bounds(self._page)
        target_x, target_y = _clamp_point(target_x, target_y, bounds, viewport)
        return target_x, target_y

    def _build_moves(
        self,
        actions: Any,
        bounds: tuple[float, float, float, float],
        target: tuple[float, float],
    ) -> list[tuple[tuple[int, int], float]]:
        start_x = float(getattr(actions, "curr_x", 0))
        start_y = float(getattr(actions, "curr_y", 0))
        target_x, target_y = target
        steps = self._rng.randint(self._config.move_steps_min, self._config.move_steps_max)
        steps = max(1, steps)
        viewport = _viewport_bounds(self._page)

        moves: list[tuple[tuple[int, int], float]] = []
        for step in range(1, steps + 1):
            t = step / steps
            x = start_x + (target_x - start_x) * t
            y = start_y + (target_y - start_y) * t
            if step < steps and self._rng.random() < self._config.movement_jitter_probability:
                x += self._rng.randint(-2, 2)
                y += self._rng.randint(-2, 2)
            x, y = _clamp_point(x, y, bounds, viewport)
            duration = self._rng.uniform(self._config.move_duration_min, self._config.move_duration_max)
            moves.append(((int(round(x)), int(round(y))), duration))

        if self._rng.random() < self._config.movement_overshoot_probability and len(moves) >= 1:
            span = max(1, int(min(bounds[2] - bounds[0] + 1, bounds[3] - bounds[1] + 1) * 0.2))
            over_x = target_x + self._rng.randint(-span, span)
            over_y = target_y + self._rng.randint(-span, span)
            over_x, over_y = _clamp_point(over_x, over_y, bounds, viewport)
            duration = self._rng.uniform(self._config.move_duration_min, self._config.move_duration_max)
            moves.insert(-1, ((int(round(over_x)), int(round(over_y))), duration))

        if self._config.pre_hover_enabled:
            pre_hover_delay = self._rng.uniform(self._config.pre_hover_delay_min, self._config.pre_hover_delay_max)
            moves.append(((int(round(target_x)), int(round(target_y))), pre_hover_delay))

        return moves

    def click(self) -> None:
        if not self._config.enabled:
            if hasattr(self._raw, "click"):
                self._raw.click()
            return

        actions = getattr(self._page, "actions", None)
        if actions is None or not hasattr(actions, "move_to"):
            self._fallback_click("actions.move_to missing")
            return

        bounds = _element_bounds(self._raw)
        if bounds is None:
            self._fallback_click("element bounds unavailable")
            return

        target = self._select_target(bounds)
        moves = self._build_moves(actions, bounds, target)

        for (x, y), duration in moves:
            actions.move_to((x, y), duration=duration)

        pre_pause = self._rng.uniform(self._config.pre_click_pause_min, self._config.pre_click_pause_max)
        if pre_pause > 0:
            time.sleep(pre_pause)

        if hasattr(actions, "click"):
            actions.click()
        elif hasattr(actions, "down") and hasattr(actions, "up"):
            actions.down()
            hold = self._rng.uniform(self._config.click_hold_min, self._config.click_hold_max)
            if hold > 0:
                time.sleep(hold)
            actions.up()
        else:
            self._fallback_click("actions click unavailable")
            return

        post_pause = self._rng.uniform(self._config.post_click_pause_min, self._config.post_click_pause_max)
        if post_pause > 0:
            time.sleep(post_pause)


class HumanizedWrapper:
    def __init__(self, page: Any, config: HumanizedWrapperConfig) -> None:
        self._page = page
        self._config = config
        self._rng = random.Random(config.random_seed)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._page, name)

    def ele(self, selector: str) -> Any:
        raw = self._page.ele(selector)
        if raw is None:
            return None
        return HumanizedElement(raw, self._page, self._config, self._rng)


class BrowserClient:
    def __init__(self, humanized_config: HumanizedWrapperConfig | None = None) -> None:
        self._available = False
        self._error = ""
        self._error_code = ""
        self._browser_binary = ""
        self._page: Any = None
        self._humanized_page: Any = None
        self._web_page_cls: Any = None
        self._chromium_options_cls: Any = None
        self._current_profile_dir: Optional[Path] = None

        if humanized_config is None:
            humanized_config = get_humanized_wrapper_config()
        self._humanized_config = humanized_config

        self._load()

    def _load(self) -> None:
        _ensure_vendor_on_path()
        self._available = False
        self._error = ""
        self._error_code = ""
        self._browser_binary = ""

        try:
            importlib.import_module("DrissionGet")
        except Exception as exc:
            self._error = str(exc)
            self._error_code = "missing_dependency"
            return

        try:
            dp_module = importlib.import_module("DrissionPage")
        except Exception as exc:
            self._error = str(exc)
            self._error_code = "missing_dependency"
            return

        browser_binary = _detect_browser_binary()
        if not browser_binary:
            self._error = "browser binary not found"
            self._error_code = "browser_not_found"
            return

        self._browser_binary = str(browser_binary)
        self._web_page_cls = getattr(dp_module, "WebPage", None)
        self._chromium_options_cls = getattr(dp_module, "ChromiumOptions", None)
        self._available = True

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str:
        return self._error

    @property
    def error_code(self) -> str:
        return self._error_code

    @property
    def browser_binary(self) -> str:
        return self._browser_binary

    @staticmethod
    def startup_diagnostics() -> dict[str, Any]:
        _ensure_vendor_on_path()
        drissionpage_ok = False
        drissionget_ok = False
        try:
            importlib.import_module("DrissionGet")
            drissionget_ok = True
        except Exception:
            drissionget_ok = False
        try:
            importlib.import_module("DrissionPage")
            drissionpage_ok = True
        except Exception:
            drissionpage_ok = False

        browser_binary = _detect_browser_binary()
        client = BrowserClient()
        return {
            "ready": client.available,
            "error": client.error,
            "error_code": client.error_code,
            "drissionget_importable": drissionget_ok,
            "drissionpage_importable": drissionpage_ok,
            "chromium_binary_found": browser_binary is not None,
            "chromium_binary_path": browser_binary,
        }

    def open(self, url: str, headless: bool = True, profile_id: str | None = None) -> bool:
        if not self._available:
            return False
        try:
            options = None
            self._current_profile_dir = None
            if self._chromium_options_cls is not None:
                options = self._chromium_options_cls()
                if hasattr(options, "headless"):
                    options.headless(on_off=headless)
                if profile_id:
                    import hashlib
                    import os

                    safe_id = hashlib.md5(profile_id.encode("utf-8")).hexdigest()
                    base_dir = os.environ.get("MYT_USER_DATA_DIR", "/tmp/webrpa_browser_profiles")
                    profile_dir = Path(base_dir) / safe_id
                    profile_dir.mkdir(parents=True, exist_ok=True)
                    self._current_profile_dir = profile_dir
                    if hasattr(options, "set_user_data_path"):
                        options.set_user_data_path(str(profile_dir))

            self._page = self._web_page_cls(chromium_options=options) if options else self._web_page_cls()
            self._humanized_page = HumanizedWrapper(self._page, self._humanized_config)
            self._page.get(url)
            return True
        except Exception as exc:
            self._error = str(exc)
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

        if self._current_profile_dir and self._current_profile_dir.exists():
            import shutil

            try:
                shutil.rmtree(self._current_profile_dir, ignore_errors=True)
            except Exception:
                pass

        self._page = None
        self._humanized_page = None
        self._current_profile_dir = None

    def html(self) -> str:
        if self._page is None:
            return ""
        try:
            return str(getattr(self._page, "html", ""))
        except Exception:
            return ""

    def _get_element_raw(self, selector: str) -> Any:
        if self._page is None:
            return None
        try:
            if hasattr(self._page, "ele"):
                return self._page.ele(selector)
            return None
        except Exception:
            return None

    def _get_element(self, selector: str) -> Any:
        if self._page is None:
            return None
        try:
            page = self._humanized_page if self._humanized_page is not None else self._page
            if hasattr(page, "ele"):
                return page.ele(selector)
            return None
        except Exception:
            return None

    def exists(self, selector: str) -> bool:
        return self._get_element_raw(selector) is not None

    def click(self, selector: str) -> bool:
        el = self._get_element(selector)
        if el:
            try:
                el.click()
                return True
            except Exception:
                return False
        return False

    def input(self, selector: str, text: str) -> bool:
        el = self._get_element(selector)
        if el:
            try:
                el.input(text)
                return True
            except Exception:
                return False
        return False

    def wait_url_contains(self, text: str, timeout_seconds: int = 10) -> bool:
        if self._page is None:
            return False
        try:
            if hasattr(self._page, "wait_url_contains"):
                return bool(self._page.wait_url_contains(text, timeout=timeout_seconds))
            return False
        except Exception:
            return False
