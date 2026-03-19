from models.task import TaskRequest


def test_task_request_defaults_ai_type_to_default() -> None:
    request = TaskRequest(task="demo", targets=[{"device_id": 1}], payload={})

    assert request.ai_type == "default"
