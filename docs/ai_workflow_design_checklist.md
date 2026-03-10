# AI Workflow Design Checklist

> Status: working design + progress checklist.
> This file is for ongoing AI workflow planning and implementation tracking.
> It is **not** a canonical status ledger. Canonical project status remains in `docs/project_progress.md` and `docs/current_main_status.md`.

## 1. Purpose

This document tracks the intended AI workflow direction for `webrpa`:

1. When a new task is encountered, use a vision-led exploration executor to try to run the task end-to-end.
2. During exploration, reuse existing project interfaces, actions, task control, and runtime boundaries as much as possible.
3. Persist enough multi-run evidence and logs to support later distillation.
4. Distill those logs and samples into a final runnable YAML plugin (`manifest.yaml` + `script.yaml`).

This document should be updated continuously during development.

## 2. Document Boundaries

- Use this file for working design, implementation checklist, open questions, and progress notes.
- Use `docs/HANDOFF.md` for cross-session continuation and evidence workflow.
- Use `docs/project_progress.md` and `docs/current_main_status.md` only for repo-backed canonical status claims.

## 3. Current Baseline in Main

The current main branch AI baseline is intentionally narrower than the target workflow described here.

- Managed `gpt_executor` runs through the existing `/api/tasks` control plane.
- The executor is structured-state-first.
- Fallback evidence is secondary and currently bounded.
- Model traces are persisted as append-only JSONL under `config/data/traces/`.
- Golden Run distillation currently produces reviewable YAML drafts offline.
- Drafts are not auto-installed into `plugins/`.

## 4. Target Workflow Direction

The intended target workflow is:

1. **Vision-led exploration**
   - For unseen tasks, this working design requires a strong GUI-recognition and GUI-understanding visual model as the main exploration driver.
   - Model selection remains capability-first and still open, it is not bound to a single named candidate.
   - Current AI development for this wave is cloud-machine-first, with Android cloud machines treated as the primary current AI surface.
   - browser support remains supported but secondary for this wave.
   - Prefer existing project actions and runtime interfaces over raw, ad-hoc behavior.

2. **Multi-run execution and evidence accumulation**
   - Run the same task through multiple attempts.
   - Capture successful runs, failed runs, branch points, retries, observations, and action outcomes.

3. **Distillation-ready logging**
   - Persist logs in a form that supports replay, comparison, clustering, and parameter extraction.
   - Preserve enough evidence to distinguish one-off lucky runs from stable workflow patterns.

4. **Workflow distillation**
   - Analyze one or more logged runs.
   - Extract stable steps, parameterizable inputs, waits, and produced values.
   - Generate `manifest.yaml` and `script.yaml` that can become a real plugin.

5. **Usability gate before promotion**
   - Parse the generated YAML.
   - Validate manifest inputs.
   - Load it through the current plugin path.
   - Replay-smoke it through `Runner`.
   - Only then treat it as promotable.

## 5. Design Principles

### 5.1 Plugin-first remains the durable architecture

The target direction does **not** replace plugins with free-form AI execution.
The goal is to use AI exploration to discover and distill durable plugins faster.

### 5.2 Existing interfaces first

The exploration executor should prefer:

- registered actions,
- `Runner` and runtime seams,
- task control-plane boundaries,
- current observation interfaces,
- existing browser/native/sdk helpers.

It should not default to inventing a parallel execution stack unless existing boundaries prove insufficient.

### 5.3 Logs are product assets, not debug leftovers

Distillation quality depends on trace quality.
The project should treat exploration logs, evidence summaries, and distilled samples as first-class assets.

### 5.4 Multi-run evidence matters

Single-run success is useful, but the long-term target is not “one lucky successful replay.”
The target is a stable workflow abstraction that survives repeated execution.

## 6. Planned Workflow Stages

### Stage A — Exploration setup

- define task goal,
- define allowed interfaces/actions,
- define observation policy,
- define success and stop conditions,
- define run budget and retry rules.

### Stage B — Vision-led execution loop

- observe current screen/state,
- reason about the next step,
- choose an existing action/interface,
- execute one step,
- collect outcome and evidence,
- continue until success, failure, or budget exhaustion.

### Stage C — Multi-run sample accumulation

- store successful runs,
- store failed runs with reason codes,
- keep action-by-action evidence,
- preserve transitions and branch points,
- identify repeated successful patterns.

### Stage D — Distillation pass

- extract stable action sequences,
- parameterize inputs,
- preserve produced references,
- infer waits/checkpoints,
- collapse repeated boilerplate where possible.

### Stage E — YAML generation

- generate `manifest.yaml`,
- generate `script.yaml`,
- keep outputs reviewable,
- preserve enough metadata to trace the draft back to source runs.

### Stage F — Promotion gate

- parse validation,
- loadability validation,
- replay smoke,
- optional targeted assertions,
- explicit promotion decision.

## 7. Required Artifacts

The target workflow needs the following artifacts.

- Per-run trace records
- Observation evidence
- Action/result history
- Failure reasons and stop reasons
- Distillation summary
- Draft `manifest.yaml`
- Draft `script.yaml`
- Validation results for generated drafts

## 8. Guardrails

- Keep plugins as the durable business workflow boundary.
- Prefer structured project actions over uncontrolled direct behavior.
- Do not treat a single successful run as sufficient proof of a stable plugin.
- Do not auto-promote generated YAML into `plugins/` without explicit validation.
- Keep workflow-level recovery logic bounded; do not dump uncontrolled fallback chains into generated plugins.
- Preserve parameterization and avoid baking secrets, device-specific literals, or one-off values into generated drafts.

## 9. Open Questions / Watchpoints

- How vision-led should the exploration loop be when structured-state signals are available?
- What minimum log schema is sufficient for reliable multi-run distillation?
- When does one-run distillation remain useful, and when is multi-run consensus mandatory?
- What counts as a stable step versus a transient recovery maneuver?
- Which generated waits should remain explicit in YAML, and which should be compressed into composite actions?
- What evidence threshold should be required before promotion from draft to plugin?

## 10. Implementation Checklist

### 10.1 Exploration executor

- [ ] Define the target execution contract for unseen tasks.
- [ ] Define how the executor chooses between visual reasoning and existing structured-state signals.
- [ ] Define the allowed action/interface boundary for exploration mode.
- [ ] Add explicit run budget, stop conditions, and failure taxonomy for exploration runs.

### 10.2 Logging and trace quality

- [ ] Define the distillation-oriented log schema.
- [ ] Capture observation evidence needed for later comparison across runs.
- [ ] Capture action intent, chosen parameters, and actual action results.
- [ ] Capture failure reasons, branch points, and retry context.
- [ ] Ensure logs can be grouped by task, target, run, and attempt.

### 10.3 Multi-run sample handling

- [ ] Define how multiple runs for the same task are grouped.
- [ ] Define how successful and failed runs are compared.
- [ ] Define how stable paths are identified across samples.
- [ ] Define how one-off or low-confidence steps are excluded from final drafts.

### 10.4 Distillation

- [ ] Define the distillation input contract for one run vs multiple runs.
- [ ] Define stable-step extraction rules.
- [ ] Define parameterization rules for literals, secrets, identifiers, and produced refs.
- [ ] Define how waits, checkpoints, and post-action transitions map into YAML.
- [ ] Define how to surface draft provenance back to source runs.

### 10.5 YAML generation and promotion

- [ ] Generate reviewable `manifest.yaml` drafts.
- [ ] Generate reviewable `script.yaml` drafts.
- [ ] Validate parse/load/replay usability.
- [ ] Define explicit promotion rules from draft to runnable plugin.
- [ ] Define whether promotion remains manual, approved, or fully automated.

### 10.6 Progress notes

- [ ] Add date-stamped progress entries here as implementation advances.
- [ ] Keep major architecture decisions and reversals summarized in this file.

## 11. Progress Log

### 2026-03-10

- Initial working checklist created.
- Current repo baseline and target AI workflow direction documented.
- Main identified gap: current implementation supports bounded planning and offline draft distillation, but not yet vision-led multi-run exploration and sample-based plugin generation.
