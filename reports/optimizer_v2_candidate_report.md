# Optimizer V2 Candidate Report

This report compares a conservative optimizer-v2 candidate against the strongest current simple baselines.

Candidate formulas:

- `player`: `0.8 * series_top1_p75 + 0.1 * series_mean_p75 - 80 * top_stat_share - 240 * volatility_ratio`
- `role_slot`: `0.5 * series_top1_p75 + 0.1 * series_mean_p75 - 120 * sample_weight`

## Entity Comparison

| Entity type | Scope | Model | Spearman | Top5 overlap | NDCG@5 | Regret@1 |
|---|---|---|---:|---:|---:|---:|
| player | all | top1_p75_only | 0.667 | 0.000 | 0.782 | 4703.09 |
| player | all | ceiling_blend | 0.641 | 0.000 | 0.782 | 3072.51 |
| player | all | optimizer_v2_candidate | 0.675 | 0.000 | 0.794 | 3072.51 |
| player | ti2026 | top1_p75_only | 0.693 | 0.000 | 0.782 | 4703.09 |
| player | ti2026 | ceiling_blend | 0.657 | 0.000 | 0.782 | 3072.51 |
| player | ti2026 | optimizer_v2_candidate | 0.697 | 0.000 | 0.794 | 3072.51 |
| role_slot | all | top1_p75_only | 0.643 | 0.400 | 0.859 | 4662.79 |
| role_slot | all | ceiling_blend | 0.630 | 0.400 | 0.869 | 3032.21 |
| role_slot | all | optimizer_v2_candidate | 0.649 | 0.400 | 0.872 | 3032.21 |
| role_slot | ti2026 | top1_p75_only | 0.675 | 0.400 | 0.859 | 4662.79 |
| role_slot | ti2026 | ceiling_blend | 0.662 | 0.400 | 0.869 | 3032.21 |
| role_slot | ti2026 | optimizer_v2_candidate | 0.683 | 0.400 | 0.872 | 3032.21 |

## Segment Diagnostics

| Entity type | Scope | Segment | Model | Spearman | Top3 overlap | NDCG@5 | Regret@1 |
|---|---|---|---|---:|---:|---:|---:|
| player | all | core | optimizer_v2_candidate | 0.109 | 0.333 | 0.776 | 8025.96 |
| player | all | mid | optimizer_v2_candidate | -0.429 | 0.000 | 0.880 | 3032.21 |
| player | all | support | optimizer_v2_candidate | 0.091 | 0.000 | 0.825 | 3671.84 |
| player | ti2026 | core | optimizer_v2_candidate | 0.178 | 0.333 | 0.776 | 8025.96 |
| player | ti2026 | mid | optimizer_v2_candidate | -0.679 | 0.000 | 0.880 | 3032.21 |
| player | ti2026 | support | optimizer_v2_candidate | 0.046 | 0.000 | 0.825 | 3671.84 |
| role_slot | all | core_pair | optimizer_v2_candidate | -0.381 | 0.333 | 0.840 | 1705.11 |
| role_slot | all | mid_single | optimizer_v2_candidate | -0.429 | 0.000 | 0.880 | 3032.21 |
| role_slot | all | support_pair | optimizer_v2_candidate | -0.500 | 0.000 | 0.824 | 2181.77 |
| role_slot | ti2026 | core_pair | optimizer_v2_candidate | -0.250 | 0.333 | 0.869 | 1705.11 |
| role_slot | ti2026 | mid_single | optimizer_v2_candidate | -0.679 | 0.000 | 0.880 | 3032.21 |
| role_slot | ti2026 | support_pair | optimizer_v2_candidate | -0.679 | 0.000 | 0.883 | 2181.77 |

