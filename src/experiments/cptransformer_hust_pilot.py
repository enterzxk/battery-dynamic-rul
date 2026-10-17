#!/usr/bin/env python3
"""Safe BatteryLife CPTransformer HUST pilot runner.

Default command only does a real-data CPU/no-grad preflight. Fit additionally requires
--fit --authorize-fit and a frozen, authorized config. Test files are never loaded.
"""
import argparse, csv, hashlib, json, math, os, pickle, random, sys, time, fcntl, datetime
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch
from torch.utils.data import DataLoader

ROOT=Path("/home/yndx/zxk/rul")
CODE=ROOT/"repos/pinned/BatteryLife_3b17bb53202e10711deae0448c91f84144bb3dd9"
STAGE=ROOT/"data/source_audit/stage_v11_hust_v11_labels"
STAGE_MANIFEST=STAGE/"stage_manifest.json"
CONFIG=ROOT/"configs/experiments/cptransformer_hust_pilot_seed42_v1.json"
EXP=ROOT/"experiments/cptransformer_hust_pilot_seed42"
def sha_file(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for b in iter(lambda:f.read(8*1024*1024),b""): h.update(b)
 return h.hexdigest()
def digest_obj(obj):
 return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def now():
 return datetime.datetime.now(datetime.timezone.utc).isoformat()
def load_config():
 c=json.loads(CONFIG.read_text())
 if c["training_semantics"]!="official_total_eol": raise RuntimeError("This runner only supports official total EOL")
 if c["dataset"]!="HUST" or c["release"]!="v11": raise RuntimeError("Unexpected source")
 for key in ["seq_len","charge_discharge_length","early_cycle_threshold","d_model","d_ff","e_layers","d_layers","dropout","n_heads","factor","activation","output_num"]:
  c[key]=c["model"][key]
 c["batch_size"]=c.get("fit_budget",c.get("fit_budget_proposal"))["batch_size"]
 return c
def source_manifest():
 m=json.loads(STAGE_MANIFEST.read_text())
 if m["record_id"]!=19688272: raise RuntimeError("Unexpected Zenodo record")
 return m
def make_trainval_view(cfg, manifest):
 """Create-only view excludes test PKLs and test labels, while retaining source hashes."""
 target=ROOT/"experiments/cpmlp_hust_pilot_seed42/input_trainval"
 hdir=target/"HUST"; ldir=target/"Life labels"
 if target.exists():
  prior=target/"view_manifest.json"
  if not prior.is_file(): raise RuntimeError("existing input view is incomplete; preserve and inspect")
  existing=json.loads(prior.read_text())
  if existing.get("source_stage_manifest_sha256")!=sha_file(STAGE_MANIFEST): raise RuntimeError("existing input view source mismatch")
  if existing.get("test_pkls_present") is not False: raise RuntimeError("existing view has test files")
  expected_names=set(cfg["split_files"]["train"]+cfg["split_files"]["val"])
  actual_names={p.name for p in hdir.iterdir()}
  if actual_names!=expected_names: raise RuntimeError("existing HUST view file set differs from exact train/val split")
  if actual_names & set(cfg["split_files"]["test"]): raise RuntimeError("test PKLs present in existing view")
  labels_out=ldir/"HUST_labels.json"
  if not labels_out.is_file() or sha_file(labels_out)!=existing.get("trainval_label_sha256"):
   raise RuntimeError("existing train/val labels SHA mismatch")
  parsed=json.loads(labels_out.read_text())
  if set(parsed)!=expected_names or set(parsed)&set(cfg["split_files"]["test"]):
   raise RuntimeError("existing train/val label keys differ from exact split")
  if existing.get("trainval_label_keys")!=sorted(expected_names):
   raise RuntimeError("view manifest train/val label list mismatch")
  if {rec.get("name") for rec in existing.get("hust_files",[])}!=expected_names:
   raise RuntimeError("view manifest does not enumerate exact train/val HUST files")
  for rec in existing.get("hust_files",[]):
   fp=Path(rec["view_path"])
   if fp.name not in expected_names or not fp.is_symlink() or os.readlink(fp)!=rec.get("symlink_target"):
    raise RuntimeError("existing HUST view link mismatch")
   if sha_file(fp)!=rec.get("source_sha256"): raise RuntimeError("existing HUST source hash mismatch")
  return existing
 raise RuntimeError("CPTransformer must reuse the existing audited CPMLP train/val view; view creation is disabled")
 target.mkdir(parents=True)
 hdir.mkdir(); ldir.mkdir()
 split=cfg["split_files"]
 allowed=set(split["train"]+split["val"])
 if set(split["train"])&set(split["val"]) or set(split["train"])&set(split["test"]) or set(split["val"])&set(split["test"]):
  raise RuntimeError("split overlap")
 if allowed & set(split["test"]): raise RuntimeError("test contamination")
 byname={Path(x["path"]).name:x for x in manifest["hust_files"]}
 if allowed-set(byname): raise RuntimeError("Missing train/val files from stage")
 for name in sorted(allowed):
  rec=byname[name]
  path=Path(rec["path"])
  if sha_file(path)!=rec["sha256"]: raise RuntimeError("stage SHA mismatch:"+name)
  os.symlink(path,hdir/name)
 labels_path=Path(manifest["label_file"]["path"])
 if sha_file(labels_path)!=manifest["label_file"]["sha256"]: raise RuntimeError("label source SHA mismatch")
 labels=json.loads(labels_path.read_text())
 trainval_labels={k:v for k,v in labels.items() if k in allowed}
 if set(trainval_labels)!=allowed: raise RuntimeError("labels missing train/val file")
 out_label=ldir/"HUST_labels.json"
 with open(out_label,"x",encoding="utf-8") as f: json.dump(trainval_labels,f,ensure_ascii=False,indent=2); f.write("\n")
 view={"created_utc":now(),"root":str(target),"dataset":"HUST","record_id":19688272,"source_label_sha256":sha_file(labels_path),"trainval_label_sha256":sha_file(out_label),"trainval_label_keys":sorted(trainval_labels),"omitted_test_label_keys":sorted(set(labels)-allowed),"hust_files":[{"name":n,"view_path":str(hdir/n),"symlink_target":os.readlink(hdir/n),"source_sha256":byname[n]["sha256"]} for n in sorted(allowed)],"source_stage_manifest_sha256":sha_file(STAGE_MANIFEST),"test_pkls_present":False}
 with open(target/"view_manifest.json","x") as f: json.dump(view,f,ensure_ascii=False,indent=2); f.write("\n")
 return view
class DenyAllUnpickler(pickle.Unpickler):
 def find_class(self,module,name): raise pickle.UnpicklingError("BLOCKED_GLOBAL:%s.%s"%(module,name))
 def persistent_load(self,pid): raise pickle.UnpicklingError("BLOCKED_PERSISTENT_ID")
class RestrictedPickleFacade:
 """Only exact train/val files are readable; hash checked before restricted decode."""
 def __init__(self, allowed_hashes):
  self.allowed_hashes=allowed_hashes
  self.reads=[]
 def load(self, fileobj):
  name=os.path.abspath(fileobj.name)
  expected=self.allowed_hashes.get(name)
  if expected is None: raise PermissionError("PKL path outside train/val allowlist:"+name)
  fileobj.seek(0)
  h=hashlib.sha256()
  for b in iter(lambda:fileobj.read(8*1024*1024),b""): h.update(b)
  got=h.hexdigest()
  if got!=expected: raise RuntimeError("PKL SHA mismatch:"+name)
  fileobj.seek(0)
  obj=DenyAllUnpickler(fileobj).load()
  # Check pure primitives without invoking object methods.
  todo=[obj]
  while todo:
   v=todo.pop()
   if isinstance(v,(str,bytes,int,float,bool,type(None))): continue
   if isinstance(v,dict):
    for k,x in v.items():
     if not isinstance(k,(str,int,float,bool,bytes,type(None))): raise TypeError("nonprimitive dict key")
     todo.append(x)
   elif isinstance(v,(list,tuple,set,frozenset)): todo.extend(v)
   else: raise TypeError("nonprimitive value:"+type(v).__name__)
  self.reads.append({"path":name,"sha256":got})
  return obj
def install_safe_pickle(dataset_loader, view):
 allowed={os.path.abspath(x["view_path"]):x["source_sha256"] for x in view["hust_files"]}
 dataset_loader.pickle=RestrictedPickleFacade(allowed)
 return dataset_loader.pickle
def make_dataset_args(root,cfg):
 return SimpleNamespace(root_path=str(root),dataset="HUST",seq_len=cfg["seq_len"],
   charge_discharge_length=cfg["charge_discharge_length"],early_cycle_threshold=cfg["early_cycle_threshold"],
   weighted_loss=False)
def tracked_dataset_class(dataset_loader):
 """Record per-cell prefix counts without modifying the pinned source file."""
 cls=dataset_loader.Dataset_original
 original=cls.read_samples_from_one_cell
 def wrapped(self,file_name):
  result=original(self,file_name)
  if not hasattr(self,"_audit_cell_counts"): self._audit_cell_counts=[]
  count=len(result[0]) if result[0] is not None else 0
  self._audit_cell_counts.append({"file_name":file_name,"prefix_count":count})
  return result
 cls.read_samples_from_one_cell=wrapped
 return original
def mask_collate(dataset_loader):
 return dataset_loader.my_collate_fn_baseline
def compute_val_predictions(dataset, loader, model, scaler, device):
 model.eval(); rows=[]; offset=0
 counts=dataset._audit_cell_counts
 if sum(x["prefix_count"] for x in counts)!=len(dataset): raise RuntimeError("cell prefix accounting mismatch")
 with torch.no_grad():
  for batch in loader:
   x,mask,y,life_class,scaled_life,weights,seen=batch
   pred=model(x.to(device),mask.to(device)).detach().cpu().numpy().reshape(-1)
   raw_y=scaler.inverse_transform(y.numpy().reshape(-1,1)).reshape(-1)
   raw_pred=scaler.inverse_transform(pred.reshape(-1,1)).reshape(-1)
   if len(pred)!=len(raw_y): raise RuntimeError("prediction target mismatch")
   for yp,pp in zip(raw_y,raw_pred):
    rows.append((float(yp),float(pp)))
   offset+=len(pred)
 if offset!=len(dataset): raise RuntimeError("validation inference count mismatch")
 out=[]; pos=0
 for cell in counts:
  for j in range(cell["prefix_count"]):
   y,p=rows[pos]; pos+=1
   out.append({"file_name":cell["file_name"],"prefix_index":j+1,"label_total_life_cycles":y,"prediction_total_life_cycles":p,"absolute_error_cycles":abs(p-y),"absolute_percentage_error":abs(p-y)/abs(y) if y else None})
 return out
def metrics(predictions):
 by={}
 for r in predictions: by.setdefault(r["file_name"],[]).append(r)
 cell_metrics=[]
 for name,rs in sorted(by.items()):
  cell_metrics.append({"file_name":name,"prefixes":len(rs),"mae_cycles":float(np.mean([x["absolute_error_cycles"] for x in rs])),"mape":float(np.mean([x["absolute_percentage_error"] for x in rs if x["absolute_percentage_error"] is not None]))})
 return {"cell_count":len(cell_metrics),"prefix_count":len(predictions),"prefix_mean_mae_cycles":float(np.mean([r["absolute_error_cycles"] for r in predictions])) if predictions else None,"prefix_mean_mape":float(np.mean([r["absolute_percentage_error"] for r in predictions if r["absolute_percentage_error"] is not None])) if predictions else None,"cell_equal_mae_cycles":float(np.mean([x["mae_cycles"] for x in cell_metrics])) if cell_metrics else None,"cell_equal_mape":float(np.mean([x["mape"] for x in cell_metrics])) if cell_metrics else None,"per_cell":cell_metrics}
def append_jsonl(path, record):
 with open(path,"a",encoding="utf-8") as f: f.write(json.dumps(record,ensure_ascii=False)+"\n"); f.flush(); os.fsync(f.fileno())
def write_prediction_csv(path, rows):
 with open(path,"x",newline="",encoding="utf-8") as f:
  fields=list(rows[0].keys()) if rows else ["file_name","prefix_index","label_total_life_cycles","prediction_total_life_cycles","absolute_error_cycles","absolute_percentage_error"]
  w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
def run_fit(cfg, train, val, train_loader, val_loader, model, lock_handle, resume_dir=None):
 budget=cfg["fit_budget"]
 source_sha=sha_file(STAGE_MANIFEST); config_sha=sha_file(CONFIG); view_sha=sha_file(ROOT/"experiments/cpmlp_hust_pilot_seed42/input_trainval/view_manifest.json")
 runs=EXP/"fit_runs"; runs.mkdir(exist_ok=True)
 if resume_dir:
  run_dir=Path(resume_dir).resolve()
  if run_dir.parent!=runs.resolve() or not run_dir.is_dir(): raise RuntimeError("resume_dir must be an existing direct child of fit_runs")
  rm=json.loads((run_dir/"run_manifest.json").read_text())
  run_manifest=rm
  if (run_dir/"completion_receipt.json").exists(): raise RuntimeError("completed run cannot be resumed")
  expected={"config_sha256":config_sha,"stage_manifest_sha256":source_sha,"view_manifest_sha256":view_sha,"repository_commit":cfg["repository_commit"],"seed":cfg["seed"],"runner_sha256":sha_file(Path(__file__).resolve()),"pinned_model_sha256":sha_file(CODE/"models/CPTransformer.py"),"pinned_loader_sha256":sha_file(CODE/"data_provider/data_loader.py")}
  if any(rm.get(k)!=v for k,v in expected.items()): raise RuntimeError("resume manifest hash/source mismatch")
  cps=sorted(run_dir.glob("checkpoint_epoch_*.pt"))
  if not cps: raise RuntimeError("resume requires an epoch checkpoint")
  resume_checkpoint=cps[-1]
  append_jsonl(run_dir/"budget_ledger.jsonl",{"time_utc":now(),"event":"resume_requested","checkpoint":resume_checkpoint.name,"checkpoint_sha256":sha_file(resume_checkpoint)})
 else:
  run_id="fit_"+datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
  run_dir=runs/run_id; run_dir.mkdir(exist_ok=False)
  run_manifest={"created_utc":now(),"state":"FIT_RUNNING","protocol_id":cfg["protocol_id"],"config_sha256":config_sha,"stage_manifest_sha256":source_sha,"view_manifest_sha256":view_sha,"repository_commit":cfg["repository_commit"],"runner_sha256":sha_file(Path(__file__).resolve()),"pinned_model_sha256":sha_file(CODE/"models/CPTransformer.py"),"pinned_loader_sha256":sha_file(CODE/"data_provider/data_loader.py"),"versions":{"python":sys.version.split()[0],"torch":torch.__version__,"numpy":np.__version__,"scipy":__import__("scipy").__version__,"scikit_learn":__import__("sklearn").__version__},"model":"CPTransformer","training_semantics":"official_total_eol","dataset":"HUST_v11","train_cells":sorted(train.files),"validation_cells":sorted(val.files),"test_files_loaded":[],"test_inference":False,"seed":cfg["seed"],"budget":budget,"fit_authorization_argument":True}
  with open(run_dir/"run_manifest.json","x",encoding="utf-8") as f: json.dump(run_manifest,f,ensure_ascii=False,indent=2); f.write("\n")
  append_jsonl(run_dir/"budget_ledger.jsonl",{"time_utc":now(),"event":"fit_started","budget":budget,"test_access":"locked"})
  resume_checkpoint=None
 ledger=run_dir/"budget_ledger.jsonl"
 device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
 model=model.to(device)
 optimizer=torch.optim.Adam(model.parameters(),lr=budget["learning_rate"],betas=tuple(budget["optimizer_args"]["betas"]),eps=budget["optimizer_args"]["eps"],weight_decay=budget["optimizer_args"]["weight_decay"])
 train_unique=np.asarray(train.unique_labels,dtype=float)
 train_median=float(np.median(train_unique))
 best_val_mape=float("inf"); best_epoch=None; step=0; start=time.monotonic(); elapsed_before=0.0; start_epoch=1; final_state="FIT_COMPLETED"
 def elapsed_now(): return elapsed_before+(time.monotonic()-start)
 if resume_checkpoint is not None:
  state=torch.load(resume_checkpoint,map_location="cpu",weights_only=True)
  with open(ledger,encoding="utf-8") as lf:
   step_events=[json.loads(line) for line in lf if line.strip() and json.loads(line).get("event")=="optimizer_step"]
  cp_step=int(state["optimizer_steps_total"])
  if any(int(rec["optimizer_step"])>cp_step for rec in step_events):
   raise RuntimeError("ledger has optimizer steps newer than epoch checkpoint; conservative resume refused")
  for key,value in {"config_sha256":config_sha,"stage_manifest_sha256":source_sha,"view_manifest_sha256":view_sha,"repository_commit":cfg["repository_commit"],"seed":cfg["seed"]}.items():
   if state.get(key)!=value: raise RuntimeError("checkpoint source mismatch: "+key)
  model.load_state_dict(state["model_state_dict"]); optimizer.load_state_dict(state["optimizer_state_dict"])
  start_epoch=int(state["epoch"])+1; step=int(state["optimizer_steps_total"]); best_epoch=state["best_epoch"]; best_val_mape=float(state["best_val_prefix_mean_mape"]); elapsed_before=float(state["elapsed_total_seconds"])
  if step>=budget["max_optimizer_steps"] or elapsed_before>=budget["max_wall_seconds"] or start_epoch>budget["max_epochs"]:
   raise RuntimeError("resume checkpoint already exhausted configured budget")
  py_state=state["rng_python_state"]
  random.setstate(tuple(py_state))
  ns=state["rng_numpy_state"]
  np.random.set_state((ns[0],np.asarray(ns[1],dtype=np.uint32),int(ns[2]),int(ns[3]),float(ns[4])))
  torch.set_rng_state(state["rng_torch_cpu_state"])
  if torch.cuda.is_available() and state.get("rng_torch_cuda_states") is not None:
   torch.cuda.set_rng_state_all(state["rng_torch_cuda_states"])
 log_path=run_dir/"epoch_metrics.jsonl"
 for epoch in range(start_epoch,budget["max_epochs"]+1):
  model.train(); total_loss=0.; batches=0; stopped=False
  for batch in train_loader:
   if step>=budget["max_optimizer_steps"] or elapsed_now()>=budget["max_wall_seconds"]:
    stopped=True; break
   x,mask,y,life_class,scaled_life,weights,seen=batch
   x=x.to(device); mask=mask.to(device); y=y.to(device).reshape(-1,1); weights=weights.to(device).reshape(-1,1)
   optimizer.zero_grad(set_to_none=True)
   pred=model(x,mask)
   loss=(torch.nn.functional.mse_loss(pred,y,reduction="none")*weights).mean()
   if not torch.isfinite(loss): raise RuntimeError("nonfinite training loss")
   loss.backward(); optimizer.step()
   step+=1
   append_jsonl(ledger,{"time_utc":now(),"event":"optimizer_step","optimizer_step":step,"epoch":epoch,"batch_loss_scaled_mse":float(loss.detach().cpu()),"elapsed_total_seconds":elapsed_now()})
   total_loss+=float(loss.detach().cpu()); batches+=1
  if batches==0:
   final_state="BUDGET_EXHAUSTED_NO_EPOCH"
   append_jsonl(ledger,{"time_utc":now(),"event":"budget_exhausted","epoch":epoch,"optimizer_steps":step})
   break
  val_predictions=compute_val_predictions(val,val_loader,model,val.return_label_scaler(),device)
  val_metrics=metrics(val_predictions)
  baseline=[dict(r,prediction_total_life_cycles=train_median,absolute_error_cycles=abs(train_median-r["label_total_life_cycles"]),absolute_percentage_error=abs(train_median-r["label_total_life_cycles"])/abs(r["label_total_life_cycles"])) for r in val_predictions]
  val_mape=val_metrics["prefix_mean_mape"]
  is_best=val_mape is not None and val_mape<best_val_mape
  if is_best: best_val_mape=val_mape; best_epoch=epoch
  write_prediction_csv(run_dir/("val_predictions_epoch_%03d.csv"%epoch),val_predictions)
  write_prediction_csv(run_dir/("train_median_val_predictions_epoch_%03d.csv"%epoch),baseline)
  record={"time_utc":now(),"epoch":epoch,"optimizer_steps_total":step,"train_loss_scaled_mse":total_loss/max(1,batches),"train_batches":batches,"validation_metrics_native_cycles":val_metrics,"validation_selection_metric":"prefix_mean_mape","validation_prefix_mean_mape":val_mape,"best_epoch":best_epoch,"best_val_prefix_mean_mape":best_val_mape,"train_only_median_eol_cycles":train_median,"train_median_validation_metrics":metrics(baseline),"checkpoint_file":"checkpoint_epoch_%03d.pt"%epoch,"test_metrics":None,"test_inference":False}
  append_jsonl(log_path,record)
  checkpoint={"model_state_dict":model.state_dict(),"optimizer_state_dict":optimizer.state_dict(),"epoch":epoch,"optimizer_steps_total":step,"best_epoch":best_epoch,"best_val_prefix_mean_mape":best_val_mape,"elapsed_total_seconds":elapsed_now(),"config_sha256":config_sha,"stage_manifest_sha256":source_sha,"view_manifest_sha256":view_sha,"repository_commit":cfg["repository_commit"],"seed":cfg["seed"],"rng_python_state":random.getstate(),"rng_numpy_state":[np.random.get_state()[0],np.random.get_state()[1].tolist(),int(np.random.get_state()[2]),int(np.random.get_state()[3]),float(np.random.get_state()[4])],"rng_torch_cpu_state":torch.get_rng_state(),"rng_torch_cuda_states":torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None}
  cp=run_dir/record["checkpoint_file"]
  if cp.exists(): raise RuntimeError("checkpoint already exists; refusing overwrite")
  tmp=run_dir/(cp.name+".tmp")
  with open(tmp,"xb") as f: torch.save(checkpoint,f); f.flush(); os.fsync(f.fileno())
  os.replace(tmp,cp)
  append_jsonl(ledger,{"time_utc":now(),"event":"epoch_checkpoint_saved","epoch":epoch,"optimizer_steps_total":step,"checkpoint_sha256":sha_file(cp),"elapsed_total_seconds":elapsed_now()})
  if stopped:
   final_state="BUDGET_EXHAUSTED_AFTER_PARTIAL_EPOCH"
   break
  if step>=budget["max_optimizer_steps"]:
   final_state="STEP_BUDGET_EXHAUSTED"; break
  if elapsed_now()>=budget["max_wall_seconds"]:
   final_state="TIME_BUDGET_EXHAUSTED"; break
 run_manifest["state"]=final_state
 run_manifest["completed_utc"]=now()
 run_manifest["optimizer_steps"]=step
 run_manifest["elapsed_total_seconds"]=elapsed_now()
 run_manifest["best_epoch_selected_by_validation_prefix_mape"]=best_epoch
 run_manifest["best_validation_prefix_mape"]=best_val_mape if best_epoch is not None else None
 # Manifest is append-only by writing a separate completion receipt.
 with open(run_dir/"completion_receipt.json","x",encoding="utf-8") as f: json.dump(run_manifest,f,ensure_ascii=False,indent=2); f.write("\n")
 append_jsonl(ledger,{"time_utc":now(),"event":"fit_finished","state":final_state,"optimizer_steps":step,"best_epoch":best_epoch,"test_inference":False})
 print(json.dumps({"state":final_state,"run_dir":str(run_dir),"optimizer_steps":step,"best_epoch":best_epoch,"best_validation_prefix_mape":best_val_mape if best_epoch is not None else None,"test_inference":False},ensure_ascii=False,indent=2))

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--preflight-only",action="store_true")
 ap.add_argument("--fit",action="store_true")
 ap.add_argument("--authorize-fit",action="store_true")
 ap.add_argument("--resume-dir",default=None)
 args=ap.parse_args()
 if args.fit and args.preflight_only: raise SystemExit("--fit and --preflight-only are mutually exclusive")
 if args.resume_dir and not args.fit: raise SystemExit("--resume-dir requires --fit")
 if not args.fit and not args.preflight_only: args.preflight_only=True
 if args.fit and not args.authorize_fit: raise SystemExit("Fit requires explicit --authorize-fit after root review")
 cfg=load_config()
 if args.fit and (cfg.get("status")!="FROZEN_PILOT" or cfg.get("training_authorized") is not True): raise SystemExit("Fit blocked: config is still DRAFT/unauthorized; root must freeze and authorize it first")
 manifest=source_manifest()
 lock_handle=None
 if args.fit:
  lock_path=ROOT/"automation/locks/cpmlp_hust_pilot_gpu.lock"
  lock_path.parent.mkdir(parents=True,exist_ok=True)
  lock_handle=open(lock_path,"a+")
  try: fcntl.flock(lock_handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError: raise SystemExit("GPU/project lock is held; refusing fit")
 EXP.mkdir(parents=True,exist_ok=True)
 view=make_trainval_view(cfg,manifest)
 if sha_file(STAGE_MANIFEST)!=cfg["stage_manifest_sha256"]: raise RuntimeError("Frozen stage manifest mismatch")
 if sha_file(ROOT/"experiments/cpmlp_hust_pilot_seed42/input_trainval/view_manifest.json")!=cfg["source_view_manifest_sha256"]: raise RuntimeError("Frozen input view mismatch")
 sys.path.insert(0,str(CODE))
 os.chdir(CODE)
 import data_provider.data_loader as dl
 restricted=install_safe_pickle(dl,view)
 original=tracked_dataset_class(dl)
 torch.set_num_threads(2)
 random.seed(cfg["seed"]); np.random.seed(cfg["seed"]); torch.manual_seed(cfg["seed"])
 datargs=make_dataset_args(ROOT/"experiments/cpmlp_hust_pilot_seed42/input_trainval",cfg)
 # Assert lists directly from pinned split recorder before any dataset reads.
 tr_expected=set(cfg["split_files"]["train"]); va_expected=set(cfg["split_files"]["val"]); te_expected=set(cfg["split_files"]["test"])
 if tr_expected&va_expected or tr_expected&te_expected or va_expected&te_expected: raise RuntimeError("split not disjoint")
 train=dl.Dataset_original(args=datargs,flag="train")
 if set(train.files)!=tr_expected: raise RuntimeError("unexpected train file list")
 val=dl.Dataset_original(args=datargs,flag="val",label_scaler=train.return_label_scaler(),life_class_scaler=train.return_life_class_scaler())
 if set(val.files)!=va_expected: raise RuntimeError("unexpected val file list")
 if train.return_label_scaler() is not val.return_label_scaler(): raise RuntimeError("validation scaler not shared")
 if (set(train.files)|set(val.files)) & te_expected: raise RuntimeError("test path in datasets")
 if any(Path(x["path"]).name not in (tr_expected|va_expected) for x in restricted.reads): raise RuntimeError("test file read")
 train_loader=DataLoader(train,batch_size=cfg["batch_size"],shuffle=bool(args.fit),drop_last=bool(args.fit),collate_fn=mask_collate(dl),num_workers=0)
 val_loader=DataLoader(val,batch_size=cfg["batch_size"],shuffle=False,drop_last=False,collate_fn=mask_collate(dl),num_workers=0)
 batch=next(iter(train_loader))
 # x:[B,100,3,300]；mask:[B,100]；不可见循环由collate置零。
 x,mask,y,life_class,scaled_life,weights,seen=batch
 from models.CPTransformer import Model
 model_cfg=SimpleNamespace(d_ff=cfg["d_ff"],d_model=cfg["d_model"],charge_discharge_length=cfg["charge_discharge_length"],early_cycle_threshold=cfg["early_cycle_threshold"],dropout=cfg["dropout"],e_layers=cfg["e_layers"],d_layers=cfg["d_layers"],n_heads=cfg["n_heads"],factor=cfg["factor"],activation=cfg["activation"],output_num=cfg["output_num"])
 model=Model(model_cfg).eval()
 device=torch.device("cpu")
 with torch.no_grad(): out=model(x.to(device),mask.to(device))
 if list(x.shape)[2:]!=[3,cfg["charge_discharge_length"]]: raise RuntimeError("actual Dataset channel/time order mismatch")
 if tuple(out.shape)!=(x.shape[0],1): raise RuntimeError("CPTransformer shape mismatch")
 if args.fit:
  return run_fit(cfg,train,val,train_loader,val_loader,model,lock_handle,args.resume_dir)
 predictions=compute_val_predictions(val,val_loader,model,val.return_label_scaler(),device)
 # One training-only median EOL reference per held-out val cell/prefix.
 train_median=float(np.median(np.asarray(train.unique_labels,dtype=float)))
 baseline=[dict(r,prediction_total_life_cycles=train_median,absolute_error_cycles=abs(train_median-r["label_total_life_cycles"]),absolute_percentage_error=abs(train_median-r["label_total_life_cycles"])/abs(r["label_total_life_cycles"])) for r in predictions]
 result={"created_utc":now(),"status":"REAL_DATA_PREFLIGHT_PASS_NO_FIT","repository_commit":cfg["repository_commit"],"config_sha256":sha_file(CONFIG),"stage_manifest_sha256":sha_file(STAGE_MANIFEST),"view_manifest_sha256":sha_file(ROOT/"experiments/cpmlp_hust_pilot_seed42/input_trainval/view_manifest.json"),"train_files":sorted(train.files),"val_files":sorted(val.files),"test_files_loaded":[],"train_cell_prefix_counts":train._audit_cell_counts,"val_cell_prefix_counts":val._audit_cell_counts,"pickle_reads":restricted.reads,"restricted_unpickle":"find_class and persistent_load always reject; SHA checked before each load; allowlist train/val only","dataset_lengths":{"train_prefix_samples":len(train),"val_prefix_samples":len(val)},"actual_batch":{"cycle_curve_data_shape":list(x.shape),"curve_attn_mask_shape":list(mask.shape),"target_shape":list(y.shape),"weights_shape":list(weights.shape),"tensor_order":"[batch,early_cycle,channel=3,fixed_curve_point=300]","mask_zeroes_observed":int((mask==0).sum()),"zeroed_unobserved_input_values":float(x[mask==0].abs().sum())},"model":{"name":"CPTransformer","input_shape":list(x.shape),"output_shape":list(out.shape),"finite":bool(torch.isfinite(out).all()),"device":"CPU","no_grad":True},"scalers":{"train_label_scaler_mean":train.return_label_scaler().mean_.reshape(-1).tolist(),"train_label_scaler_scale":train.return_label_scaler().scale_.reshape(-1).tolist(),"val_uses_same_scaler_object":True},"validation_metrics":metrics(predictions),"train_median_eol_reference_metrics":metrics(baseline),"optimizer_created":False,"backward_called":False,"fit_count":0,"test_inference":False,"test_labels_loaded":False}
 outdir=EXP/"preflight"
 if outdir.exists():
  outdir=EXP/("preflight_"+datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ"))
 outdir.mkdir(exist_ok=False)
 with open(outdir/"val_predictions.csv","x",newline="",encoding="utf-8") as f:
  fields=list(predictions[0].keys()) if predictions else ["file_name","prefix_index","label_total_life_cycles","prediction_total_life_cycles","absolute_error_cycles","absolute_percentage_error"]
  w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(predictions)
 with open(outdir/"baseline_train_median_val_predictions.csv","x",newline="",encoding="utf-8") as f:
  fields=list(baseline[0].keys()) if baseline else []
  w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(baseline)
 with open(outdir/"preflight.json","x",encoding="utf-8") as f: json.dump(result,f,ensure_ascii=False,indent=2); f.write("\n")
 print(json.dumps({"status":result["status"],"train_samples":len(train),"val_samples":len(val),"train_cells":len(train.files),"val_cells":len(val.files),"test_files_loaded":0,"input_shape":list(x.shape),"mask_shape":list(mask.shape),"output_shape":list(out.shape),"val_cell_equal_mae":result["validation_metrics"]["cell_equal_mae_cycles"],"report":str(outdir/"preflight.json")},ensure_ascii=False,indent=2))
if __name__=="__main__": main()
