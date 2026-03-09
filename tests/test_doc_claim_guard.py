from __future__ import annotations

# pyright: reportMissingImports=false, reportMissingModuleSource=false, reportUnknownMemberType=false

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Protocol, cast

import pytest
import yaml


class DocClaimToolModule(Protocol):
    def collect_doc_claim_problems(
        self,
        claims_path: Path,
        *,
        repo_root: Path,
        changed_paths: list[str | Path] | None = None,
    ) -> list[str]: ...


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _tool_path() -> Path:
    return _repo_root() / "tools" / "check_doc_claims.py"


def _load_tool_module() -> DocClaimToolModule:
    tool_path = _tool_path()
    if not tool_path.exists():
        pytest.fail(f"expected future validator at {tool_path}")

    spec = importlib.util.spec_from_file_location("check_doc_claims", tool_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(DocClaimToolModule, cast(object, module))


def _write_claim_inventory(repo_root: Path, claims: list[dict[str, object]]) -> Path:
    claims_path = repo_root / "config" / "doc_claims.yaml"
    claims_path.parent.mkdir(parents=True, exist_ok=True)
    _ = claims_path.write_text(yaml.safe_dump(claims, sort_keys=False), encoding="utf-8")
    return claims_path


def _seed_repo_files(repo_root: Path) -> None:
    for relative_path, content in {
        "README.md": "# Repo\n",
        "docs/project_progress.md": "# Progress\n",
        "docs/current_main_status.md": "# Status\n",
        "docs/HANDOFF.md": "# Handoff\n",
        ".sisyphus/notepads/example/learnings.md": "1. evidence\n2. more evidence\n",
        "engine/actions/example.py": "def run():\n    return True\n",
        "tests/test_example.py": "def test_example():\n    assert True\n",
        ".sisyphus/evidence/example.txt": "line 1\nline 2\n",
    }.items():
        target = repo_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(content, encoding="utf-8")


def _base_claim(**overrides: object) -> dict[str, object]:
    claim: dict[str, object] = {
        "claim_id": "bounded_example_claim",
        "status": "completed",
        "allowed_surfaces": [
            "README.md",
            "docs/project_progress.md",
            "docs/current_main_status.md",
            "docs/HANDOFF.md",
        ],
        "claim_type": "capability",
        "wording_note": "Keep this claim bounded to the implemented helper only.",
        "anchors": [
            "engine/actions/example.py:1-2",
            ".sisyphus/notepads/example/learnings.md:1-2",
        ],
        "verification_mode": "code_and_evidence",
        "blocking_level": "blocking",
    }
    for key, value in overrides.items():
        claim[key] = value
    return claim


def test_collect_doc_claim_problems_accepts_minimal_valid_inventory_shape(tmp_path: Path):
    repo_root = tmp_path
    _seed_repo_files(repo_root)
    claims_path = _write_claim_inventory(repo_root, [_base_claim()])

    module = _load_tool_module()
    problems = module.collect_doc_claim_problems(claims_path, repo_root=repo_root)

    assert problems == []


def test_collect_doc_claim_problems_reports_missing_required_fields(tmp_path: Path):
    repo_root = tmp_path
    _seed_repo_files(repo_root)
    claims_path = _write_claim_inventory(
        repo_root,
        [
            _base_claim(
                claim_id="missing-fields-claim",
                verification_mode=None,
                blocking_level=None,
            )
        ],
    )

    module = _load_tool_module()
    problems = module.collect_doc_claim_problems(claims_path, repo_root=repo_root)

    combined = "\n".join(problems).lower()
    assert "missing-fields-claim" in combined
    assert "missing" in combined
    assert "verification_mode" in combined
    assert "blocking_level" in combined


def test_collect_doc_claim_problems_reports_missing_anchor_targets(tmp_path: Path):
    repo_root = tmp_path
    _seed_repo_files(repo_root)
    claims_path = _write_claim_inventory(
        repo_root,
        [
            _base_claim(
                claim_id="missing-anchor-claim",
                anchors=["engine/actions/does_not_exist.py:1-4"],
            )
        ],
    )

    module = _load_tool_module()
    problems = module.collect_doc_claim_problems(claims_path, repo_root=repo_root)

    combined = "\n".join(problems).lower()
    assert "missing-anchor-claim" in combined
    assert "anchor" in combined
    assert "does_not_exist.py" in combined


def test_collect_doc_claim_problems_reports_forbidden_surface_claims(tmp_path: Path):
    repo_root = tmp_path
    _seed_repo_files(repo_root)
    claims_path = _write_claim_inventory(
        repo_root,
        [
            _base_claim(
                claim_id="validation-on-readme",
                claim_type="validation",
                allowed_surfaces=["README.md", "docs/project_progress.md"],
                wording_note="Keep this bounded to targeted validation evidence.",
                anchors=["tests/test_example.py:1-2", ".sisyphus/evidence/example.txt:1-2"],
                verification_mode="tests_plus_manual_evidence",
            )
        ],
    )

    module = _load_tool_module()
    problems = module.collect_doc_claim_problems(claims_path, repo_root=repo_root)

    combined = "\n".join(problems).lower()
    assert "validation-on-readme" in combined
    assert "surface" in combined
    assert "readme.md" in combined


def test_collect_doc_claim_problems_reports_missing_required_surface_phrase(tmp_path: Path):
    repo_root = tmp_path
    _seed_repo_files(repo_root)
    claims_path = _write_claim_inventory(
        repo_root,
        [
            _base_claim(
                claim_id="missing-surface-phrase",
                surface_assertions={
                    "README.md": {
                        "must_contain": ["nonexistent canonical phrase"],
                    }
                },
            )
        ],
    )

    module = _load_tool_module()
    problems = module.collect_doc_claim_problems(claims_path, repo_root=repo_root)

    combined = "\n".join(problems).lower()
    assert "missing-surface-phrase" in combined
    assert "missing required phrase" in combined
    assert "readme.md" in combined


def test_collect_doc_claim_problems_rejects_over_broad_next_step_claims(tmp_path: Path):
    repo_root = tmp_path
    _seed_repo_files(repo_root)
    claims_path = _write_claim_inventory(
        repo_root,
        [
            _base_claim(
                claim_id="overbroad-watchpoint",
                status="next_step",
                claim_type="watchpoint",
                allowed_surfaces=["docs/project_progress.md", "docs/current_main_status.md", "docs/HANDOFF.md"],
                wording_note="Describe this as already shipped across the platform with no remaining caveats.",
                anchors=[".sisyphus/evidence/example.txt:1-2"],
                verification_mode="evidence_gate",
                blocking_level="watchpoint",
            )
        ],
    )

    module = _load_tool_module()
    problems = module.collect_doc_claim_problems(claims_path, repo_root=repo_root)

    combined = "\n".join(problems).lower()
    assert "overbroad-watchpoint" in combined
    assert "over-broad" in combined or "downgrade" in combined
    assert "next_step" in combined or "watchpoint" in combined


def test_collect_doc_claim_problems_rejects_empty_file_anchor_line_reference(tmp_path: Path):
    repo_root = tmp_path
    _seed_repo_files(repo_root)
    empty_anchor_path = repo_root / ".sisyphus" / "evidence" / "empty.txt"
    empty_anchor_path.parent.mkdir(parents=True, exist_ok=True)
    _ = empty_anchor_path.write_text("", encoding="utf-8")
    claims_path = _write_claim_inventory(
        repo_root,
        [
            _base_claim(
                claim_id="empty-anchor-file",
                anchors=[".sisyphus/evidence/empty.txt:1"],
            )
        ],
    )

    module = _load_tool_module()
    problems = module.collect_doc_claim_problems(claims_path, repo_root=repo_root)

    combined = "\n".join(problems).lower()
    assert "empty-anchor-file" in combined
    assert "exceeds file length" in combined
    assert "0" in combined


def test_collect_doc_claim_problems_supports_changed_scope_filtering(tmp_path: Path):
    repo_root = tmp_path
    _seed_repo_files(repo_root)
    claims_path = _write_claim_inventory(
        repo_root,
        [
            _base_claim(
                claim_id="untouched-invalid-validation",
                claim_type="validation",
                allowed_surfaces=["docs/project_progress.md", "docs/current_main_status.md", "docs/HANDOFF.md"],
                wording_note="Keep this bounded to targeted validation evidence.",
                anchors=["tests/test_example.py:1-2", ".sisyphus/evidence/example.txt:1-2"],
                verification_mode="tests_plus_manual_evidence",
            ),
            _base_claim(claim_id="touched-valid-claim"),
        ],
    )

    module = _load_tool_module()
    problems = module.collect_doc_claim_problems(
        claims_path,
        repo_root=repo_root,
        changed_paths=["README.md"],
    )

    combined = "\n".join(problems).lower()
    assert "untouched-invalid-validation" not in combined
    assert problems == []


def test_collect_doc_claim_problems_treats_claim_inventory_change_as_full_validation(tmp_path: Path):
    repo_root = tmp_path
    _seed_repo_files(repo_root)
    claims_path = _write_claim_inventory(
        repo_root,
        [
            _base_claim(
                claim_id="inventory-only-invalid-validation",
                claim_type="validation",
                allowed_surfaces=["README.md", "docs/project_progress.md"],
                wording_note="Keep this bounded to targeted validation evidence.",
                anchors=["tests/test_example.py:1-2", ".sisyphus/evidence/example.txt:1-2"],
                verification_mode="tests_plus_manual_evidence",
            )
        ],
    )

    module = _load_tool_module()
    problems = module.collect_doc_claim_problems(
        claims_path,
        repo_root=repo_root,
        changed_paths=["config/doc_claims.yaml"],
    )

    combined = "\n".join(problems).lower()
    assert "inventory-only-invalid-validation" in combined
    assert "surface" in combined


def test_check_doc_claims_script_passes_for_current_repo_inventory():
    tool_path = _tool_path()
    assert tool_path.exists(), f"expected future validator at {tool_path}"

    result = subprocess.run(
        [sys.executable, str(tool_path)],
        check=True,
        capture_output=True,
        text=True,
        cwd=_repo_root(),
    )

    assert "OK" in result.stdout
