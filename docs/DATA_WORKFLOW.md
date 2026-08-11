# Data workflow

This document is the practical guide for collecting, rebuilding, and checking project data.

## When to use this document

Use it if you want to:

- rebuild fantasy stat rows from already cached payloads
- fetch missing OpenDota payloads and stage new rows
- check whether zeros are real or caused by source limitations
- understand what is still blocked by missing source support

For broader system design, use [ARCHITECTURE.md](ARCHITECTURE.md). For query examples, use [DATABASE_GUIDE.md](DATABASE_GUIDE.md).

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

### 3. Retry only failed fetches

```bash
python scripts/backfill_missing_fantasy_stats.py --source opendota --retry-errors-only --write-raw --write-stage --batch-size 5 --sleep-sec 0.75
```

### 4. Check whether STRATZ is available

```bash
python scripts/backfill_missing_fantasy_stats.py --source stratz --match-limit 1 --write-raw --schema-probe
```

This is only an availability probe. Full live STRATZ backfill still depends on token access and extractor completion.

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

Optional manual overrides:

- `CUSTOM_PROJECT_ROOT`
- `CUSTOM_SRC_DIR`
- `CUSTOM_DB_PATH`

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

Current examples:

- `watchers_taken`
- `lotus`

## Current status on August 11, 2026

Covered by the current backfill pipeline:

- `first_blood`
- `stuns`
- `runes_grabbed`
- `wards_placed`
- `smokes_used`
- `camps_stacked`
- `courier_kills`
- `roshan_kills`
- `tormentor_kills`

Still blocked:

- `watchers_taken`
- `lotus`

Reason:

- official STRATZ GraphQL requires a bearer token
- no working token is configured in the current environment

## Safe operating habits

- create a backup before major rebuilds
- prefer cached rebuilds when possible
- treat `analytics_fantasy_backfill_coverage` as the source-of-truth for completeness
- rerun validation after changing source mappings or rebuild logic
- if you maintain a separate Colab copy of the notebook, sync it back into the repository after edits
