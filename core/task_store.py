from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.base_store import BaseStore
from core.paths import task_db_path


def _db_path() -> Path:
    return task_db_path()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _next_retry_iso(backoff_seconds: int) -> str:
    dt = datetime.now(UTC) + timedelta(seconds=max(0, int(backoff_seconds)))
    return dt.isoformat()


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


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


class ManagedTaskStateClearBlockedError(RuntimeError):
    pass


class TaskStore(BaseStore):
    def __init__(self, db_path: Path | None = None) -> None:
        db_path = db_path or _db_path()
        super().__init__(db_path=db_path)

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
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
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
            # 自动迁移缺失列
            if "targets_json" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN targets_json TEXT")
            if "retry_count" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0")
            if "max_retries" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN max_retries INTEGER NOT NULL DEFAULT 0")
            if "retry_backoff_seconds" not in columns:
                conn.execute(
                    "ALTER TABLE tasks ADD COLUMN retry_backoff_seconds INTEGER NOT NULL DEFAULT 2"
                )
            if "next_retry_at" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN next_retry_at TEXT")
            if "cancel_requested" not in columns:
                conn.execute(
                    "ALTER TABLE tasks ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0"
                )
            if "priority" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN priority INTEGER NOT NULL DEFAULT 50")
            if "run_at" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN run_at TEXT")
            if "idempotency_key" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN idempotency_key TEXT")

            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_idempotency_key ON tasks(idempotency_key)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_run_at ON tasks(run_at)")
            conn.commit()

    def create_task(
        self,
        task_id: str | None,
        payload: dict[str, Any],
        devices: list[int],
        targets: list[dict[str, int]] | None = None,
        ai_type: str = "volc",
        max_retries: int = 0,
        retry_backoff_seconds: int = 2,
        priority: int = 50,
        run_at: str | None = None,
        idempotency_key: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> TaskRecord:
        task_id = task_id or str(uuid.uuid4())
        now = _now_iso()
        record = TaskRecord(
            task_id=task_id,
            payload=payload,
            devices=devices,
            targets=targets,
            ai_type=ai_type,
            idempotency_key=idempotency_key,
            status="pending",
            created_at=now,
            updated_at=now,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            priority=priority,
            run_at=run_at,
        )
        sql = """
            INSERT INTO tasks (
                task_id, payload_json, devices_json, targets_json, ai_type,
                idempotency_key, status, created_at, updated_at,
                max_retries, retry_backoff_seconds, priority, run_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            record.task_id,
            json.dumps(record.payload, ensure_ascii=False),
            json.dumps(record.devices),
            json.dumps(record.targets) if record.targets else None,
            record.ai_type,
            record.idempotency_key,
            record.status,
            record.created_at,
            record.updated_at,
            record.max_retries,
            record.retry_backoff_seconds,
            record.priority,
            record.run_at,
        )
        with self._tx(conn) as tx_conn:
            tx_conn.execute(sql, params)
        return record

    def find_active_by_idempotency_key(
        self, key: str, conn: sqlite3.Connection | None = None
    ) -> TaskRecord | None:
        with self._tx(conn) as tx_conn:
            row = tx_conn.execute(
                """
                SELECT * FROM tasks
                WHERE idempotency_key = ?
                AND status NOT IN ('completed', 'failed', 'cancelled')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (key,),
            ).fetchone()
            if row:
                return self._row_to_record(row)
        return None

    def get_task(self, task_id: str, conn: sqlite3.Connection | None = None) -> TaskRecord | None:
        with self._tx(conn) as tx_conn:
            row = tx_conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            if row:
                return self._row_to_record(row)
        return None

    def get_running_tasks_by_device(self, device_id: int) -> list[str]:
        """获取正在某个设备上运行的任务 ID 列表。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT task_id, devices_json FROM tasks WHERE status = 'running' OR cancel_requested = 1"
            ).fetchall()
            task_ids = []
            for row in rows:
                try:
                    devices = json.loads(row["devices_json"])
                    if isinstance(devices, list) and device_id in devices:
                        task_ids.append(row["task_id"])
                except Exception:
                    continue
            return task_ids

    def get_running_task_by_cloud(self, device_id: int, cloud_id: int) -> str | None:
        """检查指定云机是否已被某个运行中任务占用，返回占用的 task_id，否则返回 None。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT task_id, targets_json FROM tasks WHERE status = 'running'"
            ).fetchall()
            for row in rows:
                try:
                    targets = json.loads(row["targets_json"] or "[]")
                    for t in targets:
                        if (
                            isinstance(t, dict)
                            and int(t.get("device_id", 0)) == device_id
                            and int(t.get("cloud_id", 0)) == cloud_id
                        ):
                            return str(row["task_id"])
                except Exception:
                    continue
            return None

    def _row_to_record(self, row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            task_id=row["task_id"],
            payload=json.loads(row["payload_json"]),
            devices=json.loads(row["devices_json"]),
            targets=json.loads(row["targets_json"]) if row["targets_json"] else None,
            ai_type=row["ai_type"],
            idempotency_key=row["idempotency_key"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            error=row["error"],
            retry_count=row["retry_count"],
            max_retries=row["max_retries"],
            retry_backoff_seconds=row["retry_backoff_seconds"],
            next_retry_at=row["next_retry_at"],
            cancel_requested=bool(row["cancel_requested"]),
            priority=row["priority"],
            run_at=row["run_at"],
        )

    def list_tasks(self, limit: int = 100) -> list[TaskRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def status_counts(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status"
            ).fetchall()
        return {str(row["status"]): int(row["cnt"]) for row in rows}

    def plugin_success_counts(self) -> list[dict[str, object]]:
        """按插件统计累计成功/失败/取消次数，用于蒸馏门槛判断。"""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    json_extract(payload_json, '$.task') as task_name,
                    status,
                    COUNT(*) as cnt
                FROM tasks
                WHERE status IN ('completed', 'failed', 'cancelled')
                  AND json_extract(payload_json, '$.task') IS NOT NULL
                GROUP BY task_name, status
                """
            ).fetchall()

        stats: dict[str, dict[str, int]] = {}
        for row in rows:
            name = str(row["task_name"])
            status = str(row["status"])
            cnt = int(row["cnt"])
            if name not in stats:
                stats[name] = {"completed": 0, "failed": 0, "cancelled": 0}
            stats[name][status] = cnt

        return [
            {
                "task_name": name,
                "completed": s["completed"],
                "failed": s["failed"],
                "cancelled": s["cancelled"],
                "total": s["completed"] + s["failed"] + s["cancelled"],
                "success_rate": round(s["completed"] / max(1, s["completed"] + s["failed"]), 3),
            }
            for name, s in sorted(stats.items())
        ]

    def request_cancel(self, task_id: str, conn: sqlite3.Connection | None = None) -> str | None:
        with self._tx(conn) as tx_conn:
            row = tx_conn.execute(
                "SELECT status FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if not row:
                return None
            status = row["status"]
            if status == "pending":
                tx_conn.execute(
                    "UPDATE tasks SET status = 'cancelled', updated_at = ? WHERE task_id = ?",
                    (_now_iso(), task_id),
                )
                return "cancelled"
            if status == "running":
                tx_conn.execute(
                    "UPDATE tasks SET cancel_requested = 1, updated_at = ? WHERE task_id = ?",
                    (_now_iso(), task_id),
                )
                return "cancelling"
            return status

    def is_cancel_requested(self, task_id: str, conn: sqlite3.Connection | None = None) -> bool:
        with self._tx(conn) as tx_conn:
            row = tx_conn.execute(
                "SELECT cancel_requested FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            return bool(row["cancel_requested"]) if row else False

    def mark_running(self, task_id: str, conn: sqlite3.Connection | None = None) -> bool:
        now = _now_iso()
        with self._tx(conn) as tx_conn:
            cur = tx_conn.execute(
                """
                UPDATE tasks
                SET status = 'running',
                    started_at = ?,
                    updated_at = ?,
                    next_retry_at = NULL,
                    finished_at = NULL,
                    error = NULL,
                    result_json = NULL
                WHERE task_id = ? AND status = 'pending'
                """,
                (now, now, task_id),
            )
            return cur.rowcount > 0

    def mark_cancelled(
        self, task_id: str, message: str | None = None, conn: sqlite3.Connection | None = None
    ) -> None:
        now = _now_iso()
        with self._tx(conn) as tx_conn:
            tx_conn.execute(
                """
                UPDATE tasks
                SET status = 'cancelled',
                    updated_at = ?,
                    finished_at = ?,
                    error = ?,
                    next_retry_at = NULL,
                    cancel_requested = 0
                WHERE task_id = ?
                """,
                (now, now, message, task_id),
            )

    def mark_failed(
        self,
        task_id: str,
        error: str,
        result: dict[str, Any] | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        now = _now_iso()
        payload = json.dumps(result, ensure_ascii=False) if result is not None else None
        with self._tx(conn) as tx_conn:
            tx_conn.execute(
                """
                UPDATE tasks
                SET status = 'failed',
                    updated_at = ?,
                    finished_at = ?,
                    error = ?,
                    result_json = ?,
                    next_retry_at = NULL,
                    cancel_requested = 0
                WHERE task_id = ?
                """,
                (now, now, error, payload, task_id),
            )

    def mark_completed(
        self,
        task_id: str,
        result: dict[str, Any] | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        now = _now_iso()
        payload = json.dumps(result, ensure_ascii=False) if result is not None else None
        with self._tx(conn) as tx_conn:
            tx_conn.execute(
                """
                UPDATE tasks
                SET status = 'completed',
                    updated_at = ?,
                    finished_at = ?,
                    result_json = ?,
                    error = NULL,
                    next_retry_at = NULL,
                    cancel_requested = 0
                WHERE task_id = ?
                """,
                (now, now, payload, task_id),
            )

    def update_task_status(
        self,
        task_id: str,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        now = _now_iso()
        fields = ["status = ?", "updated_at = ?"]
        params = [status, now]
        if result is not None:
            fields.append("result_json = ?")
            params.append(json.dumps(result, ensure_ascii=False))
        if error is not None:
            fields.append("error = ?")
            params.append(error)

        if status == "running":
            fields.append("started_at = ?")
            params.append(now)
        elif status in ("completed", "failed", "cancelled"):
            fields.append("finished_at = ?")
            params.append(now)

        sql = f"UPDATE tasks SET {', '.join(fields)} WHERE task_id = ?"
        params.append(task_id)
        with self._tx(conn) as tx_conn:
            tx_conn.execute(sql, params)

    def mark_task_retry(
        self, task_id: str, backoff_seconds: int, conn: sqlite3.Connection | None = None
    ) -> None:
        now = _now_iso()
        next_at = _next_retry_iso(backoff_seconds)
        sql = "UPDATE tasks SET status = 'pending', retry_count = retry_count + 1, next_retry_at = ?, updated_at = ? WHERE task_id = ?"
        params = (next_at, now, task_id)
        with self._tx(conn) as tx_conn:
            tx_conn.execute(sql, params)

    def schedule_retry(
        self,
        task_id: str,
        error: str,
        conn: sqlite3.Connection | None = None,
    ) -> TaskRecord | None:
        with self._tx(conn) as tx_conn:
            row = tx_conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            if not row:
                return None
            record = self._row_to_record(row)
            if record.status in TERMINAL_STATUSES:
                return None
            if record.retry_count >= record.max_retries:
                return None

            now = _now_iso()
            next_at = _next_retry_iso(record.retry_backoff_seconds)
            tx_conn.execute(
                """
                UPDATE tasks
                SET status = 'pending',
                    retry_count = retry_count + 1,
                    next_retry_at = ?,
                    updated_at = ?,
                    error = ?,
                    result_json = NULL,
                    finished_at = NULL
                WHERE task_id = ?
                """,
                (next_at, now, error, task_id),
            )
            return self.get_task(task_id, conn=tx_conn)

    def has_running_tasks(self, conn: sqlite3.Connection | None = None) -> bool:
        with self._tx(conn) as tx_conn:
            row = tx_conn.execute("SELECT 1 FROM tasks WHERE status = 'running' LIMIT 1").fetchone()
            return row is not None

    def clear_all_tasks(
        self, conn: sqlite3.Connection | None = None, require_no_running: bool = False
    ) -> None:
        with self._tx(conn) as tx_conn:
            if require_no_running and self.has_running_tasks(conn=tx_conn):
                raise ManagedTaskStateClearBlockedError(
                    "cannot clear managed task state while tasks are running"
                )
            tx_conn.execute("DELETE FROM tasks")

    def clear_failed_tasks(self, conn: sqlite3.Connection | None = None) -> list[str]:
        """清理所有已停止但未成功的任务（failed, cancelled），返回被清理的任务 ID 列表。"""
        with self._tx(conn) as tx_conn:
            rows = tx_conn.execute(
                "SELECT task_id FROM tasks WHERE status IN ('failed', 'cancelled')"
            ).fetchall()
            task_ids = [row["task_id"] for row in rows]
            if task_ids:
                placeholders = ",".join(["?"] * len(task_ids))
                tx_conn.execute(f"DELETE FROM tasks WHERE task_id IN ({placeholders})", task_ids)
            return task_ids

    def list_active_task_ids(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT task_id FROM tasks WHERE status IN ('pending', 'running')"
            ).fetchall()
        return [str(row["task_id"]) for row in rows]

    def list_terminal_tasks_oldest_first(self, limit: int | None = None) -> list[TaskRecord]:
        sql = """
            SELECT *
            FROM tasks
            WHERE status IN ('completed', 'failed', 'cancelled')
            ORDER BY COALESCE(finished_at, updated_at, created_at) ASC
        """
        params: tuple[object, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (int(limit),)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def list_pending_tasks(self) -> list[TaskRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = 'pending' AND (run_at IS NULL OR run_at <= ?) AND (next_retry_at IS NULL OR next_retry_at <= ?) ORDER BY priority DESC, created_at ASC",
                (_now_iso(), _now_iso()),
            ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def recover_stale_running_tasks(
        self,
        stale_before: str,
        conn: sqlite3.Connection | None = None,
    ) -> list[TaskRecord]:
        with self._tx(conn) as tx_conn:
            rows = tx_conn.execute(
                "SELECT * FROM tasks WHERE status = 'running' AND updated_at <= ?",
                (stale_before,),
            ).fetchall()
            if not rows:
                return []

            now = _now_iso()
            task_ids = [str(row["task_id"]) for row in rows]
            tx_conn.executemany(
                """
                UPDATE tasks
                SET status = 'pending',
                    updated_at = ?,
                    started_at = NULL,
                    finished_at = NULL,
                    next_retry_at = NULL
                WHERE task_id = ?
                """,
                [(now, task_id) for task_id in task_ids],
            )
            return [self.get_task(task_id, conn=tx_conn) for task_id in task_ids if task_id]
