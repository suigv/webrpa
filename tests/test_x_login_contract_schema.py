from new.engine.runner import Runner


def test_x_login_missing_credentials_returns_error():
    """When x_auto_login is invoked without credentials_ref, the YAML
    workflow should fail at the credentials.load step."""
    result = Runner().run({"task": "x_auto_login"})
    assert result["ok"] is False
    assert result["task"] == "x_auto_login"
    # The interpreter returns status="failed" for InterpreterError
    assert result["status"] == "failed"
    assert "message" in result


def test_non_plugin_task_stays_backward_compatible():
    result = Runner().run({"task": "anonymous", "steps": []})
    assert result["ok"] is True
    assert result["status"] == "stub_executed"
