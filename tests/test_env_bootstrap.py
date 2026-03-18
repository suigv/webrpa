from __future__ import annotations

import os
from pathlib import Path

from core.env_bootstrap import load_project_dotenv


def test_load_project_dotenv_populates_missing_env_vars(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "MYT_LLM_API_KEY=from-dotenv",
                "export OPENAI_API_KEY='openai-from-dotenv'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("core.env_bootstrap.project_root", lambda: tmp_path)
    monkeypatch.setenv("MYT_LOAD_DOTENV", "1")
    monkeypatch.delenv("MYT_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    load_project_dotenv()

    assert os.environ["MYT_LLM_API_KEY"] == "from-dotenv"
    assert os.environ["OPENAI_API_KEY"] == "openai-from-dotenv"


def test_load_project_dotenv_does_not_override_existing_env_vars(
    monkeypatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("MYT_LLM_API_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.setattr("core.env_bootstrap.project_root", lambda: tmp_path)
    monkeypatch.setenv("MYT_LOAD_DOTENV", "1")
    monkeypatch.setenv("MYT_LLM_API_KEY", "already-set")

    load_project_dotenv()

    assert os.environ["MYT_LLM_API_KEY"] == "already-set"
