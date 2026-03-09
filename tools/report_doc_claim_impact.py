from __future__ import annotations

# pyright: reportMissingModuleSource=false

import argparse
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import cast

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLAIMS_PATH = ROOT / "config" / "doc_claims.yaml"
ANCHOR_PATTERN = re.compile(r"^(?P<path>[^:]+):(?P<start>\d+)(?:-(?P<end>\d+))?$")


def _normalize_repo_relative_path(path_text: str, *, repo_root: Path) -> str:
    relative_path = Path(path_text)
    if relative_path.is_absolute():
        raise ValueError(f"expected repo-relative path, got absolute path: {path_text}")
    resolved_path = (repo_root / relative_path).resolve()
    try:
        return resolved_path.relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"path escapes repo root: {path_text}") from exc


def _load_claims(claims_path: Path) -> list[dict[str, object]]:
    loaded = cast(object, yaml.safe_load(claims_path.read_text(encoding="utf-8")))
    if loaded is None:
        return []
    if not isinstance(loaded, list):
        raise ValueError(f"claims file must contain a top-level list: {claims_path}")

    claims: list[dict[str, object]] = []
    for item in cast(list[object], loaded):
        if not isinstance(item, dict):
            raise ValueError(f"claims file entries must be mappings: {claims_path}")
        claims.append(cast(dict[str, object], item))
    return claims


def _claim_label(claim: dict[str, object], *, index: int) -> str:
    claim_id = claim.get("claim_id")
    if isinstance(claim_id, str) and claim_id.strip():
        return claim_id
    return f"claim #{index}"


def _normalize_surfaces(raw_surfaces: object, *, repo_root: Path) -> list[str]:
    if not isinstance(raw_surfaces, list):
        return []

    surfaces: list[str] = []
    for surface in cast(list[object], raw_surfaces):
        if isinstance(surface, str) and surface.strip():
            surfaces.append(_normalize_repo_relative_path(surface, repo_root=repo_root))
    return surfaces


def _anchor_paths(raw_anchors: object, *, repo_root: Path) -> list[str]:
    if not isinstance(raw_anchors, list):
        return []

    anchor_paths: list[str] = []
    for anchor in cast(list[object], raw_anchors):
        if not isinstance(anchor, str) or not anchor.strip():
            continue
        match = ANCHOR_PATTERN.fullmatch(anchor.strip())
        if match is None:
            continue
        anchor_paths.append(_normalize_repo_relative_path(match.group("path"), repo_root=repo_root))
    return anchor_paths


def _collect_changed_paths(
    *,
    repo_root: Path,
    changed_paths: Iterable[str | Path],
    changed_paths_file: Path | None,
) -> list[str]:
    normalized: set[str] = set()
    for changed_path in changed_paths:
        normalized.add(_normalize_repo_relative_path(str(changed_path), repo_root=repo_root))

    if changed_paths_file is not None:
        for line in changed_paths_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                normalized.add(_normalize_repo_relative_path(line.strip(), repo_root=repo_root))

    return sorted(normalized)


def build_claim_impact_report(
    claims_path: Path,
    *,
    repo_root: Path,
    changed_paths: Iterable[str | Path] = (),
    changed_paths_file: Path | None = None,
) -> list[str]:
    normalized_changed_paths = _collect_changed_paths(
        repo_root=repo_root,
        changed_paths=changed_paths,
        changed_paths_file=changed_paths_file,
    )
    if not normalized_changed_paths:
        return ["Advisory only: no changed paths supplied; skipping doc-claim impact report."]

    changed_path_set = set(normalized_changed_paths)
    claims = _load_claims(claims_path)
    report_lines = [
        "Doc claim impact report (advisory only)",
        f"Changed paths analyzed: {len(normalized_changed_paths)}",
    ]

    impacted: list[tuple[str, str, str, list[str], list[str]]] = []
    for index, claim in enumerate(claims, start=1):
        claim_label = _claim_label(claim, index=index)
        matched_surfaces = sorted(changed_path_set & set(_normalize_surfaces(claim.get("allowed_surfaces"), repo_root=repo_root)))
        matched_anchors = sorted(changed_path_set & set(_anchor_paths(claim.get("anchors"), repo_root=repo_root)))
        if not matched_surfaces and not matched_anchors:
            continue

        status = str(claim.get("status", "unknown"))
        claim_type = str(claim.get("claim_type", "unknown"))
        impacted.append((claim_label, status, claim_type, matched_surfaces, matched_anchors))

    if not impacted:
        report_lines.append("No claim inventory overlap detected for the supplied paths.")
        return report_lines

    report_lines.append(f"Impacted claims: {len(impacted)}")
    for claim_label, status, claim_type, matched_surfaces, matched_anchors in impacted:
        report_lines.append(f"- {claim_label} [{status}/{claim_type}]")
        if matched_anchors:
            report_lines.append(f"  - anchor overlap: {', '.join(matched_anchors)}")
        if matched_surfaces:
            report_lines.append(f"  - surface overlap: {', '.join(matched_surfaces)}")
    return report_lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report bounded doc-claim impact for changed paths")
    _ = parser.add_argument(
        "changed_paths",
        nargs="*",
        help="Optional repo-relative changed paths to analyze against the claim inventory.",
    )
    _ = parser.add_argument(
        "--changed-paths-file",
        help="Optional file containing one repo-relative changed path per line.",
    )
    _ = parser.add_argument(
        "--claims-path",
        default=str(DEFAULT_CLAIMS_PATH),
        help="Path to the YAML claim inventory (default: config/doc_claims.yaml)",
    )
    args = parser.parse_args(argv)

    claims_path = Path(cast(str, args.claims_path))
    if not claims_path.is_absolute():
        claims_path = ROOT / claims_path

    changed_paths_file_arg = cast(str | None, args.changed_paths_file)
    changed_paths_file: Path | None = None
    if changed_paths_file_arg:
        changed_paths_file = Path(changed_paths_file_arg)
        if not changed_paths_file.is_absolute():
            changed_paths_file = ROOT / changed_paths_file

    report_lines = build_claim_impact_report(
        claims_path,
        repo_root=ROOT,
        changed_paths=cast(list[str], args.changed_paths),
        changed_paths_file=changed_paths_file,
    )
    print("\n".join(report_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
