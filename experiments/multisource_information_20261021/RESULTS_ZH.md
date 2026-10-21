# Raw-signal information value: first completed development evidence

This is the completed RPT pilot for the 2026-10-21 multisource research programme. It is not the formal four-cell 2x2 factorial requested in the human supplement. Historical pilot labels: F0=74 causal features; F1=F0+four raw RPT charge/discharge C/2,C/5 capacities with past differences/slopes; F2=F1+Q(V),dQ/dV curve history. Formal factor labels are specified separately in experiments/multisource_factorial_20261021/design.json.

## Real data asset

188 cells (125 train,63 development), 4,108 valid source RPTs, exact source-index/stop matches to reviewed DataV2. Per-cell features live on the server in reports/multisource_20261021_signals/all188_rpt_features_v1/. Manifest SHA256 f431eb082f09f455e8edec1cc62e944e116cea1a97544ca3b18abe5d6064c255. 61,412,452 feature bytes; zero new RPT downloads and zero C4 payload reads. 200 curve coordinates per RPT: Q(V) and local central dQ/dV on 25 fixed voltage points, four rate/leg combinations. No verified relaxation/pulse/temperature feature is fabricated. Unverified SOC hysteresis features are excluded. Both feature sample end and availability are conservatively the RPT stop plus the experimental reporting delay; source timestamps are retained. All scalars and Q are in source capacity units, with .25Ah nominal normalization in the benchmark; dQ/dV has Ah/V source convention. The exact point-level units still need source-code/integral reconciliation.

## Matched real experiment

124 training cells/6,870 arm-query examples; 62 development cells/3,765 arm-query examples. RUL metrics use the 61 development cells with known source events, current source-event Brier also includes the observed no-event-window cell. The frozen source event is first completed original RPT Q<=.20Ah; unknown subsequent outcomes are masked. Each physical cell has total training weight1. Two cell-isolated OOF regressions form each positive-RUL distribution. Existing V18 seed42 HGB hurdle reused exactly; new HGB F1/F2 and CatBoost F0/F1/F2 fit 20 estimators with predeclared hyperparameters. All new fits completed before development prediction. 22,590 saved predictions. Runtime 51.36s, excluding extraction.

| Model (historical pilot label) | Full RPT MAE, weeks | Sparse RPT MAE | 7-day delay MAE |
|---|---:|---:|---:|
| HGB F0 |2.0367|2.2381|2.3501|
| HGB F1 scalar |2.0368|2.2021|2.2961|
| HGB F2 curve |1.7942|1.9313|2.0095|
| CatBoost F0 |2.1353|2.2156|2.4135|
| CatBoost F1 scalar |1.9507|2.0818|2.2057|
| CatBoost F2 curve |1.7912|1.8610|1.9398|

Independent saved-prediction recomputation reproduced the main metrics and used 20,000 paired physical-cell bootstrap replicates. CatBoost curve-vs74 MAE improvements have positive 95% intervals in all three arms; HGB full-RPT interval crosses zero, sparse/delay do not. HGB has 1-2/61 and CatBoost 0-1/61 cells harmed by >2weeks. F2 CatBoost is not uniformly better: sparse-event Brier is worse than same-information HGB; calibration/coverage remain tradeoffs. See reports/multisource_20261021_literature/information_independent/INDEPENDENT_RECOMPUTE_ZH.md.

## Scientific interpretation and next decision

Raw RPT curve history contains useful development-set predictive information beyond the original74. The effect persists after adding four capacity scalars, but this pilot does not isolate normalized curve shape from capacity magnitude and does not establish an electrochemical causal mechanism. The evidence warrants the formal RPT x Cycling factorial and capacity-normalized curve controls, rather than another summary-only HGB calibrator.

Source Cycling data has been verified on one training cell: actual per-cycle voltage/current/capacity/energy and timestamps exist; temperature absent in inspected schema. Whole-member network responses failed twice. Completed compressed caches and all failed partials are retained. A fresh bounded acquisition now uses verified small range segments for missing members; no C4 members are selected. Acquisition is not feature-asset completion.

Candidate B and an independent-increment ablation have each completed500 optimization steps on actual irregular source RPT increments; C3 evaluation is separate and ongoing. This74-input mechanism prototype is not yet a raw-multisource method and its train-derived inspection schedule defines a different forecast intervention than the realized future source schedule. A requires actual aligned Cycling signals, not calendar time alone. No C4 confirmation or independent-generalization claim is authorized.

Limitations: repeatedly exposed C3, one seed for this information pilot, same-condition new-cell task, unverified physical serials, one chemistry, no unseen-condition group holdout yet. No complete paper contribution is claimed.
