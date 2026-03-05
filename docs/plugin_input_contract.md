# Plugin Input Contract & Rollout Policy

## Scope

This document defines runtime payload validation rules for YAML plugins and provides a rollout baseline for environments.

## Runtime Contract

Validation happens in `engine/runner.py` before interpreter execution.

1. `required` inputs must be provided unless manifest default exists.
2. Input types must match manifest declarations (`string`/`integer`/`number`/`boolean`).
3. Unknown payload keys are rejected when strict mode is enabled.
   - Reserved key `task` is always allowed.
4. Validation failures return dispatch envelope:
   - `status=failed_config_error`
   - `checkpoint=dispatch`
   - `code` in (`missing_required_param`, `invalid_params`)

## Environment Policy

### `MYT_STRICT_PLUGIN_UNKNOWN_INPUTS`

- Default: `1` (strict enabled)
- Disable values: `0`, `false`, `no`, `off`
- Any other value keeps strict mode enabled

Recommended baseline:

- **prod/staging**: strict enabled (`1`)
- **dev/sandbox**: may temporarily disable (`0`) for compatibility debugging only

### `MYT_TASK_STALE_RUNNING_SECONDS`

- Default: `300`
- Invalid numeric values fallback to `300`
- Negative values are clamped to `0`

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

## Rollout Strategy

1. Keep strict mode enabled by default in all environments.
2. If caller compatibility issues appear, temporarily disable strict unknown-key rejection only in affected non-prod environment.
3. Fix caller payloads to match plugin manifests.
4. Re-enable strict mode and keep production strict at all times.
