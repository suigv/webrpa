from hardware_adapters.mytRpc import swipe_transport_acknowledged
from hardware_adapters.myt_client import MytRpc


def test_myt_rpc_module_smoke():
    client = MytRpc()
    assert hasattr(client, "init")
    assert hasattr(client, "close")
    assert hasattr(client, "check_connect_state")
    assert hasattr(client, "touchClick")
    assert hasattr(client, "swipe")


def test_myt_rpc_sdk_version_call_is_failure_safe():
    client = MytRpc()
    result = client.get_sdk_version()
    assert result is not None


def test_swipe_transport_acknowledged_accepts_zero_and_one():
    assert swipe_transport_acknowledged(0) is True
    assert swipe_transport_acknowledged(1) is True
    assert swipe_transport_acknowledged(True) is True
    assert swipe_transport_acknowledged(-1) is False
    assert swipe_transport_acknowledged(False) is False
