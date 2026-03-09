from __future__ import annotations

# pyright: reportMissingModuleSource=false

import argparse
import re
from collections.abc import Collection, Iterable, Sequence
from pathlib import Path
from typing import cast

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLAIMS_PATH = ROOT / "config" / "doc_claims.yaml"
DEFAULT_CLAIMS_PATH_RELATIVE = DEFAULT_CLAIMS_PATH.relative_to(ROOT).as_posix()
REQUIRED_FIELDS: tuple[str, ...] = (
    "claim_id",
    "status",
    "allowed_surfaces",
    "claim_type",
    "wording_note",
    "anchors",
    "verification_mode",
    "blocking_level",
)
SURFACE_ASSERTION_KEYS: tuple[str, ...] = ("must_contain", "must_not_contain")
ANCHOR_PATTERN = re.compile(r"^(?P<path>[^:]+):(?P<start>\d+)(?:-(?P<end>\d+))?$")
OVERBROAD_NEXT_STEP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\balready shipped\b", re.IGNORECASE),
    re.compile(r"\bshipped across the platform\b", re.IGNORECASE),
    re.compile(r"\bcompleted rollout\b", re.IGNORECASE),
    re.compile(r"\bno remaining caveats\b", re.IGNORECASE),
    re.compile(r"\bfully implemented\b", re.IGNORECASE),
)
SURFACE_RULES: dict[tuple[str, str], dict[str, tuple[str, ...]]] = {
    ("completed", "capability"): {
        "required": ("README.md", "docs/project_progress.md", "docs/current_main_status.md", "docs/HANDOFF.md"),
        "allowed": ("README.md", "docs/project_progress.md", "docs/current_main_status.md", "docs/HANDOFF.md"),
    },
    ("completed", "contract"): {
        "required": ("README.md", "docs/project_progress.md", "docs/current_main_status.md", "docs/HANDOFF.md"),
        "allowed": ("README.md", "docs/project_progress.md", "docs/current_main_status.md", "docs/HANDOFF.md"),
    },
    ("completed", "workflow"): {
        "required": ("README.md", "docs/project_progress.md", "docs/current_main_status.md", "docs/HANDOFF.md"),
        "allowed": ("README.md", "docs/project_progress.md", "docs/current_main_status.md", "docs/HANDOFF.md"),
    },
    ("completed", "validation"): {
        "required": ("docs/project_progress.md", "docs/current_main_status.md", "docs/HANDOFF.md"),
        "allowed": ("docs/project_progress.md", "docs/current_main_status.md", "docs/HANDOFF.md"),
    },
    ("deferred", "status"): {
        "required": ("README.md", "docs/project_progress.md", "docs/current_main_status.md", "docs/HANDOFF.md", "docs/README.md"),
        "allowed": ("README.md", "docs/project_progress.md", "docs/current_main_status.md", "docs/HANDOFF.md", "docs/README.md"),
    },
    ("next_step", "watchpoint"): {
        "required": ("docs/project_progress.md", "docs/current_main_status.md", "docs/HANDOFF.md"),
        "allowed": ("docs/project_progress.md", "docs/current_main_status.md", "docs/HANDOFF.md"),
    },
}


def _normalize_repo_relative_path(path_text: str, *, repo_root: Path) -> str:
    relative_path = Path(path_text)
    if relative_path.is_absolute():
        raise ValueError(f"expected repo-relative path, got absolute path: {path_text}")
    resolved_path = (repo_root / relative_path).resolve()
    try:
        return resolved_path.relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"path escapes repo root: {path_text}") from exc


def _load_claims(claims_path: Path) -> tuple[list[dict[str, object]], list[str]]:
    if not claims_path.exists():
        return [], [f"claims file not found: {claims_path}"]

    loaded = cast(object, yaml.safe_load(claims_path.read_text(encoding="utf-8")))
    if loaded is None:
        return [], []
    if not isinstance(loaded, list):
        return [], [f"claims file must contain a top-level list: {claims_path}"]

    problems: list[str] = []
    claims: list[dict[str, object]] = []
    loaded_items = cast(list[object], loaded)
    for index, item in enumerate(loaded_items, start=1):
        if not isinstance(item, dict):
            problems.append(f"claim #{index}: expected mapping entry, got {type(item).__name__}")
            continue
        claims.append(cast(dict[str, object], item))
    return claims, problems


def _missing_required_fields(claim: dict[str, object]) -> list[str]:
    missing: list[str] = []
    for field_name in REQUIRED_FIELDS:
        value = claim.get(field_name)
        if value is None:
            missing.append(field_name)
        elif isinstance(value, str) and not value.strip():
            missing.append(field_name)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) == 0:
            missing.append(field_name)
    return missing


def _claim_label(claim: dict[str, object], *, index: int) -> str:
    claim_id = claim.get("claim_id")
    if isinstance(claim_id, str) and claim_id.strip():
        return claim_id
    return f"claim #{index}"


def _validate_anchor(anchor_text: str, *, claim_label: str, repo_root: Path) -> list[str]:
    match = ANCHOR_PATTERN.fullmatch(anchor_text.strip())
    if match is None:
        return [f"{claim_label}: anchor has invalid format: {anchor_text}"]

    anchor_path_text = match.group("path")
    try:
        normalized_anchor_path = _normalize_repo_relative_path(anchor_path_text, repo_root=repo_root)
    except ValueError as exc:
        return [f"{claim_label}: anchor path error for {anchor_text}: {exc}"]

    anchor_path = repo_root / normalized_anchor_path
    if not anchor_path.exists():
        return [f"{claim_label}: anchor target missing: {normalized_anchor_path}"]
    if not anchor_path.is_file():
        return [f"{claim_label}: anchor target is not a file: {normalized_anchor_path}"]

    start_line = int(match.group("start"))
    end_group = match.group("end")
    end_line = int(end_group) if end_group is not None else start_line
    if start_line <= 0 or end_line <= 0 or end_line < start_line:
        return [f"{claim_label}: anchor line range is invalid: {anchor_text}"]

    line_count = len(anchor_path.read_text(encoding="utf-8").splitlines())
    if end_line > line_count:
        return [
            f"{claim_label}: anchor line range exceeds file length for {normalized_anchor_path}: {start_line}-{end_line} > {line_count}"
        ]
    return []


def _normalize_surfaces(raw_surfaces: object, *, claim_label: str, repo_root: Path) -> tuple[list[str], list[str]]:
    if not isinstance(raw_surfaces, list):
        return [], [f"{claim_label}: allowed_surfaces must be a non-empty list"]

    normalized: list[str] = []
    problems: list[str] = []
    for surface in cast(list[object], raw_surfaces):
        if not isinstance(surface, str) or not surface.strip():
            problems.append(f"{claim_label}: allowed_surfaces entries must be non-empty strings")
            continue
        try:
            normalized.append(_normalize_repo_relative_path(surface, repo_root=repo_root))
        except ValueError as exc:
            problems.append(f"{claim_label}: allowed surface path error for {surface}: {exc}")
    if not normalized:
        problems.append(f"{claim_label}: allowed_surfaces must be a non-empty list")
    return normalized, problems


def _normalize_surface_assertions(
    raw_assertions: object,
    *,
    claim_label: str,
    repo_root: Path,
    allowed_surfaces: Collection[str],
) -> tuple[dict[str, dict[str, list[str]]], list[str]]:
    if raw_assertions is None:
        return {}, []
    if not isinstance(raw_assertions, dict):
        return {}, [f"{claim_label}: surface_assertions must be a mapping when provided"]

    normalized: dict[str, dict[str, list[str]]] = {}
    problems: list[str] = []
    allowed_surface_set = set(allowed_surfaces)
    for raw_surface, raw_rules in cast(dict[object, object], raw_assertions).items():
        if not isinstance(raw_surface, str) or not raw_surface.strip():
            problems.append(f"{claim_label}: surface_assertions keys must be non-empty strings")
            continue
        try:
            surface = _normalize_repo_relative_path(raw_surface, repo_root=repo_root)
        except ValueError as exc:
            problems.append(f"{claim_label}: surface_assertions path error for {raw_surface}: {exc}")
            continue
        if surface not in allowed_surface_set:
            problems.append(f"{claim_label}: surface_assertions surface is not listed in allowed_surfaces: {surface}")
            continue
        if not isinstance(raw_rules, dict):
            problems.append(f"{claim_label}: surface_assertions entry for {surface} must be a mapping")
            continue

        normalized_rules: dict[str, list[str]] = {}
        for key in SURFACE_ASSERTION_KEYS:
            raw_phrases = cast(dict[str, object], raw_rules).get(key)
            if raw_phrases is None:
                continue
            if not isinstance(raw_phrases, list):
                problems.append(f"{claim_label}: surface_assertions {surface} {key} must be a list")
                continue
            phrases: list[str] = []
            for phrase in cast(list[object], raw_phrases):
                if not isinstance(phrase, str) or not phrase.strip():
                    problems.append(f"{claim_label}: surface_assertions {surface} {key} entries must be non-empty strings")
                    continue
                phrases.append(phrase)
            if phrases:
                normalized_rules[key] = phrases
        normalized[surface] = normalized_rules
    return normalized, problems


def _should_validate_claim_surfaces(
    *,
    allowed_surfaces: Collection[str],
    changed_paths: Collection[str] | None,
    claims_path_relative: str,
) -> bool:
    if changed_paths is None:
        return True
    if claims_path_relative in changed_paths:
        return True
    return any(surface in changed_paths for surface in allowed_surfaces)


def _validate_surface_assertions(
    surface_assertions: dict[str, dict[str, list[str]]],
    *,
    claim_label: str,
    repo_root: Path,
) -> list[str]:
    problems: list[str] = []
    for surface, rules in surface_assertions.items():
        surface_path = repo_root / surface
        if not surface_path.exists():
            problems.append(f"{claim_label}: canonical surface missing for surface_assertions: {surface}")
            continue
        if not surface_path.is_file():
            problems.append(f"{claim_label}: canonical surface is not a file for surface_assertions: {surface}")
            continue
        surface_text = surface_path.read_text(encoding="utf-8")
        for phrase in rules.get("must_contain", []):
            if phrase not in surface_text:
                problems.append(f"{claim_label}: canonical surface missing required phrase in {surface}: {phrase}")
        for phrase in rules.get("must_not_contain", []):
            if phrase in surface_text:
                problems.append(f"{claim_label}: canonical surface contains forbidden phrase in {surface}: {phrase}")
    return problems


def _validate_surface_rules(
    claim: dict[str, object],
    *,
    claim_label: str,
    allowed_surfaces: Collection[str],
) -> list[str]:
    status = claim.get("status")
    claim_type = claim.get("claim_type")
    if not isinstance(status, str) or not isinstance(claim_type, str):
        return []

    surface_rule = SURFACE_RULES.get((status, claim_type))
    if surface_rule is None:
        return [f"{claim_label}: unsupported status/claim_type combination: {status}/{claim_type}"]

    surface_set = set(allowed_surfaces)
    required_surfaces = set(surface_rule["required"])
    allowed_surface_set = set(surface_rule["allowed"])

    problems: list[str] = []
    missing_surfaces = sorted(required_surfaces - surface_set)
    if missing_surfaces:
        problems.append(
            f"{claim_label}: missing required canonical surfaces for {status}/{claim_type}: {', '.join(missing_surfaces)}"
        )

    forbidden_surfaces = sorted(surface_set - allowed_surface_set)
    if forbidden_surfaces:
        problems.append(
            f"{claim_label}: forbidden surface usage for {status}/{claim_type}: {', '.join(forbidden_surfaces)}"
        )

    return problems


def _validate_wording_bounds(claim: dict[str, object], *, claim_label: str) -> list[str]:
    status = claim.get("status")
    claim_type = claim.get("claim_type")
    wording_note = claim.get("wording_note")
    if not isinstance(wording_note, str):
        return []
    if status != "next_step" and claim_type != "watchpoint":
        return []

    for pattern in OVERBROAD_NEXT_STEP_PATTERNS:
        if pattern.search(wording_note):
            return [
                f"{claim_label}: over-broad {status}/{claim_type} wording_note; keep next_step/watchpoint claims framed as pending watchpoints"
            ]
    return []


def collect_doc_claim_problems(
    claims_path: Path,
    *,
    repo_root: Path,
    changed_paths: Iterable[str | Path] | None = None,
) -> list[str]:
    claims, problems = _load_claims(claims_path)
    claims_path_relative = _normalize_repo_relative_path(str(claims_path.relative_to(repo_root)), repo_root=repo_root)
    normalized_changed_paths: set[str] | None = None
    if changed_paths is not None:
        normalized_changed_paths = set()
        for changed_path in changed_paths:
            normalized_changed_paths.add(_normalize_repo_relative_path(str(changed_path), repo_root=repo_root))

    for index, claim in enumerate(claims, start=1):
        claim_label = _claim_label(claim, index=index)

        missing_fields = _missing_required_fields(claim)
        if missing_fields:
            problems.append(f"{claim_label}: missing required fields: {', '.join(missing_fields)}")
            continue

        raw_anchors = claim.get("anchors")
        if not isinstance(raw_anchors, list):
            problems.append(f"{claim_label}: anchors must be a non-empty list")
            continue
        for anchor in cast(list[object], raw_anchors):
            if not isinstance(anchor, str) or not anchor.strip():
                problems.append(f"{claim_label}: anchors entries must be non-empty strings")
                continue
            problems.extend(_validate_anchor(anchor, claim_label=claim_label, repo_root=repo_root))

        allowed_surfaces, surface_shape_problems = _normalize_surfaces(
            claim.get("allowed_surfaces"),
            claim_label=claim_label,
            repo_root=repo_root,
        )
        problems.extend(surface_shape_problems)
        surface_assertions, surface_assertion_shape_problems = _normalize_surface_assertions(
            claim.get("surface_assertions"),
            claim_label=claim_label,
            repo_root=repo_root,
            allowed_surfaces=allowed_surfaces,
        )
        problems.extend(surface_assertion_shape_problems)

        if allowed_surfaces and _should_validate_claim_surfaces(
            allowed_surfaces=allowed_surfaces,
            changed_paths=normalized_changed_paths,
            claims_path_relative=claims_path_relative,
        ):
            problems.extend(
                _validate_surface_rules(
                    claim,
                    claim_label=claim_label,
                    allowed_surfaces=allowed_surfaces,
                )
            )
            problems.extend(_validate_wording_bounds(claim, claim_label=claim_label))
            problems.extend(
                _validate_surface_assertions(
                    surface_assertions,
                    claim_label=claim_label,
                    repo_root=repo_root,
                )
            )

    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate bounded doc claim inventory")
    _ = parser.add_argument(
        "changed_paths",
        nargs="*",
        help="Optional repo-relative changed paths; when provided, surface/wording checks are limited to matching claims.",
    )
    _ = parser.add_argument(
        "--claims-path",
        default=str(DEFAULT_CLAIMS_PATH),
        help="Path to the YAML claim inventory (default: config/doc_claims.yaml)",
    )
    args = parser.parse_args(argv)
    claims_path_arg = cast(str, args.claims_path)
    changed_paths_arg = cast(list[str], args.changed_paths)

    claims_path = Path(claims_path_arg)
    if not claims_path.is_absolute():
        claims_path = ROOT / claims_path

    problems = collect_doc_claim_problems(
        claims_path,
        repo_root=ROOT,
        changed_paths=changed_paths_arg or None,
    )
    if problems:
        print("Doc claim validation failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print("OK: doc claim inventory is structurally valid and canonically bounded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
