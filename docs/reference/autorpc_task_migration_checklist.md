# autorpc Task Migration Checklist

## Scope

This checklist tracks migration parity between the legacy `autorpc/tasks` Python tasks and the local YAML plugin system.

Status values:
- `done`: equivalent or better than legacy for current scope
- `partial`: task exists but is materially weaker than legacy
- `missing`: no local plugin exists
- `blocked`: cannot be completed cleanly with current runtime primitives alone

## Implemented This Turn

- `device_reboot` now waits for cloud status to return to `running` instead of stopping at dispatch only.
- `device_soft_reset` now includes shell cleanup steps and waits for cloud status recovery.
- Added a formal SDK atomic action: `sdk.wait_cloud_status`.
- Added shared-state atomic actions:
  - `core.load_shared_optional`
  - `core.append_shared_unique`
  - `core.increment_shared_counter`
  - scoped shared keys via `scope` / `scope_value`
- `blogger_scrape` now persists latest scrape payload, appends unique candidates into a scoped pool, and increments a scrape counter.
- Added `config/x_ui.yaml` as the centralized X plugin UI contract.
- Added UI config atomic actions:
  - `core.load_ui_value`
  - `core.load_ui_selector`
  - `core.load_ui_scheme`
- `x_mobile_login` and `profile_clone` now consume selectors from `config/x_ui.yaml` instead of hardcoding core login/profile locators in plugin YAML.
- `dm_reply`, `follow_interaction`, `home_interaction`, and `quote_interaction` now consume shared X UI selectors/schemes instead of embedding app navigation constants in each plugin.
- Added business-strategy primitives for nurture-style workflows:
  - `core.check_daily_limit`
  - `core.increment_daily_counter`
  - `core.pick_weighted_keyword`
  - `core.is_text_blacklisted`
- Added business-store wrappers for migration semantics:
  - `core.save_blogger_candidate`
  - `core.get_blogger_candidate`
  - `core.mark_processed`
  - `core.check_processed`
- Added a first `nurture` plugin skeleton using daily quota checks and weighted keyword search browsing.
- Added candidate extraction and selection primitives:
  - `core.extract_timeline_candidates`
  - `core.extract_search_candidates`
  - `core.pick_candidate`
- Added DM extraction primitive:
  - `core.extract_dm_last_message`
- Added unread-DM navigation primitives:
  - `core.extract_unread_dm_targets`
  - `core.open_first_unread_dm`
- Added blogger scrape helpers:
  - `core.choose_blogger_search_query`
  - `core.derive_blogger_profile`
- Added follow-list primitives:
  - `core.extract_follow_targets`
  - `core.follow_visible_targets`
- Added multi-round blogger scrape primitives:
  - `core.collect_blogger_candidates`
  - `core.save_blogger_candidates`
- Added interaction text helpers:
  - `core.generate_dm_reply`
  - `core.generate_quote_text`
- Added candidate/open helpers:
  - `core.open_candidate`
  - `core.resolve_first_non_empty`
- Added follow planning and DM outbound verification helpers:
  - `core.plan_follow_rounds`
  - `core.extract_dm_last_outbound_message`

## Execution Plan

1. `done`: build X UI config and UI-loading atomic actions
2. `done`: move X-facing plugins from hardcoded selectors to config-backed selectors
3. `done`: add blogger/interaction/nurture business stores and extraction actions
4. `in_progress`: rebuild `blogger_scrape`, `quote_interaction`, `dm_reply`, `follow_interaction`, `home_interaction`, `nurture`

## Explicitly Deferred

- Media picking, gallery traversal, avatar/banner replacement, and crop-confirm flows are not being implemented in this wave by decision.

## Checklist

| Legacy task | Local plugin | Status | Required work to reach parity | Current blocker |
|---|---|---|---|---|
| `task_login.py` | `x_mobile_login` | `partial` | account source integration, broader UI variant handling, stronger post-login verification | no shared account-source contract in plugin runtime |
| `task_reboot_device.py` | `device_reboot` | `done` | none for minimum parity | none |
| `task_soft_reset.py` | `device_soft_reset` | `partial` | account removal UI, model rotation, proxy restore, post-reset business-state cleanup | missing model/proxy business policy layer |
| `task_scrape_blogger.py` | `blogger_scrape` | `partial` | scrape cooldown, multi-worker coordination, richer multi-candidate retention policy | current plugin now supports real search and multi-round collection, but pool management is still local JSON only |
| `task_clone_profile.py` | `profile_clone` | `partial` | avatar upload, gallery selection, stronger save verification | current flow edits name/bio only; no media replacement primitives yet |
| `task_follow_followers.py` | `follow_interaction` | `partial` | duplicate/limit handling across rounds, optional pre-clone, better stop policy | current flow can plan requested follow count, batch-follow visible targets, and persist follow results, but lacks stronger business-state control |
| `task_home_interaction.py` | `home_interaction` | `partial` | content classification, stat parsing, richer reaction execution, better stop policy | current flow can extract, select, open, and like timeline candidates, but does not execute full semantic interaction |
| `task_quote_intercept.py` | `quote_interaction` | `partial` | reply-search quality, stronger target de-dup, publish verification/history | current flow supports direct URL or `to:username` search, auto-generates quote text, and persists processed targets |
| `task_reply_dm.py` | `dm_reply` | `partial` | optional unlock, stronger reply generation, stronger send verification | current flow opens unread conversations, extracts the latest DM, can auto-generate a reply template, and records the latest outbound DM after send |
| `task_nurture.py` | `nurture` | `partial` | blogger assignment, content filtering, richer reaction execution, daily strategy richness | current plugin covers daily limit, weighted keyword search, candidate selection, candidate open, and basic like interaction, but not full interaction |

## Concrete Next Steps

1. Add extraction/generation primitives for:
   - post metadata/stat parsing
   - quote/reply text generation
   - stronger feed/follower loop controls
2. Rebuild business plugins in this order:
   - `quote_interaction`
   - `dm_reply`
   - `home_interaction`
   - `nurture`

## Items Not Fully Implementable Right Now

- `blogger_scrape`: current shared store is still a single local JSON file; it is not sufficient for concurrent multi-worker pool coordination.
- `profile_clone`: no stable atomic action exists for media picking, avatar upload confirmation, or profile edit save verification.
- `follow_interaction` / `home_interaction`: no reusable action currently exposes richer semantic filtering of posts beyond text candidate extraction.
- `quote_interaction`: processed-target persistence is still local JSON, not a concurrent-safe multi-worker store.
- `dm_reply`: no PIN-unlock primitive exists yet; outbound verification is still heuristic.
- `nurture`: counters, keyword scheduling, target extraction, candidate open, and basic like now exist, but semantic content filtering and richer interaction still do not.
