#!/home/yndx/miniconda3/envs/a40_env/bin/python
"""B2-v2.1 four-fit runner: CUDA0, 4 threads, shared CPU+GPU locks, train-only
weighted standardization stored in model buffers, cell-isolated internal selection,
and explicit optimizer-step/validation history."""
from __future__ import annotations
import os
os.environ['OMP_NUM_THREADS']='4';os.environ['MKL_NUM_THREADS']='4';os.environ['OPENBLAS_NUM_THREADS']='4'
os.environ['CUDA_VISIBLE_DEVICES']='0'
import argparse,datetime,fcntl,hashlib,json,pathlib,signal,sys,time,traceback
ROOT=pathlib.Path('/home/yndx/zxk/rul');HERE=ROOT/'experiments/trajectory_b2_joint_marked_renewal_20261021/candidate_v2'
OWNER='01a15c3a-1a06-7d61-8517-27b70b246183';VARIANTS=('joint','independent')
CPU_LOCKS=('automation/state/online_survival_cpu.lock','automation/locks/isu_irregular_rul_cpu.lock')
GPU_LOCK='automation/locks/multirate_state_20261021_gpu.lock'
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def atomicj(p,x):
 t=pathlib.Path(str(p)+'.tmp');t.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8');os.replace(t,p)
def run(go_path):
 t0=time.time();out=None;receipt=None;locks=[];started=completed=0
 r={'status':'FIT_PREFLIGHT_FAILED','fit_count':0,'fits_started':0,'fits_completed':0,'C3_reads':0,'C4_reads':0}
 try:
  go=json.loads(pathlib.Path(go_path).read_text(encoding='utf-8'))
  req=('status','allow_fit','request_id','owner_thread_id','issued_utc','fit_count','variants','seed','steps_max','batch_size','prep_artifact_path','prep_artifact_sha256','source_sha256','max_runtime_seconds','output_path','receipt_path','data_scope','device')
  if any(k not in go for k in req):raise ValueError('GO missing required field')
  if go['status']!='APPROVED_FIT' or go['allow_fit'] is not True or go['owner_thread_id']!=OWNER:raise ValueError('fit GO/owner mismatch')
  if (go['fit_count'],tuple(go['variants']),go['seed'],go['steps_max'],go['batch_size'])!=(4,VARIANTS,42,3000,256):raise ValueError('frozen four-fit contract mismatch')
  if go['data_scope']!='prepared_train_only_no_C3_C4':raise ValueError('data scope mismatch')
  if str(go['device'])!='cuda:0':raise ValueError('GO must pin device cuda:0')
  issued=datetime.datetime.fromisoformat(go['issued_utc'].replace('Z','+00:00'))
  if abs((datetime.datetime.now(datetime.timezone.utc)-issued).total_seconds())>86400:raise ValueError('stale fit GO')
  runtime=int(go['max_runtime_seconds'])
  if not 60<=runtime<=43200:raise ValueError('runtime outside 60s..12h')
  coord=json.loads((ROOT/'automation/state/coordinator.json').read_text(encoding='utf-8'))
  if coord.get('owner')!=OWNER:raise ValueError('live coordinator owner changed')
  source={n:sha(HERE/n) for n in ('model.py','target_builder.py','prep_runner.py','fit_runner.py','rollout.py','PROTOCOL_V2.md','synthetic_check.py')}
  if source!=go['source_sha256']:raise ValueError('source hash mismatch')
  prep=pathlib.Path(go['prep_artifact_path']).resolve()
  if HERE.resolve() not in prep.parents or sha(prep)!=go['prep_artifact_sha256']:raise ValueError('prepared data path/hash mismatch')
  out=(ROOT/go['output_path']).resolve();receipt=pathlib.Path(go['receipt_path'])
  if HERE.resolve() not in out.parents or out.exists():raise ValueError('output must be fresh in candidate_v2')
  if receipt.parent.resolve()!=(HERE/'receipts').resolve() or receipt.exists():raise ValueError('receipt path invalid')
  deadline=time.monotonic()+runtime
  def alarm(signum,frame):raise TimeoutError('fit GO runtime deadline reached')
  signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,runtime)
  # Fixed acquisition order CPU1 -> CPU2 -> GPU so concurrent runners cannot deadlock.
  for lp in [ROOT/p for p in CPU_LOCKS]+[ROOT/GPU_LOCK]:
   f=lp.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  out.mkdir(parents=True,exist_ok=False)
  import numpy as np,torch
  torch.set_num_threads(4);torch.set_num_interop_threads(1)
  if not torch.cuda.is_available():raise RuntimeError('CUDA required by GO but unavailable')
  torch.cuda.set_device(0);dev=torch.device('cuda:0')
  from model import JointMarkedMixtureNet,log_prob,compute_weighted_normalization
  with np.load(prep,allow_pickle=False) as z:data={k:z[k] for k in z.files}
  x=data['fixed'];d=data['dynamic'];lg=data['log_gap'];dc=data['delta_log_capacity'];dk=data['delta_k'];weights=data['weight'];cells=data['cell_index']
  if x.ndim!=2 or x.shape[1]<=0 or d.shape!=(len(x),6) or len(x)!=len(lg) or len(x)!=len(dc) or len(x)!=len(dk) or len(x)!=len(weights):raise ValueError('prepared arrays malformed')
  if np.any(~np.isfinite(x)) or np.any(~np.isfinite(d)) or np.any(~np.isfinite(lg)) or np.any(~np.isfinite(dc)) or np.any((dk<1)|(dk>3)):raise ValueError('invalid prepared values')
  unique_cells=np.unique(cells);n_cells=int(len(unique_cells))
  if n_cells<5:raise ValueError('too few contributing cells for cell-isolated split')
  rng=np.random.default_rng(42);perm=rng.permutation(unique_cells);n_val=max(1,int(round(.20*n_cells)))
  val_cells=set(int(c) for c in perm[:n_val]);train_mask=np.asarray([int(c) not in val_cells for c in cells]);val_mask=~train_mask
  if not train_mask.any() or not val_mask.any():raise ValueError('cell-isolated internal split empty')
  r.update(status='FITTING',request_id=go['request_id'],go_sha256=sha(go_path),prep_artifact_sha256=sha(prep),source_sha256=source,n_rows=len(x),n_cells=n_cells,contributing_cell_ids=[int(c) for c in unique_cells],fit_budget=4,internal_validation_cells=n_val,internal_validation_cell_ids=sorted(val_cells),device='cuda:0')
  atomicj(out/'progress.json',r);atomicj(out/'fit_ledger.json',{'records':[]});fits={}
  tx=torch.as_tensor(x,dtype=torch.float32,device=dev);td=torch.as_tensor(d,dtype=torch.float32,device=dev)
  tg=torch.as_tensor(lg,dtype=torch.float32,device=dev);tc=torch.as_tensor(dc,dtype=torch.float32,device=dev)
  tk=torch.as_tensor(dk,dtype=torch.long,device=dev)
  def fit_one(variant,fit_mask,steps,validation_mask=None,early_stop=False):
   torch.manual_seed(42);torch.cuda.manual_seed_all(42)
   model=JointMarkedMixtureNet(x.shape[1])
   # Train-only weighted standardization of the rows this fit actually sees.
   fm,fs,dm,ds=compute_weighted_normalization(x[fit_mask],d[fit_mask],weights[fit_mask])
   model.set_normalization(fm,fs,dm,ds,source=('internal_train_cells' if early_stop else 'all125_cells'))
   model.to(dev)
   opt=torch.optim.AdamW(model.parameters(),lr=1e-3,weight_decay=1e-4)
   ids=np.flatnonzero(fit_mask);prob=weights[ids].astype(float);prob/=prob.sum();gen=np.random.default_rng(42)
   norm_sha=hashlib.sha256(b''.join(np.asarray(a,dtype=np.float32).tobytes() for a in (fm,fs,dm,ds))).hexdigest()
   best=float('inf');best_step=0;best_state=None;stale=0;eval_every=50;patience=6;history=[];ran=0
   for step in range(1,int(steps)+1):
    if time.monotonic()>=deadline:raise TimeoutError('runtime expired inside fit')
    batch=np.asarray(gen.choice(ids,size=256,replace=True,p=prob),dtype=int)
    opt.zero_grad(set_to_none=True);params=model(tx[batch],td[batch]);nll=-log_prob(params,tg[batch],tc[batch],tk[batch],variant)
    loss=nll.mean();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5.0);opt.step()
    ran=step
    if early_stop and (step%eval_every==0 or step==steps):
     vid=np.flatnonzero(validation_mask)
     with torch.no_grad():
      vp=model(tx[vid],td[vid]);vll=-log_prob(vp,tg[vid],tc[vid],tk[vid],variant)
      vl=float((vll.double()*torch.as_tensor(weights[vid],dtype=torch.float64,device=dev)).sum().item())
     history.append({'step':step,'validation_nll':vl})
     if vl<best-1e-7:
      best,best_step,best_state=vl,step,{k:v.detach().clone() for k,v in model.state_dict().items()};stale=0
     else: stale+=1
     if stale>=patience: break
   if early_stop:
    if best_state is None:raise RuntimeError('internal selection produced no validation state')
    model.load_state_dict(best_state)
   return model,{'optimizer_steps_ran':int(ran),'selected_steps':int(best_step if early_stop else steps),
                 'validation_history':history,'best_validation_nll':(best if early_stop else None),
                 'normalization_source':model.normalization_source,'normalization_sha256':norm_sha,
                 'fixed_scale_max':float(max(fs.tolist())),'dynamic_scale_max':float(max(ds.tolist()))}
  for variant in VARIANTS:
   started+=1;rec={'fit_index':started,'variant':variant,'phase':'internal','state':'STARTED','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
   prior=json.loads((out/'fit_ledger.json').read_text());prior['records'].append(rec);atomicj(out/'fit_ledger.json',prior);r['fits_started']=started;atomicj(out/'progress.json',r)
   try:
    model,info=fit_one(variant,train_mask,int(go['steps_max']),val_mask,True)
    torch.save(model.state_dict(),out/f'{variant}_internal.pt')
    rec.update(state='COMPLETED',**info,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());fits[(variant,'internal')]=info['selected_steps'];completed+=1;r['fits_completed']=completed;r['fit_count']+=1
   except BaseException as e:rec.update(state='FAILED',error=repr(e),finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());raise
   finally:
    prior=json.loads((out/'fit_ledger.json').read_text());prior['records'][-1]=rec;atomicj(out/'fit_ledger.json',prior);atomicj(out/'progress.json',r)
   steps=fits[(variant,'internal')]
   rec={'fit_index':started+1,'variant':variant,'phase':'full125_refit','state':'STARTED','selected_steps':steps,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
   prior=json.loads((out/'fit_ledger.json').read_text());prior['records'].append(rec);atomicj(out/'fit_ledger.json',prior);started+=1;r['fits_started']=started;atomicj(out/'progress.json',r)
   try:
    model,info=fit_one(variant,np.ones(len(x),bool),steps,None,False)
    torch.save(model.state_dict(),out/f'{variant}_full125.pt')
    rec.update(state='COMPLETED',**info,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());completed+=1;r['fits_completed']=completed;r['fit_count']+=1
   except BaseException as e:rec.update(state='FAILED',error=repr(e),finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());raise
   finally:
    prior=json.loads((out/'fit_ledger.json').read_text());prior['records'][-1]=rec;atomicj(out/'fit_ledger.json',prior);atomicj(out/'progress.json',r)
  if (started,completed,r['fit_count'])!=(4,4,4):raise ValueError('four-fit budget mismatch')
  r.update(status='COMPLETE_TRAIN_ONLY_NO_C3',elapsed_seconds=time.time()-t0,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 except BaseException as e:r.update(status='FAILED',error=repr(e),traceback=traceback.format_exc(),elapsed_seconds=time.time()-t0,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 finally:
  if 'signal' in sys.modules: signal.setitimer(signal.ITIMER_REAL,0)
  if out and out.exists():atomicj(out/'receipt.json',r)
  for f in reversed(locks):
   try:fcntl.flock(f,fcntl.LOCK_UN);f.close()
   except Exception:pass
  if receipt:
   receipt.parent.mkdir(parents=True,exist_ok=True)
   with receipt.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,ensure_ascii=False,allow_nan=True)
 print(json.dumps(r,indent=2,ensure_ascii=False));return r
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--go',required=True);args=ap.parse_args();z=run(args.go);sys.exit(0 if z['status']=='COMPLETE_TRAIN_ONLY_NO_C3' else 2)
