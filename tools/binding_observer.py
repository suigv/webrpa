#!/usr/bin/env python3
"""Binding Observer — 交互式界面特征采集工具。

用法:
    python tools/binding_observer.py --device-ip 192.168.1.214 --rpa-port 30202 --app x
    python tools/binding_observer.py --device-ip 192.168.1.214 --rpa-port 30202 --app x --output my_binding.json

操作:
    [回车]  采集当前界面（XML压缩 → LLM分析 → 确认）
    [l]     查看已记录列表
    [q]     退出并生成 binding 代码
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.models.runtime import ExecutionContext
from engine.actions.ui_actions import dumpNodeXml
from engine.actions._state_detection_support import preprocess_xml
from ai_services.llm_client import LLMClient, LLMRequest


def _load_xml_filter(binding_path: Path) -> dict[str, int]:
    """从 binding 文件读取 xml_filter 参数，缺失时返回空字典（不截断）。"""
    try:
        data = json.loads(binding_path.read_text(encoding="utf-8"))
        f = data.get("xml_filter", {})
        if not f:
            return {}
        return {
            "max_text_len": int(f.get("max_text_len", 0)),
            "max_desc_len": int(f.get("max_desc_len", 0)),
        }
    except Exception:
        return {}


# ------------------------------------------------------------------ #
# LLM 分析
# ------------------------------------------------------------------ #


def analyze_with_llm(
    xml: str,
    app_name: str,
    known_states: list[str],
    llm_client: LLMClient,
    xml_filter: dict[str, int] | None = None,
) -> dict[str, Any]:
    """调用 LLM 分析当前界面，返回 state_id 和识别特征。"""
    flt = xml_filter or {}
    node_text = preprocess_xml(xml, **flt)
    known_str = ", ".join(known_states) if known_states else "（暂无）"
    prompt = f"""你是移动端 UI 分析专家。以下是 {app_name} App 当前界面的节点属性列表（每行一个节点）：

{node_text}

已记录的界面状态：{known_str}

请完成以下任务：
1. 判断当前界面是什么状态（用英文小写+下划线，如 home_feed、password_input）
2. 从节点中找出 2-3 个最稳定的识别特征，格式要求：
   - 固定UI文字用：text=xxx
   - 固定resource-id用：resource-id=com.xxx:id/yyy
   - 不得包含 bounds 坐标
   - 不得使用动态内容（用户名、数字计数等）

返回 JSON 格式：
{{"state_id": "xxx", "features": ["特征1", "特征2"], "reason": "简短说明"}}"""

    request = LLMRequest(
        prompt=prompt,
        response_format={"type": "json_object"},
    )
    try:
        response = llm_client.evaluate(request)
        if not response.ok:
            return {"state_id": "unknown", "features": [], "reason": f"LLM error: {response.error}"}
        if response.structured_state and isinstance(response.structured_state, dict):
            return response.structured_state  # type: ignore[return-value]
        output = response.output_text.strip()
        # 去掉 markdown 代码块 ```json ... ```
        if output.startswith("```"):
            lines = output.splitlines()
            output = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(output)
    except Exception as exc:
        return {"state_id": "unknown", "features": [], "reason": f"LLM error: {exc}"}


# ------------------------------------------------------------------ #
# 生成 binding 代码
# ------------------------------------------------------------------ #

def generate_binding_code(app_name: str, records: list[dict]) -> str:
    """调用 LLM 根据记录生成 detect_xxx_stage() Python 代码。"""
    slim = [{"state_id": r["state_id"], "features": r["features"]} for r in records]
    records_str = json.dumps(slim, ensure_ascii=False, indent=2)
    llm_client = LLMClient()
    prompt = f"""根据以下 {app_name} App 的界面特征记录，生成一个 Python 函数 detect_{app_name}_stage(rpc)。

记录数据：
{records_str}

要求：
1. 函数签名：def detect_{app_name}_stage(rpc: Any) -> str
2. 使用 query_any_text_contains(rpc, ["text1", "text2"]) 进行文字匹配
3. 按优先级排列（从最具体到最通用）
4. 最后返回 "unknown"
5. 只输出 Python 代码，不要其他说明

可用的辅助函数参考：
from engine.actions._state_detection_support import query_any_text_contains"""

    request = LLMRequest(prompt=prompt)
    try:
        response = llm_client.evaluate(request)
        return response.output_text
    except Exception as exc:
        return f"# LLM 生成失败: {exc}"


# ------------------------------------------------------------------ #
# 主交互循环
# ------------------------------------------------------------------ #

def main() -> None:
    parser = argparse.ArgumentParser(description="交互式界面特征采集工具")
    parser.add_argument("--device-ip", required=True, help="设备 IP")
    parser.add_argument("--rpa-port", type=int, required=True, help="RPA 端口（30002/30102/...）")
    parser.add_argument("--app", required=True, help="App 名称（用于命名）")
    parser.add_argument("--output", default="", help="记录输出路径（默认自动命名）")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else Path(f"{args.app}_binding_records.json")
    code_path = Path(f"{args.app}_binding_draft.py")

    # 从已有 binding 文件读取 xml_filter 参数
    binding_path = Path(ROOT) / "config" / "bindings" / f"{args.app}.json"
    xml_filter = _load_xml_filter(binding_path)

    # 加载已有记录
    records: list[dict] = []
    if output_path.exists():
        try:
            data = json.loads(output_path.read_text(encoding="utf-8"))
            records = data.get("states", data) if isinstance(data, dict) else data
            print(f"已加载 {len(records)} 条历史记录")
        except Exception:
            pass

    ctx = ExecutionContext(payload={"device_ip": args.device_ip, "rpa_port": args.rpa_port})
    llm_client = LLMClient()

    print(f"\n{'='*50}")
    print(f"Binding Observer — {args.app} App")
    print(f"设备: {args.device_ip}:{args.rpa_port}")
    print(f"已记录状态: {[r['state_id'] for r in records]}")
    print(f"{'='*50}")
    print("[回车] 采集当前界面  [l] 查看记录  [q] 退出生成代码")
    print()

    while True:
        try:
            user_input = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            user_input = "q"

        if user_input.lower() == "q":
            break

        if user_input.lower() == "l":
            if not records:
                print("暂无记录")
            else:
                print(f"\n已记录 {len(records)} 个界面状态：")
                for i, r in enumerate(records, 1):
                    features_str = ", ".join(r.get("features", []))
                    print(f"  {i}. {r['state_id']} — {features_str}")
            print()
            continue

        # 采集当前界面
        print("截图并提取节点...")
        result = dumpNodeXml({"dump_all": True}, ctx)
        if not result.ok:
            print(f"获取 XML 失败: {result.code} {result.message}")
            continue

        xml = result.data.get("xml", "")

        print("LLM 分析中...")
        known_states = [r["state_id"] for r in records]
        analysis = analyze_with_llm(xml, args.app, known_states, llm_client, xml_filter)

        llm_state = analysis.get("state_id", "unknown")
        features = analysis.get("features", [])
        reason = analysis.get("reason", "")

        print(f"\nLLM 建议: {llm_state}")
        print(f"识别特征: {features}")
        if reason:
            print(f"说明: {reason}")

        confirm = input(f"确认 state_id [回车={llm_state} / 输入自定义 / s=跳过]: ").strip()
        if confirm.lower() == "s":
            print("已跳过")
            continue

        final_state = confirm if confirm else llm_state

        # 检查是否已存在，询问是否覆盖
        existing = next((r for r in records if r["state_id"] == final_state), None)
        if existing:
            overwrite = input(f"状态 '{final_state}' 已存在，覆盖? [y/n]: ").strip().lower()
            if overwrite != "y":
                print("已取消")
                continue
            records.remove(existing)

        record = {
            "state_id": final_state,
            "llm_suggestion": llm_state,
            "features": features,
            "xml": xml,
        }
        records.append(record)
        output_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ 已记录: {final_state}（共 {len(records)} 个状态）\n")

    # 退出：生成代码
    if not records:
        print("无记录，退出。")
        return

    print(f"\n共 {len(records)} 个界面状态，正在生成 binding 代码...")
    code = generate_binding_code(args.app, records)
    code_path.write_text(code, encoding="utf-8")
    print(f"\n✓ 代码草稿已生成: {code_path}")
    print(f"✓ 记录文件: {output_path}")
    print("\n下一步：审核代码后复制到 engine/actions/state_actions.py")


if __name__ == "__main__":
    main()
