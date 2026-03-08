# HANDOFF

> 用于在“新对话 / 新会话”中快速接力项目进度。  
> 每次有意义变更后，请更新本文件中的 **Current Snapshot**、**Open Items**，以及本文的证据链记录。

## 1) Project Identity

- Project: `webrpa`
- Goal: 可独立运行的 Web/RPA 自动化平台（插件化执行 + 控制平面）
- Canonical progress doc: `docs/project_progress.md`

## 2) Current Snapshot (Update this first)

- Phase: **UIStateService unified rollout completed and validated**
- Active plan source: `.sisyphus/plans/ui-state-service-unified.md` (completed)
- Core capabilities now covered:
  - API + Web console (`/web`)，当前公开云机大厅、账号池、设置与实时日志
  - Task control plane (`api/routes/task_routes.py`, `core/task_control.py`) with catalog/metrics/prometheus export
  - Plugin runtime (`engine/*`, `plugins/*`) with unified UI state contract wired through actions, interpreter, and targeted plugin migrations
  - Account pool import/parse/status/pop flows (`api/routes/data.py`, `core/account_parser.py`)
  - Selector pipeline actions with stable not-found semantics (`code=not_found`)
  - Device cloud-model mapping with malformed adapter payload safety guard (`core/device_manager.py`)
  - `UIStateService` rollout is complete across shared contract, native/browser adapters, thin wrappers, interpreter integration, and targeted plugin migrations (`x_mobile_login`, `dm_reply`, `nurture`, `profile_clone` state observation cleanup)
  - Active docs now cover plugin payload rollout, handoff evidence workflow, monitoring rollout, stale-running tuning, and post-rollout watchpoints
- Quality status (latest known baseline):
  - Legacy import guard: pass
  - Tests: full `pytest tests -q` pass
  - RPC-disabled startup + `/health`: pass
  - Monitoring render tool focused test: pass
- Reference docs moved under `docs/reference/`, including the two Chinese atomicity retrospectives
  - Legacy import guard: pass
  - Health check (`MYT_ENABLE_RPC=0`): pass

## 3) What Was Recently Done

1. Completed the `ui-state-service-unified` rollout and final validation wave.
   - Unified the shared read-only UI state contract across native/mobile and browser/web observation paths.
   - Kept adapter-specific evidence detail while routing workflow-facing state checks through one service boundary.
   - Finished thin wrapper and action registration wiring, interpreter/condition integration, and targeted plugin migrations.
2. Earlier completed follow-up docs and watchpoint work remains in place:
   - `docs/reference/sdk_actions_followup_assessment.md`
   - `docs/reference/shared_json_store_watchpoint.md`
   - `docs/reference/x_mobile_login_compression_watchpoint.md`
3. Expanded rollout/operator docs:
   - `docs/plugin_input_contract.md`
   - `docs/monitoring_rollout.md`
   - `docs/stale_running_recovery_tuning.md`
4. Standardized review handoff expectations in `docs/HANDOFF.md` and checked in rendered monitoring examples under `config/monitoring/rendered/single-node-example/`.
5. Moved the two Chinese atomicity retrospectives from repo root into `docs/reference/` and updated cross-links.
6. Earlier control-plane and runtime hardening already on this branch includes:
   - scheduler/plugin dispatch observability events
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
9. Applied post-implementation hardening fixes:
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
    - aligned plugin manifest input coverage for script payload references (`blogger_scrape`, `follow_interaction`, `home_interaction`, `quote_interaction`, `dm_reply`, `x_mobile_login`)
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
    - added `sitecustomize.py` to ensure parent import path for `*` package bootstrap in root-context execution
    - hardened `tools/check_plugin_manifest_inputs.py` direct-script execution path bootstrap
    - configured pytest `testpaths = tests` in `pyproject.toml` to avoid unintended `tmp/tests` collection
    - added `httpx` to `requirements.txt` as explicit dependency declaration
    - switched task-control DB tests to per-test `tmp_path` SQLite files to prevent shared `config/data` contention and intermittent schema/I/O failures
25. Re-audited documentation against current implementation and corrected capability descriptions:
    - aligned `README.md`, `docs/WEB_GUI_EMBED.md`, `docs/project_progress.md`, `docs/atomic_features.md`
    - clarified public account-pool/data APIs and task metrics/catalog endpoints
    - clarified that `web/js/features/tasks.js` exists but `web/index.html` does not yet expose an independent task page
    - aligned desktop-embed examples with the current `127.0.0.1:8001` baseline

## 4) Open Items (Next work queue)

- [x] Independent re-audit on latest F1/F2/F4 evidence for external sign-off - PASS (2026-03-05, session `ses_3434d6326ffehaYo5gU4vpd7Gj`)
- [x] UIStateService unified rollout implementation and final validation - COMPLETE
- [ ] Commit/PR packaging for the completed UIStateService rollout and docs sync batch
- [ ] External monitoring deployment: apply `docs/monitoring_rollout.md` and `config/monitoring/rendered/single-node-example/` in a real Prometheus/Alertmanager environment
- [ ] Runtime rollout execution: align `MYT_STRICT_PLUGIN_UNKNOWN_INPUTS` and `MYT_TASK_STALE_RUNNING_SECONDS` with actual deployment manifests and verify the live `/health` policy snapshot
- [ ] Keep the UIStateService reuse boundary and existing watchpoint docs under review, only reopening implementation work if new plugins drift back toward duplicated state ladders or other documented triggers

## 5) How to Continue in a New Conversation

Start prompt template:

```text
请先阅读 docs/HANDOFF.md、docs/project_progress.md、docs/current_main_status.md、docs/monitoring_rollout.md 和 docs/stale_running_recovery_tuning.md；
优先执行 Open Items 第 1 项（提交/PR 打包），随后推进第 2-3 项（外部监控与运行时基线落地）；
每完成一个子项即更新 docs/project_progress.md，并执行所需门禁与 `/health` 验证。
```

## 6) Required Validation Commands

Run from repository root:

```bash
./.venv/bin/python tools/update_project_progress.py
./.venv/bin/python tools/check_no_legacy_imports.py
./.venv/bin/python tools/check_plugin_manifest_inputs.py
./.venv/bin/python -m pytest tests -q
MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
curl http://127.0.0.1:8001/health
```

Alternative one-shot gate:

```bash
./tools/run_migration_gates.sh
```

## 7) Evidence and Review Handoff Workflow

### 7.1 When Evidence Is Required

- 凡是“有意义变更”都要留证据，最少覆盖：改了什么、怎么验证、产物放在哪里。
- 如果变更无法只靠 diff 说清楚，评审与交接必须能从本文和 `.sisyphus/evidence/` 直接追到验证过程。
- docs-only 变更可以只留文档证据，不必为了补证据额外跑会产生工作区噪音的运行命令。

### 7.2 Minimum Evidence by Change Type

- 代码变更：至少包含目标范围说明、执行过的命令、命令结果摘要、相关测试或门禁结论。
- 文档或配置变更：至少包含受影响文件、需要同步的约束或基线、人工校对结论；如果没有执行命令，要明确写 `docs-only, no runtime commands needed`。
- 发布、回滚或运维变更：至少包含环境范围、渲染或部署命令、生成的配置产物、上线后检查点。

### 7.3 Storage and Naming Rules

- 所有交接证据统一放在 `.sisyphus/evidence/`。
- 文件名统一用 `YYYYMMDD-<topic>-<kind>.<ext>`，其中：
  - `topic` 用短横线小写短语，直接对应本次改动主题。
  - `kind` 只用能说明用途的固定词，例如 `summary`、`commands`、`validation`、`handoff`、`rendered-config`。
  - `ext` 按内容选最简单格式，优先 `md`、`txt`、`json`、`log`。
- 一个完整证据链至少要能让评审看到 3 类东西：变更说明、命令或人工检查记录、最终交接结论。
- 如果同一主题有多份证据，保持同一个日期与 `topic` 前缀，按 `kind` 区分，不要发散命名。

### 7.4 Handoff Update Rules

- `docs/HANDOFF.md` 是交接与证据流程的单一事实来源。
- 每次完成有意义变更后，在本文 `Current Snapshot` 写结果，在 `What Was Recently Done` 记录事实，在 `Open Items` 更新后续动作。
- 交接说明必须点名本次证据链的文件路径，至少引用一个 summary 文件和一个 validation 或 commands 文件。
- 如果证据缺项，交接说明里要直接写缺什么、为什么缺、由谁在下一步补齐。

### 7.5 Reproducible Review Path

评审或发布接力时，按这个顺序检查：

1. 先读 `docs/HANDOFF.md` 的 `Current Snapshot`、`What Was Recently Done`、`Open Items`。
2. 记下对应主题名，然后到 `.sisyphus/evidence/` 查找同一 `YYYYMMDD-<topic>-*` 前缀的证据文件。
3. 先看 `summary`，再看 `commands` 或 `validation`，最后看 `handoff`，确认变更、验证、结论能串成闭环。
4. 如果交接提到代码门禁，就按本文 `Required Validation Commands` 复跑；如果交接写明 `docs-only, no runtime commands needed`，则只做文档比对与路径核对。

### 7.6 Example Evidence Chain

下面是一个完整但精简的例子，展示从变更到交接的最小闭环：

- 变更主题：标准化 handoff 证据流程
- 证据文件：
  - `.sisyphus/evidence/20260308-handoff-evidence-summary.md`
  - `.sisyphus/evidence/20260308-handoff-evidence-commands.txt`
  - `.sisyphus/evidence/20260308-handoff-evidence-handoff.md`
- `20260308-handoff-evidence-summary.md` 写明：修改了 `docs/HANDOFF.md`，新增证据命名规则、最低证据要求、评审复现路径。
- `20260308-handoff-evidence-commands.txt` 写明：`docs-only, no runtime commands needed`，并记录人工检查项，例如“核对 `.sisyphus/evidence/` 命名规则与 `docs/project_progress.md` 的待办是否一致”。
- `20260308-handoff-evidence-handoff.md` 写明：评审先读 `docs/HANDOFF.md`，再按同前缀查看 `summary` 与 `commands`，确认这是 docs-only 改动，无需额外运行服务门禁。

## 8) Risks / Notes

- Runtime DB file `config/data/tasks.db` is environment artifact; do not include in commits.
- Keep standalone constraints: no `tasks.*` and no `app.*` imports.
