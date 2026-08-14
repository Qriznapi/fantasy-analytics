# Build The Database

This project does **not** store the main SQLite databases in GitHub. You build them locally.

Canonical local database paths:

- `data/ewc_2026_fantasy_compact.sqlite`
- `data/ti_2026_fantasy_compact.sqlite`

Legacy shadow path that may still exist in older copied workspaces:

- `data/db/ewc_2026_fantasy_compact.sqlite`

Active project code now treats `data/ewc_2026_fantasy_compact.sqlite` as the canonical path.

## 1. Environment setup

Requires Python 3.10+.

```bash
python -m venv .venv
pip install -r requirements.txt
```

## 2. Build the base tournament database

Primary source notebook:

- `notebooks/01_collect_to_sqlite.ipynb`

Open the notebook and run it top to bottom.

Use it to:

- collect EWC 2026 match data from Dotabuff
- enrich matches with OpenDota payloads
- create the compact SQLite schema
- populate the core tournament and player tables

Expected main output:

- `data/ewc_2026_fantasy_compact.sqlite`

## 2a. Bootstrap the TI 2026 database

The TI 2026 compact database is bootstrapped from the shared event template and then populated from live Liquipedia + OpenDota sources.

Bootstrap an empty TI database:

```bash
python scripts/build_ti2026_database.py --replace-existing
```

Bootstrap and immediately load all currently available TI 2026 matches:

```bash
python scripts/build_ti2026_database.py --replace-existing --load-live-data
```

If the TI database already exists and you only want to refresh it with newly finished maps:

```bash
python scripts/sync_ti2026_matches.py
python scripts/validate_ti2026_database.py
```

## 3. Backfill fantasy stat categories

If raw OpenDota payloads are already cached in the database, the safest rebuild path is:

```bash
python scripts/backfill_missing_fantasy_stats.py --source opendota --match-limit 0 --write-stage --use-cached-raw
python scripts/rebuild_backfilled_fantasy_points.py --source opendota --run-id cached_rebuild
python scripts/report_backfill_coverage.py
```

If cached raw payloads are missing, fetch them first:

```bash
python scripts/backfill_missing_fantasy_stats.py --source opendota --match-limit 0 --write-raw --write-stage --batch-size 25 --sleep-sec 0.75
python scripts/rebuild_backfilled_fantasy_points.py --source opendota --run-id fetched_rebuild
python scripts/report_backfill_coverage.py
```

## 4. Replay-derived enrichment for watchers and lotus

Replay-related scripts:

- `scripts/fetch_opendota_replay_manifest.py`
- `scripts/export_replay_manifest_from_db.py`
- `scripts/download_replays_from_manifest.py`
- `scripts/download_replay_via_browser.py`
- `scripts/run_replay_team_metric_batch.py`
- `scripts/import_replay_team_metrics.py`
- `scripts/merge_replay_metrics_into_compact_db.py`
- `scripts/reconcile_replay_player_metrics.py`
- `scripts/backfill_replay_metrics_for_event.py`
- `scripts/probe_stratz_replay_download.py`

Use these when you want the replay counters merged into the compact database and resolved down to player-level final rows:

```bash
python scripts/merge_replay_metrics_into_compact_db.py --target-db data/ewc_2026_fantasy_compact.sqlite
python scripts/reconcile_replay_player_metrics.py --db-path data/ewc_2026_fantasy_compact.sqlite
python scripts/sync_summary_backfill_columns.py --db-path data/ewc_2026_fantasy_compact.sqlite
python scripts/run_cleanup_consistency_pass.py --db-path data/ewc_2026_fantasy_compact.sqlite
python scripts/build_unified_fantasy_metrics_table.py --db-path data/ewc_2026_fantasy_compact.sqlite
```

Recommended event-scoped wrapper:

```bash
python scripts/backfill_replay_metrics_for_event.py --event-id ewc2026
python scripts/backfill_replay_metrics_for_event.py --event-id ti2026
```

Current operational note as of **August 14, 2026**:

- EWC 2026 replay backfill is already usable end-to-end.
- TI 2026 replay parsing helpers are ready, but public replay archives for the current TI `cluster=413` matches are not reliably downloadable from this environment.
- Because of that, TI `watchers_taken` / `lotus` may remain unfilled until `.dem.bz2` files can be obtained and dropped into `data/cache_ti_2026/replays/`.

## 5. Validate the result

```bash
python scripts/validate_project.py
python tests/regression_tests.py
```

For the TI-specific live database:

```bash
python scripts/validate_ti2026_database.py
```

## 6. What you should expect after a successful local build

Typical local snapshot used by this project:

- 157 stored EWC 2026 maps
- 1,570 player-map fantasy rows
- 120 player identity records
- 20+ public `analytics_*` views

## 7. Known source limits

Covered in the current compact database workflow:

- `first_blood`
- `stuns`
- `runes_grabbed`
- `wards_placed`
- `smokes_used`
- `camps_stacked`
- `courier_kills`
- `roshan_kills`
- `watchers_taken` (EWC yes; TI depends on replay availability)
- `lotus` (EWC yes; TI depends on replay availability)
- `tormentor_kills`

For interpretation details, use:

- [DATA_WORKFLOW.md](DATA_WORKFLOW.md)
- [DATA_SOURCES.md](DATA_SOURCES.md)
- [database_guide.md](database_guide.md)
