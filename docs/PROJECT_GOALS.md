# Project Goals

## Purpose
This document defines the north-star goals, scope boundaries, and success criteria for `webrpa`. It is the decision anchor for what we build (and what we explicitly do not build). Progress tracking belongs in `docs/project_progress.md`, and execution planning belongs in `docs/ROADMAP.md`.

## Target Users
- Primary: Business operations teams running high-volume, repeatable workflows.
- Future: External customers who need a self-serve automation platform.

## North Star
实现从“AI 自主探索”到“Master YAML 插件”的闭环演化。其核心逻辑在于解决“辅助的悖论”：
- **2.0 模式 (AI 自主探索)**：在零辅助数据下，解放 AI 进行视觉开辟与数据生产。它是“寻路者”。
- **1.0 模式 (高性能生产)**：利用 2.0 沉淀的感知记忆（Resource ID 等）实现极速、稳定的执行。它是“主力军”。
- **Master YAML (零 AI 交付)**：将稳定的 1.0 路径编译为脱离 AI 推理的工业级插件。它是“终极产物”。

## Core Goals
- G1: **AI 极速冷启动 (Autonomous Bootstrapping)**：利用 VLM/LLM 实现在无预设规则环境下的 0-1 自主任务执行。
- G2: **动态感知回填 (App Config Backfilling)**：运行过程中自动捕获并固化 UI 特征（如 Resource ID），消除对人工语言硬编码的依赖。
- G3: **1.0 模式平滑切入 (Auto-Native Transition)**：当 AI 成功率达标时，自动将感知权由昂贵的 AI 推理转向高效的原生规则匹配（动作决策仍由 AI 完成）。
- G4: **YAML 插件终极蒸馏 (Plugin Distillation)**：基于高成功率的运行轨迹，全自动编译生成确定的 YAML 插件，实现任务的**零 AI 化（去 Token）**交付。
- G5: **工业级底座 (Robust Platform)**：具备完善的账号隔离、并发调度、指标监控与可视化审计能力。

## Workflow Scope (Ops)
- All operational workflows target supported application script tasks.
- Initial workflow list should be explicit and small (3-5 critical flows).
- The current plugin library under `plugins/` is the source of truth for **bundled workflows**, not for workflow-level launch verification.
- Current bundled list: `device_reboot`, `one_click_new_device`, `x_clone_profile`, `x_follow_followers`, `x_home_interaction`, `x_login`, `x_nurture`, `x_quote_intercept`, `x_reply_dm`, `x_scrape_blogger`.
- Current narrow launch-readiness examples should remain explicit and conservative in `docs/STATUS.md`; do not treat all bundled plugins as equally verified by default.

## Non-Goals (Near Term)
- Building a new general-purpose workflow language.
- Replacing the existing plugin contract or re-architecting routes.
- UI redesigns that are not required for operational usage.
- Long-running human-in-the-loop labeling systems beyond targeted feedback hooks.

## Success Metrics (Draft, To Confirm)
- Vision-run success rate on top N workflows in staging (goal: keep improving; set explicit thresholds per workflow).
- Distilled plugin replay pass rate over M runs.
- Evidence completeness rate per run (trace + screenshots + action results).
- Median time to diagnose a failed run using captured evidence.
- Cost per successful run (model usage + infrastructure).

## Default Success Thresholds (Can Be Tuned Per Workflow)
- Success rate (staging): simple >= 95%, complex >= 90%.
- Distilled plugin replay pass rate: >= 95% over M runs.
- Evidence completeness: >= 95% of runs have full required evidence payload.
- Latency (P95 end-to-end): simple <= 5 minutes, complex <= 12 minutes.

## Distillation Gate (Default)
- Simple tasks: distill after 3 successful runs.
- Complex tasks: distill after at most 10 successful runs.
- Only successful logs are used for distillation when each run is model-from-scratch (no external assistance or injected hints).
- Definition of simple vs complex must be documented per workflow.
- Successes are cumulative (not required to be consecutive).

## Simple vs Complex Definition (Initial)
- Simple: no branching and step count <= 10.
- Complex: any branching, or step count > 10.
- Thresholds can be adjusted per workflow, but must be documented.

## Minimum Evidence Payload (Required for Distillation)
The following evidence is required per run to qualify for distillation:
- Model trace records (JSONL) for each step and a terminal record.
- Step record fields: `chosen_action`, `action_params`, `observation` (with `modality`, `data`, and `observed_state_ids`), `action_result`, and step timestamps.
- Planner request/response metadata: `provider`, `model`, `request_id`, and error codes if any.
- Fallback evidence when used: UI XML or browser HTML snapshot.
- Screenshot capture with `save_path`, `byte_length`, and screen metadata (width/height). Real device screen dimensions are required for VLM coordinate compensation.
- Runtime context: task id, run id, target label, and runtime profile identifiers.

## Engineering Guardrails (Architecture 2.0)
- **Privacy-First**：感知回填严禁存储 PII（个人身份信息）。密码类节点（类型含 `Password`/`Secure`）永不记录，TraceLearner 必须具备自动脱敏能力。
- **Version Resilience**：感知记忆不应是死板的点对点匹配，而应具备语意容错性。优先识别稳定的 Resource ID，辅以文本哈希。
- **Safety Control**：为 AI 探索设置“试错预算（Step/Token Budget）”。超出阈值未见进展时立即熔断并人工干预。
- **Self-Healing Failover**：运行时具备自愈能力。当 1.0 数据匹配失败时，自动退避（Failover）至 2.0 AI 探索模式重新测绘。

## Constraints and Invariants
- Baseline startup must succeed with RPC enabled by default, while `MYT_ENABLE_RPC=0` remains a supported compatibility path.
- Persistent data must remain under `config/data`.
- `api/server.py` is the sole application entrypoint and `/web` remains available.
- No legacy imports from `tasks` or `app.*`.

## Roadmap Link
See `docs/ROADMAP.md` for the milestone route and current completion status.

## Open Questions
- What success thresholds should we use for completion rate and latency?
