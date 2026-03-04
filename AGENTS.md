# AGENTS.md for `new/` Standalone Project

## Mission
Build and evolve `new/` as an independent project.

Hard goals:
- Keep `new/` copy-ready and runnable by itself.
- Do not reintroduce legacy task code from old repo.
- Evolve runtime via pluginized architecture.

## Scope Rules

### In Scope
- `new/api/**`
- `new/core/**`
- `new/models/**`
- `new/common/**`
- `new/engine/**`
- `new/hardware_adapters/**`
- `new/ai_services/**`
- `new/plugins/**`
- `new/tests/**`
- `new/tools/**`
- `new/config/**`

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
   - `new/config/data`

## Required Validation
Run all before finishing any meaningful change:

```bash
./.venv/bin/python new/tools/check_no_legacy_imports.py
./.venv/bin/python -m pytest new/tests -q
MYT_NEW_ROOT=$(pwd)/new MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn new.api.server:app --host 127.0.0.1 --port 8001
```

Health check:

```bash
curl http://127.0.0.1:8001/health
```

## Architecture Contracts

### API Layer
- `new/api/server.py` is the single app entrypoint.
- Keep routes thin; business logic belongs in core/engine.
- `/web` is the default operator console endpoint and should remain available.

### Runtime Layer
- `new/engine/parser.py` normalizes script payload.
- `new/engine/runner.py` owns execution orchestration.
- `new/engine/actions/*` contains atomic action functions.

### Adapter Layer
- `new/hardware_adapters/myt_client.py` is optional capability.
- Native lib loading must be lazy and failure-safe.
- `new/hardware_adapters/browser_client.py` is optional browser capability based on vendored DrissionPage.
- Browser adapter must fail gracefully when DrissionPage or browser runtime is unavailable.

### Port Architecture
Each cloud machine has two ports; each device has one SDK port.
Ports are determined by `cloud_index` only — device IP provides isolation.

| Port | Formula | Role |
|---|---|---|
| `api_port` | `30000 + (cloud-1)*100 + 1` | Cloud machine HTTP API interface |
| `rpa_port` | `30000 + (cloud-1)*100 + 2` | MytRpc control channel (touch/app/key) |
| `sdk_port` | `8000` (configurable) | Device-level control API, shared across all clouds |

Example (device IP `192.168.1.214`, 10 clouds):
```
cloud 1  → api 30001, rpa 30002
cloud 2  → api 30101, rpa 30102
cloud 10 → api 30901, rpa 30902
```
Different devices use the same port numbers but different IPs — `(ip, port)` is unique.

### Data and Config Layer
- `new/core/config_loader.py` controls runtime config access.
- `new/core/data_store.py` controls JSON data I/O.
- Legacy TXT migration remains opt-in only.

## Pluginization Direction
- New business workflows go to `new/plugins/`.
- Avoid embedding business task logic inside API routes.
- Keep plugin interface stable and versioned once defined.

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
