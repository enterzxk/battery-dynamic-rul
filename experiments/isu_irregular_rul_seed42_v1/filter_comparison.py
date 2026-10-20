"""GO-gated filter-head comparison. No raw-label access in filter feature construction."""
from __future__ import annotations
import argparse,csv,datetime,fcntl,hashlib,json,math,os,signal,time,traceback
from collections import Counter
from pathlib import Path
import numpy as np

ROOT=Path("/home/yndx/zxk/rul")
HERE=Path(__file__).resolve().parent
FILTPROTO=HERE/"filter_fit_protocol.json"
BASEPROTO=HERE/"protocol_candidate.json"
FILTERSRC=HERE/"filter_representation.py"
CANDIDATE=HERE/"candidate_filter.py"

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def source_map():
 names=("filter_comparison.py","filter_representation.py","candidate_filter.py","baselines.py","data_adapter.py","train_eval.py","filter_fit_protocol.json","protocol_candidate.json")
 return {n:sha(HERE/n) for n in names}
def canonical_hash(d):return hashlib.sha256(json.dumps(d,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def atomic_json(p,d):
 p=Path(p);tmp=p.with_suffix(p.suffix+".tmp");tmp.write_text(json.dumps(d,indent=2,allow_nan=True),encoding="utf-8");os.replace(tmp,p)
def fresh_root(p):
 p=Path(p)
 if p.exists():raise FileExistsError("refusing to overwrite: "+str(p))
 return p
def durable_receipt(path,request_id,obj):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);payload=json.dumps(obj,indent=2,allow_nan=True).encode("utf-8")
 candidates=[p,p.with_name(p.stem+"_"+str(request_id or "no_request")+"_"+str(time.time_ns())+".failure.json")]
 for target in candidates:
  try:
   fd=os.open(str(target),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,payload);os.fsync(fd);os.close(fd);return str(target)
  except FileExistsError:continue
 raise FileExistsError("could not create a non-overwriting failure receipt")
def acquire(path,tag):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);f=path.open("a+")
 try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:
  f.close();raise RuntimeError(tag+" lock is already held")
 return f
def one_shot_claim(path,go,owner):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 fd=os.open(str(path),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 payload={"request_id":go["request_id"],"owner_thread_id":owner,"filter_protocol_sha256":sha(FILTPROTO)}
 os.write(fd,json.dumps(payload,sort_keys=True).encode());os.fsync(fd);os.close(fd)
def check_owner(cp,owner):
 from train_eval import validate_owner
 cp=Path(cp)
 if cp!=ROOT/"automation/state/coordinator.json":raise RuntimeError("unexpected coordinator file")
 return validate_owner(cp,owner)
def check_go(a):
 from train_eval import sha as t_sha
 go=json.loads(Path(a.go_json).read_text(encoding="utf-8"))
 if go.get("status")!="APPROVED" or go.get("allow_fit") is not True:raise RuntimeError("exact fit GO is absent")
 if not go.get("request_id") or go.get("owner_thread_id")!=a.owner_thread_id:raise RuntimeError("GO request/owner mismatch")
 issued=datetime.datetime.fromisoformat(str(go.get("issued_utc","")).replace("Z","+00:00"))
 if issued.tzinfo is None:raise RuntimeError("GO issued_utc needs timezone")
 now=datetime.datetime.now(datetime.timezone.utc)
 if (now-issued).total_seconds()>86400 or (issued-now).total_seconds()>60:raise RuntimeError("GO expired or future-dated")
 cap=int(go.get("max_runtime_seconds",0))
 if not 1<=cap<=21600:raise RuntimeError("GO runtime cap missing/outside 1..21600s")
 if go.get("filter_fit_protocol_sha256")!=t_sha(FILTPROTO):raise RuntimeError("filter fit protocol hash mismatch")
 if go.get("baseline_protocol_sha256")!=t_sha(BASEPROTO):raise RuntimeError("baseline protocol hash mismatch")
 sm=source_map()
 if go.get("source_sha256")!=sm or go.get("code_manifest_sha256")!=canonical_hash(sm):raise RuntimeError("source/code manifest hash mismatch")
 for key,path in (("cohort_sha256",a.cohort),("data_manifest_sha256",a.data_manifest),("baseline_predictions_sha256",a.baseline_predictions)):
  if go.get(key)!=sha(path):raise RuntimeError(key+" mismatch")
 budget={"candidate_parameter_fits":3,"scalar_parameter_fits":3,"hgb_head_fits":6,"max_total_fits":12}
 if go.get("fit_budget")!=budget or go.get("seed")!=42 or go.get("filter_maxiter")!=200:raise RuntimeError("fit budget/seed/iteration cap mismatch")
 if int(go.get("max_inference_calls",0))<=0:raise RuntimeError("GO inference-call cap missing")
 if go.get("output_path")!=str(Path(a.output)) or go.get("receipt_path")!=str(Path(a.receipt)):raise RuntimeError("GO output/receipt path binding mismatch")
 check_owner(a.coordinator_json,a.owner_thread_id)
 if Path(a.old_cpu_lock)!=ROOT/"automation/state/online_survival_cpu.lock":raise RuntimeError("wrong shared/old CPU lock path")
 if Path(a.isu_cpu_lock)!=ROOT/"automation/locks/isu_irregular_rul_cpu.lock":raise RuntimeError("wrong ISU CPU lock path")
 return go,cap,sm

def load_baseline_predictions(path):
 p=Path(path)
 with p.open("r",newline="",encoding="utf-8-sig") as f:
  rows=list(csv.DictReader(f))
 if not rows:raise ValueError("baseline prediction CSV empty")
 need={"cell_id","arm","origin_stop_epoch","target_rul_weeks","model"}
 if not need.issubset(rows[0]):raise ValueError("baseline prediction schema mismatch")
 return rows

def param_object(name,params):
 from candidate_filter import FilterParams
 if name=="candidate":
  return FilterParams(loss_drift_per_day=float(params["mu_Ah_per_day"]),
   loss_variance_per_day=float(params["v_Ah2_per_day"]),ou_kappa_per_day=float(params["lambda_per_day"]),
   ou_stationary_variance=float(params["Vz_Ah2"]),measurement_variance=float(params["R_Ah2"]))
 return params

def augment(x,kind,params):
 from baselines import features
 raw=features(x)
 nominal=float(x["nominal_capacity_ah"])
 if kind=="candidate":
  from filter_representation import filter_features_for_origin
  z=filter_features_for_origin(x,params)
  extra=[z["long_loss"]/nominal,z["short_reversible_offset"]/nominal,
   z["loss_variance"]/(nominal*nominal),z["offset_variance"]/(nominal*nominal),
   z["state_covariance"]/(nominal*nominal),z["last_standardized_innovation"],
   z["last_innovation_sd"]/nominal,float(z["update_was_projected"])]
 elif kind=="scalar":
  from filter_representation import scalar_kalman_features
  z=scalar_kalman_features(x,params)
  extra=[z["scalar_loss"]/nominal,z["scalar_variance"]/(nominal*nominal)]
 else:raise ValueError("unknown representation")
 v=np.concatenate((np.asarray(raw,float),np.asarray(extra,float)))
 if not np.all(np.isfinite(v)):raise FloatingPointError("nonfinite augmented filter features")
 return v

class FilterHeadPredictor:
 def __init__(self,model,residuals,residual_weights,kind,params):
  self.model=model;self.residuals=np.asarray(residuals,float);self.residual_weights=np.asarray(residual_weights,float);self.kind=kind;self.params=params
 def predict(self,x):
  from baselines import EmpiricalEvent
  mu=float(self.model.predict(augment(x,self.kind,self.params)[None,:])[0])
  if not math.isfinite(mu):raise FloatingPointError("nonfinite head output")
  d=np.exp(mu+self.residuals)
  if not np.all(np.isfinite(d)) or np.any(d<=0):raise FloatingPointError("invalid event-duration support")
  return EmpiricalEvent(d,self.residual_weights).shifted(float(x["origin_age_weeks"])-float(x["anchor_age_weeks"]))

def cell_folds(xs,seed=42):
 ids=sorted({x["cell_id"] for x in xs})
 if len(ids)<4:raise RuntimeError("too few cells for fixed 2-fold cell-isolated OOF")
 rng=np.random.RandomState(seed);rng.shuffle(ids)
 return [set(ids[::2]),set(ids[1::2])]

def fit_head(xs,kind,fold_params,full_params,seed=42):
 from sklearn.ensemble import HistGradientBoostingRegressor
 from train_eval import weights
 folds=cell_folds(xs,seed)
 ys=np.log(np.asarray([float(x["event_rul_from_anchor"]) for x in xs],float))
 if not np.all(np.isfinite(ys)):raise ValueError("invalid event-duration targets")
 residual=[];rw=[]
 for fold,params in zip(folds,fold_params):
  tr=[i for i,x in enumerate(xs) if x["cell_id"] not in fold]
  va=[i for i,x in enumerate(xs) if x["cell_id"] in fold]
  if not tr or not va:raise RuntimeError("empty cell-held-out fold")
  Xtr=np.stack([augment(xs[i],kind,params) for i in tr])
  Xva=np.stack([augment(xs[i],kind,params) for i in va])
  model=HistGradientBoostingRegressor(max_iter=150,max_leaf_nodes=15,l2_regularization=1.,random_state=seed)
  model.fit(Xtr,ys[tr],sample_weight=weights([xs[i] for i in tr]))
  residual.extend((ys[va]-model.predict(Xva)).tolist())
  counts={}
  for i in va:counts[xs[i]["cell_id"]]=counts.get(xs[i]["cell_id"],0)+1
  rw.extend([1./counts[xs[i]["cell_id"]] for i in va])
 Xfull=np.stack([augment(x,kind,full_params) for x in xs])
 full=HistGradientBoostingRegressor(max_iter=150,max_leaf_nodes=15,l2_regularization=1.,random_state=seed)
 full.fit(Xfull,ys,sample_weight=weights(xs))
 rw=np.asarray(rw,float);rw/=rw.sum()
 return FilterHeadPredictor(full,np.asarray(residual),rw,kind,full_params)

def check_origin_keys(candidates,baseline_rows):
 from collections import Counter
 def key(r):return (str(r["cell_id"]),str(r["arm"]),float(r["origin_stop_epoch"]),float(r["target_rul_weeks"]))
 ref=Counter(key(r) for r in baseline_rows if r["model"]=="hgb_dynamic")
 if not ref:raise ValueError("baseline predictions have no hgb_dynamic rows")
 for model in sorted({str(r["model"]) for r in candidates}):
  got=Counter(key(r) for r in candidates if r["model"]==model)
  if got!=ref:raise RuntimeError("filter and frozen baseline origin/label keys differ for "+model)

def run(a):
 t0=time.time();receipt={"request_id":None,"status":"PREFLIGHT_FAILED","data_read":False,"baseline_predictions_read":False,
  "parameter_fits_started":0,"parameter_fits_completed":0,"parameter_fit_results":{},"hgb_fits_started":0,"hgb_fits_completed":0,"inference_calls":0}
 locks=[];claim=None;out=None;runtime_cap=None
 try:
  go,runtime_cap,sm=check_go(a);receipt["request_id"]=go["request_id"]
  out=fresh_root(a.output);fresh_root(a.receipt)
  expected_claim=ROOT/"automation/locks/filter_comparison_claims"
  if Path(a.claim_dir)!=expected_claim:raise RuntimeError("unexpected persistent claim directory")
  claim=Path(a.claim_dir)/(go["request_id"]+".claim");one_shot_claim(claim,go,a.owner_thread_id)
  # Hold both the prior project-wide CPU lock and the ISU-specific lock.
  locks.append(acquire(a.old_cpu_lock,"shared/old CPU"));locks.append(acquire(a.isu_cpu_lock,"ISU CPU"))
  if json.loads(Path(a.go_json).read_text(encoding="utf-8"))!=go:raise RuntimeError("GO changed after claim")
  check_owner(a.coordinator_json,a.owner_thread_id)
  def alarm(signum,frame):raise TimeoutError("GO hard runtime cap exceeded")
  signal.signal(signal.SIGALRM,alarm);signal.alarm(runtime_cap)
  receipt.update({"status":"RUNNING","source_sha256":sm,"code_manifest_sha256":canonical_hash(sm),
   "max_runtime_seconds":runtime_cap,"fit_counting_note":"Each HGB head reserves 3 fits before two OOF folds+full fit; interruption may yield fewer completed fits. A claimed request is never reused."})
  baseline_rows=load_baseline_predictions(a.baseline_predictions);receipt["baseline_predictions_read"]=True
  # Verify status=PASS/manifest gates inside the frozen adapter before parsing any cell payload.
  from train_eval import load_split,make_examples,evaluate
  cells=load_split(a.cohort,a.data_root,a.data_manifest);receipt["data_read"]=True
  train_cells=[c for c in cells if c["role"]=="train"]
  train=make_examples(train_cells);dev=make_examples([c for c in cells if c["role"]=="development"])
  if not train or not dev:raise RuntimeError("no common event-observed train/dev origins")
  out.mkdir(parents=False,exist_ok=False)
  atomic_json(out/"feature_contract.json",{
   "raw_baseline":"The same 74-dimensional vector from baselines.features(x) (10 numeric causal features + 64 group indicators).",
   "candidate_extra_order":["long_loss/nominal_Ah","short_reversible_offset/nominal_Ah","loss_variance/nominal_Ah^2","offset_variance/nominal_Ah^2","state_covariance/nominal_Ah^2","last_standardized_innovation","last_innovation_sd/nominal_Ah","update_was_projected_as_0_or_1"],
   "candidate_total_dimensions":82,
   "scalar_extra_order":["scalar_loss/nominal_Ah","scalar_variance/nominal_Ah^2"],
   "scalar_total_dimensions":76,
   "age_staleness":"Use the common raw feature vector age and staleness columns exactly once; filter API age/staleness outputs are not appended.",
   "label_access":"Filter features consume visible records and query only; source endpoint/event labels never enter filter state features."
  })
  from filter_representation import fit_candidate_parameters,fit_scalar_kalman_parameters
  branch_specs=(("candidate",fit_candidate_parameters),("scalar",fit_scalar_kalman_parameters))
  params_ok={};statuses={}
  folds=cell_folds(train,seed=42)
  for name,fitfn in branch_specs:
   cell_params=[];branch_results=[]
   role_specs=[("full",[c for c in train_cells])]
   role_specs.extend(("oof_fold_"+str(j+1),[c for c in train_cells if c["cell_id"] not in fold]) for j,fold in enumerate(folds))
   for role,fit_cells in role_specs:
    receipt["parameter_fits_started"]+=1
    try:
     res=fitfn(fit_cells,maxiter=200);receipt["parameter_fits_completed"]+=1
     branch_results.append((role,res))
     if role!="full" and res.get("status")=="FIT_OK":
      cell_params.append(param_object(name,res["parameters"]))
    except Exception as e:
     res={"status":"FIT_FAILED","error":repr(e)}
     branch_results.append((role,res))
   statuses[name]={role:res for role,res in branch_results}
   for role,res in branch_results:atomic_json(out/(name+"_"+role+"_parameter_fit.json"),res)
   if all(res.get("status")=="FIT_OK" for _,res in branch_results):
    full_res=dict(branch_results[0][1])
    params_ok[name]={"full":param_object(name,full_res["parameters"]),"folds":cell_params}
   else:
    statuses[name]["branch_status"]="PARAMETER_CV_STOP"
  atomic_json(out/"filter_parameter_status.json",statuses)
  models={}
  for name in ("candidate","scalar"):
   if name not in params_ok:continue
   receipt["hgb_fits_started"]+=3
   try:
    head=fit_head(train,name,params_ok[name]["folds"],params_ok[name]["full"],seed=42);receipt["hgb_fits_completed"]+=3
    import joblib
    joblib.dump(head.model,out/(name+"_hgb_full.joblib"))
    np.save(out/(name+"_oof_log_residuals.npy"),head.residuals)
    np.save(out/(name+"_oof_cell_equal_weights.npy"),head.residual_weights)
    models["filter_"+name]=head
   except Exception as e:
    statuses[name+"_head"]={"status":"HEAD_FIT_FAILED","error":repr(e)};atomic_json(out/"filter_parameter_status.json",statuses)
  if not models:
   receipt["status"]="NO_FILTER_FIT_OK"
   atomic_json(out/"filter_parameter_status.json",statuses)
   raise RuntimeError("both filter parameter fits failed/identifiability-stopped; no head was fit")
  maxcalls=int(go["max_inference_calls"])
  required=len(dev)*len(models)
  if required>maxcalls:raise RuntimeError("development inference-call cap exceeded before inference")
  # Temporary directory contains only filter-branch evaluation; baseline predictions are read-only.
  evaldir=out/"filter_only"
  evaldir.mkdir()
  receipt["inference_calls"]=required
  n=evaluate(models,dev,evaldir)
  newrows=list(csv.DictReader((evaldir/"predictions_dev.csv").open("r",newline="",encoding="utf-8")))
  check_origin_keys(newrows,baseline_rows)
  # Combine frozen saved baseline predictions and new filter predictions for one downstream summary.
  columns=list(baseline_rows[0].keys())
  if any(set(r)!=set(columns) for r in newrows):raise RuntimeError("prediction schema differs from frozen baseline")
  with (out/"predictions_dev.csv").open("x",newline="",encoding="utf-8") as f:
   w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(baseline_rows);w.writerows(newrows)
  receipt.update({"status":"SUCCESS","filter_prediction_rows":n,"baseline_rows_reused":len(baseline_rows),
   "fit_budget_proposal":{"parameter_fits_max":6,"hgb_fits_max":6,"total_max":12},"seed":42,
   "note":"Filter parameters fitted on train-role observation records only; labels never enter filter feature construction. Same raw feature vector is augmented for both filter heads. Dev results are descriptive only; no independent confirmation."})
 except Exception as e:
  receipt.update({"status":"FAILED","error":repr(e),"traceback":traceback.format_exc(limit=8)})
  raise
 finally:
  receipt["elapsed_seconds"]=time.time()-t0
  if runtime_cap is not None:
   try:signal.alarm(0)
   except Exception:pass
  try:receipt["receipt_path_written"]=durable_receipt(a.receipt,receipt.get("request_id"),receipt)
  finally:
   for lk in reversed(locks):
    try:fcntl.flock(lk,fcntl.LOCK_UN);lk.close()
    except Exception:pass

def main():
 p=argparse.ArgumentParser()
 for k in ("cohort","data_root","data_manifest","baseline_predictions","output","receipt","claim_dir","owner_thread_id","coordinator_json","old_cpu_lock","isu_cpu_lock"):
  p.add_argument("--"+k.replace("_","-"),required=True)
 p.add_argument("--go-json",required=True);run(p.parse_args())
if __name__=="__main__":main()

