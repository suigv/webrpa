# Plugin Input Contract & Rollout Policy

## Scope

This document defines runtime payload validation rules for YAML plugins and the rollout baseline that operators should keep aligned across the current caller and deployment surfaces in this repo.

## Runtime Contract

Validation happens in `engine/runner.py` before interpreter execution.

1. `required` inputs must be provided unless manifest default exists.
2. Input types must match manifest declarations (`string`/`integer`/`number`/`boolean`).
3. Unknown payload keys are rejected when strict mode is enabled.
   - Reserved key `task` is always allowed.
   - Internal keys prefixed with `_` are ignored by the unknown-input check.
4. Validation failures return dispatch envelope:
   - `status=failed_config_error`
   - `checkpoint=dispatch`
   - `code` in (`missing_required_param`, `invalid_params`)

## Caller Surfaces To Align

The current repo exposes three real caller surfaces that operators should treat as contract-sensitive:

1. `POST /api/runtime/execute`
   - `api/server.py` passes the request body directly to `Runner().run(payload)`.
   - This is the debug/internal-only direct-run surface; it does **not** create managed task rows, retries, cancellation flow, SSE task events, or task metrics artifacts.
   - Any undeclared plugin input sent here is rejected when strict mode is on.
2. `POST /api/tasks`
   - `api/routes/task_routes.py` builds `script_payload` from `task` plus `payload`, then submits that payload for runner dispatch.
   - This is the managed task lifecycle surface for queued execution, retries, cancellation, events, and metrics.
   - Unknown keys inside `payload` reach the same plugin validation path.
3. `GET /api/tasks/catalog`
   - `api/routes/task_routes.py` builds `required`, `defaults`, and `example_payload` from plugin manifests.
   - Catalog refresh uses the same shared plugin loader as runtime dispatch, so refreshed catalog output and current runner/controller plugin visibility stay aligned.
   - Callers should refresh from this catalog when payload mismatches show up during rollout.

Current repo docs that already show plugin payload examples and should stay aligned with manifest inputs:

- `README.md`
- `docs/atomic_features.md`
- `docs/reference/real_device_smoke_payloads.md`

## Deployment Baseline

### `MYT_STRICT_PLUGIN_UNKNOWN_INPUTS`

- Default: `1` (strict enabled)
- Disable values: `0`, `false`, `no`, `off`
- Any other value keeps strict mode enabled
- `engine/runner.py` and `GET /health` read the same flag interpretation

Recommended baseline:

- Keep `MYT_STRICT_PLUGIN_UNKNOWN_INPUTS=1` as the baseline for every environment unless you are actively rolling back a caller compatibility issue.
- Confirm the effective value from the running process with `GET /health`, not only from deployment config.
- If startup docs or deployment wrappers set environment variables, make sure they do not override this flag unexpectedly before `uvicorn api.server:app` starts.

### `MYT_TASK_STALE_RUNNING_SECONDS`

- Default: `300`
- Invalid numeric values fallback to `300`
- Negative values are clamped to `0`

## Compatibility And Rollback

- If strict mode breaks an existing caller, the compatibility path is to set `MYT_STRICT_PLUGIN_UNKNOWN_INPUTS=0` for the affected environment only.
- Accepted rollback values are `0`, `false`, `no`, or `off`.
- After rollback, confirm `GET /health` reports `task_policy.strict_plugin_unknown_inputs=false`.
- Treat rollback as temporary. Update the caller payload to match the plugin manifest or the `GET /api/tasks/catalog` example payload, then restore `MYT_STRICT_PLUGIN_UNKNOWN_INPUTS=1`.

## Operational Verification

Use `GET /health` to verify runtime policy at process level:

```json
{
  "status": "ok",
  "runtime": "skeleton",
  "rpc_enabled": false,
  "task_policy": {
    "strict_plugin_unknown_inputs": true,
    "stale_running_seconds": 300
  }
}
```

Focused regression evidence already exists in the repo:

- `tests/test_runner_plugin_dispatch.py`
  - strict mode rejects unknown plugin inputs
  - `task` stays allowlisted
  - strict rejection can be disabled with `MYT_STRICT_PLUGIN_UNKNOWN_INPUTS=0`
- `tests/test_health_smoke.py`
  - `/health` exposes the effective `strict_plugin_unknown_inputs` value from env

## Rollout Verification Checklist

1. Check the running baseline.

   ```bash
   curl http://127.0.0.1:8001/health
   ```

   Confirm `task_policy.strict_plugin_unknown_inputs` matches the intended rollout state.

2. Check the caller payload shape before release.

   - For sync callers, compare request bodies sent to `POST /api/runtime/execute` with the plugin manifest or `GET /api/tasks/catalog` output.
   - For async callers, compare `POST /api/tasks` `payload` fields with the same manifest-derived contract.
   - Re-check sample payload docs in `docs/reference/real_device_smoke_payloads.md` if operators use those examples during rollout.

3. Check repo regression coverage when contract mismatches are suspected.

   ```bash
   ./.venv/bin/python -m pytest tests/test_runner_plugin_dispatch.py tests/test_health_smoke.py -q
   ```

   Expect coverage for both unknown-input rejection and `/health` policy visibility.

## Rollout Strategy

1. Keep strict mode enabled as the default baseline.
2. Align all known caller surfaces, `POST /api/runtime/execute`, `POST /api/tasks`, and any operator runbooks using `docs/reference/real_device_smoke_payloads.md`, to manifest-declared inputs only.
3. Use `GET /health` to confirm the live process is actually running with the intended strictness.
4. If compatibility issues appear, use the temporary rollback path in the affected environment, then fix caller payloads and restore strict mode.
