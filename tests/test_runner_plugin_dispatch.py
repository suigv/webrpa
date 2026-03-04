from new.engine.runner import Runner


def test_runner_yaml_plugin_dispatch_fails_without_credentials():
    """Runner dispatches x_auto_login to YAML interpreter.
    Without valid credentials_ref, the workflow should fail at credentials.load step.
    """
    result = Runner().run({"task": "x_auto_login"})
    assert result["ok"] is False
    assert result["task"] == "x_auto_login"
    assert "credentials_ref" in result.get("message", "").lower() or "missing" in result.get("message", "").lower()


def test_runner_unknown_plugin_error_is_controlled():
    result = Runner().run({"task": "x_auto_login_missing"})
    assert result["ok"] is False
    assert result["status"] == "failed_config_error"
    assert result["checkpoint"] == "dispatch"
