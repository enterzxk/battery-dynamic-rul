"""As-of causal filter representations for approved origin objects only.

This O(n)-per-origin reference implementation deliberately recomputes from the
first currently visible RPT. It does not inspect cell source labels or hidden rows.
"""
from __future__ import annotations
from typing import Mapping, Sequence
from dataclasses import replace
import math

from candidate_filter import (
    FilterParams, initialize_from_first_sample, propagate, update_at_sample,
    export_filter_features,
)

DAY=86400.0
LOSS_PRIOR_VARIANCE_AH2=1.0e-5
OFFSET_PRIOR_VARIANCE_AH2=1.0e-5
MAX_REPLAY_DAYS=35.0


def _records_at_origin(origin: Mapping) -> tuple[list, float]:
    """Read only origin.visible_records, already arrival-screened by data_adapter."""
    if "visible_records" not in origin or "origin_stop_epoch" not in origin:
        raise ValueError("origin lacks screened visible_records/origin_stop_epoch")
    query=float(origin["origin_stop_epoch"])
    if not math.isfinite(query):
        raise ValueError("nonfinite as-of query time")
    rows=list(origin["visible_records"])
    if not rows:
        raise ValueError("no visible health observations")
    for r in rows:
        if not all(k in r for k in ("source_rpt_index","stop_epoch","arrival_epoch","capacityAh")):
            raise ValueError("visible record missing stable ID/sample/arrival/capacity")
        t=float(r["stop_epoch"]); a=float(r["arrival_epoch"]); q=float(r["capacityAh"])
        if not all(math.isfinite(v) for v in (t,a,q)) or t>query or a>query or a<t or q<0:
            raise ValueError("visible record violates sample/arrival barrier or has invalid value")
        if (a-t)/DAY>MAX_REPLAY_DAYS:
            raise RuntimeError("late-measurement replay exceeds frozen 35-day bound")
    rows.sort(key=lambda r:(float(r["stop_epoch"]),int(r["source_rpt_index"])))
    ids=[str(int(r["source_rpt_index"])) for r in rows]
    if len(ids)!=len(set(ids)):
        raise ValueError("duplicate observation IDs in visible prefix")
    return rows,query


def filter_state_for_origin(origin: Mapping, params: FilterParams):
    """Recompute visible prefix by sample time, then propagate to query.

    The first visible RPT supplies q_reference only after it is visible. The
    sample-time checkpoint is kept internally; no state is exported before the
    query/arrival barrier. This is a causal O(n) reference path, not O(1) online.
    """
    rows,query=_records_at_origin(origin)
    base=float(rows[0]["stop_epoch"])
    first=rows[0]
    sample_day=(float(first["stop_epoch"])-base)/DAY
    query_day=(query-base)/DAY
    # Keep the latent sample-time state internally (initialize directly at sample).
    params.validate()
    q0=float(first["capacityAh"])
    first_arrival_day=(float(first["arrival_epoch"])-base)/DAY
    state=initialize_from_first_sample(
        str(int(first["source_rpt_index"])),sample_day,sample_day,q0,
        LOSS_PRIOR_VARIANCE_AH2,OFFSET_PRIOR_VARIANCE_AH2,params)
    # Keep internal state at sample time but retain the true visibility time.
    state=replace(state,last_arrival_day=first_arrival_day)
    for r in rows[1:]:
        sday=(float(r["stop_epoch"])-base)/DAY
        state=propagate(state,sday,params)
        arrival_day=(float(r["arrival_epoch"])-base)/DAY
        state=update_at_sample(state,str(int(r["source_rpt_index"])),sday,arrival_day,
                               float(r["capacityAh"]),params)
    # Measurement-age may exceed 35 days; only each actual arrival-sample lag
    # is bounded. With no new observation, propagate state/covariance to query.
    state=propagate(state,query_day,params)
    # Export guard is at the as-of query; arrival-screening is guaranteed by adapter.
    return state


def filter_features_for_origin(origin: Mapping, params: FilterParams) -> dict:
    return export_filter_features(filter_state_for_origin(origin,params))


def training_innovations(cell: Mapping, params: FilterParams) -> list[tuple[float,float]]:
    """Return (innovation,S) from one train-role cell; labels/events are never read."""
    if cell.get("role")!="train" or "records" not in cell:
        raise ValueError("parameter likelihood accepts train-role cells only")
    records=list(cell["records"])
    if not records:
        raise ValueError("empty training records")
    records.sort(key=lambda r:(float(r["stop_epoch"]),int(r["source_rpt_index"])))
    base=float(records[0]["stop_epoch"])
    first=records[0]
    state=initialize_from_first_sample(str(int(first["source_rpt_index"])),0.0,0.0,
        float(first["capacityAh"]),LOSS_PRIOR_VARIANCE_AH2,
        OFFSET_PRIOR_VARIANCE_AH2,params)
    out=[]
    for r in records[1:]:
        day=(float(r["stop_epoch"])-base)/DAY
        state=propagate(state,day,params)
        # The innovation is evaluated before applying the measurement.
        pred=state.q_reference-state.irreversible_loss+state.reversible_offset
        e=float(r["capacityAh"])-pred
        p=state.covariance
        s=p[0][0]+p[1][1]-2*p[0][1]+params.measurement_variance
        if not math.isfinite(e) or not math.isfinite(s) or s<=0:
            raise FloatingPointError("nonfinite training innovation")
        out.append((e,s))
        state=update_at_sample(state,str(int(r["source_rpt_index"])),day,day,
                               float(r["capacityAh"]),params)
    return out


def _fit_identifiability(theta, bounds, objective):
    import numpy as np
    # Boundary gate precedes Hessian evaluation; central-difference probes stay in-domain.
    distances=np.array([min(t-l,u-t) for t,(l,u) in zip(theta,bounds)],float)
    near=bool(np.any(distances<=1e-6))
    if near: return {"near_bound":True,"hessian":None,"eigenvalues":None,"condition":None}
    steps=np.minimum(1e-3,0.25*distances)
    h=np.zeros((len(theta),len(theta)),float); f0=objective(theta)
    for i,hi in enumerate(steps):
        ei=np.zeros(len(theta));ei[i]=hi
        h[i,i]=(objective(theta+ei)-2*f0+objective(theta-ei))/(hi*hi)
        for j in range(i):
            hj=steps[j];ej=np.zeros(len(theta));ej[j]=hj
            val=(objective(theta+ei+ej)-objective(theta+ei-ej)-objective(theta-ei+ej)+objective(theta-ei-ej))/(4*hi*hj)
            h[i,j]=h[j,i]=val
    eig=np.linalg.eigvalsh(h);cond=float(np.linalg.cond(h))
    return {"near_bound":False,"hessian":h,"eigenvalues":eig,"condition":cond}

def _run_bounded_log_fit(train_cells,names,refs,lower,upper,start,innovations,maxiter,builder):
    import numpy as np
    from scipy.optimize import minimize
    if not train_cells or any(c.get("role")!="train" for c in train_cells):
        raise ValueError("fit requires nonempty train-role cells only")
    if not 1<=maxiter<=200: raise ValueError("iteration cap must be 1..200")
    refs=np.asarray(refs,float);lower=np.asarray(lower,float);upper=np.asarray(upper,float);start=np.asarray(start,float)
    if np.any(refs<=0) or np.any(lower<=0) or np.any(upper<=lower): raise ValueError("log fit requires positive bounds")
    lo=np.log(lower/refs);hi=np.log(upper/refs);theta0=np.log(start/refs)
    if np.any(theta0<=lo) or np.any(theta0>=hi): raise ValueError("start must be strictly inside bounds")
    bounds=list(zip(lo,hi))
    def unpack(theta): return builder(refs*np.exp(np.asarray(theta,float)))
    def objective(theta):
        try:
            params=unpack(theta);total=0.0
            for cell in train_cells:
                vals=innovations(cell,params)
                if not vals:return 1e100
                total+=sum(0.5*(math.log(2.0*math.pi*s)+e*e/s) for e,s in vals)/len(vals)
            val=total/len(train_cells)
            return val if math.isfinite(val) else 1e100
        except (ValueError,FloatingPointError,RuntimeError,OverflowError):return 1e100
    result=minimize(objective,theta0,method="L-BFGS-B",bounds=bounds,options={"maxiter":int(maxiter),"ftol":1e-10,"maxls":20})
    theta=np.asarray(result.x,float);loss=float(objective(theta));physical=refs*np.exp(theta)
    if not result.success or not np.all(np.isfinite(theta)) or not math.isfinite(loss) or loss>=1e99:
        return {"status":"FIT_FAILED","message":str(result.message),"iterations":int(result.nit)}
    gate=_fit_identifiability(theta,bounds,objective)
    if gate["near_bound"]:
        return {"status":"IDENTIFIABILITY_STOP","parameters":dict(zip(names,physical.tolist())),"quasi_nll":loss,"iterations":int(result.nit),"near_bound":True,"hessian_eigenvalues":None,"hessian_condition":None}
    eig=gate["eigenvalues"];cond=gate["condition"]
    if not np.all(np.isfinite(gate["hessian"])) or not np.all(np.isfinite(eig)) or eig.min()<=0 or not math.isfinite(cond) or cond>1e8:
        return {"status":"IDENTIFIABILITY_STOP","parameters":dict(zip(names,physical.tolist())),"quasi_nll":loss,"iterations":int(result.nit),"near_bound":False,"hessian_eigenvalues":eig.tolist(),"hessian_condition":cond}
    return {"status":"FIT_OK","parameters":dict(zip(names,physical.tolist())),"quasi_nll":loss,"iterations":int(result.nit),"log_coordinates":theta.tolist(),"hessian_eigenvalues":eig.tolist(),"hessian_condition":cond}

def fit_candidate_parameters(train_cells: Sequence[Mapping], *, maxiter: int=200) -> dict:
    """One train-only bounded log-coordinate innovation quasi-NLL fit proposal."""
    refs=[0.25/365.0,1e-6,1.0/7.0,1e-5,1e-6]
    lower=[1e-8,1e-12,1.0/35.0,1e-12,1e-10];upper=[0.25,0.0625,10.0,0.0625,0.0625]
    def builder(p):return FilterParams(*[float(x) for x in p])
    return _run_bounded_log_fit(train_cells,["mu_Ah_per_day","v_Ah2_per_day","lambda_per_day","Vz_Ah2","R_Ah2"],refs,lower,upper,refs,training_innovations,maxiter,builder)

def scalar_kalman_innovations(cell: Mapping, parameters: Mapping) -> list[tuple[float,float]]:
    """Ordinary one-state random-walk Kalman innovations; does not inspect labels."""
    if cell.get("role")!="train" or "records" not in cell:raise ValueError("train-role cells only")
    mu=float(parameters["mu_Ah_per_day"]);v=float(parameters["process_variance_Ah2_per_day"]);r=float(parameters["measurement_variance_Ah2"])
    if not all(math.isfinite(x) and x>0 for x in (mu,v,r)):raise ValueError("positive finite scalar parameters required")
    rows=sorted(cell["records"],key=lambda z:(float(z["stop_epoch"]),int(z["source_rpt_index"])))
    if not rows:raise ValueError("empty training records")
    base=float(rows[0]["stop_epoch"]);qref=float(rows[0]["capacityAh"]);x=0.0;var=1e-5;prev=base;out=[]
    for row in rows[1:]:
        now=float(row["stop_epoch"]);dt=(now-prev)/DAY
        if not math.isfinite(dt) or dt<=0:raise ValueError("sample times must strictly increase")
        x+=mu*dt;var+=v*dt;e=float(row["capacityAh"])-(qref-x);s=var+r
        if not math.isfinite(e) or not math.isfinite(s) or s<=0:raise FloatingPointError("invalid scalar innovation")
        out.append((e,s));k=-var/s;x+=k*e;var=(1.0-var/s)**2*var+k*k*r
        if not math.isfinite(var) or var<=0:raise FloatingPointError("invalid scalar covariance")
        prev=now
    return out

def fit_scalar_kalman_parameters(train_cells: Sequence[Mapping], *, maxiter: int=200) -> dict:
    """One train-only cell-balanced 3-parameter scalar Kalman fit proposal."""
    refs=[0.25/365.0,1e-6,1e-6];lower=[1e-8,1e-12,1e-10];upper=[0.25,0.0625,0.0625]
    names=["mu_Ah_per_day","process_variance_Ah2_per_day","measurement_variance_Ah2"]
    return _run_bounded_log_fit(train_cells,names,refs,lower,upper,refs,scalar_kalman_innovations,maxiter,lambda p:dict(zip(names,[float(x) for x in p])))

def scalar_kalman_features(origin: Mapping, parameters: Mapping) -> dict:
    """As-of scalar-Kalman features from already screened visible_records."""
    rows,query=_records_at_origin(origin);mu=float(parameters["mu_Ah_per_day"]);v=float(parameters["process_variance_Ah2_per_day"]);r=float(parameters["measurement_variance_Ah2"])
    if not all(math.isfinite(z) and z>0 for z in (mu,v,r)):raise ValueError("positive finite scalar parameters required")
    base=float(rows[0]["stop_epoch"]);qref=float(rows[0]["capacityAh"]);x=0.0;var=1e-5;prev=base
    for row in rows[1:]:
        now=float(row["stop_epoch"]);dt=(now-prev)/DAY
        if dt<=0:raise ValueError("sample times must increase")
        x+=mu*dt;var+=v*dt;e=float(row["capacityAh"])-(qref-x);k=-var/(var+r);x+=k*e;var=(1.0-var/(var+r))**2*var+k*k*r;prev=now
    age=(query-base)/DAY;stale=(query-prev)/DAY
    # Staleness is not replay delay: propagate through any no-measurement gap.
    x+=mu*stale;var+=v*stale
    return {"scalar_loss":x,"scalar_variance":var,"age_day":age,"staleness_days":stale}
