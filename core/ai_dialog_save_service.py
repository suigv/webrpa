from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core.account_service import update_account_fields
from core.ai_task_annotation_store import AITaskAnnotationStore
from core.app_branch_service import AppBranchProfileService
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
        branch_profiles: AppBranchProfileService | None = None,
    ) -> None:
        self._workflow_drafts = workflow_drafts or WorkflowDraftService()
        self._annotations = annotations or AITaskAnnotationStore()
        self._branch_profiles = branch_profiles or AppBranchProfileService()

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
        app_id = str(identity.get("app_id") or "").strip()
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
            candidates.append(
                {
                    "candidate_id": "workflow_default_branch",
                    "kind": "workflow_default_branch",
                    "label": "保存本草稿默认业务分支",
                    "description": f"后续从该草稿继续执行时默认使用 {branch_id}",
                    "value_preview": branch_id,
                    "save_target": "workflow_draft",
                }
            )

        resource_namespace = str(payload.get("resource_namespace") or "").strip()
        if app_id and branch_id and resource_namespace:
            candidates.append(
                {
                    "candidate_id": "branch_resource_namespace",
                    "kind": "branch_resource_namespace",
                    "label": "保存分支资源命名空间",
                    "description": f"写入 {app_id} / {branch_id} 分支配置",
                    "raw_value": resource_namespace,
                    "value_preview": resource_namespace,
                    "save_target": "app_branch",
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
            if app_id and branch_id and input_type == "search_keyword":
                candidates.append(
                    {
                        "candidate_id": f'{item["annotation_id"]}:branch_keyword',
                        "kind": "branch_keyword",
                        "label": "保存到分支搜索关键词",
                        "description": f"写入 {app_id} / {branch_id} 分支关键词",
                        "raw_value": raw_value,
                        "value_preview": raw_value[:120],
                        "save_target": "app_branch",
                    }
                )
            if app_id and branch_id and input_type == "dm_reply_text":
                candidates.append(
                    {
                        "candidate_id": f'{item["annotation_id"]}:branch_reply_text',
                        "kind": "branch_reply_text",
                        "label": "保存到分支回复文案",
                        "description": f"写入 {app_id} / {branch_id} 分支回复文案",
                        "raw_value": raw_value,
                        "value_preview": raw_value[:120],
                        "save_target": "app_branch",
                    }
                )

        return {
            "draft_id": draft_id,
            "snapshot": {
                "app_id": app_id or None,
                "account": str(identity.get("account") or "").strip() or None,
                "branch_id": branch_id or None,
                "task_id": latest_task_id or None,
                "resource_namespace": resource_namespace or None,
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
        workflow_branch_to_save: str | None = None
        branch_to_save: str | None = None
        branch_keywords: list[str] = []
        branch_reply_texts: list[str] = []
        branch_resource_namespace: str | None = None

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
            elif candidate["kind"] == "workflow_default_branch":
                workflow_branch_to_save = str(snapshot.get("branch_id") or "").strip() or None
                if workflow_branch_to_save:
                    saved.append({"candidate_id": candidate_id, "target": "workflow_default_branch"})
            elif candidate["kind"] == "payload_default":
                payload_key = str(candidate.get("payload_key") or "").strip()
                value = str(candidate.get("raw_value") or candidate.get("value_preview") or "").strip()
                if payload_key and value:
                    payload_defaults[payload_key] = value
                    saved.append({"candidate_id": candidate_id, "target": f"payload:{payload_key}"})
            elif candidate["kind"] == "branch_keyword":
                value = str(candidate.get("raw_value") or "").strip()
                if value:
                    branch_keywords.append(value)
                    saved.append({"candidate_id": candidate_id, "target": "app_branch:search_keywords"})
            elif candidate["kind"] == "branch_reply_text":
                value = str(candidate.get("raw_value") or "").strip()
                if value:
                    branch_reply_texts.append(value)
                    saved.append({"candidate_id": candidate_id, "target": "app_branch:reply_texts"})
            elif candidate["kind"] == "branch_resource_namespace":
                branch_resource_namespace = (
                    str(candidate.get("raw_value") or candidate.get("value_preview") or "").strip()
                    or None
                )
                if branch_resource_namespace:
                    saved.append(
                        {"candidate_id": candidate_id, "target": "app_branch:resource_namespace"}
                    )

        if branch_to_save or workflow_branch_to_save or payload_defaults:
            self._workflow_drafts.save_preferences(
                draft_id,
                branch_id=workflow_branch_to_save or branch_to_save,
                payload_defaults=payload_defaults or None,
            )

        app_id = str(snapshot.get("app_id") or "").strip()
        snapshot_branch = str(snapshot.get("branch_id") or "").strip()
        if app_id and snapshot_branch and (
            branch_keywords or branch_reply_texts or branch_resource_namespace
        ):
            self._branch_profiles.merge_branch_learning(
                app_id,
                branch_id=snapshot_branch,
                search_keywords=branch_keywords or None,
                reply_texts=branch_reply_texts or None,
                resource_namespace=branch_resource_namespace,
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
