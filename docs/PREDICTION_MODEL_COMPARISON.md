# Prediction Model Comparison

This report compares the best classical baseline against the tuned ridge layer, the quantile q50 point forecast, and the ranking-oriented GBDT experiment.

## player_map_score / group_to_playoff

| Model | Params | MAE | Entity sp. | Top5 overlap | NDCG@5 | Regret@1 | Note |
|---|---|---:|---:|---:|---:|---:|---|
| best_baseline | segment_mean | 2500.95 | 0.729 | 0.400 | 0.857 | 2372.90 | baseline winner |
| ridge_v2 | alpha=0.50 | 2602.67 | 0.708 | 0.000 | 0.743 | 3047.25 |  |
| gbdt_rank_v1 | trees=40, lr=0.05 | 2727.43 | 0.652 | 0.200 | 0.721 | 7152.53 |  |
| quantile_q50 | - | 3177.43 | 0.625 | 0.000 | 0.754 | 3047.25 |  |

## player_map_score / temporal_60_40

| Model | Params | MAE | Entity sp. | Top5 overlap | NDCG@5 | Regret@1 | Note |
|---|---|---:|---:|---:|---:|---:|---|
| gbdt_rank_v1 | trees=16, lr=0.05 | 2980.60 | 0.889 | 0.000 | 0.807 | 2619.60 |  |
| best_baseline | shrunk_mean | 2613.84 | 0.885 | 0.000 | 0.908 | 3250.96 | baseline winner |
| ridge_v2 | alpha=0.25 | 2614.37 | 0.884 | 0.200 | 0.914 | 3250.96 |  |
| quantile_q50 | - | 3463.50 | 0.883 | 0.200 | 0.907 | 1390.63 |  |

## player_series_mean / group_to_playoff

| Model | Params | MAE | Entity sp. | Top5 overlap | NDCG@5 | Regret@1 | Note |
|---|---|---:|---:|---:|---:|---:|---|
| best_baseline | segment_mean | 1931.90 | 0.724 | 0.200 | 0.811 | 4952.58 | baseline winner |
| ridge_v2 | alpha=100.00 | 2160.61 | 0.696 | 0.000 | 0.743 | 3250.34 |  |
| gbdt_rank_v1 | trees=40, lr=0.08 | 2190.82 | 0.679 | 0.200 | 0.774 | 3793.76 |  |
| quantile_q50 | - | 2907.50 | 0.641 | 0.200 | 0.787 | 3250.34 |  |

## player_series_mean / temporal_60_40

| Model | Params | MAE | Entity sp. | Top5 overlap | NDCG@5 | Regret@1 | Note |
|---|---|---:|---:|---:|---:|---:|---|
| best_baseline | entity_mean | 1834.65 | 0.890 | 0.000 | 0.880 | 3707.04 | baseline winner |
| quantile_q50 | - | 3072.90 | 0.887 | 0.200 | 0.896 | 1622.82 |  |
| gbdt_rank_v1 | trees=24, lr=0.05 | 2162.49 | 0.881 | 0.000 | 0.808 | 3170.60 |  |
| ridge_v2 | alpha=100.00 | 2115.45 | 0.859 | 0.200 | 0.895 | 1622.82 |  |

## player_series_top1 / group_to_playoff

| Model | Params | MAE | Entity sp. | Top5 overlap | NDCG@5 | Regret@1 | Note |
|---|---|---:|---:|---:|---:|---:|---|
| best_baseline | segment_mean | 2438.89 | 0.727 | 0.200 | 0.862 | 3703.49 | baseline winner |
| ridge_v2 | alpha=100.00 | 2384.48 | 0.693 | 0.200 | 0.814 | 3673.94 |  |
| gbdt_rank_v1 | trees=40, lr=0.08 | 2575.01 | 0.682 | 0.200 | 0.814 | 3673.94 |  |
| quantile_q50 | - | 3596.34 | 0.641 | 0.200 | 0.821 | 3673.94 |  |

## player_series_top1 / temporal_60_40

| Model | Params | MAE | Entity sp. | Top5 overlap | NDCG@5 | Regret@1 | Note |
|---|---|---:|---:|---:|---:|---:|---|
| quantile_q50 | - | 3826.30 | 0.888 | 0.400 | 0.914 | 4155.04 |  |
| best_baseline | entity_mean | 2283.93 | 0.887 | 0.200 | 0.936 | 104.42 | baseline winner |
| gbdt_rank_v1 | trees=16, lr=0.05 | 2834.73 | 0.875 | 0.000 | 0.813 | 2613.04 |  |
| ridge_v2 | alpha=50.00 | 2440.86 | 0.861 | 0.200 | 0.936 | 104.42 |  |

## role_slot_map_score / group_to_playoff

| Model | Params | MAE | Entity sp. | Top5 overlap | NDCG@5 | Regret@1 | Note |
|---|---|---:|---:|---:|---:|---:|---|
| best_baseline | segment_mean | 2301.53 | 0.781 | 0.400 | 0.844 | 2258.61 | baseline winner |
| ridge_v2 | alpha=0.25 | 2520.96 | 0.676 | 0.400 | 0.829 | 2932.96 |  |
| gbdt_rank_v1 | trees=40, lr=0.08 | 2622.03 | 0.657 | 0.200 | 0.815 | 4635.20 |  |
| quantile_q50 | - | 3289.15 | 0.599 | 0.400 | 0.871 | 2932.96 |  |

## role_slot_map_score / temporal_60_40

| Model | Params | MAE | Entity sp. | Top5 overlap | NDCG@5 | Regret@1 | Note |
|---|---|---:|---:|---:|---:|---:|---|
| gbdt_rank_v1 | trees=16, lr=0.05 | 2920.78 | 0.890 | 0.000 | 0.812 | 4434.58 |  |
| best_baseline | shrunk_mean | 2557.50 | 0.888 | 0.400 | 0.926 | 2759.41 | baseline winner |
| ridge_v2 | alpha=100.00 | 2557.13 | 0.879 | 0.400 | 0.926 | 2759.41 |  |
| quantile_q50 | - | 3535.68 | 0.876 | 0.200 | 0.920 | 899.09 |  |

## role_slot_series_mean / group_to_playoff

| Model | Params | MAE | Entity sp. | Top5 overlap | NDCG@5 | Regret@1 | Note |
|---|---|---:|---:|---:|---:|---:|---|
| best_baseline | segment_mean | 1755.78 | 0.759 | 0.400 | 0.833 | 4306.62 | baseline winner |
| gbdt_rank_v1 | trees=40, lr=0.08 | 2101.95 | 0.685 | 0.200 | 0.814 | 4306.62 |  |
| ridge_v2 | alpha=100.00 | 2108.12 | 0.654 | 0.200 | 0.822 | 2604.38 |  |
| quantile_q50 | - | 3047.79 | 0.650 | 0.200 | 0.827 | 2604.38 |  |

## role_slot_series_mean / temporal_60_40

| Model | Params | MAE | Entity sp. | Top5 overlap | NDCG@5 | Regret@1 | Note |
|---|---|---:|---:|---:|---:|---:|---|
| best_baseline | shrunk_mean | 1787.30 | 0.889 | 0.400 | 0.899 | 3512.83 | baseline winner |
| gbdt_rank_v1 | trees=40, lr=0.05 | 1907.38 | 0.882 | 0.400 | 0.858 | 3512.83 |  |
| quantile_q50 | - | 3140.88 | 0.877 | 0.200 | 0.869 | 1428.61 |  |
| ridge_v2 | alpha=100.00 | 2047.01 | 0.845 | 0.400 | 0.917 | 1428.61 |  |

## role_slot_series_top1 / group_to_playoff

| Model | Params | MAE | Entity sp. | Top5 overlap | NDCG@5 | Regret@1 | Note |
|---|---|---:|---:|---:|---:|---:|---|
| best_baseline | segment_mean | 2218.66 | 0.781 | 0.400 | 0.902 | 3703.49 | baseline winner |
| ridge_v2 | alpha=100.00 | 2282.37 | 0.699 | 0.400 | 0.816 | 3673.94 |  |
| gbdt_rank_v1 | trees=40, lr=0.08 | 2471.27 | 0.681 | 0.400 | 0.828 | 3673.94 |  |
| quantile_q50 | - | 3788.18 | 0.632 | 0.400 | 0.829 | 3673.94 |  |

## role_slot_series_top1 / temporal_60_40

| Model | Params | MAE | Entity sp. | Top5 overlap | NDCG@5 | Regret@1 | Note |
|---|---|---:|---:|---:|---:|---:|---|
| best_baseline | shrunk_mean | 2162.44 | 0.876 | 0.400 | 0.896 | 2092.98 | baseline winner |
| quantile_q50 | - | 3998.47 | 0.867 | 0.200 | 0.873 | 4155.04 |  |
| gbdt_rank_v1 | trees=24, lr=0.05 | 2484.87 | 0.858 | 0.000 | 0.775 | 6337.39 |  |
| ridge_v2 | alpha=100.00 | 2330.72 | 0.853 | 0.400 | 0.901 | 4155.04 |  |

