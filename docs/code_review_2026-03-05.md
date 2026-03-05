# Code Review (2026-03-05)

## Scope
- Repository-wide sanity check for import correctness and test/bootstrap readiness.
- Commands used:
  - `python -m pytest -q`
  - `rg -n "legacy namespace import patterns"`

## Findings

### 1) Critical: runtime imports pointed to a non-existent package namespace
- `api/server.py` and many other modules imported a legacy namespace directly.
- In the current repository layout, top-level directories are `api/`, `core/`, `engine/`, etc., so those imports fail during module collection and app startup unless code and imports are aligned.
- Example before fix: `from api.routes import ...` in `api/server.py`.

**Impact**
- App/test bootstrap fails with `ModuleNotFoundError: No module named 'new'`.
- Blocks all runtime and CI verification steps.

**Recommendation**
- Choose one consistent packaging strategy:
  1. Use a single package namespace and keep imports consistent; or
  2. Use repository-local imports (`api.*`, `core.*`, etc.) and update docs/tests accordingly.

### 2) High: test dependency gap (`httpx` missing)
- Test modules use `fastapi.testclient.TestClient`, which requires `httpx` in modern Starlette/FastAPI stacks.
- `requirements.txt` currently omits `httpx`.

**Impact**
- Test collection fails before executing test logic.

**Recommendation**
- Add `httpx` to dependency set (prefer pinned/compatible version with FastAPI 0.115.0).
- Optionally split runtime vs dev dependencies (`requirements.txt` + `requirements-dev.txt`).

### 3) Medium: documentation and repository layout are inconsistent
- `README.md` states commands should be run from a parent directory and references `...` paths (`tests`, `tools`, `requirements.txt`).
- Current repository content is at root (`tests/`, `tools/`, `requirements.txt`), which conflicts with documented execution model.

**Impact**
- New contributors follow README and hit path/import failures.

**Recommendation**
- Align README with actual structure, or complete the intended `` standalone directory layout.
