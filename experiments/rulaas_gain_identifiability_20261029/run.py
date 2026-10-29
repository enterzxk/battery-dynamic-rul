#!/usr/bin/env python3
"""Train-only acquisition benefit labels using one fixed held-cell positive-RUL proxy."""
import os
os.environ.setdefault("OMP_NUM_THREADS","4");os.environ.setdefault("MKL_NUM_THREADS","4")
import pathlib,sys,json,csv,collections,hashlib,datetime,fcntl,time,math,traceback,argparse,copy
import numpy as np
ROOT=pathlib.Path("/home/yndx/zxk/rul");HERE=ROOT/"experiments/rulaas_gain_identifiability_20261029"
FORMAL=ROOT/"experiments/multisource_factorial_20261021/run2_clocksafe";SIGNALS=ROOT/"reports/multisource_20261021_signals"
sys.path[:0]=[str(ROOT/"experiments/rulaas_value_gate_20261029"),str(ROOT/"experiments/multisource_factorial_20261021"),str(SIGNALS),str(ROOT/"experiments/isu_irregular_rul_seed42_v1"),str(ROOT/"experiments/dart_rul_v18")]
from value_gate import vector,sha,readj,writej,csvout,stamp,MemoCycle
from data_adapter import load_reviewed_cell
import cycle_asof_features as C
WEEK=604800.;DAY=86400.;OWNER="01a17810-6ae6-7cf2-9729-5bfcaa8df5f4";CANDIDATES=(3,7,11,15,19,23,27,31)
def progress(out,**obj):
 p=out/"progress.tmp";p.write_text(json.dumps(dict(utc=stamp(),**obj)));os.replace(p,out/"progress.json")
def arrive(rows,q):return [z for z in rows if float(z["arrival_epoch"])<=q]
def report(row,lag=7.):return dict(row,arrival_epoch=float(row["stop_epoch"])+lag*DAY)
def mean_cell(rows,key):
 by=collections.defaultdict(list)
 for r in rows:by[r["cell_id"]].append(float(r[key]))
 return float(np.mean([np.mean(v) for v in by.values()])) if by else None
def correlation(x,y):
 from scipy.stats import spearmanr
 x=np.asarray(x);y=np.asarray(y)
 if len(x)<3 or np.ptp(x)==0 or np.ptp(y)==0:return None
 v=float(spearmanr(x,y).statistic if hasattr(spearmanr(x,y),"statistic") else spearmanr(x,y)[0])
 return v if math.isfinite(v) else None
def main(go_path):
 go=readj(go_path);out=ROOT/go["output"];locks=[];start=time.time();counter=0
 rec={"request_id":go["request_id"],"status":"STARTED","started_utc":stamp(),"new_fits":0,"optimizer_steps":0,"C3_payload_reads":0,"C4_payload_reads":0,"model_rows":0,"kernel":"exp(mu) from hgb_F3_oof0 positive-RUL head only; no event head/global residual calibration"}
 try:
  for p in [ROOT/"automation/state/coordinator.lock",ROOT/"automation/locks/isu_irregular_rul_cpu.lock"]:
   lock=p.open("a+");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(lock)
  coord=readj(ROOT/"automation/state/coordinator.json")
  if coord.get("owner")!=OWNER or coord.get("thread_id")!=OWNER or coord.get("state")!="ACTIVE":raise ValueError("owner")
  hb=datetime.datetime.fromisoformat(coord["heartbeat_utc"].replace("Z","+00:00"))
  if (datetime.datetime.now(datetime.timezone.utc)-hb).total_seconds()>1800:raise ValueError("heartbeat")
  if go.get("status")!="APPROVED" or go.get("owner")!=OWNER or go.get("allow_fits") is not False or go.get("allow_C3") is not False or go.get("allow_C4") is not False or go.get("allow_inference") is not True:raise ValueError("GO")
  if go["max_model_rows"]!=12000 or go["max_source_cells"]!=48 or go["candidate_source_indices"]!=list(CANDIDATES):raise ValueError("protocol drift")
  for rel,h in go["input_sha256"].items():
   if sha(ROOT/rel)!=h:raise ValueError("input drift "+rel)
  if out.parent!=HERE or out.exists():raise ValueError("create-only output")
  writej(HERE/(go["request_id"]+".claim.json"),{"GO_sha256":sha(go_path),"utc":stamp()});out.mkdir()
  import joblib
  model=joblib.load(FORMAL/"hgb_F3_oof0.joblib")
  def predict(X):
   nonlocal counter
   X=np.asarray(X,float)
   if counter+len(X)>12000:raise ValueError("model budget")
   if X.ndim!=2 or X.shape[1]!=710 or np.isinf(X).any():raise ValueError("feature matrix")
   counter+=len(X);mu=model.predict(X)
   if not np.isfinite(mu).all():raise ValueError("nonfinite mu")
   v=np.exp(mu)
   if not np.isfinite(v).all():raise ValueError("overflow; no clipping")
   return mu,v
  with (FORMAL/"train_targets.jsonl").open() as f:targets=[json.loads(z) for z in f]
  positive=[i for i,z in enumerate(targets) if z["target_rul_weeks"] is not None and float(z["target_rul_weeks"])>0]
  ids=sorted({targets[i]["cell_id"] for i in positive});np.random.RandomState(42).shuffle(ids)
  held=set(ids[::2]);fit=set(ids[1::2])
  if len(held)!=60 or len(fit)!=60 or held&fit or any(not x.endswith(("C1","C2")) for x in ids):raise ValueError("original physical-cell fold")
  # Reuse the already-passed immutable identity check from RUN01; model/data hashes unchanged.
  prior=readj(ROOT/go["reused_identity_split"])
  old_go=readj(ROOT/go["reused_identity_GO"])
  key="experiments/multisource_factorial_20261021/run2_clocksafe/hgb_F3_oof0.joblib"
  if old_go["input_sha256"][key]!=go["input_sha256"][key] or set(prior["base_head_fit_cells"])!=fit or set(prior["base_head_unseen_cells"])!=held:raise ValueError("reused identity mismatch")
  identity_error=float(prior["residual_identity_max_error"])
  if identity_error>1e-8:raise ValueError("prior identity did not pass")
  verification_rows=0
  rec["reused_identity_original_model_rows"]=2298
  rec["reused_identity_split"]=go["reused_identity_split"]
  rng=np.random.RandomState(42)
  selected_fit=sorted(str(x) for x in rng.choice(sorted(fit),24,replace=False));selected_held=sorted(str(x) for x in rng.choice(sorted(held),24,replace=False))
  split={"seed":42,"base_head_fit_cells":sorted(fit),"base_head_unseen_cells":sorted(held),"selected_kernel_fit":selected_fit,"selected_kernel_held":selected_held,"selection_uses_C3":False,"residual_identity_max_error":identity_error,"residuals_used_for_calibration":False}
  writej(out/"cell_split.json",split)
  man=readj(ROOT/"reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json")
  roles=readj(ROOT/"reports/isu_ilcc_capacity_probe_20261020_root/cohort.json")["roles"]
  ri={x["cell_id"]:x for x in readj(SIGNALS/"all188_rpt_features_v1/manifest.json")["inventory"]}
  ci={x["cell_id"]:x for x in readj(SIGNALS/"cycling_all188_feature_manifest.json")["inventory"]}
  cases=[];points=[];excluded=[];features=[];sources=[];mutation=False
  for role,selected in [("kernel_fit",selected_fit),("kernel_held",selected_held)]:
   for cid in selected:
    if roles[cid]!="train" or not cid.endswith(("C1","C2")):raise ValueError("train-only data role")
    info=man["files"][cid];paths=[("DataV2",info),("RPT",ri[cid]),("Cycling",ci[cid])]
    for kind,it in paths:
     p=ROOT/it["path"]
     if it.get("role")!="train" or "C3" in p.name or "C4" in p.name or sha(p)!=it["sha256"]:raise ValueError("source/role "+cid)
     sources.append(dict(cell_id=cid,kind=kind,path=it["path"],sha256=it["sha256"]))
    cell=load_reviewed_cell(ROOT/info["path"],"train");rows=sorted(cell["records"],key=lambda z:float(z["stop_epoch"]))
    rpt=readj(ROOT/ri[cid]["path"]);cycle=MemoCycle(C.build_cycle_index(ROOT/ci[cid]["path"]))
    if cell["cell_id"]!=cid or cycle.cell_id!=cid or cycle.role!="train" or rpt["role"]!="train":raise ValueError("derived identity")
    cache={cid:{int(z["source_rpt_index"]):z for z in rpt["records"]}}
    event=next((float(z["stop_epoch"]) for z in rows if float(z["capacityAh"])<=.20),None)
    matrix=[];byhash={};drafts=[]
    def add(x):
     raw=np.asarray(x,np.float32).tobytes()
     if raw not in byhash:byhash[raw]=len(matrix);matrix.append(np.asarray(x,np.float32))
     return byhash[raw]
    for pos,row in enumerate(rows):
     idx=int(row["source_rpt_index"])
     if idx not in CANDIDATES or pos<3:continue
     t=datetime.datetime.fromisoformat(row["start"]).timestamp()
     background=[report(z) for j,z in enumerate(rows[:pos]) if j<3 or (j-3)%2==0]
     vis=arrive(background,t);reason=None
     if event is None:reason="no_exact_reference_RUL_label"
     elif len(vis)<3:reason="fewer_than_three_arrived_reports"
     elif any(float(z["capacityAh"])<=.20 for z in vis):reason="already_confirmed_event"
     if reason:
      excluded.append(dict(cell_id=cid,population=role,source_rpt_index=idx,request_epoch=t,reason=reason));continue
     x=vector(cell,vis,t,cache,cycle)
     if not mutation:
      mutated=copy.deepcopy(cache);fr=mutated[cid][idx]
      if isinstance(fr.get("values"),list):fr["values"]=[-99999.]*len(fr["values"])
      elif isinstance(fr.get("values"),dict):fr["values"]={k:-99999. for k in fr["values"]}
      if not np.allclose(x,vector(cell,vis,t,mutated,cycle),rtol=0,atol=0,equal_nan=True):raise ValueError("unobserved candidate affects request features")
      mutation=True;del mutated
     current_ix=add(x);slots=[]
     for k in range(1,9):
      q=t+k*.5*WEEK
      if q>=event:
       slots.append({"query_epoch":q,"alive":False,"true_RUL":0.,"none_ix":None,"now_ix":None,"delay_ix":None});continue
      if q>float(rows[-1]["stop_epoch"]):raise ValueError("pre-event followup unsupported")
      prior=arrive(background,q);zero_ix=add(vector(cell,prior,q,cache,cycle))
      with_ix=[]
      for lag in [0.,7.]:
       v=list(prior)
       if float(row["stop_epoch"])+lag*DAY<=q:v.append(report(row,lag))
       v.sort(key=lambda z:(float(z["stop_epoch"]),int(z["source_rpt_index"])))
       with_ix.append(add(vector(cell,v,q,cache,cycle)))
      slots.append({"query_epoch":q,"alive":True,"true_RUL":(event-q)/WEEK,"none_ix":zero_ix,"now_ix":with_ix[0],"delay_ix":with_ix[1]})
     drafts.append({"cell_id":cid,"population":role,"source_rpt_index":idx,"valid_ordinal":pos,"request_epoch":t,"source_event_epoch":event,"future_candidate_stop_epoch":float(row["stop_epoch"]),"input_staleness_weeks":(t-float(vis[-1]["stop_epoch"]))/WEEK,"input_arrived_RPT_count":len(vis),"input_pending_prior_reports":sum(float(z["arrival_epoch"])>t for z in background),"input_cheap_cycle_count":cycle.features_at(t)["cycle_source_asof_count"],"current_ix":current_ix,"current_X":x,"slots":slots})
    if matrix:
     mu,pred=predict(matrix)
     for draft in drafts:
      case_id=len(cases);gain_now=0.;gain_delay=0.;n_alive=0
      for k,s in enumerate(draft["slots"],1):
       if s["alive"]:
        y=s["true_RUL"];a=float(pred[s["none_ix"]]);b=float(pred[s["now_ix"]]);c=float(pred[s["delay_ix"]])
        g0=abs(a-y)-abs(b-y);g7=abs(a-y)-abs(c-y);n_alive+=1
       else:y=0.;a=b=c=None;g0=g7=0.
       gain_now+=g0/8.;gain_delay+=g7/8.
       points.append({"case_id":case_id,"cell_id":cid,"population":role,"source_rpt_index":draft["source_rpt_index"],"slot":k,"query_epoch":s["query_epoch"],"pre_reference_event":s["alive"],"true_RUL":y,"point_no_candidate":a,"point_stop_delivery":b,"point_7day_delivery":c,"gain_stop_delivery":g0,"gain_7day_delivery":g7})
      point=float(pred[draft["current_ix"]]);features.append(np.r_[draft["current_X"],point])
      cases.append({k:v for k,v in draft.items() if k not in ["slots","current_X","current_ix"]}|{"case_id":case_id,"input_point_proxy_RUL":point,"label_gain_stop_delivery_weeks":float(gain_now),"label_gain_7day_delivery_weeks":float(gain_delay),"label_delay_penalty_weeks":float(gain_now-gain_delay),"label_pre_event_slots":n_alive})
    progress(out,status="BUILDING_LABELS",source_cells_complete=len(sources)//3,cases_complete=len(cases),model_rows=counter)
    del matrix,cycle,rpt,cache
  if not cases or not mutation:raise ValueError("empty candidate label set")
  summaries=[]
  for role in ["kernel_fit","kernel_held"]:
   rr=[z for z in cases if z["population"]==role];g0=[z["label_gain_stop_delivery_weeks"] for z in rr];g7=[z["label_gain_7day_delivery_weeks"] for z in rr]
   summaries.append({"population":role,"n_cases":len(rr),"n_cells":len({z["cell_id"] for z in rr}),"gain_stop_delivery_cell_mean_weeks":mean_cell(rr,"label_gain_stop_delivery_weeks"),"gain_7day_delivery_cell_mean_weeks":mean_cell(rr,"label_gain_7day_delivery_weeks"),"positive_delayed_gain_fraction":float(np.mean(np.asarray(g7)>1e-9)),"negative_delayed_gain_fraction":float(np.mean(np.asarray(g7)<-1e-9)),"zero_delayed_gain_fraction":float(np.mean(np.abs(g7)<=1e-9)),"delay_reduces_gain_fraction":float(np.mean(np.asarray(g0)>np.asarray(g7)+1e-9)),"instant_vs_delayed_rank_correlation":correlation(g0,g7),"age_vs_delayed_gain_rank_correlation":correlation([z["input_staleness_weeks"] for z in rr],g7),"point_vs_delayed_gain_rank_correlation":correlation([z["input_point_proxy_RUL"] for z in rr],g7),"current_staleness_above_original_train_max_fraction":float(np.mean([z["input_staleness_weeks"]>3.426952600479126 for z in rr]))})
  csvout(out/"cases.csv",cases);csvout(out/"counterfactual_points.csv",points);csvout(out/"summary.csv",summaries);csvout(out/"excluded_cases.csv",excluded)
  with (out/"request_features.npz").open("xb") as f:np.savez_compressed(f,X_request=np.asarray(features,np.float32))
  names=readj(FORMAL/"feature_schema.json")["feature_names"]["F3"]+["positive_head_point_proxy_RUL_weeks"]
  writej(out/"feature_schema.json",{"features":names,"dimensions":711,"label_columns":["label_gain_stop_delivery_weeks","label_gain_7day_delivery_weeks"],"future_metadata_not_inputs":["future_candidate_stop_epoch","source_event_epoch"],"standardization_fitted":False,"new_fits":0})
  rec.update(status="SUCCESS",finished_utc=stamp(),elapsed_seconds=time.time()-start,model_rows=counter,artifact_identity_model_rows=verification_rows,label_construction_model_rows=counter-verification_rows,source_cells=len(selected_fit)+len(selected_held),cases=len(cases),counterfactual_query_slots=len(points),excluded_cases=len(excluded),OOF_residual_identity_max_error=identity_error,unobserved_candidate_feature_mutation="PASS",source_files=sources,input_sha256=go["input_sha256"],GO_sha256=sha(go_path))
  writej(out/"receipt.json",rec)
  writej(out/"ROOT_DECISION.json",{"status":"PROXY_GAIN_LABELS_BUILT_NOT_SERVICE_SUCCESS","new_method_validated":False,"paper_ready":False,"no_RUL_head_refit":True,"limits":["Only one conditional positive-RUL proxy, not full service distribution","Kernel-fit population has in-sample optimism; held population never fitted by this head","Post-failure primary-time utility defined zero; not a complete failure-detection objective","Passive observation/information-withholding replay; no verified health-trajectory intervention","48 training-source cells, fixed source-index opportunities, not independent final confirmation"],"next_action":"Independently recompute proxy gains and split provenance. If heterogeneous nonzero held-cell gains exist, freeze a small value-prediction test against age and point-scale controls using only kernel-fit cases for fitting. Full-kernel and resource validation still required."})
  progress(out,status="SUCCESS",cases=len(cases),model_rows=counter)
  print(json.dumps({"receipt":{k:v for k,v in rec.items() if k not in ["source_files","input_sha256"]},"summary":summaries},ensure_ascii=False))
 except BaseException as ex:
  rec.update(status="FAILED",model_rows=counter,error=repr(ex),traceback=traceback.format_exc(),finished_utc=stamp(),elapsed_seconds=time.time()-start)
  if out.is_dir() and not (out/"failure_receipt.json").exists():writej(out/"failure_receipt.json",rec)
  print(json.dumps(rec));raise
 finally:
  for lock in reversed(locks):fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
if __name__=="__main__":
 ap=argparse.ArgumentParser();ap.add_argument("--go",required=True);main(pathlib.Path(ap.parse_args().go))
