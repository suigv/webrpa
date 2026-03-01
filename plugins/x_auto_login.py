from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import Any, Callable
from urllib.parse import urlparse

from new.hardware_adapters.browser_client import BrowserClient

STATUS_COMPLETED = "completed"
STATUS_FAILED_BAD_CREDENTIALS = "failed_bad_credentials"
STATUS_FAILED_2FA_REQUIRED = "failed_2fa_required"
STATUS_FAILED_2FA_INVALID = "failed_2fa_invalid"
STATUS_FAILED_CHECKPOINT_TIMEOUT = "failed_checkpoint_timeout"
STATUS_FAILED_ADAPTER_UNAVAILABLE = "failed_adapter_unavailable"
STATUS_FAILED_CAPTCHA_DETECTED = "failed_captcha_detected"
STATUS_FAILED_CONFIG_ERROR = "failed_config_error"

LOGIN_URL = "https://x.com/i/flow/login"
ALLOWED_LOGIN_HOSTS = {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}

IDENTIFIER_SELECTORS = [
    "input[autocomplete='username']",
    "input[name='text']",
]
NEXT_SELECTORS = [
    "button[data-testid='LoginForm_Login_Button']",
    "div[role='button'][data-testid='ocfEnterTextNextButton']",
    "div[role='button']:has(span)",
]
PASSWORD_SELECTORS = [
    "input[name='password']",
    "input[autocomplete='current-password']",
]
TWO_FACTOR_SELECTORS = [
    "input[name='text']",
    "input[inputmode='numeric']",
]
TWO_FACTOR_SUBMIT_SELECTORS = [
    "div[role='button'][data-testid='ocfEnterTextNextButton']",
    "button[data-testid='LoginForm_Login_Button']",
]
SUCCESS_SELECTORS = [
    "a[data-testid='SideNav_AccountSwitcher_Button']",
    "button[data-testid='SideNav_AccountSwitcher_Button']",
    "div[data-testid='SideNav_AccountSwitcher_Button']",
]


@dataclass
class Credentials:
    username_or_email: str
    password: str


def _allowed_credential_roots() -> list[Path]:
    raw = os.environ.get("MYT_CREDENTIAL_ALLOWLIST", "/etc/myt")
    roots: list[Path] = []
    for item in raw.split(":"):
        cleaned = item.strip()
        if not cleaned:
            continue
        roots.append(Path(cleaned).expanduser().resolve())
    return roots


def _is_allowed_path(path: Path) -> bool:
    for root in _allowed_credential_roots():
        if path == root or root in path.parents:
            return True
    return False


def load_credentials_from_ref(credentials_ref: str) -> Credentials:
    ref = str(credentials_ref or "").strip()
    if not ref:
        raise ValueError("credentials_ref is required")

    raw_path = Path(ref).expanduser()
    if raw_path.is_symlink():
        raise ValueError("credentials_ref symlink is not allowed")

    path = raw_path.resolve()
    if not path.exists() or not path.is_file():
        raise ValueError("credentials_ref file does not exist")
    if not _is_allowed_path(path):
        raise ValueError("credentials_ref path is outside allowlist")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError("credentials_ref JSON is invalid") from exc

    if not isinstance(payload, dict):
        raise ValueError("credentials JSON must be object")

    username = str(payload.get("username_or_email") or "").strip()
    password = str(payload.get("password") or "").strip()
    if not username or not password:
        raise ValueError("credentials JSON requires username_or_email and password")

    return Credentials(username_or_email=username, password=password)


def _result(task: str, status: str, checkpoint: str, message: str, evidence_ref: str = "") -> dict[str, Any]:
    return {
        "ok": status == STATUS_COMPLETED,
        "task": task,
        "status": status,
        "checkpoint": checkpoint,
        "message": message,
        "evidence_ref": evidence_ref,
    }


def _contains_any(text: str, options: list[str]) -> bool:
    lower = text.lower()
    return any(opt.lower() in lower for opt in options)


def _is_allowed_login_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() in ALLOWED_LOGIN_HOSTS


def _try_input(browser: Any, selectors: list[str], value: str) -> bool:
    for selector in selectors:
        if browser.input(selector, value):
            return True
    return False


def _try_click(browser: Any, selectors: list[str]) -> bool:
    for selector in selectors:
        if browser.click(selector):
            return True
    return False


def _needs_two_factor(html: str) -> bool:
    return _contains_any(
        html,
        [
            "two-factor",
            "2fa",
            "verification code",
            "enter your code",
            "check your phone",
            "confirmation code",
        ],
    )


def _captcha_detected(html: str) -> bool:
    return _contains_any(html, ["captcha", "arkose", "prove you are human", "verify you are human"])


def _looks_bad_credentials(html: str) -> bool:
    return _contains_any(html, ["wrong password", "incorrect", "could not verify", "try again"])


def run(context: dict[str, Any]) -> dict[str, Any]:
    payload = context.get("payload", {})
    if not isinstance(payload, dict):
        return _result("x_auto_login", STATUS_FAILED_CONFIG_ERROR, "contract", "payload must be object")

    task = str(payload.get("task") or "x_auto_login")
    credentials_ref = str(payload.get("credentials_ref") or "")
    two_factor_code = str(payload.get("two_factor_code") or "").strip()
    headless = bool(payload.get("headless", True))
    try:
        timeout_seconds = int(payload.get("timeout_seconds", 25))
    except (TypeError, ValueError):
        return _result(task, STATUS_FAILED_CONFIG_ERROR, "contract", "timeout_seconds must be integer")
    timeout_seconds = max(1, min(timeout_seconds, 120))
    login_url = str(payload.get("login_url") or LOGIN_URL)
    if not _is_allowed_login_url(login_url):
        return _result(task, STATUS_FAILED_CONFIG_ERROR, "contract", "login_url host is not allowed")

    success_selectors = payload.get("success_selectors")
    if not isinstance(success_selectors, list) or not success_selectors:
        success_selectors = SUCCESS_SELECTORS

    loader: Callable[[str], Credentials] = context.get("credential_loader", load_credentials_from_ref)
    browser_factory: Callable[[], Any] = context.get("browser_factory", BrowserClient)

    try:
        creds = loader(credentials_ref)
    except Exception as exc:
        return _result(task, STATUS_FAILED_CONFIG_ERROR, "credentials", str(exc))

    browser = browser_factory()
    if not getattr(browser, "available", False):
        return _result(
            task,
            STATUS_FAILED_ADAPTER_UNAVAILABLE,
            "open_login",
            str(getattr(browser, "error", "browser adapter unavailable")),
        )

    checkpoint = "open_login"
    try:
        if not browser.open(login_url, headless=headless):
            return _result(task, STATUS_FAILED_CHECKPOINT_TIMEOUT, checkpoint, "failed to open login page")

        checkpoint = "input_identifier"
        if not _try_input(browser, IDENTIFIER_SELECTORS, creds.username_or_email):
            return _result(task, STATUS_FAILED_CHECKPOINT_TIMEOUT, checkpoint, "identifier field not found")

        checkpoint = "next"
        _try_click(browser, NEXT_SELECTORS)

        checkpoint = "input_password"
        if not _try_input(browser, PASSWORD_SELECTORS, creds.password):
            return _result(task, STATUS_FAILED_CHECKPOINT_TIMEOUT, checkpoint, "password field not found")

        checkpoint = "submit"
        _try_click(browser, NEXT_SELECTORS)

        deadline = time.time() + timeout_seconds
        page_html = ""
        need_two_factor = False
        bad_credentials = False
        while time.time() < deadline:
            page_html = browser.html()
            if _captcha_detected(page_html):
                return _result(task, STATUS_FAILED_CAPTCHA_DETECTED, "checkpoint_detect", "captcha challenge detected")
            if _needs_two_factor(page_html):
                need_two_factor = True
                break
            if _looks_bad_credentials(page_html):
                bad_credentials = True
                break
            if browser.wait_url_contains("/home", 1) and any(browser.exists(selector) for selector in success_selectors):
                return _result(task, STATUS_COMPLETED, "verify_success", "login completed")
            time.sleep(0.2)

        if need_two_factor:
            checkpoint = "two_factor"
            if not two_factor_code:
                return _result(task, STATUS_FAILED_2FA_REQUIRED, checkpoint, "two_factor_code is required")
            if not _try_input(browser, TWO_FACTOR_SELECTORS, two_factor_code):
                return _result(task, STATUS_FAILED_2FA_INVALID, checkpoint, "2FA input field not found")
            _try_click(browser, TWO_FACTOR_SUBMIT_SELECTORS)
            time.sleep(1)
            page_html = browser.html()
            if _needs_two_factor(page_html):
                return _result(task, STATUS_FAILED_2FA_INVALID, checkpoint, "2FA code not accepted")

        if bad_credentials:
            return _result(task, STATUS_FAILED_BAD_CREDENTIALS, "verify_success", "bad credentials")

        checkpoint = "verify_success"
        success_url = browser.wait_url_contains("/home", timeout_seconds)
        success_element = any(browser.exists(selector) for selector in success_selectors)
        if success_url and success_element:
            return _result(task, STATUS_COMPLETED, checkpoint, "login completed")

        if _looks_bad_credentials(page_html):
            return _result(task, STATUS_FAILED_BAD_CREDENTIALS, checkpoint, "bad credentials")

        return _result(task, STATUS_FAILED_CHECKPOINT_TIMEOUT, checkpoint, "success signal not reached")
    finally:
        browser.close()
