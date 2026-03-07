from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from engine.models.manifest import PluginManifest
from engine.models.workflow import WorkflowScript


# ---- Variable interpolation ----

_INTERP_RE = re.compile(r"\$\{([^}]+)\}")


def _resolve_dotpath(obj: Any, path: str) -> Any:
    """Resolve a dot-separated path like 'creds.username_or_email' against a dict/object."""
    parts = path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return None
    return current


def interpolate(template: Any, context: Dict[str, Any]) -> Any:
    """Interpolate ${payload.*} and ${vars.*} references in a value.

    Supports:
      - ${payload.key} — lookup in context["payload"]
      - ${vars.key} — lookup in context["vars"]
      - ${vars.creds.field} — nested dot-path lookup
      - ${payload.url:-https://default.com} — default value after :-
    """
    if not isinstance(template, str):
        return template

    def _replace(match: re.Match) -> str:
        expr = match.group(1)
        default: Optional[str] = None
        if ":-" in expr:
            expr, default = expr.split(":-", 1)

        parts = expr.strip().split(".", 1)
        if len(parts) < 2:
            return default if default is not None else match.group(0)

        namespace, rest = parts
        source = context.get(namespace)
        if source is None:
            return default if default is not None else match.group(0)

        value = _resolve_dotpath(source, rest)
        if value is None:
            return default if default is not None else match.group(0)
        return str(value)

    # If template is entirely a single interpolation, return the raw value (preserving type)
    full_match = _INTERP_RE.fullmatch(template)
    if full_match:
        expr = full_match.group(1)
        default: Optional[str] = None
        if ":-" in expr:
            expr, default = expr.split(":-", 1)
        parts = expr.strip().split(".", 1)
        if len(parts) >= 2:
            namespace, rest = parts
            source = context.get(namespace)
            if source is not None:
                value = _resolve_dotpath(source, rest)
                if value is not None:
                    return value
        if default is not None:
            return default

    return _INTERP_RE.sub(_replace, template)


def _interpolate_value(value: Any, context: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        return interpolate(value, context)
    if isinstance(value, list):
        return [_interpolate_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: _interpolate_value(item, context) for key, item in value.items()}
    return value


def interpolate_params(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Interpolate all nested values in a params dict."""
    return {key: _interpolate_value(value, context) for key, value in params.items()}


# ---- YAML loading ----

def parse_manifest(path: Path) -> PluginManifest:
    """Load and validate a plugin manifest.yaml file."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"failed to load manifest {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"manifest must be a YAML mapping: {path}")
    return PluginManifest.model_validate(raw)


def parse_script(path: Path) -> WorkflowScript:
    """Load and validate a plugin script.yaml file."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"failed to load script {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"script must be a YAML mapping: {path}")
    return WorkflowScript.model_validate(raw)


# ---- Legacy parser (backward compat) ----

class ScriptParser:
    def parse(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        task = str(payload.get("task") or "anonymous")
        steps = payload.get("steps")
        if not isinstance(steps, list):
            steps = []
        normalized_steps: List[Dict[str, Any]] = []
        for index, step in enumerate(steps):
            if isinstance(step, dict):
                action = str(step.get("action") or f"noop_{index}")
                params = step.get("params") if isinstance(step.get("params"), dict) else {}
            else:
                action = f"noop_{index}"
                params = {}
            normalized_steps.append({"action": action, "params": params})
        return {"task": task, "steps": normalized_steps}
