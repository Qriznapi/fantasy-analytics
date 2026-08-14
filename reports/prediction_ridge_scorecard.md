# Prediction Ridge Scorecard

This scorecard tracks the tuned ridge layer on top of the shared richer feature foundation. Ridge v2 uses a wider feature family plus inner-train alpha selection, then compares the final runs against the best current baseline per target/split.

## Ridge Results

| Target | Split | Alpha | Tuning split | MAE | Spearman row | Spearman entity | Top5 overlap | NDCG@5 | Regret@1 |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| player_map_score | group_to_playoff | 0.50 | entity_temporal_75_25_inside_train | 2602.67 | 0.603 | 0.708 | 0.000 | 0.743 | 3047.25 |
| player_map_score | temporal_60_40 | 0.25 | entity_temporal_75_25_inside_train | 2614.37 | 0.639 | 0.884 | 0.200 | 0.914 | 3250.96 |
| player_series_mean | group_to_playoff | 100.00 | entity_temporal_75_25_inside_train | 2160.61 | 0.675 | 0.696 | 0.000 | 0.743 | 3250.34 |
| player_series_mean | temporal_60_40 | 100.00 | entity_temporal_75_25_inside_train | 2115.45 | 0.730 | 0.859 | 0.200 | 0.895 | 1622.82 |
| player_series_top1 | group_to_playoff | 100.00 | entity_temporal_75_25_inside_train | 2384.48 | 0.710 | 0.693 | 0.200 | 0.814 | 3673.94 |
| player_series_top1 | temporal_60_40 | 50.00 | entity_temporal_75_25_inside_train | 2440.86 | 0.749 | 0.861 | 0.200 | 0.936 | 104.42 |
| role_slot_map_score | group_to_playoff | 0.25 | entity_temporal_75_25_inside_train | 2520.96 | 0.575 | 0.676 | 0.400 | 0.829 | 2932.96 |
| role_slot_map_score | temporal_60_40 | 100.00 | entity_temporal_75_25_inside_train | 2557.13 | 0.641 | 0.879 | 0.400 | 0.926 | 2759.41 |
| role_slot_series_mean | group_to_playoff | 100.00 | entity_temporal_75_25_inside_train | 2108.12 | 0.607 | 0.654 | 0.200 | 0.822 | 2604.38 |
| role_slot_series_mean | temporal_60_40 | 100.00 | entity_temporal_75_25_inside_train | 2047.01 | 0.729 | 0.845 | 0.400 | 0.917 | 1428.61 |
| role_slot_series_top1 | group_to_playoff | 100.00 | entity_temporal_75_25_inside_train | 2282.37 | 0.698 | 0.699 | 0.400 | 0.816 | 3673.94 |
| role_slot_series_top1 | temporal_60_40 | 100.00 | entity_temporal_75_25_inside_train | 2330.72 | 0.732 | 0.853 | 0.400 | 0.901 | 4155.04 |

## Tuning Snapshot

| Target | Split | Alpha | Inner entity sp. | Inner NDCG@5 | Inner MAE |
|---|---|---:|---:|---:|---:|
| player_map_score | group_to_playoff | 0.50 | 0.863 | 0.887 | 2510.78 |
| player_map_score | group_to_playoff | 0.25 | 0.863 | 0.887 | 2510.74 |
| player_map_score | group_to_playoff | 1.00 | 0.863 | 0.887 | 2510.86 |
| player_map_score | temporal_60_40 | 0.25 | 0.760 | 0.785 | 2334.11 |
| player_map_score | temporal_60_40 | 0.50 | 0.760 | 0.785 | 2334.25 |
| player_map_score | temporal_60_40 | 1.00 | 0.759 | 0.785 | 2334.48 |
| player_series_mean | group_to_playoff | 100.00 | 0.846 | 0.918 | 1982.77 |
| player_series_mean | group_to_playoff | 50.00 | 0.840 | 0.918 | 2026.39 |
| player_series_mean | group_to_playoff | 25.00 | 0.837 | 0.918 | 2054.36 |
| player_series_mean | temporal_60_40 | 100.00 | 0.677 | 0.713 | 2269.11 |
| player_series_mean | temporal_60_40 | 50.00 | 0.671 | 0.712 | 2293.93 |
| player_series_mean | temporal_60_40 | 25.00 | 0.670 | 0.712 | 2309.87 |
| player_series_top1 | group_to_playoff | 100.00 | 0.852 | 0.894 | 2356.20 |
| player_series_top1 | group_to_playoff | 50.00 | 0.850 | 0.894 | 2371.34 |
| player_series_top1 | group_to_playoff | 25.00 | 0.849 | 0.894 | 2380.03 |
| player_series_top1 | temporal_60_40 | 50.00 | 0.662 | 0.786 | 2762.22 |
| player_series_top1 | temporal_60_40 | 100.00 | 0.661 | 0.785 | 2738.46 |
| player_series_top1 | temporal_60_40 | 25.00 | 0.661 | 0.786 | 2775.55 |
| role_slot_map_score | group_to_playoff | 0.25 | 0.849 | 0.967 | 2469.96 |
| role_slot_map_score | group_to_playoff | 0.50 | 0.849 | 0.964 | 2470.23 |
| role_slot_map_score | group_to_playoff | 1.00 | 0.848 | 0.961 | 2470.71 |
| role_slot_map_score | temporal_60_40 | 100.00 | 0.708 | 0.800 | 2234.77 |
| role_slot_map_score | temporal_60_40 | 5.00 | 0.707 | 0.800 | 2241.31 |
| role_slot_map_score | temporal_60_40 | 2.00 | 0.707 | 0.800 | 2240.71 |
| role_slot_series_mean | group_to_playoff | 100.00 | 0.833 | 0.912 | 1951.22 |
| role_slot_series_mean | group_to_playoff | 50.00 | 0.818 | 0.927 | 2015.83 |
| role_slot_series_mean | group_to_playoff | 25.00 | 0.809 | 0.928 | 2061.15 |
| role_slot_series_mean | temporal_60_40 | 100.00 | 0.651 | 0.708 | 2256.34 |
| role_slot_series_mean | temporal_60_40 | 50.00 | 0.644 | 0.726 | 2311.42 |
| role_slot_series_mean | temporal_60_40 | 25.00 | 0.642 | 0.754 | 2352.01 |
| role_slot_series_top1 | group_to_playoff | 100.00 | 0.852 | 0.880 | 2262.20 |
| role_slot_series_top1 | group_to_playoff | 50.00 | 0.846 | 0.880 | 2293.68 |
| role_slot_series_top1 | group_to_playoff | 25.00 | 0.845 | 0.880 | 2315.22 |
| role_slot_series_top1 | temporal_60_40 | 100.00 | 0.670 | 0.795 | 2621.79 |
| role_slot_series_top1 | temporal_60_40 | 50.00 | 0.665 | 0.795 | 2661.87 |
| role_slot_series_top1 | temporal_60_40 | 25.00 | 0.663 | 0.795 | 2687.32 |

## Ridge vs Best Baseline

| Target | Split | Best baseline | Ridge entity sp. | Baseline entity sp. | Delta sp. | Ridge NDCG@5 | Baseline NDCG@5 | Delta NDCG@5 | Ridge regret@1 | Baseline regret@1 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| player_map_score | group_to_playoff | segment_mean | 0.708 | 0.729 | -0.021 | 0.743 | 0.857 | -0.114 | 3047.25 | 2372.90 |
| player_map_score | temporal_60_40 | shrunk_mean | 0.884 | 0.885 | -0.001 | 0.914 | 0.908 | +0.005 | 3250.96 | 3250.96 |
| player_series_mean | group_to_playoff | segment_mean | 0.696 | 0.724 | -0.028 | 0.743 | 0.811 | -0.068 | 3250.34 | 4952.58 |
| player_series_mean | temporal_60_40 | entity_mean | 0.859 | 0.890 | -0.031 | 0.895 | 0.880 | +0.015 | 1622.82 | 3707.04 |
| player_series_top1 | group_to_playoff | segment_mean | 0.693 | 0.727 | -0.034 | 0.814 | 0.862 | -0.048 | 3673.94 | 3703.49 |
| player_series_top1 | temporal_60_40 | entity_mean | 0.861 | 0.887 | -0.026 | 0.936 | 0.936 | +0.000 | 104.42 | 104.42 |
| role_slot_map_score | group_to_playoff | segment_mean | 0.676 | 0.781 | -0.105 | 0.829 | 0.844 | -0.015 | 2932.96 | 2258.61 |
| role_slot_map_score | temporal_60_40 | shrunk_mean | 0.879 | 0.888 | -0.009 | 0.926 | 0.926 | +0.000 | 2759.41 | 2759.41 |
| role_slot_series_mean | group_to_playoff | segment_mean | 0.654 | 0.759 | -0.105 | 0.822 | 0.833 | -0.010 | 2604.38 | 4306.62 |
| role_slot_series_mean | temporal_60_40 | shrunk_mean | 0.845 | 0.889 | -0.044 | 0.917 | 0.899 | +0.018 | 1428.61 | 3512.83 |
| role_slot_series_top1 | group_to_playoff | segment_mean | 0.699 | 0.781 | -0.082 | 0.816 | 0.902 | -0.086 | 3673.94 | 3703.49 |
| role_slot_series_top1 | temporal_60_40 | shrunk_mean | 0.853 | 0.876 | -0.023 | 0.901 | 0.896 | +0.005 | 4155.04 | 2092.98 |

