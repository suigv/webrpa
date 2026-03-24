from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core.account_service import update_account_fields
from core.ai_task_annotation_store import AITaskAnnotationStore
from core.business_profile import normalize_branch_id
from core.workflow_drafts import WorkflowDraftService

_INPUT_TYPE_META = {
    "account_credential": {"label": "账号密码", "sensitive": True, "save_eligible": False},
    "verification_code": {"label": "验证码", "sensitive": True, "save_eligible": False},
    "search_keyword": {"label": "搜索关键词", "sensitive": False, "save_eligible": True},
    "target_blogger_id": {"label": "博主ID", "sensitive": False, "save_eligible": True},
    "dm_reply_text": {"label": "私信/回复内容", "sensitive": False, "save_eligible": True},
    "profile_field_text": {"label": "资料字段内容", "sensitive": False, "save_eligible": True},
    "temporary_text": {"label": "其他临时文本", "sensitive": False, "save_eligible": False},
}

_PAYLOAD_KEY_BY_INPUT_TYPE = {
    "search_keyword": "keyword",
    "target_blogger_id": "target_blogger_id",
    "dm_reply_text": "dm_reply_text",
    "profile_field_text": "profile_field_text",
}


class AIDialogSaveService:
    def __init__(
        self,
        *,
        workflow_drafts: WorkflowDraftService | None = None,
        annotations: AITaskAnnotationStore | None = None,
    ) -> None:
        self._workflow_drafts = workflow_drafts or WorkflowDraftService()
        self._annotations = annotations or AITaskAnnotationStore()

    def create_annotation(
        self,
        *,
        task_id: str,
        input_type: str,
        raw_value: str | None,
        step_id: str | None = None,
        source: str = "human_takeover",
        action_kind: str = "manual_input",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        canonical_type = str(input_type or "").strip() or "temporary_text"
        meta = _INPUT_TYPE_META.get(canonical_type, _INPUT_TYPE_META["temporary_text"])
        record = self._annotations.create_annotation(
            task_id=task_id,
            step_id=step_id,
            source=source,
            action_kind=action_kind,
            input_type=canonical_type,
            input_label=str(meta["label"]),
            sensitive=bool(meta["sensitive"]),
            save_eligible=bool(meta["save_eligible"]),
            raw_value=str(raw_value) if raw_value is not None else None,
            metadata=metadata,
            captured_at=datetime.now(UTC).isoformat(),
        )
        return self._record_to_dict(record)

    def list_annotations(self, task_id: str) -> list[dict[str, Any]]:
        return [self._record_to_dict(item) for item in self._annotations.list_annotations(task_id)]

    def list_save_candidates(self, draft_id: str) -> dict[str, Any]:
        snapshot_bundle = self._workflow_drafts.continuation_snapshot(draft_id)
        snapshot = dict(snapshot_bundle["snapshot"])
        payload = dict(snapshot.get("payload") or {})
        identity = dict(snapshot.get("identity") or {})
        summary = self._workflow_drafts.summary(draft_id) or {}
        latest_task_id = str(summary.get("latest_completed_task_id") or "").strip()
        annotations = self.list_annotations(latest_task_id) if latest_task_id else []

        candidates: list[dict[str, Any]] = []
        branch_id = normalize_branch_id(payload.get("branch_id") or identity.get("branch_id"), default="")
        if branch_id and str(identity.get("account") or "").strip():
            candidates.append(
                {
                    "candidate_id": "account_default_branch",
                    "kind": "account_default_branch",
                    "label": "保存本账号默认业务分支",
                    "description": f"后续该账号默认使用 {branch_id}",
                    "value_preview": branch_id,
                    "save_target": "account",
                }
            )

        for item in annotations:
            input_type = str(item.get("input_type") or "").strip()
            if not item.get("save_eligible"):
                continue
            payload_key = _PAYLOAD_KEY_BY_INPUT_TYPE.get(input_type)
            raw_value = str(item.get("raw_value") or "").strip()
            if not payload_key or not raw_value:
                continue
            candidates.append(
                {
                    "candidate_id": str(item["annotation_id"]),
                    "kind": "payload_default",
                    "payload_key": payload_key,
                    "label": str(item.get("input_label") or input_type),
                    "description": "保存为该 AI 草稿的默认输入",
                    "raw_value": raw_value,
                    "value_preview": raw_value[:120],
                    "save_target": "workflow_draft",
                }
            )

        return {
            "draft_id": draft_id,
            "snapshot": {
                "app_id": str(identity.get("app_id") or "").strip() or None,
                "account": str(identity.get("account") or "").strip() or None,
                "branch_id": branch_id or None,
                "task_id": latest_task_id or None,
            },
            "candidates": candidates,
        }

    def apply_save_choices(self, draft_id: str, candidate_ids: list[str]) -> dict[str, Any]:
        selected_ids = {str(item or "").strip() for item in candidate_ids if str(item or "").strip()}
        if not selected_ids:
            return {"draft_id": draft_id, "saved": []}

        candidate_bundle = self.list_save_candidates(draft_id)
        candidates = candidate_bundle["candidates"]
        snapshot = candidate_bundle["snapshot"]
        saved: list[dict[str, Any]] = []
        payload_defaults: dict[str, Any] = {}
        branch_to_save: str | None = None

        by_id = {str(item["candidate_id"]): item for item in candidates}
        for candidate_id in selected_ids:
            candidate = by_id.get(candidate_id)
            if candidate is None:
                continue
            if candidate["kind"] == "account_default_branch":
                branch_to_save = str(snapshot.get("branch_id") or "").strip() or None
                account = str(snapshot.get("account") or "").strip()
                if branch_to_save and account:
                    update_account_fields(account, {"default_branch": branch_to_save})
                    saved.append({"candidate_id": candidate_id, "target": "account_default_branch"})
            elif candidate["kind"] == "payload_default":
                payload_key = str(candidate.get("payload_key") or "").strip()
                value = str(candidate.get("raw_value") or candidate.get("value_preview") or "").strip()
                if payload_key and value:
                    payload_defaults[payload_key] = value
                    saved.append({"candidate_id": candidate_id, "target": f"payload:{payload_key}"})

        if branch_to_save or payload_defaults:
            self._workflow_drafts.save_preferences(
                draft_id,
                branch_id=branch_to_save,
                payload_defaults=payload_defaults or None,
            )

        return {"draft_id": draft_id, "saved": saved}

    @staticmethod
    def _record_to_dict(record: Any) -> dict[str, Any]:
        return {
            "annotation_id": str(record.annotation_id),
            "task_id": str(record.task_id),
            "step_id": record.step_id,
            "source": str(record.source),
            "action_kind": str(record.action_kind),
            "input_type": str(record.input_type),
            "input_label": str(record.input_label),
            "sensitive": bool(record.sensitive),
            "save_eligible": bool(record.save_eligible),
            "raw_value": record.raw_value,
            "metadata": dict(record.metadata or {}),
            "captured_at": str(record.captured_at),
        }
