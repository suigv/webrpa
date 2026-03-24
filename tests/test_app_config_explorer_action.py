from __future__ import annotations

from pathlib import Path

from engine.actions.app_config_actions import explore_app_config_action
from engine.models.runtime import ExecutionContext


def test_explore_app_config_action_bootstraps_app_and_accepts_partial_learning(
    tmp_path, monkeypatch
):
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("core.app_config.config_dir", lambda: tmp_path)

    seen: dict[str, object] = {}

    class _FakeAgentExecutorRuntime:
        def __init__(self):
            self._trace_store = object()

        def run(self, payload, *, should_cancel=None, runtime=None):
            _ = should_cancel
            seen["payload"] = dict(payload)
            seen["runtime"] = dict(runtime or {})
            return {
                "ok": False,
                "status": "failed_runtime_error",
                "code": "planner_stalled",
                "message": "planner stalled",
            }

        def _trace_context(self, runtime):
            _ = runtime
            from core.model_trace_store import ModelTraceContext

            return ModelTraceContext(
                task_id="task-1",
                run_id="run-1",
                target_label="device-1-cloud-1",
                attempt_number=1,
            )

    class _FakeGoldenRunDistiller:
        def __init__(self, *, trace_store=None):
            seen["trace_store"] = trace_store

        def record_app_config_learning_from_context(
            self,
            context,
            *,
            snapshot_identity=None,
            draft_id=None,
        ):
            _ = draft_id
            seen["trace_context"] = context
            seen["snapshot_identity"] = dict(snapshot_identity or {})
            return {
                "app_id": "demoapp",
                "recorded": 2,
                "recorded_by_kind": {"selector": 1, "xml_filter": 1},
            }

    monkeypatch.setattr("engine.agent_executor.AgentExecutorRuntime", _FakeAgentExecutorRuntime)
    monkeypatch.setattr("core.golden_run_distillation.GoldenRunDistiller", _FakeGoldenRunDistiller)

    result = explore_app_config_action(
        {
            "package_name": "com.demo.app",
            "app_display_name": "Demo App",
            "goal": "识别首页和主导航",
            "max_steps": 9,
        },
        ExecutionContext(
            payload={},
            runtime={
                "task_id": "task-1",
                "run_id": "run-1",
                "target": {"device_id": 1, "cloud_id": 1},
            },
        ),
    )

    assert result.ok is True
    assert result.code == "partial_exploration"
    assert result.data["app_id"] == "demoapp"
    assert result.data["candidate_update"]["recorded"] == 2
    assert seen["payload"]["package"] == "com.demo.app"
    assert seen["payload"]["app_id"] == "demoapp"
    assert seen["payload"]["max_steps"] == 9
    assert seen["payload"]["allowed_actions"] == [
        "app.ensure_running",
        "app.dismiss_popups",
        "ui.click",
        "ui.long_click",
        "ui.swipe",
        "ui.key_press",
        "ui.wait_until",
        "ai.locate_point",
    ]
    assert "不要登录" in str(seen["payload"]["advanced_prompt"])
    config_path = Path(result.data["config_path"])
    assert config_path.exists()
    app_doc = config_path.read_text(encoding="utf-8")
    assert "app_id: demoapp" in app_doc
    assert "package_name: com.demo.app" in app_doc
