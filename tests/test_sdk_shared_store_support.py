from engine.actions.sdk_shared_store_support import resolve_shared_key
from engine.models.runtime import ExecutionContext


def test_resolve_shared_key_keeps_legacy_scope_defaults() -> None:
    context = ExecutionContext(
        payload={
            "device_ip": "192.168.1.214",
            "name": "android-03",
        }
    )
    context.task_id = "task-123"
    context.cloud_target_label = "cloud-03"

    assert resolve_shared_key({"key": "token", "scope": "device"}, context) == (
        "device:192.168.1.214:token"
    )
    assert resolve_shared_key({"key": "token", "scope": "task"}, context) == "task:task-123:token"
    assert resolve_shared_key({"key": "token", "scope": "cloud"}, context) == (
        "cloud:cloud-03:token"
    )


def test_resolve_shared_key_tolerates_missing_dynamic_context_attrs() -> None:
    context = ExecutionContext(
        payload={
            "device_ip": "192.168.1.215",
            "name": "android-05",
        }
    )

    assert resolve_shared_key({"key": "token", "scope": "task"}, context) == "token"
    assert resolve_shared_key({"key": "token", "scope": "cloud"}, context) == (
        "cloud:android-05:token"
    )


def test_resolve_shared_key_prefers_runtime_target_device_ip_for_managed_tasks() -> None:
    context = ExecutionContext(
        payload={},
        runtime={"target": {"device_ip": "192.168.1.214", "cloud_id": 1}},
    )

    assert resolve_shared_key({"key": "token", "scope": "device"}, context) == (
        "device:192.168.1.214:token"
    )
