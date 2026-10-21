"""Leakage-aware source-RPT target construction and frozen train-only schedule."""
from __future__ import annotations
import hashlib, json
import numpy as np
from collections import defaultdict

WEEK=604800.0


def build_train_schedule(train_cells,horizon_weeks=128.0,n_quantiles=16):
    """Deterministic repeated quantile schedule fitted only from train RPT gaps."""
    gaps=[]
    for cell in train_cells:
        rows=sorted(cell["records"],key=lambda r:(float(r["stop_epoch"]),int(r["source_rpt_index"])))
        gaps.extend((float(b["stop_epoch"])-float(a["stop_epoch"]))/WEEK
                    for a,b in zip(rows,rows[1:])
                    if float(b["stop_epoch"])>float(a["stop_epoch"]))
    if not gaps:raise ValueError("no train-only RPT intervals")
    q=np.linspace(.05,.95,int(n_quantiles))
    atoms=np.quantile(np.asarray(gaps,float),q)
    atoms=np.maximum(atoms,1e-6)
    out=[];total=0.;i=0
    while total<float(horizon_weeks):
        dt=float(atoms[i%len(atoms)])
        if total+dt>horizon_weeks:dt=float(horizon_weeks)-total
        out.append(dt);total+=dt;i+=1
        if len(out)>10000:raise ValueError("schedule exceeded guard")
    payload={"source":"C1/C2 train source-RPT gaps only","quantiles":q.tolist(),
             "atoms_weeks":atoms.tolist(),"horizon_weeks":float(horizon_weeks),
             "gaps_weeks":out}
    payload["sha256"]=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return payload


def build_targets(examples,cells):
    """Pair arrived-history queries with irregular source-path labels (train only).

    The first target begins after the last visible source STOP, not arrival time;
    it therefore retains the unreported source path through query. Actual target
    intervals are used only in the likelihood and validation horizon, never in
    the causal feature vector.
    """
    cellmap={str(c["cell_id"]):c for c in cells};out=[]
    for e in examples:
        cell=cellmap.get(str(e["cell_id"]))
        if cell is None:raise ValueError("example cell missing from supplied split")
        rows=sorted(cell["records"],key=lambda r:(float(r["stop_epoch"]),int(r["source_rpt_index"])))
        visible=e["visible_records"]
        if not visible:continue
        last_source_stop=max(float(r["stop_epoch"]) for r in visible)
        q=float(e["query_epoch"])
        if last_source_stop>q+1e-5:raise ValueError("visible source stop after query")
        start=next(r for r in reversed(rows) if abs(float(r["stop_epoch"])-last_source_stop)<1e-4)
        following=[r for r in rows if float(r["stop_epoch"])>last_source_stop+1e-5]
        prev=last_source_stop;gaps=[];caps=[];source_stops=[];hidden=[]
        for r in following:
            t=float(r["stop_epoch"])
            gaps.append((t-prev)/WEEK);caps.append(float(r["capacityAh"]));source_stops.append(t)
            hidden.append(t<=q+1e-5);prev=t
        # The next-RPT capacity target is scored at its known evaluation horizon.
        after=[r for r in rows if float(r["stop_epoch"])>q+1e-5]
        next_row=after[0] if after else None
        # Horizon labels require source observation support through q+h.
        event=cell.get("source_observed_event_stop_epoch")
        support={}
        for h in (4.0,12.0):
            observed_through=bool(rows and float(rows[-1]["stop_epoch"])>=q+h*WEEK)
            support[h]=observed_through
        out.append({
            **e,
            "latest_source_stop_epoch":last_source_stop,
            "latest_source_capacity_ah":float(start["capacityAh"]),
            "hidden_delta_weeks":max(0.,(q-last_source_stop)/WEEK),
            "trajectory_gaps_weeks":gaps,
            "trajectory_capacity_ah":caps,
            "trajectory_source_stops":source_stops,
            "trajectory_hidden_mask":hidden,
            "query_path_steps":sum(hidden),
            "next_capacity_ah":None if next_row is None else float(next_row["capacityAh"]),
            "next_elapsed_weeks":None if next_row is None else (float(next_row["stop_epoch"])-last_source_stop)/WEEK,
            "next_query_elapsed_weeks":None if next_row is None else (float(next_row["stop_epoch"])-q)/WEEK,
            "support_4w":support[4.0],"support_12w":support[12.0],
            "label_event_4w":None if not support[4.0] else bool(event is not None and event<=q+4*WEEK),
            "label_event_12w":None if not support[12.0] else bool(event is not None and event<=q+12*WEEK),
        })
    return out


def fit_feature_scaler(rows,feature_key="x_query"):
    """Cell-balanced, train-only mean/scale for the 74-D causal feature input."""
    xs=np.stack([np.asarray(r[feature_key],float) for r in rows])
    counts=defaultdict(int)
    for r in rows:counts[str(r["cell_id"])]+=1
    w=np.asarray([1.0/counts[str(r["cell_id"])] for r in rows],float);w/=w.sum()
    mean=np.sum(xs*w[:,None],axis=0)
    var=np.sum((xs-mean)**2*w[:,None],axis=0)
    return mean,np.sqrt(np.maximum(var,1e-12))


def collate_irregular(rows,indices,feature_key="x_query"):
    """Pad label-side irregular paths; mask padding and preserve variable Δt."""
    batch=[rows[int(i)] for i in indices]
    n=max((len(x["trajectory_gaps_weeks"]) for x in batch),default=0)
    b=len(batch);g=np.zeros((b,n),float);q=np.zeros((b,n),float);m=np.zeros((b,n),bool)
    for i,x in enumerate(batch):
        k=len(x["trajectory_gaps_weeks"])
        if k:
            g[i,:k]=x["trajectory_gaps_weeks"];q[i,:k]=x["trajectory_capacity_ah"];m[i,:k]=True
    return (np.stack([np.asarray(x[feature_key],float) for x in batch]),
            np.asarray([x["latest_source_capacity_ah"] for x in batch],float),g,q,m,batch)
