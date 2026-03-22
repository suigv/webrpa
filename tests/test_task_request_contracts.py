import pytest

from models.task import TaskRequest


def test_task_request_defaults_ai_type_to_default() -> None:
    request = TaskRequest.model_validate({"task": "demo", "targets": [{"device_id": 1}], "payload": {}})

    assert request.ai_type == "default"


def test_task_request_accepts_canonical_ai_managed_shape() -> None:
    request = TaskRequest.model_validate(
        {
            "task": "agent_executor",
            "payload": {"goal": "open home"},
            "targets": [{"device_id": 7, "cloud_id": 2}],
        }
    )

    assert request.task == "agent_executor"
    assert request.payload == {"goal": "open home"}
    assert [target.model_dump() for target in request.targets] == [
        {"device_id": 7, "cloud_id": 2}
    ]
    assert request.devices == []


def test_task_request_keeps_devices_as_compatibility_input() -> None:
    request = TaskRequest(task="agent_executor", payload={"goal": "open home"}, devices=[3, 5])

    assert request.devices == [3, 5]
    assert request.targets == []


def test_task_request_centralizes_controller_submission_kwargs() -> None:
    request = TaskRequest.model_validate(
        {
            "task": "agent_executor",
            "payload": {"goal": "open home"},
            "targets": [{"device_id": 7, "cloud_id": 2}],
            "ai_type": "volc",
            "display_name": "Open Home",
            "draft_id": "draft_123",
            "success_threshold": 4,
            "idempotency_key": "body-key",
            "max_retries": 2,
            "retry_backoff_seconds": 5,
            "priority": 80,
        }
    )

    assert request.controller_submission_kwargs(
        script_payload={"task": "agent_executor", "goal": "open home"},
        idempotency_key="header-key",
    ) == {
        "payload": {"task": "agent_executor", "goal": "open home"},
        "devices": [],
        "targets": [{"device_id": 7, "cloud_id": 2}],
        "ai_type": "volc",
        "max_retries": 2,
        "retry_backoff_seconds": 5,
        "priority": 80,
        "run_at": None,
        "idempotency_key": "header-key",
        "display_name": "Open Home",
        "draft_id": "draft_123",
        "success_threshold": 4,
    }


@pytest.mark.parametrize(
    ("field_name", "field_value", "expected_message"),
    [
        ("device_ip", "10.0.0.1", "device_ip is not part of the canonical top-level task request"),
        ("cloud_id", 2, "cloud_id is not part of the canonical top-level task request"),
        (
            "allowed_actions",
            ["ui.click"],
            "allowed_actions is not part of the canonical top-level task request",
        ),
    ],
)
def test_task_request_rejects_misplaced_top_level_runtime_or_payload_fields(
    field_name: str, field_value: object, expected_message: str
) -> None:
    with pytest.raises(ValueError, match=expected_message):
        TaskRequest.model_validate(
            {
                "task": "agent_executor",
                "payload": {"goal": "open home"},
                "targets": [{"device_id": 7, "cloud_id": 2}],
                field_name: field_value,
            }
        )
