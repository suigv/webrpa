# pyright: reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false

"""Tests for LLMDraftRefiner side-car distillation refinement."""

import json
from pathlib import Path
from typing import Any

import yaml

from core.golden_run_distillation import GoldenRunDraft, LLMDraftRefiner
from engine.models.manifest import PluginManifest
from engine.models.workflow import ActionStep, WorkflowScript


class _FakeLLMResponse:
    def __init__(self, ok: bool, output_text: str = "") -> None:
        self.ok = ok
        self.output_text = output_text
        self.error = None


class _FakeLLMClient:
    def __init__(self, response: _FakeLLMResponse) -> None:
        self._response = response
        self.calls: list[dict[str, object]] = []

    def evaluate(self, request: Any, **kwargs: Any) -> _FakeLLMResponse:
        self.calls.append({"prompt": request.prompt})
        return self._response


def _write_draft(tmp_path: Path) -> GoldenRunDraft:
    """Create a minimal draft with a hardcoded business value."""
    manifest = PluginManifest(
        api_version="v1",
        kind="plugin",
        name="test_flow",
        version="0.1.0",
        display_name="Test Flow",
        category="AI Drafts",
        inputs=[],
    )
    script = WorkflowScript(
        version="v1",
        workflow="test_flow",
        steps=[
            ActionStep(
                kind="action",
                action="ui.input_text",
                params={"text": "hello@example.com"},
            ),
            ActionStep(
                kind="action",
                action="ui.click",
                params={"text": "Submit"},
            ),
        ],
    )

    output_dir = tmp_path / "draft"
    output_dir.mkdir()
    manifest_path = output_dir / "manifest.yaml"
    script_path = output_dir / "script.yaml"
    manifest_path.write_text(
        yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    script_path.write_text(
        yaml.safe_dump(script.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return GoldenRunDraft(
        manifest=manifest,
        script=script,
        output_dir=output_dir,
        manifest_path=manifest_path,
        script_path=script_path,
    )


def test_llm_refiner_applies_replacement(tmp_path: Path) -> None:
    """LLM suggests replacing an email with a payload variable."""
    draft = _write_draft(tmp_path)
    llm_response = _FakeLLMResponse(
        ok=True,
        output_text=json.dumps(
            {
                "replacements": [
                    {
                        "original_value": "hello@example.com",
                        "variable_name": "user_email",
                        "input_type": "string",
                        "description": "the email to input",
                    }
                ]
            }
        ),
    )
    client = _FakeLLMClient(llm_response)
    refiner = LLMDraftRefiner(llm_client=client)
    refined = refiner.refine(draft, [])

    # Script should now contain the template variable
    script_text = refined.script_path.read_text(encoding="utf-8")
    assert "${payload.user_email}" in script_text
    assert "hello@example.com" not in script_text

    # Manifest should now have the new input
    manifest_data = yaml.safe_load(refined.manifest_path.read_text(encoding="utf-8"))
    input_names = [inp["name"] for inp in manifest_data.get("inputs", [])]
    assert "user_email" in input_names

    # The returned models should be valid
    assert refined.manifest is not None
    assert refined.script is not None


def test_llm_refiner_returns_original_on_llm_failure(tmp_path: Path) -> None:
    """When LLM returns an error, the original draft is returned unchanged."""
    draft = _write_draft(tmp_path)
    original_script = draft.script_path.read_text(encoding="utf-8")
    llm_response = _FakeLLMResponse(ok=False)
    client = _FakeLLMClient(llm_response)
    refiner = LLMDraftRefiner(llm_client=client)
    refined = refiner.refine(draft, [])

    # Script should be unchanged
    assert refined.script_path.read_text(encoding="utf-8") == original_script
    assert refined is draft


def test_llm_refiner_returns_original_on_empty_replacements(tmp_path: Path) -> None:
    """When LLM suggests no replacements, the original draft is returned."""
    draft = _write_draft(tmp_path)
    llm_response = _FakeLLMResponse(
        ok=True,
        output_text=json.dumps({"replacements": []}),
    )
    client = _FakeLLMClient(llm_response)
    refiner = LLMDraftRefiner(llm_client=client)
    refined = refiner.refine(draft, [])

    assert refined is draft


def test_llm_refiner_returns_original_on_invalid_json(tmp_path: Path) -> None:
    """When LLM returns invalid JSON, the original draft is returned."""
    draft = _write_draft(tmp_path)
    llm_response = _FakeLLMResponse(ok=True, output_text="not valid json {{{")
    client = _FakeLLMClient(llm_response)
    refiner = LLMDraftRefiner(llm_client=client)
    refined = refiner.refine(draft, [])

    assert refined is draft


def test_llm_refiner_skips_action_name_replacements(tmp_path: Path) -> None:
    """LLM should not be allowed to replace action names."""
    draft = _write_draft(tmp_path)
    llm_response = _FakeLLMResponse(
        ok=True,
        output_text=json.dumps(
            {
                "replacements": [
                    {
                        "original_value": "ui.click",
                        "variable_name": "action_type",
                        "input_type": "string",
                        "description": "should be blocked",
                    }
                ]
            }
        ),
    )
    client = _FakeLLMClient(llm_response)
    refiner = LLMDraftRefiner(llm_client=client)
    refined = refiner.refine(draft, [])

    # Original should be returned since actionname replacement is blocked
    assert refined is draft


def test_llm_refiner_returns_original_on_exception(tmp_path: Path) -> None:
    """If the LLM client raises, the refiner catches and returns the original."""
    draft = _write_draft(tmp_path)

    class _ExplodingClient:
        def evaluate(self, *args: Any, **kwargs: Any) -> None:
            raise ConnectionError("network down")

    refiner = LLMDraftRefiner(llm_client=_ExplodingClient())
    refined = refiner.refine(draft, [])

    assert refined is draft
