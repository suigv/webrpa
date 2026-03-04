from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    env_root = os.environ.get("MYT_NEW_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return Path(__file__).resolve().parents[1]


def _db_path() -> Path:
    data_dir = _project_root() / "config" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "tasks.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskEvent:
    event_id: int
    task_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: str


class TaskEventStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _db_path()
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path), timeout=30)

    def _init_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                _ = conn.execute(
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
                _ = conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_task_events_task_id_event_id ON task_events(task_id, event_id)"
                )
                conn.commit()

    def append_event(self, task_id: str, event_type: str, payload: dict[str, Any]) -> int:
        now = _now_iso()
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO task_events (task_id, event_type, payload_json, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (task_id, event_type, json.dumps(payload, ensure_ascii=False), now),
                )
                conn.commit()
                event_id = int(cur.lastrowid or 0)
        return event_id

    def list_events(self, task_id: str, after_event_id: int = 0, limit: int = 200) -> list[TaskEvent]:
        with self._lock:
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
                    event_id=int(row[0]),
                    task_id=str(row[1]),
                    event_type=str(row[2]),
                    payload=json.loads(str(row[3])),
                    created_at=str(row[4]),
                )
            )
        return output
