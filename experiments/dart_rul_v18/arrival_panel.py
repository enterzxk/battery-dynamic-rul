"""GO-gated 0-fit arrival-before/after diagnostic for DART V18."""
from __future__ import annotations
import csv,datetime,fcntl,json,math,os,signal,sys,time,traceback
from pathlib import Path

ROOT=Path("/home/yndx/zxk/rul")
HERE=Path(__file__).resolve().parent
OLD=ROOT/"experiments/isu_irregular_rul_seed42_v1"
sys.path.insert(0,str(HERE));sys.path.insert(0,str(OLD))
from benchmark import (ASSETS,COHORT,DATA,HERE as V18,MANIFEST,STATE,canonical,maps,owner,sha)
import recover_evaluation as recovery
SEEDS=[42,13,77]
ARMS=("raw","sparse2","delay7d")
DAY=86400.0
WEEK=7.0*DAY
MAX_CALLS=90000
SOURCE_PATHS=recovery.source_paths()+[HERE/"arrival_panel.py"]
PRIOR=HERE/"run1_receipt.json"


def _atomic_create_json(path,obj):
    path=Path(path)
    fd=os.open(str(path),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as f:
        json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=True)
        f.write("\n");f.flush();os.fsync(f.fileno())


def _development_cells():
    import json
    from data_adapter import load_reviewed_cell
    cohort=json.loads(COHORT.read_text(encoding="utf-8"))
    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    roles=cohort["roles"];files=manifest.get("files",{})
    expected={cid for cid,role in roles.items() if role in ("train","development")}
    if manifest.get("status")!="PASS" or set(files)!=expected:
        raise RuntimeError("frozen manifest/cohort role mismatch")
    ids=sorted(cid for cid,role in roles.items() if role=="development")
    cells=[]
    for cid in ids:
        p=DATA/(cid+".json")
        if not p.is_file() or sha(p)!=files[cid].get("sha256"):
            raise RuntimeError("development record missing/hash mismatch "+cid)
        cells.append(load_reviewed_cell(p,"development"))
    if len(cells)!=63 or any(c.get("role")!="development" for c in cells):
        raise RuntimeError("development-only payload contract failed")
    return cells


def _arrival_examples(cells):
    """Build every eligible delay7d report arrival +/-1s after common-arm eligibility."""
    from data_protocol import ARMS as PROTOCOL_ARMS, _arm_records, _feature_view, _history_key
    if tuple(PROTOCOL_ARMS)!=ARMS:
        raise RuntimeError("arm definition differs from frozen protocol")
    pairs=[]
    for cell in cells:
        rows=sorted(cell["records"],key=lambda r:(float(r["stop_epoch"]),int(r["source_rpt_index"])))
        if len(rows)<3:continue
        anchor=rows[1];anchor_epoch=float(anchor["stop_epoch"])
        record_lo=float(rows[0]["stop_epoch"]);record_hi=float(rows[-1]["stop_epoch"])
        arm_rows={arm:_arm_records(rows,1,arm) for arm in ARMS}
        for trigger in arm_rows["delay7d"]:
            at=float(trigger["arrival_epoch"]);before,after=at-1.0,at+1.0
            if before<max(record_lo,anchor_epoch+WEEK) or after>record_hi:
                continue
            scenarios=[]
            for side,q in (("before",before),("after",after)):
                counts={};delay_example=None
                for arm in ARMS:
                    visible=sorted(
                        (dict(r) for r in arm_rows[arm] if float(r["arrival_epoch"])<=q),
                        key=lambda r:(float(r["arrival_epoch"]),float(r["stop_epoch"]),int(r["source_rpt_index"])))
                    counts[arm]=len(visible)
                    if len(visible)<3:
                        delay_example=None;break
                    if arm!="delay7d":
                        continue
                    latest=max(float(r["arrival_epoch"]) for r in visible)
                    xq=_feature_view(cell,visible,q)
                    xa=_feature_view(cell,visible,latest)
                    latest_record=max(visible,key=lambda r:(float(r["arrival_epoch"]),float(r["stop_epoch"])))
                    age=float(latest_record["calendar_age_weeks"])+(q-float(latest_record["stop_epoch"]))/WEEK
                    event_known=any(float(r["capacityAh"])<=0.20 for r in visible)
                    delay_example={
                        "cell_id":str(cell["cell_id"]),"group_id":str(cell["group_id"]),
                        "role":"development","arm":"delay7d",
                        "query_epoch":q,"arrival_anchor_epoch":latest,
                        "last_arrival_epoch":latest,"delta_weeks":(q-latest)/WEEK,
                        "elapsed_from_warmup_weeks":(q-anchor_epoch)/WEEK,
                        "origin_age_weeks":age,"anchor_age_weeks":float(anchor["calendar_age_weeks"]),
                        "warmup_epoch":anchor_epoch,"known_event":event_known,
                        "visible_records":visible,"x_query":xq,"x_anchor":xa,
                        "history_key":_history_key(visible),
                    }
                if delay_example is None:
                    scenarios=[];break
                scenarios.append({"side":side,"example":delay_example,"common_arrived_counts":counts})
            if len(scenarios)==2:
                pairs.append({
                    "cell_id":str(cell["cell_id"]),
                    "trigger_source_rpt_index":int(trigger["source_rpt_index"]),
                    "trigger_sample_epoch":float(trigger["stop_epoch"]),
                    "arrival_epoch":at,"before_query_epoch":before,
                    "after_query_epoch":after,"scenarios":scenarios,
                })
    return pairs


def _metrics(predictor,example,on_predict):
    on_predict()
    dist=predictor.predict(example)
    unclosed_p=float(dist.cdf(0.0));unclosed_mean=float(dist.mean())
    closed=bool(example["known_event"])
    if closed:
        p_event,mean,q10,q90=1.0,0.0,0.0,0.0
    else:
        p_event=unclosed_p;mean=unclosed_mean
        q10=float(dist.quantile(.10));q90=float(dist.quantile(.90))
    if not all(math.isfinite(x) for x in (p_event,mean,q10,q90,unclosed_p,unclosed_mean)):
        raise FloatingPointError("nonfinite arrival panel summary")
    if not (0.0<=p_event<=1.0 and mean>=0 and 0<=q10<=q90):
        raise ValueError("invalid arrival panel probability or quantile")
    if closed and (p_event!=1.0 or mean!=0.0 or q10!=0.0 or q90!=0.0):
        raise AssertionError("known-event closure contract failed")
    return {
        "event_closure_applied":closed,"p_event":p_event,"mean_weeks":mean,
        "q10_weeks":q10,"q90_weeks":q90,
        "unclosed_p_event":unclosed_p,"unclosed_mean_weeks":unclosed_mean,
    }


def _load_old_reference(rec):
    import joblib,numpy as np
    from hgb_models import HGBFullWindow
    model=joblib.load(ASSETS[0]);residuals=np.load(ASSETS[1]);weights=np.load(ASSETS[2])
    rec["old_hgb_reference_loads"]+=1
    return HGBFullWindow(model,residuals,weights)


def run(go_path):
    started=time.time()
    rec={
        "status":"PREFLIGHT_FAILED","new_fits":0,"optimizer_steps":0,
        "inference_calls":0,"HGB_asset_loads":0,"neural_checkpoint_loads":0,
        "old_hgb_reference_loads":0,"development_payload_cells_read":0,
        "locked_payload_reads":0,"C4_payload_reads":0,
    }
    held=[];out=None;receipt=None;g=None
    try:
        g=json.loads(Path(go_path).read_text(encoding="utf-8"))
        receipt=Path(g["receipt_path"]);out=Path(g["output_path"])
        if g.get("status")!="APPROVED_ARRIVAL_PANEL_EVALUATION_ONLY":
            raise RuntimeError("fresh arrival-panel GO required")
        if g.get("allow_fit") is not False or g.get("new_fits")!=0 or g.get("optimizer_steps")!=0:
            raise RuntimeError("arrival panel is strictly 0-fit/0-step")
        if g.get("seeds")!=SEEDS:
            raise RuntimeError("seed set mismatch")
        if g.get("max_inference_calls",0)>MAX_CALLS or g.get("max_inference_calls",0)<1:
            raise RuntimeError("inference budget must be in [1,90000]")
        if g.get("max_runtime_seconds",0)>1800 or g.get("max_runtime_seconds",0)<1:
            raise RuntimeError("runtime budget must be in [1,1800]")
        source_sha=maps(SOURCE_PATHS)
        checkpoint_sha=maps(recovery.checkpoint_paths())
        asset_sha=maps(ASSETS)
        prior=json.loads(PRIOR.read_text(encoding="utf-8"))
        expected={
            "source_sha256":source_sha,"checkpoint_sha256":checkpoint_sha,
            "asset_sha256":asset_sha,"cohort_sha256":sha(COHORT),
            "manifest_sha256":sha(MANIFEST),"protocol_sha256":sha(HERE/"protocol.json"),
            "prior_receipt_sha256":sha(PRIOR),
        }
        for k,v in expected.items():
            if g.get(k)!=v:raise RuntimeError("GO hash mismatch: "+k)
        code_manifest=canonical({
            "source_sha256":source_sha,"checkpoint_sha256":checkpoint_sha,
            "asset_sha256":asset_sha,"cohort_sha256":expected["cohort_sha256"],
            "manifest_sha256":expected["manifest_sha256"],
            "protocol_sha256":expected["protocol_sha256"],
            "prior_receipt_sha256":expected["prior_receipt_sha256"],
        })
        if g.get("code_manifest_sha256")!=code_manifest:
            raise RuntimeError("GO canonical manifest mismatch")
        if prior.get("CPU_fits_completed")!=21 or prior.get("neural_fits_completed")!=12 or prior.get("optimizer_steps")!=3600:
            raise RuntimeError("prior V18 fit receipt is incomplete")
        issued=datetime.datetime.fromisoformat(g["issued_utc"])
        age=(datetime.datetime.now(datetime.timezone.utc)-issued).total_seconds()
        if not -60<=age<=86400:raise RuntimeError("GO is stale or future dated")
        if out.parent!=HERE/"runs" or not out.name.startswith("arrival_panel_"):
            raise RuntimeError("output must be a fresh runs/arrival_panel_* directory")
        if receipt.parent!=HERE or out.exists() or receipt.exists():
            raise FileExistsError("create-only output or receipt already exists")
        if g.get("owner_thread_id")!="01a1598a-bcaa-7443-9579-c48ee2303172":
            raise RuntimeError("owner thread mismatch")
        owner(g["owner_thread_id"])
        for p in (ROOT/"automation/state/online_survival_cpu.lock",
                  ROOT/"automation/locks/isu_irregular_rul_cpu.lock"):
            if not p.is_file():raise FileNotFoundError("required CPU lock missing: "+str(p))
            f=p.open("a+");fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);held.append(f)
        owner(g["owner_thread_id"])
        if json.loads(Path(go_path).read_text(encoding="utf-8"))!=g:
            raise RuntimeError("GO changed during preflight")
        claim=ROOT/"automation/locks/dart_v18_claims"/g["request_id"]
        claim.parent.mkdir(parents=True,exist_ok=True)
        with claim.open("x",encoding="ascii") as f:f.write(sha(go_path))
        cells=_development_cells()
        rec["development_payload_cells_read"]=len(cells)
        pairs=_arrival_examples(cells)
        n_scenarios=len(pairs)*2
        # Six V18 models plus the old HGB reference, each for all 3 seeds.
        expected_calls=n_scenarios*(7*len(SEEDS))
        rec["arrival_report_pairs"]=len(pairs)
        rec["arm_query_scenarios"]=n_scenarios
        rec["expected_inference_calls"]=expected_calls
        if expected_calls>g["max_inference_calls"]:
            raise RuntimeError("complete panel exceeds fresh GO inference budget; no checkpoint loaded")
        signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError("arrival panel runtime cap")))
        signal.alarm(g["max_runtime_seconds"])
        out.mkdir(exist_ok=False)
        rec.update(
            status="RUNNING",request_id=g["request_id"],GO_sha256=sha(go_path),
            source_sha256=source_sha,checkpoint_sha256=checkpoint_sha,
            asset_sha256=asset_sha,panel_scope="delay7d report arrival triggers; delay7d predictions only; raw/sparse2 are common-eligibility guards",
            seeds=SEEDS,expected_inference_calls=expected_calls,
        )
        models_by_seed={}
        for seed in SEEDS:
            owner(g["owner_thread_id"])
            models_by_seed[seed]=recovery.load_models(seed,rec)
        old_reference=_load_old_reference(rec)
        model_names=("hgb_fullwindow","hgb_hurdle","risk_query","joint_query","dart_joint","dart_split")
        def count():
            rec["inference_calls"]+=1
            if rec["inference_calls"]>g["max_inference_calls"]:
                raise RuntimeError("arrival panel inference cap exceeded")
        csv_path=out/"arrival_panel.csv"
        fields=[
            "cell_id","trigger_source_rpt_index","trigger_sample_epoch","arrival_epoch",
            "side","query_epoch","arm","history_key","known_event","delta_weeks",
            "raw_arrived_count","sparse2_arrived_count","delay7d_arrived_count",
            "seed","model","event_closure_applied","p_event","mean_weeks","q10_weeks",
            "q90_weeks","unclosed_p_event","unclosed_mean_weeks",
        ]
        with csv_path.open("x",encoding="utf-8",newline="") as f:
            # File was reserved with O_EXCL above; reopen without replacing it.
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
            for pair in pairs:
                for sc in pair["scenarios"]:
                    ex=sc["example"]
                    common={
                        "cell_id":pair["cell_id"],
                        "trigger_source_rpt_index":pair["trigger_source_rpt_index"],
                        "trigger_sample_epoch":pair["trigger_sample_epoch"],
                        "arrival_epoch":pair["arrival_epoch"],"side":sc["side"],
                        "query_epoch":ex["query_epoch"],"arm":ex["arm"],
                        "history_key":ex["history_key"],"known_event":ex["known_event"],
                        "delta_weeks":ex["delta_weeks"],
                        "raw_arrived_count":sc["common_arrived_counts"]["raw"],
                        "sparse2_arrived_count":sc["common_arrived_counts"]["sparse2"],
                        "delay7d_arrived_count":sc["common_arrived_counts"]["delay7d"],
                    }
                    for seed in SEEDS:
                        models=models_by_seed[seed]
                        for name in model_names:
                            stats=_metrics(models[name],ex,count)
                            writer.writerow(dict(common,seed=seed,model=name,**stats))
                        stats=_metrics(old_reference,ex,count)
                        writer.writerow(dict(common,seed=seed,model="existing_hgb_reference",**stats))
                if rec["inference_calls"]%100==0:
                    f.flush();os.fsync(f.fileno())
            f.flush();os.fsync(f.fileno())
        rec.update(
            status="SUCCESS",written_prediction_rows=n_scenarios*7*len(SEEDS),
            report_pairs=len(pairs),arm_query_scenarios=n_scenarios,
            source_role_C4_reads=0,development_payload_cells_read=len(cells),
            elapsed_seconds=time.time()-started,
        )
    except Exception as ex:
        rec.update(status="FAILED",error=repr(ex),traceback=traceback.format_exc())
    finally:
        signal.alarm(0);rec["elapsed_seconds"]=time.time()-started
        if receipt is not None and not receipt.exists():
            receipt.parent.mkdir(exist_ok=True)
            try:_atomic_create_json(receipt,rec)
            except FileExistsError:pass
        for f in reversed(held):
            fcntl.flock(f,fcntl.LOCK_UN);f.close()
    return rec


if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--go",required=True)
    args=ap.parse_args()
    result=run(args.go)
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=True))
    sys.exit(0 if result["status"]=="SUCCESS" else 2)
