import pytest
from pydantic import ValidationError

from engine.models.declarative_script import DeclarativeScriptV0


def _sample_payload() -> dict[str, object]:
    return {
        "version": "v0",
        "kind": "declarative_script",
        "app_id": "x",
        "app_scope": "engagement",
        "name": "x_follow_followers_decl",
        "title": "批量关注目标博主粉丝",
        "description": "从目标博主粉丝列表中批量关注符合条件的账号。",
        "goal": "完成一轮关注截流",
        "role": "engage",
        "depends_on": ["x_login_decl"],
        "consumes": [
            {
                "name": "login_state",
                "kind": "state",
                "description": "账号已登录且可进入 X 页面",
                "required": True,
                "source": "runtime_state",
            }
        ],
        "produces": [
            {
                "name": "follow_summary",
                "kind": "result",
                "description": "本轮关注统计结果",
                "persistent": True,
                "exposed": True,
            }
        ],
        "stages": [
            {
                "name": "prepare_follow_flow",
                "title": "准备关注流程",
                "description": "确保账号、页面、限额状态满足执行条件。",
                "kind": "setup",
                "goal": "进入可执行关注动作的准备态",
                "exit_when": ["已进入目标粉丝列表"],
                "handoff_policy": {
                    "allowed": True,
                    "triggers": ["验证码"],
                    "on_handoff": "pause_and_wait",
                },
            },
            {
                "name": "follow_targets_loop",
                "title": "循环执行关注",
                "description": "查找可关注对象并执行关注。",
                "kind": "loop",
                "goal": "完成本轮关注目标",
                "exit_when": ["达到目标关注数", "没有更多可操作对象"],
                "handoff_policy": {
                    "allowed": True,
                    "triggers": ["页面状态无法判断"],
                    "on_handoff": "pause_and_exit",
                },
            },
        ],
        "success_definition": {
            "summary": "达成本轮目标关注数并输出统计",
            "signals": ["达到目标关注数", "输出关注结果统计"],
        },
        "failure_definition": {
            "summary": "无法进入可执行状态或出现不可恢复异常",
            "signals": ["登录失效", "连续失败过多"],
            "retryable": True,
        },
        "handoff_policy": {
            "allowed": True,
            "triggers": ["验证码", "风控验证"],
            "on_handoff": "pause_and_wait",
        },
    }


def test_declarative_script_v0_accepts_minimal_valid_payload():
    model = DeclarativeScriptV0.model_validate(_sample_payload())

    assert model.app_id == "x"
    assert model.role == "engage"
    assert model.stages[1].kind == "loop"


def test_declarative_script_v0_rejects_self_dependency():
    payload = _sample_payload()
    payload["depends_on"] = ["x_login_decl", "x_follow_followers_decl"]

    with pytest.raises(ValidationError, match="depends_on cannot contain self"):
        DeclarativeScriptV0.model_validate(payload)


def test_declarative_script_v0_rejects_loop_without_exit_conditions():
    payload = _sample_payload()
    payload["stages"][1]["exit_when"] = []

    with pytest.raises(ValidationError, match="loop stages must declare"):
        DeclarativeScriptV0.model_validate(payload)


def test_declarative_script_v0_rejects_disallowed_handoff_triggers():
    payload = _sample_payload()
    payload["handoff_policy"] = {
        "allowed": False,
        "triggers": ["验证码"],
        "on_handoff": "record_and_fail",
    }

    with pytest.raises(ValidationError, match="triggers must be empty"):
        DeclarativeScriptV0.model_validate(payload)


def test_declarative_script_v0_json_schema_exposes_required_contract_fields():
    schema = DeclarativeScriptV0.model_json_schema()
    required = set(schema.get("required") or [])

    assert {
        "version",
        "kind",
        "app_id",
        "app_scope",
        "name",
        "title",
        "description",
        "goal",
        "role",
        "consumes",
        "produces",
        "depends_on",
        "stages",
        "success_definition",
        "failure_definition",
        "handoff_policy",
    }.issubset(required)
