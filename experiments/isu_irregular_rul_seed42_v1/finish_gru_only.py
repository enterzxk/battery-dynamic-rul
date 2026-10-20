"""Fresh-GO GRU-only recovery after the first baseline runner stopped before epoch checkpointing."""
from __future__ import annotations
import argparse,datetime,fcntl,hashlib,json,os,signal,time,traceback
from pathlib import Path

ROOT=Path("/home/yndx/zxk/rul")
HERE=Path(__file__).resolve().parent
PROTOCOL=HERE/"protocol_candidate.json"
for _name in ("OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS","NUMEXPR_NUM_THREADS"):
 os.environ[_name]="4"

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical_hash(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def source_map():
 return {n:sha(HERE/n) for n in ("finish_gru_only.py","train_eval.py","baselines.py","data_adapter.py","protocol_candidate.json")}
def durable_receipt(path,request_id,obj):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 payload=json.dumps(obj,indent=2,allow_nan=False).encode("utf-8")
 for target in (p,p.with_name(p.stem+"_"+str(request_id or "no_request")+"_"+str(time.time_ns())+".failure.json")):
  try:
   fd=os.open(str(target),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
   try:os.write(fd,payload);os.fsync(fd)
   finally:os.close(fd)
   return str(target)
  except FileExistsError:pass
 raise FileExistsError("could not write non-overwriting run receipt")
def acquire_lock(path,label):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);f=p.open("a+")
 try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:f.close();raise RuntimeError(label+" lock already held")
 return f
def validate_owner(path,owner):
 from train_eval import validate_owner as validate
 cp=Path(path)
 if cp!=ROOT/"automation/state/coordinator.json":raise RuntimeError("unexpected coordinator path")
 return validate(cp,owner)
def check_go(a):
 go=json.loads(Path(a.go_json).read_text(encoding="utf-8"))
 if go.get("status")!="APPROVED" or go.get("allow_fit") is not True:raise RuntimeError("fresh GRU-only GO absent")
 if not go.get("request_id") or go.get("owner_thread_id")!=a.owner_thread_id:raise RuntimeError("GO request/owner mismatch")
 issued=datetime.datetime.fromisoformat(str(go.get("issued_utc","")).replace("Z","+00:00"))
 if issued.tzinfo is None:raise RuntimeError("GO issued_utc requires timezone")
 now=datetime.datetime.now(datetime.timezone.utc)
 if (now-issued).total_seconds()>86400 or (issued-now).total_seconds()>60:raise RuntimeError("GO expired or future-dated")
 cap=int(go.get("max_runtime_seconds",0))
 if not 1<=cap<=21600:raise RuntimeError("GO runtime cap outside 1..21600 seconds")
 if go.get("protocol_sha256")!=sha(PROTOCOL):raise RuntimeError("protocol SHA mismatch")
 sm=source_map()
 if go.get("source_sha256")!=sm or go.get("code_manifest_sha256")!=canonical_hash(sm):raise RuntimeError("source/code manifest mismatch")
 for key,path in (("cohort_sha256",a.cohort),("data_manifest_sha256",a.data_manifest),("prior_failure_receipt_sha256",a.prior_failure_receipt)):
  if go.get(key)!=sha(path):raise RuntimeError(key+" mismatch")
 old=json.loads(Path(a.prior_failure_receipt).read_text(encoding="utf-8"))
 if old.get("status")!="FAILED" or old.get("fits_started")!=8 or old.get("fits_completed")!=7 or old.get("gru_epochs_completed")!=0:raise RuntimeError("prior run receipt is not the expected pre-checkpoint failure")
 if go.get("prior_request_id")!=old.get("request_id"):raise RuntimeError("prior failed request binding mismatch")
 budget={"hgb_fits":0,"aft_fits":0,"gru_fits":1}
 if go.get("fit_budget")!=budget or go.get("seed")!=42 or go.get("gru_epochs")!=100:raise RuntimeError("GRU-only fit budget/seed/epoch mismatch")
 if int(go.get("max_inference_calls",0))<=0:raise RuntimeError("development inference-call cap missing")
 expected={"coordinator_json":str(ROOT/"automation/state/coordinator.json"),
           "old_cpu_lock":str(ROOT/"automation/state/online_survival_cpu.lock"),
           "isu_cpu_lock":str(ROOT/"automation/locks/isu_irregular_rul_cpu.lock"),
           "claim_dir":str(ROOT/"automation/locks/finish_gru_only_claims")}
 for key,value in expected.items():
  if str(Path(getattr(a,key)))!=value or go.get(key)!=value:raise RuntimeError("path binding mismatch for "+key)
 if go.get("output_path")!=str(Path(a.output)) or go.get("receipt_path")!=str(Path(a.receipt)):raise RuntimeError("output/receipt path mismatch")
 for key,arg in (("data_root_path",a.data_root),("cohort_path",a.cohort),("data_manifest_path",a.data_manifest),("prior_failure_receipt_path",a.prior_failure_receipt)):
  if go.get(key)!=str(Path(arg)):raise RuntimeError("input path binding mismatch for "+key)
 validate_owner(a.coordinator_json,a.owner_thread_id)
 return go,cap,sm
def run(a):
 start=time.time();rec={"status":"PREFLIGHT_FAILED","request_id":None,"data_read":False,"fit_started":0,"fit_completed":0,"gru_epochs_checkpointed":0,"inference_calls":0}
 held=[];cap=None
 try:
  go,cap,sm=check_go(a);rec["request_id"]=go["request_id"]
  out=Path(a.output);receipt=Path(a.receipt)
  if out.exists() or receipt.exists():raise FileExistsError("output or receipt already exists")
  claim_dir=Path(a.claim_dir);claim_dir.mkdir(parents=True,exist_ok=True)
  claim=claim_dir/(go["request_id"]+".claim")
  fd=os.open(str(claim),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
  os.write(fd,json.dumps({"request_id":go["request_id"],"owner_thread_id":a.owner_thread_id,"source_sha256":sm}).encode());os.fsync(fd);os.close(fd)
  held.append(acquire_lock(a.old_cpu_lock,"shared/old CPU"))
  held.append(acquire_lock(a.isu_cpu_lock,"ISU CPU"))
  if json.loads(Path(a.go_json).read_text(encoding="utf-8"))!=go:raise RuntimeError("GO changed after claim")
  validate_owner(a.coordinator_json,a.owner_thread_id)
  def on_alarm(signum,frame):raise TimeoutError("approved GRU-only hard runtime cap exceeded")
  signal.signal(signal.SIGALRM,on_alarm);signal.alarm(cap)
  rec.update({"status":"RUNNING","owner_thread_id":a.owner_thread_id,"source_sha256":sm,"code_manifest_sha256":canonical_hash(sm),"protocol_sha256":sha(PROTOCOL),"max_runtime_seconds":cap,"fit_budget":{"hgb_fits":0,"aft_fits":0,"gru_fits":1},"seed":42,"epochs_requested":100,"cpu_threads":4,"prior_failure_receipt_sha256":sha(a.prior_failure_receipt),"prior_failure_receipt_path":str(Path(a.prior_failure_receipt))})
  out.mkdir(parents=False,exist_ok=False)
  # Frozen train/dev loader enforces manifest PASS and excludes locked cell files.
  from train_eval import load_split,make_examples,train_gru,GRUEvent,evaluate
  cells=load_split(a.cohort,a.data_root,a.data_manifest);rec["data_read"]=True
  tr=make_examples([c for c in cells if c["role"]=="train"])
  dev=make_examples([c for c in cells if c["role"]=="development"])
  if not tr or not dev:raise RuntimeError("frozen train/development examples are empty")
  if len(dev)>int(go["max_inference_calls"]):raise RuntimeError("development inference-call cap exceeded")
  import torch
  torch.set_num_threads(4);torch.set_num_interop_threads(1)
  rec["fit_started"]=1
  def epoch_progress(epoch,loss):
   rec.update({"gru_epochs_checkpointed":int(epoch),"last_gru_loss":float(loss)})
  model=train_gru(tr,epochs=100,seed=42,checkpoint_dir=out,on_epoch=epoch_progress)
  rec.update({"fit_completed":1,"gru_epochs_checkpointed":100})
  torch.save(model.state_dict(),out/"gru_state.pt")
  rec["inference_calls"]=len(dev)
  rec["predictions"]=evaluate({"gru_dynamic":GRUEvent(model)},dev,out)
  rec.update({"status":"SUCCESS","note":"One fresh GRU fit of 100 epochs only; no old CPU estimator/checkpoint was loaded or inferred. Development predictions are standalone and source-observed endpoint descriptive."})
 except Exception as e:
  rec.update({"status":"FAILED","error":repr(e),"traceback":traceback.format_exc(limit=8)})
  raise
 finally:
  rec["elapsed_seconds"]=time.time()-start
  if cap is not None:
   try:signal.alarm(0)
   except Exception:pass
  try:rec["receipt_path_written"]=durable_receipt(a.receipt,rec.get("request_id"),rec)
  finally:
   for lock in reversed(held):
    try:fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
    except Exception:pass
def main():
 p=argparse.ArgumentParser()
 for key in ("cohort","data_root","data_manifest","output","receipt","owner_thread_id","coordinator_json","old_cpu_lock","isu_cpu_lock","claim_dir","prior_failure_receipt"):
  p.add_argument("--"+key.replace("_","-"),required=True)
 p.add_argument("--go-json",required=True)
 run(p.parse_args())
if __name__=="__main__":main()
