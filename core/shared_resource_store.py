from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.base_store import BaseStore
from core.paths import data_dir, now_iso


def _db_path() -> Path:
    return data_dir() / "shared_resources.db"


@dataclass
class SharedResourceItem:
    namespace: str
    item_id: str
    item: dict[str, Any]
    state: str
    owner_id: str | None = None
    created_at: str = ""
    updated_at: str = ""


class SharedResourceStore(BaseStore):
    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__(db_path=db_path or _db_path())

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS shared_resources (
                    namespace TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    item_json TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'collected',
                    owner_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (namespace, item_id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_shared_resources_lookup
                ON shared_resources(namespace, state, updated_at, created_at)
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_shared_resources_owner ON shared_resources(owner_id)"
            )
            conn.commit()

    def collect_items(
        self,
        *,
        namespace: str,
        items: list[dict[str, Any]],
        identity_field: str,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        added = 0
        updated = 0
        with self._tx(conn) as tx_conn:
            for item in items:
                item_id = _item_id_for(item, identity_field=identity_field)
                if not item_id:
                    continue
                now = now_iso()
                existing = tx_conn.execute(
                    """
                    SELECT state FROM shared_resources
                    WHERE namespace = ? AND item_id = ?
                    """,
                    (namespace, item_id),
                ).fetchone()
                if existing is None:
                    tx_conn.execute(
                        """
                        INSERT INTO shared_resources (
                            namespace, item_id, item_json, state, owner_id, created_at, updated_at
                        ) VALUES (?, ?, ?, 'collected', NULL, ?, ?)
                        """,
                        (namespace, item_id, json.dumps(item, ensure_ascii=False), now, now),
                    )
                    added += 1
                elif str(existing["state"] or "") == "collected":
                    tx_conn.execute(
                        """
                        UPDATE shared_resources
                        SET item_json = ?, updated_at = ?
                        WHERE namespace = ? AND item_id = ?
                        """,
                        (json.dumps(item, ensure_ascii=False), now, namespace, item_id),
                    )
                    updated += 1
        return {"added": added, "updated": updated}

    def claim_next(
        self,
        *,
        namespace: str,
        owner_id: str,
        conn: sqlite3.Connection | None = None,
    ) -> SharedResourceItem | None:
        with self._tx(conn) as tx_conn:
            owned = tx_conn.execute(
                """
                SELECT * FROM shared_resources
                WHERE namespace = ? AND owner_id = ? AND state = 'reserved'
                ORDER BY updated_at ASC, created_at ASC
                LIMIT 1
                """,
                (namespace, owner_id),
            ).fetchone()
            if owned is not None:
                return self._row_to_item(owned)

            selected = tx_conn.execute(
                """
                SELECT * FROM shared_resources
                WHERE namespace = ? AND state = 'collected'
                ORDER BY updated_at ASC, created_at ASC
                LIMIT 1
                """,
                (namespace,),
            ).fetchone()
            if selected is None:
                return None

            now = now_iso()
            tx_conn.execute(
                """
                UPDATE shared_resources
                SET state = 'reserved', owner_id = ?, updated_at = ?
                WHERE namespace = ? AND item_id = ? AND state = 'collected'
                """,
                (owner_id, now, namespace, selected["item_id"]),
            )
            row = tx_conn.execute(
                """
                SELECT * FROM shared_resources
                WHERE namespace = ? AND item_id = ?
                """,
                (namespace, selected["item_id"]),
            ).fetchone()
            return self._row_to_item(row) if row is not None else None

    def finalize_owner_claims(
        self,
        owner_id: str,
        *,
        success: bool,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        with self._tx(conn) as tx_conn:
            now = now_iso()
            if success:
                cur = tx_conn.execute(
                    """
                    UPDATE shared_resources
                    SET state = 'consumed', updated_at = ?
                    WHERE owner_id = ? AND state = 'reserved'
                    """,
                    (now, owner_id),
                )
            else:
                cur = tx_conn.execute(
                    """
                    UPDATE shared_resources
                    SET state = 'collected', owner_id = NULL, updated_at = ?
                    WHERE owner_id = ? AND state = 'reserved'
                    """,
                    (now, owner_id),
                )
            return int(cur.rowcount or 0)

    def namespace_stats(self, namespace: str) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT state, COUNT(*) AS count
                FROM shared_resources
                WHERE namespace = ?
                GROUP BY state
                """,
                (namespace,),
            ).fetchall()
        result = {"collected": 0, "reserved": 0, "consumed": 0}
        for row in rows:
            result[str(row["state"] or "collected")] = int(row["count"] or 0)
        return result

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> SharedResourceItem:
        try:
            payload = json.loads(str(row["item_json"] or "{}"))
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return SharedResourceItem(
            namespace=str(row["namespace"]),
            item_id=str(row["item_id"]),
            item=payload,
            state=str(row["state"]),
            owner_id=str(row["owner_id"]) if row["owner_id"] is not None else None,
            created_at=str(row["created_at"] or ""),
            updated_at=str(row["updated_at"] or ""),
        )


def _item_id_for(item: dict[str, Any], *, identity_field: str) -> str:
    raw = str(item.get(identity_field) or "").strip()
    if raw:
        return raw
    return json.dumps(item, ensure_ascii=False, sort_keys=True)


_store_lock = threading.Lock()
_store: SharedResourceStore | None = None


def get_shared_resource_store() -> SharedResourceStore:
    global _store
    if _store is not None:
        return _store
    with _store_lock:
        if _store is None:
            _store = SharedResourceStore()
    return _store
