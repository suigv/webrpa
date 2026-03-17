from __future__ import annotations

import importlib.util
import re
from pathlib import Path

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

from core.paths import plugins_dir
from engine.parser import parse_manifest

PLUGINS_ROOT = plugins_dir()
PAYLOAD_REF_PATTERN = re.compile(r"\$\{payload\.([A-Za-z_][A-Za-z0-9_\.]*)[^}]*\}")


def _extract_manifest_inputs(plugin_dir: Path) -> set[str]:
    manifest = parse_manifest(plugin_dir / "manifest.yaml")
    return {plugin_input.name for plugin_input in manifest.inputs}


def _extract_script_payload_inputs(script_path: Path) -> set[str]:
    script_text = script_path.read_text(encoding="utf-8")
    result: set[str] = set()
    for match in PAYLOAD_REF_PATTERN.finditer(script_text):
        raw_name = match.group(1)
        top_level_name = raw_name.split(".", 1)[0]
        result.add(top_level_name)
    return result


def collect_manifest_input_gaps(plugins_root: Path = PLUGINS_ROOT) -> list[str]:
    gaps: list[str] = []
    if not plugins_root.exists():
        return [f"plugins root not found: {plugins_root}"]

    for plugin_dir in sorted(plugins_root.iterdir()):
        if not plugin_dir.is_dir():
            continue

        manifest_path = plugin_dir / "manifest.yaml"
        script_path = plugin_dir / "script.yaml"
        if not manifest_path.exists() or not script_path.exists():
            continue

        declared_inputs = _extract_manifest_inputs(plugin_dir)
        script_inputs = _extract_script_payload_inputs(script_path)
        missing_inputs = sorted(script_inputs - declared_inputs)
        if missing_inputs:
            gaps.append(
                f"{plugin_dir.name}: missing manifest inputs for payload refs: {', '.join(missing_inputs)}"
            )

    return gaps


def main() -> int:
    gaps = collect_manifest_input_gaps()
    if gaps:
        print("Plugin manifest input completeness check failed:")
        for gap in gaps:
            print(f"- {gap}")
        return 1

    print("OK: all plugin payload references are declared in manifest inputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
