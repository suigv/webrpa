# HANDOFF

> 用于在“新对话 / 新会话”中快速接力项目进度。  
> 每次有意义变更后，请更新本文件中的 **Current Snapshot** 与 **Open Items**。

## 1) Project Identity

- Project: `webrpa` (standalone package namespace: `new.*`)
- Goal: 可独立运行的 Web/RPA 自动化平台（插件化执行 + 控制平面）
- Canonical progress doc: `docs/project_progress.md`

## 2) Current Snapshot (Update this first)

- Phase: **Legacy capability extraction closed (Tasks 1-12 + Final Verification F1/F2/F3/F4 complete)**
- Migration plan source: `.sisyphus/plans/legacy-feature-extraction.md`
- Core capabilities now covered:
  - API + Web console (`/web`)
  - Task control plane (`api/routes/task_routes.py`, `core/task_control.py`)
  - Plugin runtime (`engine/*`, `plugins/*`) with migrated reboot/login/interaction/scrape-clone paths
  - Selector pipeline actions with stable not-found semantics (`code=not_found`)
  - Device cloud-model mapping with malformed adapter payload safety guard (`core/device_manager.py`)
- Quality status (latest known baseline):
  - Full gates: `./tools/run_migration_gates.sh` -> pass
  - Tests: `209 passed`
  - Legacy import guard: pass
  - Health check (`MYT_ENABLE_RPC=0`): pass

## 3) What Was Recently Done

1. Closed Final Verification mismatches from migration audits:
   - Task 6 evidence/contract aligned to selector `not_found` behavior
   - Task 11 unsupported-task evidence chain hardened
2. Added runtime safety hardening in `core/device_manager.py`:
   - guarded `HostPort` parsing with `try/except (TypeError, ValueError)`
3. Added/updated focused tests:
   - `tests/test_selector_pipeline_actions.py`
   - `tests/test_cloud_model_info.py`
4. Updated final evidence set:
   - `.sisyphus/evidence/f1-plan-compliance.txt`
   - `.sisyphus/evidence/f2-runtime-safety.txt`
   - refreshed task evidence files for Task 6/11/12 and scope fidelity
5. Removed out-of-scope drift from `web/*` and re-validated full migration gates (pass)
6. Added scheduler/plugin dispatch observability events:
   - `task.dispatching` emitted before runner dispatch
   - `task.dispatch_result` emitted immediately after runner returns
   - covered by SSE lifecycle regression in `tests/test_task_scheduling_events.py`
7. Added plugin dispatch hardening in `engine/runner.py`:
   - manifest input validation (required/type) before interpreter execution
   - script action gate: must be registered and within allowed namespaces
    - dispatch error code normalization (`unsupported_task`, `missing_required_param`, `invalid_params`, `unknown_action`, `action_not_allowed`, `plugin_dispatch_error`)
    - regression tests updated/added in `tests/test_runner_plugin_dispatch.py`, `tests/test_x_login_contract_schema.py`, `tests/test_x_login_runtime_integration.py`
8. Added reliability/idempotency hardening in task control plane:
   - API supports idempotency key (payload field `idempotency_key` or header `X-Idempotency-Key`)
   - active duplicate submits (`pending`/`running`) now return existing task instead of creating duplicate task records
   - cancellation request now consistently yields `cancelled` state even on runner exception path
   - regression tests added in `tests/test_task_control_plane.py` and `tests/test_task_cancellation.py`
9. Applied post-implementation oracle hardening fixes:
   - dedupe lookup+insert made atomic in `TaskStore.create_or_get_active_task(...)` to avoid TOCTOU duplicate-submit race
    - API rejects body/header idempotency key conflicts with `400` (`idempotency key mismatch between body and header`)
    - task SSE event stream now reads from controller-bound event store for consistent control-plane/event-plane source
10. Added task event aggregation metrics endpoint:
     - `GET /api/tasks/metrics` returns task `status_counts`, `event_type_counts`, and terminal outcomes (`completed`/`failed`/`cancelled`) in a rolling time window
     - pending-task cancel path now emits `task.cancelled` event so cancellation outcomes are counted consistently in event metrics
     - regression test added: `tests/test_task_control_plane.py::test_task_metrics_aggregates_status_and_event_counts`
11. Added alert-threshold evaluation to task metrics endpoint:
    - `/api/tasks/metrics` now accepts `failure_rate_threshold`, `cancellation_rate_threshold`, `min_terminal_samples`
    - response now includes derived `rates` (`completion_rate`, `failure_rate`, `cancellation_rate`) and `alerts` decision block (`evaluated`, `triggered`, `reasons`, `thresholds`, `terminal_total`)
    - regression test extended to validate both non-evaluated default window and evaluated+triggered threshold scenario
12. Added Prometheus scrape export for task metrics:
    - new endpoint `GET /api/tasks/metrics/prometheus` exposes status/event/terminal/rate/alert gauges in Prometheus text exposition format
    - query params mirror JSON metrics endpoint (`window_seconds`, `failure_rate_threshold`, `cancellation_rate_threshold`, `min_terminal_samples`) for alert-rule parity
    - regression test extended in `tests/test_task_control_plane.py` to verify export content and triggered alert metric
13. Added cross-process idempotency regression coverage:
    - new test `test_idempotency_key_dedupes_pending_task_across_controller_restart` verifies pending-task dedupe survives controller restart when sharing persisted task DB
    - validates duplicate submit behavior is store-backed rather than controller-instance-local
14. Stabilized idempotency duplicate-submit regression isolation:
    - `test_duplicate_submit_with_same_idempotency_key_returns_same_task` now uses an isolated temporary DB file
    - avoids pagination/history-coupled flakiness from shared task history accumulation during repeated full-gate runs
15. Added in-repo monitoring wiring assets for external Prometheus integration:
    - added scrape template: `config/monitoring/prometheus/task_metrics_scrape.example.yml`
    - added alert rule template: `config/monitoring/prometheus/task_metrics_alerts.yml`
    - added parameterized rendering tool: `tools/render_task_metrics_monitoring.py`
    - added regression tests: `tests/test_task_metrics_monitoring_tool.py`
16. Expanded cross-process idempotency coverage for running/retry windows:
    - added `test_idempotency_key_dedupes_running_task_across_controller_restart`
    - added `test_idempotency_key_dedupes_retry_scheduled_task_across_controller_restart`
    - confirms duplicate submit stays deduped across controller restart when task is `running` or retry-scheduled `pending`
17. Added stale-running recovery on controller startup:
    - `TaskController.start()` now performs store-backed stale-running recovery before worker loop starts
    - `TaskStore.recover_stale_running_tasks(...)` reverts stale `running` rows to `pending`, clears stale execution timestamps, and keeps task records resumable
    - recovered tasks are re-enqueued with existing priority/schedule semantics and emit `task.recovered_stale_running`
    - stale threshold configurable via env `MYT_TASK_STALE_RUNNING_SECONDS` (default `300`)
    - regression test added: `tests/test_task_control_plane.py::test_stale_running_task_recovered_and_requeued_on_controller_start`
18. Completed plugin manifest input completeness audit groundwork:
    - added payload-reference guard tool: `tools/check_plugin_manifest_inputs.py`
    - integrated guard into one-shot migration gates (`tools/run_migration_gates.sh`)
    - added regression tests: `tests/test_plugin_manifest_input_guard.py`
    - aligned plugin manifest input coverage for script payload references (`blogger_scrape`, `follow_interaction`, `home_interaction`, `quote_interaction`, `dm_reply`, `x_auto_login`)
19. Enforced strict unknown-parameter rejection for plugin runtime payloads:
    - `engine/runner.py::_validate_plugin_payload` now rejects undeclared payload keys (except reserved `task`) with `code=invalid_params`
    - preserves existing dispatch error envelope (`status=failed_config_error`, `checkpoint=dispatch`)
    - added regression tests in `tests/test_runner_plugin_dispatch.py` for unknown-key rejection and `task` allowlist behavior
20. Added rollout toggle for strict plugin unknown-parameter validation:
    - new env `MYT_STRICT_PLUGIN_UNKNOWN_INPUTS` controls unknown-key rejection (`1` default, accepts `0/false/no/off` to disable)
    - keeps strict mode as default while enabling environment-based phased rollout
    - added regression test for disabled-mode compatibility in `tests/test_runner_plugin_dispatch.py`
21. Added runtime policy visibility and caller contract doc for rollout operations:
    - `/health` now exposes `task_policy.strict_plugin_unknown_inputs` and `task_policy.stale_running_seconds`
    - added health regression coverage in `tests/test_health_smoke.py` for env-driven policy values and stale-threshold fallback/clamping
    - added external contract doc: `docs/plugin_input_contract.md` (validation rules, env baseline, rollout strategy)
22. Expanded monitoring delivery-chain assets for Alertmanager handoff:
    - added template: `config/monitoring/alertmanager/task_metrics_route.example.yml`
    - extended `tools/render_task_metrics_monitoring.py` to render `task_metrics_alertmanager.yml`
    - extended regression tests: `tests/test_task_metrics_monitoring_tool.py`
23. Added stale-running recovery observability alert rule:
    - `config/monitoring/prometheus/task_metrics_alerts.yml` now includes `NewTaskStaleRunningRecovered`
    - rendering tool emits the same rule for deployment parity
24. Fixed bootstrap/test-context instability and DB test flakiness:
    - added `sitecustomize.py` to ensure parent import path for `new.*` package bootstrap in root-context execution
    - hardened `tools/check_plugin_manifest_inputs.py` direct-script execution path bootstrap
    - added `pytest.ini` (`testpaths = tests`) to avoid unintended `tmp/tests` collection
    - added `httpx` to `requirements.txt` as explicit dependency declaration
    - switched task-control DB tests to per-test `tmp_path` SQLite files to prevent shared `config/data` contention and intermittent schema/I/O failures

## 4) Open Items (Next work queue)

- [x] Independent re-audit (oracle) on latest F1/F2/F4 evidence for external sign-off — PASS (2026-03-05, session `ses_3434d6326ffehaYo5gU4vpd7Gj`)
- [ ] Commit/PR packaging for migration-closure batch (if not yet submitted)
- [ ] Post-migration hardening roadmap (next): complete external monitoring delivery chain (Prometheus/Alertmanager deployment-side integration), and tune/operationalize stale-running threshold policy
- [ ] Rollout execution: align environment baselines (`MYT_STRICT_PLUGIN_UNKNOWN_INPUTS`, `MYT_TASK_STALE_RUNNING_SECONDS`) with deployment manifests and Alertmanager routing policy

## 5) How to Continue in a New Conversation

Start prompt template:

```text
请先阅读 new/docs/HANDOFF.md、new/docs/project_progress.md 和 .sisyphus/plans/legacy-feature-extraction.md；
优先执行 Open Items 第 2 项（提交打包），随后推进第 3 项（迁移后加固）；
每完成一个子项即更新 docs/project_progress.md，并执行 ./tools/run_migration_gates.sh。
```

## 6) Required Validation Commands

Run from parent directory of `new/`:

```bash
./new/.venv/bin/python new/tools/update_project_progress.py
./new/.venv/bin/python new/tools/check_no_legacy_imports.py
./new/.venv/bin/python new/tools/check_plugin_manifest_inputs.py
./new/.venv/bin/python -m pytest new/tests -q
MYT_NEW_ROOT=$(pwd)/new MYT_ENABLE_RPC=0 ./new/.venv/bin/python -m uvicorn new.api.server:app --host 127.0.0.1 --port 8001
curl http://127.0.0.1:8001/health
```

Alternative one-shot gate (preferred for migration closure):

```bash
./tools/run_migration_gates.sh
```

## 7) Risks / Notes

- Runtime DB file `new/config/data/tasks.db` is environment artifact; do not include in commits.
- Keep standalone constraints: no `tasks.*` and no `app.*` imports.
