# Prediction Foundation Scorecard

This scorecard summarizes the new map-first prediction foundation layer. It is intended as the baseline comparison surface that will replace the old best2-only framing over time.

## player_map_score / group_to_playoff

| Model | MAE | Spearman row | Spearman entity | Top5 overlap | Regret@1 |
|---|---:|---:|---:|---:|---:|
| segment_mean | 2500.95 | 0.621 | 0.729 | 0.400 | 2372.90 |
| shrunk_mean | 2583.80 | 0.596 | 0.698 | 0.200 | 3047.25 |
| entity_mean | 2602.39 | 0.603 | 0.708 | 0.000 | 3047.25 |
| team_segment_mean | 2691.67 | 0.538 | 0.613 | 0.200 | 3047.25 |
| recent_mean_5 | 2842.54 | 0.524 | 0.635 | 0.000 | 3047.25 |

## player_map_score / temporal_60_40

| Model | MAE | Spearman row | Spearman entity | Top5 overlap | Regret@1 |
|---|---:|---:|---:|---:|---:|
| shrunk_mean | 2613.84 | 0.642 | 0.885 | 0.000 | 3250.96 |
| entity_mean | 2614.49 | 0.639 | 0.884 | 0.200 | 3250.96 |
| team_segment_mean | 2700.94 | 0.609 | 0.836 | 0.000 | 3250.96 |
| segment_mean | 2705.65 | 0.608 | 0.825 | 0.000 | 3250.96 |
| recent_mean_5 | 2790.88 | 0.598 | 0.832 | 0.200 | 4592.65 |

## player_series_mean / group_to_playoff

| Model | MAE | Spearman row | Spearman entity | Top5 overlap | Regret@1 |
|---|---:|---:|---:|---:|---:|
| segment_mean | 1931.90 | 0.716 | 0.724 | 0.200 | 4952.58 |
| shrunk_mean | 2036.02 | 0.683 | 0.698 | 0.000 | 3250.34 |
| recent_mean_5 | 2085.92 | 0.691 | 0.690 | 0.200 | 3250.34 |
| entity_mean | 2113.99 | 0.695 | 0.713 | 0.000 | 3250.34 |
| team_segment_mean | 2157.68 | 0.631 | 0.627 | 0.200 | 3250.34 |

## player_series_mean / temporal_60_40

| Model | MAE | Spearman row | Spearman entity | Top5 overlap | Regret@1 |
|---|---:|---:|---:|---:|---:|
| entity_mean | 1834.65 | 0.780 | 0.890 | 0.000 | 3707.04 |
| recent_mean_5 | 1839.52 | 0.779 | 0.889 | 0.000 | 3707.04 |
| shrunk_mean | 1852.73 | 0.778 | 0.886 | 0.200 | 3707.04 |
| team_segment_mean | 1977.08 | 0.736 | 0.833 | 0.200 | 3707.04 |
| segment_mean | 2008.67 | 0.733 | 0.807 | 0.000 | 3707.04 |

## player_series_top1 / group_to_playoff

| Model | MAE | Spearman row | Spearman entity | Top5 overlap | Regret@1 |
|---|---:|---:|---:|---:|---:|
| segment_mean | 2438.89 | 0.684 | 0.727 | 0.200 | 3703.49 |
| shrunk_mean | 2528.26 | 0.656 | 0.671 | 0.000 | 3673.94 |
| entity_mean | 2558.80 | 0.645 | 0.656 | 0.000 | 3673.94 |
| recent_mean_5 | 2587.18 | 0.634 | 0.625 | 0.000 | 3673.94 |
| team_segment_mean | 2640.07 | 0.605 | 0.614 | 0.000 | 3673.94 |

## player_series_top1 / temporal_60_40

| Model | MAE | Spearman row | Spearman entity | Top5 overlap | Regret@1 |
|---|---:|---:|---:|---:|---:|
| entity_mean | 2283.93 | 0.782 | 0.887 | 0.200 | 104.42 |
| recent_mean_5 | 2294.01 | 0.781 | 0.886 | 0.200 | 104.42 |
| recent_p75_5 | 2360.18 | 0.766 | 0.875 | 0.200 | 104.42 |
| shrunk_mean | 2370.27 | 0.774 | 0.876 | 0.200 | 2092.98 |
| entity_p75 | 2376.50 | 0.765 | 0.874 | 0.200 | 104.42 |

## role_slot_map_score / group_to_playoff

| Model | MAE | Spearman row | Spearman entity | Top5 overlap | Regret@1 |
|---|---:|---:|---:|---:|---:|
| segment_mean | 2301.53 | 0.659 | 0.781 | 0.400 | 2258.61 |
| shrunk_mean | 2488.76 | 0.574 | 0.676 | 0.400 | 2932.96 |
| entity_mean | 2520.54 | 0.574 | 0.676 | 0.400 | 2932.96 |
| team_segment_mean | 2520.54 | 0.574 | 0.676 | 0.400 | 2932.96 |
| recent_mean_5 | 2795.18 | 0.492 | 0.627 | 0.200 | 2932.96 |

## role_slot_map_score / temporal_60_40

| Model | MAE | Spearman row | Spearman entity | Top5 overlap | Regret@1 |
|---|---:|---:|---:|---:|---:|
| shrunk_mean | 2557.50 | 0.648 | 0.888 | 0.400 | 2759.41 |
| team_segment_mean | 2563.57 | 0.641 | 0.879 | 0.400 | 2759.41 |
| entity_mean | 2563.57 | 0.641 | 0.879 | 0.400 | 2759.41 |
| segment_mean | 2604.13 | 0.638 | 0.852 | 0.000 | 2759.41 |
| entity_p75 | 2714.56 | 0.633 | 0.875 | 0.200 | 2759.41 |

## role_slot_series_mean / group_to_playoff

| Model | MAE | Spearman row | Spearman entity | Top5 overlap | Regret@1 |
|---|---:|---:|---:|---:|---:|
| segment_mean | 1755.78 | 0.739 | 0.759 | 0.400 | 4306.62 |
| shrunk_mean | 1985.40 | 0.642 | 0.691 | 0.200 | 2604.38 |
| recent_mean_5 | 2029.00 | 0.665 | 0.693 | 0.400 | 2604.38 |
| entity_mean | 2042.89 | 0.642 | 0.691 | 0.200 | 2604.38 |
| team_segment_mean | 2042.89 | 0.642 | 0.691 | 0.200 | 2604.38 |

## role_slot_series_mean / temporal_60_40

| Model | MAE | Spearman row | Spearman entity | Top5 overlap | Regret@1 |
|---|---:|---:|---:|---:|---:|
| shrunk_mean | 1787.30 | 0.773 | 0.889 | 0.400 | 3512.83 |
| entity_mean | 1819.73 | 0.764 | 0.879 | 0.400 | 3512.83 |
| team_segment_mean | 1819.73 | 0.764 | 0.879 | 0.400 | 3512.83 |
| recent_mean_5 | 1822.45 | 0.766 | 0.880 | 0.400 | 3512.83 |
| segment_mean | 1873.95 | 0.757 | 0.864 | 0.000 | 3512.83 |

## role_slot_series_top1 / group_to_playoff

| Model | MAE | Spearman row | Spearman entity | Top5 overlap | Regret@1 |
|---|---:|---:|---:|---:|---:|
| segment_mean | 2218.66 | 0.731 | 0.781 | 0.400 | 3703.49 |
| shrunk_mean | 2369.45 | 0.651 | 0.689 | 0.400 | 3673.94 |
| entity_mean | 2418.48 | 0.645 | 0.683 | 0.400 | 3673.94 |
| team_segment_mean | 2418.48 | 0.645 | 0.683 | 0.400 | 3673.94 |
| recent_mean_5 | 2463.67 | 0.649 | 0.662 | 0.400 | 3673.94 |

## role_slot_series_top1 / temporal_60_40

| Model | MAE | Spearman row | Spearman entity | Top5 overlap | Regret@1 |
|---|---:|---:|---:|---:|---:|
| entity_mean | 2146.91 | 0.766 | 0.875 | 0.400 | 2092.98 |
| team_segment_mean | 2146.91 | 0.766 | 0.875 | 0.400 | 2092.98 |
| shrunk_mean | 2162.44 | 0.767 | 0.876 | 0.400 | 2092.98 |
| recent_mean_5 | 2165.04 | 0.768 | 0.875 | 0.400 | 2092.98 |
| entity_p75 | 2229.25 | 0.743 | 0.854 | 0.200 | 4155.04 |

