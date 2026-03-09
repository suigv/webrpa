from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from core.paths import project_root, task_db_path


def _project_root() -> Path:
    return project_root()


def _db_path() -> Path:
    return task_db_path()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_retry_iso(backoff_seconds: int) -> str:
    dt = datetime.now(timezone.utc) + timedelta(seconds=max(0, int(backoff_seconds)))
    return dt.isoformat()


@dataclass
class TaskRecord:
    task_id: str
    payload: dict[str, Any]
    devices: list[int]
    targets: list[dict[str, int]] | None = None
    ai_type: str = ""
    idempotency_key: str | None = None
    status: str = "pending"
    created_at: str = ""
    updated_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    retry_count: int = 0
    max_retries: int = 0
    retry_backoff_seconds: int = 2
    next_retry_at: str | None = None
    cancel_requested: bool = False
    priority: int = 50
    run_at: str | None = None


class ManagedTaskStateClearBlocked(RuntimeError):
    pass


class TaskStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _db_path()
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path), timeout=30)

    def _init_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                _ = conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        task_id TEXT PRIMARY KEY,
                        payload_json TEXT NOT NULL,
                        devices_json TEXT NOT NULL,
                        targets_json TEXT,
                        ai_type TEXT NOT NULL,
                        idempotency_key TEXT,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        started_at TEXT,
                        finished_at TEXT,
                        result_json TEXT,
                        error TEXT,
                        retry_count INTEGER NOT NULL DEFAULT 0,
                        max_retries INTEGER NOT NULL DEFAULT 0,
                        retry_backoff_seconds INTEGER NOT NULL DEFAULT 2,
                        next_retry_at TEXT,
                        cancel_requested INTEGER NOT NULL DEFAULT 0,
                        priority INTEGER NOT NULL DEFAULT 50,
                        run_at TEXT
                    )
                    """
                )
                columns = {
                    str(row[1])
                    for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
                }
                if "targets_json" not in columns:
                    _ = conn.execute("ALTER TABLE tasks ADD COLUMN targets_json TEXT")
                if "retry_count" not in columns:
                    _ = conn.execute("ALTER TABLE tasks ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0")
                if "max_retries" not in columns:
                    _ = conn.execute("ALTER TABLE tasks ADD COLUMN max_retries INTEGER NOT NULL DEFAULT 0")
                if "retry_backoff_seconds" not in columns:
                    _ = conn.execute(
                        "ALTER TABLE tasks ADD COLUMN retry_backoff_seconds INTEGER NOT NULL DEFAULT 2"
                    )
                if "next_retry_at" not in columns:
                    _ = conn.execute("ALTER TABLE tasks ADD COLUMN next_retry_at TEXT")
                if "cancel_requested" not in columns:
                    _ = conn.execute("ALTER TABLE tasks ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0")
                if "priority" not in columns:
                    _ = conn.execute("ALTER TABLE tasks ADD COLUMN priority INTEGER NOT NULL DEFAULT 50")
                if "run_at" not in columns:
                    _ = conn.execute("ALTER TABLE tasks ADD COLUMN run_at TEXT")
                if "idempotency_key" not in columns:
                    _ = conn.execute("ALTER TABLE tasks ADD COLUMN idempotency_key TEXT")
                _ = conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tasks_idempotency_status_created ON tasks(idempotency_key, status, created_at)"
                )
                conn.commit()

    @contextmanager
    def transaction(self, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = self._connect()
            try:
                if immediate:
                    conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def create_task(
        self,
        task_id: str,
        payload: dict[str, Any],
        devices: list[int],
        targets: list[dict[str, int]] | None,
        ai_type: str,
        idempotency_key: str | None,
        max_retries: int,
        retry_backoff_seconds: int,
        priority: int,
        run_at: str | None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        if conn is None:
            with self.transaction(immediate=True) as tx_conn:
                self.create_task(
                    task_id=task_id,
                    payload=payload,
                    devices=devices,
                    targets=targets,
                    ai_type=ai_type,
                    idempotency_key=idempotency_key,
                    max_retries=max_retries,
                    retry_backoff_seconds=retry_backoff_seconds,
                    priority=priority,
                    run_at=run_at,
                    conn=tx_conn,
                )
            return
        now = _now_iso()
        self._insert_task(
            conn=conn,
            task_id=task_id,
            payload=payload,
            devices=devices,
            targets=targets,
            ai_type=ai_type,
            idempotency_key=idempotency_key,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            priority=priority,
            run_at=run_at,
            now=now,
        )

    def create_or_get_active_task(
        self,
        payload: dict[str, Any],
        devices: list[int],
        targets: list[dict[str, int]] | None,
        ai_type: str,
        idempotency_key: str | None,
        max_retries: int,
        retry_backoff_seconds: int,
        priority: int,
        run_at: str | None,
        conn: sqlite3.Connection | None = None,
    ) -> tuple[TaskRecord, bool]:
        if conn is None:
            with self.transaction(immediate=True) as tx_conn:
                return self.create_or_get_active_task(
                    payload=payload,
                    devices=devices,
                    targets=targets,
                    ai_type=ai_type,
                    idempotency_key=idempotency_key,
                    max_retries=max_retries,
                    retry_backoff_seconds=retry_backoff_seconds,
                    priority=priority,
                    run_at=run_at,
                    conn=tx_conn,
                )
        task_id = str(uuid.uuid4())
        now = _now_iso()
        if idempotency_key:
            existing = conn.execute(
                """
                SELECT task_id, payload_json, devices_json, targets_json, ai_type, idempotency_key, status,
                       created_at, updated_at, started_at, finished_at,
                       result_json, error, retry_count, max_retries,
                       retry_backoff_seconds, next_retry_at, cancel_requested,
                       priority, run_at
                FROM tasks
                WHERE idempotency_key = ?
                  AND status IN ('pending', 'running')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                return self._row_to_record(existing), False
        self._insert_task(
            conn=conn,
            task_id=task_id,
            payload=payload,
            devices=devices,
            targets=targets,
            ai_type=ai_type,
            idempotency_key=idempotency_key,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            priority=priority,
            run_at=run_at,
            now=now,
        )

        created = self.get_task(task_id, conn=conn)
        if created is None:
            raise RuntimeError("failed to create task")
        return created, True

    def _insert_task(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        payload: dict[str, Any],
        devices: list[int],
        targets: list[dict[str, int]] | None,
        ai_type: str,
        idempotency_key: str | None,
        max_retries: int,
        retry_backoff_seconds: int,
        priority: int,
        run_at: str | None,
        now: str,
    ) -> None:
        _ = conn.execute(
            """
            INSERT INTO tasks (
                task_id, payload_json, devices_json, targets_json, ai_type,
                idempotency_key,
                status, created_at, updated_at,
                retry_count, max_retries, retry_backoff_seconds, next_retry_at
                , cancel_requested, priority, run_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                json.dumps(payload, ensure_ascii=False),
                json.dumps(devices, ensure_ascii=False),
                json.dumps(targets, ensure_ascii=False) if targets is not None else None,
                ai_type,
                idempotency_key,
                "pending",
                now,
                now,
                0,
                int(max_retries),
                int(retry_backoff_seconds),
                None,
                0,
                int(priority),
                run_at,
            ),
        )

    def _row_to_record(self, row: tuple[Any, ...]) -> TaskRecord:
        payload = json.loads(str(row[1]))
        targets: list[dict[str, int]] | None = None
        if row[3]:
            try:
                targets = json.loads(str(row[3]))
            except (ValueError, TypeError):
                targets = None
        return TaskRecord(
            task_id=str(row[0]),
            payload=payload,
            devices=json.loads(str(row[2])),
            targets=targets,
            ai_type=str(row[4]),
            idempotency_key=str(row[5]) if row[5] is not None else None,
            status=str(row[6]),
            created_at=str(row[7]),
            updated_at=str(row[8]),
            started_at=str(row[9]) if row[9] is not None else None,
            finished_at=str(row[10]) if row[10] is not None else None,
            result=json.loads(str(row[11])) if row[11] else None,
            error=str(row[12]) if row[12] is not None else None,
            retry_count=int(row[13]),
            max_retries=int(row[14]),
            retry_backoff_seconds=int(row[15]),
            next_retry_at=str(row[16]) if row[16] is not None else None,
            cancel_requested=bool(int(row[17])),
            priority=int(row[18]),
            run_at=str(row[19]) if row[19] is not None else None,
        )

    def get_task(self, task_id: str, conn: sqlite3.Connection | None = None) -> TaskRecord | None:
        if conn is None:
            with self._lock:
                with self._connect() as tx_conn:
                    row = tx_conn.execute(
                        """
                        SELECT task_id, payload_json, devices_json, targets_json, ai_type, idempotency_key, status,
                               created_at, updated_at, started_at, finished_at,
                               result_json, error, retry_count, max_retries,
                               retry_backoff_seconds, next_retry_at, cancel_requested,
                               priority, run_at
                        FROM tasks WHERE task_id = ?
                        """,
                        (task_id,),
                    ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT task_id, payload_json, devices_json, targets_json, ai_type, idempotency_key, status,
                       created_at, updated_at, started_at, finished_at,
                       result_json, error, retry_count, max_retries,
                       retry_backoff_seconds, next_retry_at, cancel_requested,
                       priority, run_at
                FROM tasks WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def list_pending_tasks(self) -> list[TaskRecord]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT task_id, payload_json, devices_json, targets_json, ai_type, idempotency_key, status,
                           created_at, updated_at, started_at, finished_at,
                           result_json, error, retry_count, max_retries,
                           retry_backoff_seconds, next_retry_at, cancel_requested,
                           priority, run_at
                    FROM tasks
                    WHERE status = 'pending' AND cancel_requested = 0
                    ORDER BY created_at ASC
                    """
                ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def list_tasks(self, limit: int = 100) -> list[TaskRecord]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT task_id, payload_json, devices_json, targets_json, ai_type, idempotency_key, status,
                           created_at, updated_at, started_at, finished_at,
                           result_json, error, retry_count, max_retries,
                           retry_backoff_seconds, next_retry_at, cancel_requested,
                           priority, run_at
                    FROM tasks
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def status_counts(self) -> dict[str, int]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT status, COUNT(*)
                    FROM tasks
                    GROUP BY status
                    """
                ).fetchall()
        counts: dict[str, int] = {}
        for row in rows:
            counts[str(row[0])] = int(row[1])
        return counts

    def recover_stale_running_tasks(
        self,
        stale_before: str,
        message: str = "recovered stale running after controller restart",
        conn: sqlite3.Connection | None = None,
    ) -> list[TaskRecord]:
        if conn is None:
            with self.transaction(immediate=True) as tx_conn:
                return self.recover_stale_running_tasks(stale_before=stale_before, message=message, conn=tx_conn)
        now = _now_iso()
        recovered: list[TaskRecord] = []
        rows = conn.execute(
            """
            SELECT task_id
            FROM tasks
            WHERE status = 'running' AND updated_at <= ?
            ORDER BY updated_at ASC
            """,
            (stale_before,),
        ).fetchall()
        for row in rows:
            task_id = str(row[0])
            cur = conn.execute(
                """
                UPDATE tasks
                SET status = 'pending',
                    updated_at = ?,
                    started_at = NULL,
                    finished_at = NULL,
                    error = ?,
                    cancel_requested = 0
                WHERE task_id = ? AND status = 'running'
                """,
                (now, message, task_id),
            )
            if cur.rowcount == 1:
                record = self.get_task(task_id, conn=conn)
                if record is not None:
                    recovered.append(record)
        return recovered

    def mark_running(self, task_id: str, conn: sqlite3.Connection | None = None) -> bool:
        if conn is None:
            with self.transaction(immediate=True) as tx_conn:
                return self.mark_running(task_id, conn=tx_conn)
        now = _now_iso()
        cur = conn.execute(
            """
            UPDATE tasks
            SET status = 'running', started_at = COALESCE(started_at, ?), updated_at = ?, next_retry_at = NULL
            WHERE task_id = ?
              AND status = 'pending'
              AND (next_retry_at IS NULL OR next_retry_at <= ?)
              AND (run_at IS NULL OR run_at <= ?)
              AND cancel_requested = 0
            """,
            (now, now, task_id, now, now),
        )
        return cur.rowcount == 1

    def mark_completed(self, task_id: str, result: dict[str, Any], conn: sqlite3.Connection | None = None) -> None:
        if conn is None:
            with self.transaction(immediate=True) as tx_conn:
                self.mark_completed(task_id, result=result, conn=tx_conn)
            return
        now = _now_iso()
        _ = conn.execute(
            """
            UPDATE tasks
            SET status = 'completed', finished_at = ?, updated_at = ?,
                result_json = ?, error = NULL, next_retry_at = NULL
                , cancel_requested = 0
            WHERE task_id = ?
            """,
            (now, now, json.dumps(result, ensure_ascii=False), task_id),
        )

    def mark_failed(
        self,
        task_id: str,
        error: str,
        result: dict[str, Any] | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        if conn is None:
            with self.transaction(immediate=True) as tx_conn:
                self.mark_failed(task_id, error=error, result=result, conn=tx_conn)
            return
        now = _now_iso()
        _ = conn.execute(
            """
            UPDATE tasks
            SET status = 'failed', finished_at = ?, updated_at = ?,
                result_json = ?, error = ?, next_retry_at = NULL
                , cancel_requested = 0
            WHERE task_id = ?
            """,
            (now, now, json.dumps(result, ensure_ascii=False) if result else None, error, task_id),
        )

    def schedule_retry(self, task_id: str, error: str, conn: sqlite3.Connection | None = None) -> TaskRecord | None:
        if conn is None:
            with self.transaction(immediate=True) as tx_conn:
                return self.schedule_retry(task_id, error=error, conn=tx_conn)
        now = _now_iso()
        row = conn.execute(
            """
            SELECT retry_count, max_retries, retry_backoff_seconds, cancel_requested
            FROM tasks
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        retry_count = int(row[0])
        max_retries = int(row[1])
        backoff = int(row[2])
        cancel_requested = bool(int(row[3]))
        if cancel_requested:
            return None
        if retry_count >= max_retries:
            return None
        next_retry_at = _next_retry_iso(backoff * (2**retry_count))
        _ = conn.execute(
            """
            UPDATE tasks
            SET status = 'pending',
                updated_at = ?,
                error = ?,
                retry_count = retry_count + 1,
                next_retry_at = ?,
                result_json = NULL,
                cancel_requested = 0
            WHERE task_id = ?
            """,
            (now, error, next_retry_at, task_id),
        )
        return self.get_task(task_id, conn=conn)

    def find_active_by_idempotency_key(self, idempotency_key: str) -> TaskRecord | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT task_id, payload_json, devices_json, targets_json, ai_type, idempotency_key, status,
                           created_at, updated_at, started_at, finished_at,
                           result_json, error, retry_count, max_retries,
                           retry_backoff_seconds, next_retry_at, cancel_requested,
                           priority, run_at
                    FROM tasks
                    WHERE idempotency_key = ?
                      AND status IN ('pending', 'running')
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (idempotency_key,),
                ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def cancel_pending(self, task_id: str) -> bool:
        now = _now_iso()
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    UPDATE tasks
                    SET status = 'cancelled', finished_at = ?, updated_at = ?,
                        error = 'cancelled by user', next_retry_at = NULL
                    WHERE task_id = ? AND status = 'pending'
                    """,
                    (now, now, task_id),
                )
                conn.commit()
                return cur.rowcount == 1

    def request_cancel(self, task_id: str, conn: sqlite3.Connection | None = None) -> str | None:
        if conn is None:
            with self.transaction(immediate=True) as tx_conn:
                return self.request_cancel(task_id, conn=tx_conn)
        now = _now_iso()
        cur_pending = conn.execute(
            """
            UPDATE tasks
            SET status = 'cancelled', finished_at = ?, updated_at = ?,
                error = 'cancelled by user', next_retry_at = NULL, cancel_requested = 0
            WHERE task_id = ? AND status = 'pending'
            """,
            (now, now, task_id),
        )
        if cur_pending.rowcount == 1:
            return "cancelled"

        cur_running = conn.execute(
            """
            UPDATE tasks
            SET cancel_requested = 1, updated_at = ?, error = 'cancellation requested'
            WHERE task_id = ? AND status = 'running'
            """,
            (now, task_id),
        )
        if cur_running.rowcount == 1:
            return "cancelling"

        row = conn.execute("SELECT task_id FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return "unchanged"

    def is_cancel_requested(self, task_id: str) -> bool:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT cancel_requested FROM tasks WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
        if row is None:
            return False
        return bool(int(row[0]))

    def mark_cancelled(
        self,
        task_id: str,
        message: str = "cancelled by user",
        conn: sqlite3.Connection | None = None,
    ) -> None:
        if conn is None:
            with self.transaction(immediate=True) as tx_conn:
                self.mark_cancelled(task_id, message=message, conn=tx_conn)
            return
        now = _now_iso()
        _ = conn.execute(
            """
            UPDATE tasks
            SET status = 'cancelled', finished_at = ?, updated_at = ?,
                error = ?, next_retry_at = NULL, cancel_requested = 0
            WHERE task_id = ?
            """,
            (now, now, message, task_id),
        )

    def has_running_tasks(self, conn: sqlite3.Connection | None = None) -> bool:
        if conn is None:
            with self._lock:
                with self._connect() as tx_conn:
                    return self.has_running_tasks(conn=tx_conn)
        row = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'running'"
        ).fetchone()
        return int(row[0]) > 0

    def clear_all_tasks(self, conn: sqlite3.Connection | None = None, *, require_no_running: bool = True) -> None:
        if conn is None:
            with self.transaction(immediate=True) as tx_conn:
                self.clear_all_tasks(conn=tx_conn, require_no_running=require_no_running)
            return
        if require_no_running and self.has_running_tasks(conn=conn):
            raise ManagedTaskStateClearBlocked("cannot clear managed task state while tasks are running")
        _ = conn.execute("DELETE FROM tasks")
