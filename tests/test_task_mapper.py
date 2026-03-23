# pyright: reportMissingImports=false
from datetime import UTC, datetime

from api.mappers.task_mapper import (
    extract_targets,
    parse_datetime,
    to_task_detail_response,
    to_task_response,
)
from core.task_store import TaskRecord


def test_task_mapper_parses_datetimes_and_record_targets():
    record = TaskRecord(
        task_id="task-1",
        payload={
            "task": "demo-task",
        },
        devices=[1],
        targets=[
            {"device_id": 1, "cloud_id": 2},
            {"device_id": 0, "cloud_id": 1},
        ],
        status="pending",
        created_at="2026-03-09T01:02:03Z",
        started_at="2026-03-09T01:02:13Z",
        finished_at="2026-03-09T01:02:23Z",
        next_retry_at="2026-03-09T01:03:03+00:00",
        run_at="2026-03-09T01:04:03",
    )

    response = to_task_response(record)
    response_targets = [item.model_dump() for item in response.targets]

    assert parse_datetime("2026-03-09T01:02:03Z") == datetime(2026, 3, 9, 1, 2, 3, tzinfo=UTC)
    assert parse_datetime("not-a-datetime") is None
    assert response.task_name == "demo-task"
    assert response_targets == [{"device_id": 1, "cloud_id": 2}]
    assert response.created_at == datetime(2026, 3, 9, 1, 2, 3, tzinfo=UTC)
    assert response.started_at == datetime(2026, 3, 9, 1, 2, 13, tzinfo=UTC)
    assert response.finished_at == datetime(2026, 3, 9, 1, 2, 23, tzinfo=UTC)
    assert response.next_retry_at == datetime(2026, 3, 9, 1, 3, 3, tzinfo=UTC)
    assert response.run_at == datetime(2026, 3, 9, 1, 4, 3)


def test_task_mapper_prefers_record_targets_and_detail_fields():
    record = TaskRecord(
        task_id="task-2",
        payload={
            "task": "demo-task",
        },
        devices=[7],
        targets=[{"device_id": 7, "cloud_id": 3}],
        status="failed",
        created_at="2026-03-09T01:02:03+00:00",
        result={"ok": False},
        error="boom",
    )

    assert [item.model_dump() for item in extract_targets(record)] == [
        {"device_id": 7, "cloud_id": 3}
    ]

    detail = to_task_detail_response(record)

    assert [item.model_dump() for item in detail.targets] == [{"device_id": 7, "cloud_id": 3}]
    assert detail.result == {"ok": False}
    assert detail.error == "boom"
