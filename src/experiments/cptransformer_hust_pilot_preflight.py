#!/usr/bin/env python3
"""No-fit CPTransformer HUST v11 preflight. No optimizer/backward/fit path exists."""
import os,sys,pickle,hashlib,json,random,csv,datetime
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch
from torch.utils.data import DataLoader
ROOT=Path("/home/yndx/zxk/rul")
CODE=ROOT/"repos/pinned/BatteryLife_3b17bb53202e10711deae0448c91f84144bb3dd9"
STAGE=ROOT/"data/source_audit/stage_v11_hust_v11_labels"
VIEW=ROOT/"experiments/cpmlp_hust_pilot_seed42/input_trainval"
OUT=ROOT/"experiments/cptransformer_hust_pilot_seed42"
CONFIG=ROOT/"configs/experiments/cptransformer_hust_pilot_seed42_draft.json"
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(8*1024*1024),b""):h.update(b)
 return h.hexdigest()
class DenyAllUnpickler(pickle.Unpickler):
 def find_class(self,module,name):raise pickle.UnpicklingError("BLOCKED_GLOBAL:%s.%s"%(module,name))
 def persistent_load(self,pid):raise pickle.UnpicklingError("BLOCKED_PERSISTENT_ID")
class RestrictedPickleFacade:
 def __init__(self,allowed):self.allowed=allowed;self.reads=[]
 def load(self,f):
  path=os.path.abspath(f.name);want=self.allowed.get(path)
  if want is None:raise PermissionError("PKL outside HUST train/val allowlist: "+path)
  f.seek(0);h=hashlib.sha256()
  for b in iter(lambda:f.read(8*1024*1024),b""):h.update(b)
  got=h.hexdigest()
  if got!=want:raise RuntimeError("PKL SHA mismatch: "+path)
  f.seek(0);obj=DenyAllUnpickler(f).load()
  todo=[obj]
  while todo:
   x=todo.pop()
   if isinstance(x,(str,bytes,int,float,bool,type(None))):continue
   if isinstance(x,dict):
    for k,v in x.items():
     if not isinstance(k,(str,bytes,int,float,bool,type(None))):raise TypeError("nonprimitive dict key")
     todo.append(v)
   elif isinstance(x,(list,tuple,set,frozenset)):todo.extend(x)
   else:raise TypeError("nonprimitive pickle value "+type(x).__name__)
  self.reads.append({"path":path,"sha256":got});return obj
def main():
 cfg=json.loads(CONFIG.read_text())
 if cfg.get("status")!="DRAFT" or cfg.get("training_authorized") is not False:raise RuntimeError("draft config authorization guard failed")
 if sha(STAGE/"stage_manifest.json")!=cfg["stage_manifest_sha256"]:raise RuntimeError("stage manifest hash mismatch")
 vm=json.loads((VIEW/"view_manifest.json").read_text())
 if sha(VIEW/"view_manifest.json")!=cfg["source_view_manifest_sha256"]:raise RuntimeError("source view manifest hash mismatch")
 if vm.get("source_stage_manifest_sha256")!=cfg["stage_manifest_sha256"]:raise RuntimeError("view/stage mismatch")
 train=set(cfg["split_files"]["train"]);val=set(cfg["split_files"]["val"]);test=set(cfg["split_files"]["test"])
 if len(train)!=47 or len(val)!=15 or len(test)!=15 or train&val or train&test or val&test:raise RuntimeError("split count/overlap mismatch")
 files=sorted(p.name for p in (VIEW/"HUST").iterdir())
 if set(files)!=train|val or set(files)&test:raise RuntimeError("source view is not exact 47+15 trainval")
 labels=VIEW/"Life labels/HUST_labels.json"
 if sha(labels)!=vm["trainval_label_sha256"]:raise RuntimeError("trainval labels sha mismatch")
 labs=json.loads(labels.read_text())
 if set(labs)!=train|val or set(labs)&test:raise RuntimeError("test/missing label key in view")
 hashes={os.path.abspath(str(VIEW/"HUST"/x["name"])):x["source_sha256"] for x in vm["hust_files"]}
 sys.path.insert(0,str(CODE));os.chdir(CODE)
 import data_provider.data_loader as dl
 safe=RestrictedPickleFacade(hashes);dl.pickle=safe
 torch.set_num_threads(2);random.seed(cfg["seed"]);np.random.seed(cfg["seed"]);torch.manual_seed(cfg["seed"])
 args=SimpleNamespace(root_path=str(VIEW),dataset="HUST",seq_len=1,charge_discharge_length=300,early_cycle_threshold=100,weighted_loss=False)
 train_ds=dl.Dataset_original(args=args,flag="train")
 if set(train_ds.files)!=train:raise RuntimeError("loader train split differs")
 val_ds=dl.Dataset_original(args=args,flag="val",label_scaler=train_ds.return_label_scaler(),life_class_scaler=train_ds.return_life_class_scaler())
 if set(val_ds.files)!=val:raise RuntimeError("loader val split differs")
 if train_ds.return_label_scaler() is not val_ds.return_label_scaler():raise RuntimeError("val scaler not train scaler")
 if any(Path(r["path"]).name not in train|val for r in safe.reads):raise RuntimeError("test file accessed")
 collate=dl.my_collate_fn_baseline
 tr_loader=DataLoader(train_ds,batch_size=2,shuffle=False,drop_last=False,collate_fn=collate,num_workers=0)
 va_loader=DataLoader(val_ds,batch_size=2,shuffle=False,drop_last=False,collate_fn=collate,num_workers=0)
 tr=next(iter(tr_loader));va=next(iter(va_loader))
 mc=cfg["model"]
 margs=SimpleNamespace(d_ff=mc["d_ff"],d_model=mc["d_model"],charge_discharge_length=mc["charge_discharge_length"],early_cycle_threshold=mc["early_cycle_threshold"],dropout=mc["dropout"],e_layers=mc["e_layers"],d_layers=mc["d_layers"],n_heads=mc["n_heads"],factor=mc["factor"],activation=mc["activation"],output_num=mc["output_num"])
 from models.CPTransformer import Model
 model=Model(margs).eval()
 def forward(batch):
  x,mask,y,life_class,scaled_life,weights,seen=batch
  with torch.no_grad():out=model(x,mask)
  return {"input_shape":list(x.shape),"mask_shape":list(mask.shape),"target_shape":list(y.shape),"weights_shape":list(weights.shape),"mask_zeros":int((mask==0).sum()),"masked_input_abs_sum":float(x[mask==0].abs().sum()),"output_shape":list(out.shape),"finite":bool(torch.isfinite(out).all()),"device":"CPU","no_grad":True}
 result={"created_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"status":"CPTRANSFORMER_REAL_DATA_PREFLIGHT_PASS_NO_FIT","new_fits":0,"optimizer_steps":0,"optimizer_created":False,"backward_called":False,"model_forward_calls":2,"repository_commit":cfg["repository_commit"],"config_sha256":sha(CONFIG),"runner_sha256":sha(Path(__file__).resolve()),"pinned_model_sha256":sha(CODE/"models/CPTransformer.py"),"pinned_loader_sha256":sha(CODE/"data_provider/data_loader.py"),"stage_manifest_sha256":sha(STAGE/"stage_manifest.json"),"view_manifest_sha256":sha(VIEW/"view_manifest.json"),"source_view_path":str(VIEW),"train_cells":sorted(train_ds.files),"validation_cells":sorted(val_ds.files),"test_files_loaded":[],"test_inference":False,"pickle_reads":safe.reads,"dataset_lengths":{"train_prefix_samples":len(train_ds),"validation_prefix_samples":len(val_ds)},"train_batch":forward(tr),"validation_batch":forward(va),"label_scaler":{"mean":train_ds.return_label_scaler().mean_.reshape(-1).tolist(),"scale":train_ds.return_label_scaler().scale_.reshape(-1).tolist(),"validation_same_object":True},"no_optimizer_path":"companion has no optimizer/backward/fit function","future_fit_lock_path":"automation/locks/cptransformer_hust_pilot_gpu.lock"}
 OUT.mkdir(parents=True,exist_ok=True)
 dest=OUT/"preflight.json"
 if dest.exists():raise RuntimeError("create-only preflight output exists")
 with dest.open("x",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write(chr(10))
 print(json.dumps({"status":result["status"],"train_cells":len(train_ds.files),"val_cells":len(val_ds.files),"test_files_loaded":0,"train_shape":result["train_batch"]["input_shape"],"val_shape":result["validation_batch"]["input_shape"],"pinned_model_sha256":result["pinned_model_sha256"],"report":str(dest)},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
