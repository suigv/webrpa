from engine.agent_executor_support import _planner_inputs, _rewrite_text_entry_locate_params


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
