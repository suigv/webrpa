from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tools.check_plugin_manifest_inputs import collect_manifest_input_gaps


def _tool_path() -> Path:
    return Path(__file__).resolve().parents[1] / "tools" / "check_plugin_manifest_inputs.py"


def test_collect_manifest_input_gaps_reports_missing_payload_inputs(tmp_path: Path):
    plugin_dir = tmp_path / "plugins" / "demo"
    plugin_dir.mkdir(parents=True)
    _ = (plugin_dir / "manifest.yaml").write_text(
        "\n".join(
            [
                "api_version: v1",
                "kind: plugin",
                "name: demo",
                "version: '1.0.0'",
                "display_name: Demo",
                "entry_script: script.yaml",
                "inputs:",
                "  - name: declared",
                "    type: string",
                "    required: false",
            ]
        ),
        encoding="utf-8",
    )
    _ = (plugin_dir / "script.yaml").write_text(
        "\n".join(
            [
                "version: v1",
                "workflow: demo",
                "steps:",
                "  - kind: action",
                "    action: core.noop",
                "    params:",
                "      key: \"${payload.missing_ref}\"",
            ]
        ),
        encoding="utf-8",
    )

    gaps = collect_manifest_input_gaps(tmp_path / "plugins")
    assert len(gaps) == 1
    assert "demo" in gaps[0]
    assert "missing_ref" in gaps[0]


def test_check_plugin_manifest_inputs_script_passes_for_current_repo():
    result = subprocess.run(
        [sys.executable, str(_tool_path())],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "OK: all plugin payload references are declared in manifest inputs" in result.stdout
