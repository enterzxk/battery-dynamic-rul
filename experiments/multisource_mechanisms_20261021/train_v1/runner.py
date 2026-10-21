"""Exact-GO serial trainer for B-full and its independent-increment ablation."""
from __future__ import annotations
import argparse,datetime,fcntl,hashlib,json,math,os,random,sys,time,traceback
from pathlib import Path
ROOT=Path("/home/yndx/zxk/rul");HERE=Path(__file__).resolve().parent
OLD=ROOT/"experiments/isu_irregular_rul_seed42_v1";V18=ROOT/"experiments/dart_rul_v18"
COHORT=ROOT/"reports/isu_ilcc_capacity_probe_20261020_root/cohort.json"
MANIFEST=ROOT/"reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json"
DATA=ROOT/"data/processed/ISU_ILCC_DataV2_v1";STATE=ROOT/"automation/state/coordinator.json"
SOURCES=[HERE/"mechanisms.py",HERE/"targets.py",HERE/"runner.py",V18/"protocol.json",
 V18/"data_protocol.py",OLD/"train_eval.py",OLD/"data_adapter.py",OLD/"baselines.py"]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def source_map():return {str(p.relative_to(ROOT)):sha(p) for p in SOURCES}
def canonical(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def atomic(p,x):
 p=Path(p);tmp=p.with_suffix(p.suffix+".tmp");tmp.write_text(json.dumps(x,indent=2,allow_nan=True),encoding="utf-8");os.replace(tmp,p)
def schedule_contract_hash(g):
 return canonical({"builder_sha256":g["source_sha256"][str((HERE/"targets.py").relative_to(ROOT))],
  "method":"train-only empirical RPT interval quantiles, deterministic repeated schedule",
  "horizon_weeks":float(g["schedule_horizon_weeks"]),"quantiles":int(g["schedule_quantiles"])})
def validate_go(g,path):
 required=("request_id","status","allow_fit","owner_thread_id","issued_utc","source_sha256",
  "code_manifest_sha256","cohort_sha256","manifest_sha256","seed","models","max_steps_per_model",
  "batch_size","learning_rate","max_runtime_seconds","output_path","receipt_path",
  "schedule_horizon_weeks","schedule_quantiles","schedule_contract_sha256","threads","device")
 miss=[k for k in required if k not in g]
 if miss:raise ValueError("GO missing fields: "+",".join(miss))
 if g["status"]!="APPROVED" or g["allow_fit"] is not True:raise ValueError("GO not approved")
 if g["seed"]!=42 or g["models"]!=["full","independent"]:raise ValueError("seed/model contract mismatch")
 if not 1<=int(g["max_steps_per_model"])<=500:raise ValueError("step cap outside 1..500/model")
 if int(g["batch_size"])<1 or float(g["learning_rate"])<=0:raise ValueError("invalid optimizer settings")
 if int(g["threads"])!=4:raise ValueError("thread count must be 4")
 if g["device"] not in ("cpu","cuda"):raise ValueError("device must be cpu or cuda")
 if int(g["max_runtime_seconds"])>10800:raise ValueError("runtime cap exceeds 3h")
 if g["source_sha256"]!=source_map():raise ValueError("source SHA mismatch")
 if g["code_manifest_sha256"]!=canonical({"source_sha256":g["source_sha256"]}):raise ValueError("code manifest mismatch")
 if g["cohort_sha256"]!=sha(COHORT) or g["manifest_sha256"]!=sha(MANIFEST):raise ValueError("cohort/manifest SHA mismatch")
 if g["schedule_contract_sha256"]!=schedule_contract_hash(g):raise ValueError("train-only schedule contract mismatch")
 issued=datetime.datetime.fromisoformat(str(g["issued_utc"]).replace("Z","+00:00"))
 age=(datetime.datetime.now(datetime.timezone.utc)-issued).total_seconds()
 if age < -60 or age>86400:raise ValueError("GO is stale/future dated")
 out=Path(g["output_path"]);receipt=Path(g["receipt_path"])
 if out.parent!=HERE/"runs" or out.exists():raise ValueError("output must be a fresh child of runs/")
 if receipt.parent!=HERE/"receipts" or receipt.exists():raise ValueError("receipt must be a fresh child of receipts/")
 import sys;sys.path.insert(0,str(OLD))
 from train_eval import validate_owner
 validate_owner(STATE,g["owner_thread_id"])
 if not math.isclose(float(g["schedule_horizon_weeks"]),128.) or int(g["schedule_quantiles"])!=16:
  raise ValueError("schedule contract requires 128 weeks and 16 quantiles")
 if json.loads(Path(path).read_text(encoding="utf-8"))!=g:raise ValueError("GO changed during preflight")
 return out,receipt

def fit_one(name,model,rows,by_cell,seed,steps,batch_size,lr,progress,started,deadline,feature_mean,feature_scale):
 import numpy as np,torch
 from targets import collate_irregular
 device=next(model.parameters()).device
 names=sorted(by_cell);rng=np.random.RandomState(seed+(name=="independent"));losses=[]
 opt=torch.optim.AdamW(model.parameters(),lr=lr)
 for step in range(1,steps+1):
  if time.time()>deadline:raise TimeoutError("approved runtime exhausted during "+name)
  idx=[]
  for _ in range(batch_size):
   cid=names[int(rng.randint(len(names)))];choices=by_cell[cid]
   idx.append(choices[int(rng.randint(len(choices)))])
  x,start,gaps,target,mask,_=collate_irregular(rows,idx)
  xt=(torch.as_tensor(x,dtype=torch.float32,device=device)-feature_mean)/feature_scale;st=torch.as_tensor(start,dtype=torch.float32,device=device)
  gt=torch.as_tensor(gaps,dtype=torch.float32,device=device);yt=torch.as_tensor(target,dtype=torch.float32,device=device)
  mt=torch.as_tensor(mask,dtype=torch.bool,device=device)
  opt.zero_grad(set_to_none=True);loss=model.masked_increment_nll(xt,st,gt,yt,mt)
  if not torch.isfinite(loss):raise FloatingPointError(name+" nonfinite loss at step "+str(step))
  loss.backward()
  if any(p.grad is not None and not torch.isfinite(p.grad).all() for p in model.parameters()):
   raise FloatingPointError(name+" nonfinite gradient at step "+str(step))
  opt.step();losses.append(float(loss.detach()))
  progress["optimizer_steps"]+=1
  progress.update(last_fit=name,last_step=step,last_loss=losses[-1],
                  elapsed_seconds=time.time()-started)
  if step%10==0:atomic(progress["progress_path"],progress)
 return {"steps":steps,"first_loss":losses[0],"last_loss":losses[-1],
         "min_loss":min(losses),"max_loss":max(losses)}

def run(go_path):
 started=time.time();go_path=Path(go_path);receipt=HERE/"preflight_failure.json";out=None;locks=[]
 rec={"status":"PREFLIGHT_FAILED","optimizer_steps":0,"fits_started":0,"fits_completed":0}
 try:
  g=json.loads(go_path.read_text(encoding="utf-8"));out,receipt=validate_go(g,go_path)
  lockpaths=[ROOT/"automation/state/online_survival_cpu.lock",ROOT/"automation/locks/isu_irregular_rul_cpu.lock"]
  if g["device"]=="cuda":lockpaths.append(ROOT/"automation/locks/multisource_mechanisms_20261021_gpu.lock")
  for lp in lockpaths:
   f=lp.open("a+");fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  out.parent.mkdir(parents=True,exist_ok=True)
  out.mkdir(parents=True,exist_ok=False)
  rec.update(status="PREFLIGHT_PASSED",request_id=g["request_id"],go_sha256=sha(go_path),
             source_sha256=source_map(),cohort_sha256=sha(COHORT),manifest_sha256=sha(MANIFEST))
  atomic(out/"receipt.json",rec);deadline=started+int(g["max_runtime_seconds"])
  # No payload is opened until the exact GO and owner/hash checks above pass.
  sys.path[:0]=[str(OLD),str(V18),str(HERE)]
  from train_eval import load_split
  from data_protocol import make_examples
  from targets import build_train_schedule,build_targets,fit_feature_scaler
  from mechanisms import ConditionalCapacityPath,IndependentIncrementAblation
  import numpy as np,torch
  if g.get("device","cpu")=="cuda" and not torch.cuda.is_available():raise RuntimeError("requested CUDA unavailable")
  device=torch.device(g["device"])
  torch.set_num_threads(4)
  cells=load_split(COHORT,DATA,MANIFEST)
  if any(c["role"] not in ("train","development") for c in cells):raise RuntimeError("unexpected role")
  train=[c for c in cells if c["role"]=="train"]
  examples=make_examples(train);rows=build_targets(examples,train)
  rows=[x for x in rows if x["trajectory_gaps_weeks"]]
  by_cell={}
  for i,x in enumerate(rows):
   if x["role"]!="train":raise RuntimeError("nontrain row in fit")
   by_cell.setdefault(x["cell_id"],[]).append(i)
  if len(by_cell)<2:raise RuntimeError("too few train cells with trajectory targets")
  feature_mean,feature_scale=fit_feature_scaler(rows)
  scaler={"mean":feature_mean.tolist(),"scale":feature_scale.tolist(),"fit_rows":len(rows),"feature_key":"x_query","cell_balanced":True}
  (out/"feature_scaler.json").write_text(json.dumps(scaler,indent=2),encoding="utf-8")
  mean_t=torch.as_tensor(feature_mean,dtype=torch.float32,device=device);scale_t=torch.as_tensor(feature_scale,dtype=torch.float32,device=device)
  schedule=build_train_schedule(train,float(g["schedule_horizon_weeks"]),int(g["schedule_quantiles"]))
  (out/"train_only_schedule.json").write_text(json.dumps(schedule,indent=2),encoding="utf-8")
  rec.update(status="TRAINING",train_cells=len(by_cell),train_examples=len(rows),
             schedule_sha256=schedule["sha256"],schedule_contract_sha256=g["schedule_contract_sha256"],
             source_C4_reads=0)
  results={};rec["progress_path"]=str(out/"progress.json");atomic(out/"receipt.json",rec)
  classes=(("full",ConditionalCapacityPath),("independent",IndependentIncrementAblation))
  for name,cls in classes:
   if time.time()>deadline:raise TimeoutError("runtime cap before "+name)
   torch.manual_seed(int(g["seed"])+(name=="independent"));model=cls(feature_dim=74).to(device)
   rec["fits_started"]+=1;atomic(out/"receipt.json",rec)
   results[name]=fit_one(name,model,rows,by_cell,int(g["seed"]),int(g["max_steps_per_model"]),
                         int(g["batch_size"]),float(g["learning_rate"]),rec,started,deadline,mean_t,scale_t)
   torch.save({"state_dict":model.state_dict(),"seed":int(g["seed"]),
               "feature_dim":74,"model":name,"feature_mean":feature_mean.tolist(),
               "feature_scale":feature_scale.tolist()},out/(name+".pt"))
   rec["fits_completed"]+=1;atomic(out/"receipt.json",rec)
  if rec["optimizer_steps"]!=2*int(g["max_steps_per_model"]):
   raise RuntimeError("optimizer step count mismatch")
  rec.update(status="FIT_COMPLETE_NO_DEV_SELECTION",fit_results=results,
             completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
             elapsed_seconds=time.time()-started,locked_payload_reads=0)
 except Exception as exc:
  rec.update(status="FAILED",error=repr(exc),traceback=traceback.format_exc(),elapsed_seconds=time.time()-started)
 finally:
  if out is not None and out.exists():atomic(out/"receipt.json",rec)
  for f in reversed(locks):
   try:fcntl.flock(f,fcntl.LOCK_UN);f.close()
   except Exception:pass
  if receipt.exists():receipt=receipt.with_name(receipt.stem+"_"+str(time.time_ns())+".failure.json")
  receipt.parent.mkdir(parents=True,exist_ok=True)
  with receipt.open("x",encoding="utf-8") as f:json.dump(rec,f,indent=2,allow_nan=True)
 return rec

if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--go",required=True);a=p.parse_args()
 rec=run(a.go);print(json.dumps(rec,indent=2,allow_nan=True))
 raise SystemExit(0 if rec["status"]=="FIT_COMPLETE_NO_DEV_SELECTION" else 2)
