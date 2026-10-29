#!/usr/bin/env python3
"""Preregistered train-cell gain prediction pilot; never loads C3/C4."""
import os
os.environ.setdefault("OMP_NUM_THREADS","4");os.environ.setdefault("MKL_NUM_THREADS","4")
import pathlib,sys,json,csv,collections,datetime,fcntl,hashlib,time,traceback,argparse
import numpy as np
ROOT=pathlib.Path("/home/yndx/zxk/rul");HERE=ROOT/"experiments/rulaas_gain_learning_20261029"
DATA=ROOT/"experiments/rulaas_gain_identifiability_20261029/run02";REVIEW=ROOT/"reports/rulaas_gain_review_20261029_terra"
OWNER="01a17810-6ae6-7cf2-9729-5bfcaa8df5f4"
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def readj(p):return json.loads(pathlib.Path(p).read_text())
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def writej(p,obj):
 with pathlib.Path(p).open("x",encoding="utf-8") as f:json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False)
def csvout(p,rows):
 if rows:
  with pathlib.Path(p).open("x",newline="") as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def progress(out,x):
 tmp=out/"progress.tmp";tmp.write_text(json.dumps(x,ensure_ascii=False));os.replace(tmp,out/"progress.json")
def weighted_quantile(values,weights,level):
 order=np.argsort(values,kind="mergesort");values=np.asarray(values)[order];weights=np.asarray(weights)[order]
 return float(values[min(len(values)-1,int(np.searchsorted(np.cumsum(weights)/sum(weights),level,side="left")))])
def main(path):
 g=readj(path);out=ROOT/g["output"];t0=time.time();locks=[]
 rec={"status":"STARTED","request_id":g["request_id"],"started_utc":stamp(),"predictive_estimator_fits_started":0,"predictive_estimator_fits_completed":0,"preprocessor_components_fit":0,"model_prediction_rows":0,"C3_payload_reads":0,"C4_payload_reads":0}
 try:
  for p in [ROOT/"automation/state/coordinator.lock",ROOT/"automation/locks/isu_irregular_rul_cpu.lock"]:
   f=p.open("a+");fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  c=readj(ROOT/"automation/state/coordinator.json")
  if c.get("owner")!=OWNER or c.get("thread_id")!=OWNER or c.get("state")!="ACTIVE":raise ValueError("owner")
  hb=datetime.datetime.fromisoformat(c["heartbeat_utc"].replace("Z","+00:00"))
  if (datetime.datetime.now(datetime.timezone.utc)-hb).total_seconds()>1800:raise ValueError("heartbeat")
  if g.get("status")!="APPROVED" or g.get("owner")!=OWNER or g.get("allow_fits") is not True or g.get("allow_C3") is not False or g.get("allow_C4") is not False or g.get("model_preference_resolved") is not True:raise ValueError("fresh GO or model preference")
  rec["coordinator_model_recorded"]=g["actual_model"];rec["model_record_note"]="Recorded by the coordinator; Python runner cannot independently introspect the assistant model."
  if g["predictive_estimator_fit_cap"]!=5 or g["prediction_row_cap"]!=1000 or g["seed"]!=42:raise ValueError("budget")
  for p,h in g["input_sha256"].items():
   if sha(ROOT/p)!=h:raise ValueError("input digest "+p)
  if out.parent!=HERE or out.exists():raise ValueError("output must be new")
  writej(HERE/(g["request_id"]+".claim.json"),{"utc":stamp(),"GO_sha256":sha(path)});out.mkdir()
  audit=readj(REVIEW/"AUDIT.json");split=readj(DATA/"cell_split.json");schema=readj(DATA/"feature_schema.json")
  if audit["status"]!="PASS" or audit["C3_payload_reads"] or audit["C4_payload_reads"] or schema["dimensions"]!=711:raise ValueError("input audit")
  with (DATA/"cases.csv").open() as f:cases=list(csv.DictReader(f))
  X=np.load(DATA/"request_features.npz",allow_pickle=False)["X_request"]
  if X.shape!=(186,711) or len(cases)!=186 or np.isinf(X).any():raise ValueError("feature dimensions")
  if schema["features"][6]!="query_gap_from_last_rpt_weeks" or schema["features"][-1]!="positive_head_point_proxy_RUL_weeks":raise ValueError("feature identities")
  for j,r in enumerate(cases):
   if int(r["case_id"])!=j:raise ValueError("row identity")
  train=np.asarray([r["population"]=="kernel_fit" for r in cases]);val=np.asarray([r["population"]=="kernel_held" for r in cases])
  if train.sum()!=101 or val.sum()!=85 or not np.all(train|val):raise ValueError("population")
  ctrain=np.asarray([r["cell_id"] for r in cases])[train];cval=np.asarray([r["cell_id"] for r in cases])[val]
  if set(ctrain)!=set(split["selected_kernel_fit"]) or set(cval)!=set(split["selected_kernel_held"]) or set(ctrain)&set(cval):raise ValueError("physical cell split")
  if not set(cval)<=set(split["base_head_unseen_cells"]) or set(cval)&set(split["base_head_fit_cells"]):raise ValueError("held head leakage")
  y=np.asarray([float(r["label_gain_7day_delivery_weeks"]) for r in cases],float)
  if not np.isfinite(y).all():raise ValueError("nonfinite gain")
  counts=collections.Counter(ctrain);weights=np.asarray([1./counts[z] for z in ctrain]);weights*=len(weights)/weights.sum()
  allidx=np.arange(711);f0=np.r_[np.arange(74),710];f2=np.r_[np.arange(74),np.arange(686,710),710];age=np.asarray([6,710])
  if schema["features"][686]!="cycle_count_observed":raise ValueError("unexpected F3 panel layout")
  from sklearn.pipeline import Pipeline
  from sklearn.impute import SimpleImputer
  from sklearn.preprocessing import StandardScaler
  from sklearn.linear_model import Ridge
  from sklearn.ensemble import HistGradientBoostingRegressor
  import sklearn,joblib
  ridge=lambda:Pipeline([("impute",SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True)),("scale",StandardScaler()),("ridge",Ridge(alpha=10.))])
  hgb=lambda:HistGradientBoostingRegressor(max_iter=120,max_leaf_nodes=7,min_samples_leaf=10,l2_regularization=2.,random_state=42,early_stopping=False)
  specs=[("ridge_age_point",age,ridge()),("ridge_F2_point",f2,ridge()),("hgb_F0_point",f0,hgb()),("hgb_F2_point",f2,hgb()),("hgb_F3_point",allidx,hgb())]
  estimator={};data={}
  for name,indices,model in specs:
   rec["predictive_estimator_fits_started"]+=1;progress(out,rec)
   if rec["predictive_estimator_fits_started"]>g["predictive_estimator_fit_cap"]:raise ValueError("fit cap")
   if name.startswith("ridge"):
    model.fit(X[train][:,indices],y[train],ridge__sample_weight=weights);rec["preprocessor_components_fit"]+=2
   else:model.fit(X[train][:,indices],y[train],sample_weight=weights)
   rec["predictive_estimator_fits_completed"]+=1
   with (out/(name+".joblib")).open("xb") as f:joblib.dump(model,f,compress=3)
   estimator[name]=(indices,model);progress(out,rec)
  if rec["predictive_estimator_fits_completed"]!=5:raise ValueError("incomplete model set")
  # All fits complete before any held-population prediction.
  rec["all_fits_before_held_predictions"]=True;progress(out,rec)
  ytrain=y[train];yval=y[val]
  per_train=[float(np.mean(ytrain[ctrain==cid])) for cid in sorted(set(ctrain))]
  constant=float(np.mean(per_train))
  data["constant"]={"train":np.full(len(ytrain),constant),"held":np.full(len(yval),constant)}
  for name,(indices,model) in estimator.items():
   rows=len(ytrain)+len(yval)
   if rec["model_prediction_rows"]+rows>g["prediction_row_cap"]:raise ValueError("model row cap")
   predtrain=np.asarray(model.predict(X[train][:,indices]),float);predval=np.asarray(model.predict(X[val][:,indices]),float)
   rec["model_prediction_rows"]+=rows
   if not np.isfinite(predtrain).all() or not np.isfinite(predval).all():raise ValueError("nonfinite model outputs; no clipping")
   data[name]={"train":predtrain,"held":predval}
  # Cell-equal gain-prediction MAE, not RUL MAE or station cost.
  heldids=np.flatnonzero(val);rows=[];summaries=[];cell_errors={}
  try:
   from scipy.stats import spearmanr
  except ImportError:raise ValueError("scipy required for rank metric")
  for name,pred in data.items():
   score=pred["held"];tr=pred["train"];threshold=weighted_quantile(tr,weights,.75);by=collections.defaultdict(list);u=collections.defaultdict(list)
   for i,(j,yp,yt) in enumerate(zip(heldids,score,yval)):
    r=cases[j];error=abs(float(yp)-float(yt));chosen=bool(yp>=threshold);cid=r["cell_id"]
    rows.append({"model":name,"cell_id":cid,"case_id":int(r["case_id"]),"observed_gain_weeks":float(yt),"predicted_gain_weeks":float(yp),"absolute_gain_prediction_error":error,"selected_by_train_75pct_threshold":chosen})
    by[cid].append(error);u[cid].append(float(yt) if chosen else 0.)
   cell_errors[name]={cid:float(np.mean(v)) for cid,v in by.items()}
   rho=float(spearmanr(score,yval)[0]) if len(set(score))>1 and len(set(yval))>1 else None
   if rho is not None and not np.isfinite(rho):rho=None
   selected=score>=threshold
   summaries.append({"model":name,"held_cells":len(by),"held_cases":len(yval),"cell_macro_gain_MAE":float(np.mean(list(cell_errors[name].values()))),"pooled_gain_MAE":float(np.mean(np.abs(score-yval))),"held_spearman":rho,"train_threshold_75pct":threshold,"held_selected_cases":int(selected.sum()),"held_selected_fraction":float(np.mean(selected)),"selected_negative_gain_cases":int(np.sum(yval[selected]<-1e-9)),"selected_mean_gain":float(np.mean(yval[selected])) if selected.any() else None,"cell_macro_gain_if_selected_per_opportunity":float(np.mean([np.mean(v) for v in u.values()])),"selection_note":"threshold frozen from training predictions; different selected rates are not matched cost"})
  contrasts=[]
  for candidate,refs in [("hgb_F3_point",["constant","ridge_age_point","hgb_F0_point","ridge_F2_point","hgb_F2_point"]),("hgb_F2_point",["constant","ridge_age_point","hgb_F0_point","ridge_F2_point"])]:
   alpha=.05/len(refs);cells=sorted(set(cval));groups=sorted({cid.rsplit("C",1)[0] for cid in cells})
   rng=np.random.RandomState(42);indices=rng.randint(len(groups),size=(5000,len(groups)))
   for ref in refs:
    delta=np.asarray([cell_errors[candidate][cid]-cell_errors[ref][cid] for cid in cells])
    sums=np.asarray([sum(delta[i] for i,cid in enumerate(cells) if cid.rsplit("C",1)[0]==g) for g in groups])
    counts=np.asarray([sum(cid.rsplit("C",1)[0]==g for cid in cells) for g in groups])
    boot=sums[indices].sum(axis=1)/counts[indices].sum(axis=1)
    cand=np.mean(list(cell_errors[candidate].values()));base=np.mean(list(cell_errors[ref].values()))
    contrasts.append({"candidate":candidate,"reference":ref,"delta_gain_MAE":float(delta.mean()),"family_corrected_CI_low":float(np.quantile(boot,alpha/2)),"family_corrected_CI_high":float(np.quantile(boot,1-alpha/2)),"relative_gain_MAE_improvement":float((base-cand)/base) if base>0 else None,"held_cells":len(cells),"held_groups":len(groups),"bootstrap_replicates":5000,"CI_scope":"resample source groups; within-group cells retained; conditional on fixed proxy and cases"})
  def passes(candidate):
   a=[z for z in contrasts if z["candidate"]==candidate]
   return all(z["family_corrected_CI_high"]<0 and z["relative_gain_MAE_improvement"] is not None and z["relative_gain_MAE_improvement"]>=.05 for z in a)
  if passes("hgb_F3_point"):result="F3_PROXY_GAIN_SIGNAL_PASSES_PRESPECIFIED_PILOT"
  elif passes("hgb_F2_point"):result="F2_PROXY_GAIN_SIGNAL_PASSES_SECONDARY_PILOT_F3_NO_GAIN"
  else:result="NO_GAIN_BOTH_PREDECLARED_PROXY_CANDIDATES"
  csvout(out/"predictions.csv",rows);csvout(out/"summary.csv",summaries);csvout(out/"paired_contrasts.csv",contrasts)
  rec.update(status="SUCCESS",finished_utc=stamp(),elapsed_seconds=time.time()-t0,train_cells=len(set(ctrain)),held_cells=len(set(cval)),train_cases=int(train.sum()),held_cases=int(val.sum()),sklearn_version=sklearn.__version__,GO_sha256=sha(path),input_sha256=g["input_sha256"])
  writej(out/"receipt.json",rec);writej(out/"ROOT_DECISION.json",{"status":result,"paper_ready":False,"new_method_in_resource_service_validated":False,"no_C3_selection":True,"PENDING_FLAG_VARIATION":False,"prespecified_5pct_relative_threshold":True,"criteria":"family-corrected paired group-cluster bootstrap upper CI below zero and at least 5% gain-MAE reduction against every predeclared comparator","limits":["single fixed positive-RUL proxy, no event head/full service model","held cells are historical C1/C2, not final confirmation","train proxy head fitted on meta-training cells, possible gain-label distribution shift","all 186 initial cases have no pending report","selection thresholds do not give matched budget or a fleet result"],"next":"If a candidate passes, test its score under a freshly specified causal resource replay and strong age baseline; otherwise stop these fixed scoring configurations and investigate distinct support/mechanism, not extra seeds."})
  progress(out,rec);print(json.dumps({"receipt":rec,"summary":summaries,"contrasts":contrasts,"status":result},ensure_ascii=False))
 except BaseException as ex:
  rec.update(status="FAILED",error=repr(ex),traceback=traceback.format_exc(),finished_utc=stamp(),elapsed_seconds=time.time()-t0,partial_preprocessing_may_have_fitted=rec["predictive_estimator_fits_started"]>rec["predictive_estimator_fits_completed"])
  if out.is_dir() and not (out/"failure_receipt.json").exists():writej(out/"failure_receipt.json",rec)
  print(json.dumps(rec));raise
 finally:
  for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
if __name__=="__main__":
 ap=argparse.ArgumentParser();ap.add_argument("--go",required=True);main(pathlib.Path(ap.parse_args().go))
