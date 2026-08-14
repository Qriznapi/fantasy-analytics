# Modeling notes and limitations

This document describes what is actually implemented or stored in the bundled Project F database. It intentionally avoids presenting the project-specific scores as calibrated probabilities.

## Fantasy score

For a player on one map, the public analytics layer now uses an official-client-like selected-stat relationship:

```text
fantasy_score = Σ(selected_stat_base_points * selected_multiplier)
              + title_bonus_points
              = base_points_total + profile_bonus_points + title_bonus_points
```

`base_points_total` is the sum of x1 base points only for the stats selected by the active profile for the player's official role. `profile_bonus_points` is the uplift above x1 for those same selected stats. `title_bonus_points` is an optional extra layer from configured coach-title rules when their condition fires on that player-map.

The regression suite checks that this decomposition agrees with the stored `fantasy_score` values to within a small numerical tolerance.

## Prediction foundation

The cleaner statistical base now lives in `src/fantasy_prediction_foundation.py`.

This layer builds generic targets from the same compact SQLite database instead of hardcoding a single best-series framing. The current target registry includes:

- `player_map_score`
- `player_series_mean`
- `player_series_top1`
- `role_slot_map_score`
- `role_slot_series_mean`
- `role_slot_series_top1`

The stored evaluation setups are:

1. `group_to_playoff`
2. `temporal_60_40`

Baseline models in the current foundation layer include:

- `global_mean`
- `segment_mean`
- `entity_mean`
- `entity_p75`
- `recent_mean_5`
- `recent_p75_5`
- `team_segment_mean`
- `shrunk_mean`

Use `docs/PREDICTION_FOUNDATION_SCORECARD.md` for the current baseline comparison surface.

## Reliability foundation

The new primary recommendation-oriented layer now lives in `src/fantasy_reliability_foundation.py`.

It is built on top of the generic target framework and is meant to estimate **repeatable fantasy upside with stability controls**, not just raw average map score.

The current implementation uses:

- map-level mean, floor, p75, p90, and volatility;
- series-level mean and top1 summaries;
- recent form over the last few maps and series;
- team-segment strength;
- stat-profile breadth and concentration;
- sample-size shrinkage;
- volatility and over-concentration penalties.

The final score is scaled to `1-100` within the relevant segment:

- player segments: `core`, `mid`, `support`
- role-slot segments: `core_pair`, `mid_single`, `support_pair`

The main stored outputs are:

- `foundation_reliability_entity_scores`
- `foundation_reliability_backtest`
- `analytics_reliable_players_foundation`
- `analytics_reliable_role_slots_foundation`
- `analytics_reliability_foundation_backtest`

The current backtest logic is intentionally simple and transparent:

1. learn from `group_stage` rows;
2. score entities from those rows;
3. compare them against non-group-stage outcomes;
4. evaluate whether the ranking preserves strong playoff-style picks.

Use `docs/RELIABILITY_FOUNDATION_SCORECARD.md` for the current summary table.

### Support-player caveat

Support players and the `support_pair` slot are included in the default recommendation flow. Their utility-oriented metrics can still be more context-sensitive than classic core farm metrics, so it is worth reading the source coverage and stat mix alongside the final score.

## Optimizer foundation

The older comparison optimizer surface now lives in `src/fantasy_optimizer_foundation.py`.

It starts from the foundation reliability layer and then re-ranks entities using a more lineup-oriented objective. The current heuristic blends:

- `expected_estimate`
- `high_estimate`
- `reliability_score_1_100`
- upper-quantile signals such as `map_p75_score`, `series_mean_p75`, `series_top1_p75`
- `stat_balance_score`
- penalties for `volatility_ratio`
- sample trust via `sample_weight`

The main stored outputs are:

- `foundation_optimizer_recommendations`
- `foundation_optimizer_backtest`
- `foundation_optimizer_evaluation_reports`
- `analytics_optimizer_players_foundation`
- `analytics_optimizer_role_slots_foundation`
- `analytics_optimizer_foundation_backtest`
- `analytics_optimizer_foundation_evaluation`

This layer is still heuristic, but it is cleaner than the older optimizer because it no longer depends directly on the legacy `best2_series_score` target family.

Use `docs/OPTIMIZER_FOUNDATION_SCORECARD.md` for the reference comparison table.

The current optimizer backtest surface compares the recommendation score against non-group-stage outcomes built as a simple playoff-style target:

- `0.60 * series_mean`
- `0.40 * series_top1`

The stored quality metrics currently include:

- `mae`
- `spearman`
- `top3_overlap`
- `top5_overlap`
- `top10_overlap`
- `ndcg_5`
- `ndcg_10`
- `regret_at_1`

This is still a first evaluation layer, not a final calibrated forecast benchmark.

## Optimizer v2

As of August 12, 2026, the project stores a separate conservative optimizer-v2 layer and now uses it as the default recommendation surface in notebooks and the deterministic fact-agent router.

It is intentionally simpler than the current default foundation optimizer and starts from strong ceiling-oriented baselines instead of from the broader reliability blend.

Current candidate formulas:

- player: `0.8 * series_top1_p75 + 0.1 * series_mean_p75 - 80 * top_stat_share - 240 * volatility_ratio`
- role-slot: `0.5 * series_top1_p75 + 0.1 * series_mean_p75 - 120 * sample_weight`

Stored outputs:

- `foundation_optimizer_v2_recommendations`
- `foundation_optimizer_v2_backtest`
- `foundation_optimizer_v2_evaluation_reports`
- `analytics_optimizer_v2_players`
- `analytics_optimizer_v2_role_slots`
- `analytics_optimizer_v2_backtest`
- `analytics_optimizer_v2_evaluation`

This layer exists because the simpler ceiling-first design currently outperforms the older foundation optimizer on entity-level holdout Spearman ranking, even though some small segments remain unstable.

Use `reports/optimizer_v2_scorecard.md` for the current scorecard and `reports/optimizer_v2_candidate_report.md` for the original comparison against the simpler baselines that motivated the switch.

## Ridge prediction layer

As of August 12, 2026, the project stores a tuned ridge-based prediction layer in `src/fantasy_prediction_ridge.py`.

This is now a richer version of the earlier ridge experiment. It still aims to stay transparent, but it no longer uses only a tiny feature bundle or a fixed alpha.

Current feature family:

- entity mean, p25, p75, p90
- recent mean over the last 3 and 5 observations
- recent p75 over the last 5 observations
- entity max, min, standard deviation, coefficient of variation
- span and ceiling-gap features such as `range_span`, `max_minus_mean`, `p75_minus_mean`
- momentum-style deltas such as `recent_delta_mean` and `recent_delta_p75`
- segment mean, team-segment mean, and relative-vs-segment gaps
- sample trust features such as `sample_weight`, `sample_trust`, and `train_count`
- `maps_in_observation`
- simple encoded role indicator `role_code`

Stored outputs:

- `ridge_prediction_runs`
- `ridge_prediction_outputs`
- `ridge_evaluation_reports`
- `ridge_tuning_reports`
- `analytics_prediction_ridge_evaluation`
- `analytics_prediction_ridge_tuning`

The current implementation:

- builds the same target family from `dataset_prediction_targets`
- keeps the same outer evaluation splits: `group_to_playoff` and `temporal_60_40`
- performs an inner temporal split inside the train portion
- tunes `alpha` over a fixed grid before the final outer-run fit
- evaluates with the same MAE / Spearman / overlap / NDCG / regret metrics used elsewhere

The tuned ridge layer improves some rank-oriented scenarios relative to the earlier ridge attempt, but it still does not consistently beat the strongest simple baselines across the whole target set.

## Quantile prediction layer

As of August 12, 2026, the project also stores a linear quantile layer in `src/fantasy_prediction_quantile.py`.

Its purpose is different from the main baseline/ridge/GBDT comparisons:

- q50 is used as a point prediction
- q25 / q75 / q90 expose the shape of the predicted score distribution
- the stored diagnostics let us reason about uncertainty coverage, not only rank quality

Stored outputs:

- `quantile_prediction_runs`
- `quantile_prediction_outputs`
- `quantile_evaluation_reports`
- `analytics_prediction_quantile_evaluation`

Stored diagnostics include:

- standard point-metric rows such as `mae`, `entity_spearman`, `top5_overlap`, `ndcg_5`, `regret_at_1`
- quantile-specific rows such as `pinball_q25`, `pinball_q50`, `pinball_q75`, `pinball_q90`
- empirical coverage checks such as `coverage_q75` and `coverage_q90`
- interval width diagnostics such as `band_width_q25_q75`

This layer is currently more useful as an uncertainty surface than as the strongest point-forecast model.

## GBDT ranking experiment

As of August 12, 2026, the project stores a lightweight ranking-oriented boosted-tree experiment in `src/fantasy_prediction_gbdt.py`.

Important limitation:

- this is **not** LambdaMART or a full library GBDT implementation
- it is an in-project boosted-stump regressor
- ranking behavior is encouraged through target-aware sample weights rather than through a true pairwise/listwise ranking loss

Stored outputs:

- `gbdt_prediction_runs`
- `gbdt_prediction_outputs`
- `gbdt_evaluation_reports`
- `gbdt_tuning_reports`
- `gbdt_feature_importance`
- `analytics_prediction_gbdt_evaluation`
- `analytics_prediction_gbdt_importance`

The current implementation:

- uses the same shared richer feature layer as ridge and quantile
- tunes `(n_estimators, learning_rate)` on an inner temporal validation split
- upweights stronger train outcomes so the model pays more attention to ceiling-relevant cases
- stores split-gain-based feature importance summaries for inspection

This experiment is promising on some temporal ranking slices, especially for entity-level Spearman, but it is still an experiment rather than a production default.

## Production prediction surface

As of August 12, 2026, the project stores a production prediction layer in `src/fantasy_prediction_production.py`.

Its job is not to train yet another model family. Instead, it:

- reads the stored baseline, ridge, quantile, and GBDT evaluation surfaces;
- chooses the strongest available family per `target_id + split_name`;
- exposes one default ranking surface for downstream analysis, notebooks, and the fact agent.

Stored outputs:

- `production_prediction_model_choices`
- `production_prediction_entity_scores`
- `analytics_prediction_production_model_choices`
- `analytics_prediction_production_players`
- `analytics_prediction_production_role_slots`

The production layer is intentionally pragmatic. Different targets currently prefer different model families, so the project does not force one global winner across every role, split, and aggregation target.

## Monte Carlo layer

As of August 12, 2026, the project also stores a Monte Carlo layer in `src/fantasy_prediction_monte_carlo.py`.

This layer sits on top of the production prediction surface and converts stored point forecasts plus uncertainty information into ranking-stability estimates.

Current implementation:

- starts from `analytics_prediction_production_players` and `analytics_prediction_production_role_slots`
- uses `q25/q75` when available to derive an uncertainty scale with `sigma = (q75 - q25) / 1.349`
- falls back to a clipped MAE-based scale when quantile bands are unavailable
- samples repeated normal draws per entity inside each role segment
- estimates ranking-oriented quantities such as top-finish probability and expected rank

Stored outputs:

- `production_monte_carlo_runs`
- `production_monte_carlo_entity_results`
- `analytics_prediction_monte_carlo_players`
- `analytics_prediction_monte_carlo_role_slots`

Important stored fields include:

- `simulated_mean_score`
- `simulated_std_score`
- `p_top1`
- `p_top3`
- `p_top5`
- `expected_rank`
- `p_above_segment_mean`
- `p90_sim_score`

This layer should be read as a stability and upside simulator, not as a claim that fantasy outcomes are exactly Gaussian. Its value is comparative: it helps separate profiles that look similar on raw prediction but differ in uncertainty and rank-collapse risk.

## Unified evaluator

As of August 12, 2026, the project also stores a unified evaluator layer in `src/fantasy_model_evaluator.py`.

Its purpose is organizational rather than predictive:

- normalize prediction, reliability, and optimizer backtests into one schema
- keep simulation-only layers visible without pretending they are directly comparable backtests
- expose one leaderboard-oriented surface for notebooks, reports, and future agent routing

Stored outputs:

- `unified_evaluation_runs`
- `unified_evaluation_metrics`
- `analytics_unified_evaluation_metrics`
- `analytics_unified_evaluation_summary`
- `analytics_unified_evaluation_leaderboard`

The evaluator currently treats Monte Carlo as `diagnostic_only`, while prediction/reliability/optimizer layers remain `backtest` surfaces with comparable ranking metrics.

## Banner rescoring layer

As of August 12, 2026, the project stores a banner rescoring layer in `src/fantasy_banner_rescoring.py`.

This layer starts from the production prediction surface and the Monte Carlo diagnostics, then rebuilds one cleaner recommendation anchor for the currently active fantasy profile.

Current implementation:

- blends target types with weights `0.20 map + 0.25 series_mean + 0.55 series_top1`
- blends split types with weights `0.40 group_to_playoff + 0.60 temporal_60_40`
- combines production predicted score, Monte Carlo `p90`, `p_top3`, expected-rank strength, and stability
- rescales the final output to `1-100` inside each player role group or role-slot segment

Stored outputs:

- `banner_rescoring_runs`
- `banner_rescoring_entity_scores`
- `analytics_banner_rescoring_players`
- `analytics_banner_rescoring_role_slots`

## Banner decision layer

As of August 12, 2026, the project also stores a practical decision layer in `src/fantasy_banner_decision.py`.

This layer is meant for actual pick recommendations rather than for generic scoring analysis.

Current risk profiles:

- `conservative`
- `balanced`
- `aggressive`

Current implementation:

- starts from the rescoring layer
- changes feature weights depending on the desired risk profile
- ranks both players and role slots
- generates ready-made three-team lineups from `core_pair + mid_single + support_pair`
- enforces team uniqueness across those three role slots

Stored outputs:

- `banner_decision_runs`
- `banner_decision_entity_scores`
- `banner_decision_lineups`
- `analytics_banner_decision_players`
- `analytics_banner_decision_role_slots`
- `analytics_banner_decision_lineups`

## Reliability v2

The older reliability v2 surface should now be treated as a **legacy heuristic layer** rather than the foundation for future modeling work.

It was useful for early experimentation, but new evaluation and recommendation work should prefer the map-first prediction foundation and the newer reliability foundation built on top of it.

The `*_v2(...)` Python helpers remain only as compatibility aliases for older notebook cells.

## Uncertainty bands

The fields:

- `low_estimate`
- `expected_estimate`
- `high_estimate`

are **heuristic uncertainty bands**. They are not classical confidence intervals and should not be described as statistically calibrated Bayesian credible intervals.

## Banner optimizer

The banner optimizer works on profile-specific player and role-slot data and combines repeatability and upside-related features into recommendations. The source code includes features such as top means, percentiles, dispersion, repeated high performance, and spike-related quantities before scaling final recommendation scores.

This is a decision-support heuristic for the fantasy mechanics represented by the database, not a claim of optimal play under every tournament format.

For the exact meaning of stored metrics, use `docs/METRICS_REFERENCE.md` or the SQLite view `analytics_metric_definitions`.

## Dataset completeness

The SQLite metadata records:

- `actual_match_count = 157`
- `expected_dotabuff_match_count = 159`
- build validation status indicating an incomplete match count

This limitation should remain visible when interpreting results.
