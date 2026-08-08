# Modeling notes and limitations

This document describes what is actually implemented or stored in the bundled Project F database. It intentionally avoids presenting the project-specific scores as calibrated probabilities.

## Fantasy score

For a player on one map, the public analytics layer uses the stored relationship:

```text
fantasy_score = base_points_total + profile_bonus_points
```

`base_points_total` is built from the stored BattlePass-style scoring categories. `profile_bonus_points` depends on the selected fantasy scoring profile and role-aware banner statistics.

The regression suite checks that this decomposition agrees with the stored `fantasy_score` values to within a small numerical tolerance.

## Reliability v2

The project describes reliability v2 as an estimate of **repeatable fantasy ceiling** rather than simple expected-map performance.

The stored/model logic uses signals such as:

- best-two / top-series performance;
- second-best and other top-tail summaries;
- upper quantiles such as p75;
- recent form;
- spike penalties;
- volatility penalties;
- role-level shrinkage for small samples.

The final score is scaled to 1–100 within the relevant role or role-slot segment.

### Support-player caveat

The project explicitly records support statistics as incomplete and lower-confidence. Default recommendations therefore exclude support players and the `support_pair` slot. Support data remains queryable when requested explicitly.

## Uncertainty bands

The fields:

- `low_estimate`
- `expected_estimate`
- `high_estimate`

are **heuristic uncertainty bands**. They are not classical confidence intervals and should not be described as statistically calibrated Bayesian credible intervals.

## Banner optimizer

The banner optimizer works on profile-specific player/role-slot series data and combines repeatability/upside-related features into recommendations. The source code includes features such as top means, percentiles, dispersion, repeated high performance, and spike-related quantities before scaling final recommendation scores.

This is a decision-support heuristic for the fantasy mechanics represented by the database, not a claim of optimal play under every tournament format.

## Stored backtesting

The database includes two broad evaluation setups:

1. **group stage → playoffs** evaluation;
2. **first 60% → last 40%** temporal evaluation.

Selected aggregate rows stored in the database are:

| Evaluation | Entity | n | MAE | RMSE | Spearman | Top-5 overlap | Top-10 overlap |
|---|---|---:|---:|---:|---:|---:|---:|
| group → playoffs | player / all | 40 | 3189.96 | 4040.70 | 0.718 | 0.00 | 0.30 |
| group → playoffs | role slot / all | 24 | 3149.45 | 3963.60 | 0.583 | 0.00 | 0.50 |
| first 60% → last 40% | player temporal / all | 120 | 3229.31 | 4411.59 | 0.827 | 0.00 | 0.20 |

These aggregate numbers should not be read in isolation. Several role-specific segments in the same evaluation table are substantially weaker (including negative rank correlation in some group→playoffs segments). The repository therefore exposes the full evaluation view through `analytics_reliability_backtest` instead of presenting a single metric as proof of general predictive quality.

## Dataset completeness

The SQLite metadata records:

- `actual_match_count = 157`;
- `expected_dotabuff_match_count = 159`;
- build validation status indicating an incomplete match count.

This limitation should remain visible when interpreting results.
