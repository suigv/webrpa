#!/usr/bin/env python3
# pyright: reportMissingTypeArgument=false

"""从 agent_executor trace jsonl 文件蒸馏 NativeStateBinding 代码草稿。

用法:
    python tools/distill_binding.py <task_id>
    python tools/distill_binding.py <task_id> --binding-id app_home --app-package com.example.app

示例:
    python tools/distill_binding.py 882b29cf-9f96-400b-b860-4ace326e0918
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import xml.etree.ElementTree as ET
from collections import Counter
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

bootstrap_project_root()

from core.paths import traces_dir

TRACES_DIR = traces_dir()


def find_jsonl_files(trace_root: Path) -> list[Path]:
    return sorted(trace_root.rglob("*.jsonl"))


def load_trace_records(jsonl_path: Path) -> list[dict]:
    records = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def extract_xml(record: dict) -> str | None:
    fe = record.get("fallback_evidence") or {}
    ui_xml = fe.get("ui_xml") or {}
    content = ui_xml.get("content") or ""
    if content:
        return content.strip()

    save_path = ui_xml.get("save_path") or ""
    if save_path:
        p = Path(save_path)
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    return None


def parse_features(xml_content: str) -> dict:
    features: dict = {
        "packages": Counter(),
        "resource_ids": Counter(),
        "texts": Counter(),
        "content_descs": Counter(),
    }

    # 首先尝试正常解析
    try:
        root = ET.fromstring(xml_content)
        for node in root.iter():
            pkg = node.get("package", "")
            if pkg:
                features["packages"][pkg] += 1
            rid = node.get("resource-id", "")
            if rid and ":id/" in rid:
                features["resource_ids"][rid] += 1
            text = node.get("text", "").strip()
            if text and len(text) < 60:
                features["texts"][text] += 1
            desc = node.get("content-desc", "").strip()
            if desc and len(desc) < 60:
                features["content_descs"][desc] += 1
        return features
    except ET.ParseError:
        pass

    # 如果 XML 不完整（常见于 4KB 截断），使用正则提取特征
    import re

    patterns = {
        "packages": r'package="([^"]*)"',
        "resource_ids": r'resource-id="([^"]*)"',
        "texts": r'text="([^"]*)"',
        "content_descs": r'content-desc="([^"]*)"',
    }

    for key, pattern in patterns.items():
        matches = re.findall(pattern, xml_content)
        for m in matches:
            if not m.strip():
                continue
            if key == "resource_ids" and ":id/" not in m:
                continue
            if key in ("texts", "content_descs") and len(m) > 60:
                continue
            features[key][m] += 1

    return features


def infer_label(features: dict, step_index: int) -> str:
    packages = features["packages"]
    texts = features["texts"]
    resource_ids = features["resource_ids"]
    main_pkg = packages.most_common(1)[0][0] if packages else "unknown"
    rid_str = " ".join(resource_ids.keys()).lower()
    text_str = " ".join(texts.keys())

    if "login" in rid_str or "signin" in rid_str or "登录" in text_str:
        return "login"
    if "password" in rid_str or "密码" in text_str:
        return "password"
    if "two_factor" in rid_str or "verification" in rid_str or "验证" in text_str:
        return "two_factor"
    if "captcha" in rid_str or "验证码" in text_str:
        return "captcha"
    if "timeline" in rid_str or "为你推荐" in text_str or "home" in rid_str:
        return "home"
    if "notification" in rid_str or "通知" in text_str:
        return "notification_panel"
    if "launcher" in main_pkg or "launcher" in rid_str:
        return "launcher"
    if "systemui" in main_pkg:
        return "system_ui"
    return f"screen_{step_index}"


def _top_markers(counter: Counter, limit: int = 3) -> list[str]:
    return [value for value, _ in counter.most_common(limit) if value]


def _build_state_patterns(steps: list[dict]) -> dict[str, dict[str, list[str]]]:
    patterns: dict[str, dict[str, list[str]]] = {}
    seen: set[str] = set()
    for step in steps:
        label = step["label"]
        if label in seen:
            continue
        seen.add(label)
        patterns[label] = {
            "resource_ids": _top_markers(step["resource_ids"]),
            "focus_markers": [],
            "text_markers": _top_markers(step["texts"]) + _top_markers(step["content_descs"]),
        }
    return patterns


def generate_code(binding_id: str, app_package: str, steps: list[dict]) -> str:
    state_ids = sorted({s["label"] for s in steps})
    state_tuple = ", ".join(f'"{s}"' for s in state_ids)
    binding_var = f"_{binding_id.upper()}_BINDING"
    state_patterns = _build_state_patterns(steps)
    state_patterns_literal = json.dumps(
        state_patterns, ensure_ascii=False, indent=4, sort_keys=True
    )
    state_order_literal = ", ".join(f'"{state_id}"' for state_id in state_ids)

    hints = []
    seen: set[str] = set()
    for s in steps:
        label = s["label"]
        if label in seen:
            continue
        seen.add(label)
        top_rids = _top_markers(s["resource_ids"])
        top_texts = _top_markers(s["texts"])
        top_descs = _top_markers(s["content_descs"])
        hints.append(f"    # [{label}]")
        if top_rids:
            hints.append(f"    #   resource-ids: {top_rids}")
        if top_texts:
            hints.append(f"    #   texts: {top_texts}")
        if top_descs:
            hints.append(f"    #   content-descs: {top_descs}")

    hints_str = "\n".join(hints)
    bid = binding_id
    bid_upper = binding_id.upper()

    lines = [
        "# =================================================================",
        "# AUTO-GENERATED by tools/distill_binding.py",
        f"# binding_id : {bid}",
        f"# app_package: {app_package}",
        f"# detected states: {state_ids}",
        "#",
        "# Per-state recognition hints (review and refine stage patterns if needed):",
        hints_str,
        "#",
        "# Generated detector uses the shared RPC stage matcher with distilled markers.",
        "# Review marker stability, then register the binding in engine/ui_state_native_bindings.py.",
        "# =================================================================",
        "",
        "from engine.actions import state_actions",
        "from engine.ui_state_native_bindings import NativeStateBinding",
        "from engine.models.runtime import ActionResult, ExecutionContext",
        "",
        f'_{bid_upper}_STATE_IDS = ({state_tuple}, "unknown")',
        "",
        f"_{bid_upper}_STAGE_PATTERNS = {state_patterns_literal}",
        "",
        f"_{bid_upper}_STAGE_ORDER = ({state_order_literal},)",
        "",
        f"def _normalize_{bid}_state(state_id: str) -> str:",
        f'    return state_id if state_id in _{bid_upper}_STATE_IDS else "unknown"',
        "",
        f"def _detect_{bid}_stage(",
        "    params: dict,",
        "    context: ExecutionContext,",
        ") -> ActionResult:",
        "    merged_params = dict(params)",
        f'    merged_params.setdefault("package", "{app_package}")',
        f'    merged_params["stage_patterns"] = _{bid_upper}_STAGE_PATTERNS',
        f'    merged_params["stage_order"] = list(_{bid_upper}_STAGE_ORDER)',
        "    return state_actions.detect_login_stage(merged_params, context)",
        "",
        f"{binding_var} = NativeStateBinding(",
        f'    binding_id="{bid}",',
        f'    display_name="{bid} (auto-distilled from trace)",',
        '    state_noun="stage",',
        f"    supported_state_ids=_{bid_upper}_STATE_IDS,",
        f"    normalize_state_id=_normalize_{bid}_state,",
        f"    state_id_from_action_result=lambda r: _normalize_{bid}_state(",
        '        str(r.data.get("stage", "unknown"))',
        "    ),",
        f"    match_action=_detect_{bid}_stage,",
        ")",
        "",
        "# Registration snippet for engine/ui_state_native_bindings.py:",
        f"# {binding_var}.binding_id: {binding_var},",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="从 trace 蒸馏 NativeStateBinding 代码草稿")
    parser.add_argument("task_id", help="任务 ID 或 trace 目录路径")
    parser.add_argument("--binding-id", default="", help="binding 名称（默认自动推断）")
    parser.add_argument("--app-package", default="", help="App 包名（默认从 XML 提取）")
    parser.add_argument("--output", default="", help="输出文件路径（默认打印到 stdout）")
    args = parser.parse_args()

    # 定位 trace 目录
    trace_root = Path(args.task_id)
    if not trace_root.exists():
        trace_root = TRACES_DIR / args.task_id
    if not trace_root.exists():
        print(f"ERROR: trace 目录不存在: {trace_root}")
        raise SystemExit(1)

    jsonl_files = find_jsonl_files(trace_root)
    if not jsonl_files:
        print(f"ERROR: 未找到 jsonl 文件: {trace_root}")
        raise SystemExit(1)

    print(f"找到 {len(jsonl_files)} 个 trace 文件")

    # 收集所有步骤的特征
    steps: list[dict] = []
    all_packages: Counter = Counter()

    for jsonl_path in jsonl_files:
        records = load_trace_records(jsonl_path)
        for record in records:
            xml = extract_xml(record)
            if not xml:
                continue
            step_index = record.get("step_index") or len(steps) + 1
            features = parse_features(xml)
            label = infer_label(features, step_index)
            steps.append({"step_index": step_index, "label": label, **features})
            all_packages.update(features["packages"])
            print(f"  step {step_index}: {label} (package={list(features['packages'].keys())[:1]})")

    if not steps:
        print("ERROR: trace 中没有找到 UI XML 数据")
        raise SystemExit(1)

    # 推断 app_package 和 binding_id
    app_package = args.app_package
    if not app_package and all_packages:
        # 取出现最多的非系统包名
        for pkg, _ in all_packages.most_common():
            if not any(
                sys in pkg for sys in ["android.systemui", "android.launcher", "com.android"]
            ):
                app_package = pkg
                break
        if not app_package:
            app_package = all_packages.most_common(1)[0][0]

    binding_id = args.binding_id
    if not binding_id:
        # 从包名推断：com.example.app -> example
        parts = app_package.split(".")
        name = parts[-2] if len(parts) >= 2 else parts[0]
        binding_id = f"{name}_auto"

    print(f"\napp_package : {app_package}")
    print(f"binding_id  : {binding_id}")
    print(f"states      : {sorted({s['label'] for s in steps})}")

    code = generate_code(binding_id, app_package, steps)

    if args.output:
        Path(args.output).write_text(code, encoding="utf-8")
        print(f"\n代码草稿已写入: {args.output}")
    else:
        print("\n" + "=" * 64)
        print(code)
        print("=" * 64)


if __name__ == "__main__":
    main()
