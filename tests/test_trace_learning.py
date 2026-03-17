from __future__ import annotations

import json

import yaml

from core import app_config as app_config_module
from core import app_config_writer as writer_module
from core.app_config_writer import AppConfigWriter
from core.trace_learner import TraceLearner


def test_trace_learner_extracts_resource_ids_by_state_and_skips_unknown_and_sensitive() -> None:
    learner = TraceLearner()

    records = [
        {
            "record_type": "step",
            "observation": {
                "observed_state_ids": ["home"],
                "data": {"state": {"state_id": "home"}},
            },
            "action_params": {},
            "action_result": {"data": {"resource_id": "com.twitter.android:id/home_timeline"}},
        },
        {
            "record_type": "step",
            "observation": {
                "observed_state_ids": ["unknown"],
                "data": {"state": {"state_id": "unknown"}},
            },
            "action_params": {"resource_id": "com.twitter.android:id/unknown_button"},
            "action_result": {"data": {}},
        },
        {
            "record_type": "step",
            "observation": {
                "observed_state_ids": ["login_password"],
                "data": {"state": {"state_id": "login_password"}},
            },
            "action_params": {
                "resource_id": "com.twitter.android:id/password_field",
                "query_type": "password",
            },
            "action_result": {"data": {"resource_id": "com.twitter.android:id/password_field"}},
        },
        {
            "record_type": "step",
            "observation": {
                "observed_state_ids": ["profile"],
                "data": {"state": {"state_id": "profile"}},
            },
            "action_params": {"resource_id": "com.twitter.android:id/profile_header"},
            "action_result": {"data": {}},
        },
    ]

    learned = learner.learn_from_records(records)

    assert learned == {
        "home": ["com.twitter.android:id/home_timeline"],
        "profile": ["com.twitter.android:id/profile_header"],
    }


def test_app_config_writer_applies_threshold_before_merging_stage_patterns(
    tmp_path, monkeypatch
) -> None:
    config_root = tmp_path / "config"
    apps_dir = config_root / "apps"
    apps_dir.mkdir(parents=True)
    data_root = config_root / "data"
    data_root.mkdir(parents=True)

    app_path = apps_dir / "x.yaml"
    app_path.write_text(
        yaml.safe_dump(
            {
                "version": "v1",
                "package_name": "com.twitter.android",
                "states": [{"id": "home", "description": "timeline"}],
                "schemes": {},
                "selectors": {},
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_config_module, "config_dir", lambda: config_root)
    monkeypatch.setattr(writer_module, "data_dir", lambda: data_root)

    writer = AppConfigWriter(threshold=3)
    learned = {"home": ["com.twitter.android:id/home_timeline"]}

    first = writer.merge_stage_resource_ids("x", learned)
    second = writer.merge_stage_resource_ids("x", learned)
    third = writer.merge_stage_resource_ids("x", learned)

    assert first["updated"] is False
    assert second["updated"] is False
    assert third["updated"] is True
    assert third["added"] == {"home": ["com.twitter.android:id/home_timeline"]}

    persisted = yaml.safe_load(app_path.read_text(encoding="utf-8"))
    assert persisted["stage_patterns"]["home"]["resource_ids"] == [
        "com.twitter.android:id/home_timeline"
    ]
    assert persisted["stage_patterns"]["home"]["focus_markers"] == []
    assert persisted["stage_patterns"]["home"]["text_markers"] == []

    counts_path = data_root / "learned_ids.json"
    counts = json.loads(counts_path.read_text(encoding="utf-8"))
    assert counts["counts"]["x"]["home"]["com.twitter.android:id/home_timeline"] == 3

    fourth = writer.merge_stage_resource_ids("x", learned)
    assert fourth["updated"] is False
    persisted_again = yaml.safe_load(app_path.read_text(encoding="utf-8"))
    assert persisted_again["stage_patterns"]["home"]["resource_ids"] == [
        "com.twitter.android:id/home_timeline"
    ]
