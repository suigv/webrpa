# HANDOFF

> 用于在“新对话 / 新会话”中快速接力项目进度。  
> 每次有意义变更后，请更新本文件中的 **Current Snapshot**、**Open Items**，以及本文的证据链记录。

## 1) Project Identity

- Project: `webrpa`
- Goal: 可独立运行的 Web/RPA 自动化平台（插件化执行 + 控制平面）
- Canonical progress doc: `docs/project_progress.md`

### Canonical doc ownership

- `README.md`: entrypoint and summary only.
- `docs/project_progress.md`: canonical capability and progress ledger.
- `docs/current_main_status.md`: short canonical status ledger.
- `docs/HANDOFF.md`: continuation runbook, alignment workflow, and evidence handoff.
- `docs/README.md`: optional index only, not canonical.
- Validator-facing rule: status or progress claims belong in the canonical status docs, while this file owns handoff steps, evidence paths, and continuation guidance.

## 2) Current Snapshot (Update this first)

- Phase: **2026-03-09 executor wave and docs-sync refresh completed for this batch**
- Active plan source: `.sisyphus/plans/webrpa-docs-progress-sync.md` (Task 4 handoff refresh)
- Latest completed implementation wave now captured for handoff use:
  - `wait_until` polling semantics are tightened and covered for success-before-timeout, timeout text, `on_timeout goto`, `on_fail` fallback, cancellation, and dynamic re-polling against changing context data
  - `ExecutionContext.session.defaults` is the minimal task-scoped seam, with explicit action params still winning over session defaults and raw payload fallback
  - UI-state observation coverage expanded conservatively with `timeline_candidates`, `follow_targets`, and first-item aliases without changing the top-level result shape
  - Shared UI-state semantics are further tightened: result construction, timing, and browser polling now flow through shared helpers, and native bindings live in a dedicated registry module
  - Bounded helpers `ui.navigate_to` and `ui.fill_form` are part of the completed rollout, but they remain bounded navigation/form helpers, not workflow-level recovery
  - `x_mobile_login` wording is narrowed to repeated runtime plumbing only: `device_ip` is covered via `_target`-derived/session defaults, while `package` is only claimed as no longer needing per-step repetition, without implying `_target` sources it
  - `/web` remains documented only as the smoke-backed static console entrypoint
  - `/ws/logs` keeps user-facing documentation only because the dedicated route regression now covers ping and filtered broadcast behavior
  - Runtime/control-plane validation for the same wave is backed by targeted tests plus `MYT_ENABLE_RPC=0` startup and `/health` smoke evidence
- Current docs-sync evidence chain:
  - summary: `.sisyphus/evidence/20260309-docs-progress-sync-summary.md`
  - commands: `.sisyphus/evidence/20260309-docs-progress-sync-commands.md`
  - validation: `.sisyphus/evidence/20260309-docs-progress-sync-validation.md`
  - this file remains the continuation/runbook surface; canonical status details stay in `docs/project_progress.md` and `docs/current_main_status.md`
- Quality status for the latest completed wave, from existing evidence:
  - Login workflow targeted tests: pass
  - Runtime/control-plane targeted tests: pass
  - RPC-disabled startup + `/health`: pass
  - Workflow-level conservative recovery extraction: **DEFERRED**, keep as watchpoint only

## 3) What Was Recently Done

1. Completed the 2026-03-09 docs-sync evidence chain for this batch:
   - `.sisyphus/evidence/20260309-docs-progress-sync-summary.md`
   - `.sisyphus/evidence/20260309-docs-progress-sync-commands.md`
   - `.sisyphus/evidence/20260309-docs-progress-sync-validation.md`
   - Together they record the allowed claims, bounded docs+tool regeneration commands, and final validation conclusions.
2. Added the 2026-03-09 docs-sync source-of-truth matrix at `.sisyphus/evidence/20260309-docs-progress-sync-summary.md`.
   - It defines the allowed completed, deferred, and next-step claims for `README.md`, `docs/project_progress.md`, `docs/current_main_status.md`, and `docs/HANDOFF.md`.
   - It also locks the docs hierarchy so this file stays a continuation/runbook surface rather than the only source of truth.
3. Captured the latest completed executor wave for handoff wording:
   - `wait_until` polling semantics and dynamic re-poll coverage are now treated as completed and evidenced.
   - `ExecutionContext.session.defaults` is documented as the minimal task-scoped seam with explicit-param override order preserved.
   - UI-state observation coverage now includes `timeline_candidates`, `follow_targets`, and first-item aliases without a result-shape redesign.
   - Shared UI-state helpers now own result construction, timing, and browser polling semantics, while native binding registration has been split out of the adapter.
4. Recorded bounded workflow-helper progress from the same wave:
   - `ui.navigate_to` and `ui.fill_form` are completed bounded helpers, not a broad recovery framework.
   - `x_mobile_login` reduced repeated runtime plumbing through manifest defaults and `_target`-derived session defaults while keeping `status` and `message` contracts stable, without claiming `_target` directly provides `package`.
5. Linked the completed wave back to validation evidence already on hand:
   - `.sisyphus/evidence/20260309-docs-progress-sync-summary.md` and `.sisyphus/evidence/20260309-docs-progress-sync-validation.md` together cover the targeted login workflow tests plus the `login completed` runtime smoke for this docs-sync wave.
   - `.sisyphus/evidence/20260309-docs-progress-sync-summary.md` and `.sisyphus/evidence/20260309-docs-progress-sync-validation.md` together cover the targeted runtime/control-plane validation plus `MYT_ENABLE_RPC=0` startup and `/health` smoke conclusion.
   - `.sisyphus/evidence/20260309-docs-progress-sync-summary.md` and `.sisyphus/evidence/20260309-docs-progress-sync-validation.md` keep workflow-level conservative recovery extraction explicitly **DEFERRED** for this handoff trail.
6. Earlier completed work from the previous rollout remains valid and available as branch context:
   - `ui-state-service-unified` rollout and final validation wave
   - `docs/plugin_input_contract.md`, `docs/monitoring_rollout.md`, `docs/stale_running_recovery_tuning.md`
   - `docs/reference/sdk_actions_followup_assessment.md`, `docs/reference/shared_json_store_watchpoint.md`, `docs/reference/x_mobile_login_compression_watchpoint.md`
7. Earlier control-plane and runtime hardening already on this branch includes:
   - scheduler/plugin dispatch observability events
   - `task.dispatching` emitted before runner dispatch
   - `task.dispatch_result` emitted immediately after runner returns
   - covered by SSE lifecycle regression in `tests/test_task_scheduling_events.py`
8. Added plugin dispatch hardening in `engine/runner.py`:
   - manifest input validation (required/type) before interpreter execution
   - script action gate: must be registered and within allowed namespaces
    - dispatch error code normalization (`unsupported_task`, `missing_required_param`, `invalid_params`, `unknown_action`, `action_not_allowed`, `plugin_dispatch_error`)
    - regression tests updated/added in `tests/test_runner_plugin_dispatch.py`, `tests/test_x_login_contract_schema.py`, `tests/test_x_login_runtime_integration.py`
9. Added reliability/idempotency hardening in task control plane:
   - API supports idempotency key (payload field `idempotency_key` or header `X-Idempotency-Key`)
   - active duplicate submits (`pending`/`running`) now return existing task instead of creating duplicate task records
   - cancellation request now consistently yields `cancelled` state even on runner exception path
   - regression tests added in `tests/test_task_control_plane.py` and `tests/test_task_cancellation.py`
10. Applied post-implementation hardening fixes:
   - dedupe lookup+insert made atomic in `TaskStore.create_or_get_active_task(...)` to avoid TOCTOU duplicate-submit race
    - API rejects body/header idempotency key conflicts with `400` (`idempotency key mismatch between body and header`)
    - task SSE event stream now reads from controller-bound event store for consistent control-plane/event-plane source
11. Added task event aggregation metrics endpoint:
     - `GET /api/tasks/metrics` returns task `status_counts`, `event_type_counts`, and terminal outcomes (`completed`/`failed`/`cancelled`) in a rolling time window
     - pending-task cancel path now emits `task.cancelled` event so cancellation outcomes are counted consistently in event metrics
     - regression test added: `tests/test_task_control_plane.py::test_task_metrics_aggregates_status_and_event_counts`
12. Added alert-threshold evaluation to task metrics endpoint:
    - `/api/tasks/metrics` now accepts `failure_rate_threshold`, `cancellation_rate_threshold`, `min_terminal_samples`
    - response now includes derived `rates` (`completion_rate`, `failure_rate`, `cancellation_rate`) and `alerts` decision block (`evaluated`, `triggered`, `reasons`, `thresholds`, `terminal_total`)
    - regression test extended to validate both non-evaluated default window and evaluated+triggered threshold scenario
13. Added Prometheus scrape export for task metrics:
    - new endpoint `GET /api/tasks/metrics/prometheus` exposes status/event/terminal/rate/alert gauges in Prometheus text exposition format
    - query params mirror JSON metrics endpoint (`window_seconds`, `failure_rate_threshold`, `cancellation_rate_threshold`, `min_terminal_samples`) for alert-rule parity
    - regression test extended in `tests/test_task_control_plane.py` to verify export content and triggered alert metric
14. Added cross-process idempotency regression coverage:
    - new test `test_idempotency_key_dedupes_pending_task_across_controller_restart` verifies pending-task dedupe survives controller restart when sharing persisted task DB
    - validates duplicate submit behavior is store-backed rather than controller-instance-local
15. Stabilized idempotency duplicate-submit regression isolation:
    - `test_duplicate_submit_with_same_idempotency_key_returns_same_task` now uses an isolated temporary DB file
    - avoids pagination/history-coupled flakiness from shared task history accumulation during repeated full-gate runs
16. Added in-repo monitoring wiring assets for external Prometheus integration:
    - added scrape template: `config/monitoring/prometheus/task_metrics_scrape.example.yml`
    - added alert rule template: `config/monitoring/prometheus/task_metrics_alerts.yml`
    - added parameterized rendering tool: `tools/render_task_metrics_monitoring.py`
    - added regression tests: `tests/test_task_metrics_monitoring_tool.py`
17. Expanded cross-process idempotency coverage for running/retry windows:
    - added `test_idempotency_key_dedupes_running_task_across_controller_restart`
    - added `test_idempotency_key_dedupes_retry_scheduled_task_across_controller_restart`
    - confirms duplicate submit stays deduped across controller restart when task is `running` or retry-scheduled `pending`
18. Added stale-running recovery on controller startup:
    - `TaskController.start()` now performs store-backed stale-running recovery before worker loop starts
    - `TaskStore.recover_stale_running_tasks(...)` reverts stale `running` rows to `pending`, clears stale execution timestamps, and keeps task records resumable
    - recovered tasks are re-enqueued with existing priority/schedule semantics and emit `task.recovered_stale_running`
    - stale threshold configurable via env `MYT_TASK_STALE_RUNNING_SECONDS` (default `300`)
    - regression test added: `tests/test_task_control_plane.py::test_stale_running_task_recovered_and_requeued_on_controller_start`
19. Completed plugin manifest input completeness audit groundwork:
    - added payload-reference guard tool: `tools/check_plugin_manifest_inputs.py`
    - integrated guard into one-shot migration gates (`tools/run_migration_gates.sh`)
    - added regression tests: `tests/test_plugin_manifest_input_guard.py`
    - aligned plugin manifest input coverage for script payload references (`blogger_scrape`, `follow_interaction`, `home_interaction`, `quote_interaction`, `dm_reply`, `x_mobile_login`)
20. Enforced strict unknown-parameter rejection for plugin runtime payloads:
    - `engine/runner.py::_validate_plugin_payload` now rejects undeclared payload keys (except reserved `task`) with `code=invalid_params`
    - preserves existing dispatch error envelope (`status=failed_config_error`, `checkpoint=dispatch`)
    - added regression tests in `tests/test_runner_plugin_dispatch.py` for unknown-key rejection and `task` allowlist behavior
21. Added rollout toggle for strict plugin unknown-parameter validation:
    - new env `MYT_STRICT_PLUGIN_UNKNOWN_INPUTS` controls unknown-key rejection (`1` default, accepts `0/false/no/off` to disable)
    - keeps strict mode as default while enabling environment-based phased rollout
    - added regression test for disabled-mode compatibility in `tests/test_runner_plugin_dispatch.py`
22. Added runtime policy visibility and caller contract doc for rollout operations:
    - `/health` now exposes `task_policy.strict_plugin_unknown_inputs` and `task_policy.stale_running_seconds`
    - added health regression coverage in `tests/test_health_smoke.py` for env-driven policy values and stale-threshold fallback/clamping
    - added external contract doc: `docs/plugin_input_contract.md` (validation rules, env baseline, rollout strategy)
23. Expanded monitoring delivery-chain assets for Alertmanager handoff:
    - added template: `config/monitoring/alertmanager/task_metrics_route.example.yml`
    - extended `tools/render_task_metrics_monitoring.py` to render `task_metrics_alertmanager.yml`
    - extended regression tests: `tests/test_task_metrics_monitoring_tool.py`
24. Added stale-running recovery observability alert rule:
    - `config/monitoring/prometheus/task_metrics_alerts.yml` now includes `NewTaskStaleRunningRecovered`
    - rendering tool emits the same rule for deployment parity
25. Fixed bootstrap/test-context instability and DB test flakiness:
    - added `sitecustomize.py` to ensure parent import path for `*` package bootstrap in root-context execution
    - hardened `tools/check_plugin_manifest_inputs.py` direct-script execution path bootstrap
    - configured pytest `testpaths = tests` in `pyproject.toml` to avoid unintended `tmp/tests` collection
    - added `httpx` to `requirements.txt` as explicit dependency declaration
    - switched task-control DB tests to per-test `tmp_path` SQLite files to prevent shared `config/data` contention and intermittent schema/I/O failures
26. Re-audited documentation against current implementation and corrected capability descriptions:
    - aligned `README.md`, `docs/WEB_GUI_EMBED.md`, `docs/project_progress.md`, `docs/atomic_features.md`
    - clarified public account-pool/data APIs and task metrics/catalog endpoints
    - clarified that `web/js/features/tasks.js` exists but `web/index.html` does not yet expose an independent task page
    - aligned desktop-embed examples with the current `127.0.0.1:8001` baseline
27. Tightened weakly anchored public claims for the doc/code alignment task:
- narrowed `x_mobile_login` wording so docs no longer imply `_target` directly provides `package`
    - kept `/web` at static-entry smoke scope only
    - retained `/ws/logs` in user-facing docs because `tests/test_websocket_logs_route.py` now exercises ping plus filtered broadcast delivery

## 4) Open Items (Next work queue)

- [x] Independent re-audit on latest F1/F2/F4 evidence for external sign-off - PASS (2026-03-05, session `ses_3434d6326ffehaYo5gU4vpd7Gj`)
- [x] UIStateService unified rollout implementation and final validation - COMPLETE
- [x] 2026-03-09 docs-sync batch complete - surfaces aligned and evidence chain closed (`.sisyphus/evidence/20260309-docs-progress-sync-summary.md`, `.sisyphus/evidence/20260309-docs-progress-sync-commands.md`, `.sisyphus/evidence/20260309-docs-progress-sync-validation.md`)
- [ ] Keep workflow-level conservative recovery extraction deferred until the same bounded ordered chain repeats across multiple workflows
- [ ] External monitoring deployment: apply `docs/monitoring_rollout.md` and `config/monitoring/rendered/single-node-example/` in a real Prometheus/Alertmanager environment
- [ ] Runtime rollout execution: align `MYT_STRICT_PLUGIN_UNKNOWN_INPUTS` and `MYT_TASK_STALE_RUNNING_SECONDS` with actual deployment manifests and verify the live `/health` policy snapshot
- [ ] Commit/PR packaging for the now-completed docs-sync batch and prior rollout work

## 5) How to Continue in a New Conversation

Start prompt template:

```text
请先阅读 docs/HANDOFF.md、docs/project_progress.md、docs/current_main_status.md、docs/monitoring_rollout.md 和 docs/stale_running_recovery_tuning.md；
先基于已完成的 docs-sync 证据链（`20260309-docs-progress-sync-summary.md`、`20260309-docs-progress-sync-commands.md`、`20260309-docs-progress-sync-validation.md`）确认文档状态，再安排提交/PR 打包；
workflow-level conservative recovery 继续按 DEFERRED 处理，不要改写成已完成；
每完成一个子项即更新 docs/project_progress.md，并执行所需门禁与 `/health` 验证。
```

## 6) Alignment runbook

### 6.1 Use the claim inventory first

- Treat `config/doc_claims.yaml` as the bounded inventory for canonical capability, contract, workflow, validation, deferred, and watchpoint claims.
- Before editing canonical docs, check whether the wording belongs to an existing claim, a deferred item, or a next-step watchpoint.
- If the claim inventory already bounds the wording, clean up the prose to match it. Do not restate validator rules in full here.
- If a new long-lived canonical claim is needed, add or update the inventory and keep the allowed surfaces aligned with the ownership list above.

### 6.2 Run the doc validators

- Docs-only alignment work is docs-only, no runtime commands needed.
- From repo root, use the deterministic guards that CI also uses:

```bash
python tools/check_doc_claims.py
python tools/check_evidence_chain.py
```

- `tools/check_doc_claims.py` checks the bounded claim inventory, anchors, and canonical surface usage.
- `tools/check_evidence_chain.py` checks evidence naming, required triplets, and the exact docs-only wording allowance.
- Only move to broader runtime commands when the change introduces or depends on new executable behavior.

### 6.3 Decide between wording cleanup and new tests

- Choose wording cleanup when docs are broader than what current code, tests, or evidence prove. Narrow the claim to the supported behavior.
- Choose new tests or a new executable anchor when you want to keep or add a stronger user-facing claim that is not yet backed by code-level or route-level verification.
- If the strongest safe statement is still narrower than the old wording, prefer the narrower wording. Don't add speculative tests just to preserve marketing language.
- If a route, workflow, or contract stays documented as supported, keep at least one concrete code, test, or evidence anchor behind that claim.

### 6.4 When evidence chains are required

- Any meaningful alignment change needs an evidence chain when the diff alone is not enough for the next reviewer to reconstruct the claim, validation path, and conclusion.
- New alignment-topic evidence under `.sisyphus/evidence/` should use one shared `YYYYMMDD-<topic>` prefix with `summary`, `commands`, and `validation` files.
- For docs-only alignment waves, the commands record may say exactly `docs-only, no runtime commands needed`.
- Historical `task-*` evidence stays grandfathered. Do not rename old files just to match the newer pattern.

## 7) Required Validation Commands

Run from repository root:

```bash
./.venv/bin/python tools/update_project_progress.py
./.venv/bin/python tools/check_doc_claims.py
./.venv/bin/python tools/check_evidence_chain.py
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

## 8) Evidence and Review Handoff Workflow

### 8.1 When Evidence Is Required

- 凡是“有意义变更”都要留证据，最少覆盖：改了什么、怎么验证、产物放在哪里。
- 如果变更无法只靠 diff 说清楚，评审与交接必须能从本文和 `.sisyphus/evidence/` 直接追到验证过程。
- docs-only 变更可以只留文档证据，不必为了补证据额外跑会产生工作区噪音的运行命令。

### 8.2 Minimum Evidence by Change Type

- 代码变更：至少包含目标范围说明、执行过的命令、命令结果摘要、相关测试或门禁结论。
- 文档或配置变更：至少包含受影响文件、需要同步的约束或基线、人工校对结论；如果没有执行命令，要明确写 `docs-only, no runtime commands needed`。
- 发布、回滚或运维变更：至少包含环境范围、渲染或部署命令、生成的配置产物、上线后检查点。

### 8.3 Storage and Naming Rules

- 所有交接证据统一放在 `.sisyphus/evidence/`。
- 文件名统一用 `YYYYMMDD-<topic>-<kind>.<ext>`，其中：
  - `topic` 用短横线小写短语，直接对应本次改动主题。
  - `kind` 只用能说明用途的固定词，例如 `summary`、`commands`、`validation`、`handoff`、`rendered-config`。
  - `ext` 按内容选最简单格式，优先 `md`、`txt`、`json`、`log`。
- 一个完整证据链至少要能让评审看到 3 类东西：变更说明、命令或人工检查记录、最终交接结论。
- 如果同一主题有多份证据，保持同一个日期与 `topic` 前缀，按 `kind` 区分，不要发散命名。

### 8.4 Handoff Update Rules

- `docs/HANDOFF.md` 是交接与证据流程的单一事实来源。
- 每次完成有意义变更后，在本文 `Current Snapshot` 写结果，在 `What Was Recently Done` 记录事实，在 `Open Items` 更新后续动作。
- 交接说明必须点名本次证据链的文件路径，至少引用一个 summary 文件和一个 validation 或 commands 文件。
- 如果证据缺项，交接说明里要直接写缺什么、为什么缺、由谁在下一步补齐。

### 8.5 Reproducible Review Path

评审或发布接力时，按这个顺序检查：

1. 先读 `docs/HANDOFF.md` 的 `Current Snapshot`、`What Was Recently Done`、`Open Items`。
2. 记下对应主题名，然后到 `.sisyphus/evidence/` 查找同一 `YYYYMMDD-<topic>-*` 前缀的证据文件。
3. 先看 `summary`，再看 `commands` 或 `validation`，最后看 `handoff`，确认变更、验证、结论能串成闭环。
4. 如果交接提到代码门禁，就按本文 `Required Validation Commands` 复跑；如果交接写明 `docs-only, no runtime commands needed`，则只做文档比对与路径核对。

### 8.6 Example Evidence Chain

下面是一个完整但精简的例子，展示从变更到交接的最小闭环：

- 变更主题：标准化 handoff 证据流程
- 证据文件：
  - `.sisyphus/evidence/20260308-handoff-evidence-summary.md`
  - `.sisyphus/evidence/20260308-handoff-evidence-commands.txt`
  - `.sisyphus/evidence/20260308-handoff-evidence-handoff.md`
- `20260308-handoff-evidence-summary.md` 写明：修改了 `docs/HANDOFF.md`，新增证据命名规则、最低证据要求、评审复现路径。
- `20260308-handoff-evidence-commands.txt` 写明：`docs-only, no runtime commands needed`，并记录人工检查项，例如“核对 `.sisyphus/evidence/` 命名规则与 `docs/project_progress.md` 的待办是否一致”。
- `20260308-handoff-evidence-handoff.md` 写明：评审先读 `docs/HANDOFF.md`，再按同前缀查看 `summary` 与 `commands`，确认这是 docs-only 改动，无需额外运行服务门禁。

## 9) Risks / Notes

- Runtime DB file `config/data/tasks.db` is environment artifact; do not include in commits.
- Keep standalone constraints: no `tasks.*` and no `app.*` imports.
