# pyright: reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

from ai_services.llm_client import LLMError, LLMRequest, LLMResponse, retry_backoff_seconds
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
    wait_observations: list[ActionResult | Mapping[str, object]] | None = None,
    trace_store: ModelTraceStore | None = None,
    extra_actions: dict[str, Callable[..., ActionResult]] | None = None,
) -> AgentExecutorRuntime:
    registry = ActionRegistry()
    observed: list[ActionResult] = [_coerce_action_result(item) for item in observations]
    fallback_observation = observed[-1]
    waited: list[ActionResult] | None = (
        [_coerce_action_result(item) for item in wait_observations]
        if wait_observations is not None
        else None
    )
    fallback_wait_observation = waited[-1] if waited else fallback_observation

    def _ui_match_state(params, context):
        _ = (params, context)
        return observed.pop(0) if observed else fallback_observation

    def _ui_wait_until(params, context):
        _ = (params, context)
        if waited is None:
            return observed.pop(0) if observed else fallback_observation
        return waited.pop(0) if waited else fallback_wait_observation

    def _ui_observe_transition(params, context):
        _ = (params, context)
        if waited is None:
            return observed.pop(0) if observed else fallback_observation
        return waited.pop(0) if waited else fallback_wait_observation

    def _ui_click(params, context):
        _ = context
        return ActionResult(ok=True, code="ok", data={"clicked": params})

    registry.register("ui.match_state", _ui_match_state)
    registry.register("ui.wait_until", _ui_wait_until)
    registry.register("ui.observe_transition", _ui_observe_transition)
    registry.register("ui.click", _ui_click)
    for action_name, handler in (extra_actions or {}).items():
        registry.register(action_name, handler)
    return AgentExecutorRuntime(
        registry=registry, llm_client_factory=lambda: llm_client, trace_store=trace_store
    )


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
    return [
        json.loads(line)
        for line in files[0].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_agent_executor_circuit_breaker_step_budget_exhausted(tmp_path: Path):
    trace_store = ModelTraceStore(root_dir=tmp_path / "traces")
    runtime = _build_runtime(
        llm_client=_SequencedLLMClient(
            responses=[
                LLMResponse(
                    ok=True,
                    request_id="req-1",
                    provider="openai",
                    model="gpt-5.4",
                    output_text=json.dumps({"action": "ui.click", "params": {}}),
                ),
                LLMResponse(
                    ok=True,
                    request_id="req-2",
                    provider="openai",
                    model="gpt-5.4",
                    output_text=json.dumps({"action": "ui.click", "params": {}}),
                ),
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
    assert result["circuit_breaker"]["code"] == "step_budget_exhausted"
    assert result["circuit_breaker"]["max_steps"] == 2
    assert result["circuit_breaker"]["effective_max_steps"] == 2
    assert result["circuit_breaker"]["step_budget_extensions_used"] == 0
    assert result["circuit_breaker"]["extended_steps_total"] == 0
    records = _read_trace_records(tmp_path / "traces")
    assert [record["record_type"] for record in records] == ["step", "step", "terminal"]
    assert records[-1]["code"] == "step_budget_exhausted"
    assert records[-1]["status"] == "failed_circuit_breaker"


def test_agent_executor_circuit_breaker_stagnant_state_abort():
    observation = {"state": {"state_id": "account"}, "status": "matched"}
    runtime = _build_runtime(
        llm_client=_SequencedLLMClient(
            responses=[
                LLMResponse(
                    ok=True,
                    request_id="req-1",
                    provider="openai",
                    model="gpt-5.4",
                    output_text=json.dumps({"action": "ui.click", "params": {}}),
                ),
                LLMResponse(
                    ok=True,
                    request_id="req-2",
                    provider="openai",
                    model="gpt-5.4",
                    output_text=json.dumps({"action": "ui.click", "params": {}}),
                ),
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


def test_agent_executor_allows_follow_up_after_successful_locate_point_on_same_screen():
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps(
                    {"action": "ai.locate_point", "params": {"prompt": "find login"}}
                ),
            ),
            LLMResponse(
                ok=True,
                request_id="req-2",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"action": "ui.click", "params": {"x": 10, "y": 20}}),
            ),
            LLMResponse(
                ok=True,
                request_id="req-3",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "entered login form"}),
            ),
        ]
    )

    def _locate_point(params, context):
        _ = (params, context)
        return ActionResult(ok=True, code="ok", data={"x": 10, "y": 20})

    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "login_entry"},
                "status": "no_match",
                "ok": False,
            },
            {
                "platform": "native",
                "state": {"state_id": "login_entry"},
                "status": "no_match",
                "ok": False,
            },
            {"platform": "native", "state": {"state_id": "home"}, "status": "matched", "ok": True},
        ],
        extra_actions={"ai.locate_point": _locate_point},
    )

    result = runtime.run(
        {
            "goal": "enter login form",
            "expected_state_ids": ["home"],
            "allowed_actions": ["ai.locate_point", "ui.click"],
            "max_steps": 5,
            "stagnant_limit": 1,
        }
    )

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert len(llm_client.calls) == 3


def test_agent_executor_ensures_target_app_running_before_observation():
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "ready"}),
            ),
        ]
    )
    app_calls: list[dict[str, object]] = []

    def _app_ensure_running(params, context):
        _ = context
        app_calls.append(dict(params))
        return ActionResult(ok=True, code="ok")

    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "account"},
                "status": "matched",
                "ok": True,
            }
        ],
        extra_actions={"app.ensure_running": _app_ensure_running},
    )

    result = runtime.run(
        {
            "goal": "open target app first",
            "package": "com.twitter.android",
            "expected_state_ids": ["account"],
            "allowed_actions": ["ui.click"],
            "max_steps": 1,
            "stagnant_limit": 1,
        }
    )

    assert result["ok"] is True
    assert app_calls == [{"package": "com.twitter.android", "verify_timeout": 1.5}]


def test_agent_executor_includes_login_payload_inputs_in_planner_prompt():
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "ready"}),
            ),
        ]
    )

    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "account"},
                "status": "matched",
                "ok": True,
            }
        ],
    )

    result = runtime.run(
        {
            "goal": "login",
            "acc": "demo_user",
            "pwd": "demo_pass",
            "two_factor_code": "123456",
            "expected_state_ids": ["account"],
            "allowed_actions": ["ui.click"],
            "max_steps": 1,
            "stagnant_limit": 1,
        }
    )

    assert result["ok"] is True
    planner_prompt = json.loads(cast(LLMRequest, llm_client.calls[0]["request"]).prompt)
    assert planner_prompt["payload"] == {
        "acc": "demo_user",
        "pwd": "demo_pass",
        "two_factor_code": "123456",
    }


def test_agent_executor_triggers_learning_hook_after_completed_trace(monkeypatch, tmp_path: Path):
    trace_store = ModelTraceStore(root_dir=tmp_path / "traces")
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "ready"}),
            ),
        ]
    )

    def _app_ensure_running(params, context):
        _ = (params, context)
        return ActionResult(ok=True, code="ok")

    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "home"},
                "status": "matched",
                "ok": True,
                "package": "com.twitter.android",
            }
        ],
        trace_store=trace_store,
        extra_actions={"app.ensure_running": _app_ensure_running},
    )

    hook_calls: list[dict[str, object]] = []

    def _fake_hook(trace_context, package_name):
        records = trace_store.read_records(trace_context)
        hook_calls.append(
            {
                "package": package_name,
                "terminal_status": records[-1]["status"],
                "record_types": [record["record_type"] for record in records],
            }
        )

    monkeypatch.setattr(runtime, "_trigger_learning_hook", _fake_hook)

    result = runtime.run(
        {
            "goal": "finish task",
            "package": "com.twitter.android",
            "expected_state_ids": ["home"],
            "allowed_actions": ["ui.click"],
            "max_steps": 1,
            "stagnant_limit": 1,
        },
        runtime=_trace_runtime_args(),
    )

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert hook_calls == [
        {
            "package": "com.twitter.android",
            "terminal_status": "completed",
            "record_types": ["terminal"],
        }
    ]


def test_agent_executor_auto_submits_login_field_after_input():
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps(
                    {"action": "ui.input_text", "params": {"text": "demo_user"}}
                ),
            ),
            LLMResponse(
                ok=True,
                request_id="req-2",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "moved on"}),
            ),
        ]
    )
    key_calls: list[dict[str, object]] = []

    def _key_press(params, context):
        _ = context
        key_calls.append(dict(params))
        return ActionResult(ok=True, code="ok", data={"key": params.get("key")})

    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "account"},
                "status": "matched",
                "ok": True,
            },
            {
                "platform": "native",
                "state": {"state_id": "account"},
                "status": "matched",
                "ok": True,
            },
            {
                "platform": "native",
                "state": {"state_id": "password"},
                "status": "matched",
                "ok": True,
            },
        ],
        extra_actions={
            "ui.key_press": _key_press,
            "ui.input_text": lambda p, c: ActionResult(ok=True, code="ok"),
        },
    )

    result = runtime.run(
        {
            "goal": "login",
            "expected_state_ids": ["account", "password"],
            "allowed_actions": ["ui.input_text", "ui.key_press"],
            "max_steps": 3,
            "stagnant_limit": 2,
        }
    )

    assert result["ok"] is True
    assert key_calls == [{"key": "enter"}]
    assert len(llm_client.calls) == 2


def test_agent_executor_observes_transition_after_submit_keypress():
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps(
                    {"action": "ui.input_text", "params": {"text": "demo_user"}}
                ),
            ),
            LLMResponse(
                ok=True,
                request_id="req-2",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "moved to password"}),
            ),
        ]
    )
    transition_calls: list[dict[str, object]] = []

    def _key_press(params, context):
        _ = context
        return ActionResult(ok=True, code="ok", data={"key": params.get("key")})

    def _ui_observe_transition(params, context):
        _ = context
        transition_calls.append(dict(params))
        return ActionResult(
            ok=True,
            code="ok",
            data={
                "platform": "native",
                "state": {"state_id": "password"},
                "status": "transition_observed",
                "transition": {
                    "from_state": {"state_id": "account"},
                    "to_state": {"state_id": "password"},
                    "changed": True,
                },
            },
        )

    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "account"},
                "status": "matched",
                "ok": True,
            },
            {
                "platform": "native",
                "state": {"state_id": "account"},
                "status": "matched",
                "ok": True,
            },
        ],
        wait_observations=[
            {
                "platform": "native",
                "state": {"state_id": "password"},
                "status": "matched",
                "ok": True,
            }
        ],
        extra_actions={
            "ui.key_press": _key_press,
            "ui.input_text": lambda p, c: ActionResult(ok=True, code="ok"),
            "ui.observe_transition": _ui_observe_transition,
        },
    )

    result = runtime.run(
        {
            "goal": "login",
            "expected_state_ids": ["account", "password"],
            "allowed_actions": ["ui.input_text", "ui.key_press"],
            "max_steps": 3,
            "stagnant_limit": 2,
        }
    )

    assert result["ok"] is True
    assert transition_calls == [
        {
            "expected_state_ids": ["account", "password"],
            "from_state_ids": ["account"],
            "to_state_ids": ["password"],
            "timeout_ms": 2500,
            "interval_ms": 300,
        }
    ]
    second_prompt = json.loads(cast(LLMRequest, llm_client.calls[1]["request"]).prompt)
    assert second_prompt["observation"]["state"]["state_id"] == "password"


def test_agent_executor_does_not_offer_ui_observe_transition_to_planner():
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "planner inspected actions"}),
            )
        ]
    )

    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "password"},
                "status": "no_match",
                "ok": False,
            }
        ],
        extra_actions={
            "ai.locate_point": lambda p, c: ActionResult(ok=True, code="ok", data={"x": 1, "y": 2})
        },
    )

    result = runtime.run(
        {
            "goal": "login",
            "expected_state_ids": ["account", "password", "two_factor"],
            "allowed_actions": ["ai.locate_point", "ui.click", "ui.observe_transition"],
            "max_steps": 1,
            "stagnant_limit": 1,
        }
    )

    assert result["ok"] is True
    prompt = json.loads(cast(LLMRequest, llm_client.calls[0]["request"]).prompt)
    assert prompt["allowed_actions"] == ["ai.locate_point", "ui.click"]


def test_agent_executor_rewrites_fallback_password_locate_query_toward_input_field():
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"action": "ui.click", "params": {"x": 50, "y": 60}}),
            ),
            LLMResponse(
                ok=True,
                request_id="req-2",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps(
                    {"action": "ai.locate_point", "params": {"query": "登录或继续按钮"}}
                ),
            ),
            LLMResponse(
                ok=True,
                request_id="req-3",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "query corrected"}),
            ),
        ]
    )
    locate_calls: list[dict[str, object]] = []

    def _locate_point(params, context):
        _ = context
        locate_calls.append(dict(params))
        return ActionResult(ok=True, code="ok", data={"x": 200, "y": 740})

    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "account"},
                "status": "matched",
                "ok": True,
            },
            {
                "platform": "native",
                "state": {"state_id": "password"},
                "status": "no_match",
                "ok": False,
            },
            {
                "platform": "native",
                "state": {"state_id": "password"},
                "status": "no_match",
                "ok": False,
            },
        ],
        extra_actions={
            "ai.locate_point": _locate_point,
            "ui.input_text": lambda p, c: ActionResult(ok=True, code="ok"),
        },
    )

    result = runtime.run(
        {
            "goal": "login",
            "expected_state_ids": ["account", "password", "two_factor"],
            "allowed_actions": ["ai.locate_point", "ui.click", "ui.input_text"],
            "max_steps": 3,
            "stagnant_limit": 3,
        }
    )

    assert result["ok"] is True
    assert locate_calls == [
        {
            "query": (
                "密码输入页面中的密码输入框或密码文本框区域。"
                "优先返回输入框中心点，不要返回登录/继续按钮。"
            )
        }
    ]


def test_agent_executor_preserves_submit_target_locate_query_after_enter_on_account_page():
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps(
                    {"action": "ui.input_text", "params": {"text": "demo_user"}}
                ),
            ),
            LLMResponse(
                ok=True,
                request_id="req-2",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "submit target preserved"}),
            ),
        ]
    )
    locate_calls: list[dict[str, object]] = []

    def _locate_point(params, context):
        _ = context
        locate_calls.append(dict(params))
        return ActionResult(ok=True, code="ok", data={"x": 930, "y": 1813})

    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "account"},
                "status": "matched",
                "ok": True,
            },
            {
                "platform": "native",
                "state": {"state_id": "account"},
                "status": "matched",
                "ok": True,
            },
            {
                "platform": "native",
                "state": {"state_id": "account"},
                "status": "no_match",
                "ok": False,
            },
            {
                "platform": "native",
                "state": {"state_id": "password"},
                "status": "matched",
                "ok": True,
            },
        ],
        wait_observations=[
            {
                "platform": "native",
                "state": {"state_id": "account"},
                "status": "transition_timeout",
                "ok": False,
            }
        ],
        extra_actions={
            "ai.locate_point": _locate_point,
            "ui.input_text": lambda p, c: ActionResult(ok=True, code="ok"),
            "ui.key_press": lambda p, c: ActionResult(ok=True, code="ok", data={"key": "enter"}),
        },
    )

    result = runtime.run(
        {
            "goal": "login",
            "expected_state_ids": ["account", "password"],
            "allowed_actions": ["ai.locate_point", "ui.click", "ui.input_text", "ui.key_press"],
            "max_steps": 4,
            "stagnant_limit": 4,
        }
    )

    assert result["ok"] is True
    assert len(llm_client.calls) == 2
    assert locate_calls == [
        {
            "query": (
                "当前页面中用于提交已填写标识字段并推进流程的主操作控件。"
                "优先返回页面主按钮、键盘动作键或明显的前进控件中心点，不要返回输入框。"
            )
        }
    ]
    assert result["history"][2]["action"] == "ui.click"


def test_agent_executor_normalizes_goal_param_for_locate_point():
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps(
                    {"action": "ai.locate_point", "params": {"goal": "登录按钮"}}
                ),
            ),
            LLMResponse(
                ok=True,
                request_id="req-2",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "goal normalized"}),
            ),
        ]
    )
    locate_calls: list[dict[str, object]] = []

    def _locate_point(params, context):
        _ = context
        locate_calls.append(dict(params))
        return ActionResult(ok=True, code="ok", data={"x": 100, "y": 200})

    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "login_entry"},
                "status": "no_match",
                "ok": False,
            },
            {
                "platform": "native",
                "state": {"state_id": "login_entry"},
                "status": "no_match",
                "ok": False,
            },
        ],
        extra_actions={"ai.locate_point": _locate_point},
    )

    result = runtime.run(
        {
            "goal": "login",
            "expected_state_ids": ["login_entry", "account"],
            "allowed_actions": ["ai.locate_point"],
            "max_steps": 2,
            "stagnant_limit": 2,
        }
    )

    assert result["ok"] is True
    assert locate_calls == [{"goal": "登录按钮", "query": "登录按钮"}]


def test_agent_executor_uses_saved_fallback_xml_for_stagnation_fingerprint(tmp_path: Path):
    trace_store = ModelTraceStore(root_dir=tmp_path / "traces")
    xml_payloads = [
        '<hierarchy bounds="[0,0][1080,1920]"><node class="android.widget.EditText" /></hierarchy>',
        (
            '<hierarchy bounds="[0,0][1080,1920]"><node class="android.widget.EditText" '
            'password="true" resource-id="com.example:id/password" /></hierarchy>'
        ),
    ]

    def _dump_node_xml_ex(params, context):
        _ = (params, context)
        xml = xml_payloads.pop(0)
        return ActionResult(ok=True, code="ok", data={"xml": xml})

    runtime = _build_runtime(
        llm_client=_SequencedLLMClient(
            responses=[
                LLMResponse(
                    ok=True,
                    request_id="req-1",
                    provider="openai",
                    model="gpt-5.4",
                    output_text=json.dumps({"action": "ui.click", "params": {"x": 1, "y": 2}}),
                ),
                LLMResponse(
                    ok=True,
                    request_id="req-2",
                    provider="openai",
                    model="gpt-5.4",
                    output_text=json.dumps({"done": True, "message": "advanced"}),
                ),
            ]
        ),
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "unknown"},
                "status": "no_match",
                "ok": False,
            },
            {
                "platform": "native",
                "state": {"state_id": "unknown"},
                "status": "no_match",
                "ok": False,
            },
        ],
        trace_store=trace_store,
        extra_actions={"ui.dump_node_xml_ex": _dump_node_xml_ex},
    )

    result = runtime.run(
        {
            "goal": "login",
            "expected_state_ids": ["account", "password"],
            "allowed_actions": ["ui.click"],
            "max_steps": 2,
            "stagnant_limit": 1,
        },
        runtime=_trace_runtime_args(),
    )

    assert result["ok"] is True
    assert len(result["history"]) == 1


def test_agent_executor_blocks_direct_text_entry_on_cross_state_fallback():
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"action": "ui.click", "params": {"x": 100, "y": 200}}),
            ),
            LLMResponse(
                ok=True,
                request_id="req-2",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "inspect before typing"}),
            ),
        ]
    )

    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "account"},
                "status": "matched",
                "ok": True,
            },
            {
                "platform": "native",
                "state": {"state_id": "password"},
                "status": "no_match",
                "ok": False,
            },
        ],
        extra_actions={
            "ai.locate_point": lambda p, c: ActionResult(ok=True, code="ok", data={"x": 1, "y": 2}),
            "ui.input_text": lambda p, c: ActionResult(ok=True, code="ok"),
            "ui.key_press": lambda p, c: ActionResult(ok=True, code="ok"),
        },
    )

    result = runtime.run(
        {
            "goal": "login",
            "expected_state_ids": ["account", "password"],
            "allowed_actions": ["ai.locate_point", "ui.click", "ui.input_text", "ui.key_press"],
            "max_steps": 3,
            "stagnant_limit": 3,
        }
    )

    assert result["ok"] is True
    second_prompt = json.loads(cast(LLMRequest, llm_client.calls[1]["request"]).prompt)
    assert second_prompt["observation"]["state"]["state_id"] == "password"
    assert second_prompt["allowed_actions"] == ["ai.locate_point", "ui.click"]


def test_agent_executor_stabilizes_regressive_fallback_after_submit():
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps(
                    {"action": "ui.input_text", "params": {"text": "demo_pass"}}
                ),
            ),
            LLMResponse(
                ok=True,
                request_id="req-2",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"action": "ui.click", "params": {"x": 50, "y": 60}}),
            ),
            LLMResponse(
                ok=True,
                request_id="req-3",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "kept password stage stable"}),
            ),
        ]
    )

    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "password"},
                "status": "matched",
                "ok": True,
            },
            {
                "platform": "native",
                "state": {"state_id": "password"},
                "status": "matched",
                "ok": True,
            },
            {
                "platform": "native",
                "state": {"state_id": "account"},
                "status": "no_match",
                "ok": False,
                "raw_details": {"fallback_state_source": "ui_xml"},
                "evidence": {"summary": "fallback inferred login stage 'account' from ui_xml"},
            },
        ],
        extra_actions={
            "ui.input_text": lambda p, c: ActionResult(ok=True, code="ok"),
            "ui.key_press": lambda p, c: ActionResult(ok=True, code="ok", data={"key": "enter"}),
        },
    )

    result = runtime.run(
        {
            "goal": "login",
            "expected_state_ids": ["account", "password", "two_factor"],
            "allowed_actions": ["ui.click", "ui.input_text", "ui.key_press"],
            "max_steps": 4,
            "stagnant_limit": 4,
        }
    )

    assert result["ok"] is True
    third_prompt = json.loads(cast(LLMRequest, llm_client.calls[2]["request"]).prompt)
    assert third_prompt["observation"]["state"]["state_id"] == "password"
    assert third_prompt["observation"]["raw_details"]["fallback_state_source"] == (
        "stabilized_after_submit"
    )


def test_agent_executor_collects_fallback_evidence_into_planner_and_trace(tmp_path: Path):
    trace_store = ModelTraceStore(root_dir=tmp_path / "traces")

    def _dump_node_xml_ex(params, context):
        _ = (params, context)
        return ActionResult(
            ok=True, code="ok", data={"xml": "<hierarchy><node text='Retry'/></hierarchy>"}
        )

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


def test_agent_executor_treats_unknown_match_as_fallback_and_keeps_observed_states_clean(
    tmp_path: Path,
):
    trace_store = ModelTraceStore(root_dir=tmp_path / "traces")

    def _dump_node_xml_ex(params, context):
        _ = (params, context)
        return ActionResult(
            ok=True, code="ok", data={"xml": "<hierarchy><node text='Log in'/></hierarchy>"}
        )

    def _capture_compressed(params, context):
        _ = (params, context)
        return ActionResult(ok=True, code="ok", data={"byte_length": 456, "save_path": None})

    runtime = _build_runtime(
        llm_client=_SequencedLLMClient(
            responses=[
                LLMResponse(
                    ok=True,
                    request_id="req-unknown-fallback",
                    provider="openai",
                    model="gpt-5.4",
                    output_text=json.dumps({"done": True, "message": "fallback used"}),
                )
            ]
        ),
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "unknown"},
                "status": "matched",
                "ok": True,
                "matched_state_ids": ["unknown"],
                "expected_state_ids": ["account", "home", "unknown"],
                "evidence": {"confidence": 0.0},
            }
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
            "goal": "inspect unknown state fallback",
            "expected_state_ids": ["account", "home", "unknown"],
            "allowed_actions": ["ui.click"],
            "max_steps": 1,
            "fallback_modalities": ["xml", "screenshot"],
        },
        runtime=_trace_runtime_args(),
    )

    assert result["ok"] is True
    records = _read_trace_records(tmp_path / "traces")
    record = records[0]
    observation = cast(dict[str, object], record["observation"])
    observed_state_ids = cast(list[object], observation["observed_state_ids"])
    observed_state_ids_str = [str(item) for item in observed_state_ids]
    assert "account" not in observed_state_ids_str
    assert "home" not in observed_state_ids_str
    assert observed_state_ids_str
    planner = cast(dict[str, object], record["planner"])
    planner_request = cast(dict[str, object], planner["request"])
    planner_prompt = cast(dict[str, object], json.loads(cast(str, planner_request["prompt"])))
    planner_observation = cast(dict[str, object], planner_prompt["observation"])
    planner_state = cast(dict[str, object], planner_observation["state"])
    assert str(planner_state["state_id"]).strip() in {"unknown", "login_entry"}


def test_agent_executor_infers_password_state_from_fallback_xml_for_planner():
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-password-hint",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "password page inferred"}),
            ),
        ]
    )

    def _dump_node_xml_ex(params, context):
        _ = (params, context)
        return ActionResult(
            ok=True,
            code="ok",
            data={
                "xml": '<hierarchy><node text="パスワードを入力" resource-id="com.twitter.android:id/primary_text" />'
                '<node text="demo_user" resource-id="com.twitter.android:id/uneditable_identifier_edit_text" />'
                '<node text="" resource-id="com.twitter.android:id/password" class="android.widget.EditText" /></hierarchy>'
            },
        )

    def _capture_compressed(params, context):
        _ = (params, context)
        return ActionResult(ok=True, code="ok", data={"byte_length": 128, "save_path": None})

    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "unknown"},
                "status": "no_match",
                "ok": False,
            },
        ],
        extra_actions={
            "ui.dump_node_xml_ex": _dump_node_xml_ex,
            "device.capture_compressed": _capture_compressed,
        },
    )

    result = runtime.run(
        {
            "goal": "infer password state",
            "expected_state_ids": ["home", "password"],
            "allowed_actions": ["ui.click"],
            "max_steps": 1,
        }
    )

    assert result["ok"] is True
    prompt = cast(
        dict[str, object], json.loads(cast(LLMRequest, llm_client.calls[0]["request"]).prompt)
    )
    observation = cast(dict[str, object], prompt["observation"])
    state = cast(dict[str, object], observation["state"])
    raw_details = cast(dict[str, object], observation["raw_details"])
    assert state["state_id"] == "password"
    assert raw_details["fallback_state_hint"] == "password"


def test_agent_executor_infers_two_factor_state_from_verification_copy_in_fallback_xml():
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-two-factor-hint",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "two factor page inferred"}),
            )
        ]
    )

    def _dump_node_xml_ex(params, context):
        _ = (params, context)
        xml = (
            '<hierarchy bounds="[0,0][1080,1920]">'
            '<node text="输入你的验证码" class="android.widget.TextView" />'
            '<node text="" class="android.widget.EditText" />'
            "</hierarchy>"
        )
        return ActionResult(ok=True, code="ok", data={"xml": xml})

    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "unknown"},
                "status": "no_match",
                "ok": False,
            }
        ],
        extra_actions={"ui.dump_node_xml_ex": _dump_node_xml_ex},
    )

    result = runtime.run(
        {
            "goal": "infer two factor state",
            "expected_state_ids": ["password", "two_factor"],
            "allowed_actions": ["ui.click"],
            "max_steps": 1,
            "stagnant_limit": 1,
        }
    )

    assert result["ok"] is True
    prompt = json.loads(cast(LLMRequest, llm_client.calls[0]["request"]).prompt)
    state = prompt["observation"]["state"]
    raw_details = prompt["observation"]["raw_details"]
    assert state["state_id"] == "two_factor"
    assert raw_details["fallback_state_hint"] == "two_factor"


def test_agent_executor_waits_through_loading_overlay_before_replanning():
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-loading-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"action": "ui.click", "params": {"x": 10, "y": 20}}),
            ),
            LLMResponse(
                ok=True,
                request_id="req-loading-2",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "loading cleared"}),
            ),
        ]
    )

    def _dump_node_xml_ex(params, context):
        _ = (params, context)
        return ActionResult(
            ok=True,
            code="ok",
            data={
                "xml": '<hierarchy><node class="android.widget.ProgressBar" resource-id="android:id/progress" />'
                '<node text="正在载入…" resource-id="android:id/message" /></hierarchy>'
            },
        )

    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "two_factor"},
                "status": "matched",
                "ok": True,
            },
            {
                "platform": "native",
                "state": {"state_id": "unknown"},
                "status": "no_match",
                "ok": False,
            },
        ],
        wait_observations=[
            {
                "platform": "native",
                "state": {"state_id": "home"},
                "status": "matched",
                "ok": True,
            }
        ],
        extra_actions={"ui.dump_node_xml_ex": _dump_node_xml_ex},
    )

    result = runtime.run(
        {
            "goal": "wait through loading overlay",
            "expected_state_ids": ["two_factor", "home"],
            "allowed_actions": ["ui.click"],
            "max_steps": 2,
            "stagnant_limit": 2,
        }
    )

    assert result["ok"] is True
    assert len(llm_client.calls) == 2
    prompt = json.loads(cast(LLMRequest, llm_client.calls[1]["request"]).prompt)
    state = prompt["observation"]["state"]
    assert state["state_id"] == "home"


def test_agent_executor_auto_submits_after_input_on_fallback_inferred_account_state():
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps(
                    {"action": "ui.input_text", "params": {"text": "demo_user"}}
                ),
            ),
            LLMResponse(
                ok=True,
                request_id="req-2",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "moved on"}),
            ),
        ]
    )
    key_calls: list[dict[str, object]] = []

    def _key_press(params, context):
        _ = context
        key_calls.append(dict(params))
        return ActionResult(ok=True, code="ok", data={"key": params.get("key")})

    def _dump_node_xml_ex(params, context):
        _ = (params, context)
        return ActionResult(
            ok=True,
            code="ok",
            data={
                "xml": '<hierarchy><node text="電話番号/メールアドレス/ユーザー名" resource-id="com.twitter.android:id/identifier" class="android.widget.EditText" />'
                '<node text="次へ" resource-id="com.twitter.android:id/button_text" /></hierarchy>'
            },
        )

    def _capture_compressed(params, context):
        _ = (params, context)
        return ActionResult(ok=True, code="ok", data={"byte_length": 128, "save_path": None})

    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "unknown"},
                "status": "no_match",
                "ok": False,
            },
            {
                "platform": "native",
                "state": {"state_id": "unknown"},
                "status": "no_match",
                "ok": False,
            },
            {"platform": "native", "state": {"state_id": "home"}, "status": "matched", "ok": True},
        ],
        extra_actions={
            "ui.key_press": _key_press,
            "ui.input_text": lambda p, c: ActionResult(ok=True, code="ok"),
            "ui.dump_node_xml_ex": _dump_node_xml_ex,
            "device.capture_compressed": _capture_compressed,
        },
    )

    result = runtime.run(
        {
            "goal": "login",
            "expected_state_ids": ["account", "home"],
            "allowed_actions": ["ui.input_text", "ui.key_press"],
            "max_steps": 3,
            "stagnant_limit": 2,
        }
    )

    assert result["ok"] is True
    assert key_calls == [{"key": "enter"}]


def test_agent_executor_reflection_marks_successful_locate_point_for_follow_up_click():
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps(
                    {"action": "ai.locate_point", "params": {"prompt": "find login"}}
                ),
            ),
            LLMResponse(
                ok=True,
                request_id="req-2",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"action": "ui.click", "params": {"x": 10, "y": 20}}),
            ),
            LLMResponse(
                ok=True,
                request_id="req-3",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "entered login form"}),
            ),
        ]
    )

    def _locate_point(params, context):
        _ = (params, context)
        return ActionResult(ok=True, code="ok", data={"x": 10, "y": 20})

    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "login_entry"},
                "status": "no_match",
                "ok": False,
            },
            {
                "platform": "native",
                "state": {"state_id": "login_entry"},
                "status": "no_match",
                "ok": False,
            },
            {"platform": "native", "state": {"state_id": "home"}, "status": "matched", "ok": True},
        ],
        extra_actions={"ai.locate_point": _locate_point},
    )

    result = runtime.run(
        {
            "goal": "enter login form",
            "expected_state_ids": ["home"],
            "allowed_actions": ["ai.locate_point", "ui.click"],
            "max_steps": 5,
            "stagnant_limit": 1,
        }
    )

    assert result["ok"] is True
    second_prompt = cast(
        dict[str, object], json.loads(cast(LLMRequest, llm_client.calls[1]["request"]).prompt)
    )
    reflection = cast(dict[str, object], second_prompt["reflection"])
    assert reflection["locate_point_ready"] is True
    assert reflection["locate_point"] == {"x": 10, "y": 20}
    assert second_prompt["allowed_actions"] == ["ui.click"]


def test_agent_executor_removes_swipe_after_ambiguous_swipe_failure_in_unknown_fallback():
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"action": "ui.swipe", "params": {"direction": "up"}}),
            ),
            LLMResponse(
                ok=True,
                request_id="req-2",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "inspected with fallback"}),
            ),
        ]
    )

    def _swipe(params, context):
        _ = (params, context)
        return ActionResult(
            ok=False,
            code="swipe_failed",
            message="swipe transport did not acknowledge action; verify the next observation",
            data={"effect_uncertain": True},
        )

    def _dump_node_xml_ex(params, context):
        _ = (params, context)
        return ActionResult(
            ok=True, code="ok", data={"xml": "<hierarchy><node text='Log in'/></hierarchy>"}
        )

    def _capture_compressed(params, context):
        _ = (params, context)
        return ActionResult(ok=True, code="ok", data={"byte_length": 128, "save_path": None})

    def _locate_point(params, context):
        _ = (params, context)
        return ActionResult(ok=True, code="ok", data={"x": 10, "y": 20})

    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {
                "platform": "native",
                "state": {"state_id": "unknown"},
                "status": "no_match",
                "ok": False,
            },
            {
                "platform": "native",
                "state": {"state_id": "unknown"},
                "status": "no_match",
                "ok": False,
            },
        ],
        extra_actions={
            "ai.locate_point": _locate_point,
            "ui.swipe": _swipe,
            "ui.dump_node_xml_ex": _dump_node_xml_ex,
            "device.capture_compressed": _capture_compressed,
        },
    )

    result = runtime.run(
        {
            "goal": "inspect unknown state",
            "expected_state_ids": ["home", "unknown"],
            "allowed_actions": ["ai.locate_point", "ui.click", "ui.swipe"],
            "max_steps": 2,
            "stagnant_limit": 5,
        }
    )

    assert result["ok"] is True
    second_prompt = cast(
        dict[str, object], json.loads(cast(LLMRequest, llm_client.calls[1]["request"]).prompt)
    )
    assert second_prompt["allowed_actions"] == ["ai.locate_point", "ui.click"]


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
        observations=[
            {"platform": "native", "state": {"state_id": "account"}, "status": "matched"}
        ],
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
    assert result["circuit_breaker"]["step_budget_extensions_used"] == 0


def test_agent_executor_extends_step_budget_once_when_recent_progress_exists():
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-extend-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"action": "ui.click", "params": {"x": 10, "y": 20}}),
            ),
            LLMResponse(
                ok=True,
                request_id="req-extend-2",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"action": "ui.click", "params": {"x": 30, "y": 40}}),
            ),
            LLMResponse(
                ok=True,
                request_id="req-extend-3",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "completed after extension"}),
            ),
        ]
    )
    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {"platform": "native", "state": {"state_id": "login_entry"}, "status": "matched"},
            {"platform": "native", "state": {"state_id": "account"}, "status": "matched"},
            {"platform": "native", "state": {"state_id": "password"}, "status": "matched"},
        ],
    )

    result = runtime.run(
        {
            "task": "agent_executor",
            "goal": "allow one tail extension when progress is still happening",
            "expected_state_ids": ["login_entry", "account", "password"],
            "allowed_actions": ["ui.click"],
            "max_steps": 2,
            "stagnant_limit": 10,
        }
    )

    assert result["ok"] is True
    assert result["step_count"] == 2
    assert len(llm_client.calls) == 3


def test_agent_executor_cancellation_writes_terminal_trace_record(tmp_path: Path):
    trace_store = ModelTraceStore(root_dir=tmp_path / "traces")
    runtime = _build_runtime(
        llm_client=_SequencedLLMClient(
            responses=[
                LLMResponse(
                    ok=True,
                    request_id="req-1",
                    provider="openai",
                    model="gpt-5.4",
                    output_text=json.dumps({"action": "ui.click", "params": {}}),
                )
            ]
        ),
        observations=[
            {"platform": "native", "state": {"state_id": "account"}, "status": "matched"}
        ],
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


def test_reflection_injected_on_action_failure(tmp_path: Path):
    """When last action fails, reflection block should appear in the planner prompt."""
    trace_store = ModelTraceStore(root_dir=tmp_path / "traces")

    def _ui_click_fail(params, context):
        _ = (params, context)
        return ActionResult(ok=False, code="element_not_found", message="selector returned 0 nodes")

    llm_client = _SequencedLLMClient(
        responses=[
            # Step 1: plan ui.click (will fail)
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"action": "ui.click", "params": {"x": 100, "y": 200}}),
            ),
            # Step 2: after failure, planner should see reflection; plan done
            LLMResponse(
                ok=True,
                request_id="req-2",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps(
                    {"done": True, "message": "adjusted strategy after failure"}
                ),
            ),
        ]
    )

    registry = ActionRegistry()
    registry.register(
        "ui.match_state",
        lambda p, c: ActionResult(
            ok=True,
            code="ok",
            data={"platform": "native", "state": {"state_id": "home"}, "status": "matched"},
        ),
    )
    registry.register("ui.click", _ui_click_fail)
    runtime = AgentExecutorRuntime(
        registry=registry, llm_client_factory=lambda: llm_client, trace_store=trace_store
    )

    result = runtime.run(
        {
            "goal": "test failure reflection",
            "expected_state_ids": ["home"],
            "allowed_actions": ["ui.click"],
            "max_steps": 3,
            "stagnant_limit": 10,
        },
        runtime=_trace_runtime_args(),
    )

    assert result["ok"] is True
    assert len(llm_client.calls) == 2

    # Verify that the second planner call received a reflection block
    second_call = llm_client.calls[1]
    prompt = json.loads(cast(LLMRequest, second_call["request"]).prompt)
    assert "reflection" in prompt
    reflection = prompt["reflection"]
    assert reflection["last_action_failed"] is True
    assert reflection["failure_code"] == "element_not_found"
    assert "suggestion" in reflection

    # Verify history_digest is present in second call
    assert "history_digest" in prompt
    digest = prompt["history_digest"]
    assert len(digest) == 1
    assert digest[0]["action"] == "ui.click"
    assert digest[0]["ok"] is False


def test_history_digest_sliding_window():
    """History digest should only contain the most recent N steps."""
    from engine.agent_executor import _build_history_digest

    history: list[dict[str, object]] = [
        {
            "step_index": i,
            "action": f"action_{i}",
            "params": {"x": i},
            "result": {"ok": True, "message": ""},
        }
        for i in range(1, 9)  # 8 steps
    ]

    digest = _build_history_digest(history, window=5)
    assert len(digest) == 5
    assert digest[0]["step"] == 4  # starts at step 4 (8 - 5 + 1)
    assert digest[-1]["step"] == 8

    # Small history
    small = _build_history_digest(history[:2], window=5)
    assert len(small) == 2


def test_repeated_action_warning_injected_in_prompt():
    """When planner selects the same action+params repeatedly, a warning should appear."""
    llm_client = _SequencedLLMClient(
        responses=[
            # Steps 1-3: always choose same click
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"action": "ui.click", "params": {"x": 10, "y": 20}}),
            ),
            LLMResponse(
                ok=True,
                request_id="req-2",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"action": "ui.click", "params": {"x": 10, "y": 20}}),
            ),
            LLMResponse(
                ok=True,
                request_id="req-3",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"done": True, "message": "finally done"}),
            ),
        ]
    )
    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {"platform": "native", "state": {"state_id": f"state-{i}"}, "status": "matched"}
            for i in range(1, 5)
        ],
    )

    result = runtime.run(
        {
            "goal": "test repeated action warning",
            "expected_state_ids": ["state"],
            "allowed_actions": ["ui.click"],
            "max_steps": 5,
            "stagnant_limit": 10,
        }
    )

    assert result["ok"] is True
    assert len(llm_client.calls) == 3

    # Third call should have repeated_action_detected warning
    third_prompt = json.loads(cast(LLMRequest, llm_client.calls[2]["request"]).prompt)
    assert "reflection" in third_prompt
    reflection = third_prompt["reflection"]
    assert reflection["repeated_action_detected"] is True
    assert reflection["repeated_count"] == 2


def test_reflection_trace_records_include_metadata(tmp_path: Path):
    """Trace records should contain reflection metadata for observability."""
    trace_store = ModelTraceStore(root_dir=tmp_path / "traces")
    llm_client = _SequencedLLMClient(
        responses=[
            LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"action": "ui.click", "params": {"x": 10, "y": 20}}),
            ),
            LLMResponse(
                ok=True,
                request_id="req-2",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps({"action": "ui.click", "params": {"x": 10, "y": 20}}),
            ),
        ]
    )
    runtime = _build_runtime(
        llm_client=llm_client,
        observations=[
            {"platform": "native", "state": {"state_id": f"s{i}"}, "status": "matched"}
            for i in range(1, 4)
        ],
        trace_store=trace_store,
    )

    runtime.run(
        {
            "goal": "test trace metadata",
            "expected_state_ids": ["s"],
            "allowed_actions": ["ui.click"],
            "max_steps": 2,
            "stagnant_limit": 10,
        },
        runtime=_trace_runtime_args(),
    )

    records = _read_trace_records(tmp_path / "traces")
    step_records = [r for r in records if r["record_type"] == "step"]
    assert len(step_records) == 2

    # First step: no reflection (no previous action)
    assert step_records[0]["reflection"] is None
    assert step_records[0]["history_digest_length"] == 0
    assert step_records[0]["repeated_action_count"] == 1  # first occurrence = 1

    # Second step: has repeated action count
    assert step_records[1]["history_digest_length"] == 1
    assert step_records[1]["repeated_action_count"] == 2
