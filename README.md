# Dota 2 Fantasy Analytics - EWC 2026

An end-to-end analytics project for **Esports World Cup 2026 Dota 2 fantasy data**. It combines a compact SQLite warehouse, fantasy scoring profiles, reliability estimates, banner optimization, source-aware backfills, and a database-first fact agent.

## Project snapshot

- **157** stored EWC 2026 maps
- **1,570** player-map fantasy rows
- **120** player identity records
- **16** public `analytics_*` SQLite views
- reliability and optimizer outputs for both players and aggregated role slots
- notebook, dashboard, and deterministic query interface on top of the same database

The guiding rule is simple: if a fact exists in SQLite, answers come from the database; if not, it is treated as a data-collection problem instead of being guessed.

## What this project does

- stores tournament, player, roster, role, fantasy, and provenance data in one SQLite file
- calculates fantasy outputs for players and role aggregates such as `core_pair`, `mid`, and `support_pair`
- estimates fantasy reliability using ceiling-aware features and temporal validation
- ranks stats, banners, and player options for different fantasy setups
- supports controlled enrichment from OpenDota and future STRATZ backfills
- exposes a fact-oriented query layer for notebook and agent-style usage

## Repository structure

```text
fantasy-analytics/
|-- data/
|   `-- ewc_2026_fantasy_compact.sqlite
|-- notebooks/
|   `-- ewc2026_fact_agent_demo.ipynb
|-- scripts/
|   |-- backfill_missing_fantasy_stats.py
|   |-- rebuild_backfilled_fantasy_points.py
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
|   |-- DATABASE_GUIDE.md
|   `-- DATA_WORKFLOW.md
`-- tests/
```

## Quick start

Requires **Python 3.10+**.

```bash
python -m venv .venv
pip install -r requirements.txt
python scripts/validate_project.py
```

Useful entry points:

```bash
python tests/regression_tests.py
python scripts/report_backfill_coverage.py
streamlit run dashboard/app.py
```

## Where to start

- Want to understand the system: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Want to query the database: [docs/DATABASE_GUIDE.md](docs/DATABASE_GUIDE.md)
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

## Notebook and agent usage

The main interactive notebook is [notebooks/ewc2026_fact_agent_demo.ipynb](notebooks/ewc2026_fact_agent_demo.ipynb).

It supports two path modes from the first configuration cell:

- `project` for the normal repository layout
- `flat_colab` for flat Google Colab uploads into `/content`

The deterministic query layer lives in `src/ewc_fact_agent_tools.py` and can answer database-backed questions without depending on an external LLM.

## Data status

Backfilled in the current pipeline:

- `first_blood`
- `stuns`
- `runes_grabbed`
- `wards_placed`
- `smokes_used`
- `camps_stacked`
- `courier_kills`
- `roshan_kills`
- `tormentor_kills`

Still source-blocked in the current environment:

- `watchers_taken`
- `lotus`

`analytics_fantasy_backfill_coverage` is the authoritative place to distinguish real zero values from unsupported or source-missing metrics.

## Why this reads well in a portfolio

This repository is shaped as a full analytics product rather than just a notebook dump:

- a compact reusable database
- documented data lineage
- deterministic analytical interface
- reproducible rebuild scripts
- explicit handling of missing and uncertain source fields
- fantasy-specific modeling layered on top of raw esports data
