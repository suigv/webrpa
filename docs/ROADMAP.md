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

### M1: Vision-Model Script Execution MVP
Status: Partial.
Definition of done: Vision-capable executor can complete representative ops workflows with bounded retries, loop detection, and stable action contracts.
Current state (unverified): GPT executor and VLM path are implemented. A representative vision workflow confirmed successful on real device (2026-03-10). Screen metadata (screen_width/height) now parsed from XML bounds and injected into trace. Binding-free AI runs confirmed working.

### M2: Evidence Capture and Diagnostics
Status: Partial.
Definition of done: Every run captures structured traces, screenshots with real screen metadata, and action results sufficient for failure diagnosis and distillation.
Current state (unverified): Evidence collection significantly improved (2026-03-12):
- XML dump now collected unconditionally every step (not only on observation failure).
- XML saved as full file under `traces/<task>/<run>/xml/<target>/`, no longer truncated to 4000 chars.
- screen_width/height parsed from XML root bounds and injected into screen_capture.metadata.
- task.observation and task.planning events now emitted per step for real-time log visibility.
- DB event poller added to broadcast subprocess task events to WebSocket clients.

### M3: Distillation to Model-Free YAML Plugin
Status: Verified (Stage 1).
Definition of done: Multi-run evidence can distill a reviewable YAML plugin that passes replay smoke checks without model dependency.
Distillation gate: simple tasks require 3 successful runs; complex tasks require at most 10 successful runs.
Current state (Verified): 
- XML 截断问题已通过 `distill_binding.py` 的正则回溯机制解决。
- 实现了通用的 `app_stage` 探测机制，支持从 `config/apps/*.yaml` 动态加载特征，不再依赖硬编码框架。
- 成功为 X App 产生了首页 binding 选择器。
- 自动 Selector Merge 机制已在 GoldenRunDistiller 中闭环。
- 下一步：支持多 trace 聚合蒸馏 (Multi-run) 以提高 feature 覆盖率。

### M4: External User Readiness
Status: Planned.
Definition of done: Account system (authentication + basic access control) is production-ready for external customers.

## Evidence Anchors (Where to Attach Proof)
- Validation gates: `.sisyphus/evidence/` and `docs/project_progress.md`.
- Distillation: `core/golden_run_distillation.py`, `tools/distill_golden_run.py`, `tests/test_gpt_distillation.py`.
- Trace storage: `core/model_trace_store.py` and `engine/gpt_executor.py`.

## Next Evidence Actions (Suggested)
- Accumulate representative successful runs (need 10 for complex task distillation gate).
- Run `tools/distill_binding.py` on collected traces to generate login_stage NativeStateBinding draft.
- Verify binding draft enables structured_state path (observed_state_ids non-empty).
- Add multi-run distillation design + tests for M3.
- Run full test suite after recent gpt_executor changes to re-verify M0 gate.
