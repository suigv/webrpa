from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.base_store import BaseStore
from core.business_profile import coerce_role_tags, normalize_branch_id
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
                    default_branch TEXT NOT NULL DEFAULT 'default',
                    role_tags_json TEXT NOT NULL DEFAULT '[]',
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
            if "default_branch" not in columns:
                conn.execute(
                    "ALTER TABLE accounts ADD COLUMN default_branch TEXT NOT NULL DEFAULT 'default'"
                )
            if "role_tags_json" not in columns:
                conn.execute(
                    "ALTER TABLE accounts ADD COLUMN role_tags_json TEXT NOT NULL DEFAULT '[]'"
                )
            conn.execute(
                """
                UPDATE accounts
                SET default_branch = 'default'
                WHERE default_branch IS NULL OR TRIM(default_branch) = ''
                """
            )
            conn.execute(
                """
                UPDATE accounts
                SET role_tags_json = '[]'
                WHERE role_tags_json IS NULL OR TRIM(role_tags_json) = ''
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_app_id ON accounts(app_id)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_accounts_default_branch ON accounts(default_branch)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_accounts_updated_at ON accounts(updated_at)"
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_accounts_status_app_branch_updated
                ON accounts(status, app_id, default_branch, updated_at, created_at, account)
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
            "default_branch",
            "role_tags_json",
            "status",
            "last_used",
            "error_msg",
            "updated_at",
            "metadata_json",
        ]

        metadata = {
            k: v
            for k, v in data.items()
            if k not in fields and k not in {"created_at", "role_tags"}
        }
        normalized_app_id = self._normalize_app_id(data.get("app_id")) or "default"
        normalized_branch_id = normalize_branch_id(data.get("default_branch"))
        role_tags = coerce_role_tags(data.get("role_tags"))

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
            normalized_branch_id,
            json.dumps(role_tags, ensure_ascii=False),
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

    def list_accounts(
        self,
        app_id: str | None = None,
        *,
        branch_id: str | None = None,
        role_tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        requested = self._normalize_app_id(app_id)
        requested_branch = normalize_branch_id(branch_id, default="") if branch_id else ""
        required_tags = coerce_role_tags(role_tags or [])
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
            accounts = [self._row_to_dict(row) for row in rows]
            return [
                account
                for account in accounts
                if self._account_matches_filters(
                    account,
                    branch_id=requested_branch or None,
                    role_tags=required_tags,
                )
            ]

    def count_accounts(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()
            return row[0] if row else 0

    def pop_ready_account(
        self,
        app_id: str | None = None,
        *,
        branch_id: str | None = None,
        role_tags: list[str] | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        """原子化获取一个 ready 状态的账号并标记为 in_progress"""
        now = _now_iso()
        requested = self._normalize_app_id(app_id)
        requested_branch = normalize_branch_id(branch_id, default="") if branch_id else ""
        required_tags = coerce_role_tags(role_tags or [])
        with self._tx(conn) as tx_conn:
            if requested is None:
                rows = tx_conn.execute(
                    """
                    SELECT * FROM accounts
                    WHERE status = 'ready'
                    ORDER BY updated_at ASC, created_at ASC, account ASC
                    """
                ).fetchall()
            else:
                rows = tx_conn.execute(
                    """
                    SELECT * FROM accounts
                    WHERE status = 'ready'
                      AND app_id IN (?, 'default')
                    ORDER BY
                        CASE WHEN app_id = ? THEN 0 ELSE 1 END,
                        updated_at ASC,
                        created_at ASC,
                        account ASC
                    """,
                    (requested, requested),
                ).fetchall()
            selected = None
            for row in rows:
                candidate = self._row_to_dict(row)
                if self._account_matches_filters(
                    candidate,
                    branch_id=requested_branch or None,
                    role_tags=required_tags,
                ):
                    selected = row
                    break
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
            if k == "default_branch":
                v = normalize_branch_id(v)
            if k == "role_tags":
                k = "role_tags_json"
                v = json.dumps(coerce_role_tags(v), ensure_ascii=False)
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
        d["default_branch"] = normalize_branch_id(d.get("default_branch"))
        try:
            d["role_tags"] = coerce_role_tags(json.loads(str(d.pop("role_tags_json") or "[]")))
        except Exception:
            d["role_tags"] = []
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

    @staticmethod
    def _account_matches_filters(
        account: dict[str, Any],
        *,
        branch_id: str | None = None,
        role_tags: list[str] | None = None,
    ) -> bool:
        if branch_id:
            account_branch = normalize_branch_id(account.get("default_branch"))
            if account_branch != normalize_branch_id(branch_id):
                return False
        required_tags = coerce_role_tags(role_tags or [])
        if required_tags:
            account_tags = set(coerce_role_tags(account.get("role_tags") or []))
            if not account_tags.intersection(required_tags):
                return False
        return True
