# RULaaS fixed-HGB information-value gate

Development-only, zero-fit. Observed RPT information thinning; not fleet queue control or physical inspection savings.

|policy|positive-RUL MAE wk|cov80|IS80 wk|retained at-risk RPTs|
|---|---:|---:|---:|---:|
|all0|2.350901|0.7801|11.3871|965/965|
|all7|2.527397|0.7881|11.9568|965/965|
|half_even7|2.695319|0.7567|12.7246|499/965|
|half_odd7|2.725773|0.7464|12.7911|466/965|
|half_hash7|2.737879|0.7476|12.9304|488/965|
|anchor7|6.372320|0.5091|32.3899|0/965|

## Paired cell bootstrap (candidate minus reference)
- anchor7 vs all7: 3.844923 [3.189518, 4.538852] wk, 61 cells
- half_even7 vs all7: 0.167922 [0.096937, 0.237648] wk, 61 cells
- half_odd7 vs all7: 0.198377 [0.126861, 0.270872] wk, 61 cells
- half_hash7 vs all7: 0.210483 [0.128390, 0.289679] wk, 61 cells
- all7 vs all0: 0.176495 [0.094327, 0.262228] wk, 61 cells

## Decision
{
  "status": "COMPLETED_DEVELOPMENT_GATE",
  "screen_noninferiority_margin_weeks": 0.1,
  "margin_status": "engineering screening only; not externally justified SLO",
  "no_novelty_claim": true,
  "no_service_SLO_claim": true,
  "additional_RPT_value": "SUPPORTED_IN_THIS_FIXED_MODEL_GATE",
  "next_action": "Implement a bounded queue-aware observed-opportunity scheduler comparison; frozen model and delayed visibility, no controller using unavailable RUL labels.",
  "thinning_screen": [
    {
      "candidate": "half_even7",
      "passes_development_screen": false
    },
    {
      "candidate": "half_odd7",
      "passes_development_screen": false
    },
    {
      "candidate": "half_hash7",
      "passes_development_screen": false
    }
  ]
}

## Limits
- The 0.10-week margin is a development screen, not a validated noninferiority contract.
- All policies keep the first 3 RPTs free as warmup. Counts exclude warmup and describe retained information during the fixed reference at-risk window.
- Physical diagnostics, degradation interventions, queue interference, policy selection bias and delayed-label feedback have not been validated.
- All cheap cycling features, including capacity proxies, stay visible under identical source-completion assumptions.
- Primary queries have positive reference RUL, with a fixed policy-independent grid. Source-event and censored rows remain in predictions.
- C3 has been used repeatedly; no independent confirmation. No new fits; C4 payload reads zero.