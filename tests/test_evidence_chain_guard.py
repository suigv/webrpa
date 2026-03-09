from __future__ import annotations

# pyright: reportMissingImports=false, reportMissingModuleSource=false, reportUnknownMemberType=false

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Protocol, cast

import pytest


class EvidenceToolModule(Protocol):
    ALLOWED_DOCS_ONLY_COMMAND_TEXT: str

    def collect_evidence_chain_problems(self, evidence_root: Path = ...) -> list[str]: ...


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _tool_path() -> Path:
    return _repo_root() / "tools" / "check_evidence_chain.py"


def _load_tool_module() -> EvidenceToolModule:
    tool_path = _tool_path()
    if not tool_path.exists():
        pytest.fail(f"expected future validator at {tool_path}")

    spec = importlib.util.spec_from_file_location("check_evidence_chain", tool_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(EvidenceToolModule, cast(object, module))


def _write_evidence_file(evidence_root: Path, name: str, content: str) -> None:
    evidence_root.mkdir(parents=True, exist_ok=True)
    _ = (evidence_root / name).write_text(content, encoding="utf-8")


def _seed_new_triplet(
    evidence_root: Path,
    *,
    prefix: str = "20260309-doc-code-alignment",
    commands_content: str | None = None,
) -> None:
    _write_evidence_file(evidence_root, f"{prefix}-summary.md", "# Summary\n")
    _write_evidence_file(
        evidence_root,
        f"{prefix}-commands.md",
        commands_content if commands_content is not None else "```bash\npython -m pytest\n```\n",
    )
    _write_evidence_file(evidence_root, f"{prefix}-validation.md", "# Validation\n")


def test_collect_evidence_chain_problems_accepts_valid_triplet(tmp_path: Path):
    evidence_root = tmp_path / ".sisyphus" / "evidence"
    _seed_new_triplet(evidence_root)

    module = _load_tool_module()
    problems = module.collect_evidence_chain_problems(evidence_root)

    assert problems == []


def test_collect_evidence_chain_problems_accepts_docs_only_exact_wording(tmp_path: Path):
    evidence_root = tmp_path / ".sisyphus" / "evidence"
    module = _load_tool_module()
    _seed_new_triplet(evidence_root, commands_content=module.ALLOWED_DOCS_ONLY_COMMAND_TEXT)

    problems = module.collect_evidence_chain_problems(evidence_root)

    assert problems == []


def test_collect_evidence_chain_problems_rejects_incomplete_new_triplet(tmp_path: Path):
    evidence_root = tmp_path / ".sisyphus" / "evidence"
    _write_evidence_file(evidence_root, "20260309-doc-code-alignment-summary.md", "# Summary\n")
    _write_evidence_file(evidence_root, "20260309-doc-code-alignment-validation.md", "# Validation\n")

    module = _load_tool_module()
    problems = module.collect_evidence_chain_problems(evidence_root)

    combined = "\n".join(problems).lower()
    assert "20260309-doc-code-alignment" in combined
    assert "missing required evidence kinds" in combined
    assert "commands" in combined


def test_collect_evidence_chain_problems_rejects_malformed_new_filename(tmp_path: Path):
    evidence_root = tmp_path / ".sisyphus" / "evidence"
    _write_evidence_file(evidence_root, "docs-progress-sync-summary.md", "# Summary\n")

    module = _load_tool_module()
    problems = module.collect_evidence_chain_problems(evidence_root)

    combined = "\n".join(problems).lower()
    assert "docs-progress-sync-summary.md" in combined
    assert "expected filename format" in combined


def test_collect_evidence_chain_problems_rejects_inexact_docs_only_wording(tmp_path: Path):
    evidence_root = tmp_path / ".sisyphus" / "evidence"
    _seed_new_triplet(evidence_root, commands_content="docs-only; no runtime commands needed\n")

    module = _load_tool_module()
    problems = module.collect_evidence_chain_problems(evidence_root)

    combined = "\n".join(problems).lower()
    assert "docs-only command evidence" in combined
    assert "exact wording" in combined


def test_collect_evidence_chain_problems_grandfathers_task_files(tmp_path: Path):
    evidence_root = tmp_path / ".sisyphus" / "evidence"
    _write_evidence_file(evidence_root, "task-7-recovery-gate.txt", "legacy evidence\n")

    module = _load_tool_module()
    problems = module.collect_evidence_chain_problems(evidence_root)

    assert problems == []


def test_check_evidence_chain_script_passes_for_current_repo_evidence():
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
