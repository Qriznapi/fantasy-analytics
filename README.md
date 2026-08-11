# Dota 2 Fantasy Analytics - EWC 2026

An end-to-end analytics project for **Esports World Cup 2026 Dota 2 fantasy data**. It combines a compact SQLite warehouse, fantasy scoring profiles, reliability estimates, banner optimization, source-aware backfills, and a database-first fact agent.

The repository is intentionally kept **database-free** for GitHub. Large SQLite artifacts are built locally from the provided notebooks and scripts.

## Project snapshot

Current local build snapshot:

- **157** stored EWC 2026 maps
- **1,570** player-map fantasy rows
- **120** player identity records
- **20+** public `analytics_*` SQLite views
- full replay-derived coverage for **157 / 157** maps
- reliability and optimizer outputs for both players and aggregated role slots
- notebook, dashboard, and deterministic query interface on top of the same database

The guiding rule is simple: if a fact exists in SQLite, answers come from the database; if not, it is treated as a data-collection problem instead of being guessed.

## What this project does

- stores tournament, player, roster, role, fantasy, and provenance data in one SQLite file built locally
- calculates fantasy outputs for players and role aggregates such as `core_pair`, `mid`, and `support_pair`
- estimates fantasy reliability using ceiling-aware features and temporal validation
- ranks stats, banners, and player options for different fantasy setups
- supports controlled enrichment from OpenDota and future STRATZ backfills
- exposes a fact-oriented query layer for notebook and agent-style usage

## Repository structure

```text
fantasy-analytics/
|-- app/
|   `-- ewc_fantasy_dashboard.py
|-- dashboard/
|   `-- app.py
|-- data/
|   `-- .gitkeep
|-- notebooks/
|   |-- 01_collect_to_sqlite.ipynb
|   |-- 02_fact_agent.ipynb
|   `-- ewc2026_fact_agent_demo.ipynb
|-- scripts/
|   |-- backfill_missing_fantasy_stats.py
|   |-- merge_replay_metrics_into_compact_db.py
|   |-- rebuild_backfilled_fantasy_points.py
|   |-- report_replay_backfill_status.py
|   |-- report_backfill_coverage.py
|   `-- validate_project.py
|-- src/
|   |-- ewc_fact_agent_tools.py
|   |-- fantasy_banner_optimizer.py
|   |-- fantasy_profile_constructor.py
|   `-- enrichment/
|-- docs/
|   |-- ARCHITECTURE.md
|   |-- MODELING.md
|   |-- DATA_SOURCES.md
|   |-- BUILD_DATABASE.md
|   |-- database_guide.md
|   |-- REPLAY_DATABASE_GUIDE.md
|   `-- DATA_WORKFLOW.md
`-- tests/
```

## Quick start

Requires **Python 3.10+**.

```bash
python -m venv .venv
pip install -r requirements.txt
```

Then build the local SQLite database:

1. Open and run `notebooks/01_collect_to_sqlite.ipynb`.
2. Then run:

   ```bash
   python scripts/backfill_missing_fantasy_stats.py --source opendota --match-limit 0 --write-stage --use-cached-raw
   python scripts/rebuild_backfilled_fantasy_points.py --source opendota --run-id cached_rebuild
   python scripts/validate_project.py
   ```

If you want the full step-by-step workflow, use [docs/BUILD_DATABASE.md](docs/BUILD_DATABASE.md).

Useful entry points:

```bash
python tests/regression_tests.py
python scripts/report_backfill_coverage.py
streamlit run dashboard/app.py
```

The codebase resolves the compact database from either of these locations after you build it locally:

- `data/ewc_2026_fantasy_compact.sqlite`
- `data/db/ewc_2026_fantasy_compact.sqlite`

This makes the same project folder usable both in the repository-style layout and in the earlier nested workspace layout.

## Where to start

- Want to understand the system: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Want to build the database locally: [docs/BUILD_DATABASE.md](docs/BUILD_DATABASE.md)
- Want to query the database: [docs/database_guide.md](docs/database_guide.md)
- Want to rebuild or backfill data: [docs/DATA_WORKFLOW.md](docs/DATA_WORKFLOW.md)
- Want source caveats and coverage notes: [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md)
- Want scoring and modeling logic: [docs/MODELING.md](docs/MODELING.md)
- Want a human-facing fantasy recommendation guide: [docs/EWC2026_Fantasy_Selection_Guide.docx](docs/EWC2026_Fantasy_Selection_Guide.docx)

## Main analytical surfaces

For most analysis, use the public SQLite views rather than internal tables.

Most useful views:

- `analytics_player_maps`
- `analytics_team_role_maps`
- `analytics_reliable_players`
- `analytics_reliable_role_slots`
- `analytics_optimizer_players`
- `analytics_optimizer_role_slots`
- `analytics_rosters`
- `analytics_sources`
- `analytics_fantasy_backfill_coverage`
- `analytics_fantasy_backfill_sanity`
- `analytics_replay_team_metrics_long`
- `analytics_replay_team_metrics_wide`
- `analytics_replay_match_coverage`
- `analytics_replay_metric_summary`

## Notebook and agent usage

The main interactive notebook is [notebooks/ewc2026_fact_agent_demo.ipynb](notebooks/ewc2026_fact_agent_demo.ipynb).

It supports two path modes from the first configuration cell:

- `project` for the normal repository layout
- `flat_colab` for flat Google Colab uploads into `/content`

The deterministic query layer lives in `src/ewc_fact_agent_tools.py` and can answer database-backed questions without depending on an external LLM.

## Data status

Backfilled in the current compact database:

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

Additional replay-derived coverage artifacts are stored separately and can be merged later when needed.

`analytics_fantasy_backfill_coverage` is the authoritative place to distinguish real zero values from unsupported or source-missing metrics.

Replay-derived team-slot coverage is usually stored separately in:

- `data/replay_team_metrics_ewc2026_complete157.sqlite`

If you want those tables copied into the main compact database, use:

```bash
python scripts/merge_replay_metrics_into_compact_db.py \
  --target-db data/ewc_2026_fantasy_compact.sqlite
```

## GitHub policy

The repository should not contain:

- `data/ewc_2026_fantasy_compact.sqlite`
- `data/db/ewc_2026_fantasy_compact.sqlite`
- replay-only SQLite artifacts
- backup SQLite files

What is safe to keep in GitHub:

- notebooks
- source code
- scripts
- markdown documentation
- lightweight manifests such as replay manifest JSON files
