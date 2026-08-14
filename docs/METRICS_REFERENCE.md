# Metrics Reference

This document is the human-readable companion to the SQLite view `analytics_metric_definitions`.

## How to use it

- `fantasy` layer metrics describe direct map scoring under the active banner profile.
- `prediction_foundation` metrics describe reusable map/series targets for baseline modeling.
- `reliability_foundation` metrics describe the current default reliability layer.
- `optimizer_legacy` metrics describe the older best2-based optimizer layer that still exists for comparison.

For SQL access, use:

```sql
SELECT *
FROM analytics_metric_definitions
ORDER BY layer_name, metric_name;
```

## Important examples

### `fantasy_score`

- What it is: final fantasy points for one player on one map.
- How it is calculated: `sum(selected_stat_base_points * selected_multiplier) + title_bonus_points`, which is also stored as `base_points_total + profile_bonus_points + title_bonus_points`.
- Why it matters: this is the final number most map-level fantasy queries use.

### `title_bonus_points`

- What it is: extra bonus from active coach titles.
- How it is calculated: when a configured title condition triggers on a player-map, the system adds `selected_stat_score_before_titles * bonus_pct`.
- Why it matters: this is the most likely explanation for residual gaps between a correct banner reconstruction and the official client.

### `map_p75_score`

- What it is: 75th percentile of map scores for one player or role slot.
- How it is calculated: empirical p75 over training-map fantasy scores.
- Why it matters: one of the best practical ceiling metrics because it captures strong outcomes without trusting only a single spike.

### `series_top1_p75`

- What it is: 75th percentile of best-map-in-series values.
- How it is calculated: empirical p75 over `series_top1` target rows.
- Why it matters: strong signal when the fantasy format rewards high-end maps or high-end series outcomes.

### `stat_balance_score`

- What it is: diversification score for the fantasy stat profile.
- How it is calculated: positive-stat breadth multiplied by `(1 - top_stat_share)`.
- Why it matters: higher means the player is less dependent on one single stat category.

### `volatility_ratio`

- What it is: normalized volatility.
- How it is calculated: `map_std_score / max(map_mean_score, 1)`, capped.
- Why it matters: higher means the pick is swingier relative to its own mean.

### `reliability_raw_score`

- What it is: internal foundation reliability score before 1-100 scaling.
- How it is calculated: weighted mix of ceiling, stability, recent form, stat-balance, sample trust, and volatility penalties.
- Why it matters: this is the main internal ordering signal of the new reliability layer.

### `reliability_score_1_100`

- What it is: rank-scaled foundation reliability score.
- How it is calculated: rank-scaling of `reliability_raw_score` inside the relevant role group or role slot.
- Why it matters: easiest score for quick comparison, but it is ordinal rather than probabilistic.

### `best2_series_score`

- What it is: old optimizer's “sum of the two best maps in a series”.
- How it is calculated: take the two best map fantasy scores in the series and sum them.
- Why it matters: legacy ceiling target from the older optimizer layer.

### `repeatability_ratio`

- What it is: legacy repeatability check.
- How it is calculated: `second_best2_series_score / best2_series_score`.
- Why it matters: larger values mean the player repeated strong series outcomes instead of peaking once.

## Recommendation

For new analysis:

1. use `analytics_reliable_players_foundation`
2. use `analytics_reliable_role_slots_foundation`
3. use `analytics_reliability_foundation_backtest`
4. consult `analytics_metric_definitions` when a metric needs interpretation
