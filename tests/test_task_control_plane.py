# pyright: reportMissingImports=false
import json
import os
import sqlite3
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import request as urllib_request

from fastapi.testclient import TestClient

from api.server import app
from core.task_control import TaskController, override_task_controller_for_tests, reset_task_controller_for_tests
from core.task_events import TaskEventStore
from core.task_queue import InMemoryTaskQueue
from core.task_store import ManagedTaskStateClearBlocked, TaskStore
from engine.action_registry import ActionRegistry
from engine.agent_executor import AgentExecutorRuntime
from engine.models.runtime import ActionResult
from engine.runner import Runner
from ai_services.llm_client import LLMResponse


def _wait_status(client: TestClient, task_id: str, timeout_s: float = 3.0) -> str:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get(f"/api/tasks/{task_id}")
        assert resp.status_code == 200
        status = resp.json()["status"]
        if status in {"completed", "failed", "cancelled"}:
            return status
        time.sleep(0.05)
    return "timeout"


def _wait_event(controller: TaskController, task_id: str, event_type: str, timeout_s: float = 3.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if any(event.event_type == event_type for event in controller.list_events(task_id)):
            return True
        time.sleep(0.05)
    return False


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _SequencedLLMClient:
    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def evaluate(self, request, *, runtime_config=None):
        self.calls.append({"request": request, "runtime_config": runtime_config})
        if self._responses:
            return self._responses.pop(0)
        return LLMResponse(
            ok=True,
            request_id="req-default",
            provider="openai",
            model="gpt-5.4",
            output_text=json.dumps({"done": True, "message": "default complete"}),
        )


def _build_agent_executor_runner(*, llm_client: _SequencedLLMClient, stagnant_state_id: str = "account") -> Runner:
    registry = ActionRegistry()

    def _ui_match_state(params, context):
        _ = (params, context)
        return ActionResult(
            ok=True,
            code="ok",
            data={
                "operation": "match_state",
                "status": "matched",
                "state": {"state_id": stagnant_state_id},
                "expected_state_ids": [stagnant_state_id],
            },
        )

    def _ui_click(params, context):
        _ = context
        return ActionResult(ok=True, code="ok", data={"clicked": params})

    registry.register("ui.match_state", _ui_match_state)
    registry.register("ui.click", _ui_click)
    return Runner(
        agent_executor_runtime=AgentExecutorRuntime(
            registry=registry,
            llm_client_factory=lambda: llm_client,
        )
    )


def test_task_control_plane_success_flow():
    os.environ["MYT_TASK_QUEUE_BACKEND"] = "memory"
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        create = client.post(
            "/api/tasks/",
            json={
                "script": {"task": "anonymous", "steps": []},
                "devices": [1],
                "ai_type": "volc",
            },
        )
        assert create.status_code == 200
        task_id = create.json()["task_id"]

        status = _wait_status(client, task_id)
        assert status == "completed"

        detail = client.get(f"/api/tasks/{task_id}")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["status"] == "completed"
        assert payload["result"]["ok"] is True


def test_task_control_plane_agent_executor_managed_lifecycle_and_cancel_support(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_agent_executor_control_plane_test.db"
    if db_path.exists():
        db_path.unlink()

    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": False, "action": "ui.click", "params": {"selector": "#continue"}}),
            ),
            LLMResponse(
                ok=True,
                request_id="req-2",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "executor completed"}),
            ),
        ]
    )
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        runner=_build_agent_executor_runner(llm_client=llm_client),
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
                },
            )
            assert create.status_code == 200
            created = create.json()
            task_id = created["task_id"]
            assert created["task_name"] == "agent_executor"

            listing = client.get("/api/tasks/?limit=50")
            assert listing.status_code == 200
            assert any(item["task_id"] == task_id for item in listing.json())

            assert _wait_status(client, task_id, timeout_s=30.0) == "completed"

            detail = client.get(f"/api/tasks/{task_id}")
            assert detail.status_code == 200
            payload = detail.json()
            assert payload["status"] == "completed"
            assert payload["result"]["ok"] is True
            assert payload["result"]["task"] == "agent_executor"
            target_result = payload["result"]["targets"][0]["result"]
            assert target_result["step_count"] == 1
            assert target_result["history"][0]["action"] == "ui.click"

            event_types = [event.event_type for event in controller.list_events(task_id)]
            # Event sequence now includes task.observation and task.planning per step
            assert event_types[0] == "task.created"
            assert "task.started" in event_types
            assert "task.dispatching" in event_types
            assert "task.dispatch_result" in event_types
            assert "task.completed" in event_types

            cancel_create = client.post(
                "/api/tasks/",
                json={
                    "task": "agent_executor",
                    "payload": {
                        "goal": "wait for later",
                        "expected_state_ids": ["account"],
                        "allowed_actions": ["ui.click"],
                    },
                    "targets": [{"device_id": 7, "cloud_id": 2}],
                    "ai_type": "volc",
                    "run_at": "2999-01-01T00:00:00+00:00",
                },
            )
            assert cancel_create.status_code == 200
            cancel_task_id = cancel_create.json()["task_id"]

            cancel = client.post(f"/api/tasks/{cancel_task_id}/cancel")
            assert cancel.status_code == 200
            assert cancel.json()["cancelled"] is True

            cancelled_detail = client.get(f"/api/tasks/{cancel_task_id}")
            assert cancelled_detail.status_code == 200
            assert cancelled_detail.json()["status"] == "cancelled"

            cancel_event_types = [event.event_type for event in controller.list_events(cancel_task_id)]
            assert cancel_event_types == ["task.created", "task.cancel_requested", "task.cancelled"]
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_invalid_agent_executor_payload_fails_with_machine_readable_error(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_invalid_agent_executor_control_plane_test.db"
    if db_path.exists():
        db_path.unlink()

    llm_client = _SequencedLLMClient(responses=[])
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        runner=_build_agent_executor_runner(llm_client=llm_client),
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
                        "goal": "missing action contract",
                        "expected_state_ids": ["account"],
                    },
                    "targets": [{"device_id": 7, "cloud_id": 2}],
                    "ai_type": "volc",
                    "max_retries": 0,
                    "retry_backoff_seconds": 0,
                },
            )
            assert create.status_code == 200
            task_id = create.json()["task_id"]

            assert _wait_status(client, task_id, timeout_s=3.0) == "failed"

            detail = client.get(f"/api/tasks/{task_id}")
            assert detail.status_code == 200
            payload = detail.json()
            assert payload["status"] == "failed"
            assert payload["error"] == "agent_executor requires allowed_actions"
            assert payload["result"]["ok"] is False
            assert payload["result"]["status"] == "failed_config_error"
            target_result = payload["result"]["targets"][0]["result"]
            assert target_result["code"] == "invalid_params"
            assert target_result["checkpoint"] == "dispatch"
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_agent_executor_live_uvicorn_tasks_path_uses_default_runner_wiring() -> None:
    reset_task_controller_for_tests()
    project_root = Path(__file__).resolve().parents[1]
    port = _find_free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=project_root,
        env={**os.environ, "MYT_ENABLE_RPC": "0"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        health_url = f"http://127.0.0.1:{port}/health"
        for _ in range(50):
            if proc.poll() is not None:
                stdout, stderr = proc.communicate(timeout=5)
                raise AssertionError(f"uvicorn exited early\nstdout:\n{stdout}\nstderr:\n{stderr}")
            try:
                live = urllib_request.urlopen(health_url, timeout=1)
                try:
                    if live.status == 200:
                        break
                finally:
                    live.close()
            except Exception:
                time.sleep(0.1)
        else:
            proc.terminate()
            stdout, stderr = proc.communicate(timeout=5)
            raise AssertionError(f"uvicorn did not become healthy\nstdout:\n{stdout}\nstderr:\n{stderr}")

        create_request = urllib_request.Request(
            f"http://127.0.0.1:{port}/api/tasks/",
            data=json.dumps(
                {
                    "task": "agent_executor",
                    "payload": {
                        "goal": "exercise live default wiring",
                        "expected_state_ids": ["account"],
                    },
                    "targets": [{"device_id": 1, "cloud_id": 1}],
                    "ai_type": "volc",
                    "max_retries": 0,
                    "retry_backoff_seconds": 0,
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        create_response = urllib_request.urlopen(create_request, timeout=10)
        try:
            created = json.loads(create_response.read().decode("utf-8"))
        finally:
            create_response.close()

        task_id = created["task_id"]
        detail_payload: dict[str, object] = {}
        deadline = time.time() + 5.0
        while time.time() < deadline:
            detail_response = urllib_request.urlopen(f"http://127.0.0.1:{port}/api/tasks/{task_id}", timeout=10)
            try:
                detail_payload = json.loads(detail_response.read().decode("utf-8"))
            finally:
                detail_response.close()
            if detail_payload.get("status") in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.1)

        assert detail_payload["status"] == "failed"
        assert detail_payload["task_name"] == "agent_executor"
        assert detail_payload["error"] == "agent_executor requires allowed_actions"

        result_payload = detail_payload["result"]
        assert isinstance(result_payload, dict)
        assert result_payload["status"] == "failed_config_error"
        assert "unsupported task: agent_executor" not in json.dumps(detail_payload, ensure_ascii=False)
    finally:
        reset_task_controller_for_tests()
        if proc.poll() is None:
            proc.terminate()
            try:
                _ = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                _ = proc.communicate(timeout=5)


class _RecordingManagedRunner:
    def __init__(self):
        self.calls = []

    def run(self, script_payload, should_cancel=None, runtime=None):
        self.calls.append({"script_payload": dict(script_payload), "runtime": dict(runtime or {})})
        return {"ok": True, "status": "completed", "message": "done"}


def test_managed_task_submission_uses_api_surface_and_managed_execution_lifecycle(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_managed_lifecycle_test.db"
    if db_path.exists():
        db_path.unlink()

    runner = _RecordingManagedRunner()
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        runner=runner,
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            controller.stop()

            create = client.post(
                "/api/tasks/",
                json={
                    "task": "anonymous",
                    "payload": {"foo": "bar"},
                    "targets": [{"device_id": 7, "cloud_id": 2}],
                    "ai_type": "volc",
                },
            )
            assert create.status_code == 200
            task_id = create.json()["task_id"]

            dequeued = controller._queue.dequeue(timeout_seconds=1)
            assert dequeued == task_id
            controller._execution_service._process_task(task_id)

            assert _wait_event(controller, task_id, "task.completed", timeout_s=3.0)
            assert _wait_status(client, task_id, timeout_s=3.0) == "completed"

            assert len(runner.calls) == 1
            assert runner.calls[0]["script_payload"] == {"task": "anonymous", "foo": "bar"}
            runtime = runner.calls[0]["runtime"]
            assert runtime["task_id"] == task_id
            assert runtime["cloud_target"] == "Unit #7-2"
            assert runtime["target"] == {"device_id": 7, "cloud_id": 2}
            assert "emit_event" in runtime

            event_types = [event.event_type for event in controller.list_events(task_id)]
            # Event sequence now includes task.observation and task.planning per step
            assert event_types[0] == "task.created"
            assert "task.started" in event_types
            assert "task.dispatching" in event_types
            assert "task.dispatch_result" in event_types
            assert "task.completed" in event_types
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_task_control_plane_failed_flow():
    os.environ["MYT_TASK_QUEUE_BACKEND"] = "memory"
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        create = client.post(
            "/api/tasks/",
            json={
                "script": {"task": "nonexistent_task"},
                "devices": [1],
                "ai_type": "volc",
                "max_retries": 0,
                "retry_backoff_seconds": 0,
            },
        )
        assert create.status_code == 200
        task_id = create.json()["task_id"]

        status = _wait_status(client, task_id)
        assert status == "failed"

        detail = client.get(f"/api/tasks/{task_id}")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["status"] == "failed"
        assert payload["retry_count"] == 0
        assert "unsupported task" in (payload.get("error") or "")


class _WrongPasswordRunner:
    def run(self, script_payload, should_cancel=None, runtime=None):
        return {"ok": False, "status": "failed", "message": "wrong password provided"}


class _RecordingAccountFeedback:
    def __init__(self):
        self.calls = []

    def handle_terminal_failure(self, payload, error):
        self.calls.append({"payload": payload, "error": error})


def test_task_controller_routes_terminal_failure_through_account_feedback_hook(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_account_feedback_hook_test.db"
    if db_path.exists():
        db_path.unlink()

    account_feedback = _RecordingAccountFeedback()
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        runner=_WrongPasswordRunner(),
        event_store=TaskEventStore(db_path=db_path),
        account_feedback=account_feedback,
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            create = client.post(
                "/api/tasks/",
                json={
                    "script": {
                        "task": "anonymous",
                        "steps": [],
                        "credentials_ref": json.dumps({"account": "alice@example.com"}),
                    },
                    "devices": [1],
                    "ai_type": "volc",
                    "max_retries": 0,
                    "retry_backoff_seconds": 0,
                },
            )
            assert create.status_code == 200
            task_id = create.json()["task_id"]

            assert _wait_status(client, task_id, timeout_s=3.0) == "failed"
            assert len(account_feedback.calls) == 1
            assert account_feedback.calls[0]["payload"]["credentials_ref"] == json.dumps({"account": "alice@example.com"})
            assert account_feedback.calls[0]["error"] == "wrong password provided"
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_task_control_plane_retries_then_fails():
    os.environ["MYT_TASK_QUEUE_BACKEND"] = "memory"
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        create = client.post(
            "/api/tasks/",
            json={
                "script": {"task": "nonexistent_task"},
                "devices": [1],
                "ai_type": "volc",
                "max_retries": 2,
                "retry_backoff_seconds": 0,
            },
        )
        assert create.status_code == 200
        task_id = create.json()["task_id"]

        status = _wait_status(client, task_id, timeout_s=5.0)
        assert status == "failed"

        detail = client.get(f"/api/tasks/{task_id}")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["status"] == "failed"
        assert payload["retry_count"] == 2
        assert payload["max_retries"] == 2
        assert payload["retry_backoff_seconds"] == 0


def test_task_control_plane_create_returns_retry_metadata():
    os.environ["MYT_TASK_QUEUE_BACKEND"] = "memory"
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        create = client.post(
            "/api/tasks/",
            json={
                "script": {"task": "anonymous", "steps": []},
                "devices": [1],
                "ai_type": "volc",
                "max_retries": 3,
                "retry_backoff_seconds": 1,
            },
        )
        assert create.status_code == 200
        payload = create.json()
        assert payload["retry_count"] == 0
        assert payload["max_retries"] == 3
        assert payload["retry_backoff_seconds"] == 1


def test_task_control_plane_list_contains_created_task():
    os.environ["MYT_TASK_QUEUE_BACKEND"] = "memory"
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        create = client.post(
            "/api/tasks/",
            json={
                "script": {"task": "anonymous", "steps": []},
                "devices": [1],
                "ai_type": "volc",
            },
        )
        assert create.status_code == 200
        task_id = create.json()["task_id"]

        listing = client.get("/api/tasks/?limit=50")
        assert listing.status_code == 200
        ids = {item["task_id"] for item in listing.json()}
        assert task_id in ids




def test_task_control_plane_rejects_managed_submit_without_targets_or_devices():
    os.environ["MYT_TASK_QUEUE_BACKEND"] = "memory"
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        response = client.post(
            "/api/tasks/",
            json={
                "task": "named-task",
                "payload": {"foo": "bar"},
                "ai_type": "volc",
            },
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert any("either targets or devices must be provided" in str(item.get("msg", "")) for item in detail)


def test_task_control_plane_devices_input_is_normalized_to_explicit_targets():
    os.environ["MYT_TASK_QUEUE_BACKEND"] = "memory"
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        response = client.post(
            "/api/tasks/",
            json={
                "task": "named-task",
                "payload": {"foo": "bar"},
                "devices": [3, 3, 5],
                "ai_type": "volc",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["devices"] == [3, 5]
        assert payload["targets"] == [
            {"device_id": 3, "cloud_id": 1},
            {"device_id": 5, "cloud_id": 1},
        ]


def test_task_controller_rejects_submit_without_targets_or_devices(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_missing_targets_service_test.db"
    if db_path.exists():
        db_path.unlink()

    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        event_store=TaskEventStore(db_path=db_path),
    )

    try:
        try:
            controller.submit_with_retry(
                payload={"task": "anonymous", "steps": []},
                devices=[],
                targets=None,
                ai_type="volc",
                max_retries=0,
                retry_backoff_seconds=0,
                priority=50,
                run_at=None,
            )
            raise AssertionError("submit_with_retry should reject missing targets/devices")
        except ValueError as exc:
            assert str(exc) == "either targets or devices must be provided"
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_task_control_plane_rejects_conflicting_devices_and_targets():
    os.environ["MYT_TASK_QUEUE_BACKEND"] = "memory"
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        response = client.post(
            "/api/tasks/",
            json={
                "task": "named-task",
                "payload": {"foo": "bar"},
                "devices": [3],
                "targets": [{"device_id": 5, "cloud_id": 1}],
                "ai_type": "volc",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "devices and targets must refer to the same device set"


def test_task_control_plane_targets_drive_canonical_devices_even_with_duplicates():
    os.environ["MYT_TASK_QUEUE_BACKEND"] = "memory"
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        response = client.post(
            "/api/tasks/",
            json={
                "task": "named-task",
                "payload": {"foo": "bar"},
                "targets": [
                    {"device_id": 3, "cloud_id": 2},
                    {"device_id": 3, "cloud_id": 4},
                    {"device_id": 5, "cloud_id": 1},
                ],
                "ai_type": "volc",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["devices"] == [3, 5]
        assert payload["targets"] == [
            {"device_id": 3, "cloud_id": 2},
            {"device_id": 3, "cloud_id": 4},
            {"device_id": 5, "cloud_id": 1},
        ]


def test_task_control_plane_clear_route_clears_managed_tasks_and_events(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_clear_managed_state_test.db"
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
                    "task": "named-task",
                    "payload": {"foo": "bar"},
                    "targets": [{"device_id": 3, "cloud_id": 2}],
                    "ai_type": "volc",
                    "run_at": "2999-01-01T00:00:00+00:00",
                },
            )
            assert create.status_code == 200
            task_id = create.json()["task_id"]
            assert controller.list_events(task_id)

            with sqlite3.connect(db_path) as conn:
                assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone() == (1,)
                assert conn.execute("SELECT COUNT(*) FROM task_events").fetchone() == (1,)
                assert conn.execute("SELECT task_id, event_type FROM task_events").fetchone() == (task_id, "task.created")

            cleared = client.delete("/api/tasks/")
            assert cleared.status_code == 200
            assert cleared.json() == {"status": "ok", "message": "managed task state cleared"}
            assert client.get("/api/tasks/?limit=50").json() == []
            assert controller.list_events(task_id) == []

            with sqlite3.connect(db_path) as conn:
                assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone() == (0,)
                assert conn.execute("SELECT COUNT(*) FROM task_events").fetchone() == (0,)
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_task_controller_clear_all_blocks_when_running_tasks_exist(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_clear_blocked_running_test.db"
    if db_path.exists():
        db_path.unlink()

    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        event_store=TaskEventStore(db_path=db_path),
    )

    try:
        created = controller.submit_with_retry(
            payload={"task": "anonymous", "steps": []},
            devices=[1],
            targets=None,
            ai_type="volc",
            max_retries=0,
            retry_backoff_seconds=0,
            priority=50,
            run_at=None,
        )
        assert controller._store.mark_running(created.task_id) is True

        try:
            controller.clear_all()
            raise AssertionError("clear_all should block while tasks are running")
        except ManagedTaskStateClearBlocked as exc:
            assert str(exc) == "cannot clear managed task state while tasks are running"

        assert controller.get(created.task_id) is not None
        assert controller.list_events(created.task_id)
        with sqlite3.connect(db_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone() == (1,)
            assert conn.execute("SELECT COUNT(*) FROM task_events").fetchone() == (1,)
            assert conn.execute("SELECT status FROM tasks WHERE task_id = ?", (created.task_id,)).fetchone() == ("running",)
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_task_control_plane_clear_route_rejects_when_running_tasks_exist(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_clear_route_blocked_running_test.db"
    if db_path.exists():
        db_path.unlink()

    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    try:
        created = controller.submit_with_retry(
            payload={"task": "anonymous", "steps": []},
            devices=[1],
            targets=None,
            ai_type="volc",
            max_retries=0,
            retry_backoff_seconds=0,
            priority=50,
            run_at=None,
        )
        assert controller._store.mark_running(created.task_id) is True

        with TestClient(app) as client:
            response = client.delete("/api/tasks/")

        assert response.status_code == 409
        assert response.json()["detail"] == "cannot clear managed task state while tasks are running"
        assert controller.get(created.task_id) is not None
        assert [event.event_type for event in controller.list_events(created.task_id)] == ["task.created"]
        with sqlite3.connect(db_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone() == (1,)
            assert conn.execute("SELECT COUNT(*) FROM task_events").fetchone() == (1,)
            assert conn.execute("SELECT status FROM tasks WHERE task_id = ?", (created.task_id,)).fetchone() == ("running",)
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_task_control_plane_create_list_detail_share_task_mapping():
    os.environ["MYT_TASK_QUEUE_BACKEND"] = "memory"
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        run_at = "2999-01-01T00:00:00+00:00"
        normalized_run_at = "2999-01-01T00:00:00Z"
        create = client.post(
            "/api/tasks/",
            json={
                "task": "named-task",
                "payload": {"foo": "bar"},
                "targets": [
                    {"device_id": 3, "cloud_id": 2},
                    {"device_id": 3, "cloud_id": 4},
                ],
                "ai_type": "volc",
                "max_retries": 2,
                "retry_backoff_seconds": 5,
                "priority": 80,
                "run_at": run_at,
            },
        )
        assert create.status_code == 200
        created = create.json()

        assert created["task_name"] == "named-task"
        assert created["devices"] == [3]
        assert created["targets"] == [{"device_id": 3, "cloud_id": 2}, {"device_id": 3, "cloud_id": 4}]
        assert created["status"] == "pending"
        assert created["max_retries"] == 2
        assert created["retry_backoff_seconds"] == 5
        assert created["priority"] == 80
        assert created["run_at"] == normalized_run_at

        task_id = created["task_id"]

        listing = client.get("/api/tasks/?limit=50")
        assert listing.status_code == 200
        listed = next(item for item in listing.json() if item["task_id"] == task_id)

        assert listed["task_name"] == created["task_name"]
        assert listed["devices"] == created["devices"]
        assert listed["targets"] == created["targets"]
        assert listed["run_at"] == normalized_run_at

        detail = client.get(f"/api/tasks/{task_id}")
        assert detail.status_code == 200
        detailed = detail.json()

        assert detailed["task_name"] == created["task_name"]
        assert detailed["devices"] == created["devices"]
        assert detailed["targets"] == created["targets"]
        assert detailed["run_at"] == normalized_run_at
        assert detailed["error"] is None


def test_duplicate_submit_with_same_idempotency_key_returns_same_task(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_idempotency_duplicate_submit_test.db"
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
            request = {
                "script": {"task": "anonymous", "steps": []},
                "devices": [1],
                "ai_type": "volc",
                "idempotency_key": "dup-key-1",
                "run_at": "2999-01-01T00:00:00+00:00",
                "max_retries": 0,
                "retry_backoff_seconds": 0,
            }
            first = client.post("/api/tasks/", json=request)
            second = client.post("/api/tasks/", json=request)

            assert first.status_code == 200
            assert second.status_code == 200
            assert first.json()["task_id"] == second.json()["task_id"]

            listing = client.get("/api/tasks/?limit=100")
            assert listing.status_code == 200
            ids = [item["task_id"] for item in listing.json()]
            assert ids.count(first.json()["task_id"]) == 1
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_idempotency_key_dedupes_pending_task_across_controller_restart(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_idempotency_restart_test.db"
    if db_path.exists():
        db_path.unlink()

    try:
        first_controller = TaskController(
            store=TaskStore(db_path=db_path),
            queue_backend=InMemoryTaskQueue(),
            event_store=TaskEventStore(db_path=db_path),
        )
        override_task_controller_for_tests(first_controller)

        with TestClient(app) as client:
            request = {
                "script": {"task": "anonymous", "steps": []},
                "devices": [1],
                "ai_type": "volc",
                "idempotency_key": "restart-key-1",
                "run_at": "2999-01-01T00:00:00+00:00",
                "max_retries": 0,
                "retry_backoff_seconds": 0,
            }
            first = client.post("/api/tasks/", json=request)
            assert first.status_code == 200
            first_id = first.json()["task_id"]

            restarted_controller = TaskController(
                store=TaskStore(db_path=db_path),
                queue_backend=InMemoryTaskQueue(),
                event_store=TaskEventStore(db_path=db_path),
            )
            override_task_controller_for_tests(restarted_controller)

            second = client.post("/api/tasks/", json=request)
            assert second.status_code == 200
            assert second.json()["task_id"] == first_id
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_idempotency_key_dedupes_running_task_across_controller_restart(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_idempotency_running_restart_test.db"
    if db_path.exists():
        db_path.unlink()

    try:
        first_store = TaskStore(db_path=db_path)
        first_controller = TaskController(
            store=first_store,
            queue_backend=InMemoryTaskQueue(),
            event_store=TaskEventStore(db_path=db_path),
        )
        override_task_controller_for_tests(first_controller)

        created = first_controller.submit_with_retry(
            payload={"task": "anonymous", "steps": []},
            devices=[1],
            targets=None,
            ai_type="volc",
            max_retries=1,
            retry_backoff_seconds=1,
            priority=50,
            run_at=None,
            idempotency_key="restart-running-key-1",
        )
        assert first_store.mark_running(created.task_id) is True

        restarted_controller = TaskController(
            store=TaskStore(db_path=db_path),
            queue_backend=InMemoryTaskQueue(),
            event_store=TaskEventStore(db_path=db_path),
        )
        override_task_controller_for_tests(restarted_controller)

        duplicate = restarted_controller.submit_with_retry(
            payload={"task": "anonymous", "steps": []},
            devices=[1],
            targets=None,
            ai_type="volc",
            max_retries=1,
            retry_backoff_seconds=1,
            priority=50,
            run_at=None,
            idempotency_key="restart-running-key-1",
        )
        assert duplicate.task_id == created.task_id
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_idempotency_key_dedupes_retry_scheduled_task_across_controller_restart(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_idempotency_retry_window_restart_test.db"
    if db_path.exists():
        db_path.unlink()

    try:
        first_store = TaskStore(db_path=db_path)
        first_controller = TaskController(
            store=first_store,
            queue_backend=InMemoryTaskQueue(),
            event_store=TaskEventStore(db_path=db_path),
        )
        override_task_controller_for_tests(first_controller)

        created = first_controller.submit_with_retry(
            payload={"task": "anonymous", "steps": []},
            devices=[1],
            targets=None,
            ai_type="volc",
            max_retries=2,
            retry_backoff_seconds=60,
            priority=50,
            run_at=None,
            idempotency_key="restart-retry-key-1",
        )

        retry_record = first_store.schedule_retry(created.task_id, error="forced retry for idempotency test")
        assert retry_record is not None
        assert retry_record.status == "pending"
        assert retry_record.next_retry_at is not None

        restarted_controller = TaskController(
            store=TaskStore(db_path=db_path),
            queue_backend=InMemoryTaskQueue(),
            event_store=TaskEventStore(db_path=db_path),
        )
        override_task_controller_for_tests(restarted_controller)

        duplicate = restarted_controller.submit_with_retry(
            payload={"task": "anonymous", "steps": []},
            devices=[1],
            targets=None,
            ai_type="volc",
            max_retries=2,
            retry_backoff_seconds=60,
            priority=50,
            run_at=None,
            idempotency_key="restart-retry-key-1",
        )
        assert duplicate.task_id == created.task_id
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_stale_running_task_recovered_and_requeued_on_controller_start(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_stale_running_recovery_test.db"
    if db_path.exists():
        db_path.unlink()

    previous_stale = os.environ.get("MYT_TASK_STALE_RUNNING_SECONDS")
    os.environ["MYT_TASK_STALE_RUNNING_SECONDS"] = "0"

    try:
        first_store = TaskStore(db_path=db_path)
        first_controller = TaskController(
            store=first_store,
            queue_backend=InMemoryTaskQueue(),
            event_store=TaskEventStore(db_path=db_path),
        )
        override_task_controller_for_tests(first_controller)

        created = first_controller.submit_with_retry(
            payload={"task": "anonymous", "steps": []},
            devices=[1],
            targets=None,
            ai_type="volc",
            max_retries=0,
            retry_backoff_seconds=0,
            priority=50,
            run_at=None,
            idempotency_key="stale-running-key-1",
        )
        assert first_store.mark_running(created.task_id) is True

        restarted_controller = TaskController(
            store=TaskStore(db_path=db_path),
            queue_backend=InMemoryTaskQueue(),
            runner=_ImmediateSuccessRunner(),
            event_store=TaskEventStore(db_path=db_path),
        )
        override_task_controller_for_tests(restarted_controller)
        restarted_controller.start()

        deadline = time.time() + 3.0
        final_status = "running"
        while time.time() < deadline:
            record = restarted_controller.get(created.task_id)
            assert record is not None
            final_status = record.status
            if final_status == "completed":
                break
            time.sleep(0.05)

        assert final_status == "completed"

        events = restarted_controller.list_events(created.task_id)
        assert any(ev.event_type == "task.recovered_stale_running" for ev in events)
    finally:
        reset_task_controller_for_tests()
        if previous_stale is None:
            os.environ.pop("MYT_TASK_STALE_RUNNING_SECONDS", None)
        else:
            os.environ["MYT_TASK_STALE_RUNNING_SECONDS"] = previous_stale
        if db_path.exists():
            db_path.unlink()


class _ImmediateSuccessRunner:
    def run(self, script_payload, should_cancel=None, runtime=None):
        return {"ok": True, "status": "completed", "message": "done"}


def test_same_idempotency_key_allows_new_task_after_terminal_state(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_idempotency_terminal_test.db"
    if db_path.exists():
        db_path.unlink()

    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        runner=_ImmediateSuccessRunner(),
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            first = client.post(
                "/api/tasks/",
                json={
                    "script": {"task": "anonymous", "steps": []},
                    "devices": [1],
                    "ai_type": "volc",
                    "idempotency_key": "dup-key-2",
                },
            )
            assert first.status_code == 200
            first_id = first.json()["task_id"]
            assert _wait_status(client, first_id, timeout_s=3.0) == "completed"

            second = client.post(
                "/api/tasks/",
                json={
                    "script": {"task": "anonymous", "steps": []},
                    "devices": [1],
                    "ai_type": "volc",
                    "idempotency_key": "dup-key-2",
                },
            )
            assert second.status_code == 200
            assert second.json()["task_id"] != first_id
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_idempotency_key_can_be_supplied_via_header():
    os.environ["MYT_TASK_QUEUE_BACKEND"] = "memory"
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        request = {
            "script": {"task": "anonymous", "steps": []},
            "devices": [1],
            "ai_type": "volc",
            "run_at": "2999-01-01T00:00:00+00:00",
            "max_retries": 0,
            "retry_backoff_seconds": 0,
        }
        first = client.post("/api/tasks/", json=request, headers={"X-Idempotency-Key": "header-key-1"})
        second = client.post("/api/tasks/", json=request, headers={"X-Idempotency-Key": "header-key-1"})

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["task_id"] == second.json()["task_id"]
        assert first.json()["idempotency_key"] == "header-key-1"


def test_conflicting_body_and_header_idempotency_key_rejected():
    os.environ["MYT_TASK_QUEUE_BACKEND"] = "memory"
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        request = {
            "script": {"task": "anonymous", "steps": []},
            "devices": [1],
            "ai_type": "volc",
            "idempotency_key": "body-key",
        }
        response = client.post("/api/tasks/", json=request, headers={"X-Idempotency-Key": "header-key"})

        assert response.status_code == 400
        assert "idempotency key mismatch" in response.json().get("detail", "")


def test_task_metrics_aggregates_status_and_event_counts(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_metrics_test.db"
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
            success = client.post(
                "/api/tasks/",
                json={
                    "script": {"task": "anonymous", "steps": []},
                    "devices": [1],
                    "ai_type": "volc",
                    "max_retries": 0,
                    "retry_backoff_seconds": 0,
                },
            )
            failed = client.post(
                "/api/tasks/",
                json={
                    "script": {"task": "nonexistent_task"},
                    "devices": [1],
                    "ai_type": "volc",
                    "max_retries": 0,
                    "retry_backoff_seconds": 0,
                },
            )
            cancelled = client.post(
                "/api/tasks/",
                json={
                    "script": {"task": "anonymous", "steps": []},
                    "devices": [1],
                    "ai_type": "volc",
                    "run_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                    "max_retries": 0,
                    "retry_backoff_seconds": 0,
                },
            )

            assert success.status_code == 200
            assert failed.status_code == 200
            assert cancelled.status_code == 200

            assert _wait_status(client, success.json()["task_id"], timeout_s=5.0) == "completed"
            assert _wait_status(client, failed.json()["task_id"], timeout_s=5.0) == "failed"

            cancel_resp = client.post(f"/api/tasks/{cancelled.json()['task_id']}/cancel")
            assert cancel_resp.status_code == 200
            assert cancel_resp.json()["cancelled"] is True

            metrics = client.get("/api/tasks/metrics?window_seconds=86400")
            assert metrics.status_code == 200
            payload = metrics.json()

            assert payload["window_seconds"] == 86400
            assert payload["status_counts"].get("completed", 0) >= 1
            assert payload["status_counts"].get("failed", 0) >= 1
            assert payload["status_counts"].get("cancelled", 0) >= 1

            assert payload["event_type_counts"].get("task.created", 0) >= 3
            assert payload["terminal_outcomes"].get("completed", 0) >= 1
            assert payload["terminal_outcomes"].get("failed", 0) >= 1
            assert payload["terminal_outcomes"].get("cancelled", 0) >= 1
            assert payload["alerts"]["evaluated"] is False
            assert payload["alerts"]["triggered"] is False

            evaluated_metrics = client.get(
                "/api/tasks/metrics?window_seconds=86400&failure_rate_threshold=0.2&cancellation_rate_threshold=0.2&min_terminal_samples=1"
            )
            assert evaluated_metrics.status_code == 200
            evaluated_payload = evaluated_metrics.json()
            assert evaluated_payload["alerts"]["evaluated"] is True
            assert evaluated_payload["alerts"]["triggered"] is True
            assert "failure_rate" in evaluated_payload["rates"]
            assert "cancellation_rate" in evaluated_payload["rates"]
            assert "completion_rate" in evaluated_payload["rates"]
            assert len(evaluated_payload["alerts"].get("reasons", [])) >= 1

            prometheus_metrics = client.get(
                "/api/tasks/metrics/prometheus?window_seconds=86400&failure_rate_threshold=0.2&cancellation_rate_threshold=0.2&min_terminal_samples=1"
            )
            assert prometheus_metrics.status_code == 200
            body = prometheus_metrics.text
            assert "# TYPE new_task_status_count gauge" in body
            assert "new_task_status_count{status=\"completed\"}" in body
            assert "new_task_terminal_outcome_total{outcome=\"failed\"}" in body
            assert "new_task_failure_rate " in body
            assert "new_task_alert_triggered 1" in body
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()
