# WebRPA Docs

`docs/STATUS.md` is the **current truth anchor** for the frozen 1.0 launch state.

This folder is intentionally split into:

- **top-level current docs** — current contracts and launch-state truth
- **`governance/`** — history, debt, handoff
- **`strategy/`** — roadmap and future-facing architecture
- **`ops/`** — operational rollout/runbook notes
- **`reference/`** — large external/vendor API references

This docs landing page is intentionally conservative:

- **1.0 launch scope is limited to** device management, task scheduling, and plugin execution.
- **Browser hands-on QA remains environment-blocked**; current docs should not imply full browser live verification.
- **M5/WebRTC is out of scope for 1.0** and belongs only to future-facing roadmap/strategy materials.

## Current reference

Use these first when you need the current contract, current state, or launch-readiness boundaries.

- **[STATUS.md](STATUS.md)** — current status matrix and launch-readiness snapshot; start here.
- **[HTTP_API.md](HTTP_API.md)** — current backend control-plane API reference.
- **[PLUGIN_CONTRACT.md](PLUGIN_CONTRACT.md)** — current plugin/runtime payload contract.
- **[CONFIGURATION.md](CONFIGURATION.md)** — current configuration and environment-variable reference.
- **[FRONTEND.md](FRONTEND.md)** — current frontend deployment contract and known constraints.
- **[AI_ONBOARDING.md](AI_ONBOARDING.md)** — guided reading order for new AI sessions.

## Historical / governance

Use these for implementation history, debt tracking, handoff context, and governance records. They are useful, but they are **not** the primary source for the frozen 1.0 launch snapshot.

- **[governance/README.md](governance/README.md)** — entry point for progress log, debt register, and handoff docs.
- **[ops/README.md](ops/README.md)** — entry point for rollout and deployment notes.

## Future / strategy

Use these for direction-setting and longer-horizon planning. They should not be read as proof that those items are in the frozen 1.0 launch scope.

- **[strategy/README.md](strategy/README.md)** — entry point for roadmap, goals, architecture vision, and future-facing notes.
- **[reference/README.md](reference/README.md)** — entry point for large SDK/API reference manuals.

## Quick orientation

1. Read **[STATUS.md](STATUS.md)** for the current launch-ready snapshot.
2. Use **[HTTP_API.md](HTTP_API.md)**, **[PLUGIN_CONTRACT.md](PLUGIN_CONTRACT.md)**, **[CONFIGURATION.md](CONFIGURATION.md)**, and **[FRONTEND.md](FRONTEND.md)** for current contracts.
3. Use **[governance/README.md](governance/README.md)** for history and governance context.
4. Read **[strategy/README.md](strategy/README.md)** only as future-facing material.
