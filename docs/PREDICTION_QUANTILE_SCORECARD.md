# Prediction Quantile Scorecard

This scorecard summarizes the linear quantile layer built on the shared richer feature foundation. The point estimate is q50, while q25/q75/q90 expose distribution shape and coverage behavior.

| Target | Split | MAE(q50) | Entity sp. | Pinball q25 | Pinball q50 | Pinball q75 | Coverage q75 | Coverage q90 | Band q25-q75 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| player_map_score | group_to_playoff | 3177.43 | 0.625 | 1468.09 | 1588.71 | 1709.03 | 0.553 | 0.553 | 1.23 |
| player_map_score | temporal_60_40 | 3463.50 | 0.883 | 1456.19 | 1731.75 | 2007.00 | 0.480 | 0.480 | 1.23 |
| player_series_mean | group_to_playoff | 2907.50 | 0.641 | 1430.46 | 1453.75 | 1476.89 | 0.525 | 0.525 | 0.61 |
| player_series_mean | temporal_60_40 | 3072.90 | 0.887 | 1314.22 | 1536.45 | 1758.53 | 0.479 | 0.479 | 0.61 |
| player_series_top1 | group_to_playoff | 3596.34 | 0.641 | 1676.66 | 1798.17 | 1919.52 | 0.550 | 0.550 | 0.61 |
| player_series_top1 | temporal_60_40 | 3826.30 | 0.888 | 1574.80 | 1913.15 | 2251.19 | 0.461 | 0.461 | 1.23 |
| role_slot_map_score | group_to_playoff | 3289.15 | 0.599 | 1563.46 | 1644.57 | 1725.38 | 0.544 | 0.544 | 1.23 |
| role_slot_map_score | temporal_60_40 | 3535.68 | 0.876 | 1562.33 | 1767.84 | 1973.04 | 0.508 | 0.508 | 1.23 |
| role_slot_series_mean | group_to_playoff | 3047.79 | 0.650 | 1636.11 | 1523.89 | 1411.37 | 0.542 | 0.542 | 1.23 |
| role_slot_series_mean | temporal_60_40 | 3140.88 | 0.877 | 1486.25 | 1570.44 | 1654.33 | 0.476 | 0.476 | 1.23 |
| role_slot_series_top1 | group_to_playoff | 3788.18 | 0.632 | 1906.43 | 1894.09 | 1881.45 | 0.521 | 0.521 | 1.23 |
| role_slot_series_top1 | temporal_60_40 | 3998.47 | 0.867 | 1726.73 | 1999.23 | 2271.58 | 0.440 | 0.440 | 0.61 |
