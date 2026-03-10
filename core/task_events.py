from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.paths import project_root, task_db_path


def _project_root() -> Path:
    return project_root()


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


class TaskEventStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _db_path()
        self._lock = threading.RLock()
        self._observers: list[Callable[[TaskEvent], None]] = []
        self._init_schema()

    def subscribe(self, observer: Callable[[TaskEvent], None]) -> None:
        """订阅新事件 (覆盖式，防止热重载产生重复订阅)"""
        with self._lock:
            # 每次订阅直接覆盖之前的观察者列表，确保只有一个活跃的广播器
            self._observers = [observer]

    def _notify(self, event: TaskEvent) -> None:
        for observer in self._observers:
            try:
                observer(event)
            except Exception:
                pass

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

    def append_event(
        self,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
        conn: sqlite3.Connection | None = None,
    ) -> int:
        now = _now_iso()
        if conn is None:
            with self._lock:
                with self._connect() as tx_conn:
                    cur = tx_conn.execute(
                        """
                        INSERT INTO task_events (task_id, event_type, payload_json, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (task_id, event_type, json.dumps(payload, ensure_ascii=False), now),
                    )
                    tx_conn.commit()
                    event_id = int(cur.lastrowid or 0)
                    self._notify(TaskEvent(event_id, task_id, event_type, payload, now))
                    return event_id
        cur = conn.execute(
            """
            INSERT INTO task_events (task_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (task_id, event_type, json.dumps(payload, ensure_ascii=False), now),
        )
        event_id = int(cur.lastrowid or 0)
        self._notify(TaskEvent(event_id, task_id, event_type, payload, now))
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

    def count_by_type(self, since: str | None = None) -> dict[str, int]:
        with self._lock:
            with self._connect() as conn:
                if since is None:
                    rows = conn.execute(
                        """
                        SELECT event_type, COUNT(*)
                        FROM task_events
                        GROUP BY event_type
                        """
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT event_type, COUNT(*)
                        FROM task_events
                        WHERE created_at >= ?
                        GROUP BY event_type
                        """,
                        (since,),
                    ).fetchall()
        counts: dict[str, int] = {}
        for row in rows:
            counts[str(row[0])] = int(row[1])
        return counts

    def clear_all_events(self, conn: sqlite3.Connection | None = None) -> None:
        if conn is None:
            with self._lock:
                with self._connect() as tx_conn:
                    _ = tx_conn.execute("DELETE FROM task_events")
                    tx_conn.commit()
            return
        _ = conn.execute("DELETE FROM task_events")
