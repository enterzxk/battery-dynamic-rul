# Multisource dynamic battery prognosis under sparse health reporting

Status: research manuscript scaffold, 21 October 2026. Development evidence is available for the raw-RPT information pilot and the first joint-trajectory candidate. The full factorial and multirate state experiments have not yet finished. Statements of superiority and novelty remain conditional on those experiments and independent review.

## 1. Problem and observable estimand

Let cell i have operating records u_ij completed at s_ij and health checks (t_ik,y_ik,c_ik), where y is the protocol capacity measurement in Ah and c contains raw diagnostic curves. A record's sampling end and its information arrival are different quantities. Denote arrival by a_ij or b_ik. At query q the permissible filtration is

F_i(q)=sigma{u_ij:s_ij<=a_ij<=q; (y_ik,c_ik):t_ik<=b_ik<=q; design information available before q}.

For this dataset communication arrival was not measured. RPT arrival is therefore an explicit experimental policy (complete, every-second report, or seven-day delay). Cycling availability at completion is an assumption, not a measured communication latency. Features must retain source identity, units, sample end, assumed arrival, and extraction algorithm.

The observed endpoint is T_i^obs=min{t_ik:y_ik<=0.20 Ah} for the original valid ISU-ILCC RPT sequence, with R_i(q)=max(0,T_i^obs-q) measured in weeks. Removing or delaying a report changes the information available to a predictor, not the original endpoint. An unobserved endpoint at the end of a finite source record remains unknown. Its observation mechanism is not asserted to be independent censoring.

T_i^obs is exact on the source observation grid. It is not an interval-censored physical failure time. If capacity can recover, the first latent crossing is not necessarily bracketed by the final above-threshold and first below-threshold measurements. Any latent first-passage analysis needs a separate stochastic path assumption and must be labeled accordingly.

The prediction problem has three outputs with distinct support: capacity at a requested future horizon, a distribution over future health trajectories, and the protocol-observed threshold-event/RUL distribution. Their relationship cannot be established by evaluating instantaneous P(Q(q)<=threshold) against a first-ever-event label.

## 2. Identifying information before changing architecture

The primary information experiment is a 2x2 factorial: F0 is the existing 74-dimensional causal summary; F1 adds arrived raw-RPT features; F2 adds completed Cycling records; F3 contains both increments. All four use identical physical cells, query timestamps, targets, weights, and evaluation rules. C1/C2 and C3 identify replicate roles within operating group G; C3 assesses new cells under represented conditions, not unseen conditions.

RPT features include four measured charge/discharge capacity summaries and Q(V), dQ/dV(V) at fixed voltages, with latest value, change from first visible report, and past stop-time slope. Missing support is retained. Extra capacity magnitudes are separated from capacity-normalized shape features. Cycling inputs contain actual leg voltage/current/energy summaries, durations, measured capacities, and observed throughput. A separate VI/E/time panel excludes capacity, Q endpoints, and throughput. Neither missing temperature nor unverified pulse/impedance signals are synthesized.

Two strong families, HGB and CatBoost, are trained independently at every information level. Physical-cell-isolated OOF residuals construct the positive-RUL distribution. The factorial interaction for loss L is

I_L=(L_F3-L_F1)-(L_F2-L_F0).

This measures a prediction-level interaction under the specified learners; it is not automatically a causal interaction or an information-theoretic mutual information estimate. Cell-paired intervals and per-cell harm accompany aggregate effects.

For consecutive queries with unchanged RPT history, the earlier forecast can be transported exactly as R_b=max(0,R_a-(q_b-q_a)). Compare that transported distribution, a refreshed F0/F1 prediction, and a refreshed F2/F3 prediction on the same query-b targets. Prediction movement alone does not establish useful state updating.

## 3. Candidate A: multirate state propagation and report correction

The candidate state x=(D,R) separates accumulated log damage D from a reversible capacity offset R. The state-to-capacity map is h(x)=Q_nom exp(-D)+R. D is constrained to increase during propagation; it is not asserted to be directly measured or uniquely identifiable from capacity alone. Report correction can change the posterior estimate of D in either direction.

For an operating interval Delta and past-visible record u, a learned transition outputs nonnegative damage rate d(u,Delta), relaxation rate lambda(u,Delta), equilibrium r_eq(u,Delta), and nonnegative process variances v_D,v_R. Write alpha=exp(-lambda Delta). Conditional propagation is

D'=D+d Delta;
R'=alpha R+(1-alpha)r_eq;
P'=diag(1,alpha) P diag(1,alpha)+diag(v_D Delta,v_R(1-alpha^2)).

Missing inputs are represented by value/mask pairs. Calendar-only propagation is explicit when no operating record is available. At an arrived RPT, a nonlinear Gaussian correction uses H=(-Q_nom exp(-D),1), S=H P H^T+V, K=P H^T/S, and a Joseph covariance update. A bounded curve-conditioned observation correction is allowed only when that curve has arrived with the same report. In A_full_F3, the correction head uses 200 Q(V)/dQdV(V) curve slots normalized by the same arrived capacity y, while y remains explicit in the innovation. These inputs are dependent; this is a learned curve-conditioned observation model with a Gaussian-approximate (EKF-style) update, not an exact Bayesian update absent an explicit joint measurement likelihood. Delayed reports are replayed at their source times after applying the query-time arrival barrier.

The transition coefficients do not depend on the hidden state. Therefore a consecutive block of n operating intervals can be propagated exactly, rather than truncated or approximately pooled:

D_n=D_0+sum_i d_i Delta_i;
R_n=(prod_i alpha_i)R_0+sum_i[(1-alpha_i)r_eq,i prod_{j>i}alpha_j];
P_DD,n=P_DD,0+sum_i v_D,i Delta_i;
P_DR,n=(prod_i alpha_i)P_DR,0;
P_RR,n=(prod_i alpha_i^2)P_RR,0+sum_i[v_R,i(1-alpha_i^2)prod_{j>i}alpha_j^2].

The implementation includes the numerical covariance jitter in this equivalence. The operation-conditioned transition noises are treated as conditionally independent across event intervals. A synthetic double-precision comparison checked means, covariances and gradients before real fitting. This computational identity is not by itself a scientific novelty claim.

Training predicts the next source capacity at a requested horizon from the query state and the same 74-dimensional context, without actual future operating inputs. The future policy used for training and next/trajectory evaluation must be identical. Readout corrections are recorded to detect whether a flexible output head bypasses the state. Compare operating-input removal and explicit-RPT-correction removal separately. The latter retains the common F0 report summary; it is not a zero-RPT-information model.

This A experiment evaluates state/next-capacity/trajectory quality. Instantaneous capacity-threshold probabilities are diagnostics. They do not supply a valid natural source-event RUL distribution without a model of the relevant inspection and path process.

## 4. Candidate B: path distributions and threshold events

The first candidate models irregular health increments with a conditional Gaussian transition and a recurrent path state, compared with an independent-increment counterpart. Training likelihood factors over actual training source transitions; future values are used only as supervision, not query features. Short-term positive capacity increments are permitted. Sampling is autoregressive and does not sort or clip trajectories to force monotonicity.

For a specified future inspection policy pi with check times S_pi, define

T_pi=min{s in S_pi:Q(s)<=Q_threshold}, R_pi(q)=max(0,T_pi-q).

For sampled coherent paths, the event CDF is the fraction whose first sampled protocol check has crossed by each horizon. Already-hidden past checks, the atom at zero, and unresolved right-tail mass must be represented. Event-bin probabilities plus tail mass must sum to one. The numerical calendar used for scoring and event binning is reconstructed from the frozen train-only schedule with consistent precision.

The first completed experiment uses a deterministic repeated train-gap schedule. Its R_pi is an intervention-specific quantity and cannot be silently equated to the natural unknown future source grid. Next-capacity forecasts at requested source times and teacher-forced transition likelihoods remain useful diagnostics, with their information permissions stated. Comparing restricted RUL point errors against natural source endpoints is exploratory under the schedule assumption, not independent confirmation of the event law.

A complete natural-protocol extension would require p(S_future,U_future | F(q)) and integrate over future inspections and operations, or restrict claims to an explicitly controlled inspection policy. This is a substantive identification requirement, not a plotting choice. No true future operations or test-derived inspection distribution may be inserted to improve scores.

## 5. Falsifiable questions and experiment commitments

Q1: compare 2x2 main effects plus scalar, normalized-shape and VI/E/time controls. A gain confined to extra capacity magnitudes does not establish independent shape information.

Q2: evaluate unchanged-RPT-history query pairs against exact time transport and same-input strong refreshed baselines. Signals that move forecasts without improving error/calibration do not establish reliable updating.

Q3: evaluate pre/post-arrival capacity innovations and uncertainty, with explicit-update ablation retaining common input permissions. Static summary access and sequential correction are distinct mechanisms.

Q4: compare B against strong next-capacity regressors using the same 74 inputs and requested horizon, against its independent path mechanism, and against direct-RUL baselines where the event estimand is compatible. Better transition likelihood without better path/event calibration is a limited result.

Q5: report physical-cell effects, SOH stages, forecast lead times, report sparsity/delay, serious overestimation, calibration and runtime. A separate G-group holdout inside legal C1/C2 training data is required before claiming unseen-condition generalization. Constant-condition cells cannot by themselves establish within-cell robustness to operating-regime changes.

C4 stays sealed through development. Independent confirmation requires a frozen candidate, exact source/protocol/model hashes and a new limited authorization. No consumed GO, negative model result or historical V18 result is replaced.

## 6. Second-chemistry qualification

The official UConn-ISU-ILCC LFP/Gr dataset page describes 64 cells, 11 conditions, 1 Hz RPT/Cycling records and approximately 3.5-day checks with short pulses. The official author repository exposes pulse feature extraction at SOC 20/50/90 and capacity/SOH definitions. It also documents an approximately four-minute pulse interruption in the reference charge that its processed analysis interpolates across. Such interpolation must not be silently inherited as a measured continuous signal in this online protocol.

The official raw README and parameter attachments returned HTTP403 in the present read attempts. Raw acquisition/protocol qualification and a legal internal split are therefore unfinished; no second-chemistry result is claimed. Its capacity denominator, voltage range, pulse current and event definition will be established within that dataset rather than copied from the 0.25Ah ISU study.

Sources: https://digitalcommons.lib.uconn.edu/reil_datasets/1/ ; https://github.com/REIL-UConn/fine-tuning-for-rapid-soh-estimation/blob/main/scripts/data_processing/postprocessing.py ; DOI 10.1016/j.jpowsour.2024.235813 and 10.1016/j.ensm.2025.104425.

## 7. Current contribution boundary

The existing raw-RPT pilot provides real information-value evidence, with paired improvements for CatBoost across three reporting arms and weaker/mixed architecture-specific probability results. The complete RPT/Cycling factorial, A mechanism, unseen-group evaluation and independent confirmation are pending. The initial recurrent B path model has a mechanism signal relative to independent increments but has not established superiority over fair strong baselines. A high-level method-paper contribution must be supported by those subsequent results, not inferred from the use of continuous-time notation, filtering, recurrence or first-passage sampling. The initial state is initialized at the first replayed source event; without an earlier event, calendar propagation before the query is not anchored to a measured cell-origin timestamp. This initialization convention limits interpretation of early queries and must be stated with any A results.


## Empirical information result (C3 development, 21 October 2026)

The complete 2x2 experiment retrains HGB and CatBoost on equal information and query sets, with80 fits and75300 saved predictions. HGB F0 to F3 MAE is2.029 to1.606 weeks (full),2.230 to1.730 (sparse),2.344 to1.826 (7-day delay). Shape normalization and VI/time controls support further signal research, with model-dependent paired uncertainty. CatBoost severe overestimation and calibration-distance deterioration rule out a blanket reliability claim. The first B trajectory prototype loses against same-information next-capacity tree baselines; its fixed inspection schedule changes the estimand. Candidate A and the off-inspection-time evaluation are pending. See the source-backed Chinese information report for all paired controls and limits. No C4 result is available.

## Empirical results update — 22 October 2026 (C3 development only)

Scope: every number below is C3 source-63 development evidence. C4 was not read, not
inferred and not trained. Each run was issued under a fresh exact-hash root GO with a
durable receipt; the zero-fit comparisons read saved predictions only and record zero
payload, weight and C4 reads. One comparison was retracted during the day and is reported
here with its correction, not hidden.

### Candidate A (four-state capacity mechanism) — negative, mechanism-diagnosed

- Exact-key matched comparison (3,579 queries, 61 cells, three reporting arms, 5,000
  cell-bootstrap replicates): A's four variants give cell-balanced RMSE 0.01274–0.01313 Ah,
  against 0.00782–0.00888 Ah for the same-information tree baselines and 0.01208 Ah for a
  naive past-slope control. Paired differences exclude zero in every arm.
- Diagnostics: state-only capacity RMSE is 0.031 Ah while the readout-corrected error is
  0.0098 Ah (mean signed readout offset +0.019 to +0.026 Ah); RPT updates contract the
  covariance only 2.8–4.2 % and move the state by 0.002–0.004 Ah against innovations of
  0.032–0.039 Ah. The parameterisation — nominal 0.25 Ah anchor, learned readout bypass, and
  a network output used as a variance — absorbs the information before the state can use it.
- Consequence: A was replaced by A2 (first-arrived Q_ref anchor, state-only Q_ref·e^{−D}+R,
  no readout bypass, σ as a standard deviation with variance σ²).

### Candidate B (joint marked-renewal trajectories) — negative, with a retracted comparison

- Four mandatory fixes (lock/device/standardisation discipline, global proposal-order
  truncation, float64 epochs, predeclared conditioning-off and fixed-gap controls with
  posterior-conditional marks) were implemented before any fit; 38,963 teacher-forced
  transitions from 2,506 anchored paths over 124 contributing train cells, and exactly four
  neural fits, were completed. C3 inference produced 18,922 rows over 63 cells with 68
  frozen-contract failures (0.36 %; 65 of them in the fixed-gap control arm, 3 in the main
  panel).
- The first comparison (19:20) concluded that B2 beat the saved B1 mechanism model. That
  conclusion was wrong: the comparison key map did not filter the comparator's `model`
  column, so B1's `independent` ablation overwrote B1 `full`. An independent review found
  it; the comparison was rewritten with an explicit `model == "full"` filter and a
  per-key target-equality assertion, and re-run under a new GO.
- Corrected result on 4,637 exact keys / 61 cells: B1 `full` is better on every proper
  score — cell-MAE 4.111 versus 6.384 (B2 joint) and 6.346 (independent) weeks; pinball50
  2.056 versus 3.192/3.173; interval score (80 %) 22.96 versus 38.17/35.00; 80 % coverage
  0.608 versus 0.550/0.687 with a narrower interval (7.11 versus 9.91/18.87 weeks). Paired
  ΔMAE (B2 − B1 full) is +2.27 weeks [0.76, 4.23]. Including the 815 rule-zero known-event
  queries, which both models predict as zero, gives 5.05/4.98 versus 3.20 weeks, so the
  exclusion is conservative.
- The horizon split does not rescue the claim: only the 0–4 week stratum favours the
  independent variant (0.74 versus 1.13 weeks); 4–12, 12–32 and 32+ weeks are all worse
  (3.18/5.07 versus 3.08; 11.5/11.8 versus 6.89; 45.1/29.3 versus 20.4), and joint 80 %
  coverage at 32+ weeks is 0.074.
- Mechanistic contrasts are still informative: joint versus product-of-marginals changes MAE
  by +0.03 weeks [−1.69, +1.79] while halving the interval and dropping coverage from 0.69
  to 0.55 (over-confident, no accuracy gain); the no-extra-arrival constraint changes MAE by
  +0.005 weeks [−0.002, +0.012]; fixing the inter-report gap gives +11.7 weeks but that
  contrast loses 65 of its queries on the acceptance floor, with failed targets at a median
  of 24.5 weeks versus 10.25 for the survivors, so it is a directional diagnostic rather
  than a paired effect.
- One-step next-source capacity (1,806 raw exact-source queries) also favours the 18-fit
  trees: NLL −3.46 versus +3.55 per Ah and RMSE 0.0057 versus 0.0091 Ah.

### Candidate A2 — mechanism works, still short of strong trees

A2's six selection/refit fits are complete, and its C3 evaluation has run twice: once for the original 100-cell
checkpoints (63 cells, 2,350 as-of queries, 7,050 model rows; zero fits, zero C4/raw reads) and once after a
protocol repair that refit the final checkpoints on all 125 training cells (the 25 held-internal-validation cells
included) with frozen selection step counts. The first-arrived anchor lands at Q_ref = 0.279-0.287 Ah, which is
exactly the offset that A1 absorbed through its readout. Replacing the readout with the state-only map
Q = Q_ref·e^{−D} + R, with the RPT innovation NLL and sigma as a standard deviation, moves the
next-source-capacity error from A1's 0.031 Ah (state-only) to about 0.010 Ah RMSE with no readout at all.

On 903 exact-source raw keys over 61 cells, scored under the primary convention RMSE = sqrt(mean-cell MSE), the
best A2 arm (time-only control, all-125 refit) reaches NLL −3.122, RMSE 0.0101 Ah and MAE 0.0051 Ah, against
−3.465 / 0.0057 / 0.0033 for the F3 CatBoost tree on the same keys; the paired cell bootstrap puts A2 time behind
the F0 HGB tree by 1.97 mAh [1.29, 2.86] MAE on raw (1.35 mAh on sparse2, 4.65 mAh on delay7d) with NLL the same
direction. The all-125 refit itself changed almost nothing for the time arm (paired MAE +0.00006 Ah versus the
100-cell version) and slightly improved the full arm's point accuracy while worsening its NLL — the protocol gap
was real but not load-bearing. The no-RPT-update arm degrades to 0.059 Ah RMSE, an order of magnitude worse, so
the measurement update is the dominant information source, and the full arm remains 5.4 mAh [3.7, 7.1] worse than
the time arm: under this parameterisation, training scale and held-operation forecast policy the 24-dimensional
cycle control hurts (the same cycle information is useful to the F2 trees, so this is not a claim about cycling
signals in general).

The mechanism is therefore established and clearly better than A1 and B2, but it does not yet beat the strong
trees, with a single split and seed on the C3 development set. No superiority claim is warranted.



### Candidate A3 — the individual rate state closes the gap

A3 makes the degradation rate itself a filtered state: x = (D, ℓ, R) with dD = softplus(ℓ)·dt (D is
pathwise non-decreasing by construction), dℓ = −κ(ℓ − μ_θ(u))·dt + σ_ℓ dW, and the same reversible
component and RPT observation map as A2. The rate ℓ is not directly observed; it is updated only
indirectly, through the dependence of the observation on exp(−D). Training follows the repaired
protocol (selection on the 100 internal train cells, frozen step counts, final refit on all 125
cells) under a single 8-fit GO, with a consumed-GO registry now enforcing one-time GO use.
Four ablation arms share the engine: full (cycle-driven rate mean + rate updates), noRateUpdate
(rate never updated by measurements), time (constant rate mean), and noEll (no rate state at all —
the A2-type structure with the burn-in repair and the all-125 refit).

On the 2,326 frozen common keys (5,000-cell paired bootstrap), A3-full is the first mechanism model
in this project that does not lose to the strong same-input trees. On raw exact-source queries its
MAE 0.003062 Ah is statistically indistinguishable from the best tree (paired difference vs F2 HGB
+12 µAh [−354, +414]); on sparse reporting (sparse2) it is significantly better than F0 HGB
(−0.44 mAh [−0.92, −0.03]) and F3 CatBoost (−0.49 mAh [−0.84, −0.14]); on 7-day-delayed reporting it
remains 1.0–1.5 mAh behind on MAE, with NLL already tied. On the full predictive density it wins
decisively where the trees have no mechanism: NLL is better by 0.42–0.47 nats on raw and 0.52–0.60
nats on sparse2 against every tree (all CIs exclude zero), with better calibrated intervals
(cov90 0.959 vs the trees' 0.98 and A2's 0.984).

The ablations attribute the gain to the mechanism, not to the protocol repairs. Removing the rate
update (noRateUpdate) more than doubles the raw MAE (0.0071 Ah); removing the rate state entirely
(noEll) costs another 3.1 mAh; and noEll — which contains the burn-in repair and the all-125 refit —
still beats A2-full by only 4.3 mAh, so the ℓ mechanism contributes an independent ~3.1 mAh beyond
the repairs. Routing cycle information through the rate state also reverses the A2 finding: the
full arm now beats the time arm, so completed cycle controls are useful as drivers of the *rate
prior* even though adding them as exogenous state inputs was harmful. The remaining honest
limitation is the delay arm and the single split/seed on the development set; no independent-
confirmation claim is made.
### Contribution boundary (updated)

The defensible contributions are (i) a quantified information-value result under sparse and
delayed health reporting and (ii) a diagnosed mechanism account of why the four-state
capacity parameterisation failed and what the redesign fixed. Neither candidate beats a fair
strong baseline on C3 yet: B2 is beaten by the previous B1 mechanism model on point,
probability and interval scores, A2 recovered the state mechanism but stayed behind; its redesigned successor
A3 — an individual degradation-rate state updated through the capacity measurements — is the
first candidate that matches the strongest same-input trees on point accuracy (raw and sparse2)
and beats all of them on the full predictive density, with in-engine ablations attributing the
gain to the rate mechanism rather than to protocol repairs. These are development-set results
with a single seed; the delayed-reporting arm is still behind on MAE. No
independent-confirmation claim is warranted, and the A3 result is not yet replicated.
