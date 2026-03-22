# Project Status Matrix

This document provides a concise "done vs not-done" view tied to the goal and roadmap definitions. It does not replace `docs/governance/project_progress.md` (which is a living log), nor `docs/strategy/ROADMAP.md` (which defines milestones).

## Status Legend
- Verified: Evidence captured (tests or validation logs).
- Implemented (Unverified): Code exists but verification evidence is missing.
- Partial: Some deliverables exist; key gaps remain.
- Planned: Not implemented yet.

## Launch 1.0 Readiness Snapshot

- Launch 1.0 scope is functionally complete for **device management, task scheduling, and plugin execution**.
- Validation gates passed for this launch-readiness state:
  - `./.venv/bin/python tools/check_no_legacy_imports.py`
  - `./.venv/bin/python -m pytest tests -q`
  - default `uvicorn api.server:app` startup + `/health`
  - `MYT_ENABLE_RPC=0` compatibility startup + `/health`
- W1.2 is code-aligned and test-aligned: device-scoped stop wording matches the frozen 1.0 contract, `node --test "web/js/features/device_detail_modal.test.js"` passed, and `npm --prefix web run typecheck` passed.
- W1.2 hands-on browser QA remains environment-blocked. Playwright launch could not start because Chrome or Chromium was unavailable, and install attempts timed out. This launch state does **not** claim full browser hands-on verification.
- Current backend `/web` behavior remains an API-side console entry shim: if `MYT_FRONTEND_URL` is unset it returns `501` with frontend deployment guidance; this launch state does **not** claim backend-hosted web assets or browser hands-on console verification.
- M5/WebRTC is not part of this completion state. Current launch readiness covers the existing screenshot-preview plus light-control path, not real-time WebRTC takeover.

## Milestone Status

| Milestone | Status | Evidence Notes |
|---|---|---|
| M0 Baseline Compliance | Verified | 2026-03-18 本地复核通过：imports、pytest、启动、/health OK。 |
| M1 AI Bootstrapping (探索) | Implemented (Unverified) | VLM 自主寻路与 `unknown` 兜底链路已实现，但缺少统一近期证据锚点。 |
| M2 Data-Driven Mode (演进) | Implemented (Unverified) | `TraceLearner` / `AppConfigWriter` 已落地，但缺少统一近期证据锚点。 |
| M3 YAML Mastery (蒸馏) | Partial | `GoldenRunDistiller` 基座与相关工具已存在，仍缺多轮蒸馏证据闭环。 |
| Launch 1.0 readiness | Verified | 1.0 launch scope limited to device management, task scheduling, and plugin execution. Validation gates passed. W1.2 browser hands-on QA remains environment-blocked. M5/WebRTC excluded from this state. |

- **文本化文档对齐 (2026-03-13)**：完成全量 `docs/` 内容审计，确立了多云机动态端口公式，修复了 SDK/API 文档的陈旧代码引用。
- **执行器热点拆分完成 (2026-03-18)**：`agent_executor` 已拆为 runtime/planning/trace/support/types 多文件结构，`sdk_actions` 已拆为 façade + action catalog，当前热点文件继续演进时的变更面明显缩小。
- **Skills 演进战略确立**：发布了 `docs/strategy/SKILLS_EVOLUTION.md`，识别出 ActionRegistry、Variable Scoping、Error Hooks 等核心架构优化点。
- **AI 观察自愈能力**：针对 X App 复杂界面的 XML 4KB 截断问题实现了自愈式捕获。
- **App 配置归一化与感知**：移除了硬编码绑定，统一收敛至 `config/apps/*.yaml`；实现了 **Runner 级应用感知注入**，支持根据 `app_id` 自动填充包名和选择器。
- **运维功能增强 (2026-03-15)**：新增了 **“清理未成功轨迹”** API 与前端按钮，支持一键移除 `failed/cancelled` 任务记录及其物理文件。
- **设备可用性提前熔断 (2026-03-15)**：云机 probe 离线状态已接入任务执行链路；活跃 target 连续探测失败后，任务会提前以 `failed_circuit_breaker` / `target_unavailable` 结束，而不是等 RPC 动作超时。
- **场景模板服务化**：AI 提示词场景模板已下沉为 API 服务。

## Workflow Coverage (Ops Scope)
Source of truth for shipped manifests: current `plugins/` library. Source of truth for **verified launch claims**: this section only.

- Bundled plugin library (currently loaded by `/health`): `device_reboot`, `one_click_new_device`, `x_clone_profile`, `x_follow_followers`, `x_home_interaction`, `x_login`, `x_nurture`, `x_quote_intercept`, `x_reply_dm`, `x_scrape_blogger`.
- Workflow-level verification currently documented here:
  - Implemented (Unverified): `one_click_new_device`
  - Implemented (Unverified): `device_reboot`
- The bundled `x_*` workflows are present in the repo/plugin loader, but this document does **not** currently claim they are individually launch-verified.

## Distillation Thresholds (Current Plugins)
Complexity is defined by branching or step count > 10. Successes are cumulative.

| Workflow | Steps | Branching | Complexity | Successes Needed |
|---|---:|---|---|---:|
| one_click_new_device | 6 | no | simple | 3 |
| device_reboot | 4 | no | simple | 3 |

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
