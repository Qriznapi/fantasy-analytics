# Database guide

Database file: `data/ewc_2026_fantasy_compact.sqlite`

For ordinary analysis, prefer the public views with the `analytics_` prefix rather than querying implementation tables directly.

## Main public views

- `analytics_player_maps` - fantasy score for each player-map under the current default profile.
- `analytics_team_role_maps` - team/map role aggregation (`core`, `mid`, `support`).
- `analytics_reliable_players` - reliability-v2 player output with low/expected/high heuristic bands.
- `analytics_reliable_role_slots` - reliability-v2 output for `core_pair`, `mid_single`, `support_pair`.
- `analytics_optimizer_players` - optimizer attractiveness for players.
- `analytics_optimizer_role_slots` - optimizer attractiveness for role slots.
- `analytics_rosters` - official names and positions from the stored roster registry.
- `analytics_ti2026_teams` - TI 2026 qualification data stored by the project.
- `analytics_sources` - source provenance and cache status.
- `analytics_scoring_formula` - active fantasy scoring and banner-formula rows.
- `analytics_reliability_backtest` - stored evaluation rows.
- `analytics_db_objects` - catalog of recommended database objects.
- `analytics_fantasy_backfill_coverage` - source coverage and zero-value semantics for backfilled stats.
- `analytics_fantasy_backfill_sanity` - data-quality warnings for the backfill layer.

## Most useful implementation tables

Only query these directly when you need source or rebuild detail:

- `fantasy_player_map_stat_points`
- `fantasy_player_map_scores`
- `player_game_fantasy_summary`
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
SELECT reliability_score_1_100, official_name, team_name, predicted_score_raw,
       low_estimate, expected_estimate, high_estimate, confidence_label
FROM analytics_reliable_players
WHERE official_position = 1
  AND recommended_default = 1
ORDER BY reliability_score_1_100 DESC
LIMIT 15;
```

### TI-scoped optimizer output

```sql
SELECT optimizer_score_1_100, official_name, team_name, predicted_score_raw,
       best2_series_score, repeatability_ratio, spike_gap
FROM analytics_optimizer_players
WHERE optimizer_scope = 'ti2026'
  AND official_position = 1
ORDER BY optimizer_score_1_100 DESC
LIMIT 15;
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

## Practical interpretation tips

- If `analytics_player_maps` looks right but a single fantasy category seems odd, inspect `fantasy_player_map_stat_points`.
- If a stat in `fantasy_player_map_stat_points` is all zeros, do **not** assume it is fully sourced. Check `analytics_fantasy_backfill_coverage`.
- If `coverage_status = 'source_needed'` and `has_stage_evidence = 0`, the current project still lacks a confirmed extractor for that stat.
- `sparse_zero_rows` means zero inferred from source sparsity, not broken data.

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
- `reliable_players_v2(...)`
- `reliable_role_slots_v2(...)`
- `banner_optimizer_players(...)`
- `banner_optimizer_role_slots(...)`
- `roster(team)`
- `ti_qualified_teams()`
- `source_cache_status()`
- `scoring_formula()`

## Validation and reporting

```bash
python scripts/report_backfill_coverage.py
python tests/regression_tests.py
python scripts/validate_project.py
```
