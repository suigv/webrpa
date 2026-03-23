from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.base_store import BaseStore
from core.paths import account_db_path


def _db_path() -> Path:
    return account_db_path()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class AccountStore(BaseStore):
    def __init__(self, db_path: Path | None = None) -> None:
        db_path = db_path or _db_path()
        super().__init__(db_path=db_path)

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    account TEXT PRIMARY KEY,
                    password TEXT NOT NULL,
                    twofa TEXT,
                    email TEXT,
                    email_password TEXT,
                    token TEXT,
                    email_token TEXT,
                    app_id TEXT NOT NULL DEFAULT 'default',
                    status TEXT NOT NULL DEFAULT 'ready',
                    last_used TEXT,
                    error_msg TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT
                )
                """
            )
            columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(accounts)").fetchall()
            }
            if "app_id" not in columns:
                conn.execute("ALTER TABLE accounts ADD COLUMN app_id TEXT")
                rows = conn.execute(
                    "SELECT account, metadata_json FROM accounts WHERE app_id IS NULL OR TRIM(app_id) = ''"
                ).fetchall()
                for row in rows:
                    normalized_app_id = "default"
                    metadata_json = row["metadata_json"]
                    if metadata_json:
                        try:
                            metadata = json.loads(metadata_json)
                        except Exception:
                            metadata = None
                        if isinstance(metadata, dict):
                            normalized_app_id = (
                                self._normalize_app_id(metadata.get("app_id")) or "default"
                            )
                    conn.execute(
                        "UPDATE accounts SET app_id = ? WHERE account = ?",
                        (normalized_app_id, row["account"]),
                    )
            conn.execute(
                "UPDATE accounts SET app_id = 'default' WHERE app_id IS NULL OR TRIM(app_id) = ''"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_app_id ON accounts(app_id)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_accounts_updated_at ON accounts(updated_at)"
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_accounts_status_app_id_updated
                ON accounts(status, app_id, updated_at, created_at, account)
                """
            )
            conn.commit()

    def upsert_account(self, data: dict[str, Any], conn: sqlite3.Connection | None = None) -> None:
        account = str(data.get("account", "")).strip()
        if not account:
            raise ValueError("account is required")

        now = _now_iso()
        fields = [
            "account",
            "password",
            "twofa",
            "email",
            "email_password",
            "token",
            "email_token",
            "app_id",
            "status",
            "last_used",
            "error_msg",
            "updated_at",
            "metadata_json",
        ]

        metadata = {k: v for k, v in data.items() if k not in fields and k != "created_at"}
        normalized_app_id = self._normalize_app_id(data.get("app_id")) or "default"

        placeholders = ", ".join(["?"] * (len(fields) + 1))  # +1 for created_at
        update_set = ", ".join([f"{f} = excluded.{f}" for f in fields if f != "account"])

        sql = f"""
            INSERT INTO accounts ({", ".join(fields)}, created_at)
            VALUES ({placeholders})
            ON CONFLICT(account) DO UPDATE SET
                {update_set}
        """

        params = (
            account,
            str(data.get("password", "")),
            data.get("twofa"),
            data.get("email"),
            data.get("email_password"),
            data.get("token"),
            data.get("email_token"),
            normalized_app_id,
            data.get("status", "ready"),
            data.get("last_used"),
            data.get("error_msg"),
            now,
            json.dumps(metadata, ensure_ascii=False) if metadata else None,
            now,  # created_at (only used if INSERT)
        )

        with self._tx(conn) as tx_conn:
            tx_conn.execute(sql, params)

    def get_account(
        self, account: str, conn: sqlite3.Connection | None = None
    ) -> dict[str, Any] | None:
        with self._tx(conn) as tx_conn:
            row = tx_conn.execute("SELECT * FROM accounts WHERE account = ?", (account,)).fetchone()
            if row:
                return self._row_to_dict(row)
        return None

    @staticmethod
    def _normalize_app_id(app_id: str | None) -> str | None:
        raw = str(app_id or "").strip().lower()
        return raw or None

    def list_accounts(self, app_id: str | None = None) -> list[dict[str, Any]]:
        requested = self._normalize_app_id(app_id)
        with self._connect() as conn:
            if requested is None:
                rows = conn.execute(
                    "SELECT * FROM accounts ORDER BY created_at ASC, account ASC"
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM accounts
                    WHERE app_id = ?
                    ORDER BY created_at ASC, account ASC
                    """,
                    (requested,),
                ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def count_accounts(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()
            return row[0] if row else 0

    def pop_ready_account(
        self,
        app_id: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        """原子化获取一个 ready 状态的账号并标记为 in_progress"""
        now = _now_iso()
        requested = self._normalize_app_id(app_id)
        with self._tx(conn) as tx_conn:
            if requested is None:
                selected = tx_conn.execute(
                    """
                    SELECT * FROM accounts
                    WHERE status = 'ready'
                    ORDER BY updated_at ASC, created_at ASC, account ASC
                    LIMIT 1
                    """
                ).fetchone()
            else:
                selected = tx_conn.execute(
                    """
                    SELECT * FROM accounts
                    WHERE status = 'ready'
                      AND app_id IN (?, 'default')
                    ORDER BY
                        CASE WHEN app_id = ? THEN 0 ELSE 1 END,
                        updated_at ASC,
                        created_at ASC,
                        account ASC
                    LIMIT 1
                    """,
                    (requested, requested),
                ).fetchone()
            if selected:
                account = selected["account"]
                tx_conn.execute(
                    "UPDATE accounts SET status = 'in_progress', last_used = ?, updated_at = ? WHERE account = ?",
                    (now, now, account),
                )
                data = self._row_to_dict(selected)
                data["status"] = "in_progress"
                data["last_used"] = now
                data["updated_at"] = now
                return data
        return None

    def update_status(
        self,
        account: str,
        status: str,
        error_msg: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> bool:
        now = _now_iso()
        with self._tx(conn) as tx_conn:
            cur = tx_conn.execute(
                "UPDATE accounts SET status = ?, error_msg = ?, updated_at = ? WHERE account = ?",
                (status, error_msg, now, account),
            )
            return cur.rowcount > 0

    def update_fields(
        self, account: str, data: dict[str, Any], conn: sqlite3.Connection | None = None
    ) -> bool:
        now = _now_iso()
        fields = []
        params = []
        for k, v in data.items():
            if k == "account":
                continue
            if k == "app_id":
                v = self._normalize_app_id(v) or "default"
            fields.append(f"{k} = ?")
            params.append(v)

        if not fields:
            return False

        fields.append("updated_at = ?")
        params.append(now)
        params.append(account)

        sql = f"UPDATE accounts SET {', '.join(fields)} WHERE account = ?"
        with self._tx(conn) as tx_conn:
            cur = tx_conn.execute(sql, tuple(params))
            return cur.rowcount > 0

    def reset_all_status(
        self,
        from_statuses: list[str],
        to_status: str = "ready",
        conn: sqlite3.Connection | None = None,
    ) -> int:
        now = _now_iso()
        placeholders = ", ".join(["?"] * len(from_statuses))
        sql = f"UPDATE accounts SET status = ?, error_msg = NULL, updated_at = ? WHERE status IN ({placeholders})"
        params = [to_status, now] + from_statuses
        with self._tx(conn) as tx_conn:
            cur = tx_conn.execute(sql, tuple(params))
            return cur.rowcount

    def clear_all(self, conn: sqlite3.Connection | None = None) -> None:
        with self._tx(conn) as tx_conn:
            tx_conn.execute("DELETE FROM accounts")

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["app_id"] = self._normalize_app_id(d.get("app_id")) or "default"
        if d.get("metadata_json"):
            try:
                meta = json.loads(d.pop("metadata_json"))
                if isinstance(meta, dict):
                    meta.pop("app_id", None)
                    d.update(meta)
            except Exception:
                pass
        else:
            d.pop("metadata_json", None)
        return d
