from __future__ import annotations

import argparse
import importlib.util
import re
from collections import defaultdict
from collections.abc import Sequence
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
DEFAULT_EVIDENCE_ROOT = ROOT / ".sisyphus" / "evidence"
ALLOWED_DOCS_ONLY_COMMAND_TEXT = "docs-only, no runtime commands needed"
REQUIRED_KINDS: frozenset[str] = frozenset({"summary", "commands", "validation"})
NEW_STYLE_PATTERN = re.compile(
    r"^(?P<prefix>(?P<date>\d{8})-(?P<topic>[a-z0-9]+(?:-[a-z0-9]+)*))-(?P<kind>summary|commands|validation)\.(?P<ext>[A-Za-z0-9]+)$"
)


def _validate_commands_content(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return [f"{path.name}: commands evidence must not be empty"]

    lowered = text.lower()
    if "docs-only" in lowered and ALLOWED_DOCS_ONLY_COMMAND_TEXT not in text:
        return [
            f"{path.name}: docs-only command evidence must include the exact wording '{ALLOWED_DOCS_ONLY_COMMAND_TEXT}'"
        ]
    return []


def collect_evidence_chain_problems(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> list[str]:
    if not evidence_root.exists():
        return [f"evidence root not found: {evidence_root}"]
    if not evidence_root.is_dir():
        return [f"evidence root is not a directory: {evidence_root}"]

    problems: list[str] = []
    grouped: dict[str, set[str]] = defaultdict(set)

    for path in sorted(p for p in evidence_root.iterdir() if p.is_file()):
        name = path.name
        if name.startswith("task-"):
            continue

        match = NEW_STYLE_PATTERN.fullmatch(name)
        if match is None:
            problems.append(
                f"{name}: expected filename format YYYYMMDD-<topic>-{{summary,commands,validation}}.<ext> or grandfathered task-*"
            )
            continue

        prefix = match.group("prefix")
        kind = match.group("kind")
        grouped[prefix].add(kind)
        if kind == "commands":
            problems.extend(_validate_commands_content(path))

    for prefix in sorted(grouped):
        seen_kinds = grouped[prefix]
        missing_kinds = sorted(REQUIRED_KINDS - seen_kinds)
        if missing_kinds:
            problems.append(
                f"{prefix}: missing required evidence kinds: {', '.join(missing_kinds)}"
            )

    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate evidence-chain filename and triplet rules"
    )
    _ = parser.add_argument(
        "--evidence-root",
        default=str(DEFAULT_EVIDENCE_ROOT),
        help="Path to the evidence directory (default: .sisyphus/evidence)",
    )
    args = parser.parse_args(argv)

    evidence_root_arg = cast(str, args.evidence_root)
    evidence_root = Path(evidence_root_arg)
    if not evidence_root.is_absolute():
        evidence_root = ROOT / evidence_root

    problems = collect_evidence_chain_problems(evidence_root)
    if problems:
        print("Evidence chain validation failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print("OK: evidence chains are complete, well-named, and docs-only wording is allowed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
