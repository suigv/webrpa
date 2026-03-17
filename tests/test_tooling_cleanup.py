from __future__ import annotations

from core.paths import project_root
from tools._bootstrap import bootstrap_project_root


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
