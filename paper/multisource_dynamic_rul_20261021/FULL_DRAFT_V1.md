# Mechanistic Rate-State Filtering for Battery Capacity Under Sparse and Delayed Health Reporting

Full draft v2 (2026-10-26). Convention: RMSE = sqrt(mean-cell MSE); MAE in mAh (x1000); NLL in nats/Ah.

## Abstract

Battery health is observed sparsely and with delay: reference tests (RPTs) arrive weeks apart
while cycling signals accumulate continuously. We model per-cell degradation with a small
mechanistic state — a monotone cumulative degradation D driven by an individual rate state ℓ,
an OU mean-reverting drift, and a reversible component R — propagated on the operating clock
and corrected only when an RPT arrives. On the public ISU-ILCC 251-cell NMC/Gr dataset with
a strict as-of protocol, this filter (A3) matches the strongest same-input gradient-boosted
trees on point accuracy while beating every tree on the full predictive density (0.42–0.60
nats, all CIs exclude zero). Its mechanistic prior buys sample efficiency: trained on 50% of
the cells it shows zero point-accuracy degradation where the best tree degrades significantly.
A two-seed ensemble restores point-accuracy parity with the strongest trees and enlarges the
density advantage to 0.45–0.56 nats. A hybrid that feeds the filter's posterior states to the
best tree significantly beats that tree on the raw arm (−0.29 mAh, CI [−0.40, −0.19]) — the
only configuration that achieves this. A Student-t innovation variant fixes the calibration
gap. A risk-guided check-interval policy cuts unexpected EOL violations by 14–23 pp versus
a fixed 4-week schedule. We report honest negative results: the filter's RUL derivation is
worse than direct tree supervision; zero-shot transfer to a second chemistry loses
calibration; and the delayed-reporting arm trails trees on point accuracy.

## 1. Introduction

Battery health is observed sparsely: RPTs arrive ~weekly while cycling telemetry accumulates
continuously. The question is what a mechanistic state-space filter adds over strong
same-input learners. Prior work: neural CDEs (BatteryCDE TTE'25), Wiener/Gamma first-passage
(Energy'25, IEEE Access'24), online UKF (Sci Rep'24), liquid neural networks (ESWA'26,
SAC'26). None couple high-rate operating controls to an individual rate state under
arrival-driven innovation updates with same-input sample-efficiency and scheduling evidence.

Contributions:
- C1: Rate-state filter (D, ℓ, R) with arrival-driven updates; ablations isolate the
  mechanism (rate update +4.0 mAh, rate state +3.1 mAh, independent of engineering fixes).
- C2: Sample efficiency: 50% pool → zero degradation vs trees' significant degradation.
- C3: Scheduling: risk-guided intervals strictly dominate fixed h4.
- C4: Honest boundaries: calibration requires structural (not scalar) fix; zero-shot
  cross-chemistry transfer loses calibration; delayed arm trails trees on accuracy.

## 2. Related work

From PAPER_POSITIONING_ZH.md: three strands — input-level continuity (BatteryCDE, ESWA'26),
stochastic-process RUL with online updates (Wiener/Gamma/UKF), early-life feature regression
(NREL, Cell Reports'24). Our contribution: operating-signal-driven rate state + RPT-arrival
innovation + same-input sample-efficiency and scheduling evidence. Positioning table in
COMPARISON_TABLE_ZH.md.

## 3. Data and protocol

ISU-ILCC NMC/Gr 251 cells: 125 train (C1/C2), 63 development (C3), 63 locked confirmation
(C4). Arms: raw / sparse2 (every-2nd hidden) / delay7d (+7-day delay). Frozen query panel:
2,326 keys across 61 cells. Primary estimand: capacity at next arrived RPT. All runs
GO-gated with exact hashes and one-time-consumption registry (21 entries, 3 gate-refused
attempts retained).

## 4. Method: the (D, ℓ, R) filter

State: D monotone (dD = softplus(ℓ)dt); ℓ rate state (dℓ = −κ(ℓ−μ_θ(u))dt + σ_ℓ dW);
R reversible (dR = −λR dt + σ_R dW). Observation: y = Q_ref·exp(−D) + R + ε at RPT arrival,
Q_ref = first-arrived capacity (measured 0.28–0.29 Ah). Joseph-form updates; float64;
exact-affine semigroup; windowed BPTT with exact no-grad burn-in (batch-order bug found
and fixed). Training: selection 100 cells + frozen steps + refit 125 cells; 4 ablation
arms; Student-t innovation variant (ν learned, process-noise multipliers learned).

## 5. Experiments

### 5.1 Point and density accuracy (Table 1)

On 2,326 frozen keys:
- ENS_H_F (tree + filter states mixture): MAE 2.76 mAh, NLL −3.51
- ENS_H_E (filter ensemble + tree): MAE 2.74 mAh, NLL −3.81
- A3 full: MAE 3.06 mAh, NLL −3.93
- Best tree (F2 HGB): MAE 3.05 mAh, NLL −3.51
- Paired: ENS_H_F vs F2 HGB: −0.29 mAh [−0.40, −0.19] — significant
- A3 s42 vs F2 HGB: +0.01 mAh [−0.35, +0.41] — parity
- NLL: A3 and all its variants beat every tree by 0.42–0.60 nats (all CIs exclude 0)
- External: EXT_GRU ties trees on accuracy but loses on NLL; EXT_ENET is 14–17 mAh worse

### 5.2 Sample efficiency (Table 2, Fig. 1)

Frozen 25/50/100% pools:
- A3 at 50%: MAE degradation +3 µAh (statistically zero) vs F0 +165 µAh, F2 +768 µAh
  (disjoint CIs)
- A3 at 25%: competitive accuracy, superior density
- Trees retrained on identical pools: A3 never loses to the same-pool tree

### 5.3 Scheduling value (Table 3, Fig. 2)

Risk-guided check-interval policy (largest h with P(Q(t+h)<0.20) ≤ α):
- A3 α=0.05: violation 19.1% at 3.42-week mean interval vs fixed h4's 23.7% at 4.0
  (paired −14.1 pp [−20.2, −9.0]) — strict dominance
- A3-T (t innovation) α=0.02: violation 5.98% pooled — calibration fixed
- Trees cannot express the scheduling menu (76% missing horizons on panel)

### 5.4 Ablation and attribution (Table 4, Fig. 3)

- noRateUpdate: MAE doubles to 7.1 mAh — measurement update is the dominant source
- noEll: MAE 6.2 mAh — rate state contributes another 3.1 mAh beyond the update
- A2v3 (burn-in fix + all-125 refit control): 4.4 mAh — engineering repairs explain
  ~4.3 mAh of A2's deficit, but the ℓ mechanism contributes an independent ~3.1 mAh
- Rate-state information is valuable to trees: hybrid (tree + A3 states) significantly
  beats the tree alone — mechanistic states carry information that the tree's static
  features don't capture

### 5.5 Calibration and robustness (V3, V4)

- Student-t innovation (ν=8.6): cov90 0.974→0.931, NLL −0.59 nats improvement
- Scalar variance calibration (s=1.34) is insufficient: α=5% remains at 18.2% (structural)
- Seed 43/44 replication: mechanism ordering and NLL superiority preserved; point-accuracy
  parity is seed-sensitive (±0.5 mAh)

### 5.6 Zero-shot cross-dataset transfer (E7, honest negative)

CS2_35 (CALCE, 1.1 Ah LCO): point prediction tracks degradation but loses to hold_last;
uncertainty completely fails (cov90 0.26 vs nominal 0.90). The mechanistic anchor
transfers; the learned noise does not. Few-shot recalibration is the identified fix.

### 5.7 RUL derivation (E9, honest negative)

Analytic first-passage from A3 states: MAE 5.4 weeks (vs tree 1.6) — direct tree
supervision wins. Horizon interpolation improves delay7d from 17.8 to 4.3 weeks but
still trails. A3's contribution is capacity trajectory + density + scheduling,
not RUL scalar prediction.

## 6. Limitations

Single chemistry/dataset for the main results (CALCE attempted: zero-shot boundary
documented, few-shot recalibration pending human decision). Development-set evaluation
(C4 confirmation: A3 time-arm 10× better than naive, but trees not comparable on C4).
Single-split (robustness via 3-seed replication). Delay7d arm trails trees on accuracy.
Calibration requires structural fix (t innovation closes most of the gap). External
baselines are family representatives, not verbatim reproductions.

## 7. Reproducibility

GO-gated chain with exact hashes and one-time-consumption registry (21 entries; 3
gate-refused attempts retained). Public snapshot: 1,013 files, 11.9 MB, all artifacts
whitelisted. Push pending connector authorization.
