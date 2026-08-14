# Prediction GBDT Scorecard

This scorecard summarizes the lightweight ranking-oriented GBDT experiment. It is not LambdaMART; it is a boosted-stump regressor with target-aware sample weights to emphasize high-value fantasy outcomes.

| Target | Split | Trees | LR | MAE | Entity sp. | Top5 overlap | NDCG@5 | Regret@1 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| player_map_score | group_to_playoff | 40 | 0.050 | 2727.43 | 0.652 | 0.200 | 0.721 | 7152.53 |
| player_map_score | temporal_60_40 | 16 | 0.050 | 2980.60 | 0.889 | 0.000 | 0.807 | 2619.60 |
| player_series_mean | group_to_playoff | 40 | 0.080 | 2190.82 | 0.679 | 0.200 | 0.774 | 3793.76 |
| player_series_mean | temporal_60_40 | 24 | 0.050 | 2162.49 | 0.881 | 0.000 | 0.808 | 3170.60 |
| player_series_top1 | group_to_playoff | 40 | 0.080 | 2575.01 | 0.682 | 0.200 | 0.814 | 3673.94 |
| player_series_top1 | temporal_60_40 | 16 | 0.050 | 2834.73 | 0.875 | 0.000 | 0.813 | 2613.04 |
| role_slot_map_score | group_to_playoff | 40 | 0.080 | 2622.03 | 0.657 | 0.200 | 0.815 | 4635.20 |
| role_slot_map_score | temporal_60_40 | 16 | 0.050 | 2920.78 | 0.890 | 0.000 | 0.812 | 4434.58 |
| role_slot_series_mean | group_to_playoff | 40 | 0.080 | 2101.95 | 0.685 | 0.200 | 0.814 | 4306.62 |
| role_slot_series_mean | temporal_60_40 | 40 | 0.050 | 1907.38 | 0.882 | 0.400 | 0.858 | 3512.83 |
| role_slot_series_top1 | group_to_playoff | 40 | 0.080 | 2471.27 | 0.681 | 0.400 | 0.828 | 3673.94 |
| role_slot_series_top1 | temporal_60_40 | 24 | 0.050 | 2484.87 | 0.858 | 0.000 | 0.775 | 6337.39 |

## Top Features / player_map_score / group_to_playoff

| Feature | Total gain | Split count |
|---|---:|---:|
| entity_mean | 243837196393.81 | 21 |
| entity_p90 | 95454269683.55 | 9 |
| entity_p75 | 28872458654.15 | 7 |
| entity_max | 4646258125.58 | 2 |
| recent_mean_5 | 3041885897.84 | 1 |

## Top Features / player_map_score / temporal_60_40

| Feature | Total gain | Split count |
|---|---:|---:|
| entity_mean | 107555703778.09 | 9 |
| entity_p90 | 58765066951.66 | 5 |
| entity_max | 19823330899.37 | 1 |
| recent_p75_5 | 6957831408.16 | 1 |

## Top Features / player_series_mean / group_to_playoff

| Feature | Total gain | Split count |
|---|---:|---:|
| entity_p90 | 58063577264.93 | 16 |
| entity_mean | 30734818478.66 | 9 |
| entity_p75 | 22385389924.14 | 8 |
| recent_mean_5 | 8295558085.55 | 2 |
| entity_max | 4979418726.26 | 1 |
| recent_p75_5 | 808279043.77 | 1 |
| maps_in_observation | 603650196.74 | 2 |
| entity_p25 | 568536634.58 | 1 |

## Top Features / player_series_mean / temporal_60_40

| Feature | Total gain | Split count |
|---|---:|---:|
| entity_p90 | 42217591675.39 | 6 |
| entity_mean | 33376376814.80 | 7 |
| recent_p75_5 | 13134562855.65 | 3 |
| recent_mean_5 | 12604337845.27 | 4 |
| entity_max | 7395129634.11 | 2 |
| entity_p75 | 5079514374.91 | 2 |

## Top Features / player_series_top1 / group_to_playoff

| Feature | Total gain | Split count |
|---|---:|---:|
| entity_mean | 80658259227.29 | 17 |
| entity_p75 | 43340302518.45 | 9 |
| entity_p90 | 36638574787.45 | 9 |
| recent_mean_5 | 7701286925.75 | 1 |
| maps_in_observation | 1605630693.79 | 3 |
| recent_mean_3 | 1400368874.73 | 1 |

## Top Features / player_series_top1 / temporal_60_40

| Feature | Total gain | Split count |
|---|---:|---:|
| entity_p90 | 52031011842.60 | 6 |
| entity_mean | 25985725158.67 | 4 |
| recent_mean_5 | 24703468728.70 | 3 |
| entity_max | 14094556246.67 | 1 |
| entity_p75 | 7857287903.75 | 2 |

## Top Features / role_slot_map_score / group_to_playoff

| Feature | Total gain | Split count |
|---|---:|---:|
| entity_mean | 74589712706.91 | 18 |
| entity_p75 | 49347809094.21 | 10 |
| entity_p90 | 17759445648.25 | 9 |
| entity_max | 6858386580.95 | 1 |
| segment_mean | 1663864412.30 | 1 |
| role_code | 1230616843.55 | 1 |

## Top Features / role_slot_map_score / temporal_60_40

| Feature | Total gain | Split count |
|---|---:|---:|
| entity_mean | 67207759000.28 | 9 |
| entity_p90 | 17992711528.38 | 2 |
| recent_p75_5 | 14838781089.81 | 2 |
| entity_max | 7507500593.25 | 1 |
| recent_mean_5 | 4835574030.91 | 1 |
| entity_p75 | 4073824950.45 | 1 |

## Top Features / role_slot_series_mean / group_to_playoff

| Feature | Total gain | Split count |
|---|---:|---:|
| entity_p75 | 29114055855.86 | 8 |
| entity_mean | 20762598669.97 | 10 |
| entity_p90 | 16038638048.01 | 16 |
| recent_mean_5 | 8166210022.50 | 2 |
| role_code | 980954957.65 | 1 |
| maps_in_observation | 600784763.10 | 3 |

## Top Features / role_slot_series_mean / temporal_60_40

| Feature | Total gain | Split count |
|---|---:|---:|
| entity_p90 | 21786667278.31 | 13 |
| entity_mean | 18254386528.20 | 9 |
| entity_p75 | 15011457644.37 | 10 |
| recent_mean_5 | 10061361885.34 | 5 |
| entity_p25 | 6646242513.93 | 1 |
| entity_max | 6616573612.81 | 2 |

## Top Features / role_slot_series_top1 / group_to_playoff

| Feature | Total gain | Split count |
|---|---:|---:|
| entity_mean | 39495701113.88 | 13 |
| entity_p90 | 25581118637.79 | 12 |
| entity_p75 | 17818957071.15 | 6 |
| entity_p25 | 11178833891.05 | 1 |
| recent_mean_3 | 4727759816.16 | 1 |
| recent_mean_5 | 3659760067.62 | 4 |
| maps_in_observation | 931359455.36 | 3 |

## Top Features / role_slot_series_top1 / temporal_60_40

| Feature | Total gain | Split count |
|---|---:|---:|
| entity_mean | 24587071520.86 | 7 |
| entity_p90 | 18759197771.03 | 7 |
| entity_p75 | 12430671784.15 | 3 |
| entity_max | 10085577182.93 | 2 |
| recent_p75_5 | 8878914634.72 | 1 |
| entity_p25 | 6538351860.95 | 1 |
| recent_mean_5 | 5981942258.70 | 2 |
| recent_mean_3 | 3475861258.06 | 1 |

