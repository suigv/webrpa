from engine.actions._context_value_support import resolve_context_value
from engine.models.runtime import ExecutionContext


def test_resolve_context_value_supports_sdk_style_order() -> None:
    context = ExecutionContext(
        payload={"device_ip": "payload-ip"},
        runtime={"device_ip": "runtime-ip", "target": {"device_ip": "target-ip"}},
    )

    value = resolve_context_value(
        {},
        context,
        "device_ip",
        source_order=("params", "payload", "target", "runtime"),
    )

    assert value == "payload-ip"


def test_resolve_context_value_supports_android_api_style_order() -> None:
    context = ExecutionContext(
        payload={"device_ip": "payload-ip"},
        runtime={"device_ip": "runtime-ip", "target": {"device_ip": "target-ip"}},
    )

    value = resolve_context_value(
        {},
        context,
        "device_ip",
        source_order=("params", "runtime", "payload"),
    )

    assert value == "runtime-ip"


def test_resolve_context_value_uses_runtime_target_when_requested() -> None:
    context = ExecutionContext(
        payload={"device_ip": "payload-ip"},
        runtime={
            "device_ip": "runtime-ip",
            "api_port": 39999,
            "target": {"device_ip": "target-ip", "api_port": 30001},
        },
    )

    target_first_value = resolve_context_value(
        {},
        context,
        "api_port",
        source_order=("params", "target", "runtime"),
    )

    assert target_first_value == 30001
