"""GO-gated C3 prediction dump and finite-horizon trajectory/FPT scoring (zero fits)."""
from __future__ import annotations
import argparse,csv,datetime,fcntl,hashlib,json,math,os,sys,time,traceback
from pathlib import Path
import numpy as np
ROOT=Path("/home/yndx/zxk/rul");HERE=Path(__file__).resolve().parent
V1=HERE/"train_v1";OLD=ROOT/"experiments/isu_irregular_rul_seed42_v1"
V18=ROOT/"experiments/dart_rul_v18"
COHORT=ROOT/"reports/isu_ilcc_capacity_probe_20261020_root/cohort.json"
MANIFEST=ROOT/"reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json"
DATA=ROOT/"data/processed/ISU_ILCC_DataV2_v1";STATE=ROOT/"automation/state/coordinator.json"
SOURCES=[HERE/"evaluate_v1.py",V1/"mechanisms.py",V1/"targets.py",V1/"runner.py",
 V18/"protocol.json",V18/"data_protocol.py",OLD/"train_eval.py",OLD/"data_adapter.py",OLD/"baselines.py"]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def source_map():return {str(p.relative_to(ROOT)):sha(p) for p in SOURCES}
def canonical(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def atomic(path,x):
 p=Path(path);tmp=p.with_suffix(p.suffix+".tmp");tmp.write_text(json.dumps(x,indent=2,allow_nan=True),encoding="utf-8");os.replace(tmp,p)
def validate_go(g,path):
 required=("request_id","status","allow_fit","allow_inference","owner_thread_id","issued_utc",
  "source_sha256","code_manifest_sha256","cohort_sha256","manifest_sha256","model_run_path",
  "model_sha256","schedule_sha256","output_path","receipt_path","batch_size","n_paths",
  "max_runtime_seconds","max_inference_batches")
 miss=[x for x in required if x not in g]
 if miss:raise ValueError("GO missing fields: "+",".join(miss))
 if g["status"]!="APPROVED" or g["allow_fit"] is not False or g["allow_inference"] is not True:raise ValueError("evaluation GO must authorize inference only")
 if g["source_sha256"]!=source_map() or g["code_manifest_sha256"]!=canonical({"source_sha256":g["source_sha256"]}):raise ValueError("evaluation code SHA mismatch")
 if g["cohort_sha256"]!=sha(COHORT) or g["manifest_sha256"]!=sha(MANIFEST):raise ValueError("cohort/manifest SHA mismatch")
 from train_eval import validate_owner
 validate_owner(STATE,g["owner_thread_id"])
 run=Path(g["model_run_path"])
 if run.parent!=V1/"runs" or not run.is_dir():raise ValueError("model run path is not a completed V1 run")
 files={"full":run/"full.pt","independent":run/"independent.pt","schedule":run/"train_only_schedule.json","scaler":run/"feature_scaler.json"}
 actual={k:sha(p) for k,p in files.items()}
 if actual!=g["model_sha256"]:raise ValueError("checkpoint/schedule/scaler SHA mismatch")
 if actual["schedule"]!=g["schedule_sha256"]:raise ValueError("schedule SHA mismatch")
 out=Path(g["output_path"]);receipt=Path(g["receipt_path"])
 if out.parent!=HERE/"evaluation_runs" or out.exists():raise ValueError("output must be a fresh evaluation_runs child")
 if receipt.parent!=HERE/"receipts" or receipt.exists():raise ValueError("receipt must be a fresh receipts child")
 if int(g["batch_size"])<1 or int(g["n_paths"])<16 or int(g["max_inference_batches"])<1:raise ValueError("invalid evaluation budget")
 if int(g["max_runtime_seconds"])>10800:raise ValueError("runtime cap exceeds 3h")
 if json.loads(Path(path).read_text(encoding="utf-8"))!=g:raise ValueError("GO changed during preflight")
 return run,out,receipt,files

def load_dev_cells():
 cohort=json.loads(COHORT.read_text());manifest=json.loads(MANIFEST.read_text())
 roles=cohort["roles"]
 dev=[cid for cid,role in roles.items() if role=="development"]
 if len(dev)!=63: raise ValueError("frozen C3 development count changed")
 sys.path.insert(0,str(OLD))
 from data_adapter import load_reviewed_cell
 out=[]
 for cid in dev:
  rec=manifest["files"].get(cid)
  if not rec or rec["role"]!="development":raise ValueError("C3 manifest role mismatch")
  path=DATA/(cid+".json")
  if sha(path)!=rec["sha256"]:raise ValueError("C3 payload hash mismatch "+cid)
  out.append(load_reviewed_cell(path,"development"))
 return out

def trajectory_nll(model,row,mean,scale,device):
 import torch
 x=torch.as_tensor(np.asarray(row["x_query"],float),dtype=torch.float32,device=device)[None,:]
 x=(x-torch.as_tensor(mean,dtype=torch.float32,device=device))/torch.as_tensor(scale,dtype=torch.float32,device=device)
 q=torch.tensor([float(row["visible_records"][-1]["capacityAh"])],dtype=torch.float32,device=device)
 gaps=row["trajectory_gaps_weeks"];targets=row["trajectory_capacity_ah"]
 if not gaps:return float("nan"),0,0
 target=torch.as_tensor(targets,dtype=torch.float32,device=device)
 dt=torch.as_tensor(gaps,dtype=torch.float32,device=device)
 with torch.no_grad():
  if hasattr(model,"cell"):
   h=model.context(x)
   for j in range(len(gaps)):
    h,mu,ls=model.transition(h,q,dt[j:j+1])
    z=(target[j:j+1]-q-mu)/ls.exp()
    q=target[j:j+1]
    term=.5*z.square()+ls+.5*math.log(2*math.pi)
    if j==0:total=term
    else:total=total+term
  else:
   ctx=model.context(x)
   for j in range(len(gaps)):
    mu,ls=model.transition(ctx,q,dt[j:j+1])
    z=(target[j:j+1]-q-mu)/ls.exp();q=target[j:j+1]
    term=.5*z.square()+ls+.5*math.log(2*math.pi)
    if j==0:total=term
    else:total=total+term
 return float(total.item()),len(gaps),len(gaps)

def fpt_summary(sampled,horizon=128.0,threshold=.20):
 import torch
 paths=sampled["capacity"];times=sampled["relative_weeks"];valid=sampled["valid_check"]
 hit=(paths<=threshold)&valid[:,None,:]
 anyhit=hit.any(-1);idx=hit.to(torch.int64).argmax(-1)
 first=times[:,None,:].expand_as(paths).gather(-1,idx[...,None]).squeeze(-1)
 rul=torch.where(anyhit,first.clamp_min(0),torch.full_like(first,float(horizon)))
 tail=(~anyhit).to(paths.dtype).mean(1)
 hidden=sampled["hidden_check"]
 hidden_hit=(hit&hidden[:,None,:]).any(-1)
 current=hidden_hit.to(paths.dtype).mean(1)
 probs={}
 for h in (4.,12.):
  probs[h]=(hit&(times[:,None,:]<=h)).any(-1).to(paths.dtype).mean(1)
 # Probability vector is [current-event atom, (0,1], (1,4], (4,12],
 # (12,32], (32,H], no hit by H]. Negative first-hit times are part of
 # current-event atom, never silently lost from positive-time bins.
 masses=[hidden_hit.to(paths.dtype).float().mean(1)]
 bins=[0.,1.,4.,12.,32.,float(horizon)]
 for lo,hi in zip(bins[:-1],bins[1:]):
  masses.append(((anyhit)&(~hidden_hit)&(first>lo)&(first<=hi)).to(paths.dtype).float().mean(1))
 masses.append(tail)
 mass=torch.stack(masses,1)
 if not torch.allclose(mass.sum(1),torch.ones_like(tail),atol=1e-5,rtol=0):
  raise RuntimeError("FPT probability mass does not sum to one")
 qs=torch.quantile(rul,torch.tensor([.1,.5,.9],device=rul.device,dtype=rul.dtype),dim=1).T
 return current,probs,rul.mean(1),qs,tail,mass

def write_predictions(models,rows,schedule,scaler,out,batch_size,n_paths,max_batches,device,started,max_runtime):
 import torch
 from mechanisms import summarize_first_passage
 mean=np.asarray(scaler["mean"],float);scale=np.asarray(scaler["scale"],float)
 gaps_all=np.asarray(schedule["gaps_weeks"],float)
 interval=float(np.median(schedule["atoms_weeks"]))
 H=float(schedule["horizon_weeks"])
 pred_path=out/"predictions_c3.csv";metric_path=out/"metrics_by_model_arm.csv"
 fields=["model","cell_id","group_id","arm","query_epoch","known_event","y_event","target_rul_weeks",
 "support_current_event","label_current_event","support_4w","label_event_4w","support_12w","label_event_12w",
 "current_event_probability","event_probability_4w","event_probability_12w",
 "rul_restricted_mean_128w","rul_q10_128w","rul_q50_128w","rul_q90_128w","fpt_tail_mass_128w","fpt_current_event_atom","fpt_bin_labels","fpt_bin_masses",
 "next_capacity_mean","next_capacity_sd","next_capacity_target","next_source_elapsed_weeks","next_query_elapsed_weeks",
 "trajectory_nll_sum","trajectory_nll_per_transition","trajectory_steps","trajectory_transition_calls"]
 rows_out=[];inference_batches=0;trajectory_transition_calls=0
 for model_name,model in models.items():
  model.eval()
  for start in range(0,len(rows),batch_size):
   if time.time()-started>max_runtime:raise TimeoutError("evaluation runtime exhausted")
   bi=rows[start:start+batch_size]
   if not bi:continue
   inference_batches+=1
   if inference_batches>max_batches:raise RuntimeError("max inference batch cap exceeded")
   x=np.stack([np.asarray(r["x_query"],float) for r in bi])
   xt=(torch.as_tensor(x,dtype=torch.float32,device=device)-torch.as_tensor(mean,dtype=torch.float32,device=device))/torch.as_tensor(scale,dtype=torch.float32,device=device)
   cap=torch.as_tensor([r["latest_source_capacity_ah"] for r in bi],dtype=torch.float32,device=device)
   hd=torch.as_tensor([r["hidden_delta_weeks"] for r in bi],dtype=torch.float32,device=device)
   future=torch.as_tensor(gaps_all,dtype=torch.float32,device=device)
   with torch.no_grad():
    samp=model.sample(xt,cap,hd,future,interval,n_paths=n_paths)
   # Calendar labels use the exact train-schedule cumulative grid, not float32 GRU clock accumulation.
   exact_times=samp["relative_weeks"].to(torch.float64)
   exact_times[:,-len(gaps_all):]=torch.as_tensor(np.cumsum(gaps_all),dtype=torch.float64,device=device)
   samp["relative_weeks"]=exact_times
   cur,p_h,rm,qs,tail,mass=fpt_summary(samp,H)
   # Source-event closure uses only arrived records.
   for i,r in enumerate(bi):
    if r["known_event"]:
     cur[i]=1.;p_h[4.][i]=1.;p_h[12.][i]=1.;rm[i]=0.;qs[i]=0.;tail[i]=0.
     mass[i]=torch.tensor([1.,0,0,0,0,0,0],device=device)
   nextmeans=[float("nan")]*len(bi);nextstds=[float("nan")]*len(bi)
   has=[i for i,r in enumerate(bi) if r["next_capacity_ah"] is not None]
   if has:
    inference_batches+=1
    if inference_batches>max_batches:raise RuntimeError("max inference batch cap exceeded")
    sub=xt[has];sc=cap[has];sh=hd[has]
    # Evaluation-only horizon from q to the actual next RPT; never a query feature.
    ng=torch.as_tensor([[bi[i]["next_query_elapsed_weeks"]] for i in has],dtype=torch.float32,device=device)
    with torch.no_grad():ns=model.sample(sub,sc,sh,ng,interval,n_paths=n_paths)
    vals=ns["capacity"][:,:,-1]
    for j,i in enumerate(has):nextmeans[i]=float(vals[j].mean());nextstds[i]=float(vals[j].std(unbiased=False))
   for i,r in enumerate(bi):
    nll,nsteps,ncalls=trajectory_nll(model,r,mean,scale,device)
    trajectory_transition_calls+=ncalls
    known=bool(r["known_event"])
    row={"model":model_name,"cell_id":r["cell_id"],"group_id":r["group_id"],"arm":r["arm"],
     "query_epoch":r["query_epoch"],"known_event":known,"y_event":r["y_event"],
     "target_rul_weeks":r["target_rul_weeks"],"support_current_event":r["support_current_event"],
     "label_current_event":r["label_current_event"],"support_4w":r["support_4w"],
     "label_event_4w":r["label_event_4w"],"support_12w":r["support_12w"],
     "label_event_12w":r["label_event_12w"],"current_event_probability":float(cur[i]),
     "event_probability_4w":float(p_h[4.][i]),"event_probability_12w":float(p_h[12.][i]),
     "rul_restricted_mean_128w":float(rm[i]),"rul_q10_128w":float(qs[i,0]),
     "rul_q50_128w":float(qs[i,1]),"rul_q90_128w":float(qs[i,2]),
     "fpt_tail_mass_128w":float(tail[i]),"fpt_current_event_atom":float(mass[i,0]),
     "fpt_bin_labels":"current_event_atom;(0,1w];(1,4w];(4,12w];(12,32w];(32,128w];tail_no_hit_128w",
     "fpt_bin_masses":json.dumps(mass[i].detach().cpu().tolist()),
     "next_capacity_mean":nextmeans[i],"next_capacity_sd":nextstds[i],
     "next_capacity_target":r["next_capacity_ah"],"next_source_elapsed_weeks":r["next_elapsed_weeks"],
     "next_query_elapsed_weeks":r["next_query_elapsed_weeks"],"trajectory_nll_sum":nll,
     "trajectory_nll_per_transition":nll/nsteps if nsteps else float("nan"),"trajectory_steps":nsteps,"trajectory_transition_calls":ncalls}
    rows_out.append(row)
 with pred_path.open("x",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows_out)
 groups={}
 for r in rows_out:
  k=(r["model"],r["arm"]);groups.setdefault(k,[]).append(r)
 metrics=[]
 for (model,arm),rr in sorted(groups.items()):
  supported_current=[x for x in rr if x["support_current_event"] and x["label_current_event"] is not None]
  supported4=[x for x in rr if x["support_4w"] and x["label_event_4w"] is not None]
  supported12=[x for x in rr if x["support_12w"] and x["label_event_12w"] is not None]
  nexts=[x for x in rr if x["next_capacity_target"] is not None and math.isfinite(x["next_capacity_mean"])]
  traj=[x for x in rr if x["trajectory_steps"]>0]
  ev=[x for x in rr if x["target_rul_weeks"] is not None]
  def cell_macro(xs, value_fn):
   by={}
   for x in xs: by.setdefault(x["cell_id"],[]).append(float(value_fn(x)))
   return float(np.mean([np.mean(v) for v in by.values()])) if by else float("nan")
  bc=cell_macro(supported_current,lambda x:(x["current_event_probability"]-float(x["label_current_event"]))**2)
  b4=cell_macro(supported4,lambda x:(x["event_probability_4w"]-float(x["label_event_4w"]))**2)
  b12=cell_macro(supported12,lambda x:(x["event_probability_12w"]-float(x["label_event_12w"]))**2)
  next_mse=cell_macro(nexts,lambda x:(x["next_capacity_mean"]-x["next_capacity_target"])**2)
  traj_per=cell_macro(traj,lambda x:x["trajectory_nll_per_transition"])
  traj_sum=cell_macro(traj,lambda x:x["trajectory_nll_sum"])
  rul_mae=cell_macro(ev,lambda x:abs(x["rul_restricted_mean_128w"]-min(float(x["target_rul_weeks"]),H)))
  tail_mean=cell_macro(rr,lambda x:x["fpt_tail_mass_128w"])
  metrics.append({"model":model,"arm":arm,"n_queries":len(rr),"n_cells":len(set(x["cell_id"] for x in rr)),
   "aggregation":"cell_equal_macro; query_equal_within_cell",
   "current_event_brier_supported":bc,"n_current_event_support":len(supported_current),
   "event_brier_4w_supported":b4,"n_event_support_4w":len(supported4),
   "event_brier_12w_supported":b12,"n_event_support_12w":len(supported12),
   "next_RPT_RMSE_Ah":math.sqrt(next_mse) if math.isfinite(next_mse) else float("nan"),
   "next_RPT_n":len(nexts),"trajectory_NLL_per_transition":traj_per,
   "trajectory_NLL_sum_per_query":traj_sum,"trajectory_n":len(traj),
   "trajectory_transition_calls":sum(int(x["trajectory_transition_calls"]) for x in traj),
   "known_event_restricted_RUL_MAE_weeks":rul_mae,"known_event_RUL_n":len(ev),
   "mean_predicted_fpt_tail_mass":tail_mean})
 with metric_path.open("x",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=list(metrics[0]));w.writeheader();w.writerows(metrics)
 return {"prediction_rows":len(rows_out),"predictions":str(pred_path),"metrics":str(metric_path),"metric_rows":metrics,"inference_batches":inference_batches,"trajectory_transition_calls":trajectory_transition_calls}

def run(go_path):
 started=time.time();receipt=HERE/"preflight_eval_failure.json";out=None;locks=[]
 rec={"status":"PREFLIGHT_FAILED","fit_count":0,"inference_batches":0,"locked_payload_reads":0}
 try:
  go=json.loads(Path(go_path).read_text(encoding="utf-8"))
  sys.path[:0]=[str(OLD),str(V18),str(V1),str(HERE)]
  runpath,out,receipt,files=validate_go(go,go_path)
  if go.get("device","cpu") not in ("cpu","cuda"): raise ValueError("device must be cpu or cuda")
  lockpaths=[ROOT/"automation/state/online_survival_cpu.lock",ROOT/"automation/locks/isu_irregular_rul_cpu.lock"]
  if go.get("device","cpu")=="cuda": lockpaths.append(ROOT/"automation/locks/multisource_mechanisms_20261021_gpu.lock")
  for lp in lockpaths:
   f=lp.open("a+");fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  out.parent.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=False)
  rec.update(status="PREFLIGHT_PASSED",request_id=go["request_id"],go_sha256=sha(go_path),source_sha256=source_map())
  atomic(out/"receipt.json",rec)
  if go.get("device","cpu")=="cuda" and not __import__("torch").cuda.is_available():raise RuntimeError("CUDA requested but unavailable")
  import torch
  torch.set_num_threads(4);torch.manual_seed(42)
  if go.get("device","cpu")=="cuda":torch.cuda.manual_seed_all(42)
  device=torch.device(go.get("device","cpu"))
  cohort=json.loads(COHORT.read_text(encoding="utf-8"));manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
  cells=load_dev_cells()
  if any(c["role"]!="development" for c in cells):raise RuntimeError("non-C3 cell loaded")
  from data_protocol import make_examples
  from targets import build_targets
  from mechanisms import ConditionalCapacityPath,IndependentIncrementAblation
  examples=make_examples(cells);rows=build_targets(examples,cells)
  cell_by={str(c["cell_id"]):c for c in cells}
  for r in rows:
   c=cell_by[str(r["cell_id"])];q=float(r["query_epoch"])
   ev=c.get("source_observed_event_stop_epoch")
   covered=bool(c["records"] and max(float(z["stop_epoch"]) for z in c["records"])>=q-1e-5)
   r["support_current_event"]=bool(covered or (ev is not None and float(ev)<=q+1e-5))
   r["label_current_event"]=None if not r["support_current_event"] else bool(ev is not None and float(ev)<=q+1e-5)
  if any(r["role"]!="development" for r in rows):raise RuntimeError("non-C3 eval row")
  schedule=json.loads(files["schedule"].read_text(encoding="utf-8"))
  scaler=json.loads(files["scaler"].read_text(encoding="utf-8"))
  models={}
  for name,cls in (("full",ConditionalCapacityPath),("independent",IndependentIncrementAblation)):
   ck=torch.load(files[name],map_location=device,weights_only=False)
   model=cls(feature_dim=74).to(device);model.load_state_dict(ck["state_dict"]);model.eval()
   if ck["feature_mean"]!=scaler["mean"] or ck["feature_scale"]!=scaler["scale"]:raise RuntimeError("checkpoint/scaler mismatch")
   models[name]=model
  result=write_predictions(models,rows,schedule,scaler,out,int(go["batch_size"]),int(go["n_paths"]),
                           int(go["max_inference_batches"]),device,started,int(go["max_runtime_seconds"]))
  rec.update(status="EVALUATION_COMPLETE_NO_FIT",prediction_rows=result["prediction_rows"],
    prediction_file=result["predictions"],metrics_file=result["metrics"],metric_rows=result["metric_rows"],
    model_sha256=go["model_sha256"],schedule_sha256=go["schedule_sha256"],
    c3_cells=len(cells),locked_payload_reads=0,elapsed_seconds=time.time()-started,
    inference_batches=result["inference_batches"],trajectory_transition_calls=result["trajectory_transition_calls"])
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
 r=run(a.go);print(json.dumps(r,indent=2,allow_nan=True))
 raise SystemExit(0 if r["status"]=="EVALUATION_COMPLETE_NO_FIT" else 2)
