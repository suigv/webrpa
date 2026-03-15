from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.paths import task_db_path
from core.base_store import BaseStore


def _db_path() -> Path:
    return task_db_path()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskEvent:
    event_id: int
    task_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: str


class TaskEventStore(BaseStore):
    def __init__(self, db_path: Path | None = None) -> None:
        db_path = db_path or _db_path()
        super().__init__(db_path=db_path)
        self._observers: list[Callable[[TaskEvent], None]] = []

    def subscribe(self, observer: Callable[[TaskEvent], None]) -> None:
        """订阅新事件（追加，不覆盖已有订阅者）"""
        with self._lock:
            if observer not in self._observers:
                self._observers.append(observer)

    def _notify(self, event: TaskEvent) -> None:
        for observer in self._observers:
            try:
                observer(event)
            except Exception: pass

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_events_task_id_event_id ON task_events(task_id, event_id)"
            )
            conn.commit()

    def append_event(
        self,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
        conn: sqlite3.Connection | None = None,
    ) -> int:
        now = _now_iso()
        payload_json = json.dumps(payload, ensure_ascii=False)
        
        sql = """
            INSERT INTO task_events (task_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?)
        """
        params = (task_id, event_type, payload_json, now)

        with self._tx(conn) as tx_conn:
            cur = tx_conn.execute(sql, params)
            event_id = int(cur.lastrowid or 0)
            self._notify(TaskEvent(event_id, task_id, event_type, payload, now))
            return event_id

    def list_events(self, task_id: str, after_event_id: int = 0, limit: int = 200) -> list[TaskEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_id, task_id, event_type, payload_json, created_at
                FROM task_events
                WHERE task_id = ? AND event_id > ?
                ORDER BY event_id ASC
                LIMIT ?
                """,
                (task_id, int(after_event_id), int(limit)),
            ).fetchall()
            
        output: list[TaskEvent] = []
        for row in rows:
            output.append(
                TaskEvent(
                    event_id=int(row["event_id"]),
                    task_id=str(row["task_id"]),
                    event_type=str(row["event_type"]),
                    payload=json.loads(str(row["payload_json"])),
                    created_at=str(row["created_at"]),
                )
            )
        return output

    def list_events_after(self, after_event_id: int = 0, limit: int = 100) -> list[TaskEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_id, task_id, event_type, payload_json, created_at
                FROM task_events
                WHERE event_id > ?
                ORDER BY event_id ASC
                LIMIT ?
                """,
                (int(after_event_id), int(limit)),
            ).fetchall()
        return [
            TaskEvent(
                event_id=int(row["event_id"]),
                task_id=str(row["task_id"]),
                event_type=str(row["event_type"]),
                payload=json.loads(str(row["payload_json"])),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def max_event_id(self) -> int:
        """Returns the latest event_id currently in the store (or 0 if empty)."""
        with self._connect() as conn:
            row = conn.execute("SELECT MAX(event_id) AS max_id FROM task_events").fetchone()
        if not row:
            return 0
        try:
            return int(row["max_id"] or 0)
        except Exception:
            return 0

    def count_by_type(self, since: str | None = None) -> dict[str, int]:
        with self._connect() as conn:
            if since is None:
                rows = conn.execute(
                    "SELECT event_type, COUNT(*) as cnt FROM task_events GROUP BY event_type"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT event_type, COUNT(*) as cnt FROM task_events WHERE created_at >= ? GROUP BY event_type",
                    (since,),
                ).fetchall()
        return {str(row[0]): int(row[1]) for row in rows}

    def clear_all_events(self, conn: sqlite3.Connection | None = None) -> None:
        with self._tx(conn) as tx_conn:
            tx_conn.execute("DELETE FROM task_events")
