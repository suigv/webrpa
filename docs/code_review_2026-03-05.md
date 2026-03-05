# Code Review (2026-03-05)

## Scope
- Repository-wide sanity check for import correctness and test/bootstrap readiness.
- Commands used:
  - `python -m pytest -q`
  - `rg -n "\b(from|import) new\b|from new\.|import new\."`

## Findings

### 1) Critical: runtime imports point to a non-existent `new` package
- `api/server.py` and many other modules import `new.*` directly.
- In the current repository layout, top-level directories are `api/`, `core/`, `engine/`, etc. (no `new/` package directory), so imports fail during module collection and app startup unless the code is relocated under a `new/` package.
- Example: `from new.api.routes import ...` in `api/server.py`.

**Impact**
- App/test bootstrap fails with `ModuleNotFoundError: No module named 'new'`.
- Blocks all runtime and CI verification steps.

**Recommendation**
- Choose one consistent packaging strategy:
  1. Move project into a real `new/` package directory and keep `new.*` imports; or
  2. Replace `new.*` imports with repository-local imports (`api.*`, `core.*`, etc.) and update docs/tests accordingly.

### 2) High: test dependency gap (`httpx` missing)
- Test modules use `fastapi.testclient.TestClient`, which requires `httpx` in modern Starlette/FastAPI stacks.
- `requirements.txt` currently omits `httpx`.

**Impact**
- Test collection fails before executing test logic.

**Recommendation**
- Add `httpx` to dependency set (prefer pinned/compatible version with FastAPI 0.115.0).
- Optionally split runtime vs dev dependencies (`requirements.txt` + `requirements-dev.txt`).

### 3) Medium: documentation and repository layout are inconsistent
- `README.md` states commands should be run from a parent directory and references `new/...` paths (`new/tests`, `new/tools`, `new/requirements.txt`).
- Current repository content is at root (`tests/`, `tools/`, `requirements.txt`), which conflicts with documented execution model.

**Impact**
- New contributors follow README and hit path/import failures.

**Recommendation**
- Align README with actual structure, or complete the intended `new/` standalone directory layout.
