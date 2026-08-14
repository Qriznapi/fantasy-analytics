# Data workflow

This document is the practical guide for collecting, rebuilding, and checking project data.

Repository note:

- the GitHub version of the project does not include the built SQLite databases
- build the local database first by following [BUILD_DATABASE.md](BUILD_DATABASE.md)

## When to use this document

Use it if you want to:

- rebuild fantasy stat rows from already cached payloads
- fetch missing OpenDota payloads and stage new rows
- reconcile replay slot counters into player-level `watchers_taken` / `lotus`
- check whether zeros are real or caused by source limitations
- understand what is still blocked by missing source support

For broader system design, use [ARCHITECTURE.md](ARCHITECTURE.md). For query examples, use [database_guide.md](database_guide.md).

## Pipeline in one view

```mermaid
flowchart LR
    A["External source"] --> B["raw_match_source_payloads"]
    B --> C["stg_player_match_enriched_stats"]
    C --> D["fantasy_player_map_stat_points"]
    D --> E["fantasy_player_map_scores"]
    E --> F["analytics_* views"]
```

## Main tables

Core analysis:

- `matches`
- `player_identity_registry`
- `fantasy_player_map_scores`
- `player_game_fantasy_summary`
- `fantasy_scoring_stat_catalog`

Backfill and provenance:

- `raw_match_source_payloads`
- `raw_match_source_status`
- `stg_player_match_enriched_stats`
- `fantasy_stat_backfill_audit`
- `replay_team_metric_final`
- `replay_player_metric_resolved`

## Most common workflows

### 1. Rebuild from cached raw payloads

Use this when the database already contains the required OpenDota raw JSON and you want the safest reproducible rebuild.

```bash
python scripts/backfill_missing_fantasy_stats.py --source opendota --match-limit 0 --write-stage --use-cached-raw
python scripts/rebuild_backfilled_fantasy_points.py --source opendota --run-id cached_rebuild
python scripts/report_backfill_coverage.py
```

This is the preferred workflow for routine maintenance.

### 2. Fetch and stage new OpenDota payloads

Use this when cached raw payloads are missing.

```bash
python scripts/backfill_missing_fantasy_stats.py --source opendota --match-limit 0 --write-raw --write-stage --batch-size 25 --sleep-sec 0.75
python scripts/rebuild_backfilled_fantasy_points.py --source opendota --run-id fetched_rebuild
python scripts/report_backfill_coverage.py
```

### 2a. Incrementally refresh TI 2026

Use this when TI 2026 is live and you want to pull newly completed maps into the dedicated TI database.

```bash
python scripts/sync_ti2026_matches.py --write-status-report
python scripts/validate_ti2026_database.py
```

This workflow:

- refreshes the current TI 2026 match list from OpenDota
- re-pulls all currently available TI payloads safely into the TI database
- refreshes stage/backfill/profile layers
- records the run in `event_sync_runs` and `event_sync_match_log`
- writes a compact markdown report to `reports/ti2026_status.md`

### 3. Retry only failed fetches

```bash
python scripts/backfill_missing_fantasy_stats.py --source opendota --retry-errors-only --write-raw --write-stage --batch-size 5 --sleep-sec 0.75
```

### 4. Check whether STRATZ is available

```bash
python scripts/backfill_missing_fantasy_stats.py --source stratz --match-limit 1 --write-raw --schema-probe
```

This is only an availability probe. The project now also contains a browser-assisted STRATZ probe for replay-related metadata, but that path is still exploratory and does not yet produce final player-stat rows by itself.

Useful exploratory helpers:

```bash
python scripts/probe_stratz_replay_download.py --help
python scripts/download_replay_via_browser.py --help
```

### 5. Reconcile replay-derived `watchers_taken` and `lotus`

Use this after replay slot metrics are already present in the compact database.

```bash
python scripts/reconcile_replay_player_metrics.py --db-path data/ewc_2026_fantasy_compact.sqlite
python scripts/sync_summary_backfill_columns.py --db-path data/ewc_2026_fantasy_compact.sqlite
python scripts/run_cleanup_consistency_pass.py --db-path data/ewc_2026_fantasy_compact.sqlite
python scripts/build_unified_fantasy_metrics_table.py --db-path data/ewc_2026_fantasy_compact.sqlite
```

This path does four things:

- matches replay `team_slot` to OpenDota `player_slot`
- resolves replay rows to concrete `account_id`
- copies canonical player-level `watchers_taken` / `lotus` rows into `fantasy_player_map_stat_points`
- refreshes summary and unified analytics layers

## What the scripts do

### `scripts/backfill_missing_fantasy_stats.py`

Collects source payloads and writes staged per-player stat rows.

Main options:

- `--source opendota|stratz`
- `--match-limit 0`
- `--write-raw`
- `--write-stage`
- `--use-cached-raw`
- `--retry-errors-only`
- `--schema-probe`

### `scripts/rebuild_backfilled_fantasy_points.py`

Reads staged rows, rewrites the corresponding rows in `fantasy_player_map_stat_points`, and refreshes dependent stored outputs.

### `scripts/report_backfill_coverage.py`

Summarizes:

- raw payload coverage
- staged extraction coverage
- final fantasy stat coverage
- source metadata
- sanity warnings

### `scripts/validate_project.py`

Runs the broader validation pass and regression checks.

## Notebook layouts

`notebooks/ewc2026_fact_agent_demo.ipynb` supports two execution layouts:

- `project` for the normal repository layout with `src/` and `data/`
- `flat_colab` for flat uploads into Google Colab such as `/content`

The current demo notebook also includes ready-to-run blocks for:

- role-slot analysis with `core_pair`, `mid_single`, `support_pair`
- stage-aware inspection using `analytics_player_maps`
- backfill coverage inspection using `analytics_fantasy_backfill_coverage`
- replay-derived coverage inspection using `analytics_replay_metric_summary` and `analytics_replay_match_coverage`
- replay-to-player inspection using `analytics_replay_player_metrics_wide`

Optional manual overrides:

- `CUSTOM_PROJECT_ROOT`
- `CUSTOM_SRC_DIR`
- `CUSTOM_DB_PATH`

Tournament switch:

- `NOTEBOOK_EVENT_ID = "ti2026"` uses the live TI database
- `NOTEBOOK_EVENT_ID = "ewc2026"` uses the historical EWC database

## How to read coverage correctly

The two key views are:

- `analytics_fantasy_backfill_coverage`
- `analytics_fantasy_backfill_sanity`

Important `analytics_fantasy_backfill_coverage` columns:

- `preferred_source`
- `coverage_status`
- `has_stage_evidence`
- `is_row_complete`
- `zero_raw_rows`
- `nonzero_raw_rows`
- `sparse_zero_rows`
- `source_missing_rows`
- `objective_derived_rows`
- `clamped_rows`

Practical interpretation:

- `has_stage_evidence = 1` means the current pipeline actually extracted or derived that stat
- `is_row_complete = 1` means row coverage is complete for the chosen source strategy
- `sparse_zero_rows > 0` means zeros may come from omitted zero-valued keys
- `source_missing_rows > 0` means the source payload did not expose the field where expected
- `objective_derived_rows > 0` means the metric was reconstructed from event/objective data

## Real zero vs missing data

### Real zero

The source supports the metric and the player truly recorded zero.

### Sparse-key zero

The source supports the metric, but a zero often appears as an omitted key instead of an explicit value.

Current example:

- `smokes_used`

### Source-blocked metric

The current environment still has no confirmed extractor for the metric.

## Current status on August 14, 2026

Covered by the current backfill pipeline:

- `first_blood`
- `stuns`
- `runes_grabbed`
- `wards_placed`
- `smokes_used`
- `camps_stacked`
- `courier_kills`
- `roshan_kills`
- `watchers_taken`
- `lotus`
- `tormentor_kills`

Still approximate rather than exact:

- `tormentor_kills`

Reason:

- replay counters do not expose a trustworthy last-hit owner for Tormentor in the stored dataset
- the project therefore keeps the existing OpenDota objective-share approximation for player-level `tormentor_kills`

Current TI replay note:

- the TI 2026 database and replay cache layout are ready
- replay manifest export works for TI maps
- public `.dem.bz2` retrieval for the current TI replay host remains blocked in this environment
- until those archives are available, `watchers_taken` / `lotus` in the TI database should be interpreted through `analytics_fantasy_backfill_coverage` rather than assumed complete

## Safe operating habits

- create a backup before major rebuilds
- prefer cached rebuilds when possible
- treat `analytics_fantasy_backfill_coverage` as the source-of-truth for completeness
- rerun validation after changing source mappings or rebuild logic
- if you maintain a separate Colab copy of the notebook, sync it back into the repository after edits
