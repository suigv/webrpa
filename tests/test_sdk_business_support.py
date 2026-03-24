from engine.actions.sdk_business_support import (
    choose_blogger_search_query_action,
    generate_dm_reply_action,
    get_blogger_candidate_action,
    pick_weighted_keyword_action,
    save_blogger_candidate_action,
)
from engine.models.runtime import ActionResult, ExecutionContext


def test_save_blogger_candidate_accepts_shared_key_alias() -> None:
    seen: dict[str, object] = {}

    def _append_shared_unique(params: dict[str, object], _context: object) -> ActionResult:
        seen.update(params)
        return ActionResult(ok=True, code="ok", data={"key": str(params["key"])})

    result = save_blogger_candidate_action(
        {
            "shared_key": "blogger_candidates",
            "candidate": {"username": "CWrightbough"},
        },
        context=None,
        append_shared_unique=_append_shared_unique,
    )

    assert result.ok is True
    assert seen["key"] == "blogger_candidates"


def test_get_blogger_candidate_accepts_shared_key_alias() -> None:
    seen: dict[str, object] = {}

    def _load_shared_optional(params: dict[str, object], _context: object) -> ActionResult:
        seen.update(params)
        return ActionResult(
            ok=True,
            code="ok",
            data={"value": [{"username": "CWrightbough"}]},
        )

    result = get_blogger_candidate_action(
        {"shared_key": "blogger_candidates"},
        context=None,
        load_shared_optional=_load_shared_optional,
    )

    assert result.ok is True
    assert result.data["candidate"] == {"username": "CWrightbough"}
    assert seen["key"] == "blogger_candidates"


def test_pick_weighted_keyword_prefers_branch_profile(monkeypatch) -> None:
    monkeypatch.setattr(
        "engine.actions.sdk_business_support.AppBranchProfileService.get_profiles",
        lambda self, app_id: {
            "app_id": app_id,
            "default_branch": "volc",
            "branches": [
                {
                    "branch_id": "volc",
                    "search_keywords": ["#mytxx", "#girl"],
                    "blacklist_keywords": [],
                    "reply_texts": [],
                    "resource_namespace": "",
                    "reply_ai_type": "",
                }
            ],
        },
    )

    result = pick_weighted_keyword_action(
        {},
        ExecutionContext(payload={"app_id": "x"}),
        load_strategy_document=lambda: {"strategies": {}},
    )

    assert result.ok is True
    assert result.data["source"] == "branch_profile"
    assert result.data["branch_id"] == "volc"
    assert result.data["keyword"] in {"#mytxx", "#girl"}


def test_generate_dm_reply_prefers_branch_profile_and_exposes_reply_ai_type(monkeypatch) -> None:
    monkeypatch.setattr(
        "engine.actions.sdk_business_support.AppBranchProfileService.get_profiles",
        lambda self, app_id: {
            "app_id": app_id,
            "default_branch": "volc",
            "branches": [
                {
                    "branch_id": "volc",
                    "search_keywords": [],
                    "blacklist_keywords": [],
                    "reply_texts": ["你好呀", "刚看到消息"],
                    "resource_namespace": "",
                    "reply_ai_type": "dating",
                }
            ],
        },
    )

    result = generate_dm_reply_action(
        {"last_message": "你在吗"},
        ExecutionContext(payload={"app_id": "x"}),
        select_interaction_template=lambda section, branch_id: f"{section}:{branch_id}",
    )

    assert result.ok is True
    assert result.data["source"] == "branch_profile"
    assert result.data["branch_id"] == "volc"
    assert result.data["reply_ai_type"] == "dating"
    assert result.data["reply_text"].startswith(("你好呀", "刚看到消息"))


def test_choose_blogger_search_query_falls_back_to_branch_profile_resource_defaults(monkeypatch) -> None:
    monkeypatch.setattr(
        "engine.actions.sdk_business_support.AppBranchProfileService.get_profiles",
        lambda self, app_id: {
            "app_id": app_id,
            "default_branch": "part_time",
            "branches": [
                {
                    "branch_id": "part_time",
                    "search_keywords": ["#paypay", "#mytjz"],
                    "blacklist_keywords": [],
                    "reply_texts": [],
                    "resource_namespace": "x.part_time.pool",
                    "reply_ai_type": "",
                }
            ],
        },
    )

    result = choose_blogger_search_query_action(
        {},
        ExecutionContext(payload={"app_id": "x"}),
        load_interaction_document=lambda: {"search_query": {"default": ["#fallback"]}},
    )

    assert result.ok is True
    assert result.data["branch_id"] == "part_time"
    assert result.data["source"] == "branch_profile"
    assert result.data["query"] in {"#paypay", "#mytjz"}
