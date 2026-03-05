from engine.runner import Runner


def test_failure_isolation_and_recovery_for_migrated_plugins():
    runner = Runner()

    failed = runner.run({"task": "profile_clone", "source_key": "not_exists"})
    assert failed["status"] == "failed"
    assert "missing_source_data" in failed.get("message", "")

    recovered = runner.run({"task": "x_mobile_login", "device_ip": "192.168.1.2", "status_hint": "success"})
    assert recovered["status"] == "success"
