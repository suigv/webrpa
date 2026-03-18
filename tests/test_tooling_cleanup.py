from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from core.paths import project_root
from tools._bootstrap import bootstrap_project_root
from tools.clean_workspace import collect_cleanup_targets, delete_targets


def test_bootstrap_project_root_matches_core_helper() -> None:
    assert bootstrap_project_root() == project_root()


def test_tools_root_inference_is_centralized() -> None:
    root = project_root()
    pattern = "Path(__file__).resolve().parents[1]"
    sys_path_insert = "sys.path.insert(0,"

    for script in (root / "tools").glob("*.py"):
        text = script.read_text(encoding="utf-8")
        if script.name == "_bootstrap.py":
            assert pattern in text
            continue
        assert pattern not in text, (
            f"{script} should use tools._bootstrap instead of inline root inference"
        )
        assert sys_path_insert not in text, (
            f"{script} should rely on tools._bootstrap for sys.path setup"
        )


def test_collect_cleanup_targets_finds_repo_junk_without_touching_skipped_dirs(tmp_path):
    root = tmp_path
    (root / "core" / "__pycache__").mkdir(parents=True)
    (root / "core" / "__pycache__" / "mod.pyc").write_bytes(b"abc")
    (root / "tests" / ".pytest_cache").mkdir(parents=True)
    (root / "tests" / ".pytest_cache" / "state").write_text("x", encoding="utf-8")
    (root / "plugins").mkdir(parents=True)
    (root / "plugins" / ".DS_Store").write_text("", encoding="utf-8")
    (root / "web" / "dist").mkdir(parents=True)
    (root / "web" / "dist" / "index.html").write_text("built", encoding="utf-8")
    (root / ".venv" / "__pycache__").mkdir(parents=True)
    (root / ".venv" / "__pycache__" / "skip.pyc").write_bytes(b"skip")
    (root / "vendor" / "__pycache__").mkdir(parents=True)
    (root / "vendor" / "__pycache__" / "skip.pyc").write_bytes(b"skip")

    targets = collect_cleanup_targets(root)
    rel_paths = {str(item.path.relative_to(root)) for item in targets}

    assert "core/__pycache__" in rel_paths
    assert "tests/.pytest_cache" in rel_paths
    assert "plugins/.DS_Store" in rel_paths
    assert "web/dist" in rel_paths
    assert ".venv/__pycache__" not in rel_paths
    assert "vendor/__pycache__" not in rel_paths


def test_collect_cleanup_targets_optionally_prunes_old_traces(tmp_path):
    root = tmp_path
    old_trace = root / "config" / "data" / "traces" / "old-task"
    old_trace.mkdir(parents=True)
    (old_trace / "trace.jsonl").write_text("old", encoding="utf-8")
    stale_time = (datetime.now(UTC) - timedelta(days=10)).timestamp()
    old_trace.touch()
    (old_trace / "trace.jsonl").touch()
    for path in (old_trace, old_trace / "trace.jsonl"):
        path.touch()
        os.utime(path, (stale_time, stale_time))

    new_trace = root / "config" / "data" / "traces" / "new-task"
    new_trace.mkdir(parents=True)
    (new_trace / "trace.jsonl").write_text("new", encoding="utf-8")

    targets = collect_cleanup_targets(root, trace_retention_days=7)
    rel_paths = {str(item.path.relative_to(root)) for item in targets}

    assert "config/data/traces/old-task" in rel_paths
    assert "config/data/traces/new-task" not in rel_paths


def test_delete_targets_removes_reported_paths(tmp_path):
    root = tmp_path
    cache_dir = root / "core" / "__pycache__"
    cache_dir.mkdir(parents=True)
    (cache_dir / "mod.pyc").write_bytes(b"abc")
    ds_store = root / "plugins" / ".DS_Store"
    ds_store.parent.mkdir(parents=True)
    ds_store.write_text("", encoding="utf-8")

    targets = collect_cleanup_targets(root, include_build_artifacts=False)
    removed_count, removed_bytes = delete_targets(targets)

    assert removed_count == 2
    assert removed_bytes >= 3
    assert not cache_dir.exists()
    assert not ds_store.exists()
