from new.engine.runner import Runner
import new.plugins.x_auto_login as x_auto_login


def test_runner_plugin_dispatch(monkeypatch):
    def fake_run(context):
        payload = context["payload"]
        return {
            "ok": True,
            "task": payload.get("task"),
            "status": "completed",
            "checkpoint": "verify_success",
            "message": "ok",
            "evidence_ref": "",
        }

    monkeypatch.setattr(x_auto_login, "run", fake_run)
    result = Runner().run({"task": "x_auto_login", "credentials_ref": "/etc/myt/x_credentials.json"})
    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["checkpoint"] == "verify_success"


def test_runner_unknown_plugin_error_is_controlled():
    result = Runner().run({"task": "x_auto_login_missing"})
    assert result["ok"] is False
    assert result["status"] == "failed_config_error"
    assert result["checkpoint"] == "dispatch"
