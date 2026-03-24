from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.base_store import BaseStore
from core.paths import now_iso, task_db_path


def _db_path() -> Path:
    return task_db_path()


def _json_dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_load(raw: object, *, default: Any) -> Any:
    if raw in (None, ""):
        return default
    try:
        loaded = json.loads(str(raw))
    except Exception:
        return default
    return loaded


@dataclass
class WorkflowDraftRecord:
    draft_id: str
    display_name: str
    task_name: str
    plugin_name_candidate: str
    source: str = "generic"
    category: str = "AI Drafts"
    status: str = "collecting"
    success_threshold: int = 3
    success_count: int = 0
    failure_count: int = 0
    cancelled_count: int = 0
    latest_prompt_text: str | None = None
    prompt_history: list[str] = field(default_factory=list)
    last_failure_advice: dict[str, Any] | None = None
    last_success_snapshot: dict[str, Any] | None = None
    last_replayable_snapshot: dict[str, Any] | None = None
    successful_task_ids: list[str] = field(default_factory=list)
    latest_terminal_task_id: str | None = None
    latest_completed_task_id: str | None = None
    last_distilled_manifest_path: str | None = None
    last_distilled_script_path: str | None = None
    saved_preferences: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class WorkflowRunAssetRecord:
    asset_id: str
    draft_id: str
    task_id: str
    app_id: str
    branch_id: str
    objective: str
    completion_status: str
    business_outcome: str
    distill_decision: str
    distill_reason: str
    value_level: str
    retained_value: list[str] = field(default_factory=list)
    learned_assets: dict[str, Any] = field(default_factory=dict)
    terminal_message: str | None = None
    created_at: str = ""
    updated_at: str = ""


class WorkflowDraftStore(BaseStore):
    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__(db_path=db_path or _db_path())

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_drafts (
                    draft_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    task_name TEXT NOT NULL,
                    plugin_name_candidate TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'generic',
                    category TEXT NOT NULL DEFAULT 'AI Drafts',
                    status TEXT NOT NULL DEFAULT 'collecting',
                    success_threshold INTEGER NOT NULL DEFAULT 3,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    cancelled_count INTEGER NOT NULL DEFAULT 0,
                    latest_prompt_text TEXT,
                    prompt_history_json TEXT NOT NULL DEFAULT '[]',
                    last_failure_advice_json TEXT,
                    last_success_snapshot_json TEXT,
                    last_replayable_snapshot_json TEXT,
                    successful_task_ids_json TEXT NOT NULL DEFAULT '[]',
                    latest_terminal_task_id TEXT,
                    latest_completed_task_id TEXT,
                    last_distilled_manifest_path TEXT,
                    last_distilled_script_path TEXT,
                    saved_preferences_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {
                str(row[1]) for row in conn.execute("PRAGMA table_info(workflow_drafts)").fetchall()
            }
            migrations = {
                "source": "ALTER TABLE workflow_drafts ADD COLUMN source TEXT NOT NULL DEFAULT 'generic'",
                "category": "ALTER TABLE workflow_drafts ADD COLUMN category TEXT NOT NULL DEFAULT 'AI Drafts'",
                "status": "ALTER TABLE workflow_drafts ADD COLUMN status TEXT NOT NULL DEFAULT 'collecting'",
                "success_threshold": "ALTER TABLE workflow_drafts ADD COLUMN success_threshold INTEGER NOT NULL DEFAULT 3",
                "success_count": "ALTER TABLE workflow_drafts ADD COLUMN success_count INTEGER NOT NULL DEFAULT 0",
                "failure_count": "ALTER TABLE workflow_drafts ADD COLUMN failure_count INTEGER NOT NULL DEFAULT 0",
                "cancelled_count": "ALTER TABLE workflow_drafts ADD COLUMN cancelled_count INTEGER NOT NULL DEFAULT 0",
                "latest_prompt_text": "ALTER TABLE workflow_drafts ADD COLUMN latest_prompt_text TEXT",
                "prompt_history_json": "ALTER TABLE workflow_drafts ADD COLUMN prompt_history_json TEXT NOT NULL DEFAULT '[]'",
                "last_failure_advice_json": "ALTER TABLE workflow_drafts ADD COLUMN last_failure_advice_json TEXT",
                "last_success_snapshot_json": "ALTER TABLE workflow_drafts ADD COLUMN last_success_snapshot_json TEXT",
                "last_replayable_snapshot_json": "ALTER TABLE workflow_drafts ADD COLUMN last_replayable_snapshot_json TEXT",
                "successful_task_ids_json": "ALTER TABLE workflow_drafts ADD COLUMN successful_task_ids_json TEXT NOT NULL DEFAULT '[]'",
                "latest_terminal_task_id": "ALTER TABLE workflow_drafts ADD COLUMN latest_terminal_task_id TEXT",
                "latest_completed_task_id": "ALTER TABLE workflow_drafts ADD COLUMN latest_completed_task_id TEXT",
                "last_distilled_manifest_path": "ALTER TABLE workflow_drafts ADD COLUMN last_distilled_manifest_path TEXT",
                "last_distilled_script_path": "ALTER TABLE workflow_drafts ADD COLUMN last_distilled_script_path TEXT",
                "saved_preferences_json": "ALTER TABLE workflow_drafts ADD COLUMN saved_preferences_json TEXT NOT NULL DEFAULT '{}'",
            }
            for column, sql in migrations.items():
                if column not in columns:
                    conn.execute(sql)

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflow_drafts_updated_at ON workflow_drafts(updated_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflow_drafts_status ON workflow_drafts(status)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_run_assets (
                    asset_id TEXT PRIMARY KEY,
                    draft_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    app_id TEXT NOT NULL DEFAULT '',
                    branch_id TEXT NOT NULL DEFAULT '',
                    objective TEXT NOT NULL DEFAULT '',
                    completion_status TEXT NOT NULL DEFAULT '',
                    business_outcome TEXT NOT NULL DEFAULT '',
                    distill_decision TEXT NOT NULL DEFAULT '',
                    distill_reason TEXT NOT NULL DEFAULT '',
                    value_level TEXT NOT NULL DEFAULT '',
                    retained_value_json TEXT NOT NULL DEFAULT '[]',
                    learned_assets_json TEXT NOT NULL DEFAULT '{}',
                    terminal_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_workflow_run_assets_lookup
                ON workflow_run_assets(app_id, objective, branch_id, updated_at DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_workflow_run_assets_draft
                ON workflow_run_assets(draft_id, updated_at DESC)
                """
            )
            conn.commit()

    def get_draft(
        self, draft_id: str, conn: sqlite3.Connection | None = None
    ) -> WorkflowDraftRecord | None:
        with self._tx(conn) as tx_conn:
            row = tx_conn.execute(
                "SELECT * FROM workflow_drafts WHERE draft_id = ?",
                (draft_id,),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_record(row)

    def list_drafts(
        self, limit: int = 100, conn: sqlite3.Connection | None = None
    ) -> list[WorkflowDraftRecord]:
        with self._tx(conn) as tx_conn:
            rows = tx_conn.execute(
                """
                SELECT * FROM workflow_drafts
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def create_draft(
        self,
        record: WorkflowDraftRecord,
        conn: sqlite3.Connection | None = None,
    ) -> WorkflowDraftRecord:
        with self._tx(conn) as tx_conn:
            tx_conn.execute(
                """
                INSERT INTO workflow_drafts (
                    draft_id, display_name, task_name, plugin_name_candidate, source, category,
                    status, success_threshold, success_count, failure_count, cancelled_count,
                    latest_prompt_text, prompt_history_json, last_failure_advice_json,
                    last_success_snapshot_json, last_replayable_snapshot_json, successful_task_ids_json,
                    latest_terminal_task_id, latest_completed_task_id,
                    last_distilled_manifest_path, last_distilled_script_path,
                    saved_preferences_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._record_params(record),
            )
        return record

    def update_draft(
        self,
        record: WorkflowDraftRecord,
        conn: sqlite3.Connection | None = None,
    ) -> WorkflowDraftRecord:
        record.updated_at = record.updated_at or now_iso()
        with self._tx(conn) as tx_conn:
            tx_conn.execute(
                """
                UPDATE workflow_drafts
                SET display_name = ?,
                    task_name = ?,
                    plugin_name_candidate = ?,
                    source = ?,
                    category = ?,
                    status = ?,
                    success_threshold = ?,
                    success_count = ?,
                    failure_count = ?,
                    cancelled_count = ?,
                    latest_prompt_text = ?,
                    prompt_history_json = ?,
                    last_failure_advice_json = ?,
                    last_success_snapshot_json = ?,
                    last_replayable_snapshot_json = ?,
                    successful_task_ids_json = ?,
                    latest_terminal_task_id = ?,
                    latest_completed_task_id = ?,
                    last_distilled_manifest_path = ?,
                    last_distilled_script_path = ?,
                    saved_preferences_json = ?,
                    updated_at = ?
                WHERE draft_id = ?
                """,
                (
                    record.display_name,
                    record.task_name,
                    record.plugin_name_candidate,
                    record.source,
                    record.category,
                    record.status,
                    record.success_threshold,
                    record.success_count,
                    record.failure_count,
                    record.cancelled_count,
                    record.latest_prompt_text,
                    _json_dump(record.prompt_history),
                    _json_dump(record.last_failure_advice)
                    if record.last_failure_advice is not None
                    else None,
                    _json_dump(record.last_success_snapshot)
                    if record.last_success_snapshot is not None
                    else None,
                    _json_dump(record.last_replayable_snapshot)
                    if record.last_replayable_snapshot is not None
                    else None,
                    _json_dump(record.successful_task_ids),
                    record.latest_terminal_task_id,
                    record.latest_completed_task_id,
                    record.last_distilled_manifest_path,
                    record.last_distilled_script_path,
                    _json_dump(record.saved_preferences),
                    record.updated_at,
                    record.draft_id,
                ),
            )
        return record

    def clear_all_drafts(self, conn: sqlite3.Connection | None = None) -> None:
        with self._tx(conn) as tx_conn:
            tx_conn.execute("DELETE FROM workflow_run_assets")
            tx_conn.execute("DELETE FROM workflow_drafts")

    def upsert_run_asset(
        self,
        record: WorkflowRunAssetRecord,
        conn: sqlite3.Connection | None = None,
    ) -> WorkflowRunAssetRecord:
        created_at = record.created_at or now_iso()
        updated_at = record.updated_at or created_at
        record.created_at = created_at
        record.updated_at = updated_at
        with self._tx(conn) as tx_conn:
            tx_conn.execute(
                """
                INSERT INTO workflow_run_assets (
                    asset_id, draft_id, task_id, app_id, branch_id, objective,
                    completion_status, business_outcome, distill_decision, distill_reason,
                    value_level, retained_value_json, learned_assets_json, terminal_message,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    draft_id = excluded.draft_id,
                    task_id = excluded.task_id,
                    app_id = excluded.app_id,
                    branch_id = excluded.branch_id,
                    objective = excluded.objective,
                    completion_status = excluded.completion_status,
                    business_outcome = excluded.business_outcome,
                    distill_decision = excluded.distill_decision,
                    distill_reason = excluded.distill_reason,
                    value_level = excluded.value_level,
                    retained_value_json = excluded.retained_value_json,
                    learned_assets_json = excluded.learned_assets_json,
                    terminal_message = excluded.terminal_message,
                    updated_at = excluded.updated_at
                """,
                (
                    record.asset_id,
                    record.draft_id,
                    record.task_id,
                    record.app_id,
                    record.branch_id,
                    record.objective,
                    record.completion_status,
                    record.business_outcome,
                    record.distill_decision,
                    record.distill_reason,
                    record.value_level,
                    _json_dump(record.retained_value),
                    _json_dump(record.learned_assets),
                    record.terminal_message,
                    created_at,
                    updated_at,
                ),
            )
        return record

    def list_run_assets(
        self,
        *,
        limit: int = 20,
        draft_id: str | None = None,
        app_id: str | None = None,
        objective: str | None = None,
        branch_id: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> list[WorkflowRunAssetRecord]:
        clauses: list[str] = []
        params: list[object] = []
        if draft_id:
            clauses.append("draft_id = ?")
            params.append(draft_id)
        if app_id is not None:
            clauses.append("app_id = ?")
            params.append(app_id)
        if objective:
            clauses.append("objective = ?")
            params.append(objective)
        if branch_id is not None:
            clauses.append("branch_id = ?")
            params.append(branch_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._tx(conn) as tx_conn:
            rows = tx_conn.execute(
                f"""
                SELECT * FROM workflow_run_assets
                {where}
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                (*params, int(limit)),
            ).fetchall()
            return [self._row_to_run_asset(row) for row in rows]

    def _record_params(self, record: WorkflowDraftRecord) -> tuple[object, ...]:
        created_at = record.created_at or now_iso()
        updated_at = record.updated_at or created_at
        record.created_at = created_at
        record.updated_at = updated_at
        return (
            record.draft_id,
            record.display_name,
            record.task_name,
            record.plugin_name_candidate,
            record.source,
            record.category,
            record.status,
            record.success_threshold,
            record.success_count,
            record.failure_count,
            record.cancelled_count,
            record.latest_prompt_text,
            _json_dump(record.prompt_history),
            _json_dump(record.last_failure_advice)
            if record.last_failure_advice is not None
            else None,
            _json_dump(record.last_success_snapshot)
            if record.last_success_snapshot is not None
            else None,
            _json_dump(record.last_replayable_snapshot)
            if record.last_replayable_snapshot is not None
            else None,
            _json_dump(record.successful_task_ids),
            record.latest_terminal_task_id,
            record.latest_completed_task_id,
            record.last_distilled_manifest_path,
            record.last_distilled_script_path,
            _json_dump(record.saved_preferences),
            created_at,
            updated_at,
        )

    def _row_to_record(self, row: sqlite3.Row) -> WorkflowDraftRecord:
        return WorkflowDraftRecord(
            draft_id=str(row["draft_id"]),
            display_name=str(row["display_name"]),
            task_name=str(row["task_name"]),
            plugin_name_candidate=str(row["plugin_name_candidate"]),
            source=str(row["source"] or "generic"),
            category=str(row["category"] or "AI Drafts"),
            status=str(row["status"] or "collecting"),
            success_threshold=int(row["success_threshold"] or 3),
            success_count=int(row["success_count"] or 0),
            failure_count=int(row["failure_count"] or 0),
            cancelled_count=int(row["cancelled_count"] or 0),
            latest_prompt_text=str(row["latest_prompt_text"])
            if row["latest_prompt_text"] is not None
            else None,
            prompt_history=list(_json_load(row["prompt_history_json"], default=[])),
            last_failure_advice=_json_load(row["last_failure_advice_json"], default=None),
            last_success_snapshot=_json_load(row["last_success_snapshot_json"], default=None),
            last_replayable_snapshot=_json_load(
                row["last_replayable_snapshot_json"], default=None
            ),
            successful_task_ids=list(_json_load(row["successful_task_ids_json"], default=[])),
            latest_terminal_task_id=str(row["latest_terminal_task_id"])
            if row["latest_terminal_task_id"] is not None
            else None,
            latest_completed_task_id=str(row["latest_completed_task_id"])
            if row["latest_completed_task_id"] is not None
            else None,
            last_distilled_manifest_path=str(row["last_distilled_manifest_path"])
            if row["last_distilled_manifest_path"] is not None
            else None,
            last_distilled_script_path=str(row["last_distilled_script_path"])
            if row["last_distilled_script_path"] is not None
            else None,
            saved_preferences=dict(_json_load(row["saved_preferences_json"], default={})),
            created_at=str(row["created_at"] or ""),
            updated_at=str(row["updated_at"] or ""),
        )

    def _row_to_run_asset(self, row: sqlite3.Row) -> WorkflowRunAssetRecord:
        return WorkflowRunAssetRecord(
            asset_id=str(row["asset_id"]),
            draft_id=str(row["draft_id"]),
            task_id=str(row["task_id"]),
            app_id=str(row["app_id"] or ""),
            branch_id=str(row["branch_id"] or ""),
            objective=str(row["objective"] or ""),
            completion_status=str(row["completion_status"] or ""),
            business_outcome=str(row["business_outcome"] or ""),
            distill_decision=str(row["distill_decision"] or ""),
            distill_reason=str(row["distill_reason"] or ""),
            value_level=str(row["value_level"] or ""),
            retained_value=list(_json_load(row["retained_value_json"], default=[])),
            learned_assets=dict(_json_load(row["learned_assets_json"], default={})),
            terminal_message=str(row["terminal_message"])
            if row["terminal_message"] is not None
            else None,
            created_at=str(row["created_at"] or ""),
            updated_at=str(row["updated_at"] or ""),
        )
