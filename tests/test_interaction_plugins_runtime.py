from new.engine.runner import Runner


def test_follow_and_home_plugin_success():
    follow = Runner().run({"task": "follow_interaction", "device_ip": "192.168.1.2", "status_hint": "success"})
    home = Runner().run({"task": "home_interaction", "device_ip": "192.168.1.2", "status_hint": "success"})
    assert follow["status"] == "success"
    assert home["status"] == "success"


def test_interaction_plugins_rate_limit_and_empty_target():
    follow_limit = Runner().run({"task": "follow_interaction", "device_ip": "192.168.1.2", "status_hint": "rate_limit"})
    home_empty = Runner().run({"task": "home_interaction", "device_ip": "192.168.1.2", "status_hint": "empty_target"})
    assert follow_limit["status"] == "failed"
    assert "rate_limit" in follow_limit.get("message", "")
    assert home_empty["status"] == "failed"
    assert "empty_target" in home_empty.get("message", "")


def test_quote_and_dm_plugin_templates_available():
    quote = Runner().run({"task": "quote_interaction", "device_ip": "192.168.1.2", "status_hint": "success"})
    dm = Runner().run({"task": "dm_reply", "device_ip": "192.168.1.2", "status_hint": "success"})
    assert quote["status"] == "success"
    assert dm["status"] == "success"
