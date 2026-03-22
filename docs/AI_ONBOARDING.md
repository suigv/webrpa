# AI Agent Onboarding Guide

This guide is for new AI sessions entering the repository.

Start from the **current launch-state docs**, not from strategy or vision materials.

## Current-state first rules

- Treat **Launch 1.0 scope as frozen**: device management, task scheduling, and plugin execution.
- Treat **`docs/STATUS.md` as the current truth anchor**.
- Do **not** infer that browser hands-on QA is complete; it remains environment-blocked.
- Do **not** treat M5/WebRTC as current launch scope; it is future roadmap material only.
- Strategy docs help with direction, but they are **not** the current implementation contract.

## Recommended reading order

### 1. Read first: current launch-state snapshot

- **[STATUS.md](STATUS.md)**  
  Start here for the frozen 1.0 launch snapshot, current verification boundary, browser QA caveat, and explicit exclusion of M5/WebRTC from launch scope.
- **[README.md](README.md)**  
  Docs landing page that separates current reference docs from historical/governance material and future/strategy material.

### 2. Read next: current contracts

- **[HTTP_API.md](HTTP_API.md)**  
  Current backend/API contract.
- **[PLUGIN_CONTRACT.md](PLUGIN_CONTRACT.md)**  
  Current plugin manifest, payload, and runtime contract.
- **[CONFIGURATION.md](CONFIGURATION.md)**  
  Current runtime configuration and environment-variable contract.
- **[FRONTEND.md](FRONTEND.md)**  
  Current frontend deployment model, payload boundary, and known constraints.

### 3. Read after that: historical and governance context

- **[project_progress.md](project_progress.md)**  
  Historical/log-oriented progress record. Useful for chronology and recent changes, but not the primary current-state contract.
- **[TECHNICAL_DEBT.md](TECHNICAL_DEBT.md)**  
  Current debt register, guardrails, and anti-regression context.
- **[HANDOFF.md](HANDOFF.md)**  
  Deeper engineering handoff and continuation context.

### 4. Read last: future / vision / strategy

These documents are useful for long-range direction, but they should not be treated as proof of what is included in the frozen 1.0 launch state.

- **[ROADMAP.md](ROADMAP.md)**  
  Future milestone framing, including post-1.0 items such as M5/WebRTC.
- **[PROJECT_GOALS.md](PROJECT_GOALS.md)**  
  Long-range goals and success criteria.
- **[architecture_2_0.md](architecture_2_0.md)**  
  Strategic architecture vision.
- **[SKILLS_EVOLUTION.md](SKILLS_EVOLUTION.md)**  
  Future-facing architecture evolution analysis.

## AI responsibilities

- Keep recommendations aligned with the current docs hierarchy above.
- Prefer current contracts over historical notes when they differ.
- Update relevant docs when functional changes alter the current contract.
- Do not over-claim completion, especially around browser hands-on QA or WebRTC takeover.

## Suggested first prompt for a new session

> Please read `docs/STATUS.md` and `docs/README.md` first, then review the current contract docs in `docs/AI_ONBOARDING.md` before making changes.
