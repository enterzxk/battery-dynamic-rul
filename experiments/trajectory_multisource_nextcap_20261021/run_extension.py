#!/home/yndx/miniconda3/envs/a40_env/bin/python3.9
from __future__ import annotations
import os
os.environ["OMP_NUM_THREADS"]="4"; os.environ["MKL_NUM_THREADS"]="4"; os.environ["OPENBLAS_NUM_THREADS"]="4"
import argparse,csv,datetime,fcntl,hashlib,json,math,pathlib,sys,time,traceback,signal
import numpy as np
ROOT=pathlib.Path("/home/yndx/zxk/rul"); HERE=ROOT/"experiments/trajectory_multisource_nextcap_20261021"
CACHE=ROOT/"experiments/multisource_factorial_20261021/run2_clocksafe"
CACHE_RECEIPT=ROOT/"experiments/multisource_factorial_20261021/MULTISOURCE_FORMAL_2X2_80FITS_CLOCK_VALIDITY_REPAIR_20261021_receipt.json"
V18=ROOT/"experiments/dart_rul_v18"; B=ROOT/"experiments/multisource_mechanisms_20261021"; OLD=ROOT/"experiments/isu_irregular_rul_seed42_v1"
COHORT=ROOT/"reports/isu_ilcc_capacity_probe_20261020_root/cohort.json"; MANIFEST=ROOT/"reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json"; DATA=ROOT/"data/processed/ISU_ILCC_DataV2_v1"
STATE=ROOT/"automation/state/coordinator.json"; OWNER="01a15c3a-1a06-7d61-8517-27b70b246183"
PANELS=("F1","F2","F3"); MODELS=("hgb","catboost"); DIMS={"F1":686,"F2":98,"F3":710}; FITS=18
CACHE_FILES=("train_features.npz","development_features.npz","train_rows.jsonl","development_rows.jsonl","feature_schema.json")
def sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open("rb") as f:
  for b in iter(lambda:f.read(1048576),b""):h.update(b)
 return h.hexdigest()
def readj(p):return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
def writej(p,x):
 with pathlib.Path(p).open("x",encoding="utf-8") as f:json.dump(x,f,indent=2,ensure_ascii=False,allow_nan=True)
def atomicj(p,x):
 t=pathlib.Path(str(p)+'.tmp');t.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=True),encoding='utf-8');os.replace(t,p)
def source_hashes():
 ps=[HERE/"run_extension.py",HERE/"PROTOCOL_ZH.md",CACHE_RECEIPT,ROOT/"experiments/multisource_factorial_20261021/runner.py",ROOT/"experiments/multisource_factorial_20261021/features.py",V18/"data_protocol.py",V18/"hgb_models.py",B/"train_v1/targets.py",OLD/"train_eval.py",OLD/"data_adapter.py",COHORT,MANIFEST]
 return {str(p.relative_to(ROOT)):sha(p) for p in ps}
def cache_hashes():return {n:sha(CACHE/n) for n in CACHE_FILES}
def validate(g,path):
 req=("status","allow_fit","request_id","owner_thread_id","issued_utc","fit_count","fit_plan","seed","panels","models","model_config","threads","device","max_runtime_seconds","cache_path","cache_receipt_sha256","cache_sha256","source_sha256","cohort_sha256","manifest_sha256","output_path","receipt_path")
 if any(k not in g for k in req):raise ValueError("GO missing fields")
 if g["status"]!="APPROVED" or g["allow_fit"] is not True or g["owner_thread_id"]!=OWNER:raise ValueError("GO approval/owner mismatch")
 if (g["fit_count"],g["seed"],tuple(g["panels"]),tuple(g["models"]))!=(FITS,42,PANELS,MODELS):raise ValueError("fit/panel/model contract mismatch")
 if g["fit_plan"]!="F1,F2,F3 x HGB/CatBoost; two cell-isolated OOF fits plus one all-train fit per panel/model":raise ValueError("fit plan mismatch")
 cfg={"hgb":{"max_iter":150,"max_leaf_nodes":15,"l2_regularization":1,"random_state":42,"early_stopping":False},"catboost":{"iterations":400,"depth":5,"learning_rate":0.04,"l2_leaf_reg":3,"random_seed":42,"thread_count":4}}
 if g["model_config"]!=cfg or (g["threads"],g["device"])!=(4,"cpu") or not 60<=int(g["max_runtime_seconds"])<=14400:raise ValueError("model/runtime contract mismatch")
 if not isinstance(g["request_id"],str) or len(g["request_id"])<8:raise ValueError("GO request_id missing/invalid")
 if pathlib.Path(g["cache_path"]).resolve()!=CACHE.resolve() or sha(CACHE_RECEIPT)!=g["cache_receipt_sha256"]:raise ValueError("cache identity mismatch")
 cr=readj(CACHE_RECEIPT)
 if cr.get("status")!="SUCCESS" or cr.get("output")!=str(CACHE) or cr.get("CPU_fits_completed")!=80 or cr.get("C4_payload_reads")!=0:raise ValueError("formal cache receipt invalid")
 if cache_hashes()!=g["cache_sha256"] or source_hashes()!=g["source_sha256"]:raise ValueError("cache/source hashes mismatch")
 if sha(COHORT)!=g["cohort_sha256"] or sha(MANIFEST)!=g["manifest_sha256"]:raise ValueError("cohort/manifest mismatch")
 ts=datetime.datetime.fromisoformat(g["issued_utc"].replace("Z","+00:00"))
 if abs((datetime.datetime.now(datetime.timezone.utc)-ts).total_seconds())>86400:raise ValueError("stale GO")
 out=(ROOT/g["output_path"]).resolve()
 if HERE.resolve() not in out.parents or out.exists():raise ValueError("output must be fresh under extension runs")
 receipt=pathlib.Path(g["receipt_path"])
 if receipt.parent.resolve()!=(HERE/"receipts").resolve() or receipt.exists():raise ValueError("receipt path invalid")
 if readj(path)!=g:raise ValueError("GO changed")
 sys.path.insert(0,str(OLD))
 from train_eval import validate_owner
 validate_owner(STATE,OWNER)
 return out,receipt
def jsonl(p):
 with pathlib.Path(p).open(encoding="utf-8") as f:return [json.loads(x) for x in f if x.strip()]
def load_cells():
 sys.path.insert(0,str(OLD))
 from train_eval import load_split
 cells=load_split(COHORT,DATA,MANIFEST)
 if len(cells)!=188 or any(str(c["cell_id"]).endswith("C4") for c in cells):raise ValueError("cohort includes unexpected/locked cells")
 return cells
def split_rows(split,cells):
 sys.path[:0]=[str(V18),str(B/"train_v1")]
 from data_protocol import make_examples
 from targets import build_targets
 ex=make_examples(cells); targets=build_targets(ex,cells)
 tm={(str(r["cell_id"]),str(r["arm"]),round(float(r["query_epoch"]),6)):r for r in targets}
 meta=jsonl(CACHE/(split+"_rows.jsonl")); z=np.load(CACHE/(split+"_features.npz"),allow_pickle=False)
 mats={p:z[p] for p in PANELS}
 for p in PANELS:
  if mats[p].shape!=(len(meta),DIMS[p]) or np.isinf(mats[p]).any():raise ValueError("feature cache shape/value error "+p)
 rows=[]
 for i,m in enumerate(meta):
  k=(str(m["cell_id"]),str(m["arm"]),round(float(m["query_epoch"]),6)); t=tm.get(k)
  if t is None or t.get("next_capacity_ah") is None:continue
  h=float(t["next_query_elapsed_weeks"])
  if math.isfinite(h) and h>0:rows.append({"key":k,"idx":i,"cell":k[0],"cell_id":k[0],"arm":k[1],"q":k[2],"h":h,"y":float(t["next_capacity_ah"])})
 if len({r["key"] for r in rows})!=len(rows):raise ValueError("duplicate eligible target keys")
 return rows,mats
def X(rows,mats,p):return np.column_stack((mats[p][[r["idx"] for r in rows]].astype(float),[r["h"] for r in rows]))
def sw(rows):
 c={}
 for r in rows:c[r["cell"]]=c.get(r["cell"],0)+1
 return np.asarray([1/c[r["cell"]] for r in rows])
def newmodel(k):
 if k=="hgb":
  from sklearn.ensemble import HistGradientBoostingRegressor
  return HistGradientBoostingRegressor(max_iter=150,max_leaf_nodes=15,l2_regularization=1,random_state=42,early_stopping=False)
 from catboost import CatBoostRegressor
 return CatBoostRegressor(iterations=400,depth=5,learning_rate=.04,l2_leaf_reg=3,loss_function="RMSE",random_seed=42,thread_count=4,verbose=False,allow_writing_files=False)
def fit(k,x,y,w):m=newmodel(k);m.fit(x,y,sample_weight=w);return m
def recorded_fit(kind,x,y,w,meta,out,r,deadline):
 if time.monotonic()>=deadline:raise TimeoutError("GO runtime deadline reached before fit")
 if r["fits_started"]>=FITS:raise RuntimeError("fit budget exceeded")
 r["fits_started"]+=1; idx=r["fits_started"]; rec={"fit_index":idx,**meta,"state":"STARTED","started_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()}
 atomicj(out/f"fit_{idx:02d}.json",rec);atomicj(out/"progress.json",r)
 try:
  m=fit(kind,x,y,w)
  if time.monotonic()>=deadline:raise TimeoutError("GO runtime deadline reached during fit")
  rec.update(state="COMPLETED",finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());r["fit_count"]+=1
  return m
 except BaseException as e:
  rec.update(state="FAILED",finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),error=repr(e));raise
 finally:
  r["fits_completed"]+=1;atomicj(out/f"fit_{idx:02d}.json",rec);atomicj(out/"progress.json",r)
def csvout(p,rows):
 if rows:
  with pathlib.Path(p).open("x",newline="",encoding="utf-8") as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def run(path):
 t0=time.time();out=None;receipt=None;locks=[];deadline=None;timer_armed=False;r={"status":"PREFLIGHT_FAILED","fit_count":0,"fits_started":0,"fits_completed":0,"dev_inference_started":False,"C4_payload_reads":0}
 try:
  g=readj(path);out,receipt=validate(g,path);go_sha256=sha(path);request_id=g["request_id"]
  deadline=time.monotonic()+int(g["max_runtime_seconds"])
  def alarm_handler(signum,frame):raise TimeoutError("GO runtime deadline reached")
  signal.signal(signal.SIGALRM,alarm_handler);signal.setitimer(signal.ITIMER_REAL,int(g["max_runtime_seconds"]));timer_armed=True
  r.update(go_sha256=go_sha256,request_id=request_id,max_runtime_seconds=int(g["max_runtime_seconds"]))
  for lp in (ROOT/"automation/state/online_survival_cpu.lock",ROOT/"automation/locks/isu_irregular_rul_cpu.lock"):
   f=lp.open("a+");fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  out.mkdir(parents=True,exist_ok=False)
  cells=load_cells(); trc=[c for c in cells if c.get("role")=="train"]; dvc=[c for c in cells if c.get("role")=="development"]
  tr,tm=split_rows("train",trc); dv,dm=split_rows("development",dvc)
  if not tr or not dv or {x["cell"] for x in tr}&{x["cell"] for x in dv}:raise ValueError("empty rows or cell split overlap")
  folds=__import__("hgb_models")._two_cell_folds(tr,42); trainids={x["cell"] for x in tr}
  if set.union(*folds)!=trainids or set.intersection(*folds):raise ValueError("invalid OOF cell partition")
  r.update(status="FITTING",train_rows=len(tr),dev_rows=len(dv),train_cells=len(trainids),dev_cells=len({x["cell"] for x in dv}),cache_sha256=cache_hashes(),fit_budget=FITS)
  atomicj(out/"progress.json",r); models={}; calib=[];calib_details=[]
  for kind in MODELS:
   for panel in PANELS:
    x=X(tr,tm,panel); y=np.asarray([z["y"] for z in tr]); w=sw(tr); oof=np.full(len(tr),np.nan)
    for fi,held in enumerate(folds):
     a=np.asarray([i for i,z in enumerate(tr) if z["cell"] not in held]); b=np.asarray([i for i,z in enumerate(tr) if z["cell"] in held])
     m=recorded_fit(kind,x[a],y[a],w[a],{"model":kind,"panel":panel,"fold":fi,"held_cells":sorted(held),"n_fit":len(a)},out,r,deadline);oof[b]=m.predict(x[b])
    if not np.isfinite(oof).all():raise ValueError("OOF incomplete")
    by={}
    for z,e in zip(tr,y-oof):by.setdefault(z["cell"],[]).append(float(e*e))
    sigma=max(math.sqrt(float(np.mean([np.mean(v) for v in by.values()]))),1e-6)
    m=recorded_fit(kind,x,y,w,{"model":kind,"panel":panel,"fold":"all","n_fit":len(y)},out,r,deadline)
    models[(kind,panel)]=(m,sigma);calib.append({"model":kind,"panel":panel,"rows":len(tr),"cells":len(by),"sigma_oof_ah":sigma});calib_details.append({"model":kind,"panel":panel,"sigma_oof_ah":sigma,"cell_squared_errors":by,"oof_rows":[{"key":z["key"],"target_capacity_ah":float(yy),"oof_prediction_ah":float(pp),"residual_ah":float(yy-pp)} for z,yy,pp in zip(tr,y,oof)]})
  if r["fit_count"]!=FITS or r["fits_started"]!=FITS or r["fits_completed"]!=FITS:raise ValueError("fit budget mismatch")
  import joblib
  joblib.dump({(kind,panel):{"estimator":m,"sigma_oof_ah":sig} for (kind,panel),(m,sig) in models.items()},out/"final_models.joblib",compress=3)
  joblib.dump({"calibration":calib_details,"train_rows":len(tr),"train_cells":len(trainids),"seed":42},out/"oof_calibration.joblib",compress=3)
  r["all_fits_completed_before_dev_inference"]=True;r["dev_inference_started"]=True;atomicj(out/"progress.json",r)
  preds=[]
  for (kind,panel),(m,sig) in models.items():
   mu=m.predict(X(dv,dm,panel))
   for z,p in zip(dv,mu):preds.append({"model":kind,"panel":panel,"cell_id":z["cell"],"arm":z["arm"],"query_epoch":z["q"],"forecast_h_weeks":z["h"],"target_capacity_ah":z["y"],"predicted_capacity_ah":float(p),"sigma_oof_ah":sig,"error_ah":float(p-z["y"]),"abs_error_ah":abs(float(p-z["y"]))})
  summ=[];cellscores=[]
  for kind,panel in models:
   sig=models[(kind,panel)][1]
   for arm in ("raw","sparse2","delay7d"):
    rr=[z for z in preds if z["model"]==kind and z["panel"]==panel and z["arm"]==arm]; by={}
    for z in rr:by.setdefault(z["cell_id"],[]).append(z)
    vals=[]
    for cid,rs in by.items():
     e=np.asarray([z["error_ah"] for z in rs]); nll=.5*(e/sig)**2+math.log(sig)+.5*math.log(2*math.pi);v={"n":len(rs),"mse":float(np.mean(e*e)),"mae":float(np.mean(abs(e))),"nll":float(np.mean(nll))};vals.append(v);cellscores.append({"model":kind,"panel":panel,"arm":arm,"cell_id":cid,**v,"cell_rmse_ah":math.sqrt(v["mse"])})
    summ.append({"model":kind,"panel":panel,"arm":arm,"rows":len(rr),"cells":len(by),"rmse_ah":math.sqrt(float(np.mean([v["mse"] for v in vals]))),"mae_ah":float(np.mean([v["mae"] for v in vals])),"gaussian_nll":float(np.mean([v["nll"] for v in vals])),"sigma_oof_ah":sig})
  csvout(out/"predictions_c3.csv",preds);csvout(out/"oof_calibration.csv",calib);csvout(out/"metrics_by_model_panel_arm.csv",summ);csvout(out/"metrics_by_cell.csv",cellscores)
  r.update(status="COMPLETE_NO_DEV_SELECTION",prediction_rows=len(preds),metrics=summ,elapsed_seconds=time.time()-t0,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 except BaseException as e:r.update(status="FAILED",error=repr(e),traceback=traceback.format_exc(),elapsed_seconds=time.time()-t0,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 finally:
  if timer_armed:signal.setitimer(signal.ITIMER_REAL,0)
  if out and out.exists():
   with (out/"receipt.json").open("w",encoding="utf-8") as f:json.dump(r,f,ensure_ascii=False,indent=2,allow_nan=True)
  for f in reversed(locks):
   try:fcntl.flock(f,fcntl.LOCK_UN);f.close()
   except Exception:pass
  if receipt:
   receipt.parent.mkdir(parents=True,exist_ok=True)
   with receipt.open("x",encoding="utf-8") as f:json.dump(r,f,ensure_ascii=False,indent=2,allow_nan=True)
 print(json.dumps(r,ensure_ascii=False,indent=2));return r
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--go",required=True);a=p.parse_args();q=run(a.go);sys.exit(0 if q["status"]=="COMPLETE_NO_DEV_SELECTION" else 2)





