from __future__ import annotations

from datetime import date
from pathlib import Path

from tools.check_docs_freshness import CURRENT_DOCS, validate_docs_freshness


def _write_doc(path: Path, *, verified_at: str = "2026-03-24") -> None:
    path.write_text(
        "\n".join(
            [
                "---",
                "doc_type: current",
                "source_of_truth: current",
                "owner: repo",
                f"last_verified_at: {verified_at}",
                "stale_after_days: 14",
                "verification_method:",
                "  - repo audit",
                "---",
                "",
                f"# {path.name}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_validate_docs_freshness_accepts_current_docs_layout(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    for name in CURRENT_DOCS:
        _write_doc(docs_dir / name)

    errors = validate_docs_freshness(tmp_path, today=date(2026, 3, 24))

    assert errors == []


def test_validate_docs_freshness_rejects_extra_dirs_and_stale_docs(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    for name in CURRENT_DOCS:
        _write_doc(docs_dir / name)
    (docs_dir / "strategy").mkdir()
    _write_doc(docs_dir / "STATUS.md", verified_at="2026-03-01")

    errors = validate_docs_freshness(tmp_path, today=date(2026, 3, 24))

    assert "unexpected docs subdirectory: strategy" in errors
    assert any(error.startswith("STATUS.md: stale") for error in errors)
