# pyright: reportMissingImports=false, reportMissingModuleSource=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownLambdaType=false

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import cast
from urllib import request
from http.client import HTTPResponse

from fastapi.testclient import TestClient

from api.server import app
from core.task_control import TaskController, override_task_controller_for_tests, reset_task_controller_for_tests
from core.task_events import TaskEventStore
from core.task_queue import InMemoryTaskQueue
from core.task_store import TaskStore


def _assert_direct_run_response_has_no_managed_task_lifecycle_fields(payload: dict[str, object]) -> None:
    forbidden_fields = {
        "task_id",
        "retry_count",
        "max_retries",
        "retry_backoff_seconds",
        "next_retry_at",
        "queued_at",
        "started_at",
        "completed_at",
        "cancelled_at",
        "events_url",
        "metrics_url",
        "cancel_url",
    }
    assert forbidden_fields.isdisjoint(payload)


def test_runtime_execute_anonymous_stub():
    client = TestClient(app)
    response = client.post("/api/runtime/execute", json={"task": "anonymous", "steps": []})
    assert response.status_code == 200
    payload = cast(dict[str, object], response.json())
    assert payload["ok"] is True
    assert payload["status"] == "stub_executed"
    assert payload["task"] == "anonymous"
    _assert_direct_run_response_has_no_managed_task_lifecycle_fields(payload)


def test_runtime_execute_unsupported_task_returns_error():
    client = TestClient(app)
    response = client.post("/api/runtime/execute", json={"task": "nonexistent_task"})
    assert response.status_code == 200
    payload = cast(dict[str, object], response.json())
    assert payload["ok"] is False
    assert payload["status"] == "failed_config_error"
    assert payload["checkpoint"] == "dispatch"
    assert "unsupported task" in cast(str, payload["message"])


def test_runtime_execute_does_not_create_managed_task_record(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "runtime_execute_does_not_create_task.db"
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            before = client.get("/api/tasks/?limit=50")
            assert before.status_code == 200

            response = client.post("/api/runtime/execute", json={"task": "anonymous", "steps": []})
            assert response.status_code == 200
            payload = cast(dict[str, object], response.json())
            assert payload["ok"] is True
            assert payload["status"] == "stub_executed"
            _assert_direct_run_response_has_no_managed_task_lifecycle_fields(payload)

            after = client.get("/api/tasks/?limit=50")
            assert after.status_code == 200
            assert after.json() == before.json()
    finally:
        reset_task_controller_for_tests()


def test_runtime_execute_does_not_create_managed_task_metrics_artifacts(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "runtime_execute_does_not_create_metrics.db"
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            before = client.get("/api/tasks/metrics?window_seconds=86400")
            assert before.status_code == 200
            before_payload = cast(dict[str, object], before.json())

            response = client.post("/api/runtime/execute", json={"task": "anonymous", "steps": []})
            assert response.status_code == 200
            direct_payload = cast(dict[str, object], response.json())
            assert direct_payload["ok"] is True

            after = client.get("/api/tasks/metrics?window_seconds=86400")
            assert after.status_code == 200
            after_payload = cast(dict[str, object], after.json())
            comparable_keys = (
                "window_seconds",
                "status_counts",
                "event_type_counts",
                "terminal_outcomes",
                "rates",
                "alerts",
            )
            assert {key: before_payload[key] for key in comparable_keys} == {
                key: after_payload[key] for key in comparable_keys
            }
    finally:
        reset_task_controller_for_tests()


def test_runtime_execute_openapi_marks_route_as_debug_only_direct_run():
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200

    openapi_payload = cast(dict[str, object], response.json())
    paths = cast(dict[str, object], openapi_payload["paths"])
    runtime_path = cast(dict[str, object], paths["/api/runtime/execute"])
    execute_route = cast(dict[str, object], runtime_path["post"])
    assert execute_route["summary"] == "Debug-only direct runtime execute"
    description = cast(str, execute_route["description"])
    assert "debug" in description.lower()
    assert "returns the raw runner result" in description.lower()
    assert "without creating managed task records" in description.lower()
    assert "synchronously" in description.lower()
    assert "retries" in description.lower()
    assert "cancellation flow" in description.lower()
    assert "sse task events" in description.lower()
    assert "task metrics artifacts" in description.lower()
    assert "exclusive to /api/tasks" in description.lower()
    assert "/api/tasks" in description


def test_runtime_execute_can_dispatch_migrated_dm_reply_plugin_actions(monkeypatch):
    from engine.actions import state_actions, ui_actions
    from engine.models.runtime import ActionResult

    class FakeRpc:
        def init(self, ip, port, timeout):
            _ = (ip, port, timeout)
            return True

        def close(self):
            return None

        def dump_node_xml_ex(self, work_mode, timeout_ms):
            _ = (work_mode, timeout_ms)
            return "<hierarchy />"

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

        def touchClick(self, finger_id, x, y):
            _ = (finger_id, x, y)
            return True

    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)
    monkeypatch.setattr(ui_actions, "app_ensure_running", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "exec_command", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "selector_click_one", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "input_text", lambda params, context: ActionResult(ok=True, code="ok"))

    client = TestClient(app)
    response = client.post(
        "/api/runtime/execute",
        json={
            "task": "dm_reply",
            "device_ip": "192.168.1.2",
            "reply_text": "hello dm",
        },
    )
    assert response.status_code == 200
    payload = cast(dict[str, object], response.json())
    assert payload["ok"] is True
    assert payload["status"] == "success"
    assert payload["task"] == "dm_reply"


def test_action_registry_is_initialized_in_fresh_process_without_runner() -> None:
    project_root = Path(__file__).resolve().parents[1]
    script = (
        "from engine.action_registry import get_registry\n"
        "print(get_registry().has('ui.focus_and_input_with_shell_fallback'))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "True"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return cast(int, sock.getsockname()[1])


def test_runtime_execute_live_uvicorn_path_dispatches_migrated_plugin_actions() -> None:
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
                response = cast(HTTPResponse, request.urlopen(health_url, timeout=1))
                try:
                    if response.status == 200:
                        break
                finally:
                    response.close()
            except Exception:
                time.sleep(0.1)
        else:
            proc.terminate()
            stdout, stderr = proc.communicate(timeout=5)
            raise AssertionError(f"uvicorn did not become healthy\nstdout:\n{stdout}\nstderr:\n{stderr}")

        runtime_request = request.Request(
            f"http://127.0.0.1:{port}/api/runtime/execute",
            data=json.dumps(
                {
                    "task": "x_mobile_login",
                    "device_ip": "192.168.1.2",
                    "status_hint": "success",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        response = cast(HTTPResponse, request.urlopen(runtime_request, timeout=10))
        try:
            payload = cast(dict[str, object], json.loads(response.read().decode("utf-8")))
        finally:
            response.close()

        assert payload["ok"] is True
        assert payload["status"] == "success"
        assert payload["task"] == "x_mobile_login"
        assert payload.get("code") != "unknown_action"
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                _ = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                _ = proc.communicate(timeout=5)
