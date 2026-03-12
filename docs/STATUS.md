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
| M3 Distillation to Model-Free YAML Plugin | Partial | Multi-run distillation tool (`tools/distill_multi_run.py`) implemented. Per-plugin success rate API and frontend progress panel added. Single-run distillation also exists. |
| M4 External User Readiness | Planned | Account system work not started. |

## Recent Implementation Notes (Unverified)
- BaseStore migration for TaskStore/TaskEventStore completed; validation pending.
- Config parsing consolidated into Pydantic-based ConfigStore/ConfigLoader; validation pending. ConfigLoader.load() now returns ConfigStore directly.
- DeviceManager split with CloudProbeService wiring; validation pending.
- VLM client lifecycle + retry/backoff alignment implemented; validation pending.
- Port architecture corrected (2026-03-12): 8000/30001/30002 fully separated. AndroidApiClient added for 30001. mytos.* actions now route to android.* (30001) instead of sdk.* (8000).
- Multi-run distillation pipeline added: tools/distill_multi_run.py, /api/tasks/metrics/plugins, /api/tasks/distill/{plugin}.
- VLM screen metadata (width/height) now extracted from compressed capture bytes.
- Device-level exclusive lock added to prevent concurrent task conflicts on same cloud instance.

## Workflow Coverage (Ops Scope)
Source of truth: current `plugins/` library (representative workflows).

- Implemented (Unverified): `device_reboot`, `device_soft_reset`, `hezi_sdk_probe`, `mytos_device_setup`.

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
