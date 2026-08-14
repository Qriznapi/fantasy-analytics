# Optimizer Foundation Scorecard

This scorecard summarizes the newer foundation-first optimizer layer. It is a recommendation surface built on top of the reliability foundation, with extra emphasis on usable ceiling, balanced stat exposure, and lineup-oriented upside.

## Segment Summary

| Entity type | Scope | Segment | Rows | Avg optimizer | Avg expected | Avg high | Avg reliability | Avg stat balance | Avg volatility |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| player | all | core | 48 | 50.50 | 8962.02 | 10571.83 | 50.50 | 0.830 | 0.257 |
| player | all | mid | 24 | 50.50 | 10724.68 | 12417.56 | 50.50 | 0.831 | 0.230 |
| player | all | support | 48 | 50.50 | 6053.82 | 7175.16 | 50.50 | 0.828 | 0.215 |
| player | ti2026 | core | 28 | 50.50 | 9500.27 | 11106.87 | 59.98 | 0.836 | 0.240 |
| player | ti2026 | mid | 14 | 50.50 | 11200.93 | 12938.54 | 60.95 | 0.840 | 0.228 |
| player | ti2026 | support | 28 | 50.50 | 6372.63 | 7526.50 | 61.86 | 0.837 | 0.214 |
| role_slot | all | core_pair | 24 | 50.50 | 8947.36 | 10451.66 | 50.50 | 0.846 | 0.233 |
| role_slot | all | mid_single | 24 | 50.50 | 10724.68 | 12417.56 | 50.50 | 0.831 | 0.230 |
| role_slot | all | support_pair | 24 | 50.50 | 6042.75 | 7064.88 | 50.50 | 0.841 | 0.180 |
| role_slot | ti2026 | core_pair | 14 | 50.50 | 9487.59 | 10985.94 | 61.26 | 0.848 | 0.218 |
| role_slot | ti2026 | mid_single | 14 | 50.50 | 11200.93 | 12938.54 | 60.95 | 0.840 | 0.228 |
| role_slot | ti2026 | support_pair | 14 | 50.50 | 6351.82 | 7409.57 | 63.41 | 0.851 | 0.182 |

## Backtest Summary

| Entity type | Scope | MAE | Spearman | Top3 overlap | Top5 overlap | NDCG@5 | NDCG@10 | Regret@1 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| player | all | 2366.68 | 0.643 | 0.000 | 0.200 | 0.787 | 0.802 | 3072.51 |
| player | ti2026 | 2118.45 | 0.674 | 0.000 | 0.200 | 0.787 | 0.834 | 3072.51 |
| role_slot | all | 2256.33 | 0.624 | 0.000 | 0.400 | 0.869 | 0.866 | 3032.21 |
| role_slot | ti2026 | 1974.86 | 0.662 | 0.000 | 0.400 | 0.869 | 0.903 | 3032.21 |

## Baseline Comparison

| Entity type | Scope | Baseline | MAE | Spearman | Top5 overlap | NDCG@5 | Regret@1 |
|---|---|---|---:|---:|---:|---:|---:|
| player | all | ceiling_blend | 3231.13 | 0.641 | 0.000 | 0.782 | 3072.51 |
| player | all | expected_only | 3014.90 | 0.586 | 0.000 | 0.719 | 4703.09 |
| player | all | high_only | 2551.04 | 0.571 | 0.000 | 0.732 | 4703.09 |
| player | all | reliability_only | 3014.90 | 0.586 | 0.000 | 0.719 | 4703.09 |
| player | all | top1_p75_only | 3618.90 | 0.667 | 0.000 | 0.782 | 4703.09 |
| player | ti2026 | ceiling_blend | 2829.82 | 0.657 | 0.000 | 0.782 | 3072.51 |
| player | ti2026 | expected_only | 3251.54 | 0.656 | 0.200 | 0.762 | 4703.09 |
| player | ti2026 | high_only | 2514.79 | 0.647 | 0.000 | 0.730 | 4703.09 |
| player | ti2026 | reliability_only | 3251.54 | 0.656 | 0.200 | 0.762 | 4703.09 |
| player | ti2026 | top1_p75_only | 3178.79 | 0.693 | 0.000 | 0.782 | 4703.09 |
| role_slot | all | ceiling_blend | 3186.35 | 0.630 | 0.400 | 0.869 | 3032.21 |
| role_slot | all | expected_only | 2942.97 | 0.541 | 0.200 | 0.812 | 4662.79 |
| role_slot | all | high_only | 2482.21 | 0.544 | 0.200 | 0.812 | 4662.79 |
| role_slot | all | reliability_only | 2942.97 | 0.541 | 0.200 | 0.812 | 4662.79 |
| role_slot | all | top1_p75_only | 3534.35 | 0.643 | 0.400 | 0.859 | 4662.79 |
| role_slot | ti2026 | ceiling_blend | 2726.16 | 0.662 | 0.400 | 0.869 | 3032.21 |
| role_slot | ti2026 | expected_only | 3133.37 | 0.595 | 0.400 | 0.857 | 4662.79 |
| role_slot | ti2026 | high_only | 2404.66 | 0.600 | 0.400 | 0.857 | 4662.79 |
| role_slot | ti2026 | reliability_only | 3133.37 | 0.595 | 0.400 | 0.857 | 4662.79 |
| role_slot | ti2026 | top1_p75_only | 3031.85 | 0.675 | 0.400 | 0.859 | 4662.79 |

## Segment Regret vs Baselines

| Entity type | Scope | Segment | Baseline | Regret@1 | Spearman |
|---|---|---|---|---:|---:|
| player | all | core | ceiling_blend | 8025.96 | 0.012 |
| player | all | core | expected_only | 8025.96 | -0.291 |
| player | all | core | high_only | 8025.96 | -0.244 |
| player | all | core | reliability_only | 8025.96 | -0.291 |
| player | all | core | top1_p75_only | 8025.96 | 0.109 |
| player | all | mid | ceiling_blend | 3032.21 | -0.548 |
| player | all | mid | expected_only | 4662.79 | -0.786 |
| player | all | mid | high_only | 4662.79 | -0.786 |
| player | all | mid | reliability_only | 4662.79 | -0.786 |
| player | all | mid | top1_p75_only | 4662.79 | -0.476 |
| player | all | support | ceiling_blend | 3671.84 | -0.097 |
| player | all | support | expected_only | 3671.84 | -0.203 |
| player | all | support | high_only | 3671.84 | -0.203 |
| player | all | support | reliability_only | 3671.84 | -0.203 |
| player | all | support | top1_p75_only | 3671.84 | -0.003 |
| player | ti2026 | core | ceiling_blend | 8025.96 | 0.042 |
| player | ti2026 | core | expected_only | 8025.96 | -0.125 |
| player | ti2026 | core | high_only | 8025.96 | -0.064 |
| player | ti2026 | core | reliability_only | 8025.96 | -0.125 |
| player | ti2026 | core | top1_p75_only | 8025.96 | 0.178 |
| player | ti2026 | mid | ceiling_blend | 3032.21 | -0.857 |
| player | ti2026 | mid | expected_only | 4662.79 | -0.893 |
| player | ti2026 | mid | high_only | 4662.79 | -0.893 |
| player | ti2026 | mid | reliability_only | 4662.79 | -0.893 |
| player | ti2026 | mid | top1_p75_only | 4662.79 | -0.750 |
| player | ti2026 | support | ceiling_blend | 3671.84 | -0.209 |
| player | ti2026 | support | expected_only | 3671.84 | -0.042 |
| player | ti2026 | support | high_only | 3671.84 | 0.015 |
| player | ti2026 | support | reliability_only | 3671.84 | -0.042 |
| player | ti2026 | support | top1_p75_only | 3671.84 | -0.020 |
| role_slot | all | core_pair | ceiling_blend | 1705.11 | -0.476 |
| role_slot | all | core_pair | expected_only | 5720.57 | -0.738 |
| role_slot | all | core_pair | high_only | 5720.57 | -0.738 |
| role_slot | all | core_pair | reliability_only | 5720.57 | -0.738 |
| role_slot | all | core_pair | top1_p75_only | 1705.11 | -0.381 |
| role_slot | all | mid_single | ceiling_blend | 3032.21 | -0.548 |
| role_slot | all | mid_single | expected_only | 4662.79 | -0.786 |
| role_slot | all | mid_single | high_only | 4662.79 | -0.786 |
| role_slot | all | mid_single | reliability_only | 4662.79 | -0.786 |
| role_slot | all | mid_single | top1_p75_only | 4662.79 | -0.476 |
| role_slot | all | support_pair | ceiling_blend | 2181.77 | -0.500 |
| role_slot | all | support_pair | expected_only | 1475.09 | -0.619 |
| role_slot | all | support_pair | high_only | 1475.09 | -0.595 |
| role_slot | all | support_pair | reliability_only | 1475.09 | -0.619 |
| role_slot | all | support_pair | top1_p75_only | 2181.77 | -0.500 |
| role_slot | ti2026 | core_pair | ceiling_blend | 1705.11 | -0.393 |
| role_slot | ti2026 | core_pair | expected_only | 5720.57 | -0.679 |
| role_slot | ti2026 | core_pair | high_only | 5720.57 | -0.679 |
| role_slot | ti2026 | core_pair | reliability_only | 5720.57 | -0.679 |
| role_slot | ti2026 | core_pair | top1_p75_only | 1705.11 | -0.250 |
| role_slot | ti2026 | mid_single | ceiling_blend | 3032.21 | -0.857 |
| role_slot | ti2026 | mid_single | expected_only | 4662.79 | -0.893 |
| role_slot | ti2026 | mid_single | high_only | 4662.79 | -0.893 |
| role_slot | ti2026 | mid_single | reliability_only | 4662.79 | -0.893 |
| role_slot | ti2026 | mid_single | top1_p75_only | 4662.79 | -0.750 |
| role_slot | ti2026 | support_pair | ceiling_blend | 2181.77 | -0.679 |
| role_slot | ti2026 | support_pair | expected_only | 1475.09 | -0.536 |
| role_slot | ti2026 | support_pair | high_only | 1475.09 | -0.536 |
| role_slot | ti2026 | support_pair | reliability_only | 1475.09 | -0.536 |
| role_slot | ti2026 | support_pair | top1_p75_only | 2181.77 | -0.679 |

## Top Players / all / core

| Player | Team | Optimizer | Raw | Expected | High | Reliability | Top1 p75 | Stat balance |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Ghost | GamerLegion | 100.00 | 17389.44 | 11216.68 | 13631.97 | 93.68 | 24820.43 | 0.794 |
| Timado | Virtus.pro | 97.89 | 16772.44 | 12096.44 | 14618.67 | 100.00 | 21325.53 | 0.821 |
| SumaiL | Nigma Galaxy | 95.79 | 15892.86 | 12090.81 | 13825.19 | 97.89 | 19509.03 | 0.856 |
| Yuma | LGD Gaming | 93.68 | 15624.04 | 11910.36 | 13924.33 | 95.79 | 19083.26 | 0.861 |
| Pure | 1w | 91.57 | 15091.83 | 10931.38 | 12629.12 | 91.57 | 19016.09 | 0.858 |
| Crystallis | MOUZ | 89.47 | 14785.59 | 10128.25 | 12541.23 | 76.83 | 20043.92 | 0.833 |
| shiro | Vici Gaming | 87.36 | 14700.97 | 10846.98 | 12833.67 | 87.36 | 17837.19 | 0.836 |
| Yatoro | Team Spirit | 85.26 | 14475.01 | 10855.93 | 12172.60 | 89.47 | 18052.01 | 0.833 |

## Top Players / all / mid

| Player | Team | Optimizer | Raw | Expected | High | Reliability | Top1 p75 | Stat balance |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Malr1ne | Team Falcons | 100.00 | 16800.00 | 11860.47 | 13999.64 | 78.48 | 20470.33 | 0.837 |
| lorenof | Nigma Galaxy | 95.70 | 16776.94 | 13037.62 | 14825.46 | 100.00 | 20548.17 | 0.863 |
| NothingToSay | Xtreme Gaming | 91.39 | 16614.40 | 11904.94 | 13968.16 | 82.78 | 21545.73 | 0.842 |
| bzm | 1w | 87.09 | 16397.80 | 11823.97 | 13816.37 | 65.57 | 20769.65 | 0.865 |
| Abed | Virtus.pro | 82.78 | 16168.22 | 12276.39 | 14240.45 | 95.70 | 19727.64 | 0.769 |
| MidOne | MOUZ | 78.48 | 15904.80 | 11832.06 | 13461.68 | 74.17 | 20429.84 | 0.818 |
| Nisha | Team Liquid | 74.17 | 15740.85 | 12048.95 | 14133.71 | 87.09 | 19653.04 | 0.832 |
| TaiLung | LGD Gaming | 69.87 | 15735.19 | 12178.17 | 14184.04 | 91.39 | 19862.69 | 0.850 |

## Top Players / all / support

| Player | Team | Optimizer | Raw | Expected | High | Reliability | Top1 p75 | Stat balance |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| XinQ | Vici Gaming | 100.00 | 10319.98 | 7249.88 | 8925.86 | 97.89 | 12816.15 | 0.826 |
| tOfu | Team Liquid | 97.89 | 9547.49 | 7027.80 | 8831.11 | 91.57 | 11301.83 | 0.834 |
| Ari | 1w | 95.79 | 9516.97 | 6867.46 | 8175.04 | 87.36 | 12157.48 | 0.850 |
| Bignum | GamerLegion | 93.68 | 9404.33 | 6614.87 | 7776.66 | 70.51 | 11713.39 | 0.799 |
| Thiolicor | LGD Gaming | 91.57 | 9331.00 | 7301.76 | 8646.24 | 100.00 | 10597.78 | 0.856 |
| KJ | LGD Gaming | 89.47 | 9292.89 | 7170.43 | 8463.51 | 93.68 | 10929.78 | 0.852 |
| Whitemon | 1w | 87.36 | 9194.84 | 6658.27 | 7851.47 | 81.04 | 11635.01 | 0.847 |
| Saksa | Team Yandex | 85.26 | 9189.94 | 6448.85 | 7565.39 | 64.19 | 11801.91 | 0.866 |

## Top Players / ti2026 / core

| Player | Team | Optimizer | Raw | Expected | High | Reliability | Top1 p75 | Stat balance |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Ghost | GamerLegion | 100.00 | 17389.44 | 11216.68 | 13631.97 | 93.68 | 24820.43 | 0.794 |
| SumaiL | Nigma Galaxy | 96.33 | 15892.86 | 12090.81 | 13825.19 | 97.89 | 19509.03 | 0.856 |
| Yuma | LGD Gaming | 92.67 | 15624.04 | 11910.36 | 13924.33 | 95.79 | 19083.26 | 0.861 |
| Pure | 1w | 89.00 | 15091.83 | 10931.38 | 12629.12 | 91.57 | 19016.09 | 0.858 |
| shiro | Vici Gaming | 85.33 | 14700.97 | 10846.98 | 12833.67 | 87.36 | 17837.19 | 0.836 |
| Yatoro | Team Spirit | 81.67 | 14475.01 | 10855.93 | 12172.60 | 89.47 | 18052.01 | 0.833 |
| skiter | Team Falcons | 78.00 | 14469.26 | 9855.95 | 11692.40 | 68.40 | 19168.34 | 0.867 |
| m1CKe | Team Liquid | 74.33 | 13937.75 | 10355.04 | 12563.39 | 83.15 | 17791.03 | 0.850 |

## Top Players / ti2026 / mid

| Player | Team | Optimizer | Raw | Expected | High | Reliability | Top1 p75 | Stat balance |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Malr1ne | Team Falcons | 100.00 | 16800.00 | 11860.47 | 13999.64 | 78.48 | 20470.33 | 0.837 |
| lorenof | Nigma Galaxy | 92.38 | 16776.94 | 13037.62 | 14825.46 | 100.00 | 20548.17 | 0.863 |
| NothingToSay | Xtreme Gaming | 84.77 | 16614.40 | 11904.94 | 13968.16 | 82.78 | 21545.73 | 0.842 |
| bzm | 1w | 77.15 | 16397.80 | 11823.97 | 13816.37 | 65.57 | 20769.65 | 0.865 |
| Nisha | Team Liquid | 69.54 | 15740.85 | 12048.95 | 14133.71 | 87.09 | 19653.04 | 0.832 |
| TaiLung | LGD Gaming | 61.92 | 15735.19 | 12178.17 | 14184.04 | 91.39 | 19862.69 | 0.850 |
| Xm | Vici Gaming | 54.31 | 15440.34 | 11828.35 | 13610.89 | 69.87 | 18638.64 | 0.827 |
| gpk~ | BoomBoys | 46.69 | 15008.29 | 11090.60 | 12787.17 | 52.65 | 18962.87 | 0.863 |

## Top Players / ti2026 / support

| Player | Team | Optimizer | Raw | Expected | High | Reliability | Top1 p75 | Stat balance |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| XinQ | Vici Gaming | 100.00 | 10319.98 | 7249.88 | 8925.86 | 97.89 | 12816.15 | 0.826 |
| tOfu | Team Liquid | 96.33 | 9547.49 | 7027.80 | 8831.11 | 91.57 | 11301.83 | 0.834 |
| Ari | 1w | 92.67 | 9516.97 | 6867.46 | 8175.04 | 87.36 | 12157.48 | 0.850 |
| Bignum | GamerLegion | 89.00 | 9404.33 | 6614.87 | 7776.66 | 70.51 | 11713.39 | 0.799 |
| Thiolicor | LGD Gaming | 85.33 | 9331.00 | 7301.76 | 8646.24 | 100.00 | 10597.78 | 0.856 |
| KJ | LGD Gaming | 81.67 | 9292.89 | 7170.43 | 8463.51 | 93.68 | 10929.78 | 0.852 |
| Whitemon | 1w | 78.00 | 9194.84 | 6658.27 | 7851.47 | 81.04 | 11635.01 | 0.847 |
| Saksa | Team Yandex | 74.33 | 9189.94 | 6448.85 | 7565.39 | 64.19 | 11801.91 | 0.866 |

## Top Role Slots / all / core_pair

| Players | Team | Optimizer | Raw | Expected | High | Reliability | Top1 p75 | Stat balance |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Ghost, Fayde | GamerLegion | 100.00 | 14304.15 | 9643.85 | 11592.27 | 61.26 | 18975.14 | 0.823 |
| Timado, SaberLight | Virtus.pro | 95.70 | 14183.56 | 10768.03 | 12799.98 | 95.70 | 18305.65 | 0.837 |
| Yuma, Wisper | LGD Gaming | 91.39 | 14042.10 | 11149.97 | 12952.37 | 100.00 | 16814.02 | 0.871 |
| skiter, ATF | Team Falcons | 87.09 | 13846.96 | 9831.10 | 11333.52 | 74.17 | 18338.76 | 0.876 |
| Darklord^, Malik | Rune Eaters | 82.78 | 13359.41 | 10306.56 | 11817.78 | 87.09 | 16861.76 | 0.857 |
| SumaiL, Davai | Nigma Galaxy | 78.48 | 13221.78 | 10694.38 | 12103.75 | 91.39 | 16211.94 | 0.861 |
| Crystallis, BOOM | MOUZ | 74.17 | 13186.88 | 9554.49 | 11333.94 | 56.96 | 17569.19 | 0.842 |
| shiro, Bach | Vici Gaming | 69.87 | 12963.38 | 9907.08 | 11582.54 | 78.48 | 15869.42 | 0.853 |

## Top Role Slots / all / mid_single

| Players | Team | Optimizer | Raw | Expected | High | Reliability | Top1 p75 | Stat balance |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Malr1ne | Team Falcons | 100.00 | 16553.82 | 11860.47 | 13999.64 | 78.48 | 20470.33 | 0.837 |
| NothingToSay | Xtreme Gaming | 95.70 | 16457.03 | 11904.94 | 13968.16 | 82.78 | 21545.73 | 0.842 |
| lorenof | Nigma Galaxy | 91.39 | 16422.51 | 13037.62 | 14825.46 | 100.00 | 20548.17 | 0.863 |
| bzm | 1w | 87.09 | 16303.96 | 11823.97 | 13816.37 | 65.57 | 20769.65 | 0.865 |
| Abed | Virtus.pro | 82.78 | 15892.68 | 12276.39 | 14240.45 | 95.70 | 19727.64 | 0.769 |
| MidOne | MOUZ | 78.48 | 15696.27 | 11832.06 | 13461.68 | 74.17 | 20429.84 | 0.818 |
| Nisha | Team Liquid | 74.17 | 15521.49 | 12048.95 | 14133.71 | 87.09 | 19653.04 | 0.832 |
| TaiLung | LGD Gaming | 69.87 | 15461.66 | 12178.17 | 14184.04 | 91.39 | 19862.69 | 0.850 |

## Top Role Slots / all / support_pair

| Players | Team | Optimizer | Raw | Expected | High | Reliability | Top1 p75 | Stat balance |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Ari, Whitemon | 1w | 100.00 | 8975.96 | 6699.57 | 7801.71 | 78.48 | 11066.07 | 0.872 |
| Cr1t-, Sneyking | Team Falcons | 95.70 | 8929.02 | 6473.70 | 7448.33 | 69.87 | 11154.48 | 0.859 |
| Thiolicor, KJ | LGD Gaming | 91.39 | 8914.21 | 7197.73 | 8449.67 | 100.00 | 10327.95 | 0.860 |
| XinQ, y` | Vici Gaming | 87.09 | 8772.97 | 6719.51 | 7923.55 | 82.78 | 10499.58 | 0.824 |
| OmaR, GH | Nigma Galaxy | 82.78 | 8766.85 | 7001.55 | 8085.56 | 95.70 | 10344.24 | 0.869 |
| Hellscream, Fly | Virtus.pro | 78.48 | 8756.57 | 6816.25 | 8055.86 | 91.39 | 10243.96 | 0.851 |
| fy, xNova | Xtreme Gaming | 74.17 | 8678.10 | 6448.25 | 7716.66 | 65.57 | 10413.33 | 0.851 |
| Ekki, aik | Rune Eaters | 69.87 | 8431.73 | 6740.18 | 7857.95 | 87.09 | 9878.19 | 0.864 |

## Top Role Slots / ti2026 / core_pair

| Players | Team | Optimizer | Raw | Expected | High | Reliability | Top1 p75 | Stat balance |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Ghost, Fayde | GamerLegion | 100.00 | 14304.15 | 9643.85 | 11592.27 | 61.26 | 18975.14 | 0.823 |
| Yuma, Wisper | LGD Gaming | 92.38 | 14042.10 | 11149.97 | 12952.37 | 100.00 | 16814.02 | 0.871 |
| skiter, ATF | Team Falcons | 84.77 | 13846.96 | 9831.10 | 11333.52 | 74.17 | 18338.76 | 0.876 |
| SumaiL, Davai | Nigma Galaxy | 77.15 | 13221.78 | 10694.38 | 12103.75 | 91.39 | 16211.94 | 0.861 |
| shiro, Bach | Vici Gaming | 69.54 | 12963.38 | 9907.08 | 11582.54 | 78.48 | 15869.42 | 0.853 |
| Pure, 33 | 1w | 61.92 | 12861.56 | 9801.02 | 11138.88 | 65.57 | 15891.89 | 0.851 |
| m1CKe, Ace | Team Liquid | 54.31 | 12729.75 | 9823.71 | 11622.37 | 69.87 | 15778.02 | 0.851 |
| Yatoro, Collapse | Team Spirit | 46.69 | 12538.66 | 9920.75 | 10995.81 | 82.78 | 15127.25 | 0.858 |

## Top Role Slots / ti2026 / mid_single

| Players | Team | Optimizer | Raw | Expected | High | Reliability | Top1 p75 | Stat balance |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Malr1ne | Team Falcons | 100.00 | 16553.82 | 11860.47 | 13999.64 | 78.48 | 20470.33 | 0.837 |
| NothingToSay | Xtreme Gaming | 92.38 | 16457.03 | 11904.94 | 13968.16 | 82.78 | 21545.73 | 0.842 |
| lorenof | Nigma Galaxy | 84.77 | 16422.51 | 13037.62 | 14825.46 | 100.00 | 20548.17 | 0.863 |
| bzm | 1w | 77.15 | 16303.96 | 11823.97 | 13816.37 | 65.57 | 20769.65 | 0.865 |
| Nisha | Team Liquid | 69.54 | 15521.49 | 12048.95 | 14133.71 | 87.09 | 19653.04 | 0.832 |
| TaiLung | LGD Gaming | 61.92 | 15461.66 | 12178.17 | 14184.04 | 91.39 | 19862.69 | 0.850 |
| Xm | Vici Gaming | 54.31 | 15113.01 | 11828.35 | 13610.89 | 69.87 | 18638.64 | 0.827 |
| LarI | Team Spirit | 46.69 | 14798.04 | 10975.94 | 12621.41 | 48.35 | 19740.07 | 0.840 |

## Top Role Slots / ti2026 / support_pair

| Players | Team | Optimizer | Raw | Expected | High | Reliability | Top1 p75 | Stat balance |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Ari, Whitemon | 1w | 100.00 | 8975.96 | 6699.57 | 7801.71 | 78.48 | 11066.07 | 0.872 |
| Cr1t-, Sneyking | Team Falcons | 92.38 | 8929.02 | 6473.70 | 7448.33 | 69.87 | 11154.48 | 0.859 |
| Thiolicor, KJ | LGD Gaming | 84.77 | 8914.21 | 7197.73 | 8449.67 | 100.00 | 10327.95 | 0.860 |
| XinQ, y` | Vici Gaming | 77.15 | 8772.97 | 6719.51 | 7923.55 | 82.78 | 10499.58 | 0.824 |
| OmaR, GH | Nigma Galaxy | 69.54 | 8766.85 | 7001.55 | 8085.56 | 95.70 | 10344.24 | 0.869 |
| fy, xNova | Xtreme Gaming | 61.92 | 8678.10 | 6448.25 | 7716.66 | 65.57 | 10413.33 | 0.851 |
| Boxi, tOfu | Team Liquid | 54.31 | 8401.30 | 6631.79 | 7995.32 | 74.17 | 9628.05 | 0.845 |
| TIMS, skem | OG | 46.69 | 8310.94 | 6086.27 | 7055.44 | 52.65 | 10088.60 | 0.838 |

