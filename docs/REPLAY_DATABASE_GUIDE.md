# Replay database guide

Replay status is stored in:

- `deliverables/replay_team_metrics_ewc2026_probe6.sqlite`

If you later want to merge it into the main compact tournament database, use:

```bash
python scripts/merge_replay_metrics_into_compact_db.py \
  --target-db data/ewc_2026_fantasy_compact.sqlite
```

## Main replay objects

- `replay_team_metric_events` - event-level counter changes from replay parsing.
- `replay_team_metric_final` - final metric values by `match_id + team_side + team_slot + stat_name`.

## Public replay views

- `analytics_replay_team_metrics_long` - long-format replay metrics.
- `analytics_replay_team_metrics_wide` - one row per `match_id + team_side + team_slot`.
- `analytics_replay_match_coverage` - how many replay rows were loaded per match.
- `analytics_replay_metric_summary` - metric-level coverage summary.

## Useful SQL

### One match, all replay team-slot metrics

```sql
SELECT *
FROM analytics_replay_team_metrics_wide
WHERE match_id = 8904419709
ORDER BY team_side, team_slot;
```

### Coverage by metric

```sql
SELECT *
FROM analytics_replay_metric_summary
ORDER BY stat_name;
```

### Coverage by match

```sql
SELECT *
FROM analytics_replay_match_coverage
ORDER BY match_id;
```
