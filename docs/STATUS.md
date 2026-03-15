# Project Status Matrix

This document provides a concise "done vs not-done" view tied to the goal and roadmap definitions. It does not replace `docs/project_progress.md` (which is a living log), nor `docs/ROADMAP.md` (which defines milestones).

## Status Legend
- Verified: Evidence captured (tests or validation logs).
- Implemented (Unverified): Code exists but verification evidence is missing.
- Partial: Some deliverables exist; key gaps remain.
- Planned: Not implemented yet.

## Milestone Status

| Milestone | Status | Evidence Notes |
|---|---|---|
| M0 Baseline Compliance and Runtime Stability | Verified | Full gate evidence captured: check_no_legacy_imports OK, pytest 264/264 passed, server startup OK, /health 200 OK. See .sisyphus/evidence/m0-gate-pytest-full.txt |
| M1 Vision-Model Script Execution MVP | Partial | Vision 路径已在真实设备验证（2026-03-10），screen_width/height 从 XML 根节点 bounds 解析并注入 trace。Binding-free vision path confirmed working. |
| M2 Evidence Capture and Diagnostics | Partial | XML collected unconditionally per step, saved as full file under traces/xml/ (not truncated). screen_width/height injected into screen_capture.metadata. task.observation and task.planning events emitted per step. DB event poller broadcasts subprocess events to WebSocket. |
| M3 技能蒸馏与 Skills 化演进 | Partial | 自动化蒸馏工具 `distill_multi_run.py` 可用；`SKILLS_EVOLUTION.md` 确定了阻力点与演进方案。动作注册表正向 Metadata 化改造。 |
| M4 平台化与外部就绪 | Planned | 账号系统与权限控制尚未开始。 |

- **文本化文档对齐 (2026-03-13)**：完成全量 `docs/` 内容审计，确立了多云机动态端口公式，修复了 SDK/API 文档的陈旧代码引用。
- **Skills 演进战略确立**：发布了 `docs/SKILLS_EVOLUTION.md`，识别出 ActionRegistry、Variable Scoping、Error Hooks 等核心架构优化点。
- **AI 观察自愈能力**：针对 X App 复杂界面的 XML 4KB 截断问题实现了自愈式捕获。
- **App 配置归一化与感知**：移除了硬编码绑定，统一收敛至 `config/apps/*.yaml`；实现了 **Runner 级应用感知注入**，支持根据 `app_id` 自动填充包名和选择器。
- **运维功能增强 (2026-03-15)**：新增了 **“清理未成功轨迹”** API 与前端按钮，支持一键移除 `failed/cancelled` 任务记录及其物理文件。
- **设备可用性提前熔断 (2026-03-15)**：云机 probe 离线状态已接入任务执行链路；活跃 target 连续探测失败后，任务会提前以 `failed_circuit_breaker` / `target_unavailable` 结束，而不是等 RPC 动作超时。
- **场景模板服务化**：AI 提示词场景模板已下沉为 API 服务。

## Workflow Coverage (Ops Scope)
Source of truth: current `plugins/` library (representative workflows).

- Implemented (Unverified): `device_reboot`, `device_soft_reset` (软件复位), `hezi_sdk_probe`, `mytos_device_setup`.

## Distillation Thresholds (Current Plugins)
Complexity is defined by branching or step count > 10. Successes are cumulative.

| Workflow | Steps | Branching | Complexity | Successes Needed |
|---|---:|---|---|---:|
| device_reboot | 2 | no | simple | 3 |
| device_soft_reset | 4 | no | simple | 3 |
| hezi_sdk_probe | 3 | no | simple | 3 |
| mytos_device_setup | 5 | no | simple | 3 |

## Evidence Anchors (Current)
- `.sisyphus/evidence/task-1-db-characterization.txt`
- `.sisyphus/evidence/task-1-db-characterization-error.txt`
- `.sisyphus/evidence/task-3-config-characterization.txt`
- `.sisyphus/evidence/task-3-config-characterization-error.txt`

## Gaps Blocking "Verified"
- VLM coordinate compensation end-to-end verification with real device screenshots.
- Multi-run distillation evidence: need 3+ successful runs per simple plugin, 10+ for complex.
- Port architecture (30001) end-to-end verification: android.* actions need real device testing.
- External account system requirements and implementation evidence (M4).
