from engine.agent_executor_support import (
    _business_completion_hint,
    _default_max_steps,
    _planner_allowed_actions,
    _planner_inputs,
    _rewrite_text_entry_locate_params,
)


def test_planner_inputs_accepts_canonical_login_field_names() -> None:
    payload = {
        "account": "demo_user",
        "password": "demo_pass",
        "two_factor_code": "123456",
        "twofa_secret": "secret-otp",
    }

    assert _planner_inputs(payload) == {
        "acc": "demo_user",
        "pwd": "demo_pass",
        "two_factor_code": "123456",
        "fa2_secret": "secret-otp",
    }


def test_rewrite_text_entry_locate_params_preserves_submit_intent_for_account_stage() -> None:
    params = {
        "instruction": (
            "定位当前 X 登录界面中用于提交账号并进入下一步的主按钮，"
            "可能文字为 Next、Log in、登录、Continue、下一步。"
        )
    }

    rewritten = _rewrite_text_entry_locate_params(
        "ai.locate_point",
        params,
        {"state": {"state_id": "account"}},
        last_action={"action": "ui.click", "result": {"ok": True}},
        previous_state_id="login_entry",
        observation_requires_fallback=True,
    )

    assert "主操作控件" in str(rewritten["instruction"])


def test_planner_allowed_actions_removes_navigate_without_navigation_context() -> None:
    actions = _planner_allowed_actions(
        allowed_actions=["ui.navigate_to", "ui.click", "ui.dump_node_xml_ex"],
        last_action=None,
        observation_payload={"state": {"state_id": "home"}},
        previous_state_id="",
        observation_requires_fallback=False,
        navigation_available=False,
    )

    assert actions == ["ui.click", "ui.dump_node_xml_ex"]


def test_business_completion_hint_triggers_on_return_home_branch_goal() -> None:
    message = _business_completion_hint(
        goal="进入通知页面如果有新的关注就回关没有则返回主页",
        previous_state_id="notifications",
        observation_payload={"state": {"state_id": "home"}},
        last_action={"action": "ui.click", "result": {"ok": True}},
    )

    assert "已返回主页" in message


def test_default_max_steps_uses_app_profile_for_app_level_ai_tasks() -> None:
    max_steps, allow_extension = _default_max_steps(
        {
            "task": "agent_executor",
            "app_id": "x",
            "package": "com.twitter.android",
            "_app_states": {"home": {"label": "首页"}},
        }
    )

    assert max_steps == 12
    assert allow_extension is True


def test_default_max_steps_respects_explicit_override() -> None:
    max_steps, allow_extension = _default_max_steps(
        {
            "task": "agent_executor",
            "app_id": "x",
            "max_steps": 5,
        }
    )

    assert max_steps == 5
    assert allow_extension is True
