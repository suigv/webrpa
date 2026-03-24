from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.base_store import BaseStore
from core.paths import task_db_path


def _db_path() -> Path:
    return task_db_path()


@dataclass
class AITaskAnnotationRecord:
    annotation_id: str
    task_id: str
    step_id: str | None = None
    source: str = "human_takeover"
    action_kind: str = "manual_input"
    input_type: str = "temporary_text"
    input_label: str = ""
    sensitive: bool = False
    save_eligible: bool = False
    raw_value: str | None = None
    metadata: dict[str, Any] | None = None
    captured_at: str = ""


class AITaskAnnotationStore(BaseStore):
    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__(db_path=db_path or _db_path())

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_task_annotations (
                    annotation_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    step_id TEXT,
                    source TEXT NOT NULL,
                    action_kind TEXT NOT NULL,
                    input_type TEXT NOT NULL,
                    input_label TEXT NOT NULL,
                    sensitive INTEGER NOT NULL DEFAULT 0,
                    save_eligible INTEGER NOT NULL DEFAULT 0,
                    raw_value TEXT,
                    metadata_json TEXT,
                    captured_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ai_task_annotations_task
                ON ai_task_annotations(task_id, captured_at DESC)
                """
            )
            conn.commit()

    def create_annotation(
        self,
        *,
        task_id: str,
        step_id: str | None,
        source: str,
        action_kind: str,
        input_type: str,
        input_label: str,
        sensitive: bool,
        save_eligible: bool,
        raw_value: str | None,
        metadata: dict[str, Any] | None,
        captured_at: str,
        conn: sqlite3.Connection | None = None,
    ) -> AITaskAnnotationRecord:
        record = AITaskAnnotationRecord(
            annotation_id=f"ann_{uuid.uuid4().hex[:12]}",
            task_id=task_id,
            step_id=step_id,
            source=source,
            action_kind=action_kind,
            input_type=input_type,
            input_label=input_label,
            sensitive=sensitive,
            save_eligible=save_eligible,
            raw_value=raw_value,
            metadata=metadata,
            captured_at=captured_at,
        )
        with self._tx(conn) as tx_conn:
            tx_conn.execute(
                """
                INSERT INTO ai_task_annotations (
                    annotation_id, task_id, step_id, source, action_kind,
                    input_type, input_label, sensitive, save_eligible, raw_value,
                    metadata_json, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.annotation_id,
                    record.task_id,
                    record.step_id,
                    record.source,
                    record.action_kind,
                    record.input_type,
                    record.input_label,
                    int(record.sensitive),
                    int(record.save_eligible),
                    record.raw_value,
                    json.dumps(record.metadata, ensure_ascii=False) if record.metadata else None,
                    record.captured_at,
                ),
            )
        return record

    def list_annotations(
        self,
        task_id: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> list[AITaskAnnotationRecord]:
        with self._tx(conn) as tx_conn:
            rows = tx_conn.execute(
                """
                SELECT * FROM ai_task_annotations
                WHERE task_id = ?
                ORDER BY captured_at DESC
                """,
                (task_id,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> AITaskAnnotationRecord:
        try:
            metadata = json.loads(str(row["metadata_json"] or "null"))
        except Exception:
            metadata = None
        if not isinstance(metadata, dict):
            metadata = None
        return AITaskAnnotationRecord(
            annotation_id=str(row["annotation_id"]),
            task_id=str(row["task_id"]),
            step_id=str(row["step_id"]) if row["step_id"] is not None else None,
            source=str(row["source"]),
            action_kind=str(row["action_kind"]),
            input_type=str(row["input_type"]),
            input_label=str(row["input_label"]),
            sensitive=bool(row["sensitive"]),
            save_eligible=bool(row["save_eligible"]),
            raw_value=str(row["raw_value"]) if row["raw_value"] is not None else None,
            metadata=metadata,
            captured_at=str(row["captured_at"]),
        )
