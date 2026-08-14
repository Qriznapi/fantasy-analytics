# Dota 2 Fantasy Analytics - EWC 2026 + TI 2026

An end-to-end analytics project for **Esports World Cup 2026** and the live **The International 2026** fantasy workflow. It combines compact SQLite warehouses, fantasy scoring profiles, reliability estimates, banner optimization, source-aware backfills, and a database-first fact agent.

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
- calculates fantasy outputs for players and role-slot aggregates such as `core_pair`, `mid_single`, and `support_pair`
- estimates fantasy reliability using ceiling-aware features and temporal validation
- includes a newer prediction-foundation layer built from map-level and generic series-level targets for cleaner baseline evaluation
- includes a newer foundation-first reliability layer for player and role-slot recommendations built on top of that target framework
- includes a newer foundation-first optimizer layer for player and role-slot recommendations built on top of the reliability layer
- includes a newer `optimizer_v2` layer that now acts as the default recommendation surface for player and role-slot banner choices
- includes a first ridge-based prediction layer for stronger model-based comparisons on the same split scenarios
- includes a production prediction layer that chooses the strongest stored model per target/split and exposes it as the default model-based ranking surface
- includes a Monte Carlo layer on top of the production prediction surface for ranking-stability and top-finish probability estimates
- includes a unified evaluator layer that normalizes prediction, reliability, optimizer, and simulation surfaces into one comparison registry
- includes a banner rescoring layer that re-ranks players and role slots with weighted production-prediction and Monte Carlo signals
- includes a practical decision layer with conservative, balanced, and aggressive banner-pick profiles plus ready-made role-slot lineups
- ranks stats, banners, and player options for different fantasy setups
- supports controlled enrichment from OpenDota, replay-derived backfills, and limited STRATZ probing
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
|-- reports/
|   |-- banner_decision_scorecard.md
|   |-- banner_rescoring_scorecard.md
|   |-- optimizer_v2_scorecard.md
|   |-- prediction_foundation_scorecard.md
|   |-- prediction_monte_carlo_scorecard.md
|   |-- prediction_production_scorecard.md
|   |-- prediction_ridge_scorecard.md
|   |-- unified_evaluation_scorecard.md
|   `-- reliability_foundation_scorecard.md
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

If you want the full step-by-step workflow for either EWC or TI, use [docs/BUILD_DATABASE.md](docs/BUILD_DATABASE.md).

Useful entry points:

```bash
python tests/regression_tests.py
python scripts/report_backfill_coverage.py
streamlit run dashboard/app.py
```

The canonical local database path is:

- `data/ewc_2026_fantasy_compact.sqlite`
- `data/ti_2026_fantasy_compact.sqlite`

Some older scripts or copied workspaces may still contain a legacy shadow copy at `data/db/ewc_2026_fantasy_compact.sqlite`, but the active project code now treats `data/ewc_2026_fantasy_compact.sqlite` as the primary path.

## Where to start

- Want to understand the system: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Want to build the database locally: [docs/BUILD_DATABASE.md](docs/BUILD_DATABASE.md)
- Want to query the database: [docs/database_guide.md](docs/database_guide.md)
- Want to rebuild or backfill data: [docs/DATA_WORKFLOW.md](docs/DATA_WORKFLOW.md)
- Want source caveats and coverage notes: [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md)
- Want scoring and modeling logic: [docs/MODELING.md](docs/MODELING.md)
- Want the current report bundle: [reports](reports)
- Want the baseline target comparison table: [docs/PREDICTION_FOUNDATION_SCORECARD.md](docs/PREDICTION_FOUNDATION_SCORECARD.md)
- Want the new reliability comparison table: [docs/RELIABILITY_FOUNDATION_SCORECARD.md](docs/RELIABILITY_FOUNDATION_SCORECARD.md)
- Want the optimizer recommendation comparison table: [docs/OPTIMIZER_FOUNDATION_SCORECARD.md](docs/OPTIMIZER_FOUNDATION_SCORECARD.md)
- Want the current optimizer-v2 comparison table: [reports/optimizer_v2_scorecard.md](reports/optimizer_v2_scorecard.md)
- Want the current ridge prediction comparison table: [reports/prediction_ridge_scorecard.md](reports/prediction_ridge_scorecard.md)
- Want the current production prediction table: [reports/prediction_production_scorecard.md](reports/prediction_production_scorecard.md)
- Want the current Monte Carlo stability table: [reports/prediction_monte_carlo_scorecard.md](reports/prediction_monte_carlo_scorecard.md)
- Want the unified model/recommendation comparison table: [reports/unified_evaluation_scorecard.md](reports/unified_evaluation_scorecard.md)
- Want banner rescoring on top of prediction + Monte Carlo: [reports/banner_rescoring_scorecard.md](reports/banner_rescoring_scorecard.md)
- Want practical conservative/balanced/aggressive lineup choices: [reports/banner_decision_scorecard.md](reports/banner_decision_scorecard.md)
- Want metric explanations and formulas: [docs/METRICS_REFERENCE.md](docs/METRICS_REFERENCE.md)
- Want a human-facing fantasy recommendation guide in Markdown: [docs/EWC2026_Fantasy_Selection_Guide.md](docs/EWC2026_Fantasy_Selection_Guide.md)
- Want a human-facing fantasy recommendation guide: [docs/EWC2026_Fantasy_Selection_Guide.docx](docs/EWC2026_Fantasy_Selection_Guide.docx)

## Main analytical surfaces

For most analysis, use the public SQLite views rather than internal tables.

Most useful views:

- `analytics_player_maps`
- `analytics_team_role_maps`
- `analytics_reliable_players_foundation`
- `analytics_reliable_role_slots_foundation`
- `analytics_reliability_foundation_backtest`
- `analytics_optimizer_players_foundation`
- `analytics_optimizer_role_slots_foundation`
- `analytics_optimizer_foundation_evaluation`
- `analytics_optimizer_v2_players`
- `analytics_optimizer_v2_role_slots`
- `analytics_optimizer_v2_evaluation`
- `analytics_prediction_ridge_evaluation`
- `analytics_prediction_production_model_choices`
- `analytics_prediction_production_players`
- `analytics_prediction_production_role_slots`
- `analytics_prediction_monte_carlo_players`
- `analytics_prediction_monte_carlo_role_slots`
- `analytics_banner_rescoring_players`
- `analytics_banner_rescoring_role_slots`
- `analytics_banner_decision_players`
- `analytics_banner_decision_role_slots`
- `analytics_banner_decision_lineups`
- `analytics_unified_evaluation_summary`
- `analytics_unified_evaluation_leaderboard`
- `analytics_metric_definitions`
- `analytics_rosters`
- `analytics_sources`
- `analytics_fantasy_backfill_coverage`
- `analytics_fantasy_backfill_sanity`
- `analytics_replay_team_metrics_long`
- `analytics_replay_team_metrics_wide`
- `analytics_replay_match_coverage`
- `analytics_replay_metric_summary`

## Notebook and agent usage

The main interactive notebooks are:

- [notebooks/02_fact_agent.ipynb](notebooks/02_fact_agent.ipynb)
- [notebooks/ewc2026_fact_agent_demo.ipynb](notebooks/ewc2026_fact_agent_demo.ipynb)

It supports two path modes from the first configuration cell:

- `project` for the normal repository layout
- `flat_colab` for flat Google Colab uploads into `/content`

It also supports tournament switching from the same first configuration cell:

- `NOTEBOOK_EVENT_ID = "ti2026"` for the live TI 2026 database
- `NOTEBOOK_EVENT_ID = "ewc2026"` for the historical EWC 2026 database

The current demo notebook is wired to the newer analytical surfaces as well:

- role-slot keys `core_pair`, `mid_single`, `support_pair`
- stage-aware fields such as `stage_name`, `stage_bucket`, `is_group_stage_bucket`, `is_main_playoff`
- coverage views such as `analytics_fantasy_backfill_coverage`
- replay summary views such as `analytics_replay_metric_summary` and `analytics_replay_match_coverage`
- resolved replay-to-player views such as `analytics_replay_player_metrics_long`, `analytics_replay_player_metrics_wide`, and `analytics_replay_player_metric_summary`

The deterministic query layer lives in `src/ewc_fact_agent_tools.py` and can answer database-backed questions without depending on an external LLM.

The default optimizer surface now points to `optimizer_v2`; the older foundation optimizer remains available as an explicit comparison/reference path.

The default model-based prediction surface now points to the production champion layer, which reuses the strongest stored model family per target/split instead of forcing one global model everywhere.

On top of that, the Monte Carlo layer estimates ranking stability and top-finish probabilities under repeated simulated tournament outcomes.

The optimizer and prediction layers also store direct backtest/evaluation surfaces in SQLite, so recommendation quality can be queried with metrics such as MAE, Spearman, Top-k overlap, NDCG, and regret-at-1.

The unified evaluator layer sits above those surfaces and exposes one normalized comparison registry for prediction, reliability, optimizer, and simulation outputs.

For notebook exploration, the fastest way to interpret stored scores is:

1. query one of the foundation views;
2. inspect `low_estimate`, `expected_estimate`, `high_estimate`, and `confidence_label`;
3. open `metric_definitions(...)` or `analytics_metric_definitions` when a feature name needs explanation.

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
- `watchers_taken` (fully resolved in EWC, source-blocked for current TI replay cache)
- `lotus` (fully resolved in EWC, source-blocked for current TI replay cache)
- `tormentor_kills`

`analytics_fantasy_backfill_coverage` is the authoritative place to distinguish real zero values from unsupported or source-missing metrics.

Replay-derived provenance now exists in both layers:

- canonical player-level final rows in `fantasy_player_map_stat_points` for `watchers_taken` and `lotus` where replay files were successfully processed
- resolved replay provenance in `replay_player_metric_resolved`
- raw replay slot provenance in `replay_team_metric_final`

Current practical split:

- EWC 2026: replay-derived `watchers_taken` / `lotus` are fully loaded into the compact database
- TI 2026: the replay wrapper and browser/STRATZ probes are in place, but public `.dem.bz2` downloads are currently blocked, so those two metrics may still remain zero or source-missing until replay archives become available

If you want to re-run the replay-to-player reconciliation after importing or refreshing replay slot data, use:

```bash
python scripts/reconcile_replay_player_metrics.py
```
