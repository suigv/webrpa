# Plugin Contract (`new/plugins/`)

## Goal
Define a stable contract for task plugins so runtime can execute business flows without coupling to API or legacy task code.

## Version
- Current contract: `plugin_contract_version = "1.0"`
- Breaking changes require version bump.

## File Layout
Recommended plugin structure:

- `new/plugins/<plugin_name>/manifest.json`
- `new/plugins/<plugin_name>/script.json` (optional, if using declarative script)
- `new/plugins/<plugin_name>/handler.py` (optional, if using code handler)

At least one of `script.json` or `handler.py` must exist.

## Manifest Schema
`manifest.json` fields:

- `name` (string, required): unique plugin name
- `version` (string, required): plugin version
- `plugin_contract_version` (string, required): must match runtime-supported contract
- `entry_type` (string, required): `"script" | "handler"`
- `entry` (string, required): path to `script.json` or `handler.py:callable`
- `description` (string, optional)
- `capabilities` (array[string], optional): e.g. `"ui"`, `"ai"`, `"rpc"`, `"data"`
  - browser workflows should include `"browser"`
- `timeout_seconds` (int, optional, default 60)
- `retry` (object, optional)
  - `max_attempts` (int, default 1)
  - `backoff_ms` (int, default 0)
- `on_fail` (string, optional, default `"abort"`): `"abort" | "skip" | "retry"`

Example:

```json
{
  "name": "account_warmup_v1",
  "version": "0.1.0",
  "plugin_contract_version": "1.0",
  "entry_type": "script",
  "entry": "script.json",
  "description": "Warmup flow for new accounts",
  "capabilities": ["ui", "data"],
  "timeout_seconds": 120,
  "retry": {
    "max_attempts": 2,
    "backoff_ms": 1000
  },
  "on_fail": "abort"
}
```

## Script Schema (`entry_type = script`)
Top-level fields:
- `task` (string, required)
- `steps` (array, required)

Step fields:
- `id` (string, required)
- `action` (string, required): maps to `new/engine/actions/*`
- `params` (object, optional)
- `timeout_ms` (int, optional)
- `retry` (object, optional)
  - `max_attempts` (int)
  - `backoff_ms` (int)
- `on_fail` (string, optional): `"abort" | "skip" | "retry" | "handoff"`
- `expect` (object, optional): expected output shape/conditions

Example:

```json
{
  "task": "warmup_login",
  "steps": [
    {
      "id": "open_app",
      "action": "click",
      "params": {"target": "app_icon"},
      "timeout_ms": 5000,
      "on_fail": "abort"
    },
    {
      "id": "input_username",
      "action": "input_text",
      "params": {"target": "username", "text": "${vars.username}"},
      "retry": {"max_attempts": 2, "backoff_ms": 500},
      "on_fail": "retry"
    }
  ]
}
```

Browser action example:

```json
{
  "id": "open_landing_page",
  "action": "browser_open",
  "params": {"url": "https://example.com", "headless": true},
  "timeout_ms": 20000,
  "on_fail": "abort"
}
```

## Handler Contract (`entry_type = handler`)
Entry format: `handler.py:run`

Callable signature:

```python
def run(context: dict[str, object]) -> dict[str, object]:
    ...
```

`context` includes:
- `task_id` (str)
- `plugin_name` (str)
- `input` (dict)
- `devices` (list[int])
- `ai_type` (str)
- `config` (dict)
- `logger` (callable)

Return payload:
- `ok` (bool, required)
- `status` (str, required): `"completed" | "failed" | "partial"`
- `result` (object, optional)
- `error` (str, optional)
- `metrics` (object, optional)

## Runtime Execution Rules
1. Runtime validates `manifest.json` first.
2. Runtime checks contract version compatibility.
3. Runtime dispatches by `entry_type`:
   - `script` -> `new/engine/parser.py` + `new/engine/runner.py`
   - `handler` -> import callable and execute with context
4. Runtime enforces timeout/retry/on_fail.
5. Runtime returns structured result and updates task status.

## Security and Isolation Rules
- Plugin must not import old `tasks` or `app.*` modules.
- Plugin must not perform destructive file operations outside `new/`.
- Secrets must be read from env/config, never hardcoded.

## Validation Checklist
For each new plugin:
- Manifest schema valid.
- Entry resolvable.
- Dry-run passes.
- Error path tested (`on_fail` behavior).
- Output payload includes required fields.

## Future Extension Points
- Add `requires` for dependency declarations.
- Add `permissions` for capability gating.
- Add `schema_ref` for strict JSON Schema validation.
