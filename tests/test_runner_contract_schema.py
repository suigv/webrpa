from new.engine.runner import Runner


def test_runner_unsupported_task_returns_controlled_error():
    result = Runner().run({"task": "some_unknown_task"})
    assert result["ok"] is False
    assert result["status"] == "failed_config_error"
    assert result["checkpoint"] == "dispatch"
    assert "message" in result
    assert "timestamp" in result


def test_anonymous_task_stays_backward_compatible():
    result = Runner().run({"task": "anonymous", "steps": []})
    assert result["ok"] is True
    assert result["status"] == "stub_executed"
