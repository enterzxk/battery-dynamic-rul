# Implemented mechanism and observation protocol

These branches are evaluated separately. An integrated A+B model has not been implemented.

```mermaid
flowchart LR
    O[Completed operating records<br/>V / I / Q / E / source clock] --> G[As-of arrival gate<br/>unknown time stays missing]
    H[Arrived valid RPT<br/>capacity and optional normalized curves] --> G
    G --> R[Replay in source-time order<br/>only reports available at query]
    R --> T[Operating-input state transition<br/>nonnegative mean damage drift<br/>reversible offset / process covariance]
    T --> U[RPT capacity observation update<br/>EKF and Joseph covariance update]
    U --> S[Query posterior<br/>state mean and covariance]
    S --> P[No actual future operations<br/>calendar-only horizon propagation]
    X[Same legal 74-feature query context] --> D[Learned capacity readout correction]
    P --> D
    D --> C[Capacity mean and uncertainty<br/>future observation-horizon scoring]
    S -.-> L[Separate train-operation scenario<br/>latent first-passage diagnostic]
```

A's damage drift is nonnegative in mean. Gaussian process noise and Bayesian corrections do not impose pathwise monotonicity. Capacity readout can bypass the latent state; its adjustment and state increments are recorded to test this failure mode. The latent first-passage diagnostic is not the source-observed RPT event target.

```mermaid
flowchart LR
    Q[Query and arrived RPT history<br/>source indices / arrival policy] --> A[Last arrived valid source-RPT anchor]
    A --> J[Conditional valid-check renewal law<br/>next gap / source-index jump / capacity increment]
    J --> N[Condition on no additional due report<br/>integrate unreported checks before query]
    N --> F[Joint future recorded-RPT paths<br/>unknown future operations marginalized]
    F --> E[First valid source RPT at or below threshold]
    E --> R[Clipped RUL distribution<br/>event mass at zero / restricted tail]
    F --> K[Joint clock-capacity density<br/>conditional next-capacity and ordinal trajectories]
```

B2's second diagram is an implementation design under development, with no empirical claim. The model excludes administrative censor likelihood because stopping reasons remain unknown. Index gaps preserve invalid source slots. First-event labels refer to recorded valid RPTs and never assert a latent physical crossing. Fixed-gap and independent-marginal controls must be scored using the same target and horizon support.
