# Project Goals

## Purpose
This document defines the north-star goals, scope boundaries, and success criteria for `webrpa`. It is the decision anchor for what we build (and what we explicitly do not build). Progress tracking belongs in `docs/project_progress.md`, and execution planning belongs in `docs/ROADMAP.md`.

## Target Users
- Primary: Business operations teams running high-volume, repeatable workflows.
- Future: External customers who need a self-serve automation platform.

## North Star
实现从“AI 驱动”到“技能驱动”的闭环演进。通过视觉模型自主执行复杂任务并收集证据，蒸馏出稳定、确定的 YAML 插件（Skills），最终形成可被 AI 或 引擎直接调用的“业务专家技能库”，摆脱对大模型实时推理的依赖。

## Core Goals
- G1: **AI 自主执行**：愿景模型能可靠执行业务指令，并实现 self-healing 观察。
- G2: **证据闭环采集**：多轮运行日志记录完整轨迹，支撑诊断与蒸馏。
- G3: **技能自动化蒸馏 (Skills Discovery)**：从成功轨迹中自动提取原子动作序列、选择器和业务状态，生成可复用的 Skills。
- G4: **架构合理化 (Action-to-Skill)**：建立具备自描述能力动作注册表，支持变量隔离、异常闭环，使 Skills 成为一等公民。
- G5: **平台化能力**：具备完善的账号系统、监控指标与运维看板。

## Workflow Scope (Ops)
- All operational workflows target supported application script tasks.
- Initial workflow list should be explicit and small (3-5 critical flows).
- Representative workflows are the current plugin library under `plugins/` (source of truth).
  - Current list: `device_reboot`, `device_soft_reset`, `hezi_sdk_probe`, `mytos_device_setup`.

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

## Constraints and Invariants
- Baseline startup must succeed with `MYT_ENABLE_RPC=0`.
- Persistent data must remain under `config/data`.
- `api/server.py` is the sole application entrypoint and `/web` remains available.
- No legacy imports from `tasks` or `app.*`.

## Roadmap Link
See `docs/ROADMAP.md` for the milestone route and current completion status.

## Open Questions
- What success thresholds should we use for completion rate and latency?
