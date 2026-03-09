# 2026-03-09 docs progress sync, source-of-truth matrix

Scope: evidence synthesis only. This file defines what later docs tasks may claim. It does not update `README.md`, `docs/project_progress.md`, `docs/current_main_status.md`, `docs/HANDOFF.md`, or `docs/README.md`.

## Target surfaces

| Surface | Role in later sync |
| --- | --- |
| `README.md` | Summary surface only, short feature and rollout summary |
| `docs/project_progress.md` | Canonical progress and capability ledger |
| `docs/current_main_status.md` | Short current-status ledger |
| `docs/HANDOFF.md` | Continuation and evidence-runbook surface |
| `docs/README.md` | Optional wording sync only if active-doc descriptions become stale |

## Claim matrix

| Status | Allowed claim for later docs | Backing source(s) | Target surface(s) |
| --- | --- | --- | --- |
| completed | `wait_until` polling semantics were tightened and regression coverage was added for success-before-timeout, timeout text, `on_timeout goto`, `on_fail` fallback, cancellation, and dynamic re-polling against changing context data. | `/Users/chenhuien/webrpa/.sisyphus/notepads/workflow-roadmap-executable-checklist/learnings.md:1-2` | `README.md`, `docs/project_progress.md`, `docs/current_main_status.md`, `docs/HANDOFF.md` |
| completed | `ExecutionContext.session.defaults` is now the minimal task-scoped seam. Later docs may say normalized connection values can come from payload or `_target` plus manifest defaults, while explicit action params still override those defaults. | `/Users/chenhuien/webrpa/.sisyphus/notepads/workflow-roadmap-executable-checklist/learnings.md:3` | `README.md`, `docs/project_progress.md`, `docs/current_main_status.md`, `docs/HANDOFF.md` |
| completed | UI-state coverage expanded conservatively with `timeline_candidates` and `follow_targets` bindings, plus first-item aliases for collection observations, without changing the top-level observation result shape. | `/Users/chenhuien/webrpa/.sisyphus/notepads/workflow-roadmap-executable-checklist/learnings.md:4` | `README.md`, `docs/project_progress.md`, `docs/current_main_status.md`, `docs/HANDOFF.md` |
| completed | Bounded composite actions `ui.navigate_to` and `ui.fill_form` are part of the recent completed wave. Docs may describe them as bounded page-level navigation and form-driving helpers, not as a full workflow-recovery system. | `/Users/chenhuien/webrpa/.sisyphus/notepads/workflow-roadmap-executable-checklist/learnings.md:6`, `/Users/chenhuien/webrpa/tests/test_login_composite_actions.py` matches for `ui.navigate_to` and `ui.fill_form` from targeted repo search | `README.md`, `docs/project_progress.md`, `docs/current_main_status.md`, `docs/HANDOFF.md` |
| completed | `x_mobile_login` can omit repeated runtime plumbing such as `device_ip` and `package` via manifest or `_target` session defaults without changing status or message contracts. | `/Users/chenhuien/webrpa/.sisyphus/notepads/workflow-roadmap-executable-checklist/learnings.md:5`, `/Users/chenhuien/webrpa/.sisyphus/evidence/task-8-login-workflow.txt:3-14` | `README.md`, `docs/project_progress.md`, `docs/current_main_status.md`, `docs/HANDOFF.md` |
| completed | The `x_mobile_login` validation wave is backed by targeted login workflow tests and a manual runtime smoke that returned `status: success`, `message: login completed`, and `task: x_mobile_login`. | `/Users/chenhuien/webrpa/.sisyphus/evidence/task-8-login-workflow.txt:3-14` | `docs/project_progress.md`, `docs/current_main_status.md`, `docs/HANDOFF.md` |
| completed | The runtime plane validation wave is backed by targeted runtime/control-plane tests and a live startup plus `/health` smoke with `MYT_ENABLE_RPC=0`. | `/Users/chenhuien/webrpa/.sisyphus/evidence/task-9-runtime-plane.txt:3-14` | `docs/project_progress.md`, `docs/current_main_status.md`, `docs/HANDOFF.md` |
| deferred | Workflow-level conservative recovery extraction is explicitly DEFERRED. Later docs must not describe it as shipped or completed. | `/Users/chenhuien/webrpa/.sisyphus/evidence/task-7-recovery-gate.txt:1-9`, `/Users/chenhuien/webrpa/.sisyphus/notepads/workflow-roadmap-executable-checklist/learnings.md:7` | `README.md`, `docs/project_progress.md`, `docs/current_main_status.md`, `docs/HANDOFF.md`, `docs/README.md` |
| next step | The next wording should keep workflow-level conservative recovery framed as a watchpoint: wait for the same bounded ordered chain to recur across multiple workflows before extracting shared policy upward. | `/Users/chenhuien/webrpa/.sisyphus/evidence/task-7-recovery-gate.txt:3-9`, `/Users/chenhuien/webrpa/.sisyphus/notepads/workflow-roadmap-executable-checklist/learnings.md:7` | `docs/project_progress.md`, `docs/current_main_status.md`, `docs/HANDOFF.md` |
| next step | Later doc editors should preserve the hierarchy from the plan: `README.md` stays summary-level, `docs/project_progress.md` and `docs/current_main_status.md` stay canonical status surfaces, `docs/HANDOFF.md` stays continuation and evidence-runbook context, and `docs/README.md` is optional only if stale. | `/Users/chenhuien/webrpa/.sisyphus/plans/webrpa-docs-progress-sync.md:29-37`, `/Users/chenhuien/webrpa/.sisyphus/plans/webrpa-docs-progress-sync.md:58-68`, `/Users/chenhuien/webrpa/.sisyphus/plans/webrpa-docs-progress-sync.md:109-137` | `README.md`, `docs/project_progress.md`, `docs/current_main_status.md`, `docs/HANDOFF.md`, `docs/README.md` |

## Wording guardrails for later tasks

- Keep recent-progress claims bounded to the evidence above.
- Treat `DEFERRED` as a required literal status for workflow-level conservative recovery extraction.
- For `ui.navigate_to` and `ui.fill_form`, describe bounded navigation and form helpers only. Don't expand that into a broader recovery claim.
- For `ExecutionContext.session.defaults`, keep the override order explicit: action params first, then session defaults, then raw payload fallback.
- For `x_mobile_login`, claim reduced repeated runtime plumbing and preserved status/message contracts, not a full workflow rewrite.
