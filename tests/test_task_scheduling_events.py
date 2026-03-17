# pyright: reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import json
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from ai_services.llm_client import LLMResponse
from api.server import app
from core.model_trace_store import ModelTraceStore
from core.task_control import (
    TaskController,
    override_task_controller_for_tests,
    reset_task_controller_for_tests,
)
from core.task_events import TaskEventStore
from core.task_queue import InMemoryTaskQueue
from core.task_store import TaskStore
from engine.action_registry import ActionRegistry
from engine.agent_executor import AgentExecutorRuntime
from engine.models.runtime import ActionResult
from engine.runner import Runner


def _wait_status(client: TestClient, task_id: str, wanted: str, timeout_s: float = 6.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get(f"/api/tasks/{task_id}")
        if resp.status_code == 200 and resp.json().get("status") == wanted:
            return True
        time.sleep(0.05)
    return False


def _stream_task_events(client: TestClient, task_id: str) -> str:
    text = ""
    with client.stream("GET", f"/api/tasks/{task_id}/events") as resp:
        assert resp.status_code == 200
        for chunk in resp.iter_text():
            text += chunk
            if ": close" in text:
                break
    return text


def _sse_event_names(text: str) -> list[str]:
    return [
        line.removeprefix("event: ") for line in text.splitlines() if line.startswith("event: ")
    ]


class OrderRunner:
    def __init__(self) -> None:
        self.order: list[str] = []
        self._lock = threading.Lock()

    def run(self, script_payload, should_cancel=None, runtime=None):
        with self._lock:
            self.order.append(str(script_payload.get("label", "unknown")))
        return {"ok": True, "status": "completed", "message": "ok"}


class _SequencedLLMClient:
    def __init__(self, responses):
        self._responses = list(responses)

    def evaluate(self, request, *, runtime_config=None):
        if not self._responses:
            raise AssertionError("missing fake llm response")
        return self._responses.pop(0)


class _ExplodingTraceStore(ModelTraceStore):
    def append_record(self, context, record):
        _ = (context, record)
        raise RuntimeError("trace append exploded")


def _build_trace_runner(*, trace_store, observations=None):
    registry = ActionRegistry()
    observed = list(
        observations
        or [
            {"status": "matched", "state": {"state_id": "login_prompt"}},
            {"status": "matched", "state": {"state_id": "logged_in"}},
        ]
    )
    fallback_observation = dict(observed[-1])

    def _ui_match_state(params, context):
        current = observed.pop(0) if observed else fallback_observation
        return ActionResult(ok=True, code="ok", data=current)

    def _ui_click(params, context):
        return ActionResult(ok=True, code="ok", data={"clicked": params})

    registry.register("ui.match_state", _ui_match_state)
    registry.register("ui.click", _ui_click)
    llm_client = _SequencedLLMClient(
        [
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text='{"done": false, "action": "ui.click", "params": {"selector": "#continue"}}',
            ),
            LLMResponse(
                ok=True,
                request_id="req-2",
                provider="openai",
                model="gpt-5.4",
                output_text='{"done": true, "message": "executor completed"}',
            ),
        ]
    )
    runtime = AgentExecutorRuntime(
        registry=registry, llm_client_factory=lambda: llm_client, trace_store=trace_store
    )
    return Runner(agent_executor_runtime=runtime)


def test_run_at_delays_execution():
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        run_at = (datetime.now(UTC) + timedelta(seconds=1.5)).isoformat()
        create = client.post(
            "/api/tasks/",
            json={
                "script": {"task": "anonymous", "steps": []},
                "devices": [1],
                "ai_type": "volc",
                "priority": 50,
                "run_at": run_at,
                "max_retries": 0,
                "retry_backoff_seconds": 0,
            },
        )
        assert create.status_code == 200
        task_id = create.json()["task_id"]

        early = client.get(f"/api/tasks/{task_id}")
        assert early.status_code == 200
        assert early.json()["status"] == "pending"

        time.sleep(0.6)
        still_waiting = client.get(f"/api/tasks/{task_id}")
        assert still_waiting.status_code == 200
        assert still_waiting.json()["status"] == "pending"

        assert _wait_status(client, task_id, "completed", timeout_s=10.0)


def test_priority_prefers_higher_first_when_same_run_at(tmp_path: Path, monkeypatch):
    reset_task_controller_for_tests()
    monkeypatch.setenv("MYT_MAX_CONCURRENT_TASKS", "1")
    db_path = tmp_path / "tasks_priority_test.db"
    if db_path.exists():
        db_path.unlink()
    runner = OrderRunner()
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        runner=runner,
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            run_at = (datetime.now(UTC) + timedelta(seconds=1.2)).isoformat()
            low = client.post(
                "/api/tasks/",
                json={
                    "script": {"task": "anonymous", "steps": [], "label": "low"},
                    "devices": [1],
                    "ai_type": "volc",
                    "priority": 1,
                    "run_at": run_at,
                    "max_retries": 0,
                    "retry_backoff_seconds": 0,
                },
            )
            high = client.post(
                "/api/tasks/",
                json={
                    "script": {"task": "anonymous", "steps": [], "label": "high"},
                    "devices": [1],
                    "ai_type": "volc",
                    "priority": 99,
                    "run_at": run_at,
                    "max_retries": 0,
                    "retry_backoff_seconds": 0,
                },
            )
            assert low.status_code == 200
            assert high.status_code == 200
            low_id = low.json()["task_id"]
            high_id = high.json()["task_id"]

            assert _wait_status(client, low_id, "completed", timeout_s=6.0)
            assert _wait_status(client, high_id, "completed", timeout_s=6.0)
            assert runner.order[0] == "high"
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_task_events_sse_stream_contains_lifecycle_events(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_lifecycle_events.db"
    if db_path.exists():
        db_path.unlink()
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            create = client.post(
                "/api/tasks/",
                json={
                    "script": {"task": "anonymous", "steps": []},
                    "devices": [1],
                    "ai_type": "volc",
                    "priority": 50,
                    "max_retries": 0,
                    "retry_backoff_seconds": 0,
                },
            )
            assert create.status_code == 200
            task_id = create.json()["task_id"]

            text = _stream_task_events(client, task_id)
            event_names = _sse_event_names(text)

            assert event_names[:5] == [
                "task.created",
                "task.started",
                "task.dispatching",
                "task.dispatch_result",
                "task.completed",
            ]
            assert ": close" in text

            with sqlite3.connect(db_path) as conn:
                assert conn.execute(
                    "SELECT status FROM tasks WHERE task_id = ?", (task_id,)
                ).fetchone() == ("completed",)
                assert conn.execute(
                    "SELECT event_type FROM task_events WHERE task_id = ? ORDER BY event_id ASC",
                    (task_id,),
                ).fetchall() == [(name,) for name in event_names]
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_task_events_sse_stream_contains_retry_and_failed_terminal_events(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_retry_failed_events.db"
    if db_path.exists():
        db_path.unlink()
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            create = client.post(
                "/api/tasks/",
                json={
                    "script": {"task": "nonexistent_task"},
                    "devices": [1],
                    "ai_type": "volc",
                    "priority": 50,
                    "max_retries": 2,
                    "retry_backoff_seconds": 0,
                },
            )
            assert create.status_code == 200
            task_id = create.json()["task_id"]

            text = _stream_task_events(client, task_id)
            event_names = _sse_event_names(text)

            assert event_names == [
                "task.created",
                "task.started",
                "task.dispatching",
                "task.dispatch_result",
                "task.retry_scheduled",
                "task.started",
                "task.dispatching",
                "task.dispatch_result",
                "task.retry_scheduled",
                "task.started",
                "task.dispatching",
                "task.dispatch_result",
                "task.failed",
            ]
            assert event_names.count("task.retry_scheduled") == 2
            assert event_names.count("task.failed") == 1
            assert ": close" in text

            with sqlite3.connect(db_path) as conn:
                assert conn.execute(
                    "SELECT status, retry_count FROM tasks WHERE task_id = ?",
                    (task_id,),
                ).fetchone() == ("failed", 2)
                assert conn.execute(
                    "SELECT event_type FROM task_events WHERE task_id = ? ORDER BY event_id ASC",
                    (task_id,),
                ).fetchall() == [(name,) for name in event_names]
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_pending_task_cancel_emits_cancel_requested_and_cancelled_without_starting():
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        run_at = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        create = client.post(
            "/api/tasks/",
            json={
                "script": {"task": "anonymous", "steps": []},
                "devices": [1],
                "ai_type": "volc",
                "priority": 50,
                "run_at": run_at,
                "max_retries": 0,
                "retry_backoff_seconds": 0,
            },
        )
        assert create.status_code == 200
        task_id = create.json()["task_id"]

        cancel = client.post(f"/api/tasks/{task_id}/cancel")
        assert cancel.status_code == 200
        assert cancel.json()["cancelled"] is True
        assert cancel.json()["cancel_state"] == "cancelled"

        text = _stream_task_events(client, task_id)

        assert "event: task.created" in text
        assert "event: task.cancel_requested" in text
        assert "event: task.cancelled" in text
        assert "event: task.started" not in text
        assert "event: task.dispatching" not in text


def test_trace_managed_gpt_execution_persists_jsonl_without_raw_trace_events(tmp_path: Path):
    reset_task_controller_for_tests()
    monkey_db = tmp_path / "tasks_trace_success.db"
    if monkey_db.exists():
        monkey_db.unlink()
    trace_store = ModelTraceStore(root_dir=tmp_path / "config" / "data" / "traces")
    controller = TaskController(
        store=TaskStore(db_path=monkey_db),
        queue_backend=InMemoryTaskQueue(),
        runner=_build_trace_runner(trace_store=trace_store),
        event_store=TaskEventStore(db_path=monkey_db),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            create = client.post(
                "/api/tasks/",
                json={
                    "task": "agent_executor",
                    "payload": {
                        "goal": "dismiss login interstitial",
                        "expected_state_ids": ["account"],
                        "allowed_actions": ["ui.click"],
                        "max_steps": 4,
                    },
                    "targets": [{"device_id": 7, "cloud_id": 2}],
                    "ai_type": "volc",
                },
            )
            assert create.status_code == 200
            task_id = create.json()["task_id"]
            assert _wait_status(client, task_id, "completed", timeout_s=3.0)

            events = controller.list_events(task_id)
            event_types_list = [event.event_type for event in events]
            # Event sequence now includes task.observation and task.planning per step
            assert event_types_list[0] == "task.created"
            assert "task.started" in event_types_list
            assert "task.dispatching" in event_types_list
            assert "task.dispatch_result" in event_types_list
            assert "task.completed" in event_types_list
            assert all(
                "trace" not in json.dumps(event.payload, ensure_ascii=False).lower()
                for event in events
            )

            trace_root = tmp_path / "config" / "data" / "traces" / task_id / f"{task_id}-run-1"
            files = list(trace_root.glob("*.jsonl"))
            assert len(files) == 1
            records = [
                json.loads(line)
                for line in files[0].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            assert [record["sequence"] for record in records] == [1, 2]
            assert records[0]["record_type"] == "step"
            assert records[0]["observation"]["modality"] == "structured_state"
            assert records[0]["observation"]["observed_state_ids"] == ["login_prompt"]
            assert records[0]["chosen_action"] == "ui.click"
            assert records[0]["action_params"] == {"selector": "#continue"}
            assert records[0]["post_action_transition"]["next_observed_state_ids"] == ["logged_in"]
            assert records[1]["record_type"] == "terminal"
            assert records[1]["planner"]["response"]["request_id"] == "req-2"
    finally:
        reset_task_controller_for_tests()
        if monkey_db.exists():
            monkey_db.unlink()


def test_trace_persistence_failure_propagates_through_existing_task_failure_path(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_trace_failure.db"
    if db_path.exists():
        db_path.unlink()
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        runner=_build_trace_runner(trace_store=_ExplodingTraceStore(root_dir=tmp_path / "unused")),
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            create = client.post(
                "/api/tasks/",
                json={
                    "task": "agent_executor",
                    "payload": {
                        "goal": "dismiss login interstitial",
                        "expected_state_ids": ["account"],
                        "allowed_actions": ["ui.click"],
                        "max_steps": 4,
                    },
                    "targets": [{"device_id": 7, "cloud_id": 2}],
                    "ai_type": "volc",
                    "max_retries": 0,
                    "retry_backoff_seconds": 0,
                },
            )
            assert create.status_code == 200
            task_id = create.json()["task_id"]
            assert _wait_status(client, task_id, "failed", timeout_s=3.0)

            detail = client.get(f"/api/tasks/{task_id}")
            assert detail.status_code == 200
            assert detail.json()["status"] == "failed"
            assert detail.json()["error"] == "trace append exploded"

            event_types = [event.event_type for event in controller.list_events(task_id)]
            # Event sequence now includes task.observation and task.planning per step
            assert event_types[0] == "task.created"
            assert "task.started" in event_types
            assert "task.dispatching" in event_types
            assert "task.dispatch_result" in event_types
            assert "task.failed" in event_types
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_trace_managed_gpt_execution_uses_browser_observation_modality(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_trace_browser.db"
    if db_path.exists():
        db_path.unlink()
    trace_store = ModelTraceStore(root_dir=tmp_path / "config" / "data" / "traces")
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        runner=_build_trace_runner(
            trace_store=trace_store,
            observations=[
                {
                    "platform": "browser",
                    "status": "matched",
                    "state": {"state_id": "html:login_prompt"},
                    "raw_details": {
                        "observations": [
                            {"kind": "html", "target": "login_prompt", "matched": True}
                        ]
                    },
                },
                {
                    "platform": "browser",
                    "status": "matched",
                    "state": {"state_id": "url:home"},
                    "raw_details": {
                        "observations": [{"kind": "url", "target": "home", "matched": True}]
                    },
                },
            ],
        ),
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            create = client.post(
                "/api/tasks/",
                json={
                    "task": "agent_executor",
                    "payload": {
                        "goal": "dismiss browser interstitial",
                        "expected_state_ids": ["html:login_prompt"],
                        "allowed_actions": ["ui.click"],
                        "max_steps": 4,
                    },
                    "targets": [{"device_id": 7, "cloud_id": 2}],
                    "ai_type": "volc",
                },
            )
            assert create.status_code == 200
            task_id = create.json()["task_id"]
            assert _wait_status(client, task_id, "completed", timeout_s=3.0)

            trace_root = tmp_path / "config" / "data" / "traces" / task_id / f"{task_id}-run-1"
            files = list(trace_root.glob("*.jsonl"))
            assert len(files) == 1
            records = [
                json.loads(line)
                for line in files[0].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            assert records[0]["record_type"] == "step"
            assert records[0]["observation"]["modality"] == "browser_html"
            assert (
                records[0]["post_action_transition"]["next_observation_modality"] == "browser_url"
            )
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()
