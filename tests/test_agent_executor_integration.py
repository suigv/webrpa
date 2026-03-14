# pyright: reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

from ai_services.llm_client import LLMError, LLMResponse, retry_backoff_seconds
from core.model_trace_store import ModelTraceStore
from engine.action_registry import ActionRegistry
from engine.agent_executor import AgentExecutorRuntime
from engine.models.runtime import ActionResult


class _SequencedLLMClient:
    def __init__(self, responses: list[LLMResponse]):
        self._responses: list[LLMResponse] = list(responses)
        self.calls: list[dict[str, object]] = []

    def evaluate(self, request, *, runtime_config=None):
        self.calls.append({"request": request, "runtime_config": runtime_config})
        if not self._responses:
            raise AssertionError("missing fake llm response")
        return self._responses.pop(0)


def _build_runtime(
    *,
    llm_client: _SequencedLLMClient,
    observations: list[ActionResult | Mapping[str, object]],
    trace_store: ModelTraceStore | None = None,
    extra_actions: dict[str, Callable[..., ActionResult]] | None = None,
) -> AgentExecutorRuntime:
    registry = ActionRegistry()
    observed: list[ActionResult] = [_coerce_action_result(item) for item in observations]
    fallback_observation = observed[-1]

    def _ui_match_state(params, context):
        _ = (params, context)
        return observed.pop(0) if observed else fallback_observation

    def _ui_click(params, context):
        _ = context
        return ActionResult(ok=True, code="ok", data={"clicked": params})

    registry.register("ui.match_state", _ui_match_state)
    registry.register("ui.click", _ui_click)
    for action_name, handler in (extra_actions or {}).items():
        registry.register(action_name, handler)
    return AgentExecutorRuntime(registry=registry, llm_client_factory=lambda: llm_client, trace_store=trace_store)


def _coerce_action_result(item: ActionResult | Mapping[str, object]) -> ActionResult:
    if isinstance(item, ActionResult):
        return item
    payload = {str(key): value for key, value in item.items()}
    return ActionResult(
        ok=bool(payload.get("ok", True)),
        code=str(payload.get("code", "ok") or "ok"),
        message=str(payload.get("message", "") or ""),
        data=cast(dict[str, object], payload.get("data") or payload),
    )


def _trace_runtime_args() -> dict[str, object]:
    return {
        "task_id": "task-gpt-executor",
        "run_id": "task-gpt-executor-run-1",
        "cloud_target": "device-1-cloud-1",
        "target": {"device_id": 1, "cloud_id": 1},
    }


def _read_trace_records(trace_root: Path) -> list[dict[str, object]]:
    files = list(trace_root.rglob("*.jsonl"))
    assert len(files) == 1
    return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines() if line.strip()]


def test_agent_executor_circuit_breaker_step_budget_exhausted(tmp_path: Path):
    trace_store = ModelTraceStore(root_dir=tmp_path / "traces")
    runtime = _build_runtime(
        llm_client=_SequencedLLMClient(
            responses=[
                LLMResponse(ok=True, request_id="req-1", provider="openai", model="gpt-5.4", output_text=json.dumps({"action": "ui.click", "params": {}})),
                LLMResponse(ok=True, request_id="req-2", provider="openai", model="gpt-5.4", output_text=json.dumps({"action": "ui.click", "params": {}})),
            ]
        ),
        observations=[
            {"platform": "native", "state": {"state_id": "account-1"}, "status": "matched"},
            {"platform": "native", "state": {"state_id": "account-2"}, "status": "matched"},
        ],
        trace_store=trace_store,
    )

    result = runtime.run(
        {
            "task": "agent_executor",
            "goal": "keep trying until budget ends",
            "expected_state_ids": ["account"],
            "allowed_actions": ["ui.click"],
            "max_steps": 2,
            "stagnant_limit": 10,
        },
        runtime=_trace_runtime_args(),
    )

    assert result["ok"] is False
    assert result["status"] == "failed_circuit_breaker"
    assert result["code"] == "step_budget_exhausted"
    assert result["step_count"] == 2
    assert result["circuit_breaker"] == {"code": "step_budget_exhausted", "max_steps": 2}
    records = _read_trace_records(tmp_path / "traces")
    assert [record["record_type"] for record in records] == ["step", "step", "terminal"]
    assert records[-1]["code"] == "step_budget_exhausted"
    assert records[-1]["status"] == "failed_circuit_breaker"


def test_agent_executor_circuit_breaker_stagnant_state_abort():
    observation = {"state": {"state_id": "account"}, "status": "matched"}
    runtime = _build_runtime(
        llm_client=_SequencedLLMClient(
            responses=[
                LLMResponse(ok=True, request_id="req-1", provider="openai", model="gpt-5.4", output_text=json.dumps({"action": "ui.click", "params": {}})),
                LLMResponse(ok=True, request_id="req-2", provider="openai", model="gpt-5.4", output_text=json.dumps({"action": "ui.click", "params": {}})),
            ]
        ),
        observations=[observation, observation, observation],
    )

    result = runtime.run(
        {
            "task": "agent_executor",
            "goal": "abort on stagnant state",
            "expected_state_ids": ["account"],
            "allowed_actions": ["ui.click"],
            "max_steps": 5,
            "stagnant_limit": 1,
        }
    )

    assert result["ok"] is False
    assert result["status"] == "failed_circuit_breaker"
    assert result["code"] == "stagnant_structured_state"
    assert result["checkpoint"] == "observe"
    assert result["circuit_breaker"]["code"] == "stagnant_structured_state"
    assert result["circuit_breaker"]["stagnant_limit"] == 1


def test_agent_executor_collects_fallback_evidence_into_planner_and_trace(tmp_path: Path):
    trace_store = ModelTraceStore(root_dir=tmp_path / "traces")

    def _dump_node_xml_ex(params, context):
        _ = (params, context)
        return ActionResult(ok=True, code="ok", data={"xml": "<hierarchy><node text='Retry'/></hierarchy>"})

    def _capture_compressed(params, context):
        _ = (params, context)
        return ActionResult(ok=True, code="ok", data={"byte_length": 321, "save_path": None})

    runtime = _build_runtime(
        llm_client=_SequencedLLMClient(
            responses=[
                LLMResponse(
                    ok=True,
                    request_id="req-fallback",
                    provider="openai",
                    model="gpt-5.4",
                    output_text=json.dumps({"done": True, "message": "need fallback evidence"}),
                )
            ]
        ),
        observations=[
            ActionResult(
                ok=False,
                code="no_match",
                message="state missing",
                data={
                    "platform": "native",
                    "state": {"state_id": "unknown"},
                    "status": "no_match",
                    "expected_state_ids": ["account"],
                    "raw_details": {"probe": "primary"},
                },
            )
        ],
        trace_store=trace_store,
        extra_actions={
            "ui.dump_node_xml_ex": _dump_node_xml_ex,
            "device.capture_compressed": _capture_compressed,
        },
    )

    result = runtime.run(
        {
            "task": "agent_executor",
            "goal": "inspect fallback evidence",
            "expected_state_ids": ["account"],
            "allowed_actions": ["ui.click"],
            "max_steps": 1,
            "fallback_modalities": ["xml", "screenshot"],
        },
        runtime=_trace_runtime_args(),
    )

    assert result["ok"] is True
    records = _read_trace_records(tmp_path / "traces")
    assert len(records) == 1
    record = records[0]
    fallback_evidence = cast(dict[str, object], record["fallback_evidence"])
    planner = cast(dict[str, object], record["planner"])
    ui_xml = cast(dict[str, object], fallback_evidence["ui_xml"])
    screen_capture = cast(dict[str, object], fallback_evidence["screen_capture"])
    screen_capture_metadata = cast(dict[str, object], screen_capture["metadata"])
    assert record["record_type"] == "terminal"
    assert record["fallback_reason"] == "observation_not_ok"
    assert "save_path" in ui_xml or "content" in ui_xml
    if "save_path" in ui_xml:
        assert str(ui_xml["save_path"]).endswith(".xml")
    else:
        assert str(ui_xml["content"]).startswith("<hierarchy>")
    assert screen_capture_metadata["byte_length"] == 321
    planner_request = cast(dict[str, object], planner["request"])
    planner_prompt = cast(dict[str, object], json.loads(cast(str, planner_request["prompt"])))
    planner_fallback_evidence = cast(dict[str, object], planner_prompt["fallback_evidence"])
    planner_ui_xml = cast(dict[str, object], planner_fallback_evidence["ui_xml"])
    planner_screen_capture = cast(dict[str, object], planner_fallback_evidence["screen_capture"])
    assert "save_path" in planner_ui_xml or "content" in planner_ui_xml
    planner_screen_capture_metadata = cast(dict[str, object], planner_screen_capture["metadata"])
    assert planner_screen_capture_metadata["byte_length"] == 321
    assert str(screen_capture_metadata["save_path"]).endswith(".png")
    assert planner_screen_capture_metadata["save_path"] == screen_capture_metadata["save_path"]


def test_agent_executor_retryable_planner_error_is_retried_with_backoff(monkeypatch):
    sleep_calls: list[float] = []
    curr_time = 1000.0

    def _fake_sleep(duration: float) -> None:
        nonlocal curr_time
        sleep_calls.append(duration)
        curr_time += duration

    monkeypatch.setattr("engine.agent_executor.time.sleep", _fake_sleep)
    monkeypatch.setattr("engine.agent_executor.time.monotonic", lambda: curr_time)
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=False,
                request_id="req-retryable-1",
                provider="openai",
                model="gpt-5.4",
                error=LLMError(
                    code="provider_http_error",
                    message="temporary upstream failure",
                    provider_status=503,
                    retryable=True,
                ),
            ),
            LLMResponse(
                ok=False,
                request_id="req-retryable-2",
                provider="openai",
                model="gpt-5.4",
                error=LLMError(
                    code="provider_http_error",
                    message="temporary upstream failure",
                    provider_status=503,
                    retryable=True,
                ),
            ),
            LLMResponse(
                ok=False,
                request_id="req-retryable-3",
                provider="openai",
                model="gpt-5.4",
                error=LLMError(
                    code="provider_http_error",
                    message="temporary upstream failure",
                    provider_status=503,
                    retryable=True,
                ),
            ),
        ]
    )
    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[{"platform": "native", "state": {"state_id": "account"}, "status": "matched"}],
    )

    result = runtime.run(
        {
            "task": "agent_executor",
            "goal": "observe retryable planner errors",
            "expected_state_ids": ["account"],
            "allowed_actions": ["ui.click"],
            "max_steps": 3,
        }
    )

    assert result["ok"] is False
    assert result["status"] == "failed_runtime_error"
    assert result["checkpoint"] == "planning"
    assert result["code"] == "provider_http_error"
    assert result["step_count"] == 0
    planner = cast(dict[str, object], result["planner"])
    planner_error = cast(dict[str, object], cast(dict[str, object], planner["response"])["error"])
    assert planner_error["retryable"] is True
    assert len(llm_client.calls) == 3
    assert sum(sleep_calls) == (retry_backoff_seconds(0) + retry_backoff_seconds(1))


def test_agent_executor_repeated_actions_without_stagnation_only_hit_step_budget():
    repeated_plan = LLMResponse(
        ok=True,
        request_id="req-repeat",
        provider="openai",
        model="gpt-5.4",
        output_text=json.dumps({"action": "ui.click", "params": {"x": 10, "y": 20}}),
    )
    runtime = _build_runtime(
        llm_client=_SequencedLLMClient(responses=[repeated_plan, repeated_plan, repeated_plan]),
        observations=[
            {"platform": "native", "state": {"state_id": "account-1"}, "status": "matched"},
            {"platform": "native", "state": {"state_id": "account-2"}, "status": "matched"},
            {"platform": "native", "state": {"state_id": "account-3"}, "status": "matched"},
        ],
    )

    result = runtime.run(
        {
            "task": "agent_executor",
            "goal": "surface repeated planner action loops",
            "expected_state_ids": ["account"],
            "allowed_actions": ["ui.click"],
            "max_steps": 3,
            "stagnant_limit": 10,
        }
    )

    assert result["ok"] is False
    assert result["status"] == "failed_circuit_breaker"
    assert result["code"] == "step_budget_exhausted"
    assert result["checkpoint"] == "loop"
    history = cast(list[dict[str, object]], result["history"])
    assert [entry["action"] for entry in history] == ["ui.click", "ui.click", "ui.click"]
    assert [entry["params"] for entry in history] == [{"x": 10, "y": 20}] * 3


def test_agent_executor_cancellation_writes_terminal_trace_record(tmp_path: Path):
    trace_store = ModelTraceStore(root_dir=tmp_path / "traces")
    runtime = _build_runtime(
        llm_client=_SequencedLLMClient(
            responses=[
                LLMResponse(ok=True, request_id="req-1", provider="openai", model="gpt-5.4", output_text=json.dumps({"action": "ui.click", "params": {}}))
            ]
        ),
        observations=[{"platform": "native", "state": {"state_id": "account"}, "status": "matched"}],
        trace_store=trace_store,
    )

    cancel_state = {"calls": 0}

    def _should_cancel() -> bool:
        cancel_state["calls"] += 1
        return cancel_state["calls"] >= 2

    result = runtime.run(
        {
            "task": "agent_executor",
            "goal": "cancel after action",
            "expected_state_ids": ["account"],
            "allowed_actions": ["ui.click"],
            "max_steps": 3,
        },
        should_cancel=_should_cancel,
        runtime=_trace_runtime_args(),
    )

    assert result["status"] == "cancelled"
    records = _read_trace_records(tmp_path / "traces")
    assert [record["record_type"] for record in records] == ["step", "terminal"]
    assert records[-1]["status"] == "cancelled"
    assert records[-1]["code"] == "task_cancelled"
