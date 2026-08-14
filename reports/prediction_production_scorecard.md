# Prediction Production Scorecard

This scorecard summarizes the production prediction surface. It does not assume a single global model; instead, it stores the historically strongest model choice per target/split and then recomputes current entity scores on the full available dataset.

## Chosen Model Per Target

| Target | Split | Family | Model | Param A | Param B | Entity sp. | NDCG@5 | Top5 overlap | MAE | Regret@1 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| player_map_score | group_to_playoff | baseline | segment_mean |  |  | 0.729 | 0.857 | 0.400 | 2500.95 | 2372.90 |
| player_map_score | temporal_60_40 | gbdt | gbdt_rank_v1 | 16.00 | 0.050 | 0.889 | 0.807 | 0.000 | 2980.60 | 2619.60 |
| player_series_mean | group_to_playoff | baseline | segment_mean |  |  | 0.724 | 0.811 | 0.200 | 1931.90 | 4952.58 |
| player_series_mean | temporal_60_40 | baseline | entity_mean |  |  | 0.890 | 0.880 | 0.000 | 1834.65 | 3707.04 |
| player_series_top1 | group_to_playoff | baseline | segment_mean |  |  | 0.727 | 0.862 | 0.200 | 2438.89 | 3703.49 |
| player_series_top1 | temporal_60_40 | quantile | quantile_linear_v1 |  |  | 0.888 | 0.914 | 0.400 | 3826.30 | 4155.04 |
| role_slot_map_score | group_to_playoff | baseline | segment_mean |  |  | 0.781 | 0.844 | 0.400 | 2301.53 | 2258.61 |
| role_slot_map_score | temporal_60_40 | gbdt | gbdt_rank_v1 | 16.00 | 0.050 | 0.890 | 0.812 | 0.000 | 2920.78 | 4434.58 |
| role_slot_series_mean | group_to_playoff | baseline | segment_mean |  |  | 0.759 | 0.833 | 0.400 | 1755.78 | 4306.62 |
| role_slot_series_mean | temporal_60_40 | baseline | shrunk_mean |  |  | 0.889 | 0.899 | 0.400 | 1787.30 | 3512.83 |
| role_slot_series_top1 | group_to_playoff | baseline | segment_mean |  |  | 0.781 | 0.902 | 0.400 | 2218.66 | 3703.49 |
| role_slot_series_top1 | temporal_60_40 | baseline | shrunk_mean |  |  | 0.876 | 0.896 | 0.400 | 2162.44 | 2092.98 |

## Top Players / group_to_playoff / player_map_score

| Player | Team | Pos | Role | Score | Q75 | Model family | Eval sp. | Eval NDCG@5 |
|---|---|---:|---|---:|---:|---|---:|---:|
| bzm | 1w | 2 | mid | 14762.68 |  | baseline | 0.729 | 0.857 |
| Mikoto | Aurora Gaming | 2 | mid | 14762.68 |  | baseline | 0.729 | 0.857 |
| gpk~ | BoomBoys | 2 | mid | 14762.68 |  | baseline | 0.729 | 0.857 |
| RCY | GamerLegion | 2 | mid | 14762.68 |  | baseline | 0.729 | 0.857 |
| Stojkov | Inner Circle x Insanity | 2 | mid | 14762.68 |  | baseline | 0.729 | 0.857 |
| Mirage` | L1 TEAM | 2 | mid | 14762.68 |  | baseline | 0.729 | 0.857 |
| TaiLung | LGD Gaming | 2 | mid | 14762.68 |  | baseline | 0.729 | 0.857 |
| Ainkrad | Level UP esports | 2 | mid | 14762.68 |  | baseline | 0.729 | 0.857 |
| MidOne | MOUZ | 2 | mid | 14762.68 |  | baseline | 0.729 | 0.857 |
| lorenof | Nigma Galaxy | 2 | mid | 14762.68 |  | baseline | 0.729 | 0.857 |

## Top Players / group_to_playoff / player_series_mean

| Player | Team | Pos | Role | Score | Q75 | Model family | Eval sp. | Eval NDCG@5 |
|---|---|---:|---|---:|---:|---|---:|---:|
| bzm | 1w | 2 | mid | 14822.34 |  | baseline | 0.724 | 0.811 |
| Mikoto | Aurora Gaming | 2 | mid | 14822.34 |  | baseline | 0.724 | 0.811 |
| gpk~ | BoomBoys | 2 | mid | 14822.34 |  | baseline | 0.724 | 0.811 |
| RCY | GamerLegion | 2 | mid | 14822.34 |  | baseline | 0.724 | 0.811 |
| Stojkov | Inner Circle x Insanity | 2 | mid | 14822.34 |  | baseline | 0.724 | 0.811 |
| Mirage` | L1 TEAM | 2 | mid | 14822.34 |  | baseline | 0.724 | 0.811 |
| TaiLung | LGD Gaming | 2 | mid | 14822.34 |  | baseline | 0.724 | 0.811 |
| Ainkrad | Level UP esports | 2 | mid | 14822.34 |  | baseline | 0.724 | 0.811 |
| MidOne | MOUZ | 2 | mid | 14822.34 |  | baseline | 0.724 | 0.811 |
| lorenof | Nigma Galaxy | 2 | mid | 14822.34 |  | baseline | 0.724 | 0.811 |

## Top Players / group_to_playoff / player_series_top1

| Player | Team | Pos | Role | Score | Q75 | Model family | Eval sp. | Eval NDCG@5 |
|---|---|---:|---|---:|---:|---|---:|---:|
| bzm | 1w | 2 | mid | 16752.53 |  | baseline | 0.727 | 0.862 |
| Mikoto | Aurora Gaming | 2 | mid | 16752.53 |  | baseline | 0.727 | 0.862 |
| gpk~ | BoomBoys | 2 | mid | 16752.53 |  | baseline | 0.727 | 0.862 |
| RCY | GamerLegion | 2 | mid | 16752.53 |  | baseline | 0.727 | 0.862 |
| Stojkov | Inner Circle x Insanity | 2 | mid | 16752.53 |  | baseline | 0.727 | 0.862 |
| Mirage` | L1 TEAM | 2 | mid | 16752.53 |  | baseline | 0.727 | 0.862 |
| TaiLung | LGD Gaming | 2 | mid | 16752.53 |  | baseline | 0.727 | 0.862 |
| Ainkrad | Level UP esports | 2 | mid | 16752.53 |  | baseline | 0.727 | 0.862 |
| MidOne | MOUZ | 2 | mid | 16752.53 |  | baseline | 0.727 | 0.862 |
| lorenof | Nigma Galaxy | 2 | mid | 16752.53 |  | baseline | 0.727 | 0.862 |

## Top Players / temporal_60_40 / player_map_score

| Player | Team | Pos | Role | Score | Q75 | Model family | Eval sp. | Eval NDCG@5 |
|---|---|---:|---|---:|---:|---|---:|---:|
| Pure | 1w | 1 | core | 14106.18 |  | gbdt | 0.889 | 0.807 |
| bzm | 1w | 2 | mid | 14106.18 |  | gbdt | 0.889 | 0.807 |
| Nightfall | Aurora Gaming | 1 | core | 14106.18 |  | gbdt | 0.889 | 0.807 |
| Mikoto | Aurora Gaming | 2 | mid | 14106.18 |  | gbdt | 0.889 | 0.807 |
| Kiritych~ | BoomBoys | 1 | core | 14106.18 |  | gbdt | 0.889 | 0.807 |
| gpk~ | BoomBoys | 2 | mid | 14106.18 |  | gbdt | 0.889 | 0.807 |
| RCY | GamerLegion | 2 | mid | 14106.18 |  | gbdt | 0.889 | 0.807 |
| Ghost | GamerLegion | 1 | core | 14106.18 |  | gbdt | 0.889 | 0.807 |
| Stojkov | Inner Circle x Insanity | 2 | mid | 14106.18 |  | gbdt | 0.889 | 0.807 |
| TaiLung | LGD Gaming | 2 | mid | 14106.18 |  | gbdt | 0.889 | 0.807 |

## Top Players / temporal_60_40 / player_series_mean

| Player | Team | Pos | Role | Score | Q75 | Model family | Eval sp. | Eval NDCG@5 |
|---|---|---:|---|---:|---:|---|---:|---:|
| Malr1ne | Team Falcons | 2 | mid | 16814.39 |  | baseline | 0.890 | 0.880 |
| Ghost | GamerLegion | 1 | core | 16612.93 |  | baseline | 0.890 | 0.880 |
| bzm | 1w | 2 | mid | 16441.41 |  | baseline | 0.890 | 0.880 |
| MidOne | MOUZ | 2 | mid | 16417.12 |  | baseline | 0.890 | 0.880 |
| NothingToSay | Xtreme Gaming | 2 | mid | 16352.16 |  | baseline | 0.890 | 0.880 |
| lorenof | Nigma Galaxy | 2 | mid | 16293.14 |  | baseline | 0.890 | 0.880 |
| Timado | Virtus.pro | 1 | core | 16268.32 |  | baseline | 0.890 | 0.880 |
| Abed | Virtus.pro | 2 | mid | 15805.43 |  | baseline | 0.890 | 0.880 |
| DarkMago | PTime | 2 | mid | 15556.42 |  | baseline | 0.890 | 0.880 |
| Nisha | Team Liquid | 2 | mid | 15458.48 |  | baseline | 0.890 | 0.880 |

## Top Players / temporal_60_40 / player_series_top1

| Player | Team | Pos | Role | Score | Q75 | Model family | Eval sp. | Eval NDCG@5 |
|---|---|---:|---|---:|---:|---|---:|---:|
| Ghost | GamerLegion | 1 | core | 11902.04 | 11902.65 | quantile | 0.888 | 0.914 |
| Malr1ne | Team Falcons | 2 | mid | 11899.86 | 11900.47 | quantile | 0.888 | 0.914 |
| Nisha | Team Liquid | 2 | mid | 11899.26 | 11899.88 | quantile | 0.888 | 0.914 |
| Timado | Virtus.pro | 1 | core | 11898.81 | 11899.42 | quantile | 0.888 | 0.914 |
| bzm | 1w | 2 | mid | 11898.48 | 11899.09 | quantile | 0.888 | 0.914 |
| NothingToSay | Xtreme Gaming | 2 | mid | 11898.46 | 11899.07 | quantile | 0.888 | 0.914 |
| No[o]ne- | PVISION | 2 | mid | 11897.39 | 11898.00 | quantile | 0.888 | 0.914 |
| lorenof | Nigma Galaxy | 2 | mid | 11897.28 | 11897.89 | quantile | 0.888 | 0.914 |
| Crystallis | MOUZ | 1 | core | 11897.18 | 11897.79 | quantile | 0.888 | 0.914 |
| m1CKe | Team Liquid | 1 | core | 11897.08 | 11897.69 | quantile | 0.888 | 0.914 |

## Top Role Slots / group_to_playoff / role_slot_map_score

| Players | Team | Role slot | Score | Q75 | Model family | Eval sp. | Eval NDCG@5 |
|---|---|---|---:|---:|---|---:|---:|
| bzm | 1w | mid_single | 14762.68 |  | baseline | 0.781 | 0.844 |
| Mikoto | Aurora Gaming | mid_single | 14762.68 |  | baseline | 0.781 | 0.844 |
| gpk~ | BoomBoys | mid_single | 14762.68 |  | baseline | 0.781 | 0.844 |
| RCY | GamerLegion | mid_single | 14762.68 |  | baseline | 0.781 | 0.844 |
| Stojkov | Inner Circle x Insanity | mid_single | 14762.68 |  | baseline | 0.781 | 0.844 |
| Mirage` | L1 TEAM | mid_single | 14762.68 |  | baseline | 0.781 | 0.844 |
| TaiLung | LGD Gaming | mid_single | 14762.68 |  | baseline | 0.781 | 0.844 |
| Ainkrad | Level UP esports | mid_single | 14762.68 |  | baseline | 0.781 | 0.844 |
| MidOne | MOUZ | mid_single | 14762.68 |  | baseline | 0.781 | 0.844 |
| lorenof | Nigma Galaxy | mid_single | 14762.68 |  | baseline | 0.781 | 0.844 |

## Top Role Slots / group_to_playoff / role_slot_series_mean

| Players | Team | Role slot | Score | Q75 | Model family | Eval sp. | Eval NDCG@5 |
|---|---|---|---:|---:|---|---:|---:|
| bzm | 1w | mid_single | 14822.34 |  | baseline | 0.759 | 0.833 |
| Mikoto | Aurora Gaming | mid_single | 14822.34 |  | baseline | 0.759 | 0.833 |
| gpk~ | BoomBoys | mid_single | 14822.34 |  | baseline | 0.759 | 0.833 |
| RCY | GamerLegion | mid_single | 14822.34 |  | baseline | 0.759 | 0.833 |
| Stojkov | Inner Circle x Insanity | mid_single | 14822.34 |  | baseline | 0.759 | 0.833 |
| Mirage` | L1 TEAM | mid_single | 14822.34 |  | baseline | 0.759 | 0.833 |
| TaiLung | LGD Gaming | mid_single | 14822.34 |  | baseline | 0.759 | 0.833 |
| Ainkrad | Level UP esports | mid_single | 14822.34 |  | baseline | 0.759 | 0.833 |
| MidOne | MOUZ | mid_single | 14822.34 |  | baseline | 0.759 | 0.833 |
| lorenof | Nigma Galaxy | mid_single | 14822.34 |  | baseline | 0.759 | 0.833 |

## Top Role Slots / group_to_playoff / role_slot_series_top1

| Players | Team | Role slot | Score | Q75 | Model family | Eval sp. | Eval NDCG@5 |
|---|---|---|---:|---:|---|---:|---:|
| bzm | 1w | mid_single | 16752.53 |  | baseline | 0.781 | 0.902 |
| Mikoto | Aurora Gaming | mid_single | 16752.53 |  | baseline | 0.781 | 0.902 |
| gpk~ | BoomBoys | mid_single | 16752.53 |  | baseline | 0.781 | 0.902 |
| RCY | GamerLegion | mid_single | 16752.53 |  | baseline | 0.781 | 0.902 |
| Stojkov | Inner Circle x Insanity | mid_single | 16752.53 |  | baseline | 0.781 | 0.902 |
| Mirage` | L1 TEAM | mid_single | 16752.53 |  | baseline | 0.781 | 0.902 |
| TaiLung | LGD Gaming | mid_single | 16752.53 |  | baseline | 0.781 | 0.902 |
| Ainkrad | Level UP esports | mid_single | 16752.53 |  | baseline | 0.781 | 0.902 |
| MidOne | MOUZ | mid_single | 16752.53 |  | baseline | 0.781 | 0.902 |
| lorenof | Nigma Galaxy | mid_single | 16752.53 |  | baseline | 0.781 | 0.902 |

## Top Role Slots / temporal_60_40 / role_slot_map_score

| Players | Team | Role slot | Score | Q75 | Model family | Eval sp. | Eval NDCG@5 |
|---|---|---|---:|---:|---|---:|---:|
| bzm | 1w | mid_single | 14290.72 |  | gbdt | 0.890 | 0.812 |
| Mikoto | Aurora Gaming | mid_single | 14290.72 |  | gbdt | 0.890 | 0.812 |
| gpk~ | BoomBoys | mid_single | 14290.72 |  | gbdt | 0.890 | 0.812 |
| Ghost, Fayde | GamerLegion | core_pair | 14290.72 |  | gbdt | 0.890 | 0.812 |
| RCY | GamerLegion | mid_single | 14290.72 |  | gbdt | 0.890 | 0.812 |
| Stojkov | Inner Circle x Insanity | mid_single | 14290.72 |  | gbdt | 0.890 | 0.812 |
| Yuma, Wisper | LGD Gaming | core_pair | 14290.72 |  | gbdt | 0.890 | 0.812 |
| TaiLung | LGD Gaming | mid_single | 14290.72 |  | gbdt | 0.890 | 0.812 |
| Crystallis, BOOM | MOUZ | core_pair | 14290.72 |  | gbdt | 0.890 | 0.812 |
| MidOne | MOUZ | mid_single | 14290.72 |  | gbdt | 0.890 | 0.812 |

## Top Role Slots / temporal_60_40 / role_slot_series_mean

| Players | Team | Role slot | Score | Q75 | Model family | Eval sp. | Eval NDCG@5 |
|---|---|---|---:|---:|---|---:|---:|
| Malr1ne | Team Falcons | mid_single | 16452.20 |  | baseline | 0.889 | 0.899 |
| bzm | 1w | mid_single | 16147.03 |  | baseline | 0.889 | 0.899 |
| MidOne | MOUZ | mid_single | 16127.16 |  | baseline | 0.889 | 0.899 |
| NothingToSay | Xtreme Gaming | mid_single | 16074.01 |  | baseline | 0.889 | 0.899 |
| lorenof | Nigma Galaxy | mid_single | 16066.87 |  | baseline | 0.889 | 0.899 |
| Abed | Virtus.pro | mid_single | 15641.59 |  | baseline | 0.889 | 0.899 |
| DarkMago | PTime | mid_single | 15422.95 |  | baseline | 0.889 | 0.899 |
| Nisha | Team Liquid | mid_single | 15352.46 |  | baseline | 0.889 | 0.899 |
| TaiLung | LGD Gaming | mid_single | 15259.77 |  | baseline | 0.889 | 0.899 |
| No[o]ne- | PVISION | mid_single | 14996.09 |  | baseline | 0.889 | 0.899 |

## Top Role Slots / temporal_60_40 / role_slot_series_top1

| Players | Team | Role slot | Score | Q75 | Model family | Eval sp. | Eval NDCG@5 |
|---|---|---|---:|---:|---|---:|---:|
| bzm | 1w | mid_single | 19591.88 |  | baseline | 0.876 | 0.896 |
| NothingToSay | Xtreme Gaming | mid_single | 18740.52 |  | baseline | 0.876 | 0.896 |
| Malr1ne | Team Falcons | mid_single | 18638.85 |  | baseline | 0.876 | 0.896 |
| MidOne | MOUZ | mid_single | 18238.06 |  | baseline | 0.876 | 0.896 |
| Nisha | Team Liquid | mid_single | 18088.60 |  | baseline | 0.876 | 0.896 |
| No[o]ne- | PVISION | mid_single | 17345.20 |  | baseline | 0.876 | 0.896 |
| lorenof | Nigma Galaxy | mid_single | 17293.85 |  | baseline | 0.876 | 0.896 |
| LarI | Team Spirit | mid_single | 17167.73 |  | baseline | 0.876 | 0.896 |
| Abed | Virtus.pro | mid_single | 17150.87 |  | baseline | 0.876 | 0.896 |
| RCY | GamerLegion | mid_single | 17120.96 |  | baseline | 0.876 | 0.896 |

