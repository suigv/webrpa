# WebRPA Docs

`docs/STATUS.md` is the **current truth anchor** for the frozen 1.0 launch state.

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

- **[project_progress.md](project_progress.md)** — historical progress log plus rolling summary; read as log-oriented history, not the primary current-state source.
- **[TECHNICAL_DEBT.md](TECHNICAL_DEBT.md)** — active debt register and anti-regression guardrails.
- **[HANDOFF.md](HANDOFF.md)** — continuation/runbook context for deeper engineering handoff.
- **[monitoring_rollout.md](monitoring_rollout.md)** — monitoring rollout notes and operational guidance.
- **[stale_running_recovery_tuning.md](stale_running_recovery_tuning.md)** — stale-running tuning guidance.

## Future / strategy

Use these for direction-setting and longer-horizon planning. They should not be read as proof that those items are in the frozen 1.0 launch scope.

- **[ROADMAP.md](ROADMAP.md)** — milestone planning and future work. M5/WebRTC belongs here as post-1.0 work.
- **[PROJECT_GOALS.md](PROJECT_GOALS.md)** — long-range goals and success criteria.
- **[architecture_2_0.md](architecture_2_0.md)** — strategic architecture vision.
- **[SKILLS_EVOLUTION.md](SKILLS_EVOLUTION.md)** — future-facing architecture/skills evolution analysis.
- **[ai_workflow_design_checklist.md](ai_workflow_design_checklist.md)** — design checklist for AI workflow evolution.

## Quick orientation

1. Read **[STATUS.md](STATUS.md)** for the current launch-ready snapshot.
2. Use **[HTTP_API.md](HTTP_API.md)**, **[PLUGIN_CONTRACT.md](PLUGIN_CONTRACT.md)**, **[CONFIGURATION.md](CONFIGURATION.md)**, and **[FRONTEND.md](FRONTEND.md)** for current contracts.
3. Use **[project_progress.md](project_progress.md)** and **[TECHNICAL_DEBT.md](TECHNICAL_DEBT.md)** for history and governance context.
4. Read **[ROADMAP.md](ROADMAP.md)** and related strategy docs only as future-facing material.
