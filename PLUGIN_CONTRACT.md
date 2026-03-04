# Plugin Contract v2 (`new/plugins/`)

## Goal
Define a stable contract for **YAML-only declarative plugins** so the runtime can execute business workflows without coupling to API routes or legacy task code.

## Version
- Current contract: `v2` (YAML-only)
- Previous: `v1` (JSON + handler.py) — **deprecated**

## File Layout

Each plugin lives in its own directory under `new/plugins/`:

```
new/plugins/<plugin_name>/
├── manifest.yaml    # Plugin metadata and input schema
└── script.yaml      # Declarative workflow steps
```

Both files are required. There are no Python handler entry points — all logic is expressed declaratively via the 5 step primitives.

## Manifest Schema (`manifest.yaml`)

| Field | Type | Required | Description |
|---|---|---|---|
| `api_version` | `"v1"` | yes | Schema version (always `v1`) |
| `kind` | `"plugin"` | yes | Resource kind (always `plugin`) |
| `name` | string | yes | Unique plugin identifier (matches directory name) |
| `version` | string | yes | Plugin version (semver) |
| `display_name` | string | yes | Human-readable name |
| `description` | string | no | Plugin description |
| `entry_script` | string | no | Script filename (default: `script.yaml`) |
| `inputs` | list[PluginInput] | no | Declared input parameters |

### PluginInput Schema

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Input parameter name |
| `type` | `"string" \| "integer" \| "number" \| "boolean"` | yes | Input type |
| `required` | bool | no | Whether input is required (default: `true`) |
| `default` | any | no | Default value if not provided |

### Example

```yaml
api_version: v1
kind: plugin
name: x_auto_login
version: "1.0.0"
display_name: "X (Twitter) Auto Login"
description: "Automates browser-based login to X.com"
entry_script: script.yaml
inputs:
  - name: credentials_ref
    type: string
    required: true
  - name: headless
    type: boolean
    required: false
    default: true
```

## Workflow Script Schema (`script.yaml`)

| Field | Type | Required | Description |
|---|---|---|---|
| `version` | `"v1"` | yes | Schema version |
| `workflow` | string | yes | Workflow name (should match plugin name) |
| `vars` | dict | no | Script-level variables (support interpolation) |
| `steps` | list[Step] | yes | Ordered list of steps |

### Variable Interpolation

Templates use `${namespace.path}` syntax:
- `${payload.key}` — value from runtime payload
- `${vars.key}` — value from script vars or saved action results
- `${vars.creds.field}` — nested dot-path lookup
- `${payload.url:-https://default.com}` — default value after `:-`

### Step Primitives (5 kinds)

#### `action` — Execute a registered action

```yaml
- label: open_login
  kind: action
  action: browser.open
  params:
    url: "${vars.login_url}"
  save_as: open_result    # optional: save result to vars
  on_fail:
    strategy: abort       # abort | skip | retry | goto
```

#### `if` — Conditional branching

```yaml
- label: check_captcha
  kind: if
  when:
    any:                  # any | all
      - type: text_contains
        text: "captcha"
  then: captcha_detected  # label to jump to if true
  otherwise: continue     # optional: label if false
```

#### `wait_until` — Polling loop

```yaml
- label: wait_home
  kind: wait_until
  check:
    any:
      - type: url_contains
        text: "/home"
  interval_ms: 500
  timeout_ms: 25000       # hard limit: 120000ms
  on_timeout:
    strategy: goto
    goto: timeout_handler
```

#### `goto` — Unconditional jump

```yaml
- kind: goto
  target: wait_home
```

#### `stop` — Terminate workflow

```yaml
- label: success
  kind: stop
  status: success         # success | failed
  message: "login completed"
```

### Condition Types

| Type | Fields | Description |
|---|---|---|
| `text_contains` | `text` | Page HTML contains text (case-insensitive) |
| `url_contains` | `text` | Current URL contains text (case-insensitive) |
| `exists` | `selector` | DOM element exists matching selector |
| `var_equals` | `var`, `equals` | Variable equals expected value |
| `result_ok` | — | Last action result was ok |

### Failure Strategies (`on_fail`)

| Strategy | Fields | Behavior |
|---|---|---|
| `abort` | — | Stop workflow with error (default) |
| `skip` | — | Ignore failure, continue to next step |
| `retry` | `retries`, `delay_ms` | Retry N times with delay |
| `goto` | `goto` | Jump to label on failure |

## Built-in Actions

### Browser Actions
- `browser.open` — Open URL (`url`, `headless`)
- `browser.input` — Type text into element (`selectors[]`, `text`)
- `browser.click` — Click element (`selectors[]`)
- `browser.exists` — Check element exists (`selectors[]`)
- `browser.check_html` — Check page HTML for keywords (`contains[]`)
- `browser.wait_url` — Wait for URL fragment (`fragment`, `timeout_s`)
- `browser.close` — Close browser session

### Credential Actions
- `credentials.load` — Load credentials from file (`credentials_ref`, `save_as`)

## Runtime Execution

1. `PluginLoader.scan()` discovers `plugins/*/manifest.yaml`
2. `Runner.run()` matches task name → plugin manifest
3. `parse_script()` loads and validates `script.yaml` via Pydantic
4. `Interpreter.execute()` runs the workflow with PC-based loop
5. Browser session opens lazily on first browser action
6. Browser session closes in interpreter `finally` block
7. `max_transitions = 500` guards against goto loops
8. `wait_until` enforces `timeout_ms` with engine hard limit of 120s

## Security and Isolation Rules
- Plugins must not import old `tasks` or `app.*` modules
- Plugins must not contain Python code — YAML only
- Credentials must be loaded via `credentials.load` action from allowlisted paths
- No destructive file operations outside `new/`

## Validation Checklist
For each new plugin:
- [ ] `manifest.yaml` validates against `PluginManifest` model
- [ ] `script.yaml` validates against `WorkflowScript` model
- [ ] All referenced labels exist in the step list
- [ ] No duplicate labels
- [ ] All referenced actions are registered
- [ ] Error paths tested (`on_fail` behavior)
- [ ] `check_no_legacy_imports.py` passes
