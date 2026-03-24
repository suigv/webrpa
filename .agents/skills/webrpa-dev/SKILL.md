---
name: webrpa-dev
description: Use when working in the webrpa repository on backend APIs, task orchestration, plugins, frontend console, browser/RPA integrations, adapters, AI services, shared utilities, or project-specific validation. Applies to tasks touching api/, core/, engine/, models/, plugins/, tests/, tools/, config/, web/, common/, hardware_adapters/, or ai_services/.
---

# WebRPA Dev

Use this skill for the current `webrpa` repository checkout.

## First Read

Always read before changing code:

- `../../../AGENTS.md`

Read these only when relevant:

- Repo setup, startup flow, or top-level feature overview: `../../../README.md`
- `agent_executor`, runtime protocol, or plugin/AI operation behavior: `../../../AI_SKILL.md`
- Frontend or `/web`: `../../../docs/FRONTEND.md`
- HTTP/API contract work: `../../../docs/HTTP_API.md`
- Plugins/workflow distillation: `../../../docs/PLUGIN_CONTRACT.md`

## Repo Shape

- Backend: FastAPI + Python 3.11 in `api/`, `core/`, `engine/`, `models/`
- Frontend: Vite + TypeScript in `web/`
- Runtime: plugin workflows in `plugins/`
- Shared utilities: `common/`
- Browser/RPA/device adapters: `hardware_adapters/`
- AI integrations: `ai_services/`

## Non-Negotiables

- Do not introduce imports from `tasks` or `app.*`
- Keep routes thin; business logic belongs in `core/` or `engine/`
- `config/apps/*.yaml` is the single source of truth for app-specific config
- Do not hardcode app package names, UI keywords, or old repo paths in framework code
- Keep data under `config/data`

## Validation

Run validation after meaningful changes, but match the cost to the surface area changed.

Always run:

```bash
cd ../../../
./.venv/bin/python tools/check_no_legacy_imports.py
./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
curl http://127.0.0.1:8001/health
```

If Python code changed, also run:

```bash
cd ../../../
./.venv/bin/python -m ruff check <touched_python_paths>
./.venv/bin/python -m pytest tests -q
```

If frontend changed, also run:

```bash
cd ../../../web
npm run typecheck
```

If the change touches startup, runtime wiring, `engine/`, `core/`, `hardware_adapters/`, `config/`, or RPC assumptions, also check the compatibility path:

```bash
cd ../../../
MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

## Task Heuristics

- API/task system work: inspect `../../../core/task_control.py`, `../../../core/task_execution.py`, `../../../core/task_finalizer.py`, `../../../core/task_metrics.py`
- Action/runtime work: inspect `../../../engine/action_registry.py`, `../../../engine/runner.py`, and related `../../../engine/actions/*`
- Plugin work: inspect `../../../plugins/*/manifest.yaml` and `../../../plugins/*/script.yaml`
- Frontend work: inspect `../../../web/js/`, `../../../web/styles.css`, and Vite entrypoints before editing
- Browser or device/RPC issues: inspect `../../../hardware_adapters/` and avoid assuming RPC is always enabled
- AI service work: inspect `../../../ai_services/` and the runtime call sites that construct model requests
- Shared helper changes: inspect `../../../common/` call sites before changing shared behavior

## MCP Preference

When available, prefer:

- `playwright` for `/web` UI flows, SSE screens, and browser regressions
- `context7` for FastAPI, Vite, TypeScript, pytest, and other library docs
- `github` only when the task depends on remote issues, PRs, or repo metadata
