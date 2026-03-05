from new.engine.runner import Runner


def test_x_login_missing_credentials_returns_error():
    result = Runner().run({"task": "x_auto_login"})
    assert result["ok"] is False
    assert result["task"] == "x_auto_login"
    assert result["status"] == "failed_config_error"
    assert result["checkpoint"] == "dispatch"
    assert result["code"] == "missing_required_param"
    assert "message" in result


def test_non_plugin_task_stays_backward_compatible():
    result = Runner().run({"task": "anonymous", "steps": []})
    assert result["ok"] is True
    assert result["status"] == "stub_executed"
