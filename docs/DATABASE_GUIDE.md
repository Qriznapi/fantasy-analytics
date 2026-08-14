# Database guide

Database files after local build:

- `data/ewc_2026_fantasy_compact.sqlite`
- `data/ti_2026_fantasy_compact.sqlite`

For ordinary analysis, prefer the public views with the `analytics_` prefix rather than querying implementation tables directly.

## Main public views

- `analytics_player_maps` - fantasy score for each player-map under the current default profile.
- `analytics_team_role_maps` - team/map role-slot aggregation with `core_pair`, `mid_single`, and `support_pair` rollups.
- `analytics_reliable_players_foundation` - default foundation-based player reliability output with low/expected/high heuristic bands.
- `analytics_reliable_role_slots_foundation` - default foundation-based role-slot reliability output for `core_pair`, `mid_single`, `support_pair`.
- `analytics_optimizer_players_foundation` - older foundation-based optimizer output for players, kept as a comparison surface.
- `analytics_optimizer_role_slots_foundation` - older foundation-based optimizer output for role slots, kept as a comparison surface.
- `analytics_optimizer_foundation_backtest` - stored optimizer backtest rows with predicted vs actual playoff-style outcomes.
- `analytics_optimizer_foundation_evaluation` - aggregate optimizer quality metrics such as MAE, Spearman, overlap, NDCG, and regret.
- `analytics_optimizer_v2_players` - current default optimizer output for players.
- `analytics_optimizer_v2_role_slots` - current default optimizer output for role slots.
- `analytics_optimizer_v2_evaluation` - backtest metrics for the current default optimizer-v2 layer.
- `analytics_prediction_ridge_evaluation` - first ridge-based prediction model evaluation layer on top of the generic target dataset.
- `analytics_prediction_ridge_tuning` - stored alpha-tuning diagnostics for the tuned ridge layer.
- `analytics_prediction_quantile_evaluation` - linear quantile model evaluation layer with q25/q50/q75/q90 diagnostics.
- `analytics_prediction_gbdt_evaluation` - ranking-oriented boosted-tree experiment evaluation layer.
- `analytics_prediction_gbdt_importance` - per-run feature-importance summary for the boosted-tree experiment.
- `analytics_prediction_production_model_choices` - current champion-model choice per target/split.
- `analytics_prediction_production_players` - default model-based ranking surface for players.
- `analytics_prediction_production_role_slots` - default model-based ranking surface for role slots.
- `analytics_prediction_monte_carlo_players` - Monte Carlo ranking-stability surface for players.
- `analytics_prediction_monte_carlo_role_slots` - Monte Carlo ranking-stability surface for role slots.
- `analytics_banner_rescoring_players` - banner rescoring surface for players using weighted production-prediction and Monte Carlo signals.
- `analytics_banner_rescoring_role_slots` - banner rescoring surface for role slots using weighted production-prediction and Monte Carlo signals.
- `analytics_banner_decision_players` - practical risk-profile player decisions.
- `analytics_banner_decision_role_slots` - practical risk-profile role-slot decisions.
- `analytics_banner_decision_lineups` - ready-made three-team lineups for conservative, balanced, and aggressive profiles.
- `analytics_unified_evaluation_metrics` - normalized metric rows across prediction, reliability, optimizer, and simulation layers.
- `analytics_unified_evaluation_summary` - one pivoted evaluation row per stored surface/run.
- `analytics_unified_evaluation_leaderboard` - recommended comparison view ordered by comparable backtest quality first.
- `analytics_metric_definitions` - reference table explaining what each stored metric means and how it is calculated.
- `analytics_rosters` - official names and positions from the stored roster registry.
- `analytics_ti2026_teams` - TI 2026 qualification data stored by the project.
- `analytics_sources` - source provenance and cache status.
- `analytics_scoring_formula` - active fantasy scoring and banner-formula rows.
- `analytics_scoring_titles` - active coach-title prefix/suffix rules for the default profile.
- `analytics_reliability_foundation_backtest` - stored foundation backtest rows.
- `analytics_db_objects` - catalog of recommended database objects.
- `analytics_fantasy_backfill_coverage` - source coverage and zero-value semantics for backfilled stats.
- `analytics_fantasy_backfill_sanity` - data-quality warnings for the backfill layer.
- `analytics_replay_team_metrics_long` - replay-derived team-slot metrics in long format.
- `analytics_replay_team_metrics_wide` - replay-derived team-slot metrics in wide format.
- `analytics_replay_match_coverage` - replay coverage summary by match.
- `analytics_replay_metric_summary` - replay coverage summary by metric.
- `analytics_replay_player_metrics_long` - replay-derived counters resolved to player/account rows.
- `analytics_replay_player_metrics_wide` - one resolved replay row per player-map.
- `analytics_replay_player_metric_summary` - summary of resolved replay player metrics.

## Most useful implementation tables

Only query these directly when you need source or rebuild detail:

- `fantasy_player_map_stat_points`
- `fantasy_player_map_scores`
- `fantasy_scoring_profile_titles`
- `player_game_fantasy_summary`
- `replay_team_metric_events`
- `replay_team_metric_final`
- `replay_player_metric_resolved`
- `raw_match_source_payloads`
- `raw_match_source_status`
- `stg_player_match_enriched_stats`
- `fantasy_stat_backfill_audit`
- `fantasy_scoring_stat_catalog`

## Example SQL

### Top fantasy maps for position 1 among stored TI 2026 qualified teams

```sql
SELECT fantasy_score, official_name, team_name, hero_name, match_id,
       qualification_path, ti_region
FROM analytics_player_maps
WHERE official_position = 1
  AND ti2026_qualified = 1
ORDER BY fantasy_score DESC
LIMIT 15;
```

### Reliability output for position 1

```sql
SELECT reliability_score_1_100, official_name, team_name, reliability_raw_score AS predicted_score_raw,
       low_estimate, expected_estimate, high_estimate, confidence_label
FROM analytics_reliable_players_foundation
WHERE official_position = 1
ORDER BY reliability_score_1_100 DESC
LIMIT 15;
```

### TI-scoped optimizer output

```sql
SELECT optimizer_score_1_100, official_name, team_name, optimizer_raw_score AS predicted_score_raw,
       expected_estimate, high_estimate, reliability_score_1_100, series_top1_p75
FROM analytics_optimizer_players_foundation
WHERE ti2026_qualified = 1
  AND official_position = 1
ORDER BY optimizer_score_1_100 DESC
LIMIT 15;
```

### Optimizer backtest metrics

```sql
SELECT entity_type, optimizer_scope, metric_name, metric_value
FROM analytics_optimizer_foundation_evaluation
WHERE metric_scope = 'entity'
ORDER BY entity_type, optimizer_scope, metric_name;
```

### Team role summary by map

```sql
SELECT match_date, stage_name, team_name, opponent_name,
       avg_core_fantasy_score, mid_fantasy_score,
       avg_support_fantasy_score, team_role_fantasy_score
FROM analytics_team_role_maps
ORDER BY match_date, team_name
LIMIT 30;
```

### Stage-aware player-map slice

```sql
SELECT match_date, team_name, official_name, official_position,
       stage_name, stage_bucket, is_group_stage_bucket, is_main_playoff,
       fantasy_score, title_bonus_points
FROM analytics_player_maps
WHERE ti2026_qualified = 1
ORDER BY match_date DESC, team_name, official_position
LIMIT 20;
```

### Check which backfilled stats are truly covered

```sql
SELECT stat_name, preferred_source, coverage_status,
       has_stage_evidence, is_row_complete,
       zero_raw_rows, nonzero_raw_rows,
       sparse_zero_rows, source_missing_rows,
       objective_derived_rows, clamped_rows
FROM analytics_fantasy_backfill_coverage
ORDER BY stat_name;
```

### Inspect suspicious or special backfill cases

```sql
SELECT stat_name, issue_type, issue_rows, sample_min_value, sample_max_value
FROM analytics_fantasy_backfill_sanity
ORDER BY stat_name, issue_type;
```

### Look at staged extraction rows for one stat

```sql
SELECT match_id, account_id, team_name, stat_name, raw_value,
       source_field_name, coverage_note
FROM stg_player_match_enriched_stats
WHERE stat_name = 'smokes_used'
ORDER BY match_id, team_name, account_id
LIMIT 50;
```

### One replay-backed match with team-slot counters

```sql
SELECT *
FROM analytics_replay_team_metrics_wide
WHERE match_id = 8904419709
ORDER BY team_side, team_slot;
```

### One replay-backed match resolved to player rows

```sql
SELECT match_id, team_name, official_name, official_position,
       watchers_taken, lotus, tormentor_kills
FROM analytics_replay_player_metrics_wide
WHERE match_id = 8904419709
ORDER BY team_name, official_position;
```

### Replay coverage by metric

```sql
SELECT *
FROM analytics_replay_metric_summary
ORDER BY stat_name;
```

## Practical interpretation tips

- If `analytics_player_maps` looks right but a single fantasy category seems odd, inspect `fantasy_player_map_stat_points`.
- If the selected-stat scoring looks right but the official client is still higher, inspect `title_bonus_points` and `analytics_scoring_titles`.
- If a stat in `fantasy_player_map_stat_points` is all zeros, do **not** assume it is fully sourced. Check `analytics_fantasy_backfill_coverage`.
- If `coverage_status = 'source_needed'` and `has_stage_evidence = 0`, the current project still lacks a confirmed extractor for that stat.
- `sparse_zero_rows` means zero inferred from source sparsity, not broken data.
- `watchers_taken` and `lotus` are resolved into player-level final rows through `player_slot -> team_slot` matching between OpenDota payloads and replay counters when replay archives are actually available for that event.
- Replay-derived raw provenance still exists at team-slot level in `replay_team_metric_final`.
- For EWC 2026 this replay path is already populated; for TI 2026 it may still be incomplete while replay downloads remain blocked.
- `tormentor_kills` should be interpreted through the coverage and provenance views, not by assuming either all-zero extraction failure or perfect event attribution. The project mixes replay and approximation logic, so use `analytics_fantasy_backfill_coverage` and `analytics_fantasy_backfill_sanity` before drawing conclusions from sparse outputs.

## Python helpers

From the repository root:

```python
from pathlib import Path
import sys

sys.path.insert(0, str(Path("src").resolve()))
from ewc_fact_agent_tools import ask, explain_sql_plan

print(ask("top 15 fantasy pos1 players from TI 2026 qualified teams").answer_markdown)
print(explain_sql_plan("top 15 fantasy pos1 players from TI 2026 qualified teams"))
```

Useful helper functions include:

- `top_fantasy_maps(...)`
- `reliable_players_foundation(...)`
- `reliable_role_slots_foundation(...)`
- `banner_optimizer_players(...)`
- `banner_optimizer_role_slots(...)`
- `optimizer_backtest_foundation(...)`
- `optimizer_v2_players(...)`
- `optimizer_v2_role_slots(...)`
- `metric_definitions(...)`
- `roster(team)`
- `ti_qualified_teams()`
- `source_cache_status()`
- `scoring_formula()`

Compatibility note:

- `reliable_players_v2(...)`
- `reliable_role_slots_v2(...)`
- `reliability_backtest_v2(...)`

still exist as thin aliases, but new notebook and agent code should use the `*_foundation(...)` helpers.

Similarly, the default optimizer aliases now point to the v2 layer:

- `banner_optimizer_players(...)` -> default `optimizer_v2`
- `banner_optimizer_role_slots(...)` -> default `optimizer_v2`

Use the explicit `*_foundation(...)` variants only when you want a comparison against the older foundation-first optimizer.

## Validation and reporting

```bash
python scripts/report_backfill_coverage.py
python tests/regression_tests.py
python scripts/validate_project.py
```


