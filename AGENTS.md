# AGENTS.md for `webrpa`

## Mission
Build and evolve `webrpa` as an independent project.

Hard goals:
- Keep `webrpa` copy-ready and runnable by itself.
- Do not reintroduce legacy task code from old repo.
- Evolve runtime via pluginized architecture.

## Scope Rules

### In Scope
- `api/**`
- `core/**`
- `models/**`
- `common/**`
- `engine/**`
- `hardware_adapters/**`
- `ai_services/**`
- `plugins/**`
- `tests/**`
- `tools/**`
- `config/**`

### Out of Scope
- Any direct dependency on old `tasks/*.py`
- Any import from old package namespace `app.*`
- Any hardcoded path to old repository root

## Guardrails (Must Pass)
1. No forbidden imports:
   - `from tasks ...` / `import tasks`
   - `from app....` / `import app....`
2. Baseline startup must work with RPC disabled:
   - `MYT_ENABLE_RPC=0`
3. Data path must stay inside:
   - `config/data`

## Required Validation
Run all before finishing any meaningful change:

```bash
./.venv/bin/python tools/check_no_legacy_imports.py
./.venv/bin/python -m pytest tests -q
MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

Health check:

```bash
curl http://127.0.0.1:8001/health
```

## Architecture Contracts

### API Layer
- `api/server.py` is the single app entrypoint.
- Keep routes thin; business logic belongs in core/engine.
- `/web` is the default operator console endpoint and should remain available.

### Runtime Layer
- `engine/parser.py` normalizes script payload.
- `engine/runner.py` owns execution orchestration.
- `engine/actions/*` contains atomic action functions.
- Keep action modules capability-focused; when one file starts mixing connection lifecycle, parameter policy, fallback strategy, and a mini-subsystem, split it before adding more features.
- Prefer shared helpers for RPC/session/bootstrap wiring; do not duplicate connection patterns across action modules.

### Orchestration Boundary
- `core/task_control.py` is orchestration glue, not a home for business policy.
- Keep execution lifecycle in dedicated services such as `core/task_execution.py`; keep terminal retry/failure policy in dedicated services such as `core/task_finalizer.py`; keep observability aggregation/export in dedicated services such as `core/task_metrics.py`.
- Business feedback or compensation rules must live behind a dedicated hook/service, not inline inside task failure/scheduling paths.
- Keep `core/task_store.py`, `core/task_queue.py`, and `core/task_events.py` as the persistence/queue/event boundaries; avoid moving those concerns back into routes or plugins.

### Plugin Workflow Boundary
- Plugins should express business workflows, not low-level transport or fallback boilerplate.
- When a workflow repeats the same fallback sequence three or more times, add a composite action instead of copying more YAML.
- Prefer shared composite actions (e.g., selector batch loading + fallback click chains) for repetitive selector wiring.
- Treat unusually long plugin scripts as an architecture smell that requires review, especially login/onboarding flows.

### Adapter Layer
- `hardware_adapters/myt_client.py` (`MytSdkClient`) — 8000 port, device-level SDK (container lifecycle, images, backup, SSH, VPC).
- `hardware_adapters/android_api_client.py` (`AndroidApiClient`) — 30001 port, cloud machine Android HTTP API.
- `hardware_adapters/mytRpc.py` (`MytRpc`) — 30002 port, RPA control (touch/key/screenshot/UI nodes).
- Native lib loading must be lazy and failure-safe.
- `hardware_adapters/browser_client.py` is optional browser capability based on vendored DrissionPage.
- Browser adapter must fail gracefully when DrissionPage or browser runtime is unavailable.

### Port Architecture
Each cloud machine has two ports; each device has one SDK port.
Ports are determined by `cloud_index` only — device IP provides isolation.

| Port | Formula | Role | Client |
|---|---|---|---|
| `api_port` | `30000 + (cloud-1)*100 + 1` | Cloud machine Android HTTP API (clipboard, proxy, screenshot, language, etc.) | `AndroidApiClient` |
| `rpa_port` | `30000 + (cloud-1)*100 + 2` | MytRpc control channel (touch/app/key/UI nodes) | `MytRpc` |
| `sdk_port` | `8000` (configurable) | Device-level SDK API — container lifecycle, images, backup, SSH, VPC | `MytSdkClient` |

Example (device IP `192.168.1.214`, 10 clouds):
```
cloud 1  → api 30001, rpa 30002
cloud 2  → api 30101, rpa 30102
cloud 10 → api 30901, rpa 30902
```
Different devices use the same port numbers but different IPs — `(ip, port)` is unique.

### Data and Config Layer
- `core/config_loader.py` controls runtime config access.
- `core/base_store.py` is the SQLite base class (WAL mode, unified transactions).
- Legacy TXT migration remains opt-in only.

## Pluginization Direction
- New business workflows go to `plugins/`.
- Avoid embedding business task logic inside API routes.
- Keep plugin interface stable and versioned once defined.
- Use plugins for workflow composition and state flow; move reusable low-level interaction patterns into actions or composite actions.
- Before expanding an existing large workflow, check whether the repeated pattern belongs in a new action instead.

## Commit and Change Hygiene
- Small, capability-based commits.
- Do not mix refactor + feature + formatting in one change.
- Keep tests updated with each behavior change.

## Definition of Done
A change is done only if:
- static gate passes,
- tests pass,
- app starts and `/health` returns 200,
- no legacy imports were introduced.

## Merged Reference (from CLAUDE.md)

This section keeps practical project guidance that used to live in `CLAUDE.md`.

### Project Overview
- Web/RPA automation platform: FastAPI + pluginized execution engine + browser automation.
- Key capabilities: multi-device/cloud topology mapping, task scheduling with retry/SSE, YAML workflow engine, Web console (`/web`) and log stream (`/ws/logs`).

### Tech Stack
- Runtime: Python 3.11+, FastAPI 0.115, uvicorn 0.32, Pydantic 2.9.
- Communication: WebSocket (`websockets` 13.1), SSE task events.
- Data: SQLite (`config/data/tasks.db`) + JSON configs.
- RPA/Parsing: DownloadKit, lxml, cssselect, browser automation stack.
- AI clients: `ai_services/llm_client.py`, `ai_services/vlm_client.py`.

### Common Commands (uv)
Install dependencies:
```bash
uv pip install -r requirements.txt
```

Start service:
```bash
uv run python api/server.py
uv run uvicorn api.server:app --host 0.0.0.0 --port 8001
```

Operational debugging:
```bash
curl http://localhost:8001/health | jq
curl http://localhost:8001/api/tasks/metrics | jq
curl -N http://localhost:8001/api/tasks/{task_id}/events
websocat ws://localhost:8001/ws/logs
```

Code quality:
```bash
uv run ruff check api/ core/ engine/ ai_services/ common/
uv run ruff check --fix .
uv run ruff format .
```

### Development Conventions (Additions)
- New API route:
  - Add route module under `api/routes/`.
  - Register route in `api/server.py`.
  - Reuse standard response models where possible.
- New engine action:
  - Add implementation in `engine/actions/`.
  - Register via `register_defaults()` in `engine/action_registry.py`.
  - Action handlers must return `ActionResult`.
  - Keep the action narrowly scoped; if the change needs selector frameworks, shared state policy, or complex connection management, extract helpers or submodules instead of growing a god-file.
- Task system key classes:
  - `TaskController` (`core/task_control.py`)
  - `TaskExecutionService` (`core/task_execution.py`)
  - `TaskAttemptFinalizer` (`core/task_finalizer.py`)
  - `TaskMetricsService` (`core/task_metrics.py`)
  - `InMemoryTaskQueue` / `RedisTaskQueue` (`core/task_queue.py`)
  - `TaskStore` (`core/task_store.py`)
  - `TaskEventStore` (`core/task_events.py`)
  - `Interpreter` (`engine/interpreter.py`)
- Humanized behavior config:
  - `models/humanized.HumanizedConfig` controls move/click/input rhythm and fallback strategy.
- Config and Paths:
  - Use `core/paths.py` for all directory resolutions.
  - `core/config_loader.py` is the primary entry point for device and system config.

### Additional Do-Not Rules
- Do not directly mutate `config/data/tasks.db`; use task store/control APIs.
- Do not block event loop in action handlers; keep `async/await` discipline.
- Do not hardcode secrets; use `credentials_loader` or environment variables.
- If plugin contract changes, keep implementation and docs synchronized.
- Do not place account/business remediation logic directly in orchestration hot paths when a hook/service boundary can own it.
- Do not solve repeated workflow boilerplate by copying more YAML when a composite action is the real abstraction.

### Plugin Notes
- Reference implementation path: `plugins/hezi_sdk_probe/`.
- Workflow supports template interpolation: `${payload.key}`, `${vars.key}`, and `${payload.url:-default_val}`. Do NOT use Jinja2 `{{ }}` syntax.

### Debug Tips
Task execution flow quick check:
```bash
response=$(curl -s -X POST http://localhost:8001/api/tasks -H "Content-Type: application/json" -d '{"name":"test","priority":10}')
task_id=$(echo "$response" | jq -r '.data.task_id')
curl -N http://localhost:8001/api/tasks/$task_id/events
curl http://localhost:8001/api/tasks/$task_id | jq
```

Action registry smoke check:
```bash
uv run python -c "from engine.action_registry import list_actions; print('\\n'.join(list_actions()))"
```
