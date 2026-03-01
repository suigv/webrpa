from new.engine.runner import Runner


def test_x_login_contract_schema_missing_credentials_ref():
    result = Runner().run({"task": "x_auto_login"})
    assert result["ok"] is False
    assert result["status"] == "failed_config_error"
    assert result["checkpoint"] == "credentials"
    assert "message" in result
    assert "evidence_ref" in result


def test_non_plugin_task_stays_backward_compatible():
    result = Runner().run({"task": "anonymous", "steps": []})
    assert result["ok"] is True
    assert result["status"] == "stub_executed"
