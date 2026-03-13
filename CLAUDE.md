# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Install dependencies
```bash
uv pip install -r requirements.txt
# or
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
```

### Start service
```bash
MYT_ENABLE_RPC=0 uv run uvicorn api.server:app --host 127.0.0.1 --port 8001
```

### Run tests
```bash
uv run python -m pytest tests -q
# single test file
uv run python -m pytest tests/test_foo.py -q
```

### Lint / format
```bash
uv run ruff check api/ core/ engine/ ai_services/
uv run ruff check --fix .
uv run ruff format .
```

### Required validation before finishing any change
```bash
uv run python tools/check_no_legacy_imports.py
uv run python -m pytest tests -q
MYT_ENABLE_RPC=0 uv run uvicorn api.server:app --host 127.0.0.1 --port 8001
curl http://127.0.0.1:8001/health
```

### Useful debug commands
```bash
curl http://localhost:8001/api/tasks/metrics | jq
curl -N http://localhost:8001/api/tasks/{task_id}/events
uv run python -c "from engine.action_registry import list_actions; print('\n'.join(list_actions()))"
```

## Architecture

Three-layer model:
1. **Control Plane** — FastAPI REST, task persistence, state machine, metrics (`api/`, `core/`)
2. **Execution Engine** — YAML plugin interpreter, deterministic + autonomous (AI) modes (`engine/`)
3. **Driver/Hardware Layer** — three-port protocol per cloud machine; browser via DrissionPage/CDP (`hardware_adapters/`)

### Port mapping per cloud machine
| Port formula | Role | Client |
|---|---|---|
| `30000 + (cloud-1)*100 + 1` | Android HTTP API | `AndroidApiClient` |
| `30000 + (cloud-1)*100 + 2` | RPA control (touch/screenshot/UI nodes) | `MytRpc` |
| `8000` (configurable) | Device SDK (container lifecycle) | `MytSdkClient` |

### Task system key classes
- `TaskController` (`core/task_control.py`) — orchestration entry
- `TaskExecutionService` (`core/task_execution.py`) — execution lifecycle
- `TaskAttemptFinalizer` (`core/task_finalizer.py`) — terminal/retry policy
- `TaskMetricsService` (`core/task_metrics.py`) — metrics aggregation/export
- `TaskStore` / `TaskEventStore` / `InMemoryTaskQueue` — persistence/event/queue boundaries

### Engine key classes
- `engine/parser.py` — normalizes script payload
- `engine/runner.py` — owns execution orchestration (dual-track: named plugin vs anonymous script)
- `engine/interpreter.py` — step-by-step YAML executor; supports label/goto/if/wait_until/stop; MAX_TRANSITIONS=500, WAIT_UNTIL hard limit 120s, 2s cancellation pulse
- `engine/action_registry.py` — action registration via `register_defaults()`
- `engine/actions/*` — atomic action implementations, capability-focused modules

### Config and paths
- `core/config_loader.py` — primary config entry point
- `core/paths.py` — all directory resolutions (use this, never hardcode paths)
- `core/base_store.py` — SQLite base class (WAL mode)
- Main DB: `config/data/tasks.db`
- Plugin dir: `plugins/`
- UI config: `config/apps/*.yaml` (default: `config/apps/default.yaml`, override via `MYT_DEFAULT_APP`)
- UI bindings: `config/bindings/*.json` (loaded by `app_package`)
- AI traces: `config/data/traces/`

### Active plugins
- `plugins/hezi_sdk_probe/` — reference plugin; SDK probe workflow

### Plugin workflow conventions
- Template interpolation: `${payload.key}`, `${vars.key}`, `${payload.url:-default}` — do NOT use Jinja2 `{{ }}`
- Reference plugin: `plugins/hezi_sdk_probe/`
- When a fallback sequence repeats 3+ times, add a composite action instead of copying YAML
- Composite actions: `core.load_ui_selectors`, `ui.selector_click_with_fallback`

### Adding new things
- **New route**: add under `api/routes/`, register in `api/server.py`
- **New action**: add in `engine/actions/`, register via `register_defaults()` in `engine/action_registry.py`; must return `ActionResult`
- **New business workflow**: go to `plugins/`, not API routes

### AI / VLM action dependencies
`engine/actions/ai_actions.py` provides `llm_evaluate`, `vlm_evaluate`, `locate_point`. These require:
- LLM config via `core/config_loader.py` (`ConfigLoader.load().llm`): `provider`, `model`, `base_url`, `api_key`
- Defaults: provider=`openai`, model=`gpt-5.4`; override via app config or env vars surfaced through `ConfigLoader`
- VLM calls use the same LLM client with `image` modality; screenshot is taken by the action itself via the hardware adapter
- No standalone env vars are read directly — all config flows through `ConfigLoader`

## Guardrails

- No imports from `tasks.*` or `app.*` (legacy namespaces)
- `MYT_ENABLE_RPC=0` startup path must always work
- All data paths must stay inside `config/data/`
- Keep routes thin — business logic belongs in `core/` or `engine/`
- Do not block the event loop in action handlers; use `async/await`
- Do not mutate `config/data/tasks.db` directly; use store/control APIs
- Do not put account/business logic inline in orchestration hot paths; use a dedicated service
- If plugin contract changes, keep `docs/PLUGIN_CONTRACT.md` in sync
