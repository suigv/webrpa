from __future__ import annotations

import json
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from core.app_config import resolve_app_id
from core.business_profile import branch_id_from_payload, normalize_branch_id
from core.golden_run_distillation import GoldenRunDistiller
from core.model_trace_store import ModelTraceContext
from core.paths import plugins_dir, traces_dir
from core.workflow_draft_store import WorkflowDraftRecord, WorkflowDraftStore

_TASK_TEXT_KEYS = ("goal", "prompt", "query", "instruction", "text", "description")
_ASCII_WORD_RE = re.compile(r"[^a-z0-9]+")
_TRACE_FILE_RE = re.compile(r"^(?P<target>.+)\.attempt-(?P<attempt>\d+)\.jsonl$")


def _dedupe_keep_last(items: list[str], *, limit: int = 20) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in reversed(items):
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    result.reverse()
    if len(result) > limit:
        return result[-limit:]
    return result


def _truncate_text(value: str, *, max_len: int) -> str:
    stripped = " ".join(value.split())
    if len(stripped) <= max_len:
        return stripped
    return stripped[: max_len - 1].rstrip() + "…"


def _extract_prompt_text(payload: dict[str, Any]) -> str | None:
    for key in _TASK_TEXT_KEYS:
        raw = payload.get(key)
        text = str(raw or "").strip()
        if text:
            return text
    return None


def _derive_display_name(payload: dict[str, Any], explicit: str | None) -> str | None:
    if str(explicit or "").strip():
        return str(explicit).strip()
    for key in ("_workflow_display_name", "workflow_display_name", "display_name"):
        text = str(payload.get(key) or "").strip()
        if text:
            return text
    prompt_text = _extract_prompt_text(payload)
    if prompt_text:
        return _truncate_text(prompt_text, max_len=32)
    return None


def _ascii_slug(value: str) -> str:
    lowered = value.strip().lower()
    cleaned = _ASCII_WORD_RE.sub("_", lowered).strip("_")
    return cleaned


def _plugin_name_candidate(display_name: str, task_name: str, draft_id: str) -> str:
    stem = _ascii_slug(display_name)
    if not stem:
        stem = _ascii_slug(task_name) or "workflow"
    stem = stem[:40].strip("_") or "workflow"
    suffix = draft_id.replace("-", "")[:8]
    return f"{stem}_{suffix}"


def _resolve_status(record: WorkflowDraftRecord, *, latest_failed: bool = False) -> str:
    if record.last_distilled_manifest_path and record.last_distilled_script_path:
        return "distilled"
    if record.success_count >= record.success_threshold:
        return "ready"
    if latest_failed:
        return "needs_attention"
    return "collecting"


def _list_trace_contexts(task_id: str) -> list[ModelTraceContext]:
    task_root = traces_dir() / task_id
    if not task_root.is_dir():
        return []
    trace_paths: list[tuple[float, str, str, int, Path]] = []
    for path in task_root.glob("*/*.jsonl"):
        match = _TRACE_FILE_RE.match(path.name)
        if match is None:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        trace_paths.append(
            (
                stat.st_mtime,
                path.parent.name,
                match.group("target"),
                int(match.group("attempt")),
                path,
            )
        )
    contexts: list[ModelTraceContext] = []
    for _, run_id, target_label, attempt_number, _path in sorted(trace_paths, reverse=True):
        contexts.append(
            ModelTraceContext(
                task_id=task_id,
                run_id=run_id,
                target_label=target_label,
                attempt_number=attempt_number,
            )
        )
    return contexts


def _find_latest_trace_context(task_id: str) -> ModelTraceContext | None:
    contexts = _list_trace_contexts(task_id)
    if not contexts:
        return None
    return contexts[0]


def _trace_context_to_dict(context: ModelTraceContext) -> dict[str, object]:
    return {
        "task_id": context.task_id,
        "run_id": context.run_id,
        "target_label": context.target_label,
        "attempt_number": context.attempt_number,
    }


def _trace_context_from_dict(value: object) -> ModelTraceContext | None:
    if not isinstance(value, dict):
        return None
    task_id = str(value.get("task_id") or "").strip()
    run_id = str(value.get("run_id") or "").strip()
    target_label = str(value.get("target_label") or "").strip()
    attempt_number = value.get("attempt_number")
    if not task_id or not run_id or not target_label:
        return None
    if attempt_number is None:
        return None
    try:
        attempt = int(str(attempt_number).strip())
    except Exception:
        return None
    if attempt < 1:
        return None
    return ModelTraceContext(
        task_id=task_id,
        run_id=run_id,
        target_label=target_label,
        attempt_number=attempt,
    )


def _trace_context_exists(context: ModelTraceContext) -> bool:
    path = (
        traces_dir()
        / context.task_id
        / context.run_id
        / (f"{context.target_label}.attempt-{context.attempt_number}.jsonl")
    )
    return path.is_file()


def _build_snapshot_identity(payload: dict[str, Any]) -> dict[str, Any]:
    package = str(payload.get("package") or "").strip() or None
    app_id = resolve_app_id(payload)

    credentials_ref_raw = str(payload.get("credentials_ref") or "").strip()
    credentials_ref_kind = "missing"
    credentials_ref_path: str | None = None
    account_from_creds: str | None = None

    if credentials_ref_raw:
        if credentials_ref_raw.startswith("{") and credentials_ref_raw.endswith("}"):
            credentials_ref_kind = "inline_json"
            try:
                creds_payload = json.loads(credentials_ref_raw)
            except Exception:
                creds_payload = None
            if isinstance(creds_payload, dict):
                account_from_creds = (
                    str(
                        creds_payload.get("account") or creds_payload.get("username_or_email") or ""
                    ).strip()
                    or None
                )
        else:
            credentials_ref_kind = "path"
            credentials_ref_path = credentials_ref_raw

    account_inline = (
        str(payload.get("account") or "").strip() or str(payload.get("acc") or "").strip()
    ).strip() or None
    account = account_inline or account_from_creds

    account_source = "unknown"
    if account_from_creds:
        account_source = "credentials_ref"
    elif account_inline:
        account_source = "inline_payload"

    return {
        "app_id": app_id,
        "branch_id": branch_id_from_payload(payload),
        "package": package,
        "credentials_ref_kind": credentials_ref_kind,
        "credentials_ref_path": credentials_ref_path,
        "account": account,
        "account_source": account_source,
    }


class WorkflowDraftService:
    def __init__(self, store: WorkflowDraftStore | None = None) -> None:
        self._store = store or WorkflowDraftStore()

    def prepare_submission(
        self,
        *,
        payload: dict[str, Any],
        targets: list[dict[str, int]] | None,
        max_retries: int,
        retry_backoff_seconds: int,
        priority: int,
        display_name: str | None,
        draft_id: str | None,
        success_threshold: int | None,
        is_named_plugin: bool,
        conn: sqlite3.Connection | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        task_name = str(payload.get("task") or "anonymous")
        resolved_display_name = _derive_display_name(payload, display_name)
        has_text_prompt = _extract_prompt_text(payload) is not None
        should_track = (
            bool(draft_id)
            or bool(resolved_display_name)
            or (has_text_prompt and not is_named_plugin)
        )
        if not should_track:
            return dict(payload), None

        with self._store._tx(conn) as tx_conn:
            if draft_id:
                record = self._store.get_draft(draft_id, conn=tx_conn)
                if record is None:
                    raise ValueError(f"workflow draft not found: {draft_id}")
                self._validate_existing_draft(
                    record=record,
                    task_name=task_name,
                    display_name=resolved_display_name,
                    success_threshold=success_threshold,
                )
            else:
                if resolved_display_name is None:
                    return dict(payload), None
                new_draft_id = f"draft_{uuid.uuid4().hex[:12]}"
                threshold = max(1, int(success_threshold or 3))
                record = WorkflowDraftRecord(
                    draft_id=new_draft_id,
                    display_name=resolved_display_name,
                    task_name=task_name,
                    plugin_name_candidate=_plugin_name_candidate(
                        resolved_display_name, task_name, new_draft_id
                    ),
                    source=str(payload.get("_workflow_source") or "generic").strip() or "generic",
                    success_threshold=threshold,
                )
                self._store.create_draft(record, conn=tx_conn)

            if resolved_display_name and not draft_id:
                record.display_name = resolved_display_name
            if success_threshold is not None and not draft_id:
                record.success_threshold = max(1, int(success_threshold))
            prompt_text = _extract_prompt_text(payload)
            if prompt_text:
                record.latest_prompt_text = prompt_text
                record.prompt_history = _dedupe_keep_last(
                    [*record.prompt_history, prompt_text],
                    limit=20,
                )
            record.task_name = task_name
            record.status = _resolve_status(record)
            self._store.update_draft(record, conn=tx_conn)

        updated_payload = dict(payload)
        updated_payload["_workflow_draft_id"] = record.draft_id
        updated_payload["_workflow_display_name"] = record.display_name
        updated_payload["_workflow_success_threshold"] = record.success_threshold
        updated_payload["_workflow_plugin_name_candidate"] = record.plugin_name_candidate
        return updated_payload, self.summary(record.draft_id, conn=conn)

    def summary_for_payload(
        self, payload: dict[str, Any] | None, conn: sqlite3.Connection | None = None
    ) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        draft_id = str(payload.get("_workflow_draft_id") or "").strip()
        if not draft_id:
            return None
        return self.summary(draft_id, conn=conn)

    def summary(
        self, draft_id: str, conn: sqlite3.Connection | None = None
    ) -> dict[str, Any] | None:
        record = self._store.get_draft(draft_id, conn=conn)
        if record is None:
            return None
        remaining = max(0, record.success_threshold - record.success_count)
        summary = {
            "draft_id": record.draft_id,
            "display_name": record.display_name,
            "task_name": record.task_name,
            "status": record.status,
            "plugin_name_candidate": record.plugin_name_candidate,
            "source": record.source,
            "success_count": record.success_count,
            "failure_count": record.failure_count,
            "cancelled_count": record.cancelled_count,
            "success_threshold": record.success_threshold,
            "remaining_successes": remaining,
            "can_continue": record.last_success_snapshot is not None,
            "can_distill": (
                record.success_count >= record.success_threshold
                and not (record.last_distilled_manifest_path and record.last_distilled_script_path)
            ),
            "latest_prompt_text": record.latest_prompt_text,
            "latest_failure_advice": record.last_failure_advice,
            "last_success_snapshot_available": record.last_success_snapshot is not None,
            "last_distilled_manifest_path": record.last_distilled_manifest_path,
            "last_distilled_script_path": record.last_distilled_script_path,
            "saved_preferences": dict(record.saved_preferences or {}),
            "latest_terminal_task_id": record.latest_terminal_task_id,
            "latest_completed_task_id": record.latest_completed_task_id,
            "successful_task_ids": list(record.successful_task_ids),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }
        if record.status == "needs_attention":
            summary["message"] = (
                f"“{record.display_name}”本次执行未成功，已生成修改建议，可直接应用后重试。"
            )
            summary["next_action"] = "apply_suggestion"
        elif record.status == "distilled":
            summary["message"] = f"“{record.display_name}”的 YAML 草稿已生成，可继续测试或发布。"
            summary["next_action"] = "review_distilled"
        elif remaining > 0:
            summary["message"] = (
                f"当前稳定性样本 {record.success_count}/{record.success_threshold}。"
                f"可继续自动验证 {remaining} 次。"
            )
            summary["next_action"] = "continue_validation"
        else:
            summary["message"] = (
                f"已满足 {record.success_count}/{record.success_threshold} 成功样本，可生成 YAML。"
            )
            summary["next_action"] = "distill"
        return summary

    def list_summaries(
        self,
        limit: int = 100,
        conn: sqlite3.Connection | None = None,
        *,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            summary
            for record in self._store.list_drafts(limit=limit, conn=conn)
            if source is None or record.source == source
            if (summary := self.summary(record.draft_id, conn=conn)) is not None
        ]

    def list_ai_dialog_history(
        self, limit: int = 20, conn: sqlite3.Connection | None = None
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for record in self._store.list_drafts(limit=max(limit * 4, 50), conn=conn):
            if record.source != "ai_dialog":
                continue
            summary = self.summary(record.draft_id, conn=conn)
            if summary is None:
                continue
            snapshot = (
                dict(record.last_success_snapshot)
                if isinstance(record.last_success_snapshot, dict)
                else {}
            )
            identity = dict(snapshot.get("identity") or {}) if snapshot else {}
            items.append(
                {
                    "draft_id": record.draft_id,
                    "display_name": record.display_name,
                    "status": record.status,
                    "updated_at": record.updated_at or None,
                    "app_id": str(identity.get("app_id") or "").strip() or None,
                    "account": str(identity.get("account") or "").strip() or None,
                    "last_task_id": record.latest_completed_task_id
                    or record.latest_terminal_task_id
                    or None,
                    "can_replay": bool(record.last_success_snapshot),
                    "can_edit": bool(record.last_success_snapshot),
                    "workflow_draft": summary,
                }
            )
            if len(items) >= limit:
                break
        return items

    def record_terminal(
        self,
        *,
        task_record: Any,
        result: dict[str, Any] | None,
        payload_override: dict[str, Any] | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        if not isinstance(payload_override, dict) and not isinstance(
            getattr(task_record, "payload", None), dict
        ):
            return None
        payload = (
            dict(payload_override)
            if isinstance(payload_override, dict)
            else dict(task_record.payload)
        )
        draft_id = str(payload.get("_workflow_draft_id") or "").strip()
        if not draft_id:
            return None
        with self._store._tx(conn) as tx_conn:
            record = self._store.get_draft(draft_id, conn=tx_conn)
            if record is None:
                return None
            record.latest_terminal_task_id = str(task_record.task_id)
            prompt_text = _extract_prompt_text(payload)
            if prompt_text:
                record.latest_prompt_text = prompt_text
                record.prompt_history = _dedupe_keep_last(
                    [*record.prompt_history, prompt_text],
                    limit=20,
                )
            task_status = str(getattr(task_record, "status", "") or "").lower()
            if task_status == "completed":
                trace_contexts = _list_trace_contexts(str(task_record.task_id))
                latest_trace_context = trace_contexts[0] if len(trace_contexts) == 1 else None
                record.success_count += 1
                record.latest_completed_task_id = str(task_record.task_id)
                record.successful_task_ids = _dedupe_keep_last(
                    [*record.successful_task_ids, str(task_record.task_id)],
                    limit=20,
                )
                record.last_success_snapshot = {
                    "payload": payload,
                    "devices": list(getattr(task_record, "devices", []) or []),
                    "targets": list(getattr(task_record, "targets", []) or []),
                    "max_retries": int(getattr(task_record, "max_retries", 0) or 0),
                    "retry_backoff_seconds": int(
                        getattr(task_record, "retry_backoff_seconds", 2) or 2
                    ),
                    "priority": int(getattr(task_record, "priority", 50) or 50),
                    "identity": _build_snapshot_identity(payload),
                    "trace_context": (
                        _trace_context_to_dict(latest_trace_context)
                        if latest_trace_context is not None
                        else None
                    ),
                    "trace_context_count": len(trace_contexts),
                    "trace_context_ambiguous": len(trace_contexts) > 1,
                }
                record.last_failure_advice = None
                record.status = _resolve_status(record)
            elif task_status == "failed":
                record.failure_count += 1
                record.last_failure_advice = self._build_failure_advice(
                    payload=payload,
                    task_name=str(payload.get("task") or "anonymous"),
                    error=str(getattr(task_record, "error", "") or ""),
                    result=result or getattr(task_record, "result", None),
                )
                record.status = _resolve_status(record, latest_failed=True)
            elif task_status == "cancelled":
                record.cancelled_count += 1
                record.status = _resolve_status(record)
            else:
                return None
            self._store.update_draft(record, conn=tx_conn)
            return self._build_terminal_event_payload(record)

    def continuation_snapshot(self, draft_id: str) -> dict[str, Any]:
        record = self._store.get_draft(draft_id)
        if record is None:
            raise ValueError(f"workflow draft not found: {draft_id}")
        if not isinstance(record.last_success_snapshot, dict):
            raise ValueError("workflow draft has no successful snapshot to replay")
        snapshot = dict(record.last_success_snapshot)
        payload = dict(snapshot.get("payload") or {})
        saved_preferences = dict(record.saved_preferences or {})
        saved_payload_defaults = dict(saved_preferences.get("payload_defaults") or {})
        for key, value in saved_payload_defaults.items():
            if payload.get(key) in (None, "", []):
                payload[key] = value
        saved_branch = normalize_branch_id(saved_preferences.get("branch_id"), default="")
        if saved_branch and payload.get("branch_id") in (None, ""):
            payload["branch_id"] = saved_branch
        snapshot["payload"] = payload
        return {
            "display_name": record.display_name,
            "draft_id": record.draft_id,
            "success_threshold": record.success_threshold,
            "snapshot": snapshot,
        }

    def save_preferences(
        self,
        draft_id: str,
        *,
        branch_id: str | None = None,
        payload_defaults: dict[str, Any] | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        with self._store._tx(conn) as tx_conn:
            record = self._store.get_draft(draft_id, conn=tx_conn)
            if record is None:
                raise ValueError(f"workflow draft not found: {draft_id}")
            saved_preferences = dict(record.saved_preferences or {})
            if branch_id:
                saved_preferences["branch_id"] = normalize_branch_id(branch_id)
            if isinstance(payload_defaults, dict) and payload_defaults:
                merged_defaults = dict(saved_preferences.get("payload_defaults") or {})
                merged_defaults.update(payload_defaults)
                saved_preferences["payload_defaults"] = merged_defaults
            record.saved_preferences = saved_preferences
            self._store.update_draft(record, conn=tx_conn)
            return dict(record.saved_preferences)

    def distill_draft(
        self,
        draft_id: str,
        *,
        plugin_name: str | None = None,
        force: bool = False,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        with self._store._tx(conn) as tx_conn:
            record = self._store.get_draft(draft_id, conn=tx_conn)
            if record is None:
                raise ValueError(f"workflow draft not found: {draft_id}")
            if not force and record.success_count < record.success_threshold:
                return {
                    "ok": False,
                    "code": "threshold_not_met",
                    "message": (
                        f"草稿 {record.display_name} 成功样本 {record.success_count} "
                        f"未达到门槛 {record.success_threshold}"
                    ),
                    "draft_id": draft_id,
                    "success_count": record.success_count,
                    "success_threshold": record.success_threshold,
                }

            trace_context = self._resolve_distill_trace_context(record)
            if trace_context is None:
                raise ValueError("no successful golden run trace found for workflow draft")

            resolved_name = _ascii_slug(plugin_name or record.plugin_name_candidate)
            resolved_name = resolved_name[:56].strip("_") or f"workflow_{draft_id[-8:]}"
            output_name = (
                resolved_name if resolved_name.endswith("_draft") else f"{resolved_name}_draft"
            )
            output_dir = plugins_dir() / ".drafts" / output_name
            snapshot = (
                dict(record.last_success_snapshot)
                if isinstance(record.last_success_snapshot, dict)
                else {}
            )
            identity = snapshot.get("identity") if isinstance(snapshot, dict) else None
            distilled = GoldenRunDistiller().distill(
                context=trace_context,
                output_dir=output_dir,
                plugin_name=output_name,
                display_name=record.display_name,
                category=record.category,
                snapshot_identity=identity if isinstance(identity, dict) else None,
                draft_id=record.draft_id,
            )
            record.last_distilled_manifest_path = str(distilled.manifest_path)
            record.last_distilled_script_path = str(distilled.script_path)
            record.status = _resolve_status(record)
            self._store.update_draft(record, conn=tx_conn)
            return {
                "ok": True,
                "draft_id": record.draft_id,
                "display_name": record.display_name,
                "plugin_name": output_name,
                "output_dir": str(output_dir),
                "manifest_path": str(distilled.manifest_path),
                "script_path": str(distilled.script_path),
                "report_path": str(distilled.report_path),
                "success_count": record.success_count,
                "success_threshold": record.success_threshold,
            }

    def cleanup_task_references(
        self,
        task_ids: list[str],
        *,
        clear_all: bool = False,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        with self._store._tx(conn) as tx_conn:
            if clear_all:
                self._store.clear_all_drafts(conn=tx_conn)
                return
            removed = {str(task_id).strip() for task_id in task_ids if str(task_id).strip()}
            if not removed:
                return
            for record in self._store.list_drafts(limit=10000, conn=tx_conn):
                changed = False
                if record.latest_terminal_task_id in removed:
                    record.latest_terminal_task_id = None
                    if record.status == "needs_attention":
                        record.last_failure_advice = None
                    changed = True
                if record.latest_completed_task_id in removed:
                    record.latest_completed_task_id = None
                    record.last_success_snapshot = None
                    changed = True
                filtered_successful_ids = [
                    task_id for task_id in record.successful_task_ids if task_id not in removed
                ]
                if filtered_successful_ids != record.successful_task_ids:
                    record.successful_task_ids = filtered_successful_ids
                    changed = True
                if not changed:
                    continue
                record.status = _resolve_status(record)
                self._store.update_draft(record, conn=tx_conn)

    def clear_all(self, conn: sqlite3.Connection | None = None) -> None:
        with self._store._tx(conn) as tx_conn:
            self._store.clear_all_drafts(conn=tx_conn)

    def _validate_existing_draft(
        self,
        *,
        record: WorkflowDraftRecord,
        task_name: str,
        display_name: str | None,
        success_threshold: int | None,
    ) -> None:
        if task_name != record.task_name:
            raise ValueError(
                f"workflow draft task mismatch: expected {record.task_name}, got {task_name}"
            )
        if display_name is not None and display_name != record.display_name:
            raise ValueError(
                "workflow draft display_name mismatch: "
                f"expected {record.display_name}, got {display_name}"
            )
        if success_threshold is not None and int(success_threshold) != int(
            record.success_threshold
        ):
            raise ValueError(
                "workflow draft success_threshold mismatch: "
                f"expected {record.success_threshold}, got {success_threshold}"
            )

    def _resolve_distill_trace_context(
        self, record: WorkflowDraftRecord
    ) -> ModelTraceContext | None:
        snapshot = record.last_success_snapshot
        if isinstance(snapshot, dict):
            trace_context = _trace_context_from_dict(snapshot.get("trace_context"))
            if trace_context is not None:
                if bool(snapshot.get("trace_context_ambiguous")):
                    raise ValueError(
                        "multiple golden run traces found for latest successful task; "
                        "target-specific distillation is required"
                    )
                if _trace_context_exists(trace_context):
                    return trace_context
        for task_id in reversed(record.successful_task_ids):
            contexts = _list_trace_contexts(task_id)
            if len(contexts) > 1:
                raise ValueError(
                    "multiple golden run traces found for a successful task; "
                    "target-specific distillation is required"
                )
            if contexts:
                return contexts[0]
        return None

    def _build_failure_advice(
        self,
        *,
        payload: dict[str, Any],
        task_name: str,
        error: str,
        result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        message = str((result or {}).get("message") or error or "任务执行未成功").strip()
        checkpoint = str((result or {}).get("checkpoint") or "").strip()
        prompt_text = _extract_prompt_text(payload) or ""
        suggestions: list[str] = []
        missing: list[str] = []

        if len(prompt_text.strip()) < 8:
            missing.append("任务目标")
            suggestions.append("明确说明要完成的动作和目标页面。")
        if not any(
            key in payload for key in ("expected_state_ids", "success_state", "success_criteria")
        ):
            missing.append("成功标准")
            suggestions.append("补充成功标准，例如“进入首页并看到已登录头像”。")
        if not any(key in payload for key in ("package", "app_name", "app", "package_name")):
            suggestions.append("标明目标应用或包名，避免系统在错误应用中尝试。")
        if not any(key in payload for key in ("allowed_actions", "routes", "hops")):
            suggestions.append("补充允许动作或页面跳转线索，减少无关探索。")
        if "verify" in message.lower() or "验证码" in message or "二次验证" in message:
            suggestions.append("补充异常分支：若出现验证码或二次验证，立即停止并返回原因。")
        if not suggestions:
            suggestions.append("保留当前目标描述，并补充成功标准或异常处理分支后重试。")

        base_prompt = prompt_text or str(payload.get("_workflow_display_name") or task_name)
        rewritten_parts = [base_prompt.strip() or "完成目标任务"]
        if "成功标准" in missing:
            rewritten_parts.append("成功标准：进入目标页面并确认账号处于已登录状态。")
        if not any("异常分支" in item for item in suggestions):
            rewritten_parts.append("若出现验证码、弹窗或风控页面，停止并返回原因。")
        rewritten_prompt = "；".join(part for part in rewritten_parts if part).strip("；")

        return {
            "summary": message or "任务执行未成功",
            "checkpoint": checkpoint,
            "missing": missing,
            "suggestions": _dedupe_keep_last(suggestions, limit=8),
            "suggested_prompt": rewritten_prompt,
            "evidence": {
                "task_name": task_name,
                "error": error,
                "checkpoint": checkpoint,
            },
        }

    def _build_terminal_event_payload(self, record: WorkflowDraftRecord) -> dict[str, Any]:
        summary = self.summary(record.draft_id)
        if summary is None:
            return {}
        if record.status == "needs_attention":
            summary["message"] = (
                f"“{record.display_name}”本次执行未成功，已生成修改建议，可直接应用后重试。"
            )
            summary["next_action"] = "apply_suggestion"
            return summary
        if record.status == "distilled":
            summary["message"] = f"“{record.display_name}”的 YAML 草稿已生成，可继续测试或发布。"
            summary["next_action"] = "review_distilled"
            return summary
        remaining = max(0, record.success_threshold - record.success_count)
        if remaining > 0:
            summary["message"] = (
                f"已成功完成“{record.display_name}”，当前稳定性样本 "
                f"{record.success_count}/{record.success_threshold}。"
                f"是否继续自动验证 {remaining} 次以提升脚本成功率？"
            )
            summary["next_action"] = "continue_validation"
            return summary
        summary["message"] = (
            f"“{record.display_name}”已获得 {record.success_count}/{record.success_threshold} "
            "成功样本，可生成 YAML 脚本草稿。"
        )
        summary["next_action"] = "distill"
        return summary
