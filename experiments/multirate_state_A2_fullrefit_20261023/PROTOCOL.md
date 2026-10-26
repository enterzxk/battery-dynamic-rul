# A2 all-125 final refit: protocol repair, not a new architecture

The three existing final models were fit on 100 C1/C2 cells; the held internal25 were omitted. Preserve them. Refit once per arm using all125 legal training cells and a normalizer fit on all125, with frozen train-only selected steps full550/time100/noRPTupdate550; identical initialization42/sampling43, AdamW.001/.0001, batch8, window256/exact no-grad burn-in, clip1. No selection, new seeds or C3 calibration. Exactly3 fits/1200 optimizer steps. CPU4 threads; both sharedCPU locks, durable exclusive GO claim and incremental receipt.

Only the prepared train cache is read; no source archive, C3/C4, or old checkpoint payload. Fresh exact GO required, and CODEX_RETAKEOVER_20261023.json must verify DSH execution stopped. Preserve all old budgets/failed attempts/weights.

Next inference must use a separate GO and the same frozen queries, arms, target horizon and metrics as the previous A2 evaluation. Report same-key paired cell differences against old A2, F0/F2/F3 HGB/CatBoost. Capacity at a given horizon is conditional on h; using the realized next-check gap to score Q(q+h) does not establish an unconditional next-check or RUL prediction. Future operating values must remain declared past-only policy.

Do not call a better refit an architecture innovation. The state model still lacks an individualized latent degradation rate; assess this limitation before further mechanism development. A2 full-vs-time evidence pertains to this parametrization and held-operation forecast policy, not intrinsic harm of cycling measurements.
