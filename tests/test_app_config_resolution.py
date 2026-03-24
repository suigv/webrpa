import yaml

from core.app_config import AppConfigManager, resolve_app_id, resolve_app_payload


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


def test_resolve_app_id_supports_alias_and_multiple_package_names(tmp_path, monkeypatch) -> None:
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir(parents=True, exist_ok=True)
    (apps_dir / "x.yaml").write_text(
        yaml.safe_dump(
            {
                "app_id": "x",
                "display_name": "X",
                "aliases": ["twitter", "tweet"],
                "package_name": "com.twitter.android",
                "package_names": ["com.twitter.android", "com.twitter.android.beta"],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("core.app_config.config_dir", lambda: tmp_path)

    assert resolve_app_id({"app_id": "twitter"}, default_app="default") == "x"
    assert resolve_app_id({"package": "com.twitter.android.beta"}, default_app="default") == "x"


def test_ensure_app_config_bootstraps_identity_document(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("core.app_config.config_dir", lambda: tmp_path)

    result = AppConfigManager.ensure_app_config(
        app_id="twitter_cn",
        display_name="Twitter 中文",
        package_name="com.twitter.cn",
    )

    assert result["app_id"] == "twitter_cn"
    assert result["created"] is True
    document = yaml.safe_load((tmp_path / "apps" / "twitter_cn.yaml").read_text(encoding="utf-8"))
    assert document["app_id"] == "twitter_cn"
    assert document["display_name"] == "Twitter 中文"
    assert document["package_name"] == "com.twitter.cn"
