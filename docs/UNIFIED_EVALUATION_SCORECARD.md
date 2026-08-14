# Unified Evaluation Scorecard

This scorecard is the unified evaluation surface for Project F. It normalizes prediction, reliability, optimizer, and simulation layers into one comparison registry.

## Comparable Backtests

| Layer | Family | Surface | Entity | Task | Target | Split | Scope | Spearman | NDCG@5 | Top5 | MAE | Regret@1 |
|---|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|
| optimizer | optimizer_v2 | all | player | optimizer | - | group_to_playoff | all | 0.675 | 0.794 | 0.000 | 2708.34 | 3072.51 |
| optimizer | optimizer_v2 | all | role_slot | optimizer | - | group_to_playoff | all | 0.649 | 0.872 | 0.400 | 2987.60 | 3032.21 |
| optimizer | optimizer_foundation | all | player | optimizer | - | group_to_playoff | all | 0.643 | 0.787 | 0.200 | 2366.68 | 3072.51 |
| optimizer | optimizer_foundation | all | role_slot | optimizer | - | group_to_playoff | all | 0.624 | 0.869 | 0.400 | 2256.33 | 3032.21 |
| optimizer | optimizer_v2 | ti2026 | player | optimizer | - | group_to_playoff | ti2026 | 0.697 | 0.794 | 0.000 | 2379.07 | 3072.51 |
| optimizer | optimizer_v2 | ti2026 | role_slot | optimizer | - | group_to_playoff | ti2026 | 0.683 | 0.872 | 0.400 | 3300.22 | 3032.21 |
| optimizer | optimizer_foundation | ti2026 | player | optimizer | - | group_to_playoff | ti2026 | 0.674 | 0.787 | 0.200 | 2118.45 | 3072.51 |
| optimizer | optimizer_foundation | ti2026 | role_slot | optimizer | - | group_to_playoff | ti2026 | 0.662 | 0.869 | 0.400 | 1974.86 | 3032.21 |
| prediction | baseline | segment_mean | player | prediction | player_map_score | group_to_playoff | - | 0.729 | 0.857 | 0.400 | 2500.95 | 2372.90 |
| prediction | production | baseline::segment_mean | player | prediction | player_map_score | group_to_playoff | - | 0.729 | 0.857 | 0.400 | 2500.95 | 2372.90 |
| prediction | baseline | entity_mean | player | prediction | player_map_score | group_to_playoff | - | 0.708 | 0.743 | 0.000 | 2602.39 | 3047.25 |
| prediction | ridge | ridge_v2(alpha=0.5) | player | prediction | player_map_score | group_to_playoff | - | 0.708 | 0.743 | 0.000 | 2602.67 | 3047.25 |
| prediction | baseline | shrunk_mean | player | prediction | player_map_score | group_to_playoff | - | 0.698 | 0.760 | 0.200 | 2583.80 | 3047.25 |
| prediction | gbdt | gbdt_rank_v1(trees=40,lr=0.05) | player | prediction | player_map_score | group_to_playoff | - | 0.652 | 0.721 | 0.200 | 2727.43 | 7152.53 |
| prediction | baseline | recent_mean_5 | player | prediction | player_map_score | group_to_playoff | - | 0.635 | 0.747 | 0.000 | 2842.54 | 3047.25 |
| prediction | quantile | quantile_linear_v1 | player | prediction | player_map_score | group_to_playoff | - | 0.625 | 0.754 | 0.000 | 3177.43 | 3047.25 |
| prediction | baseline | team_segment_mean | player | prediction | player_map_score | group_to_playoff | - | 0.613 | 0.805 | 0.200 | 2691.67 | 3047.25 |
| prediction | baseline | entity_p75 | player | prediction | player_map_score | group_to_playoff | - | 0.611 | 0.741 | 0.000 | 3137.11 | 3047.25 |
| prediction | baseline | recent_p75_5 | player | prediction | player_map_score | group_to_playoff | - | 0.581 | 0.803 | 0.000 | 3267.41 | 3047.25 |
| prediction | baseline | global_mean | player | prediction | player_map_score | group_to_playoff | - | -0.102 | 0.747 | 0.200 | 3301.04 | 4709.86 |
| prediction | gbdt | gbdt_rank_v1(trees=16,lr=0.05) | player | prediction | player_map_score | temporal_60_40 | - | 0.889 | 0.807 | 0.000 | 2980.60 | 2619.60 |
| prediction | production | gbdt::gbdt_rank_v1 | player | prediction | player_map_score | temporal_60_40 | - | 0.889 | 0.807 | 0.000 | 2980.60 | 2619.60 |
| prediction | baseline | shrunk_mean | player | prediction | player_map_score | temporal_60_40 | - | 0.885 | 0.908 | 0.000 | 2613.84 | 3250.96 |
| prediction | ridge | ridge_v2(alpha=0.25) | player | prediction | player_map_score | temporal_60_40 | - | 0.884 | 0.914 | 0.200 | 2614.37 | 3250.96 |
| prediction | baseline | entity_mean | player | prediction | player_map_score | temporal_60_40 | - | 0.884 | 0.914 | 0.200 | 2614.49 | 3250.96 |
| prediction | quantile | quantile_linear_v1 | player | prediction | player_map_score | temporal_60_40 | - | 0.883 | 0.907 | 0.200 | 3463.50 | 1390.63 |
| prediction | baseline | entity_p75 | player | prediction | player_map_score | temporal_60_40 | - | 0.875 | 0.850 | 0.200 | 2805.17 | 4592.65 |
| prediction | baseline | team_segment_mean | player | prediction | player_map_score | temporal_60_40 | - | 0.836 | 0.908 | 0.000 | 2700.94 | 3250.96 |
| prediction | baseline | recent_mean_5 | player | prediction | player_map_score | temporal_60_40 | - | 0.832 | 0.868 | 0.200 | 2790.88 | 4592.65 |
| prediction | baseline | segment_mean | player | prediction | player_map_score | temporal_60_40 | - | 0.825 | 0.810 | 0.000 | 2705.65 | 3250.96 |
| prediction | baseline | recent_p75_5 | player | prediction | player_map_score | temporal_60_40 | - | 0.810 | 0.872 | 0.200 | 3062.90 | 1383.02 |
| prediction | baseline | global_mean | player | prediction | player_map_score | temporal_60_40 | - | 0.000 | 0.657 | 0.000 | 3491.75 | 9102.64 |
| prediction | baseline | segment_mean | player | prediction | player_series_mean | group_to_playoff | - | 0.724 | 0.811 | 0.200 | 1931.90 | 4952.58 |
| prediction | production | baseline::segment_mean | player | prediction | player_series_mean | group_to_playoff | - | 0.724 | 0.811 | 0.200 | 1931.90 | 4952.58 |
| prediction | baseline | entity_mean | player | prediction | player_series_mean | group_to_playoff | - | 0.713 | 0.743 | 0.000 | 2113.99 | 3250.34 |
| prediction | baseline | shrunk_mean | player | prediction | player_series_mean | group_to_playoff | - | 0.698 | 0.748 | 0.000 | 2036.02 | 3250.34 |
| prediction | ridge | ridge_v2(alpha=100.0) | player | prediction | player_series_mean | group_to_playoff | - | 0.696 | 0.743 | 0.000 | 2160.61 | 3250.34 |
| prediction | baseline | recent_mean_5 | player | prediction | player_series_mean | group_to_playoff | - | 0.690 | 0.755 | 0.200 | 2085.92 | 3250.34 |
| prediction | gbdt | gbdt_rank_v1(trees=40,lr=0.08) | player | prediction | player_series_mean | group_to_playoff | - | 0.679 | 0.774 | 0.200 | 2190.82 | 3793.76 |
| prediction | quantile | quantile_linear_v1 | player | prediction | player_series_mean | group_to_playoff | - | 0.641 | 0.787 | 0.200 | 2907.50 | 3250.34 |
| prediction | baseline | team_segment_mean | player | prediction | player_series_mean | group_to_playoff | - | 0.627 | 0.793 | 0.200 | 2157.68 | 3250.34 |
| prediction | baseline | recent_p75_5 | player | prediction | player_series_mean | group_to_playoff | - | 0.626 | 0.760 | 0.200 | 2571.18 | 3250.34 |
| prediction | baseline | entity_p75 | player | prediction | player_series_mean | group_to_playoff | - | 0.625 | 0.792 | 0.200 | 2657.42 | 3250.34 |
| prediction | baseline | global_mean | player | prediction | player_series_mean | group_to_playoff | - | 0.000 | 0.749 | 0.400 | 2970.85 | 5054.36 |
| prediction | baseline | entity_mean | player | prediction | player_series_mean | temporal_60_40 | - | 0.890 | 0.880 | 0.000 | 1834.65 | 3707.04 |
| prediction | production | baseline::entity_mean | player | prediction | player_series_mean | temporal_60_40 | - | 0.890 | 0.880 | 0.000 | 1834.65 | 3707.04 |
| prediction | baseline | recent_mean_5 | player | prediction | player_series_mean | temporal_60_40 | - | 0.889 | 0.880 | 0.000 | 1839.52 | 3707.04 |
| prediction | quantile | quantile_linear_v1 | player | prediction | player_series_mean | temporal_60_40 | - | 0.887 | 0.896 | 0.200 | 3072.90 | 1622.82 |
| prediction | baseline | shrunk_mean | player | prediction | player_series_mean | temporal_60_40 | - | 0.886 | 0.885 | 0.200 | 1852.73 | 3707.04 |
| prediction | gbdt | gbdt_rank_v1(trees=24,lr=0.05) | player | prediction | player_series_mean | temporal_60_40 | - | 0.881 | 0.808 | 0.000 | 2162.49 | 3170.60 |
| prediction | baseline | recent_p75_5 | player | prediction | player_series_mean | temporal_60_40 | - | 0.876 | 0.843 | 0.000 | 2040.55 | 3293.91 |
| prediction | baseline | entity_p75 | player | prediction | player_series_mean | temporal_60_40 | - | 0.873 | 0.838 | 0.000 | 2065.36 | 3293.91 |
| prediction | ridge | ridge_v2(alpha=100.0) | player | prediction | player_series_mean | temporal_60_40 | - | 0.859 | 0.895 | 0.200 | 2115.45 | 1622.82 |
| prediction | baseline | team_segment_mean | player | prediction | player_series_mean | temporal_60_40 | - | 0.833 | 0.885 | 0.200 | 1977.08 | 3707.04 |
| prediction | baseline | segment_mean | player | prediction | player_series_mean | temporal_60_40 | - | 0.807 | 0.792 | 0.000 | 2008.67 | 3707.04 |
| prediction | baseline | global_mean | player | prediction | player_series_mean | temporal_60_40 | - | 0.000 | 0.629 | 0.000 | 3066.46 | 9495.66 |
| prediction | baseline | segment_mean | player | prediction | player_series_top1 | group_to_playoff | - | 0.727 | 0.862 | 0.200 | 2438.89 | 3703.49 |
| prediction | production | baseline::segment_mean | player | prediction | player_series_top1 | group_to_playoff | - | 0.727 | 0.862 | 0.200 | 2438.89 | 3703.49 |
| prediction | ridge | ridge_v2(alpha=100.0) | player | prediction | player_series_top1 | group_to_playoff | - | 0.693 | 0.814 | 0.200 | 2384.48 | 3673.94 |
| prediction | gbdt | gbdt_rank_v1(trees=40,lr=0.08) | player | prediction | player_series_top1 | group_to_playoff | - | 0.682 | 0.814 | 0.200 | 2575.01 | 3673.94 |
| prediction | baseline | shrunk_mean | player | prediction | player_series_top1 | group_to_playoff | - | 0.671 | 0.781 | 0.000 | 2528.26 | 3673.94 |
| prediction | baseline | entity_p75 | player | prediction | player_series_top1 | group_to_playoff | - | 0.659 | 0.772 | 0.000 | 3088.33 | 5197.05 |
| prediction | baseline | entity_mean | player | prediction | player_series_top1 | group_to_playoff | - | 0.656 | 0.738 | 0.000 | 2558.80 | 3673.94 |
| prediction | quantile | quantile_linear_v1 | player | prediction | player_series_top1 | group_to_playoff | - | 0.641 | 0.821 | 0.200 | 3596.34 | 3673.94 |
| prediction | baseline | recent_p75_5 | player | prediction | player_series_top1 | group_to_playoff | - | 0.626 | 0.856 | 0.200 | 3031.53 | 3673.94 |
| prediction | baseline | recent_mean_5 | player | prediction | player_series_top1 | group_to_playoff | - | 0.625 | 0.774 | 0.000 | 2587.18 | 3673.94 |
| prediction | baseline | team_segment_mean | player | prediction | player_series_top1 | group_to_playoff | - | 0.614 | 0.781 | 0.000 | 2640.07 | 3673.94 |
| prediction | baseline | global_mean | player | prediction | player_series_top1 | group_to_playoff | - | 0.000 | 0.732 | 0.200 | 3700.71 | 6312.52 |
| prediction | production | quantile::quantile_linear_v1 | player | prediction | player_series_top1 | temporal_60_40 | - | 0.888 | 0.914 | 0.400 | 3826.30 | 4155.04 |
| prediction | quantile | quantile_linear_v1 | player | prediction | player_series_top1 | temporal_60_40 | - | 0.888 | 0.914 | 0.400 | 3826.30 | 4155.04 |
| prediction | baseline | entity_mean | player | prediction | player_series_top1 | temporal_60_40 | - | 0.887 | 0.936 | 0.200 | 2283.93 | 104.42 |
| prediction | baseline | recent_mean_5 | player | prediction | player_series_top1 | temporal_60_40 | - | 0.886 | 0.936 | 0.200 | 2294.01 | 104.42 |
| prediction | baseline | shrunk_mean | player | prediction | player_series_top1 | temporal_60_40 | - | 0.876 | 0.912 | 0.200 | 2370.27 | 2092.98 |
| prediction | gbdt | gbdt_rank_v1(trees=16,lr=0.05) | player | prediction | player_series_top1 | temporal_60_40 | - | 0.875 | 0.813 | 0.000 | 2834.73 | 2613.04 |
| prediction | baseline | recent_p75_5 | player | prediction | player_series_top1 | temporal_60_40 | - | 0.875 | 0.901 | 0.200 | 2360.18 | 104.42 |
| prediction | baseline | entity_p75 | player | prediction | player_series_top1 | temporal_60_40 | - | 0.874 | 0.901 | 0.200 | 2376.50 | 104.42 |
| prediction | ridge | ridge_v2(alpha=50.0) | player | prediction | player_series_top1 | temporal_60_40 | - | 0.861 | 0.936 | 0.200 | 2440.86 | 104.42 |
| prediction | baseline | team_segment_mean | player | prediction | player_series_top1 | temporal_60_40 | - | 0.837 | 0.867 | 0.000 | 2468.59 | 2092.98 |
| prediction | baseline | segment_mean | player | prediction | player_series_top1 | temporal_60_40 | - | 0.805 | 0.794 | 0.000 | 2604.65 | 2092.98 |
| prediction | baseline | global_mean | player | prediction | player_series_top1 | temporal_60_40 | - | 0.000 | 0.674 | 0.000 | 3815.33 | 10849.68 |
| prediction | baseline | segment_mean | role_slot | prediction | role_slot_map_score | group_to_playoff | - | 0.781 | 0.844 | 0.400 | 2301.53 | 2258.61 |
| prediction | production | baseline::segment_mean | role_slot | prediction | role_slot_map_score | group_to_playoff | - | 0.781 | 0.844 | 0.400 | 2301.53 | 2258.61 |
| prediction | baseline | shrunk_mean | role_slot | prediction | role_slot_map_score | group_to_playoff | - | 0.676 | 0.829 | 0.400 | 2488.76 | 2932.96 |
| prediction | baseline | entity_mean | role_slot | prediction | role_slot_map_score | group_to_playoff | - | 0.676 | 0.829 | 0.400 | 2520.54 | 2932.96 |
| prediction | baseline | team_segment_mean | role_slot | prediction | role_slot_map_score | group_to_playoff | - | 0.676 | 0.829 | 0.400 | 2520.54 | 2932.96 |
| prediction | ridge | ridge_v2(alpha=0.25) | role_slot | prediction | role_slot_map_score | group_to_playoff | - | 0.676 | 0.829 | 0.400 | 2520.96 | 2932.96 |
| prediction | gbdt | gbdt_rank_v1(trees=40,lr=0.08) | role_slot | prediction | role_slot_map_score | group_to_playoff | - | 0.657 | 0.815 | 0.200 | 2622.03 | 4635.20 |
| prediction | baseline | recent_mean_5 | role_slot | prediction | role_slot_map_score | group_to_playoff | - | 0.627 | 0.826 | 0.200 | 2795.18 | 2932.96 |
| prediction | baseline | entity_p75 | role_slot | prediction | role_slot_map_score | group_to_playoff | - | 0.602 | 0.822 | 0.200 | 3039.01 | 2932.96 |
| prediction | quantile | quantile_linear_v1 | role_slot | prediction | role_slot_map_score | group_to_playoff | - | 0.599 | 0.871 | 0.400 | 3289.15 | 2932.96 |
| prediction | baseline | recent_p75_5 | role_slot | prediction | role_slot_map_score | group_to_playoff | - | 0.527 | 0.828 | 0.200 | 3328.77 | 2932.96 |
| prediction | baseline | global_mean | role_slot | prediction | role_slot_map_score | group_to_playoff | - | 0.000 | 0.783 | 0.200 | 3369.20 | 3259.01 |
| prediction | gbdt | gbdt_rank_v1(trees=16,lr=0.05) | role_slot | prediction | role_slot_map_score | temporal_60_40 | - | 0.890 | 0.812 | 0.000 | 2920.78 | 4434.58 |
| prediction | production | gbdt::gbdt_rank_v1 | role_slot | prediction | role_slot_map_score | temporal_60_40 | - | 0.890 | 0.812 | 0.000 | 2920.78 | 4434.58 |
| prediction | baseline | shrunk_mean | role_slot | prediction | role_slot_map_score | temporal_60_40 | - | 0.888 | 0.926 | 0.400 | 2557.50 | 2759.41 |
| prediction | baseline | team_segment_mean | role_slot | prediction | role_slot_map_score | temporal_60_40 | - | 0.879 | 0.926 | 0.400 | 2563.57 | 2759.41 |
| prediction | baseline | entity_mean | role_slot | prediction | role_slot_map_score | temporal_60_40 | - | 0.879 | 0.926 | 0.400 | 2563.57 | 2759.41 |
| prediction | ridge | ridge_v2(alpha=100.0) | role_slot | prediction | role_slot_map_score | temporal_60_40 | - | 0.879 | 0.926 | 0.400 | 2557.13 | 2759.41 |
| prediction | quantile | quantile_linear_v1 | role_slot | prediction | role_slot_map_score | temporal_60_40 | - | 0.876 | 0.920 | 0.200 | 3535.68 | 899.09 |
| prediction | baseline | entity_p75 | role_slot | prediction | role_slot_map_score | temporal_60_40 | - | 0.875 | 0.879 | 0.200 | 2714.56 | 2759.41 |
| prediction | baseline | segment_mean | role_slot | prediction | role_slot_map_score | temporal_60_40 | - | 0.852 | 0.818 | 0.000 | 2604.13 | 2759.41 |
| prediction | baseline | recent_mean_5 | role_slot | prediction | role_slot_map_score | temporal_60_40 | - | 0.803 | 0.900 | 0.200 | 2744.89 | 899.09 |
| prediction | baseline | recent_p75_5 | role_slot | prediction | role_slot_map_score | temporal_60_40 | - | 0.788 | 0.847 | 0.000 | 2992.84 | 3625.40 |
| prediction | baseline | global_mean | role_slot | prediction | role_slot_map_score | temporal_60_40 | - | -0.070 | 0.743 | 0.000 | 3568.93 | 4434.58 |
| prediction | baseline | segment_mean | role_slot | prediction | role_slot_series_mean | group_to_playoff | - | 0.759 | 0.833 | 0.400 | 1755.78 | 4306.62 |
| prediction | production | baseline::segment_mean | role_slot | prediction | role_slot_series_mean | group_to_playoff | - | 0.759 | 0.833 | 0.400 | 1755.78 | 4306.62 |
| prediction | baseline | recent_mean_5 | role_slot | prediction | role_slot_series_mean | group_to_playoff | - | 0.693 | 0.830 | 0.400 | 2029.00 | 2604.38 |
| prediction | baseline | shrunk_mean | role_slot | prediction | role_slot_series_mean | group_to_playoff | - | 0.691 | 0.822 | 0.200 | 1985.40 | 2604.38 |
| prediction | baseline | entity_mean | role_slot | prediction | role_slot_series_mean | group_to_playoff | - | 0.691 | 0.822 | 0.200 | 2042.89 | 2604.38 |
| prediction | baseline | team_segment_mean | role_slot | prediction | role_slot_series_mean | group_to_playoff | - | 0.691 | 0.822 | 0.200 | 2042.89 | 2604.38 |
| prediction | gbdt | gbdt_rank_v1(trees=40,lr=0.08) | role_slot | prediction | role_slot_series_mean | group_to_playoff | - | 0.685 | 0.814 | 0.200 | 2101.95 | 4306.62 |
| prediction | ridge | ridge_v2(alpha=100.0) | role_slot | prediction | role_slot_series_mean | group_to_playoff | - | 0.654 | 0.822 | 0.200 | 2108.12 | 2604.38 |
| prediction | baseline | recent_p75_5 | role_slot | prediction | role_slot_series_mean | group_to_playoff | - | 0.653 | 0.838 | 0.400 | 2557.02 | 2604.38 |
| prediction | quantile | quantile_linear_v1 | role_slot | prediction | role_slot_series_mean | group_to_playoff | - | 0.650 | 0.827 | 0.200 | 3047.79 | 2604.38 |
| prediction | baseline | entity_p75 | role_slot | prediction | role_slot_series_mean | group_to_playoff | - | 0.650 | 0.827 | 0.200 | 2652.43 | 2604.38 |
| prediction | baseline | global_mean | role_slot | prediction | role_slot_series_mean | group_to_playoff | - | 0.000 | 0.793 | 0.200 | 3055.72 | 2763.65 |
| prediction | baseline | shrunk_mean | role_slot | prediction | role_slot_series_mean | temporal_60_40 | - | 0.889 | 0.899 | 0.400 | 1787.30 | 3512.83 |
| prediction | production | baseline::shrunk_mean | role_slot | prediction | role_slot_series_mean | temporal_60_40 | - | 0.889 | 0.899 | 0.400 | 1787.30 | 3512.83 |
| prediction | gbdt | gbdt_rank_v1(trees=40,lr=0.05) | role_slot | prediction | role_slot_series_mean | temporal_60_40 | - | 0.882 | 0.858 | 0.400 | 1907.38 | 3512.83 |
| prediction | baseline | recent_mean_5 | role_slot | prediction | role_slot_series_mean | temporal_60_40 | - | 0.880 | 0.899 | 0.400 | 1822.45 | 3512.83 |
| prediction | baseline | entity_mean | role_slot | prediction | role_slot_series_mean | temporal_60_40 | - | 0.879 | 0.899 | 0.400 | 1819.73 | 3512.83 |
| prediction | baseline | team_segment_mean | role_slot | prediction | role_slot_series_mean | temporal_60_40 | - | 0.879 | 0.899 | 0.400 | 1819.73 | 3512.83 |
| prediction | quantile | quantile_linear_v1 | role_slot | prediction | role_slot_series_mean | temporal_60_40 | - | 0.877 | 0.869 | 0.200 | 3140.88 | 1428.61 |
| prediction | baseline | entity_p75 | role_slot | prediction | role_slot_series_mean | temporal_60_40 | - | 0.873 | 0.847 | 0.200 | 1978.13 | 2300.20 |
| prediction | baseline | recent_p75_5 | role_slot | prediction | role_slot_series_mean | temporal_60_40 | - | 0.872 | 0.855 | 0.200 | 1971.30 | 2300.20 |
| prediction | baseline | segment_mean | role_slot | prediction | role_slot_series_mean | temporal_60_40 | - | 0.864 | 0.803 | 0.000 | 1873.95 | 3512.83 |
| prediction | ridge | ridge_v2(alpha=100.0) | role_slot | prediction | role_slot_series_mean | temporal_60_40 | - | 0.845 | 0.917 | 0.400 | 2047.01 | 1428.61 |
| prediction | baseline | global_mean | role_slot | prediction | role_slot_series_mean | temporal_60_40 | - | 0.000 | 0.712 | 0.000 | 3141.81 | 5202.31 |
| prediction | baseline | segment_mean | role_slot | prediction | role_slot_series_top1 | group_to_playoff | - | 0.781 | 0.902 | 0.400 | 2218.66 | 3703.49 |
| prediction | production | baseline::segment_mean | role_slot | prediction | role_slot_series_top1 | group_to_playoff | - | 0.781 | 0.902 | 0.400 | 2218.66 | 3703.49 |
| prediction | ridge | ridge_v2(alpha=100.0) | role_slot | prediction | role_slot_series_top1 | group_to_playoff | - | 0.699 | 0.816 | 0.400 | 2282.37 | 3673.94 |
| prediction | baseline | shrunk_mean | role_slot | prediction | role_slot_series_top1 | group_to_playoff | - | 0.689 | 0.816 | 0.400 | 2369.45 | 3673.94 |
| prediction | baseline | entity_mean | role_slot | prediction | role_slot_series_top1 | group_to_playoff | - | 0.683 | 0.816 | 0.400 | 2418.48 | 3673.94 |
| prediction | baseline | team_segment_mean | role_slot | prediction | role_slot_series_top1 | group_to_playoff | - | 0.683 | 0.816 | 0.400 | 2418.48 | 3673.94 |
| prediction | gbdt | gbdt_rank_v1(trees=40,lr=0.08) | role_slot | prediction | role_slot_series_top1 | group_to_playoff | - | 0.681 | 0.828 | 0.400 | 2471.27 | 3673.94 |
| prediction | baseline | recent_mean_5 | role_slot | prediction | role_slot_series_top1 | group_to_playoff | - | 0.662 | 0.809 | 0.400 | 2463.67 | 3673.94 |
| prediction | baseline | entity_p75 | role_slot | prediction | role_slot_series_top1 | group_to_playoff | - | 0.643 | 0.857 | 0.400 | 2912.16 | 5197.05 |
| prediction | baseline | recent_p75_5 | role_slot | prediction | role_slot_series_top1 | group_to_playoff | - | 0.637 | 0.829 | 0.400 | 2889.22 | 3673.94 |
| prediction | quantile | quantile_linear_v1 | role_slot | prediction | role_slot_series_top1 | group_to_playoff | - | 0.632 | 0.829 | 0.400 | 3788.18 | 3673.94 |
| prediction | baseline | global_mean | role_slot | prediction | role_slot_series_top1 | group_to_playoff | - | -0.277 | 0.622 | 0.000 | 3799.47 | 9571.45 |
| prediction | baseline | shrunk_mean | role_slot | prediction | role_slot_series_top1 | temporal_60_40 | - | 0.876 | 0.896 | 0.400 | 2162.44 | 2092.98 |
| prediction | production | baseline::shrunk_mean | role_slot | prediction | role_slot_series_top1 | temporal_60_40 | - | 0.876 | 0.896 | 0.400 | 2162.44 | 2092.98 |
| prediction | baseline | recent_mean_5 | role_slot | prediction | role_slot_series_top1 | temporal_60_40 | - | 0.875 | 0.896 | 0.400 | 2165.04 | 2092.98 |
| prediction | baseline | entity_mean | role_slot | prediction | role_slot_series_top1 | temporal_60_40 | - | 0.875 | 0.896 | 0.400 | 2146.91 | 2092.98 |
| prediction | baseline | team_segment_mean | role_slot | prediction | role_slot_series_top1 | temporal_60_40 | - | 0.875 | 0.896 | 0.400 | 2146.91 | 2092.98 |
| prediction | quantile | quantile_linear_v1 | role_slot | prediction | role_slot_series_top1 | temporal_60_40 | - | 0.867 | 0.873 | 0.200 | 3998.47 | 4155.04 |
| prediction | gbdt | gbdt_rank_v1(trees=24,lr=0.05) | role_slot | prediction | role_slot_series_top1 | temporal_60_40 | - | 0.858 | 0.775 | 0.000 | 2484.87 | 6337.39 |
| prediction | baseline | entity_p75 | role_slot | prediction | role_slot_series_top1 | temporal_60_40 | - | 0.854 | 0.872 | 0.200 | 2229.25 | 4155.04 |
| prediction | ridge | ridge_v2(alpha=100.0) | role_slot | prediction | role_slot_series_top1 | temporal_60_40 | - | 0.853 | 0.901 | 0.400 | 2330.72 | 4155.04 |
| prediction | baseline | recent_p75_5 | role_slot | prediction | role_slot_series_top1 | temporal_60_40 | - | 0.851 | 0.873 | 0.200 | 2235.26 | 4155.04 |
| prediction | baseline | segment_mean | role_slot | prediction | role_slot_series_top1 | temporal_60_40 | - | 0.834 | 0.809 | 0.200 | 2399.18 | 2092.98 |
| prediction | baseline | global_mean | role_slot | prediction | role_slot_series_top1 | temporal_60_40 | - | 0.000 | 0.736 | 0.200 | 3968.20 | 6367.71 |
| reliability | reliability_foundation | series_mean_plus_top1_v1 | player | reliability | - | group_to_playoff | all | 0.586 | 0.719 | 0.000 | 3014.90 | 4703.09 |
| reliability | reliability_foundation | series_mean_plus_top1_v1 | role_slot | reliability | - | group_to_playoff | all | 0.541 | 0.812 | 0.200 | 2942.97 | 4662.79 |

## Best Surfaces / optimizer / player

| Family | Surface | Target | Split | Scope | Spearman | NDCG@5 | Top5 | MAE |
|---|---|---|---|---|---:|---:|---:|---:|
| optimizer_v2 | all | - | group_to_playoff | all | 0.675 | 0.794 | 0.000 | 2708.34 |
| optimizer_foundation | all | - | group_to_playoff | all | 0.643 | 0.787 | 0.200 | 2366.68 |
| optimizer_v2 | ti2026 | - | group_to_playoff | ti2026 | 0.697 | 0.794 | 0.000 | 2379.07 |
| optimizer_foundation | ti2026 | - | group_to_playoff | ti2026 | 0.674 | 0.787 | 0.200 | 2118.45 |

## Best Surfaces / optimizer / role_slot

| Family | Surface | Target | Split | Scope | Spearman | NDCG@5 | Top5 | MAE |
|---|---|---|---|---|---:|---:|---:|---:|
| optimizer_v2 | all | - | group_to_playoff | all | 0.649 | 0.872 | 0.400 | 2987.60 |
| optimizer_foundation | all | - | group_to_playoff | all | 0.624 | 0.869 | 0.400 | 2256.33 |
| optimizer_v2 | ti2026 | - | group_to_playoff | ti2026 | 0.683 | 0.872 | 0.400 | 3300.22 |
| optimizer_foundation | ti2026 | - | group_to_playoff | ti2026 | 0.662 | 0.869 | 0.400 | 1974.86 |

## Best Surfaces / prediction / player

| Family | Surface | Target | Split | Scope | Spearman | NDCG@5 | Top5 | MAE |
|---|---|---|---|---|---:|---:|---:|---:|
| baseline | segment_mean | player_map_score | group_to_playoff | - | 0.729 | 0.857 | 0.400 | 2500.95 |
| production | baseline::segment_mean | player_map_score | group_to_playoff | - | 0.729 | 0.857 | 0.400 | 2500.95 |
| baseline | entity_mean | player_map_score | group_to_playoff | - | 0.708 | 0.743 | 0.000 | 2602.39 |
| ridge | ridge_v2(alpha=0.5) | player_map_score | group_to_playoff | - | 0.708 | 0.743 | 0.000 | 2602.67 |
| baseline | shrunk_mean | player_map_score | group_to_playoff | - | 0.698 | 0.760 | 0.200 | 2583.80 |
| gbdt | gbdt_rank_v1(trees=40,lr=0.05) | player_map_score | group_to_playoff | - | 0.652 | 0.721 | 0.200 | 2727.43 |
| baseline | recent_mean_5 | player_map_score | group_to_playoff | - | 0.635 | 0.747 | 0.000 | 2842.54 |
| quantile | quantile_linear_v1 | player_map_score | group_to_playoff | - | 0.625 | 0.754 | 0.000 | 3177.43 |

## Best Surfaces / prediction / role_slot

| Family | Surface | Target | Split | Scope | Spearman | NDCG@5 | Top5 | MAE |
|---|---|---|---|---|---:|---:|---:|---:|
| baseline | segment_mean | role_slot_map_score | group_to_playoff | - | 0.781 | 0.844 | 0.400 | 2301.53 |
| production | baseline::segment_mean | role_slot_map_score | group_to_playoff | - | 0.781 | 0.844 | 0.400 | 2301.53 |
| baseline | shrunk_mean | role_slot_map_score | group_to_playoff | - | 0.676 | 0.829 | 0.400 | 2488.76 |
| baseline | entity_mean | role_slot_map_score | group_to_playoff | - | 0.676 | 0.829 | 0.400 | 2520.54 |
| baseline | team_segment_mean | role_slot_map_score | group_to_playoff | - | 0.676 | 0.829 | 0.400 | 2520.54 |
| ridge | ridge_v2(alpha=0.25) | role_slot_map_score | group_to_playoff | - | 0.676 | 0.829 | 0.400 | 2520.96 |
| gbdt | gbdt_rank_v1(trees=40,lr=0.08) | role_slot_map_score | group_to_playoff | - | 0.657 | 0.815 | 0.200 | 2622.03 |
| baseline | recent_mean_5 | role_slot_map_score | group_to_playoff | - | 0.627 | 0.826 | 0.200 | 2795.18 |

## Best Surfaces / reliability / player

| Family | Surface | Target | Split | Scope | Spearman | NDCG@5 | Top5 | MAE |
|---|---|---|---|---|---:|---:|---:|---:|
| reliability_foundation | series_mean_plus_top1_v1 | - | group_to_playoff | all | 0.586 | 0.719 | 0.000 | 3014.90 |

## Best Surfaces / reliability / role_slot

| Family | Surface | Target | Split | Scope | Spearman | NDCG@5 | Top5 | MAE |
|---|---|---|---|---|---:|---:|---:|---:|
| reliability_foundation | series_mean_plus_top1_v1 | - | group_to_playoff | all | 0.541 | 0.812 | 0.200 | 2942.97 |

## Diagnostic-only Layers

| Layer | Family | Surface | Entity | Target | Split | Avg p_top1 | Avg p_top3 | Avg p_top5 | Avg sim std |
|---|---|---|---|---|---|---:|---:|---:|---:|
| simulation | monte_carlo | production_monte_carlo | player | player_map_score | group_to_playoff | 0.025 | 0.075 | 0.125 | 1996.80 |
| simulation | monte_carlo | production_monte_carlo | player | player_map_score | temporal_60_40 | 0.025 | 0.075 | 0.125 | 2383.06 |
| simulation | monte_carlo | production_monte_carlo | player | player_series_mean | group_to_playoff | 0.025 | 0.075 | 0.125 | 1544.30 |
| simulation | monte_carlo | production_monte_carlo | player | player_series_mean | temporal_60_40 | 0.025 | 0.075 | 0.125 | 1464.59 |
| simulation | monte_carlo | production_monte_carlo | player | player_series_top1 | group_to_playoff | 0.025 | 0.075 | 0.125 | 1951.88 |
| simulation | monte_carlo | production_monte_carlo | player | player_series_top1 | temporal_60_40 | 0.025 | 0.075 | 0.125 | 249.98 |
| simulation | monte_carlo | production_monte_carlo | role_slot | role_slot_map_score | group_to_playoff | 0.042 | 0.125 | 0.208 | 1843.73 |
| simulation | monte_carlo | production_monte_carlo | role_slot | role_slot_map_score | temporal_60_40 | 0.042 | 0.125 | 0.208 | 2334.49 |
| simulation | monte_carlo | production_monte_carlo | role_slot | role_slot_series_mean | group_to_playoff | 0.042 | 0.125 | 0.208 | 1402.73 |
| simulation | monte_carlo | production_monte_carlo | role_slot | role_slot_series_mean | temporal_60_40 | 0.042 | 0.125 | 0.208 | 1430.92 |
| simulation | monte_carlo | production_monte_carlo | role_slot | role_slot_series_top1 | group_to_playoff | 0.042 | 0.125 | 0.208 | 1774.00 |
| simulation | monte_carlo | production_monte_carlo | role_slot | role_slot_series_top1 | temporal_60_40 | 0.042 | 0.125 | 0.208 | 1726.50 |

