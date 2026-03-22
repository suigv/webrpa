from core.app_config import resolve_app_id, resolve_app_payload


def test_resolve_app_id_prefers_canonical_keys_over_legacy_alias() -> None:
    assert (
        resolve_app_id(
            {"app_id": "x", "app": "legacy"},
            params={"app_id": "canonical", "app": "legacy-param"},
            default_app="default",
        )
        == "canonical"
    )


def test_resolve_app_payload_normalizes_app_id_and_drops_matching_legacy_alias() -> None:
    payload = resolve_app_payload("x", {"task": "demo", "app": "x"})

    assert payload["app_id"] == "x"
    assert "app" not in payload


def test_resolve_app_payload_injects_hidden_app_defaults(monkeypatch) -> None:
    monkeypatch.setattr(
        "core.app_config.get_app_config",
        lambda app_id: {
            "package_name": "com.twitter.android",
            "states": ["home"],
            "stage_patterns": {"home": {"text_markers": ["For you"]}},
            "selectors": {"home_tab": {"type": "id", "value": "home"}},
        },
    )

    payload = resolve_app_payload(
        "x",
        {"task": "demo", "package": "explicit.package"},
    )

    assert payload["package"] == "explicit.package"
    assert payload["_app_states"] == ["home"]
    assert payload["_app_stage_patterns"] == {"home": {"text_markers": ["For you"]}}
    assert payload["_app_selectors"] == {"home_tab": {"type": "id", "value": "home"}}
