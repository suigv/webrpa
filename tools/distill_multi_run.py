#!/usr/bin/env python3
"""多轮 trace 聚合蒸馏工具。

扫描指定插件的所有成功 trace，聚合步骤序列，生成高质量 YAML 插件草稿。

用法:
    python tools/distill_multi_run.py --plugin device_reboot
    python tools/distill_multi_run.py --plugin mytos_device_setup --min-runs 2 --output-dir plugins/mytos_device_setup_draft
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

import yaml

ROOT = Path(__file__).resolve().parents[1]
TRACES_DIR = ROOT / "config" / "data" / "traces"
PLUGINS_DIR = ROOT / "plugins"

# 蒸馏门槛（与 docs/STATUS.md 保持一致）
DISTILL_THRESHOLDS: dict[str, int] = {
    "device_reboot": 3,
    "device_soft_reset": 3,
    "hezi_sdk_probe": 3,
    "mytos_device_setup": 3,
}


def load_jsonl(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def find_successful_traces(plugin_name: str) -> list[dict]:
    """从所有 trace 目录扫描指定插件的成功 trace。"""
    results = []
    for task_dir in sorted(TRACES_DIR.iterdir()):
        if not task_dir.is_dir():
            continue
        for run_dir in sorted(task_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            for jsonl_file in run_dir.glob("*.jsonl"):
                records = load_jsonl(jsonl_file)
                if not records:
                    continue
                # 检查是否是目标插件的成功 trace
                task = records[0].get("task", "")
                if task != plugin_name:
                    continue
                # 找终态记录
                terminal = next((r for r in reversed(records) if r.get("record_type") == "terminal"), None)
                if terminal and terminal.get("status") == "completed":
                    results.append({
                        "task_id": task_dir.name,
                        "run_id": run_dir.name,
                        "jsonl_path": jsonl_file,
                        "records": records,
                        "step_count": terminal.get("step_index", 0),
                    })
    return results


def extract_steps(records: list[dict]) -> list[dict]:
    """从 trace records 提取动作步骤。"""
    steps = []
    for r in records:
        if r.get("record_type") != "step":
            continue
        action = str(r.get("chosen_action") or "").strip()
        params = r.get("action_params") or {}
        observation = r.get("observation") or {}
        if not action:
            continue
        steps.append({
            "step_index": r.get("step_index", 0),
            "action": action,
            "params": params,
            "observation": observation,
            "action_result_ok": bool((r.get("action_result") or {}).get("ok")),
        })
    return steps


def aggregate_steps(all_steps: list[list[dict]]) -> list[dict]:
    """聚合多次运行的步骤，选取最一致的动作序列。"""
    if not all_steps:
        return []

    # 按步骤索引聚合，选取出现频率最高的动作
    step_actions: defaultdict[int, Counter] = defaultdict(Counter)
    step_params: defaultdict[int, list] = defaultdict(list)

    for run_steps in all_steps:
        for step in run_steps:
            idx = step["step_index"]
            step_actions[idx][step["action"]] += 1
            step_params[idx].append(step["params"])

    aggregated = []
    for idx in sorted(step_actions.keys()):
        best_action = step_actions[idx].most_common(1)[0][0]
        # 选取该动作最常用的参数（去掉动态值如坐标）
        params_list = [p for p in step_params[idx]]
        best_params = _merge_params(params_list)
        aggregated.append({
            "step_index": idx,
            "action": best_action,
            "params": best_params,
            "confidence": step_actions[idx][best_action] / len(all_steps),
        })

    return aggregated


def _merge_params(params_list: list[dict]) -> dict:
    """合并多次运行的参数，保留稳定值，标记动态值。"""
    if not params_list:
        return {}
    if len(params_list) == 1:
        return params_list[0]

    merged = {}
    all_keys = set()
    for p in params_list:
        all_keys.update(p.keys())

    for key in all_keys:
        values = [p.get(key) for p in params_list if key in p]
        unique = list(set(json.dumps(v, sort_keys=True) for v in values))
        if len(unique) == 1:
            # 所有运行值一致，直接使用
            merged[key] = values[0]
        else:
            # 值不一致，标记为动态参数（使用变量占位符）
            merged[key] = f"{{{{ {key} }}}}"

    return merged


def generate_yaml_script(plugin_name: str, steps: list[dict]) -> dict:
    """生成 YAML 插件脚本草稿。"""
    script_steps = []
    for step in steps:
        action = step["action"]
        params = {k: v for k, v in step["params"].items() if v is not None}
        confidence = step.get("confidence", 1.0)

        step_dict: dict = {"action": action}
        if params:
            step_dict["params"] = params
        if confidence < 0.8:
            step_dict["# confidence"] = f"{confidence:.0%} - 低置信度，请人工审核"

        script_steps.append(step_dict)

    return {
        "version": "v2",
        "steps": script_steps,
    }


def generate_manifest(plugin_name: str, run_count: int, step_count: int) -> dict:
    """生成插件 manifest 草稿。"""
    return {
        "name": f"{plugin_name}_distilled",
        "display_name": f"{plugin_name} (multi-run distilled, {run_count} runs)",
        "version": "1.0.0",
        "category": "AI Drafts",
        "entry_script": "script.yaml",
        "inputs": [
            {"name": "device_ip", "type": "string", "required": True},
        ],
        "# note": f"Auto-distilled from {run_count} successful runs, {step_count} steps. Review before use.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="多轮 trace 聚合蒸馏工具")
    parser.add_argument("--plugin", required=True, help="插件名称（如 device_reboot）")
    parser.add_argument("--min-runs", type=int, default=0, help="最少成功次数（0=使用蒸馏门槛）")
    parser.add_argument("--output-dir", type=Path, default=None, help="输出目录（默认 plugins/<plugin>_distilled）")
    parser.add_argument("--force", action="store_true", help="忽略门槛强制蒸馏")
    args = parser.parse_args()

    plugin_name = args.plugin
    threshold = DISTILL_THRESHOLDS.get(plugin_name, 3)
    min_runs = args.min_runs or threshold

    print(f"插件: {plugin_name}")
    print(f"蒸馏门槛: {threshold} 次成功")
    print(f"扫描 trace 目录: {TRACES_DIR}")

    traces = find_successful_traces(plugin_name)
    print(f"找到成功 trace: {len(traces)} 个")

    if not traces:
        print("ERROR: 没有找到成功的 trace")
        return 1

    if len(traces) < min_runs and not args.force:
        print(f"ERROR: 成功次数 {len(traces)} 未达到蒸馏门槛 {min_runs}")
        print(f"提示: 使用 --force 强制蒸馏，或 --min-runs {len(traces)} 降低门槛")
        return 1

    # 提取并聚合步骤
    all_steps = [extract_steps(t["records"]) for t in traces]
    aggregated = aggregate_steps(all_steps)

    if not aggregated:
        print("ERROR: 无法从 trace 提取有效步骤")
        return 1

    print(f"聚合步骤数: {len(aggregated)}")
    low_confidence = [s for s in aggregated if s.get("confidence", 1.0) < 0.8]
    if low_confidence:
        print(f"警告: {len(low_confidence)} 个步骤置信度低于 80%，请人工审核")

    # 生成输出
    output_dir = args.output_dir or (PLUGINS_DIR / f"{plugin_name}_distilled")
    output_dir.mkdir(parents=True, exist_ok=True)

    script = generate_yaml_script(plugin_name, aggregated)
    manifest = generate_manifest(plugin_name, len(traces), len(aggregated))

    script_path = output_dir / "script.yaml"
    manifest_path = output_dir / "manifest.yaml"

    script_path.write_text(yaml.dump(script, allow_unicode=True, sort_keys=False), encoding="utf-8")
    manifest_path.write_text(yaml.dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")

    print(f"\n蒸馏完成:")
    print(f"  manifest: {manifest_path}")
    print(f"  script:   {script_path}")
    print(f"  runs:     {len(traces)}")
    print(f"  steps:    {len(aggregated)}")

    # 输出摘要
    print("\n步骤摘要:")
    for s in aggregated:
        conf = s.get('confidence', 1.0)
        conf_str = f" [{conf:.0%}]" if conf < 1.0 else ""
        print(f"  step {s['step_index']:2d}: {s['action']}{conf_str}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
