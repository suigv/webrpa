from __future__ import annotations

import threading
from contextlib import AbstractContextManager, suppress

import anyio
from anyio.from_thread import start_blocking_portal


class WaitSignal:
    """Thread-safe wait/notify bridge built on anyio.Event."""

    def __init__(self, *, name: str | None = None) -> None:
        self._lock = threading.Lock()
        self._closed = False
        self._portal_cm: AbstractContextManager = start_blocking_portal(name=name)
        self._portal = self._portal_cm.__enter__()
        self._event = self._portal.call(anyio.Event)

    def wait(self, timeout_s: float) -> bool:
        if timeout_s <= 0:
            return False

        event = self._event

        async def _wait() -> bool:
            with anyio.move_on_after(timeout_s) as scope:
                await event.wait()
            return not scope.cancel_called

        try:
            return bool(self._portal.call(_wait))
        except RuntimeError:
            return False

    def notify(self) -> None:
        with self._lock:
            if self._closed:
                return
            event = self._event
        with suppress(RuntimeError):
            self._portal.call(event.set)

    def reset(self) -> None:
        with self._lock:
            if self._closed:
                return
            with suppress(RuntimeError):
                self._event = self._portal.call(anyio.Event)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            portal_cm = self._portal_cm
        with suppress(Exception):
            portal_cm.__exit__(None, None, None)
