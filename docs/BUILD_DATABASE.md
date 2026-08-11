# Build The Database

This project does **not** store the main SQLite databases in GitHub. You build them locally.

Target database path:

- `data/ewc_2026_fantasy_compact.sqlite`

Optional compatible path:

- `data/db/ewc_2026_fantasy_compact.sqlite`

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

## 4. Optional replay-derived enrichment

Optional replay-related scripts:

- `scripts/fetch_opendota_replay_manifest.py`
- `scripts/download_replays_from_manifest.py`
- `scripts/run_replay_team_metric_batch.py`
- `scripts/import_replay_team_metrics.py`
- `scripts/merge_replay_metrics_into_compact_db.py`

Use these only if you want replay-derived team-slot metrics merged into the compact database.

## 5. Validate the result

```bash
python scripts/validate_project.py
python tests/regression_tests.py
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
- `tormentor_kills`

Still source-limited in the main compact database:

- `watchers_taken`
- `lotus`

For interpretation details, use:

- [DATA_WORKFLOW.md](DATA_WORKFLOW.md)
- [DATA_SOURCES.md](DATA_SOURCES.md)
- [database_guide.md](database_guide.md)
