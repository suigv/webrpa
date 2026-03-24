from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

CURRENT_DOCS = {
    "AI_ONBOARDING.md",
    "CONFIGURATION.md",
    "FRONTEND.md",
    "HTTP_API.md",
    "PLUGIN_CONTRACT.md",
    "README.md",
    "STATUS.md",
}
DOCS_SCOPE_HINT = (
    "docs/ only accepts current, verifiable docs; temporary plans, progress logs, "
    "migration drafts, and implementation history must live outside docs/"
)
REQUIRED_META = {
    "doc_type",
    "source_of_truth",
    "owner",
    "last_verified_at",
    "stale_after_days",
    "verification_method",
}


@dataclass
class DocMeta:
    doc_type: str
    source_of_truth: str
    owner: str
    last_verified_at: date
    stale_after_days: int
    verification_method: object


def _parse_front_matter(content: str) -> dict[str, object]:
    if not content.startswith("---\n"):
        raise ValueError("missing YAML front matter")
    _, _, remainder = content.partition("---\n")
    front_matter, marker, _ = remainder.partition("\n---\n")
    if not marker:
        raise ValueError("unterminated YAML front matter")
    data = yaml.safe_load(front_matter)
    if not isinstance(data, dict):
        raise ValueError("front matter must be a mapping")
    return {str(key): value for key, value in data.items()}


def _load_doc_meta(path: Path) -> DocMeta:
    raw = path.read_text(encoding="utf-8")
    data = _parse_front_matter(raw)
    missing = REQUIRED_META.difference(data)
    if missing:
        rendered = ", ".join(sorted(missing))
        raise ValueError(f"missing front matter keys: {rendered}")

    if str(data["doc_type"]) != "current":
        raise ValueError("doc_type must be 'current'")
    if str(data["source_of_truth"]) != "current":
        raise ValueError("source_of_truth must be 'current'")

    try:
        verified_at = date.fromisoformat(str(data["last_verified_at"]))
    except ValueError as exc:
        raise ValueError("last_verified_at must use YYYY-MM-DD") from exc

    try:
        stale_after_days = int(data["stale_after_days"])
    except (TypeError, ValueError) as exc:
        raise ValueError("stale_after_days must be an integer") from exc
    if stale_after_days <= 0:
        raise ValueError("stale_after_days must be > 0")

    verification_method = data["verification_method"]
    if not verification_method:
        raise ValueError("verification_method must not be empty")

    return DocMeta(
        doc_type="current",
        source_of_truth="current",
        owner=str(data["owner"]),
        last_verified_at=verified_at,
        stale_after_days=stale_after_days,
        verification_method=verification_method,
    )


def validate_docs_freshness(project_root: Path, *, today: date | None = None) -> list[str]:
    today = today or date.today()
    docs_dir = project_root / "docs"
    errors: list[str] = []

    if not docs_dir.exists():
        return ["docs directory is missing"]

    entries = list(docs_dir.iterdir())
    for entry in sorted(entries):
        if entry.is_dir():
            errors.append(f"unexpected docs subdirectory: {entry.name} ({DOCS_SCOPE_HINT})")
            continue
        if entry.name not in CURRENT_DOCS:
            errors.append(f"unexpected docs file: {entry.name} ({DOCS_SCOPE_HINT})")

    for name in sorted(CURRENT_DOCS):
        path = docs_dir / name
        if not path.exists():
            errors.append(f"missing current doc: {name}")
            continue
        try:
            meta = _load_doc_meta(path)
        except ValueError as exc:
            errors.append(f"{name}: {exc}")
            continue

        age_days = (today - meta.last_verified_at).days
        if age_days > meta.stale_after_days:
            errors.append(f"{name}: stale ({age_days} days old, limit {meta.stale_after_days})")

    return errors


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    errors = validate_docs_freshness(project_root)
    if errors:
        print("docs freshness check failed:")
        for error in errors:
            print(f"- {error}")
        print(f"policy: {DOCS_SCOPE_HINT}")
        return 1
    print("docs freshness check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
