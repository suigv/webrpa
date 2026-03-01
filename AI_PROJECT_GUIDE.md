# AI Project Guide (Standalone `new/`)

## 1) Project Purpose
`new/` is a standalone baseline for independent development.

Design goals:
- keep useful foundations (API/core/models/adapters)
- remove legacy task implementations
- keep runtime as a skeleton for plugin-based redevelopment
- allow copy of only `new/` for independent development

## 2) Runtime Overview
Request flow:
1. `new/api/server.py` starts FastAPI and mounts baseline routes.
2. `new/api/server.py` serves the control console at `/web`.
2. Config/data/device routes call `new/core/*` modules.
3. Runtime endpoint `/api/runtime/execute` calls `new/engine/runner.py`.
4. Runner uses `new/engine/parser.py` and returns structured stub result.
5. Optional RPC capability is isolated in `new/hardware_adapters/myt_client.py`.
6. Optional browser automation is provided by vendored DrissionPage via `new/hardware_adapters/browser_client.py`.

## 3) File-by-File Responsibilities

### Root files
- `new/README.md`: human runbook (copy, install, start, verify).
- `new/AI_PROJECT_GUIDE.md`: this AI-oriented architecture and file-role document.
- `new/requirements.txt`: standalone dependency baseline.
- `new/__init__.py`: package marker.

### API layer
- `new/api/__init__.py`: package marker.
- `new/api/server.py`: FastAPI app entrypoint, middleware, route registration, `/health`, runtime execute endpoint.
- `new/web/index.html`: web control console shell UI.
- `new/web/styles.css`: responsive visual style for dashboard UI.
- `new/web/app.js`: frontend logic for devices/config/runtime/logs.
- `new/api/routes/__init__.py`: package marker.
- `new/api/routes/config.py`: config read/update endpoints (`/api/config`).
- `new/api/routes/data.py`: data read/update endpoints (`/api/data/accounts|location|website`) and opt-in migration endpoint.
- `new/api/routes/devices.py`: device list/status/start/stop (baseline stub behavior for start/stop).
- `new/api/routes/websocket.py`: websocket log channel (`/ws/logs`) with ping/pong and broadcast bridge.

### Core layer
- `new/core/__init__.py`: package marker.
- `new/core/config_loader.py`: config file loading/updating from `new/config/devices.json` with typed getters.
- `new/core/data_store.py`: JSON storage for accounts/location/website under `new/config/data`; legacy TXT migration is disabled unless `ENABLE_LEGACY_MIGRATION=1`.
- `new/core/device_manager.py`: in-memory device state manager and helper parsers.
- `new/core/port_calc.py`: deterministic per-device port calculation.

### Model layer
- `new/models/__init__.py`: package marker.
- `new/models/config.py`: Pydantic config schemas (`Config`, `ConfigUpdate`).
- `new/models/device.py`: device enums and response models.
- `new/models/task.py`: runtime task request/response schemas for skeleton execution.
- `new/models/judge.py`: lightweight step/task judge result dataclasses.

### Common utilities
- `new/common/__init__.py`: package marker.
- `new/common/logger.py`: unified logger and optional websocket broadcast hook.
- `new/common/toolskit.py`: root path utility (`MYT_NEW_ROOT` aware).
- `new/common/config_manager.py`: singleton config bridge over `new/core/config_loader.py`.
- `new/common/runtime_state.py`: runtime artifact cleanup helper.

### Runtime engine skeleton
- `new/engine/__init__.py`: package marker.
- `new/engine/parser.py`: normalize incoming script payload into internal plan.
- `new/engine/runner.py`: skeleton executor returning structured stub output.
- `new/engine/actions/__init__.py`: package marker.
- `new/engine/actions/ui_actions.py`: stub UI actions (`click`, `input_text`, `swipe`).
- `new/engine/actions/ai_actions.py`: stub AI actions (`llm_evaluate`, `vlm_evaluate`).

### Hardware adapters
- `new/hardware_adapters/__init__.py`: package marker.
- `new/hardware_adapters/myt_client.py`: optional MYT RPC adapter with lazy native library loading (safe when library missing).
- `new/hardware_adapters/browser_client.py`: optional browser adapter that lazy-loads vendored DrissionPage and exposes open/html/close helpers.
- `new/lib/`: native libs placeholder folder (`.so/.dylib/.dll` if needed).

### Vendored browser engine
- `new/vendor/DrissionPage/`: vendored upstream DrissionPage source tree.
- `new/vendor/DRISSIONPAGE_LICENSE`: copied upstream license file.

### AI services
- `new/ai_services/__init__.py`: package marker.
- `new/ai_services/llm_client.py`: LLM client stub.
- `new/ai_services/vlm_client.py`: VLM client stub.

### Plugins
- `new/plugins/__init__.py`: plugin namespace placeholder for future task plugins.

### Config/data assets
- `new/config/devices.json`: standalone runtime config defaults.
- `new/config/data/accounts.json`: accounts storage file.
- `new/config/data/location.json`: location storage file.
- `new/config/data/website.json`: website storage file.

### Quality, safety, and docs
- `new/tools/check_no_legacy_imports.py`: static gate that fails on forbidden imports (`tasks`, old `app.*`).
- `new/tests/conftest.py`: pytest session env setup (`MYT_NEW_ROOT`).
- `new/tests/test_import_smoke.py`: import smoke test for key modules.
- `new/tests/test_data_store_path.py`: asserts data path independence under `new/config/data`.
- `new/tests/test_health_smoke.py`: API health endpoint smoke test.
- `new/docs/migration-matrix.md`: Keep/Stub/Exclude migration decisions.

## 4) CI and Automation
- Keep CI aligned with standalone validation commands listed in this guide.
- Minimum checks: static gate + `pytest new/tests -q`.

## 5) Commands for AI or Developer

Install and run:
```bash
python3 -m venv .venv
./.venv/bin/pip install -r new/requirements.txt
MYT_NEW_ROOT=$(pwd)/new MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn new.api.server:app --host 0.0.0.0 --port 8000
```

Verify:
```bash
./.venv/bin/python new/tools/check_no_legacy_imports.py
./.venv/bin/python -m pytest new/tests -q
curl http://127.0.0.1:8000/health
```

Browser adapter smoke:
```bash
./.venv/bin/python - <<'PY'
from new.hardware_adapters.browser_client import BrowserClient
client = BrowserClient()
print("available=", client.available, "error=", bool(client.error))
PY
```

Web console smoke:
```bash
curl -I http://127.0.0.1:8000/web
```

## 6) Suggested Redevelopment Order
1. Replace runner stub in `new/engine/runner.py` with real state machine.
2. Define plugin contract in `new/plugins/` and script schema in `new/engine/parser.py`.
3. Connect `new/api/routes/devices.py` start/stop to real runtime scheduling.
4. Expand adapter interface beyond `myt_client.py` (browser adapter, mock adapter).
5. Add persistence for task runtime records (phase 2).
