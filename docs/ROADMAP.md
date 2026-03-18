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
Evidence: Re-verified in local workspace on 2026-03-18. `check_no_legacy_imports` passed, `pytest tests -q` passed, server startup clean, `/health` returned 200 OK with 4 plugins loaded.

### M1: AI 自主探索与引导 (AI Bootstrapping)
Status: Implemented (Unverified).
Definition of done: AI 具备“视觉破冰”能力，在无预设 YAML 规则下，通过 VLM 意图推理完成 0-1 的业务通路。
Current state: 相关能力已实现，包括 `unknown` 状态下的 VLM 兜底与自主寻路；但当前文档未绑定统一、可复核的近期证据，因此暂不标记为 Verified。

### M2: 感知记忆与数据驱动化 (Data-Driven Intermediary)
Status: Implemented (Unverified).
Definition of done: 实现感知回填机制（App Config Backfilling）；支持从 AI 成功轨迹中自动提取 UI 特征，并无缝注入 1.0 原生模式执行。
Current state: `TraceLearner` 与 `AppConfigWriter` 已落地，成功 Trace 可回写 `config/apps/*.yaml`；但当前缺少近期统一证据链，因此暂不标记为 Verified。

### M3: 终极 YAML 插件蒸馏 (Master YAML Distillation)
Status: Partial.
Definition of done: 当 1.0 模式成功率与稳定性达标时，系统自动“编译”出脱离 AI 依赖、全量结构化、极速执行的商业级 YAML 插件。
Current state: `GoldenRunDistiller` 基座已就绪，当前正在进行多路径收敛与自动化蒸馏质量优化。

### M4: External User Readiness
Status: Planned.
Definition of done: Account system (authentication + basic access control) is production-ready for external customers.

## Evidence Anchors (Where to Attach Proof)
- Validation gates: `.sisyphus/evidence/` and `docs/project_progress.md`.
- Distillation: `core/golden_run_distillation.py`, `tools/distill_golden_run.py`, `tools/distill_multi_run.py`, `tests/test_llm_draft_refiner.py`.
- Trace storage: `core/model_trace_store.py` and `engine/agent_executor.py`.

## Next Evidence Actions (Suggested)
- Accumulate representative successful runs (need 10 for complex task distillation gate).
- Review collected traces and promote stable signals into `config/apps/<app>.yaml`.
- Verify app config backfill improves structured observation quality (for example, clearer `observed_state_ids` and fewer fallback-only steps).
- Add multi-run distillation design + tests for M3.
- Run full test suite after recent agent_executor changes to re-verify M0 gate.
