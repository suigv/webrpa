from typing import Dict

from new.hardware_adapters.browser_client import BrowserClient


def click(params: Dict[str, object]) -> Dict[str, object]:
    return {"ok": True, "action": "click", "params": params}


def input_text(params: Dict[str, object]) -> Dict[str, object]:
    return {"ok": True, "action": "input_text", "params": params}


def swipe(params: Dict[str, object]) -> Dict[str, object]:
    return {"ok": True, "action": "swipe", "params": params}


def browser_open(params: Dict[str, object]) -> Dict[str, object]:
    url = str(params.get("url") or "").strip()
    if not url:
        return {"ok": False, "action": "browser_open", "error": "url is required"}

    headless = bool(params.get("headless", True))
    client = BrowserClient()
    if not client.available:
        return {
            "ok": False,
            "action": "browser_open",
            "error": client.error or "DrissionPage unavailable",
        }

    opened = client.open(url=url, headless=headless)
    html = client.html() if opened else ""
    client.close()
    return {
        "ok": opened,
        "action": "browser_open",
        "url": url,
        "html_length": len(html),
        "error": "" if opened else client.error,
    }
