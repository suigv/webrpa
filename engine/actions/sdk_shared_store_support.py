from __future__ import annotations

import fcntl
import json
import os
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import core.paths as paths
from engine.models.runtime import ActionResult, ExecutionContext


def shared_path() -> Path:
    path = paths.data_dir() / "migration_shared.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def shared_lock_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.lock")


@contextmanager
def exclusive_shared_lock(path: Path) -> Iterator[None]:
    lock_file = shared_lock_path(path)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "r+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_store() -> dict[str, Any]:
    path = shared_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_store(
    payload: dict[str, Any],
    *,
    write_json_atomic: Callable[[Path, dict[str, Any]], None],
) -> None:
    write_json_atomic(shared_path(), payload)


def update_store(
    updater: Callable[[dict[str, Any]], None],
    *,
    write_json_atomic: Callable[[Path, dict[str, Any]], None],
    thread_lock: threading.Lock,
) -> dict[str, Any]:
    path = shared_path()
    with thread_lock, exclusive_shared_lock(path):
        store = read_store()
        updater(store)
        write_json_atomic(path, store)
        return store


def resolve_shared_key(params: dict[str, Any], context: ExecutionContext | None) -> str:
    key = str(params.get("key") or "").strip()
    if not key:
        return ""

    scope = str(params.get("scope") or "global").strip().lower()
    if scope in {"", "global"}:
        return key

    scope_value = str(params.get("scope_value") or "").strip()
    payload = context.payload if context is not None and isinstance(context.payload, dict) else {}

    if not scope_value:
        if scope == "device":
            scope_value = str(payload.get("device_ip") or "").strip()
        elif scope == "task":
            scope_value = context.task_id if context is not None else ""
        elif scope == "cloud":
            scope_value = (
                context.cloud_target_label
                if context is not None
                else str(payload.get("name") or "").strip()
            )

    if not scope_value:
        return key
    return f"{scope}:{scope_value}:{key}"


def save_shared_action(
    params: dict[str, Any],
    context: ExecutionContext | None,
    *,
    resolve_shared_key: Callable[[dict[str, Any], ExecutionContext | None], str],
    update_store: Callable[[Callable[[dict[str, Any]], None]], dict[str, Any]],
) -> ActionResult:
    key = resolve_shared_key(params, context)
    value = params.get("value")
    if not key:
        return ActionResult(ok=False, code="invalid_params", message="key is required")

    def _updater(store: dict[str, Any]) -> None:
        store[key] = value

    update_store(_updater)
    return ActionResult(ok=True, code="ok", data={"key": key})


def load_shared_required_action(
    params: dict[str, Any],
    context: ExecutionContext | None,
    *,
    resolve_shared_key: Callable[[dict[str, Any], ExecutionContext | None], str],
    read_store: Callable[[], dict[str, Any]],
) -> ActionResult:
    key = resolve_shared_key(params, context)
    if not key:
        return ActionResult(ok=False, code="invalid_params", message="key is required")
    store = read_store()
    if key not in store:
        return ActionResult(ok=False, code="missing_source_data", message=f"missing key: {key}")
    return ActionResult(ok=True, code="ok", data={"key": key, "value": store[key]})


def load_shared_optional_action(
    params: dict[str, Any],
    context: ExecutionContext | None,
    *,
    resolve_shared_key: Callable[[dict[str, Any], ExecutionContext | None], str],
    read_store: Callable[[], dict[str, Any]],
) -> ActionResult:
    key = resolve_shared_key(params, context)
    if not key:
        return ActionResult(ok=False, code="invalid_params", message="key is required")
    store = read_store()
    exists = key in store
    default = params.get("default")
    return ActionResult(
        ok=True,
        code="ok",
        data={"key": key, "exists": exists, "value": store.get(key, default)},
    )


def append_shared_unique_action(
    params: dict[str, Any],
    context: ExecutionContext | None,
    *,
    resolve_shared_key: Callable[[dict[str, Any], ExecutionContext | None], str],
    read_store: Callable[[], dict[str, Any]],
    update_store: Callable[[Callable[[dict[str, Any]], None]], dict[str, Any]],
) -> ActionResult:
    key = resolve_shared_key(params, context)
    if not key:
        return ActionResult(ok=False, code="invalid_params", message="key is required")

    item = params.get("item")
    if item is None:
        return ActionResult(ok=False, code="invalid_params", message="item is required")

    identity_field = str(params.get("identity_field") or "").strip()
    store = read_store()
    items = store.get(key)
    if not isinstance(items, list):
        items = []

    added = True
    if identity_field and isinstance(item, dict):
        item_identity = item.get(identity_field)
        for existing in items:
            if isinstance(existing, dict) and existing.get(identity_field) == item_identity:
                added = False
                break
    elif item in items:
        added = False

    if added:

        def _updater(store: dict[str, Any]) -> None:
            current_items = store.get(key)
            if not isinstance(current_items, list):
                current_items = []
            if identity_field and isinstance(item, dict):
                item_identity = item.get(identity_field)
                for existing in current_items:
                    if isinstance(existing, dict) and existing.get(identity_field) == item_identity:
                        return
            elif item in current_items:
                return
            current_items.append(item)
            store[key] = current_items

        store = update_store(_updater)
        stored_items = store.get(key)
        if isinstance(stored_items, list):
            items = stored_items
        else:
            items = items if isinstance(items, list) else []

    return ActionResult(
        ok=True,
        code="ok",
        data={"key": key, "added": added, "size": len(items), "items": items},
    )


def increment_shared_counter_action(
    params: dict[str, Any],
    context: ExecutionContext | None,
    *,
    resolve_shared_key: Callable[[dict[str, Any], ExecutionContext | None], str],
    update_store: Callable[[Callable[[dict[str, Any]], None]], dict[str, Any]],
) -> ActionResult:
    key = resolve_shared_key(params, context)
    if not key:
        return ActionResult(ok=False, code="invalid_params", message="key is required")

    amount = int(params.get("amount", 1) or 1)
    start = int(params.get("start", 0) or 0)
    result_value = start

    def _updater(store: dict[str, Any]) -> None:
        nonlocal result_value
        current = store.get(key, start)
        try:
            current_value = int(current)
        except Exception:
            current_value = start
        current_value += amount
        store[key] = current_value
        result_value = current_value

    update_store(_updater)
    return ActionResult(
        ok=True, code="ok", data={"key": key, "value": result_value, "amount": amount}
    )
