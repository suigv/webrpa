# Stale Running Recovery Tuning

## Scope

This guide covers the repo-backed tuning and verification path for `MYT_TASK_STALE_RUNNING_SECONDS`.
It ties the setting to three existing surfaces in this repo:

- `GET /health`
- the recovery event `task.recovered_stale_running`
- the Prometheus alert rule `NewTaskStaleRunningRecovered`

This repo does not define named production environments or external SLO targets for this setting.
The repo-backed baselines below are therefore scenario-based, not environment-name-based.

## Current Behavior

`api/server.py:86` and `core/task_control.py:707` use the same parsing rule:

- default value: `300`
- invalid integer input: falls back to `300`
- negative input: clamped to `0`

`tests/test_health_smoke.py:18` verifies the invalid-input fallback.
`tests/test_health_smoke.py:31` verifies negative clamping.

On controller startup, `TaskController.start()` calls stale-running recovery before the worker loop starts, `core/task_control.py:52` and `core/task_control.py:679`.
Recovered rows come from `TaskStore.recover_stale_running_tasks(...)`, which moves stale `running` tasks back to `pending`, clears stale execution timestamps, and keeps them resumable, `core/task_store.py:336`.

Each recovered task is re-enqueued and emits `task.recovered_stale_running` with `stale_after_seconds`, `core/task_control.py:692`.

## Repo-Backed Baselines

### Steady-State Baseline

Use `300` seconds as the normal baseline.

Why this is the repo-backed default:

- `api/server.py:87` defaults to `300`
- `core/task_control.py:709` defaults to `300`
- `docs/plugin_input_contract.md:58` documents `300` as the default
- `docs/HANDOFF.md:93` records `300` as the stale threshold baseline

Keep this default when:

- you want normal controller-restart recovery behavior
- you are not actively drilling stale-running recovery
- there is no repo-backed evidence that legitimate tasks are being recovered too early or too late

### Temporary Validation Or Drill Baseline

Use `0` seconds only as a temporary validation or restart-drill baseline.

Why this is repo-backed:

- `tests/test_task_control_plane.py:402` sets `MYT_TASK_STALE_RUNNING_SECONDS="0"`
- that test proves immediate stale classification on controller restart and verifies `task.recovered_stale_running` is emitted, `tests/test_task_control_plane.py:453`
- negative values are clamped to `0`, so `0` is also the lowest effective value exposed by `/health`, `tests/test_health_smoke.py:31`

Use `0` when:

- you need a fast recovery drill in a controlled environment
- you want to prove the recovery and alerting path end to end

Reset to `300` after the drill unless you have environment-specific evidence outside this repo that justifies another value.

## Operator Tuning Rule

Use this plain rule:

- keep `300` by default
- lower the value temporarily when you need to validate the restart recovery path quickly
- raise the value only if legitimate long-running tasks are being recovered too aggressively after controller restart
- reset to `300` after temporary validation, rollback, or drills

This repo does not include workload-duration baselines, production latency targets, or per-environment thresholds beyond the default and the drill value above.
If you pick a non-default steady-state value, treat that as an operator-managed deployment decision and confirm it through the verification steps below.

## What Changes When The Value Changes

### `/health`

`GET /health` reports the effective parsed value at `task_policy.stale_running_seconds`, `api/server.py:72`.
This is the first place to confirm the live process is using the intended threshold, especially if deployment wrappers or service managers set environment variables before startup.

### Recovery Events

When a controller restart finds stale `running` rows older than the computed cutoff, the controller:

1. recovers them in the store
2. re-enqueues them with their existing scheduling metadata
3. emits `task.recovered_stale_running`

The event payload includes `stale_after_seconds`, so the recovery record itself shows which threshold was applied, `core/task_control.py:698`.

### Monitoring Path

The repo alert rule lives in `config/monitoring/prometheus/task_metrics_alerts.yml:31`.
It fires `NewTaskStaleRunningRecovered` when exported task metrics contain `new_task_event_type_count{event_type="task.recovered_stale_running"} > 0`.

`docs/monitoring_rollout.md:121` lists this rule in the rollout baseline, and `docs/monitoring_rollout.md:128` states that the rule is informational.

## Verification Procedure

This procedure stays inside repo-backed facts and uses the existing monitoring rollout chain from `docs/monitoring_rollout.md`.

### A. Confirm the live threshold

Start the service with the intended value, then check:

```bash
curl http://127.0.0.1:8001/health
```

Expected evidence:

- `task_policy.stale_running_seconds` is `300` for the steady-state baseline
- `task_policy.stale_running_seconds` is `0` for a temporary validation drill
- invalid input does not survive, it falls back to `300`
- negative input does not survive, it shows as `0`

### B. Prove recovery event emission

For a reproducible repo-backed drill, use the focused regression evidence in `tests/test_task_control_plane.py:402`.
That test demonstrates the minimal validation setup:

- set `MYT_TASK_STALE_RUNNING_SECONDS=0`
- create a task
- mark it `running`
- restart the controller
- confirm the task completes after recovery
- confirm an emitted `task.recovered_stale_running` event exists

If you validate this manually in an operator environment, the evidence to keep is:

- the task record no longer stuck in `running`
- the recovered task re-entered execution
- the task event stream or stored events include `task.recovered_stale_running`
- the recovery event payload shows the threshold you intended to test

### C. Prove the monitoring artifact path

Use the rollout baseline from `docs/monitoring_rollout.md` rather than designing a new monitoring chain.

Evidence to check after a recovery drill:

- Prometheus loads `config/monitoring/prometheus/task_metrics_alerts.yml`
- exported task metrics show `new_task_event_type_count{event_type="task.recovered_stale_running"}`
- the informational alert `NewTaskStaleRunningRecovered` appears in Prometheus and then in Alertmanager according to the external routing policy

The repo-backed alert definition is in `config/monitoring/prometheus/task_metrics_alerts.yml:31`.
The repo-backed rollout chain is documented in `docs/monitoring_rollout.md:117` and `docs/monitoring_rollout.md:142`.

## Recommended Evidence After Tuning

After any change to `MYT_TASK_STALE_RUNNING_SECONDS`, check these three artifacts together:

- `/health` shows the effective live threshold
- recovered tasks emit `task.recovered_stale_running`
- external monitoring surfaces `NewTaskStaleRunningRecovered` when the recovery event appears in exported metrics

If the purpose was only a validation drill, restore `MYT_TASK_STALE_RUNNING_SECONDS=300` and re-check `/health` so the process-level baseline is back to the repo default.
