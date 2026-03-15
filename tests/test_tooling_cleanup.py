from __future__ import annotations

from collections import Counter
from typing import cast

from core.paths import project_root
from engine.ui_state_native_bindings import NativeStateBinding
from tools import distill_binding
from tools._bootstrap import bootstrap_project_root


def test_bootstrap_project_root_matches_core_helper() -> None:
    assert bootstrap_project_root() == project_root()


def test_tools_root_inference_is_centralized() -> None:
    root = project_root()
    pattern = "Path(__file__).resolve().parents[1]"
    sys_path_insert = "sys.path.insert(0,"

    for script in (root / "tools").glob("*.py"):
        text = script.read_text(encoding="utf-8")
        if script.name == "_bootstrap.py":
            assert pattern in text
            continue
        assert pattern not in text, f"{script} should use tools._bootstrap instead of inline root inference"
        assert sys_path_insert not in text, f"{script} should rely on tools._bootstrap for sys.path setup"


def test_distill_binding_generates_concrete_detector() -> None:
    steps = [
        {
            "label": "login",
            "resource_ids": Counter({"com.example:id/login_button": 3}),
            "texts": Counter({"Log in": 2}),
            "content_descs": Counter({"Sign in": 1}),
        },
        {
            "label": "home",
            "resource_ids": Counter({"com.example:id/home_timeline": 4}),
            "texts": Counter({"For you": 2}),
            "content_descs": Counter(),
        },
    ]

    code = distill_binding.generate_code("example_auto", "com.example.app", steps)
    compiled = compile(code, "<distilled_binding>", "exec")
    namespace: dict[str, object] = {}
    exec(compiled, namespace)

    assert "# TODO:" not in code
    assert "NotImplementedError" not in code
    assert "state_actions.detect_login_stage" in code
    assert "_EXAMPLE_AUTO_STAGE_PATTERNS" in code
    assert 'merged_params.setdefault("package", "com.example.app")' in code
    assert '# _EXAMPLE_AUTO_BINDING.binding_id: _EXAMPLE_AUTO_BINDING,' in code
    assert namespace["_EXAMPLE_AUTO_STATE_IDS"] == ("home", "login", "unknown")
    assert namespace["_EXAMPLE_AUTO_STAGE_ORDER"] == ("home", "login")
    binding = cast(NativeStateBinding, namespace["_EXAMPLE_AUTO_BINDING"])
    assert binding.binding_id == "example_auto"
