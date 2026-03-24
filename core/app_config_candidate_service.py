from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.app_config import AppConfigManager, get_app_config
from core.base_store import BaseStore
from core.paths import data_dir, now_iso


def _db_path() -> Path:
    return data_dir() / "app_config_candidates.db"


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_load(raw: Any, *, default: Any) -> Any:
    if raw in (None, ""):
        return default
    try:
        loaded = json.loads(str(raw))
    except Exception:
        return default
    return loaded


def _stable_candidate_id(app_id: str, kind: str, stable_key: str) -> str:
    digest = hashlib.sha1(f"{app_id}:{kind}:{stable_key}".encode()).hexdigest()[:20]
    return f"cand_{digest}"


def _dedupe_texts(values: Any) -> list[str]:
    if isinstance(values, str):
        raw_items = [values]
    elif isinstance(values, list):
        raw_items = values
    else:
        raw_items = []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(text)
    return result


@dataclass
class AppConfigCandidateRecord:
    candidate_id: str
    app_id: str
    kind: str
    title: str
    preview: str
    stable_key: str
    value: dict[str, Any]
    evidence: dict[str, Any]
    status: str = "pending"
    created_at: str = ""
    updated_at: str = ""


class AppConfigCandidateStore(BaseStore):
    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__(db_path=db_path or _db_path())

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_config_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    app_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    preview TEXT NOT NULL DEFAULT '',
                    stable_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_app_config_candidates_unique
                ON app_config_candidates(app_id, kind, stable_key)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_app_config_candidates_lookup
                ON app_config_candidates(app_id, status, updated_at DESC)
                """
            )
            conn.commit()

    def upsert_candidate(
        self,
        *,
        app_id: str,
        draft_id: str | None,
        task_id: str | None,
        kind: str,
        title: str,
        preview: str,
        stable_key: str,
        value: dict[str, Any],
        conn: sqlite3.Connection | None = None,
    ) -> AppConfigCandidateRecord:
        candidate_id = _stable_candidate_id(app_id, kind, stable_key)
        with self._tx(conn) as tx_conn:
            row = tx_conn.execute(
                "SELECT * FROM app_config_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            now = now_iso()
            if row is None:
                evidence = {
                    "draft_ids": _dedupe_texts([draft_id] if draft_id else []),
                    "task_ids": _dedupe_texts([task_id] if task_id else []),
                    "occurrences": 1,
                }
                tx_conn.execute(
                    """
                    INSERT INTO app_config_candidates (
                        candidate_id, app_id, kind, title, preview, stable_key,
                        value_json, evidence_json, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        candidate_id,
                        app_id,
                        kind,
                        title,
                        preview,
                        stable_key,
                        _json_dump(value),
                        _json_dump(evidence),
                        now,
                        now,
                    ),
                )
            else:
                evidence = _json_load(row["evidence_json"], default={})
                evidence["draft_ids"] = _dedupe_texts(
                    [*(evidence.get("draft_ids") or []), *([draft_id] if draft_id else [])]
                )
                evidence["task_ids"] = _dedupe_texts(
                    [*(evidence.get("task_ids") or []), *([task_id] if task_id else [])]
                )
                evidence["occurrences"] = int(evidence.get("occurrences", 0) or 0) + 1
                next_status = "pending" if str(row["status"] or "") == "rejected" else row["status"]
                tx_conn.execute(
                    """
                    UPDATE app_config_candidates
                    SET title = ?,
                        preview = ?,
                        value_json = ?,
                        evidence_json = ?,
                        status = ?,
                        updated_at = ?
                    WHERE candidate_id = ?
                    """,
                    (
                        title,
                        preview,
                        _json_dump(value),
                        _json_dump(evidence),
                        next_status,
                        now,
                        candidate_id,
                    ),
                )
            stored = tx_conn.execute(
                "SELECT * FROM app_config_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            if stored is None:
                raise RuntimeError("failed to persist app config candidate")
            return self._row_to_record(stored)

    def list_candidates(
        self,
        *,
        app_id: str,
        status: str | None = "pending",
        conn: sqlite3.Connection | None = None,
    ) -> list[AppConfigCandidateRecord]:
        with self._tx(conn) as tx_conn:
            if status:
                rows = tx_conn.execute(
                    """
                    SELECT * FROM app_config_candidates
                    WHERE app_id = ? AND status = ?
                    ORDER BY updated_at DESC, created_at DESC
                    """,
                    (app_id, status),
                ).fetchall()
            else:
                rows = tx_conn.execute(
                    """
                    SELECT * FROM app_config_candidates
                    WHERE app_id = ?
                    ORDER BY updated_at DESC, created_at DESC
                    """,
                    (app_id,),
                ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def get_candidates(
        self,
        candidate_ids: list[str],
        *,
        conn: sqlite3.Connection | None = None,
    ) -> list[AppConfigCandidateRecord]:
        normalized = [str(item or "").strip() for item in candidate_ids if str(item or "").strip()]
        if not normalized:
            return []
        placeholders = ", ".join("?" for _ in normalized)
        with self._tx(conn) as tx_conn:
            rows = tx_conn.execute(
                f"SELECT * FROM app_config_candidates WHERE candidate_id IN ({placeholders})",
                tuple(normalized),
            ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def update_status(
        self,
        candidate_ids: list[str],
        *,
        status: str,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        normalized = [str(item or "").strip() for item in candidate_ids if str(item or "").strip()]
        if not normalized:
            return 0
        placeholders = ", ".join("?" for _ in normalized)
        with self._tx(conn) as tx_conn:
            cur = tx_conn.execute(
                f"""
                UPDATE app_config_candidates
                SET status = ?, updated_at = ?
                WHERE candidate_id IN ({placeholders})
                """,
                (status, now_iso(), *normalized),
            )
            return int(cur.rowcount or 0)

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> AppConfigCandidateRecord:
        return AppConfigCandidateRecord(
            candidate_id=str(row["candidate_id"]),
            app_id=str(row["app_id"]),
            kind=str(row["kind"]),
            title=str(row["title"]),
            preview=str(row["preview"] or ""),
            stable_key=str(row["stable_key"]),
            value=_json_load(row["value_json"], default={}),
            evidence=_json_load(row["evidence_json"], default={}),
            status=str(row["status"]),
            created_at=str(row["created_at"] or ""),
            updated_at=str(row["updated_at"] or ""),
        )


class AppConfigCandidateService:
    def __init__(self, *, store: AppConfigCandidateStore | None = None) -> None:
        self._store = store or AppConfigCandidateStore()

    def record_candidate(
        self,
        *,
        app_id: str,
        draft_id: str | None,
        task_id: str | None,
        kind: str,
        title: str,
        preview: str,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        stable_key = _json_dump(value)
        record = self._store.upsert_candidate(
            app_id=app_id,
            draft_id=draft_id,
            task_id=task_id,
            kind=kind,
            title=title,
            preview=preview,
            stable_key=stable_key,
            value=value,
        )
        return self._record_to_dict(record)

    def list_candidates(
        self,
        *,
        app_id: str,
        draft_id: str | None = None,
        status: str | None = "pending",
    ) -> dict[str, Any]:
        normalized_app_id = str(app_id or "").strip().lower()
        if not normalized_app_id:
            raise ValueError("app_id is required")
        records = self._store.list_candidates(app_id=normalized_app_id, status=status)
        if draft_id:
            filtered: list[AppConfigCandidateRecord] = []
            for record in records:
                draft_ids = _dedupe_texts(record.evidence.get("draft_ids"))
                if draft_id in draft_ids:
                    filtered.append(record)
            records = filtered
        config = get_app_config(normalized_app_id)
        return {
            "app_id": normalized_app_id,
            "display_name": str(
                config.get("display_name") or config.get("name") or normalized_app_id.upper()
            ).strip(),
            "status": status,
            "draft_id": draft_id or None,
            "candidates": [self._record_to_dict(item) for item in records],
        }

    def review_candidates(
        self,
        *,
        app_id: str,
        candidate_ids: list[str],
        action: str,
    ) -> dict[str, Any]:
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in {"promote", "reject"}:
            raise ValueError("action must be promote or reject")
        records = self._store.get_candidates(candidate_ids)
        if not records:
            return {"app_id": app_id, "action": normalized_action, "updated": 0, "items": []}
        if normalized_action == "reject":
            updated = self._store.update_status(candidate_ids, status="rejected")
            return {
                "app_id": app_id,
                "action": normalized_action,
                "updated": updated,
                "items": [self._record_to_dict(item) for item in records],
            }

        identity = AppConfigManager.ensure_app_config(app_id=app_id)
        normalized_app_id = str(identity["app_id"]).strip()
        document = get_app_config(normalized_app_id) or {"version": "v1"}
        changed = False
        promoted: list[dict[str, Any]] = []
        for record in records:
            if record.app_id != normalized_app_id:
                continue
            if self._merge_candidate_into_document(document, record):
                changed = True
            promoted.append(self._record_to_dict(record))
        if changed:
            AppConfigManager.write_app_config(normalized_app_id, document)
        updated = self._store.update_status(
            [item.candidate_id for item in records if item.app_id == normalized_app_id],
            status="promoted",
        )
        return {
            "app_id": normalized_app_id,
            "action": normalized_action,
            "updated": updated,
            "items": promoted,
            "config_path": str(AppConfigManager.app_config_path(normalized_app_id)),
        }

    def _merge_candidate_into_document(
        self,
        document: dict[str, Any],
        record: AppConfigCandidateRecord,
    ) -> bool:
        value = dict(record.value or {})
        if record.kind == "selector":
            selectors = document.get("selectors")
            if not isinstance(selectors, dict):
                selectors = {}
            selector_key = str(value.get("selector_key") or "").strip()
            selector_value = value.get("selector")
            if not selector_key or not isinstance(selector_value, dict):
                return False
            target_key = selector_key
            counter = 2
            while target_key in selectors and selectors[target_key] != selector_value:
                target_key = f"{selector_key}_{counter}"
                counter += 1
            if selectors.get(target_key) == selector_value:
                return False
            selectors[target_key] = selector_value
            document["selectors"] = selectors
            return True
        if record.kind == "state":
            states = document.get("states")
            existing_states = states if isinstance(states, list) else []
            state_id = str(value.get("id") or "").strip()
            if not state_id:
                return False
            if any(str(item.get("id") or "").strip() == state_id for item in existing_states):
                return False
            existing_states.append(value)
            document["states"] = existing_states
            return True
        if record.kind == "stage_pattern":
            stage_patterns = document.get("stage_patterns")
            if not isinstance(stage_patterns, dict):
                stage_patterns = {}
            state_id = str(value.get("state_id") or "").strip()
            if not state_id:
                return False
            current = stage_patterns.get(state_id)
            entry = dict(current) if isinstance(current, dict) else {}
            changed = False
            for field in ("resource_ids", "focus_markers", "text_markers"):
                merged = _dedupe_texts([*(entry.get(field) or []), *(value.get(field) or [])])
                if merged != list(entry.get(field) or []):
                    entry[field] = merged
                    changed = True
            if not changed:
                return False
            stage_patterns[state_id] = entry
            document["stage_patterns"] = stage_patterns
            return True
        if record.kind == "agent_hint":
            hint = str(value.get("text") or "").strip()
            if not hint or str(document.get("agent_hint") or "").strip() == hint:
                return False
            document["agent_hint"] = hint
            return True
        if record.kind == "xml_filter":
            xml_filter = value.get("xml_filter")
            if not isinstance(xml_filter, dict):
                return False
            normalized: dict[str, int] = {}
            for key in ("max_text_len", "max_desc_len"):
                raw = xml_filter.get(key)
                if not isinstance(raw, (int, float, str)):
                    continue
                normalized[key] = int(raw)
            if not normalized:
                return False
            if document.get("xml_filter") == normalized:
                return False
            document["xml_filter"] = normalized
            return True
        return False

    @staticmethod
    def _record_to_dict(record: AppConfigCandidateRecord) -> dict[str, Any]:
        evidence = dict(record.evidence or {})
        return {
            "candidate_id": record.candidate_id,
            "app_id": record.app_id,
            "kind": record.kind,
            "title": record.title,
            "preview": record.preview,
            "value": dict(record.value or {}),
            "status": record.status,
            "evidence": evidence,
            "evidence_count": len(_dedupe_texts(evidence.get("task_ids"))),
            "draft_ids": _dedupe_texts(evidence.get("draft_ids")),
            "task_ids": _dedupe_texts(evidence.get("task_ids")),
            "occurrences": int(evidence.get("occurrences", 0) or 0),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }


_service_lock = threading.Lock()
_service: AppConfigCandidateService | None = None


def get_app_config_candidate_service() -> AppConfigCandidateService:
    global _service
    if _service is not None:
        return _service
    with _service_lock:
        if _service is None:
            _service = AppConfigCandidateService()
    return _service
