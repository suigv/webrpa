from __future__ import annotations

import importlib.util
import re
from pathlib import Path

if __package__:
    from tools._bootstrap import bootstrap_project_root
else:
    bootstrap_path = Path(__file__).with_name("_bootstrap.py")
    spec = importlib.util.spec_from_file_location("tools._bootstrap", bootstrap_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load bootstrap helper: {bootstrap_path}")
    bootstrap_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap_module)
    bootstrap_project_root = bootstrap_module.bootstrap_project_root


SNAPSHOT_START = "<!-- AUTO_PROGRESS_SNAPSHOT:START -->"
SNAPSHOT_END = "<!-- AUTO_PROGRESS_SNAPSHOT:END -->"


def _count_matches(path: Path, pattern: str, flags: int = 0) -> int:
    text = path.read_text(encoding="utf-8")
    return len(re.findall(pattern, text, flags=flags))


def _count_api_routes(root: Path) -> tuple[int, int]:
    routes_dir = root / "api" / "routes"
    router_count = 0
    for py in routes_dir.glob("*.py"):
        router_count += _count_matches(py, r"@router\.(get|post|put|delete|patch|websocket)\(")

    app_count = _count_matches(root / "api" / "server.py", r"@app\.(get|post|put|delete|patch)\(")
    return router_count, app_count


def _count_plugins(root: Path) -> int:
    plugins_dir = root / "plugins"
    if not plugins_dir.is_dir():
        return 0
    count = 0
    for child in plugins_dir.iterdir():
        if child.is_dir() and (child / "manifest.yaml").exists():
            count += 1
    return count


def _count_tests(root: Path) -> tuple[int, int]:
    tests_dir = root / "tests"
    test_files = list(tests_dir.glob("test_*.py"))
    test_fn_count = 0
    for test_file in test_files:
        test_fn_count += _count_matches(test_file, r"^def test_", flags=re.M)
    return len(test_files), test_fn_count


def _count_sdk_actions(root: Path) -> int:
    action_dir = root / "engine" / "actions"
    total = 0
    for path in (action_dir / "sdk_actions.py", action_dir / "sdk_action_catalog.py"):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        total += len(re.findall(r'"[a-z0-9_.]+"\s*:\s*\(', text))
    return total


def _render_snapshot(root: Path) -> str:
    router_count, app_count = _count_api_routes(root)
    plugin_count = _count_plugins(root)
    test_file_count, test_fn_count = _count_tests(root)
    sdk_action_count = _count_sdk_actions(root)

    lines = [
        SNAPSHOT_START,
        "- Source: `tools/update_project_progress.py`",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| API route decorators (`api/routes`) | {router_count} |",
        f"| App-level route decorators (`api/server.py`) | {app_count} |",
        f"| Plugin count (`plugins/*/manifest.yaml`) | {plugin_count} |",
        (
            "| SDK action bindings "
            "(`engine/actions/sdk_actions.py` + `engine/actions/sdk_action_catalog.py`) "
            f"| {sdk_action_count} |"
        ),
        f"| Test files (`tests/test_*.py`) | {test_file_count} |",
        f"| Test functions (`def test_*`) | {test_fn_count} |",
        SNAPSHOT_END,
    ]
    return "\n".join(lines)


def main() -> None:
    project_root = bootstrap_project_root()
    candidates = [
        project_root / "docs" / "governance" / "project_progress.md",
        project_root / "docs" / "project_progress.md",
    ]
    progress_file = next((path for path in candidates if path.exists()), None)

    if progress_file is None:
        raise FileNotFoundError(
            "progress file not found: " + ", ".join(str(path) for path in candidates)
        )

    original = progress_file.read_text(encoding="utf-8")
    snapshot = _render_snapshot(project_root)

    if SNAPSHOT_START in original and SNAPSHOT_END in original:
        updated = re.sub(
            rf"{re.escape(SNAPSHOT_START)}[\s\S]*?{re.escape(SNAPSHOT_END)}",
            snapshot,
            original,
            count=1,
        )
    else:
        updated = f"{original.rstrip()}\n\n{snapshot}\n"

    _ = progress_file.write_text(updated, encoding="utf-8")
    print(f"updated: {progress_file}")


if __name__ == "__main__":
    main()
