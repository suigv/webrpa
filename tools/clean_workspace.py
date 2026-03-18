from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

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


ROOT = bootstrap_project_root()
SKIP_DIR_NAMES: frozenset[str] = frozenset({".git", ".venv", "vendor", "node_modules"})
JUNK_DIR_NAMES: frozenset[str] = frozenset(
    {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
)
JUNK_FILE_NAMES: frozenset[str] = frozenset({".DS_Store"})
JUNK_FILE_SUFFIXES: frozenset[str] = frozenset({".pyc", ".pyo"})
OPTIONAL_ARTIFACT_DIRS: tuple[Path, ...] = (
    Path("web/dist"),
    Path("dist"),
    Path("build"),
)


@dataclass(frozen=True)
class CleanupTarget:
    path: Path
    reason: str
    size_bytes: int


def _path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file() or path.is_symlink():
        try:
            return path.stat().st_size
        except OSError:
            return 0

    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def _should_skip(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts
    return any(part in SKIP_DIR_NAMES for part in rel_parts)


def _iter_junk_targets(root: Path, *, include_build_artifacts: bool) -> list[CleanupTarget]:
    targets: dict[Path, CleanupTarget] = {}

    for artifact_rel in OPTIONAL_ARTIFACT_DIRS:
        artifact_path = root / artifact_rel
        if (
            include_build_artifacts
            and artifact_path.exists()
            and not _should_skip(artifact_path, root)
        ):
            targets[artifact_path] = CleanupTarget(
                path=artifact_path,
                reason="build artifact directory",
                size_bytes=_path_size(artifact_path),
            )

    for current_root, dirnames, filenames in os.walk(root, topdown=True):
        current = Path(current_root)
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIR_NAMES]

        for dirname in list(dirnames):
            if dirname in JUNK_DIR_NAMES:
                target = current / dirname
                targets[target] = CleanupTarget(
                    path=target,
                    reason="cache directory",
                    size_bytes=_path_size(target),
                )
                dirnames.remove(dirname)

        for filename in filenames:
            target = current / filename
            if filename in JUNK_FILE_NAMES:
                targets[target] = CleanupTarget(
                    path=target,
                    reason="OS metadata file",
                    size_bytes=_path_size(target),
                )
                continue
            if target.suffix in JUNK_FILE_SUFFIXES:
                targets[target] = CleanupTarget(
                    path=target,
                    reason="compiled Python artifact",
                    size_bytes=_path_size(target),
                )

    return sorted(targets.values(), key=lambda item: str(item.path.relative_to(root)))


def _iter_trace_targets(root: Path, *, retention_days: int | None) -> list[CleanupTarget]:
    if retention_days is None:
        return []

    traces_root = root / "config" / "data" / "traces"
    if not traces_root.exists():
        return []

    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    targets: list[CleanupTarget] = []
    for task_dir in sorted(path for path in traces_root.iterdir() if path.is_dir()):
        try:
            modified = datetime.fromtimestamp(task_dir.stat().st_mtime, UTC)
        except OSError:
            continue
        if modified >= cutoff:
            continue
        targets.append(
            CleanupTarget(
                path=task_dir,
                reason=f"trace directory older than {retention_days} days",
                size_bytes=_path_size(task_dir),
            )
        )
    return targets


def collect_cleanup_targets(
    root: Path = ROOT,
    *,
    include_build_artifacts: bool = True,
    trace_retention_days: int | None = None,
) -> list[CleanupTarget]:
    targets = {
        item.path: item
        for item in _iter_junk_targets(root, include_build_artifacts=include_build_artifacts)
    }
    for item in _iter_trace_targets(root, retention_days=trace_retention_days):
        targets[item.path] = item
    return sorted(targets.values(), key=lambda item: str(item.path.relative_to(root)))


def delete_targets(targets: list[CleanupTarget]) -> tuple[int, int]:
    removed_count = 0
    removed_bytes = 0
    for target in targets:
        path = target.path
        if not path.exists():
            continue
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed_count += 1
        removed_bytes += target.size_bytes
    return removed_count, removed_bytes


def _format_bytes(num_bytes: int) -> str:
    units = ["B", "KiB", "MiB", "GiB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely clean local cache/build artifacts and optionally old trace data"
    )
    _ = parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete files. Without this flag, the tool only reports targets.",
    )
    _ = parser.add_argument(
        "--no-build-artifacts",
        action="store_true",
        help="Do not include ignored build directories such as web/dist, dist, and build.",
    )
    _ = parser.add_argument(
        "--trace-retention-days",
        type=int,
        default=None,
        help="Also delete config/data/traces entries older than this many days.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    trace_retention_days = cast(int | None, args.trace_retention_days)
    if trace_retention_days is not None and trace_retention_days < 0:
        parser.error("--trace-retention-days must be >= 0")

    targets = collect_cleanup_targets(
        ROOT,
        include_build_artifacts=not cast(bool, args.no_build_artifacts),
        trace_retention_days=trace_retention_days,
    )
    total_bytes = sum(item.size_bytes for item in targets)

    if not targets:
        print("No cleanup targets found.")
        return 0

    mode = "APPLY" if cast(bool, args.apply) else "DRY-RUN"
    print(f"[{mode}] cleanup targets under {ROOT}")
    for item in targets:
        rel = item.path.relative_to(ROOT)
        print(f"- {rel} ({item.reason}, {_format_bytes(item.size_bytes)})")

    print(f"Total: {len(targets)} targets, {_format_bytes(total_bytes)}")
    if not cast(bool, args.apply):
        print("Re-run with --apply to delete these paths.")
        return 0

    removed_count, removed_bytes = delete_targets(targets)
    print(f"Removed: {removed_count} targets, {_format_bytes(removed_bytes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
