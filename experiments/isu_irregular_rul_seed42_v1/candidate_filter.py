"""Causal two-timescale state filter; no parameter fit or RUL prediction."""
from __future__ import annotations
from dataclasses import dataclass, replace
import math
from typing import Optional, Sequence, Tuple

Matrix2 = Tuple[Tuple[float, float], Tuple[float, float]]

@dataclass(frozen=True)
class FilterParams:
    # Gamma-process increment moment rates: E[dx]=mu*dt; Var[dx]=v*dt.
    loss_drift_per_day: float
    loss_variance_per_day: float
    # OU parameters: kappa per day and stationary variance in Ah^2.
    ou_kappa_per_day: float
    ou_stationary_variance: float
    measurement_variance: float
    def validate(self):
        vals=(self.loss_drift_per_day,self.loss_variance_per_day,self.ou_kappa_per_day,
              self.ou_stationary_variance,self.measurement_variance)
        if any(not math.isfinite(v) or v<0 for v in vals) or self.measurement_variance<=0:
            raise ValueError("invalid filter parameters")
        if self.loss_drift_per_day==0 and self.loss_variance_per_day>0:
            raise ValueError("nonzero Gamma variance requires positive mean rate")
        if self.ou_kappa_per_day==0 and self.ou_stationary_variance>0:
            raise ValueError("OU stationary variance requires positive mean-reversion rate")

    def gamma_shape_scale(self):
        """Return (shape/day, scale_Ah); deterministic zero-variance limit is None."""
        self.validate()
        mu=self.loss_drift_per_day
        var=self.loss_variance_per_day
        if mu==0.0 and var==0.0:
            return (0.0,0.0)
        if var==0.0:
            return (math.inf,0.0)  # deterministic Gamma moment limit
        return (mu*mu/var,var/mu)


@dataclass(frozen=True)
class FilterState:
    time_day: float
    q_reference: float
    irreversible_loss: float
    reversible_offset: float
    covariance: Matrix2
    last_sample_day: Optional[float]=None
    last_arrival_day: Optional[float]=None
    last_standardized_innovation: Optional[float]=None
    last_innovation_sd: Optional[float]=None
    update_was_projected: bool=False
    processed_observation_ids: Tuple[str,...]=()
    @property
    def staleness_days(self):
        return None if self.last_sample_day is None else max(0.0,self.time_day-self.last_sample_day)


def _check_cov(p: Matrix2):
    if any(not math.isfinite(v) for row in p for v in row):
        raise ValueError("nonfinite covariance")
    if p[0][0]<-1e-10 or p[1][1]<-1e-10 or abs(p[0][1]-p[1][0])>1e-8:
        raise ValueError("invalid covariance")
    if p[0][0]*p[1][1]-p[0][1]*p[1][0]<-1e-8:
        raise ValueError("covariance is not positive semidefinite")


def propagate(state: FilterState, target_day: float, params: FilterParams) -> FilterState:
    """Propagate process moments only; add no health innovation or survival evidence."""
    params.validate()
    dt=target_day-state.time_day
    if not math.isfinite(target_day) or not math.isfinite(dt) or dt<0:
        raise ValueError("runtime clock must move forward and be finite")
    if dt==0: return state
    phi=math.exp(-params.ou_kappa_per_day*dt)
    x=state.irreversible_loss+params.loss_drift_per_day*dt
    z=phi*state.reversible_offset
    p=state.covariance
    pxx=p[0][0]+params.loss_variance_per_day*dt
    pxz=phi*p[0][1]
    pzz=phi*phi*p[1][1]+params.ou_stationary_variance*(1.0-phi*phi)
    cov=((max(0.0,pxx),pxz),(pxz,max(0.0,pzz)))
    _check_cov(cov)
    return replace(state,time_day=target_day,irreversible_loss=max(state.irreversible_loss,x),
                   reversible_offset=z,covariance=cov,update_was_projected=False)


def predicted_capacity(state: FilterState) -> float:
    return state.q_reference-state.irreversible_loss+state.reversible_offset


def initialize_from_first_sample(observation_id: str, sample_day: float, arrival_day: float,
                                 capacity: float, loss_prior_variance: float,
                                 offset_prior_variance: float, params: FilterParams) -> FilterState:
    """Initialize only when first RPT arrives; return no state from before arrival.

    The first arrived capacity defines q_reference at sample time. Explicit process
    covariance priors are initialized there, then the corrected state is propagated
    to arrival. Callers cannot obtain a feature state at sample time from this API.
    """
    params.validate()
    vals=(sample_day,arrival_day,capacity,loss_prior_variance,offset_prior_variance)
    if not observation_id or any(not math.isfinite(v) for v in vals):
        raise ValueError("first observation and finite times/values are required")
    if arrival_day<sample_day or capacity<=0 or loss_prior_variance<0 or offset_prior_variance<0:
        raise ValueError("invalid first observation")
    sample_state=FilterState(sample_day,capacity,0.0,0.0,
        ((loss_prior_variance,0.0),(0.0,offset_prior_variance)),
        sample_day,arrival_day,None,None,False,(str(observation_id),))
    _check_cov(sample_state.covariance)
    return propagate(sample_state,arrival_day,params)


def update_at_sample(state: FilterState, observation_id: str, sample_day: float,
                     arrival_day: float, capacity: float, params: FilterParams) -> FilterState:
    """Apply a previously unprocessed observation at sample time during causal replay."""
    params.validate()
    if not observation_id or str(observation_id) in state.processed_observation_ids:
        raise ValueError("missing or already processed observation ID")
    if abs(sample_day-state.time_day)>1e-8:
        raise ValueError("propagate to sample time before measurement update")
    if (not all(math.isfinite(v) for v in (sample_day,arrival_day,capacity))
            or arrival_day<sample_day or capacity<0):
        raise ValueError("invalid arrival time or capacity")
    p=state.covariance
    # y=q_ref-x+z+epsilon, H=(-1,+1)
    innovation=capacity-predicted_capacity(state)
    pht=(-p[0][0]+p[0][1],-p[0][1]+p[1][1])
    s=p[0][0]+p[1][1]-2*p[0][1]+params.measurement_variance
    if s<=0 or not math.isfinite(s): raise ValueError("invalid innovation variance")
    k=(pht[0]/s,pht[1]/s)
    raw_x=state.irreversible_loss+k[0]*innovation
    projected=raw_x<state.irreversible_loss
    if projected:
        # Approximate constrained update: rebound cannot lower irreversible loss.
        k=(0.0,p[1][1]/(p[1][1]+params.measurement_variance))
    x=max(state.irreversible_loss,state.irreversible_loss+k[0]*innovation)
    z=state.reversible_offset+k[1]*innovation
    # Joseph covariance update remains PSD for this selected gain; this is not an
    # exact posterior covariance after the nonlinear state-mean projection.
    a=((1.0+k[0],-k[0]),(k[1],1.0-k[1]))
    ap=((a[0][0]*p[0][0]+a[0][1]*p[1][0],a[0][0]*p[0][1]+a[0][1]*p[1][1]),
        (a[1][0]*p[0][0]+a[1][1]*p[1][0],a[1][0]*p[0][1]+a[1][1]*p[1][1]))
    post=((ap[0][0]*a[0][0]+ap[0][1]*a[0][1]+k[0]*k[0]*params.measurement_variance,
           ap[0][0]*a[1][0]+ap[0][1]*a[1][1]+k[0]*k[1]*params.measurement_variance),
          (ap[1][0]*a[0][0]+ap[1][1]*a[0][1]+k[1]*k[0]*params.measurement_variance,
           ap[1][0]*a[1][0]+ap[1][1]*a[1][1]+k[1]*k[1]*params.measurement_variance))
    cov=((post[0][0],0.5*(post[0][1]+post[1][0])),
         (0.5*(post[0][1]+post[1][0]),post[1][1]))
    _check_cov(cov)
    ids=state.processed_observation_ids+(str(observation_id),)
    last_arrival=max(arrival_day,state.last_arrival_day if state.last_arrival_day is not None else arrival_day)
    return replace(state,irreversible_loss=x,reversible_offset=z,covariance=cov,
                   last_sample_day=sample_day,last_arrival_day=last_arrival,
                   last_standardized_innovation=innovation/math.sqrt(s),
                   last_innovation_sd=math.sqrt(s),update_was_projected=projected,
                   processed_observation_ids=ids)


def replay_to_arrival(checkpoint: FilterState, observations: Sequence[dict],
                      arrival_day: float, params: FilterParams,
                      max_replay_days: float) -> FilterState:
    """Replay complete unseen suffix; checkpoint must strictly precede every sample.

    IDs must be unique within the suffix and absent from the checkpoint watermark.
    Future arrivals are excluded. Exceeding the replay bound is an explicit error.
    """
    if (not math.isfinite(arrival_day) or not math.isfinite(max_replay_days)
            or max_replay_days<=0 or arrival_day<checkpoint.time_day):
        raise ValueError("invalid replay window or arrival clock")
    if arrival_day-checkpoint.time_day>max_replay_days:
        raise RuntimeError("bounded replay window exceeded")
    eligible=[]; seen=set(); processed=set(checkpoint.processed_observation_ids)
    for o in observations:
        oid=str(o["id"])
        sample=float(o["sample_day"]); arrived=float(o["arrival_day"]); cap=float(o["capacity"])
        if not oid or oid in seen: raise ValueError("duplicate/empty observation ID in replay suffix")
        seen.add(oid)
        if oid in processed: raise RuntimeError("replay would double-apply a processed observation")
        if not all(math.isfinite(v) for v in (sample,arrived,cap)) or arrived<sample or cap<0:
            raise ValueError("invalid observation timestamp or capacity")
        if sample<=checkpoint.time_day+1e-8:
            raise RuntimeError("checkpoint must strictly precede every replayed sample")
        if sample>arrival_day or arrived>arrival_day: continue
        eligible.append(o)
    eligible.sort(key=lambda o:(o["sample_day"],o["arrival_day"],str(o["id"])))
    state=checkpoint
    for o in eligible:
        if o["sample_day"]<state.time_day-1e-8:
            raise RuntimeError("checkpoint predates every replayed update")
        state=propagate(state,o["sample_day"],params)
        state=update_at_sample(state,str(o["id"]),o["sample_day"],o["arrival_day"],o["capacity"],params)
    return propagate(state,arrival_day,params)


def export_filter_features(state: FilterState):
    """Causal representation; callers must only export at/after last arrival."""
    if state.last_arrival_day is not None and state.time_day+1e-8<state.last_arrival_day:
        raise RuntimeError("cannot expose a state before the latest measurement arrival")
    p=state.covariance
    return {"long_loss":state.irreversible_loss,"short_reversible_offset":state.reversible_offset,
            "loss_variance":p[0][0],"offset_variance":p[1][1],"state_covariance":p[0][1],
            "age_day":state.time_day,"staleness_days":state.staleness_days,
            "last_standardized_innovation":state.last_standardized_innovation,
            "last_innovation_sd":state.last_innovation_sd,
            "update_was_projected":state.update_was_projected}
