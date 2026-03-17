# Roadmap

This roadmap translates `docs/PROJECT_GOALS.md` into milestones with clear completion criteria and a status signal that distinguishes verified work from unverified implementation.

## Status Legend
- Verified: Evidence captured (tests or validation logs).
- Implemented (Unverified): Code exists but verification evidence is missing.
- Partial: Some deliverables exist; key gaps remain.
- Planned: Not implemented yet.

## Milestones

### M0: Baseline Compliance and Runtime Stability
Status: Verified.
Definition of done: Required validation gates pass (`check_no_legacy_imports`, `pytest -q`, RPC-disabled startup, `/health` OK).
Evidence: `.sisyphus/evidence/m0-gate-pytest-full.txt` (2026-03-11). All four gates passed: check_no_legacy_imports OK, 264/264 tests passed, server startup clean, /health 200 OK with 12 plugins loaded.

### M1: AI 自主探索与引导 (AI Bootstrapping)
Status: Verified.
Definition of done: AI 具备“视觉破冰”能力，在无预设 YAML 规则下，通过 VLM 意图推理完成 0-1 的业务通路。
Current state: ✅ **已完成**。通过 `stagnant_limit` 扩展与 `vlm` 强制兜底，彻底打通了 `unknown` 状态下的 AI 自主寻路能力。

### M2: 感知记忆与数据驱动化 (Data-Driven Intermediary)
Status: Verified.
Definition of done: 实现感知回填机制（App Config Backfilling）；支持从 AI 成功轨迹中自动提取 UI 特征，并无缝注入 1.0 原生模式执行。
Current state: ✅ **已完成**。落地了 `TraceLearner` 与 `AppConfigWriter` 闭环。成功 Trace 的 Resource ID 现已具备自动回写 `config/apps/*.yaml` 的能力。

### M3: 终极 YAML 插件蒸馏 (Master YAML Distillation)
Status: In Progress.
Definition of done: 当 1.0 模式成功率与稳定性达标时，系统自动“编译”出脱离 AI 依赖、全量结构化、极速执行的商业级 YAML 插件。
Current state: `GoldenRunDistiller` 基座已就绪，当前正在进行多路径收敛与自动化蒸馏质量优化。

### M4: External User Readiness
Status: Planned.
Definition of done: Account system (authentication + basic access control) is production-ready for external customers.

## Evidence Anchors (Where to Attach Proof)
- Validation gates: `.sisyphus/evidence/` and `docs/project_progress.md`.
- Distillation: `core/golden_run_distillation.py`, `tools/distill_golden_run.py`, `tests/test_gpt_distillation.py`.
- Trace storage: `core/model_trace_store.py` and `engine/agent_executor.py`.

## Next Evidence Actions (Suggested)
- Accumulate representative successful runs (need 10 for complex task distillation gate).
- Run `tools/distill_binding.py` on collected traces to generate login_stage NativeStateBinding draft.
- Verify binding draft enables structured_state path (observed_state_ids non-empty).
- Add multi-run distillation design + tests for M3.
- Run full test suite after recent agent_executor changes to re-verify M0 gate.
