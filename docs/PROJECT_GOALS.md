# Project Goals

## Purpose
This document defines the north-star goals, scope boundaries, and success criteria for `webrpa`. It is the decision anchor for what we build (and what we explicitly do not build). Progress tracking belongs in `docs/project_progress.md`, and execution planning belongs in `docs/ROADMAP.md`.

## Target Users
- Primary: Business operations teams running high-volume, repeatable workflows.
- Future: External customers who need a self-serve automation platform.

## North Star
Enable business operations to execute scripted tasks across supported applications using vision-capable models, collect sufficient multi-run evidence, and distill stable, model-free YAML plugins that can run without model dependency.

## Core Goals
- G1: Vision-model execution reliably completes scripted workflows for ops-grade tasks.
- G2: Multi-run logging captures enough evidence to diagnose failures and support distillation.
- G3: Distillation produces a model-free YAML plugin that can replay and pass smoke validation.
- G4: Platform is ready for external users with an account system (authentication + basic access control).

## Workflow Scope (Ops)
- All operational workflows target supported application script tasks.
- Initial workflow list should be explicit and small (3-5 critical flows).
- Representative workflows are the current plugin library under `plugins/` (source of truth).
  - Current list: `device_reboot`, `device_soft_reset`, `hezi_sdk_probe`, `mytos_device_setup`.

## Non-Goals (Near Term)
- Building a new general-purpose workflow language.
- Replacing the existing plugin contract or re-architecting routes.
- UI redesigns that are not required for operational usage.
- Long-running human-in-the-loop labeling systems beyond targeted feedback hooks.

## Success Metrics (Draft, To Confirm)
- Vision-run success rate on top N workflows in staging (goal: keep improving; set explicit thresholds per workflow).
- Distilled plugin replay pass rate over M runs.
- Evidence completeness rate per run (trace + screenshots + action results).
- Median time to diagnose a failed run using captured evidence.
- Cost per successful run (model usage + infrastructure).

## Default Success Thresholds (Can Be Tuned Per Workflow)
- Success rate (staging): simple >= 95%, complex >= 90%.
- Distilled plugin replay pass rate: >= 95% over M runs.
- Evidence completeness: >= 95% of runs have full required evidence payload.
- Latency (P95 end-to-end): simple <= 5 minutes, complex <= 12 minutes.

## Distillation Gate (Default)
- Simple tasks: distill after 3 successful runs.
- Complex tasks: distill after at most 10 successful runs.
- Only successful logs are used for distillation when each run is model-from-scratch (no external assistance or injected hints).
- Definition of simple vs complex must be documented per workflow.
- Successes are cumulative (not required to be consecutive).

## Simple vs Complex Definition (Initial)
- Simple: no branching and step count <= 10.
- Complex: any branching, or step count > 10.
- Thresholds can be adjusted per workflow, but must be documented.

## Minimum Evidence Payload (Required for Distillation)
The following evidence is required per run to qualify for distillation:
- Model trace records (JSONL) for each step and a terminal record.
- Step record fields: `chosen_action`, `action_params`, `observation` (with `modality`, `data`, and `observed_state_ids`), `action_result`, and step timestamps.
- Planner request/response metadata: `provider`, `model`, `request_id`, and error codes if any.
- Fallback evidence when used: UI XML or browser HTML snapshot.
- Screenshot capture with `save_path`, `byte_length`, and screen metadata (width/height). Real device screen dimensions are required for VLM coordinate compensation.
- Runtime context: task id, run id, target label, and runtime profile identifiers.

## Constraints and Invariants
- Baseline startup must succeed with `MYT_ENABLE_RPC=0`.
- Persistent data must remain under `config/data`.
- `api/server.py` is the sole application entrypoint and `/web` remains available.
- No legacy imports from `tasks` or `app.*`.

## Roadmap Link
See `docs/ROADMAP.md` for the milestone route and current completion status.

## Open Questions
- What success thresholds should we use for completion rate and latency?
