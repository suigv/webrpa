from __future__ import annotations

from core.data_store import read_text, write_text


def get_location_text() -> str:
    return read_text("location")


def set_location_text(content: str) -> None:
    write_text("location", content)


def get_website_text() -> str:
    return read_text("website")


def set_website_text(content: str) -> None:
    write_text("website", content)
