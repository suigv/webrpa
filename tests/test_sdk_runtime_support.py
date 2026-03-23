from engine.actions.sdk_runtime_support import load_ui_scheme_action
from engine.models.runtime import ExecutionContext


def test_load_ui_scheme_uses_context_payload_app_id() -> None:
    seen_apps: list[str] = []

    def _load_app_config_document(app_id: str) -> dict[str, object]:
        seen_apps.append(app_id)
        return {"schemes": {"profile": "twitter://user?screen_name={screen_name}"}}

    result = load_ui_scheme_action(
        {"key": "profile", "kwargs": {"screen_name": "jack"}},
        load_ui_config_document=lambda: {},
        load_app_config_document=_load_app_config_document,
        resolve_ui_key=lambda values, key: values.get(key),
        context=ExecutionContext(payload={"app_id": "x"}),
    )

    assert result.ok is True
    assert result.data["app"] == "x"
    assert result.data["url"] == "twitter://user?screen_name=jack"
    assert seen_apps == ["x"]


def test_load_ui_scheme_can_resolve_app_from_context_payload_package() -> None:
    seen_apps: list[str] = []

    def _load_app_config_document(app_id: str) -> dict[str, object]:
        seen_apps.append(app_id)
        return {"schemes": {"profile": "twitter://user?screen_name={screen_name}"}}

    result = load_ui_scheme_action(
        {"key": "profile", "kwargs": {"screen_name": "jack"}},
        load_ui_config_document=lambda: {},
        load_app_config_document=_load_app_config_document,
        resolve_ui_key=lambda values, key: values.get(key),
        context=ExecutionContext(payload={"package": "com.twitter.android"}),
    )

    assert result.ok is True
    assert result.data["app"] == "x"
    assert result.data["url"] == "twitter://user?screen_name=jack"
    assert seen_apps == ["x"]
