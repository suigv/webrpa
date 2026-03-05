from engine.runner import Runner


def test_x_mobile_login_success_status_contract():
    result = Runner().run({"task": "x_mobile_login", "device_ip": "192.168.1.2", "status_hint": "success"})
    assert result["task"] == "x_mobile_login"
    assert result["status"] == "success"


def test_x_mobile_login_bad_credentials_status_contract():
    result = Runner().run({"task": "x_mobile_login", "device_ip": "192.168.1.2", "status_hint": "bad_credentials"})
    assert result["task"] == "x_mobile_login"
    assert result["status"] == "failed"
    assert "bad credentials" in result.get("message", "")


def test_x_mobile_login_2fa_failed_status_contract():
    result = Runner().run({"task": "x_mobile_login", "device_ip": "192.168.1.2", "status_hint": "2fa_failed"})
    assert result["task"] == "x_mobile_login"
    assert result["status"] == "failed"
    assert "2fa_failed" in result.get("message", "")


def test_x_mobile_login_captcha_status_contract():
    result = Runner().run({"task": "x_mobile_login", "device_ip": "192.168.1.2", "status_hint": "captcha"})
    assert result["task"] == "x_mobile_login"
    assert result["status"] == "failed"
    assert "captcha" in result.get("message", "")
