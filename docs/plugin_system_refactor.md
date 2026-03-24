# Plugin System Refactor Design Draft

Last updated: 2026-03-24
Status: collection complete, planning generated, core slice and review/save authoring flow implemented
Source: consolidated from refactor discussion

## Implementation Status

Current completed implementation slice:

- canonical app identity resolution now supports shared app metadata such as `display_name`, `aliases`, and multiple package names
- account import can bootstrap a new app namespace without pre-writing code or config
- app catalog now exposes richer app metadata to frontend callers
- account import UI and AI dialog UI now allow selecting an existing app or entering a new app inline
- AI dialog planner accepts custom app identity metadata and can continue in exploration mode when no reviewed app config exists yet
- accounts now persist `default_branch` and `role_tags`, and account checkout supports branch-aware plus tag-aware allocation
- plugin/runtime compatibility now normalizes legacy `ai_type` into canonical `branch_id`
- pipeline payload can bind `branch_id`, `accepted_account_tags`, and `resource_namespace`, and child steps cannot override those inherited values
- blogger candidate sharing now uses claim/commit/release lifecycle backed by a dedicated shared resource store instead of ad-hoc list reads only
- AI takeover text input now supports typed annotation, and AI history supports saving reusable branch/default-input choices back into workflow draft preferences
- distilled selectors, states, stage-pattern markers, and agent hints now enter a reviewed app-config candidate pool instead of writing directly into shared app YAML
- operators can review or reject pending app-config candidates before promoting them into shared app skeleton config
- arbitrary apps now support editable branch profiles with default branch, search keywords, blacklist keywords, reply texts, reply AI type, resource namespace, and payload defaults
- post-run selective save now supports workflow default branch, branch-level search keywords, branch-level reply texts, and branch resource namespace in addition to account/draft defaults
- X plugin manifests were cleaned up to use branch-oriented semantics, and `x_login` no longer exposes the obsolete `credential_slot` input
- existing X workflow plugins now prefer app branch profiles for keyword/query/reply/resource decisions, while legacy strategy files remain compatibility fallback only

## Purpose

This document is the source of truth for the upcoming plugin-system refactor.

It is no longer a chat log or idea dump. It now captures:

- confirmed product and architecture decisions
- normalized terminology
- storage and ownership boundaries
- the remaining small set of open design questions

The next step after this document is implementation planning, not more free-form collection.

## Design Goals

- Support `AI dialog -> execution -> distill` as the primary path for app-level automation.
- Keep new app onboarding data-driven, without code changes for every new app.
- Minimize low-value plugin inputs and shift necessary complexity into a better AI-dialog control surface.
- Preserve one canonical app namespace per app while allowing human-friendly naming and aliases.
- Prevent shared app config from being polluted by one-off tasks, user prompts, or unstable learned data.
- Support reusable business workflows across accounts, clouds, and pipelines through explicit resource and branch models.

## Non-Negotiable Principles

- `schemes` are optional acceleration capability, not a prerequisite for first-run AI success.
- Canonical shared app config must contain only stable app-level capability.
- AI- or trace-learned data must not directly mutate shared app YAML unless promoted through an explicit review path.
- Accounts are mandatory for current AI-dialog-driven app tasks.
- Business branch/profile must not be forced before AI dialog begins.
- After execution, users may choose what to save; if they save nothing, the system keeps those fields empty and falls back to defaults later.
- User-facing controls must use operator-friendly wording rather than internal runtime terminology.

## Core Model

### 1. App Identity Model

Each app has one canonical identity.

Recommended shape:

- `app_id`
  - canonical immutable namespace key
  - used by accounts, plugins, tasks, stores, and config lookup
- `display_name`
  - preferred UI label
- `aliases`
  - accepted human-entered synonyms
- `package_name` or `package_names`
  - runtime package identity

Rules:

- user-facing names are not storage keys
- aliases never become independent namespaces
- all persisted records store canonical `app_id`
- alias resolution happens only at ingestion boundaries
  - account import
  - task creation
  - AI dialog
  - app onboarding

Package rule:

- one runtime package maps to one canonical app namespace
- plugins for the same package use the same shared app config
- package mapping must be globally unique

## 2. App Onboarding Model

New apps must not require code edits before accounts can be imported or tasks can be created.

Required behavior:

- account import must support selecting an existing app or creating a new app namespace
- app onboarding must be data-driven
- creating a new app should bootstrap minimal app identity/config
- app branch/profile defaults must be creatable even when rich app config does not yet exist

Suggested minimal bootstrap payload:

- `app_id`
- `display_name`
- optional `package_name`

## 3. Business Branch / Profile Model

Current values like `volc` and `part_time` are not model/provider types. They are business branches.

A branch/profile is a reusable strategy bundle inside one app namespace.

Branch-bound data examples:

- search keyword pools
- DM reply strategy
- candidate scoring strategy
- other business defaults added later

Rules:

- every app has a default branch/profile
- branch definitions are isolated per app
- one app's branch set does not bleed into another app
- tasks and pipelines carry branch binding
- pipelines do not allow per-step branch override
- single-task manual override is allowed and has the highest priority

Resolved precedence:

1. explicit single-task override
2. task / pipeline selected branch
3. account default branch
4. app default branch

Important product rule:

- branch/profile is not forced before AI dialog begins
- branch may be inferred or left unresolved during execution
- after completion, the user may confirm and save the branch for later reuse

## 4. Account Model

Accounts need more than `app_id + status`.

Confirmed required account metadata:

- `app_id`
- account status
- default branch/profile
- role tags

Optional later expansion:

- additional allocation metadata if needed

Account allocation can no longer rely only on:

- same `app_id`
- `ready` status

It must also respect:

- branch/profile resolution
- account role tags

## 5. Pipeline / Task Allocation Model

Pipelines carry reusable selection constraints.

Confirmed model:

- accounts carry `role tags`
- pipelines carry `accepted account tags`

Matching rule:

- `any-match`
- if an account matches any accepted tag, it is eligible

This is intentionally not an all-tags-must-match model.

Reason:

- tags represent reusable account categories
- they should be flexible enough to support future pipelines without brittle allowlists

## 6. Runtime Data Model

Plugin/runtime data must be separated by lifecycle.

Confirmed categories:

- `payload_inputs`
  - business inputs declared by workflow/plugin contract
- `runtime_context`
  - execution environment resolved by scheduler/runtime
- `derived_artifacts`
  - values produced during one run and reused later in that run
- `shared_resources`
  - cross-task, cross-cloud reusable pools that require coordination

Examples:

- `payload_inputs`
  - keyword intent
  - daily limit
  - run quota
- `runtime_context`
  - account
  - device
  - cloud
  - task identity
- `derived_artifacts`
  - selected blogger profile
  - scraped nickname/bio/website
  - generated reply text
- `shared_resources`
  - blogger candidate pool
  - claimed blogger identity
  - processed/consumed sets

## 7. Shared Resource Model

Current `shared_key + scope + index` patterns are not sufficient as the long-term abstraction.

Shared resources need an explicit lifecycle.

Confirmed lifecycle direction:

- `collect`
- `claim`
- `derive`
- `commit`
- `release`

Required behavior:

- one cloud/task can claim a blogger identity
- another cloud cannot claim the same identity while it is reserved or consumed
- later tasks in the same workflow family must be able to reuse the claimed resource from the current run

Canonical example chain:

1. an X account logs in
2. task searches by business keywords
3. multiple blogger candidates are collected
4. one blogger identity is claimed
5. that same identity is reused by later app tasks such as clone profile or traffic-capture workflows
6. derived profile fields remain task-local artifacts unless explicitly promoted elsewhere

## 8. Shared App Config vs Candidate Learning

Shared app YAML must stay small, stable, and reviewed.

The system must separate:

- `app skeleton`
  - audited shared app capability
- `app branch/profile config`
  - reusable inside one app and one business branch
- `workflow/plugin config`
  - reusable only inside one workflow family
- `task/draft/user artifacts`
  - temporary or operator-specific
- `learned candidates`
  - reviewable, non-authoritative suggestions from traces and distillation

### What Belongs In Shared App Skeleton

Usually safe:

- canonical app identity
- display name
- aliases
- package mapping
- reviewed stable selectors
- reviewed stable states
- reviewed `schemes`
- reviewed app-level `agent_hint`

Usually not safe:

- one operator's prompt wording
- branch-specific search keywords
- DM reply style/content
- temporary fallback instructions
- one workflow's temporary selectors
- per-task resource assignments

Promotion rule:

- one successful task is never enough to write canonical config
- repeated evidence across distinct runs is required
- conflicting evidence stays in candidate storage until reviewed
- if a datum only helps one workflow family, it should stay workflow-scoped instead of becoming app-skeleton config

## 9. `schemes` Model

`schemes` are reviewed app-level navigation capability.

Rules:

- they are optional
- they are acceleration, not baseline dependency
- AI may use them only when reviewed data exists
- missing `schemes` means "no acceleration available", not configuration failure
- future candidate discovery may exist, but formal `schemes` still require review

## 10. Input Surface Strategy

The product should be asymmetrical:

- deterministic plugins: fewer inputs
- AI dialog: slightly richer, but only with high-value semantic controls

### Deterministic Plugin Inputs

Deterministic workflows should expose only true business/operator inputs.

Inputs that are generally not normal user-facing fields:

- app-fixed `app_id`
- credential slot internals
- system credential references
- compatibility-only plumbing

These may still exist internally for runtime injection or backward compatibility, but they should not remain ordinary operator inputs.

### AI Dialog Inputs

AI dialog should not become a giant generic form.

It should expose a small control surface that improves:

- bounded execution
- repeatability
- distillability

Recommended first-wave AI-dialog controls:

- `goal`
- `app_id`
- `selected_account`
- `success_criteria`
- `stop_conditions`
- `resource_intent`
- `expected_output`

Not first-wave:

- raw low-level action lists
- app plumbing internals
- cloud slot mechanics
- hidden compatibility aliases
- provider/model plumbing unless there is explicit business need

### Human Takeover Input Annotation

When a user temporarily takes over control during an AI task and performs a manual input action, the system should ask the user to label what kind of data was entered.

Purpose:

- improve later distillation quality
- help map manual input into reusable variable categories
- distinguish saveable business data from one-off temporary input
- avoid treating all manual input as opaque text

Product rule:

- this is triggered only for AI-task human takeover flows
- the interaction should be a lightweight checkbox/radio choice, not a large form
- users should see operator-friendly labels, not internal variable jargon
- if the user does not label it, the system keeps it as untyped temporary input

Recommended first-wave input types:

- account credential
- verification code
- search keyword
- blogger id / target id
- DM / reply text
- profile field text
- other temporary text

Storage rule:

- the raw entered value is not automatically promoted into shared app config
- the input type label is task-local metadata by default
- only explicitly selected non-sensitive items may enter post-run save suggestions
- secrets such as passwords or one-time codes must never become reusable saved defaults

### Human Takeover Annotation UX Draft

Trigger:

- after the user exits takeover mode and confirms a manual input happened
- or immediately after a takeover input event is detected if the UI can do so without interrupting control flow

Recommended prompt copy:

- title: `标记本次输入内容`
- helper text: `为了便于后续复用和蒸馏，请选择你刚才输入的大致类型。`
- skip option: `暂不标记`

Recommended first-wave option labels:

- `账号密码`
- `验证码`
- `搜索关键词`
- `博主ID`
- `私信/回复内容`
- `资料字段内容`
- `其他临时文本`

Recommended option help text:

- `账号密码`
  - sensitive, never reusable as saved default
- `验证码`
  - one-time sensitive input, never reusable
- `搜索关键词`
  - may later become branch/profile candidate data
- `博主ID`
  - may later become task-local target or shared resource reference
- `私信/回复内容`
  - may later become workflow draft or branch strategy candidate
- `资料字段内容`
  - may later become derived artifact or profile-edit draft
- `其他临时文本`
  - stays task-local unless explicitly promoted later

Frontend behavior rules:

- default focus should be on quick selection, not on reading long explanations
- one-tap selection is preferred over multi-step confirmation
- the dialog must not expose internal field names such as `vars.*`, `shared_resources`, or `business_profile`
- if the user skips labeling, no blocking warning should appear
- if the user labels sensitive data, the UI should show a small non-save hint such as `此类内容不会保存为默认值`

### Human Takeover Annotation API Draft

Suggested task-local record shape:

```json
{
  "annotation_id": "uuid",
  "task_id": "task_xxx",
  "step_id": "optional_step_id",
  "source": "human_takeover",
  "action_kind": "manual_input",
  "input_type": "search_keyword",
  "input_label": "搜索关键词",
  "sensitive": false,
  "save_eligible": true,
  "captured_at": "2026-03-24T12:00:00Z"
}
```

Field rules:

- `input_type`
  - canonical enum used by backend and distillation logic
- `input_label`
  - UI label snapshot for operator review history
- `sensitive`
  - hard rule for whether this class of input may enter save suggestions
- `save_eligible`
  - derived flag, normally false for credentials and verification codes
- `step_id`
  - optional correlation to the AI-generated step or runtime event

Recommended first-wave `input_type` enum:

- `account_credential`
- `verification_code`
- `search_keyword`
- `target_blogger_id`
- `dm_reply_text`
- `profile_field_text`
- `temporary_text`

Suggested write path:

- frontend submits annotation to a dedicated AI-task annotation endpoint
- backend stores it as task-local artifact metadata
- distillation pipeline reads only the typed metadata unless explicit safe-value capture is later enabled

Suggested read path:

- post-run save UI reads annotation summary
- only `save_eligible=true` items can appear in save suggestions
- sensitive items may appear in audit history but never in reusable-save candidates

## 11. Post-Run Save Model

After AI execution completes, users may choose what to save.

Confirmed behavior:

- the UI should present save options in user-friendly language
- users can save some items and leave others empty
- unselected items remain unset
- future runs then fall back to defaults

Likely saveable items:

- business branch/profile
- reusable workflow/plugin draft
- branch-level strategy choices
- resource-related reusable settings
- selected human-takeover annotations that are non-sensitive and operator-confirmed

## 12. Initial Field Placement Matrix

This is the current default placement table for future design and implementation.

| Field / Data Kind | Recommended Layer | Why |
|---|---|---|
| `app_id` | app skeleton | canonical shared identity |
| `display_name` | app skeleton | UI label for app namespace |
| `aliases` | app skeleton | human name resolution |
| `package_name` / `package_names` | app skeleton | runtime identity |
| app default branch | app skeleton | app-level fallback |
| branch/profile definitions | app branch/profile config | business strategy bundle |
| branch keyword pools | app branch/profile config | branch behavior |
| branch DM reply strategy | app branch/profile config | branch behavior |
| branch candidate scoring rules | app branch/profile config | branch behavior |
| stable login/home selectors | app skeleton | reusable across workflows |
| stable state definitions | app skeleton | app-level observation contract |
| reviewed `schemes` | app skeleton | reusable navigation capability |
| reviewed app-level `agent_hint` | app skeleton | reusable app-wide hint |
| plugin manifest inputs | workflow/plugin config | workflow contract |
| plugin-specific fallback steps | workflow/plugin config | workflow-only behavior |
| one workflow's temporary selectors | workflow/plugin config or candidate store | too narrow for app skeleton |
| task `advanced_prompt` | task/draft/user artifacts | operator-specific and unstable |
| human takeover input type annotation | task/draft/user artifacts | task-local labeling for distillation and save decisions |
| task-local `vars.*` | task/draft/user artifacts | current-run only |
| derived blogger profile | task/draft/user artifacts | produced in one run |
| claimed blogger id | shared resources | exclusive coordinated resource |
| blogger candidate pool | shared resources | reusable pool |
| processed/consumed blogger set | shared resources | resource lifecycle state |
| account default branch | account record metadata | account identity metadata |
| account role tags | account record metadata | allocation constraint |
| pipeline accepted account tags | task/pipeline metadata | allocation requirement |
| task/pipeline selected branch | task/pipeline metadata | execution selection |

## 13. Existing App-Level Task Families

Based on the current catalog, app-level task families are roughly:

- `account_auth`
  - login and auth state reachability
- `ambient_behavior`
  - warmup, feed browsing, lightweight interaction
- `resource_collection`
  - collect reusable candidates/resources
- `resource_enrichment`
  - open a claimed resource and derive structured data
- `traffic_capture`
  - use claimed/collected targets for lead-generation interaction
- `message_engagement`
  - inbox handling, reply generation, send flow

The AI dialog should not show one flat parameter set for all of them.
It should ask or infer different follow-up controls based on task family, using user-understandable phrasing.

## 14. Open Questions

Only a small set of design questions remains open before implementation planning:

1. Canonical naming
   - keep `business_profile` as the field name, or choose another stable name?
2. App onboarding
   - create new app namespace inline during import, or via a dedicated onboarding flow?
3. Package mapping
   - support one package or multiple packages per app namespace?
4. Shared resource storage
   - move from JSON to a dedicated SQLite-backed store/service?
5. Resource claim ownership
   - should ownership be keyed by `task_id`, `(device_id, cloud_id)`, or both?
6. Account tag model extensions
   - do we need preference tags or forbidden tags, or is current `any-match` enough for phase 1?
7. Candidate promotion
   - which learned data classes, if any, are safe for partial automatic promotion?

## 15. Planning Readiness

This document is ready to drive an implementation plan.

The next plan should be generated by grouping work into these streams:

1. app identity and onboarding
2. branch/profile and account metadata
3. allocation and shared resource lifecycle
4. config ownership and candidate isolation
5. AI dialog input redesign and post-run save flow
6. deterministic plugin input cleanup

## 16. Implementation Plan

This plan is ordered to reduce migration risk and keep the system runnable throughout the refactor.

### Phase 1: App Identity And Onboarding Foundation

Goal:

- establish canonical app identity before changing account, branch, or AI-dialog behavior

Scope:

- define canonical app identity schema
  - `app_id`
  - `display_name`
  - `aliases`
  - `package_name` / `package_names`
  - app default branch placeholder
- introduce or refactor a data-driven app registry/bootstrap path
- update ingestion-time app resolution
  - account import
  - task creation
  - AI dialog
- support creating a new app namespace without code edits
- keep compatibility with existing `config/apps/*.yaml` during transition

Primary files/modules:

- [`core/app_config.py`](/Users/chenhuien/webrpa/core/app_config.py)
- [`api/routes/task_routes.py`](/Users/chenhuien/webrpa/api/routes/task_routes.py)
- [`api/routes/data.py`](/Users/chenhuien/webrpa/api/routes/data.py)
- [`web/js/features/accounts.js`](/Users/chenhuien/webrpa/web/js/features/accounts.js)
- [`web/js/features/device_ai_dialog.js`](/Users/chenhuien/webrpa/web/js/features/device_ai_dialog.js)

Deliverables:

- canonical app identity contract
- alias resolution at ingestion boundaries
- new-app bootstrap path
- no hardcoded app-type dependency in import flow

Validation focus:

- importing accounts for existing app still works
- importing accounts for a new app namespace works
- same app with alias input resolves to one canonical `app_id`

### Phase 2: Branch/Profile And Account Metadata

Goal:

- establish business branch/profile as a first-class concept and store account-level defaults

Scope:

- define canonical branch/profile naming
- introduce app-scoped branch/profile config
- extend account storage with:
  - default branch/profile
  - role tags
- extend pipeline/task metadata with:
  - selected branch/profile
  - accepted account tags
- implement precedence:
  1. task override
  2. task/pipeline branch
  3. account default branch
  4. app default branch
- keep compatibility with old `ai_type` inputs at boundaries

Primary files/modules:

- [`core/account_store.py`](/Users/chenhuien/webrpa/core/account_store.py)
- [`core/account_service.py`](/Users/chenhuien/webrpa/core/account_service.py)
- [`config/strategies/nurture_keywords.yaml`](/Users/chenhuien/webrpa/config/strategies/nurture_keywords.yaml)
- [`config/strategies/interaction_texts.yaml`](/Users/chenhuien/webrpa/config/strategies/interaction_texts.yaml)
- [`engine/actions/sdk_business_support.py`](/Users/chenhuien/webrpa/engine/actions/sdk_business_support.py)
- [`engine/actions/sdk_config_support.py`](/Users/chenhuien/webrpa/engine/actions/sdk_config_support.py)

Deliverables:

- canonical branch/profile model
- account default branch support
- account role-tag support
- pipeline accepted-account-tag support
- compatibility mapping from legacy `ai_type`

Validation focus:

- account import/edit persists branch and tags
- pipeline allocation respects `any-match` tag rule
- old plugin flows using `ai_type` still function during migration

### Phase 3: Shared Resource Lifecycle

Goal:

- replace flat shared-key list usage with explicit resource-pool semantics

Scope:

- design and implement a dedicated shared-resource service/store
- model resource lifecycle:
  - `collect`
  - `claim`
  - `derive`
  - `commit`
  - `release`
- migrate blogger-candidate workflows first
- stop relying on index-based retrieval for allocatable resources
- tie claims to a stable ownership identity

Primary files/modules:

- [`engine/actions/sdk_shared_store_support.py`](/Users/chenhuien/webrpa/engine/actions/sdk_shared_store_support.py)
- [`engine/actions/sdk_business_support.py`](/Users/chenhuien/webrpa/engine/actions/sdk_business_support.py)
- [`core/task_execution.py`](/Users/chenhuien/webrpa/core/task_execution.py)
- candidate/resource persistence under [`config/data/`](/Users/chenhuien/webrpa/config/data)

Deliverables:

- shared resource contract
- blogger candidate pool with claim semantics
- migration path from `shared_key + scope + index`

Validation focus:

- concurrent clouds do not claim the same blogger identity
- downstream workflows can reuse the claimed identity from the same run
- interrupted tasks release or transition claims correctly

### Phase 4: Config Ownership And Candidate Isolation

Goal:

- stop unstable learned data from polluting canonical app YAML

Scope:

- separate canonical app config from learned candidates
- move auto-learned selectors/states/hints into candidate storage first
- define promotion/review path from candidate -> canonical config
- narrow what can be auto-written into shared app YAML
- reevaluate current `agent_hint_candidates` behavior

Primary files/modules:

- [`core/golden_run_distillation.py`](/Users/chenhuien/webrpa/core/golden_run_distillation.py)
- [`core/app_config_writer.py`](/Users/chenhuien/webrpa/core/app_config_writer.py)
- [`config/apps/*.yaml`](/Users/chenhuien/webrpa/config/apps/x.yaml)
- candidate persistence under [`config/data/`](/Users/chenhuien/webrpa/config/data)

Deliverables:

- candidate store for learned app/workflow hints
- explicit promotion boundary
- reduced automatic mutation of shared app YAML

Validation focus:

- repeated heterogeneous tasks do not directly rewrite canonical app config
- candidate evidence still accumulates
- reviewed app config remains readable and stable

### Phase 5: AI Dialog Redesign

Goal:

- make AI dialog the primary app-task authoring surface for distillable workflows

Scope:

- redesign AI-dialog request model around high-value semantic controls
- first-wave controls:
  - `goal`
  - `app_id`
  - `selected_account`
  - `success_criteria`
  - `stop_conditions`
  - `resource_intent`
  - `expected_output`
- keep branch/profile out of pre-run mandatory inputs
- add post-run save flow where users choose which learned items to persist
- add human-takeover input annotation for manual input actions during AI tasks
- make all user-visible wording operator-friendly
- ask/infer follow-up inputs by task family instead of showing one flat form

Primary files/modules:

- [`models/ai_dialog.py`](/Users/chenhuien/webrpa/models/ai_dialog.py)
- [`api/routes/ai_dialog.py`](/Users/chenhuien/webrpa/api/routes/ai_dialog.py)
- [`core/ai_dialog_service.py`](/Users/chenhuien/webrpa/core/ai_dialog_service.py)
- frontend AI-dialog UI under [`web/js/`](/Users/chenhuien/webrpa/web/js)

Deliverables:

- revised AI-dialog request/response contract
- family-aware follow-up logic
- human-takeover input-type annotation flow
- annotation endpoint and task-local storage contract
- post-run selective save UX

Validation focus:

- account binding is mandatory
- branch is not forced before execution
- users can save some outputs and leave others blank
- manual takeover input can be labeled without exposing low-level runtime fields
- sensitive manual input is not promoted into reusable defaults
- resulting tasks remain easier to distill

### Phase 6: Deterministic Plugin Input Cleanup

Goal:

- reduce catalog noise and align plugin forms with the new runtime model

Scope:

- audit plugin manifests
- classify fields into:
  - operator input
  - runtime injected field
  - compatibility-only field
- hide or remove low-value inputs from normal operator surfaces
- stop exposing app-fixed plumbing inputs as routine fields
- migrate X-family plugin manifests first

Primary files/modules:

- plugin manifests under [`plugins/`](/Users/chenhuien/webrpa/plugins)
- task-form rendering in [`web/js/`](/Users/chenhuien/webrpa/web/js)
- task payload preparation paths in frontend/backend

Deliverables:

- cleaner plugin catalog
- smaller operator-facing forms
- preserved runtime compatibility where needed

Validation focus:

- existing tasks still submit valid payloads
- hidden/system fields still inject correctly
- catalog inputs better match true operator choices

## 17. Cross-Phase Migration Rules

- Keep compatibility aliases at ingestion boundaries during migration.
- Prefer additive schema changes before destructive cleanup.
- Do not switch multiple ownership boundaries at once in one release.
- Migrate X-family workflows first, then generalize abstractions.
- Preserve a runnable fallback path after every phase.

## 18. Recommended Execution Order

1. Phase 1
2. Phase 2
3. Phase 5
4. Phase 3
5. Phase 4
6. Phase 6

Reasoning:

- app identity and branch/account metadata must exist before AI-dialog redesign can be clean
- AI-dialog redesign should happen before broad plugin cleanup, because it defines the new control surface
- shared resource lifecycle should be stabilized before removing too many old plugin compatibility inputs
- config isolation should land before any stronger auto-learning or promotion logic
