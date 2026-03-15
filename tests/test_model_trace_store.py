# pyright: reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false

from pathlib import Path

import pytest

from core.paths import traces_dir
from core.model_trace_store import ModelTraceContext, ModelTraceStore, ModelTraceStoreError


def test_model_trace_store_appends_jsonl_records_under_config_data(tmp_path):
    _ = tmp_path  # retain fixture for parity; root is fixed in standalone project
    store = ModelTraceStore()
    context = ModelTraceContext(
        task_id="task-123",
        run_id="task-123-run-1",
        target_label="Unit #7-2",
        attempt_number=1,
    )

    path = store.append_record(context, {"sequence": 1, "step_index": 1, "record_type": "step"})
    store.append_record(context, {"sequence": 2, "step_index": 2, "record_type": "terminal"})

    assert path.parent == traces_dir() / "task-123" / "task-123-run-1"
    assert path.name.endswith(".attempt-1.jsonl")
    payload = store.read_records(context)
    assert [item["sequence"] for item in payload] == [1, 2]
    assert payload[0]["task_id"] == "task-123"
    assert payload[0]["target_label"] == "Unit #7-2"
    assert payload[1]["record_type"] == "terminal"


def test_model_trace_store_raises_explicit_error_on_append_failure(tmp_path):
    blocked_root: Path = tmp_path / "blocked"
    blocked_root.write_text("not-a-directory", encoding="utf-8")
    store = ModelTraceStore(root_dir=blocked_root)
    context = ModelTraceContext(
        task_id="task-123",
        run_id="task-123-run-1",
        target_label="Unit #7-2",
        attempt_number=1,
    )

    with pytest.raises(ModelTraceStoreError, match="failed to append model trace"):
        store.append_record(context, {"sequence": 1, "step_index": 1})
