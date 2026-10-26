# Table 1: capacity prediction at the next arrived RPT (2,326 common keys).

MAE and RMSE in mAh (x1000); NLL in nats/Ah; cov90 = 90% interval coverage.
Generated from ext_compare_run1/all_model_metrics.csv (single source).

| Model | Raw: MAE / RMSE / NLL | Sparse (2x): MAE / RMSE / NLL | Delayed (7d): MAE / RMSE / NLL |
|---|---|---|---|
| A3 rate-state filter (ours) | 3.06 / 6.59 / -3.93 | 2.52 / 4.87 / -4.07 | 6.48 / 12.11 / -3.27 |
| A3 two-seed ensemble (ours) | 3.19 / 6.25 / -3.96 | 2.81 / 4.93 / -4.04 | 6.78 / 11.47 / -3.37 |
| HYB+tree mixture (ours, best acc.) | 2.76 / 5.34 / -3.51 | 2.67 / 4.77 / -3.53 | 4.88 / 8.76 / -3.30 |
| HYB: tree + A3 states (ours) | 2.89 / 5.54 / -3.49 | 2.96 / 5.12 / -3.51 | 5.13 / 9.07 / -3.26 |

| HGB, F2 (cycling+RPT features) | 3.05 / 5.61 / -3.51 | 2.77 / 4.88 / -3.55 | 5.01 / 8.87 / -3.29 |
| HGB, F0 (RPT-only features) | 3.10 / 5.81 / -3.46 | 2.96 / 5.44 / -3.48 | 5.44 / 9.80 / -3.20 |
| HGB, F1 (RPT+arrival correction) | 3.02 / 5.42 / -3.42 | 2.80 / 4.87 / -3.44 | 5.31 / 9.19 / -3.22 |
| HGB, F3 (full multisource) | 3.12 / 5.48 / -3.44 | 2.90 / 4.97 / -3.46 | 5.20 / 8.81 / -3.26 |
| CatBoost, F2 | 3.25 / 6.00 / -3.52 | 2.91 / 5.21 / -3.56 | 5.10 / 8.92 / -3.29 |
| CatBoost, F0 | 3.17 / 6.12 / -3.46 | 2.97 / 5.71 / -3.49 | 5.40 / 9.65 / -3.21 |
| CatBoost, F1 | 3.11 / 5.60 / -3.44 | 2.93 / 5.10 / -3.46 | 5.29 / 9.05 / -3.24 |
| CatBoost, F3 | 3.30 / 5.74 / -3.46 | 3.01 / 5.04 / -3.50 | 5.19 / 8.88 / -3.27 |
| GRU sequence baseline (external repr.) | 3.35 / 6.07 / -3.34 | 3.08 / 5.63 / -3.36 | 6.13 / 12.51 / -2.96 |
| Elastic net early-feature (external repr.) | 19.22 / 22.24 / -2.34 | 19.11 / 22.24 / -2.34 | 20.50 / 24.88 / -2.26 |

# Table 2: seed robustness, raw arm (2,326 common keys).

MAE in mAh. Generated from seed43_compare_run1/all_model_metrics.csv.

| Arm | seed-42 MAE | seed-43 MAE | NLL s42 | NLL s43 |
|---|---:|---:|---:|---:|
| A3_full | 3.06 | 3.06 | -3.93 | -3.93 |
| A3_time | 3.43 | 3.43 | -3.80 | -3.80 |
| A3_noRateUpdate | 7.09 | 7.09 | -3.27 | -3.27 |
| A3_noEll | 6.17 | 6.17 | -3.18 | -3.18 |

# Table 3: data efficiency, raw arm (2,326 common keys).

MAE in mAh. Trees retrained on the identical frozen pools.
Generated from degradation_curve_compare_run1/all_model_metrics.csv.

| Training pool | A3 | F0 HGB | F2 HGB |
|---|---:|---:|---:|
| 25% (31 cells) | 3.89 | 4.05 | 4.52 |
| 50% (62 cells) | 3.06 | 3.26 | 3.82 |
| 100% (125 cells) | 3.06 | 3.10 | 3.05 |
