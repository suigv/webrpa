from __future__ import annotations

import importlib
import random
import shutil
import string
import sys
import time
from pathlib import Path
from typing import Any

from core.config_loader import get_humanized_wrapper_config
from models.humanized import HumanizedWrapperConfig


def _vendor_root() -> Path:
    return Path(__file__).resolve().parents[1] / "vendor"


def _ensure_vendor_path() -> None:
    root = _vendor_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def _detect_browser_binary() -> str | None:
    candidates = [
        "chromium",
        "chromium-browser",
        "google-chrome",
        "google-chrome-stable",
    ]
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path
    return None


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
        self._humanized_config = humanized_config or self._load_runtime_humanized_config()
        self._load()

    def _load_runtime_humanized_config(self) -> HumanizedWrapperConfig:
        try:
            return get_humanized_wrapper_config()
        except Exception:
            return HumanizedWrapperConfig()

    def _load(self) -> None:
        _ensure_vendor_path()
        self._error = ""
        self._error_code = ""
        self._browser_binary = ""
        try:
            importlib.import_module("DrissionGet")
        except Exception as exc:
            self._available = False
            self._error_code = "missing_dependency"
            self._error = f"missing DrissionGet: {exc}"
            return

        try:
            dp = importlib.import_module("DrissionPage")
            self._web_page_cls = getattr(dp, "WebPage", None)
            self._chromium_options_cls = getattr(dp, "ChromiumOptions", None)
            if self._web_page_cls is None:
                self._available = False
                self._error_code = "invalid_runtime"
                self._error = "DrissionPage classes not found"
                return
            browser_binary = _detect_browser_binary()
            if browser_binary is None:
                self._available = False
                self._error_code = "browser_not_found"
                self._error = "no chromium/chrome binary found"
                return
            self._browser_binary = browser_binary
            self._available = True
        except Exception as exc:
            self._available = False
            self._error_code = "missing_dependency"
            self._error = str(exc)

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

    @classmethod
    def startup_diagnostics(cls) -> dict[str, object]:
        _ensure_vendor_path()
        drissionget_ok = False
        drissionpage_ok = False
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
        client = cls()
        return {
            "ready": client.available,
            "error": client.error,
            "error_code": client.error_code,
            "drissionget_importable": drissionget_ok,
            "drissionpage_importable": drissionpage_ok,
            "chromium_binary_found": browser_binary is not None,
            "chromium_binary_path": browser_binary,
        }

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
            self._humanized_page = HumanizedWrapper(self._page, self._humanized_config)
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
            page = self._humanized_page if self._humanized_page is not None else self._page
            if hasattr(page, "ele"):
                return page.ele(selector)
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
        self._humanized_page = None


class HumanizedElement:
    def __init__(self, raw_element: Any, page: Any, config: HumanizedWrapperConfig, rng: random.Random) -> None:
        self._raw = raw_element
        self._page = page
        self._config = config
        self._rng = rng

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw, name)

    def _sleep(self, seconds: float) -> None:
        if seconds <= 0:
            return
        time.sleep(seconds)

    def _rand_range(self, lo: float, hi: float) -> float:
        if hi <= lo:
            return float(lo)
        return float(self._rng.uniform(lo, hi))

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        if value < lo:
            return float(lo)
        if value > hi:
            return float(hi)
        return float(value)

    @staticmethod
    def _to_point(value: Any) -> tuple[float, float] | None:
        if not isinstance(value, (tuple, list)) or len(value) < 2:
            return None
        try:
            return float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_positive(value: float, fallback: float = 1.0) -> float:
        if value <= 0:
            return float(fallback)
        return float(value)

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    @staticmethod
    def _is_word_boundary_char(ch: str) -> bool:
        if not ch:
            return False
        return ch.isspace() or ch in string.punctuation

    def _should_simulate_typo(self) -> bool:
        # Optional stub: disabled unless explicitly enabled by runtime config.
        if not bool(getattr(self._config, "enable_typo_simulation", False)):
            return False
        return self._rng.random() < self._config.typo_probability

    def _bounded_move_steps(self) -> tuple[float, int, float]:
        total_duration = self._rand_range(self._config.move_duration_min, self._config.move_duration_max)
        steps = int(max(1, self._rng.randint(self._config.move_steps_min, self._config.move_steps_max)))
        segment = max(0.02, float(total_duration) / float(max(1, steps)))
        return total_duration, steps, segment

    def _maybe_jitter_point(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        move_x_min: float,
        move_y_min: float,
        move_x_max: float,
        move_y_max: float,
    ) -> tuple[float, float]:
        if self._rng.random() >= self._config.movement_jitter_probability:
            return x, y

        jitter_span = max(1.0, min(self._safe_positive(width), self._safe_positive(height)) * 0.08)
        jx = self._rng.uniform(-jitter_span, jitter_span)
        jy = self._rng.uniform(-jitter_span, jitter_span)
        return (
            self._clamp(x + float(jx), move_x_min, move_x_max),
            self._clamp(y + float(jy), move_y_min, move_y_max),
        )

    def _maybe_overshoot_point(
        self,
        start_x: float,
        start_y: float,
        target_x: float,
        target_y: float,
        move_x_min: float,
        move_y_min: float,
        move_x_max: float,
        move_y_max: float,
    ) -> tuple[float, float] | None:
        if self._rng.random() >= self._config.movement_overshoot_probability:
            return None

        dx = target_x - start_x
        dy = target_y - start_y
        distance = (dx * dx + dy * dy) ** 0.5
        if distance <= 0:
            return None

        unit_x = dx / distance
        unit_y = dy / distance
        overshoot_distance = min(32.0, max(2.0, distance * self._rng.uniform(0.04, 0.12)))
        return (
            self._clamp(target_x + unit_x * overshoot_distance, move_x_min, move_x_max),
            self._clamp(target_y + unit_y * overshoot_distance, move_y_min, move_y_max),
        )

    def _run_move_segment(
        self,
        move_fn: Any,
        start_x: float,
        start_y: float,
        target_x: float,
        target_y: float,
        steps: int,
        segment: float,
        width: float,
        height: float,
        move_x_min: float,
        move_y_min: float,
        move_x_max: float,
        move_y_max: float,
    ) -> None:
        safe_steps = max(1, int(steps))
        for i in range(1, safe_steps + 1):
            t = float(i) / float(safe_steps)
            eased = t * t
            x = start_x + (target_x - start_x) * eased
            y = start_y + (target_y - start_y) * eased
            x, y = self._maybe_jitter_point(x, y, width, height, move_x_min, move_y_min, move_x_max, move_y_max)
            move_fn((x, y), duration=segment)

    def _extract_viewport_bounds(self) -> tuple[float, float, float, float] | None:
        def _extract_from(source: Any) -> tuple[float, float, float, float] | None:
            if source is None:
                return None

            viewport_size = getattr(source, "viewport_size", None)
            size = self._to_point(viewport_size)
            if size is not None and size[0] > 0 and size[1] > 0:
                return 0.0, 0.0, size[0] - 1.0, size[1] - 1.0

            rect = getattr(source, "rect", None)
            if rect is not None:
                rect_size = self._to_point(getattr(rect, "size", None))
                if rect_size is not None and rect_size[0] > 0 and rect_size[1] > 0:
                    rect_location = self._to_point(getattr(rect, "location", None))
                    origin_x, origin_y = rect_location if rect_location is not None else (0.0, 0.0)
                    return origin_x, origin_y, origin_x + rect_size[0] - 1.0, origin_y + rect_size[1] - 1.0

            generic_size = self._to_point(getattr(source, "size", None))
            if generic_size is not None and generic_size[0] > 0 and generic_size[1] > 0:
                return 0.0, 0.0, generic_size[0] - 1.0, generic_size[1] - 1.0

            return None

        page = self._page
        tab = getattr(page, "tab", None)
        for candidate in (tab, page):
            bounds = _extract_from(candidate)
            if bounds is not None:
                return bounds
        return None

    @staticmethod
    def _callable_attr(obj: Any, name: str) -> Any | None:
        fn = getattr(obj, name, None)
        return fn if callable(fn) else None

    def _fallback_raw_input(self, payload: str) -> None:
        input_fn = self._callable_attr(self._raw, "input")
        if input_fn is not None:
            input_fn(payload)
            return

        type_fn = self._callable_attr(self._raw, "type")
        if type_fn is not None:
            type_fn(payload)
            return

        send_keys_fn = self._callable_attr(self._raw, "send_keys")
        if send_keys_fn is not None:
            send_keys_fn(payload)

    def _fallback_raw_click(self) -> None:
        click_fn = self._callable_attr(self._raw, "click")
        if click_fn is not None:
            click_fn()

    def _apply_fallback(self, op: str, payload: str = "", exc: Exception | None = None) -> None:
        policy = str(getattr(self._config, "fallback_policy", "raw") or "raw")
        if policy == "raise":
            if exc is not None:
                raise exc
            raise RuntimeError(f"humanized {op} fallback triggered")
        if policy == "skip":
            return

        try:
            if op == "input":
                self._fallback_raw_input(payload)
            elif op == "click":
                self._fallback_raw_click()
        except Exception:
            # Raw fallback must remain non-fatal for robust degraded mode.
            return

    def _try_action_click_with_hold(self, actions: Any, hold_seconds: float) -> bool:
        hold = max(0.0, float(hold_seconds))

        click_fn = self._callable_attr(actions, "click")
        if click_fn is not None:
            if hold > 0:
                try:
                    click_fn(hold=hold)
                    return True
                except TypeError:
                    pass

        down_up_pairs = (
            ("down", "up"),
            ("mouse_down", "mouse_up"),
            ("press", "release"),
        )
        for down_name, up_name in down_up_pairs:
            down_fn = self._callable_attr(actions, down_name)
            up_fn = self._callable_attr(actions, up_name)
            if down_fn is None or up_fn is None:
                continue
            try:
                down_fn()
                self._sleep(hold)
                up_fn()
                return True
            except Exception:
                continue

        if click_fn is not None:
            try:
                click_fn()
                return True
            except Exception:
                pass

        return False

    def input(self, text: str) -> None:
        payload = str(text)
        try:
            clear_fn = self._callable_attr(self._raw, "clear")
            if clear_fn is not None:
                clear_fn()
        except Exception:
            pass

        actions = getattr(self._page, "actions", None)
        if not self._config.enabled:
            self._apply_fallback("input", payload=payload)
            return

        if actions is None:
            self._apply_fallback("input", payload=payload)
            return

        type_fn = self._callable_attr(actions, "type")
        if type_fn is None:
            self._apply_fallback("input", payload=payload)
            return

        try:
            if hasattr(self._raw, "click"):
                self._raw.click()
        except Exception:
            pass

        prev: str | None = None
        try:
            for ch in payload:
                if self._should_simulate_typo():
                    wrong = self._rng.choice("abcdefghijklmnopqrstuvwxyz")
                    type_fn(wrong)
                    self._sleep(self._rand_range(self._config.typo_delay_min, self._config.typo_delay_max))
                    type_fn("\b")
                    self._sleep(self._rand_range(self._config.backspace_delay_min, self._config.backspace_delay_max))

                type_fn(ch)
                self._sleep(self._rand_range(self._config.typing_delay_min, self._config.typing_delay_max))
                if prev is not None and (not self._is_word_boundary_char(prev)) and self._is_word_boundary_char(ch):
                    if self._rng.random() < self._config.word_pause_probability:
                        self._sleep(self._rand_range(self._config.word_pause_min, self._config.word_pause_max))
                prev = ch
        except Exception as exc:
            self._apply_fallback("input", payload=payload, exc=exc)

    def click(self) -> None:
        if not self._config.enabled:
            self._apply_fallback("click")
            return

        actions = getattr(self._page, "actions", None)
        if actions is None:
            self._apply_fallback("click")
            return

        move_fn = self._callable_attr(actions, "move_to")
        if move_fn is None:
            self._apply_fallback("click")
            return

        try:
            rect = getattr(self._raw, "rect", None)
            if rect is None:
                self._apply_fallback("click")
                return
            location = self._to_point(getattr(rect, "location", None))
            size = self._to_point(getattr(rect, "size", None))
            if location is None or size is None:
                self._apply_fallback("click")
                return

            left, top = location
            width, height = size
            if width <= 0 or height <= 0:
                self._apply_fallback("click")
                return

            elem_x_min = float(left)
            elem_y_min = float(top)
            elem_x_max = elem_x_min + float(width) - 1.0
            elem_y_max = elem_y_min + float(height) - 1.0

            viewport_bounds = self._extract_viewport_bounds()
            if viewport_bounds is not None:
                viewport_x_min, viewport_y_min, viewport_x_max, viewport_y_max = viewport_bounds
                x_min = max(elem_x_min, viewport_x_min)
                y_min = max(elem_y_min, viewport_y_min)
                x_max = min(elem_x_max, viewport_x_max)
                y_max = min(elem_y_max, viewport_y_max)
                if x_min > x_max or y_min > y_max:
                    self._apply_fallback("click")
                    return
            else:
                x_min, y_min, x_max, y_max = elem_x_min, elem_y_min, elem_x_max, elem_y_max

            center_x = elem_x_min + float(width) / 2.0
            center_y = elem_y_min + float(height) / 2.0

            strategy = self._config.target_strategy
            if strategy == "random_inside":
                base_x = self._rand_range(x_min, x_max)
                base_y = self._rand_range(y_min, y_max)
            elif strategy == "center_bias":
                if self._rng.random() < self._config.target_center_bias_probability:
                    base_x = center_x
                    base_y = center_y
                else:
                    base_x = self._rand_range(x_min, x_max)
                    base_y = self._rand_range(y_min, y_max)
            else:
                base_x = center_x
                base_y = center_y

            offset_x = int(self._rng.randint(self._config.click_offset_x_min, self._config.click_offset_x_max))
            offset_y = int(self._rng.randint(self._config.click_offset_y_min, self._config.click_offset_y_max))

            target_x = self._clamp(base_x + float(offset_x), x_min, x_max)
            target_y = self._clamp(base_y + float(offset_y), y_min, y_max)

            _total_duration, steps, segment = self._bounded_move_steps()

            start_x = self._safe_float(getattr(actions, "curr_x", 0.0), default=0.0)
            start_y = self._safe_float(getattr(actions, "curr_y", 0.0), default=0.0)

            if viewport_bounds is not None:
                move_x_min, move_y_min, move_x_max, move_y_max = viewport_bounds
            else:
                move_x_min = min(start_x, elem_x_min)
                move_y_min = min(start_y, elem_y_min)
                move_x_max = max(start_x, elem_x_max)
                move_y_max = max(start_y, elem_y_max)

            overshoot = self._maybe_overshoot_point(
                start_x,
                start_y,
                target_x,
                target_y,
                move_x_min,
                move_y_min,
                move_x_max,
                move_y_max,
            )

            if overshoot is not None:
                over_x, over_y = overshoot
                over_steps = max(1, min(4, steps // 3))
                self._run_move_segment(
                    move_fn,
                    start_x,
                    start_y,
                    over_x,
                    over_y,
                    over_steps,
                    segment,
                    width,
                    height,
                    move_x_min,
                    move_y_min,
                    move_x_max,
                    move_y_max,
                )
                start_x, start_y = over_x, over_y

            self._run_move_segment(
                move_fn,
                start_x,
                start_y,
                target_x,
                target_y,
                steps,
                segment,
                width,
                height,
                move_x_min,
                move_y_min,
                move_x_max,
                move_y_max,
            )

            if self._config.pre_hover_enabled:
                pre_hover_delay = self._rand_range(self._config.pre_hover_delay_min, self._config.pre_hover_delay_max)
                move_fn((target_x, target_y), duration=pre_hover_delay)

            self._sleep(self._rand_range(self._config.pre_click_pause_min, self._config.pre_click_pause_max))

            hold_seconds = self._rand_range(self._config.click_hold_min, self._config.click_hold_max)
            if not self._try_action_click_with_hold(actions, hold_seconds):
                self._apply_fallback("click")
                return

            self._sleep(self._rand_range(self._config.post_click_pause_min, self._config.post_click_pause_max))
        except Exception as exc:
            self._apply_fallback("click", exc=exc)


class HumanizedWrapper:
    def __init__(self, page: Any, config: HumanizedWrapperConfig | None = None) -> None:
        self._page = page
        self._config = config or HumanizedWrapperConfig()
        self._rng = random.Random(self._config.random_seed)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._page, name)

    def ele(self, selector: str) -> Any:
        raw = self._page.ele(selector)
        if raw is None:
            return None
        return HumanizedElement(raw, self._page, self._config, self._rng)
