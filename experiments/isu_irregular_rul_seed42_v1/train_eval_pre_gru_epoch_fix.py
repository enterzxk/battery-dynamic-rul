"""GO-gated immutable train/development runner. Locked cohort IDs are never opened."""
from __future__ import annotations
import argparse,csv,hashlib,json,os,random,time,traceback,fcntl,signal,datetime
from pathlib import Path
import numpy as np
from data_adapter import load_reviewed_cell,build_origins
from baselines import GroupFrozenDistribution,HGBEvent,LognormalAFT,Mixture,CDFFusionPredictor,event_time_target,features,early_features,make_gru
PROTOCOL=Path(__file__).with_name("protocol_candidate.json")
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def source_hashes():
 return {n:sha(PROTOCOL.parent/n) for n in ("train_eval.py","baselines.py","data_adapter.py","protocol_candidate.json")}
def write_json_atomic(path,obj):
 path=Path(path);tmp=path.with_suffix(path.suffix+".tmp");tmp.write_text(json.dumps(obj,indent=2),encoding="utf-8");os.replace(tmp,path)
def validate_owner(coordinator_path,owner):
 cp=Path(coordinator_path);lockpath=cp.with_suffix(".lock")
 with lockpath.open("a+") as lk:
  fcntl.flock(lk,fcntl.LOCK_EX)
  c=json.loads(cp.read_text(encoding="utf-8"))
  if c.get("state")!="ACTIVE" or c.get("owner")!=owner or c.get("thread_id")!=owner:raise RuntimeError("coordinator owner/state mismatch")
  if c.get("actual_cwd")!="/home/yndx/zxk/rul" or c.get("takeover_verified") is not True:raise RuntimeError("coordinator cwd/takeover not verified")
  hb=datetime.datetime.fromisoformat(c["heartbeat_utc"].replace("Z","+00:00"))
  if (datetime.datetime.now(datetime.timezone.utc)-hb).total_seconds()>1800:raise RuntimeError("coordinator heartbeat stale")
  fcntl.flock(lk,fcntl.LOCK_UN)
 return c
def load_split(cohort_path,data_root,manifest_path):
 cohort=json.loads(Path(cohort_path).read_text());manifest=json.loads(Path(manifest_path).read_text());roles=cohort["roles"];files=manifest.get("files",{})
 if manifest.get("status")!="PASS":raise RuntimeError("data manifest qualification is not PASS")
 allowed={c for c,r in roles.items() if r in ("train","development")}
 if set(files)!=allowed:raise RuntimeError("manifest must exactly match frozen train/dev IDs")
 cells=[]
 for role in ("train","development"):
  for cid in [c for c,r in roles.items() if r==role]:
   p=Path(data_root)/(cid+".json")
   if not p.is_file() or sha(p)!=files[cid].get("sha256"):raise RuntimeError("record missing/hash mismatch "+cid)
   x=load_reviewed_cell(p,role)
   if x["cell_id"]!=cid:raise RuntimeError("record ID mismatch")
   cells.append(x)
 return cells
def make_examples(cells):
 out=[]
 for c in cells:
  if not c["event_observed"]:continue
  for arm,delay,sparse in (("raw",0,False),("sparse2rpt",0,True),("delayed7d",7,False)):
   for x in build_origins(c,delay_days=delay,sparse=sparse):x["arm"]=arm;out.append(x)
 return out
def weights(xs):
 n={}
 for x in xs:n[x["cell_id"]]=n.get(x["cell_id"],0)+1
 return np.asarray([1./n[x["cell_id"]] for x in xs])
def train_hgb(xs,early=False,seed=42):
 from sklearn.ensemble import HistGradientBoostingRegressor
 if early:
  unique={}
  for x in xs:unique.setdefault(x["cell_id"],x)
  xs=list(unique.values())
 ids=sorted({x["cell_id"] for x in xs});rng=np.random.RandomState(seed);rng.shuffle(ids);folds=[set(ids[::2]),set(ids[1::2])]
 y=np.log([event_time_target(x) for x in xs]);res=[];rw=[];fx=early_features if early else features
 for fold in folds:
  tr=[i for i,x in enumerate(xs) if x["cell_id"] not in fold];va=[i for i,x in enumerate(xs) if x["cell_id"] in fold]
  if not tr or not va:raise RuntimeError("empty cell-isolated OOF fold")
  m=HistGradientBoostingRegressor(max_iter=150,max_leaf_nodes=15,l2_regularization=1.,random_state=seed)
  m.fit(np.stack([fx(xs[i]) for i in tr]),np.asarray(y)[tr],sample_weight=weights([xs[i] for i in tr]))
  res.extend((np.asarray(y)[va]-m.predict(np.stack([fx(xs[i]) for i in va]))).tolist())
  counts={}
  for i in va:counts[xs[i]["cell_id"]]=counts.get(xs[i]["cell_id"],0)+1
  rw.extend([1./counts[xs[i]["cell_id"]] for i in va])
 full=HistGradientBoostingRegressor(max_iter=150,max_leaf_nodes=15,l2_regularization=1.,random_state=seed)
 full.fit(np.stack([fx(x) for x in xs]),y,sample_weight=weights(xs))
 rw=np.asarray(rw);rw/=rw.sum()
 return HGBEvent(full,np.asarray(res),rw,early),rw
def sequence(x):
 from baselines import GROUPS,group_index
 rs=x["visible_records"];g=group_index(x);age=float(x["origin_age_weeks"]);stale=max(0.,age-rs[-1]["calendar_age_weeks"]);out=[];prev=None
 for r in rs:
  dt=0. if prev is None else max(0.,(r["stop_epoch"]-prev["stop_epoch"])/604800.)
  dq=0. if prev is None else (r["capacityAh"]-prev["capacityAh"])/max(dt,1e-6)
  out.append([r["calendar_age_weeks"],r["capacityAh"]/x["nominal_capacity_ah"],dt,dq,1.,age,stale]+[float(i==g) for i in range(GROUPS)]);prev=r
 return out
def train_gru(xs,epochs=100,seed=42,checkpoint_dir=None,on_epoch=None):
 import torch
 from torch import nn
 torch.manual_seed(seed);np.random.seed(seed);random.seed(seed)
 model=make_gru();opt=torch.optim.Adam(model.parameters(),lr=.003)
 optids={id(p) for g in opt.param_groups for p in g["params"]}
 if {id(p) for p in model.parameters() if p.requires_grad}-optids:raise RuntimeError("GRU optimizer misses parameters")
 seqs=[sequence(x) for x in xs];lens=torch.tensor([len(s) for s in seqs]);mx=max(lens).item();xt=torch.zeros((len(xs),mx,71))
 for i,s in enumerate(seqs):xt[i,:len(s)]=torch.tensor(s)
 y=torch.tensor(np.log([event_time_target(x) for x in xs]),dtype=torch.float32);w=torch.tensor(weights(xs),dtype=torch.float32)
 for _ in range(epochs):
  opt.zero_grad();packed=nn.utils.rnn.pack_padded_sequence(xt,lens,batch_first=True,enforce_sorted=False);_,h=model.gru(packed);p=model.head(h[-1])
  sig=torch.exp(torch.clamp(p[:,1],-5.,3.));li=.5*((y-p[:,0])/sig)**2+torch.log(sig);loss=(li*w).sum()/w.sum()
  if not torch.isfinite(loss):raise FloatingPointError("nonfinite GRU loss")
  loss.backward()
  if any(p.grad is not None and not torch.isfinite(p.grad).all() for p in model.parameters()):raise FloatingPointError("nonfinite GRU gradient")
  opt.step()
  lv=float(loss.detach().cpu())
  if checkpoint_dir is not None:
   cp=Path(checkpoint_dir)/"gru_epoch_checkpoint.pt";tmp=cp.with_suffix(".tmp");torch.save({"epoch":_+1,"model":model.state_dict(),"optimizer":opt.state_dict(),"loss":lv},tmp);os.replace(tmp,cp)
   write_json_atomic(Path(checkpoint_dir)/"gru_training_progress.json",{"epochs_completed":_+1,"loss":lv,"seed":seed})
  if on_epoch is not None:on_epoch(_+1,lv)
 return model
class GRUEvent:
 def __init__(self,model):self.model=model
 def predict(self,x):
  import torch
  from baselines import LognormalEvent
  with torch.no_grad():
   _,h=self.model.gru(torch.tensor([sequence(x)],dtype=torch.float32));p=self.model.head(h[-1])[0].numpy()
  return LognormalEvent(float(p[0]),float(np.exp(np.clip(p[1],-5,3)))).shifted(x["origin_age_weeks"]-x["anchor_age_weeks"])
def check_cdf(d,pts):
 a=np.asarray(sorted(set(pts)),float);c=np.asarray(d.cdf(a),float)
 if not np.all(np.isfinite(c)) or np.any(c<0) or np.any(c>1) or np.any(np.diff(c)<-1e-12):raise ValueError("invalid/nonmonotone CDF")
 return c
def interval(y,l,h):return (h-l)+10*max(l-y,0)+10*max(y-h,0)
def evaluate(models,dev,out):
 rows=[];by={}
 for x in dev:
  y=float(x["target_rul_weeks"])
  for name,m in models.items():
   t=time.perf_counter();d=m.predict(x);update_ms=(time.perf_counter()-t)*1000
   l=float(d.quantile(.1));h=float(d.quantile(.9));mu=float(d.mean())
   if not np.all(np.isfinite([l,h,mu])) or l<0 or h<l or mu<0:raise ValueError('nonfinite/invalid distribution summary')
   check_cdf(d,[0,4,12,y,l,h])
   r={"model_update_wall_ms":update_ms,"cell_id":x["cell_id"],"group_id":x["group_id"],"arm":x["arm"],"origin_stop_epoch":x["origin_stop_epoch"],"target_rul_weeks":y,"model":name,"pred_mean_weeks":mu,"q10_weeks":l,"q90_weeks":h,"zero_rul_mass":float(d.cdf(0.)),"brier4w":(float(d.cdf(4.))-(y<=4))**2,"brier12w":(float(d.cdf(12.))-(y<=12))**2}
   rows.append(r);by.setdefault((r["cell_id"],r["arm"],name),[]).append(r)
 with (out/"predictions_dev.csv").open("x",newline="",encoding="utf8") as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 met=[]
 for (cid,arm,name),rs in by.items():
  e=np.array([r["pred_mean_weeks"]-r["target_rul_weeks"] for r in rs])
  met.append({"cell_id":cid,"arm":arm,"model":name,"mae_weeks":float(np.mean(abs(e))),"severe_overprediction_gt4w_rate":float(np.mean(e>4)),"severe_overprediction_cell_any":bool(np.any(e>4)),"is80":float(np.mean([interval(r["target_rul_weeks"],r["q10_weeks"],r["q90_weeks"]) for r in rs])),"coverage80":float(np.mean([r["q10_weeks"]<=r["target_rul_weeks"]<=r["q90_weeks"] for r in rs])),"brier4w":float(np.mean([r["brier4w"] for r in rs])),"brier12w":float(np.mean([r["brier12w"] for r in rs])),"mean_update_wall_ms":float(np.mean([r["model_update_wall_ms"] for r in rs])),"n_origins":len(rs)})
 (out/"per_cell_metrics.json").write_text(json.dumps(met,indent=2))
 rng=np.random.RandomState(42);boot=[]
 for arm in sorted({r["arm"] for r in met}):
  for model in sorted({r["model"] for r in met}):
   v=np.array([r["mae_weeks"] for r in met if r["arm"]==arm and r["model"]==model])
   if len(v):
    d=v[rng.randint(0,len(v),(2000,len(v)))].mean(axis=1);boot.append({"arm":arm,"model":model,"n_cells":len(v),"seed":42,"ci95":[float(np.quantile(d,.025)),float(np.quantile(d,.975))]})
 (out/"cell_bootstrap_ci.json").write_text(json.dumps(boot,indent=2))
 return len(rows)
def run(a):
 t0=time.time();rec={"request_id":None,"status":"PREFLIGHT_FAILED","data_read":False,"fits_started":0,"fits_completed":0,"gru_epochs_completed":0};lock=None;out=None
 try:
  if not a.go_json:raise RuntimeError("fresh root GO required")
  go=json.loads(Path(a.go_json).read_text());ph=sha(PROTOCOL);rec["request_id"]=go.get("request_id")
  if go.get("status")!="APPROVED" or go.get("allow_fit") is not True or go.get("protocol_sha256")!=ph:raise RuntimeError("GO status/permission/protocol mismatch")
  if not go.get("request_id") or go.get("owner_thread_id")!=a.owner_thread_id:raise RuntimeError("GO request/owner mismatch")
  sh=source_hashes()
  if go.get("source_sha256")!=sh:raise RuntimeError("GO source hash binding mismatch")
  issued=datetime.datetime.fromisoformat(str(go.get("issued_utc","")).replace("Z","+00:00"))
  if issued.tzinfo is None:raise RuntimeError("GO issued_utc must carry timezone")
  if (datetime.datetime.now(datetime.timezone.utc)-issued).total_seconds()>86400 or (issued-datetime.datetime.now(datetime.timezone.utc)).total_seconds()>60:raise RuntimeError("GO timestamp expired/future")
  runtime_cap=int(go.get("max_runtime_seconds",0))
  if not 1<=runtime_cap<=21600:raise RuntimeError("GO runtime cap missing/out of bounds")
  expected_root=Path("/home/yndx/zxk/rul")
  if Path(a.coordinator_json)!=expected_root/"automation/state/coordinator.json":raise RuntimeError("unexpected coordinator path")
  if Path(a.cpu_lock)!=expected_root/"automation/locks/isu_irregular_rul_cpu.lock":raise RuntimeError("unexpected project CPU lock path")
  coordinator=validate_owner(a.coordinator_json,a.owner_thread_id)
  budget={"hgb_fits":6,"aft_fits":1,"gru_fits":1}
  if go.get("gru_epochs")!=100:raise RuntimeError("GO GRU epoch cap mismatch")
  if go.get("seed")!=42 or go.get("fit_budget")!=budget:raise RuntimeError("GO budget/seed mismatch")
  cs,ms=sha(a.cohort),sha(a.data_manifest)
  if go.get("cohort_sha256")!=cs or go.get("data_manifest_sha256")!=ms:raise RuntimeError("GO cohort/manifest mismatch")
  out=Path(a.output);rp=Path(a.receipt)
  if out.exists() or rp.exists():raise RuntimeError("output or receipt exists; no overwrite")
  ld=Path(a.lock_dir);ld.mkdir(parents=True,exist_ok=True)
  cpu_path=Path(a.cpu_lock);cpu_path.parent.mkdir(parents=True,exist_ok=True);cpu_lock=cpu_path.open("a+")
  try:fcntl.flock(cpu_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:cpu_lock.close();raise RuntimeError("project CPU flock is already held")
  claim=ld/(go["request_id"]+".claim");fd=os.open(str(claim),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
  os.write(fd,json.dumps({"owner":a.owner_thread_id,"request_id":go["request_id"],"protocol_sha256":ph}).encode());os.fsync(fd);os.close(fd)
  lock=ld/(go["request_id"]+".lock")
  fd=os.open(str(lock),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,json.dumps({"owner":a.owner_thread_id,"request_id":go["request_id"]}).encode());os.fsync(fd);os.close(fd)
  if json.loads(Path(a.go_json).read_text())!=go:raise RuntimeError("GO changed during preflight")
  rec.update({"status":"RUNNING","protocol_sha256":ph,"source_sha256":sh,"cohort_sha256":cs,"data_manifest_sha256":ms,"owner_thread_id":a.owner_thread_id,"max_runtime_seconds":runtime_cap,"fit_counting_note":"HGB started count reserves 3 fits before the helper; if a failure interrupts a fold, actual completed fits may be fewer and the request is not reusable."})
  def timeout_handler(signum,frame):raise TimeoutError("approved hard runtime cap exceeded")
  signal.signal(signal.SIGALRM,timeout_handler);signal.alarm(runtime_cap)
  cells=load_split(a.cohort,a.data_root,a.data_manifest);rec["data_read"]=True
  tr=make_examples([x for x in cells if x["role"]=="train"]);dv=make_examples([x for x in cells if x["role"]=="development"])
  if not tr or not dv:raise RuntimeError("empty train/dev examples")
  out.mkdir(parents=False,exist_ok=False)
  import joblib
  models={};g=GroupFrozenDistribution();g.fit(tr);models["group_frozen"]=g
  for early,name in ((False,"hgb_dynamic"),(True,"hgb_early_health")):
   rec["fits_started"]+=3
   mdl,rw=train_hgb(tr,early,42);rec["fits_completed"]+=3;joblib.dump(mdl.model,out/(name+".joblib"));np.save(out/(name+"_oof_residuals.npy"),mdl.r);np.save(out/(name+"_oof_cell_equal_weights.npy"),rw);models[name]=mdl
  aft=LognormalAFT(False);rec["fits_started"]+=1
  cw={}
  for z in tr:cw[z["cell_id"]]=cw.get(z["cell_id"],0)+1
  aft.fit(tr,np.asarray([1./cw[z["cell_id"]] for z in tr]));rec["fits_completed"]+=1;joblib.dump(aft.model,out/"aft_dynamic.joblib");(out/"aft_distribution.json").write_text(json.dumps({"sigma":aft.sigma,"use_group":aft.use_group}));models["aft_dynamic"]=aft
  epochs=int(go.get("gru_epochs",100))
  if not 1<=epochs<=500:raise RuntimeError("GRU epoch cap invalid")
  rec["fits_started"]+=1
  def epoch_progress(ep,loss):rec.update({"gru_epochs_completed":ep,"last_gru_loss":loss})
  gru=train_gru(tr,epochs,checkpoint_dir=out,on_epoch=epoch_progress);rec["fits_completed"]+=1;rec["gru_epochs_completed"]=epochs
  import torch;torch.save(gru.state_dict(),out/"gru_state.pt");models["gru_dynamic"]=GRUEvent(gru)
  models["cdf_fusion"]=CDFFusionPredictor([g,models["hgb_dynamic"]])
  rec["predictions"]=evaluate(models,dv,out)
  rec.update({"status":"SUCCESS","fit_wall_seconds":time.time()-t0,"arms":["raw","sparse2rpt","delayed7d"],"note":"Source-observed first RPT Q<=0.20 Ah endpoint; not latent EOL. Only anchor conditions on observed above-threshold health; subsequent gaps are not survival-conditioned. Event-time distributions shift to RUL and retain zero mass. No fixed-grid tail clipping/appending."})
 except Exception as e:
  rec.update({"status":"FAILED","error":repr(e),"traceback":traceback.format_exc(limit=8)});raise
 finally:
  rec["elapsed_seconds"]=time.time()-t0
  if "runtime_cap" in locals():signal.alarm(0)
  try:
   p=Path(a.receipt);p.parent.mkdir(parents=True,exist_ok=True)
   if p.exists():p=p.with_name(p.stem+"_"+str(rec.get("request_id") or "no_request")+"_"+str(time.time_ns())+".failure.json")
   payload=json.dumps(rec,indent=2).encode("utf-8")
   try:
    fd=os.open(str(p),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,payload);os.fsync(fd);os.close(fd)
   except FileExistsError:
    alt=p.with_name(p.stem+"_"+str(time.time_ns())+".json")
    fd=os.open(str(alt),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,payload);os.fsync(fd);os.close(fd)
  finally:
   if lock is not None:
    try:lock.unlink()
    except FileNotFoundError:pass
   if "cpu_lock" in locals():
    try:fcntl.flock(cpu_lock,fcntl.LOCK_UN);cpu_lock.close()
    except Exception:pass
def main():
 p=argparse.ArgumentParser()
 for k in ("cohort","data_root","data_manifest","output","receipt","lock_dir","owner_thread_id","coordinator_json","cpu_lock"):p.add_argument("--"+k.replace("_","-"),required=True)
 p.add_argument("--go-json",required=True);run(p.parse_args())
if __name__=="__main__":main()

