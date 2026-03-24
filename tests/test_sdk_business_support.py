from engine.actions.sdk_business_support import (
    get_blogger_candidate_action,
    save_blogger_candidate_action,
)
from engine.models.runtime import ActionResult


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
