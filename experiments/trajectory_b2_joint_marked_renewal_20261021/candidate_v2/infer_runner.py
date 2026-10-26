#!/home/yndx/miniconda3/envs/a40_env/bin/python
"""B2-v2.1 C3 (source63 development) trajectory inference. Zero fits, no C4, no raw archive.

GO-gated: pinned cohort/manifest/RPT-asset hashes, four checkpoint hashes, frozen rollout
geometry (256 accepted trajectories, <=50000 proposals, acceptance floor 1%, <=512 valid
checks per proposal, 128-week horizon) and the two predeclared zero-fit controls
(no-arrival conditioning off; fixed gap with mixture-posterior conditional marks).
"""
from __future__ import annotations
import os
os.environ['OMP_NUM_THREADS']='4';os.environ['MKL_NUM_THREADS']='4';os.environ['OPENBLAS_NUM_THREADS']='4'
os.environ['CUDA_VISIBLE_DEVICES']='0'
import argparse,csv,datetime,fcntl,hashlib,json,math,pathlib,signal,sys,time,traceback
import numpy as np
ROOT=pathlib.Path('/home/yndx/zxk/rul');HERE=ROOT/'experiments/trajectory_b2_joint_marked_renewal_20261021/candidate_v2'
OWNER='01a15c3a-1a06-7d61-8517-27b70b246183'
COHORT=ROOT/'reports/isu_ilcc_capacity_probe_20261020_root/cohort.json'
MANIFEST=ROOT/'reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json'
DATA=ROOT/'data/processed/ISU_ILCC_DataV2_v1'
RPT_MANIFEST=ROOT/'reports/multisource_20261021_signals/all188_rpt_features_v1/manifest.json'
WEEK=604800.0;THRESHOLD_AH=.20
CPU_LOCKS=('automation/state/online_survival_cpu.lock','automation/locks/isu_irregular_rul_cpu.lock')
GPU_LOCK='automation/locks/multirate_state_20261021_gpu.lock'
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def atomicj(p,x):
 t=pathlib.Path(str(p)+'.tmp');t.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=True),encoding='utf-8');os.replace(t,p)
def qtl(x,p=0.5):
 v=np.sort(np.asarray(x,dtype=float));n=len(v)
 return float('nan') if n==0 else float(np.quantile(v,p))
def load_dev_cells():
 sys.path[:0]=[str(ROOT/'experiments/isu_irregular_rul_seed42_v1'),str(ROOT/'experiments/dart_rul_v18')]
 from data_adapter import load_reviewed_cell
 co=json.loads(COHORT.read_text(encoding='utf-8'));ma=json.loads(MANIFEST.read_text(encoding='utf-8'))
 if ma.get('status')!='PASS':raise ValueError('data manifest not PASS')
 ids={c for c,r in co['roles'].items() if r in ('train','development')}
 if set(ma['files'])!=ids:raise ValueError('manifest/cohort ID mismatch')
 dev=sorted(c for c,r in co['roles'].items() if r=='development')
 if any(c.endswith('C4') for c in dev):raise ValueError('C4 cell in development cohort')
 cells=[]
 for cid in dev:
  p=DATA/(cid+'.json')
  if sha(p)!=ma['files'][cid]['sha256']:raise ValueError('C3 source hash mismatch '+cid)
  c=load_reviewed_cell(p,'development')
  if c['cell_id']!=cid:raise ValueError('C3 ID mismatch')
  cells.append(c)
 return cells,dev
def rpt_manifest_map():
 m=json.loads(RPT_MANIFEST.read_text(encoding='utf-8'))
 assets=None
 for key in ('inventory','assets','files','items'):
  if isinstance(m.get(key),list) and m[key]:assets=m[key];break
 if assets is None:raise ValueError('RPT manifest has no inventory list')
 out={}
 for a in assets:
  cid=str(a.get('cell_id') or a.get('id') or '')
  if not cid:raise ValueError('RPT manifest asset without cell_id')
  p=pathlib.Path(str(a['path']))
  if not p.is_absolute():p=ROOT/p
  out[cid]={'path':str(p),'sha256':str(a['sha256']),'role':str(a.get('role',''))}
 return out
def run(go_path):
 t0=time.time();out=None;receipt=None;locks=[];r={'status':'INFER_PREFLIGHT_FAILED','fit_count':0,'C4_reads':0,'C3_reads':0,'queries':0}
 try:
  go=json.loads(pathlib.Path(go_path).read_text(encoding='utf-8'))
  req=('status','allow_inference','allow_fit','request_id','owner_thread_id','issued_utc','max_runtime_seconds',
       'cohort_path','cohort_sha256','manifest_path','manifest_sha256','rpt_manifest_path','rpt_manifest_sha256',
       'source_sha256','checkpoints','output_path','receipt_path','data_scope','device','query_contract')
  if any(k not in go for k in req):raise ValueError('GO missing required field')
  if go['status']!='APPROVED_C3_INFERENCE' or go['allow_inference'] is not True or go['allow_fit'] is not False:raise ValueError('GO is not C3-inference-only')
  if go['owner_thread_id']!=OWNER:raise ValueError('owner mismatch')
  if go['data_scope']!='C3_source63_development_only_no_C4_no_raw':raise ValueError('data scope mismatch')
  if str(go['device'])!='cuda:0':raise ValueError('GO must pin cuda:0')
  qc=go['query_contract']
  if (int(qc['n_samples']),int(qc['max_proposals']),float(qc['min_accept_rate']),int(qc['max_valid_checks']),
      float(qc['max_weeks']),int(qc['seed']))!=(256,50000,0.01,512,128.0,42):raise ValueError('query contract mismatch')
  if sorted(qc['conditions'])!=['condition_off','fixed_gap','main']:raise ValueError('condition set mismatch')
  max_seconds_per_query=float(qc.get('max_seconds_per_query',60.0))
  if not 5.0<=max_seconds_per_query<=600.0:raise ValueError('max_seconds_per_query out of bound')
  issued=datetime.datetime.fromisoformat(go['issued_utc'].replace('Z','+00:00'))
  if abs((datetime.datetime.now(datetime.timezone.utc)-issued).total_seconds())>86400:raise ValueError('stale inference GO')
  runtime=int(go['max_runtime_seconds'])
  if not 60<=runtime<=10800:raise ValueError('runtime outside 60s..3h')
  coord=json.loads((ROOT/'automation/state/coordinator.json').read_text(encoding='utf-8'))
  if coord.get('owner')!=OWNER:raise ValueError('live coordinator owner changed')
  if sha(COHORT)!=go['cohort_sha256'] or sha(MANIFEST)!=go['manifest_sha256'] or sha(RPT_MANIFEST)!=go['rpt_manifest_sha256']:raise ValueError('cohort/manifest hash mismatch')
  sources={n:sha(HERE/n) for n in ('infer_runner.py','model.py','rollout.py','target_builder.py','PROTOCOL_V2.md')}
  if sources!=go['source_sha256']:raise ValueError('source hash mismatch')
  ck={}
  for variant,spec in go['checkpoints'].items():
   if variant not in ('joint','independent'):raise ValueError('unknown checkpoint variant '+variant)
   path=HERE/spec['path'];got=sha(path)
   if got!=spec['sha256']:raise ValueError('checkpoint hash mismatch '+variant)
   ck[variant]={'path':str(path),'sha256':got}
  out=(ROOT/go['output_path']).resolve();receipt=pathlib.Path(go['receipt_path'])
  if HERE.resolve() not in out.parents or out.exists():raise ValueError('output must be fresh under candidate_v2')
  if receipt.parent.resolve()!=(HERE/'receipts').resolve() or receipt.exists():raise ValueError('receipt path invalid')
  deadline=time.monotonic()+runtime
  def alarm(signum,frame):raise TimeoutError('inference GO runtime deadline reached')
  signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,runtime)
  for lp in [ROOT/p for p in CPU_LOCKS]+[ROOT/GPU_LOCK]:
   f=lp.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  out.mkdir(parents=True,exist_ok=False)
  import torch
  torch.set_num_threads(4);torch.set_num_interop_threads(1)
  if not torch.cuda.is_available():raise RuntimeError('CUDA required but unavailable')
  torch.cuda.set_device(0);dev_t=torch.device('cuda:0')
  from model import JointMarkedMixtureNet
  from rollout import forecast_rul
  import target_builder as TB
  cells,dev_ids=load_dev_cells()
  rpt_map=rpt_manifest_map()
  missing=[c['cell_id'] for c in cells if c['cell_id'] not in rpt_map]
  if missing:raise ValueError('missing RPT features for dev cells: '+repr(missing[:5]))
  wrong_role=[c for c in cells if rpt_map[c['cell_id']]['role']!='development']
  if wrong_role:raise ValueError('dev cell RPT asset role mismatch: '+repr([c['cell_id'] for c in wrong_role][:5]))
  models={}
  for variant,spec in ck.items():
   m=JointMarkedMixtureNet(TB.FIXED_DIM);m.load_state_dict(torch.load(spec['path'],map_location='cpu',weights_only=False))
   m.to(dev_t).eval();models[variant]=m
  r.update(status='INFERENCE_RUNNING',request_id=go['request_id'],go_sha256=sha(go_path),source_sha256=sources,
           cohorts={'cohort_sha256':sha(COHORT),'manifest_sha256':sha(MANIFEST),'rpt_manifest_sha256':sha(RPT_MANIFEST)},
           development_cells=len(dev_ids),checkpoints={k:v['sha256'] for k,v in ck.items()},device='cuda:0')
  atomicj(out/'progress.json',r)
  preds=[];samples={};failures=[];query_no=0;known_zero_count=0
  shard_no=0;shard_keys={}
  csv_path=out/'predictions_c3_rul.csv';fields=['query_id','cell_id','group_id','arm','query_epoch','anchor_stop_epoch','anchor_index','visible_records','model','variant','condition','n_samples','rul_mean','rul_q10','rul_q50','rul_q90','rul_sd','tail_gt_128w_mass','proposals','acceptance_rate','effective_sample_size','numerical_rejections','epoch_dtype','fixed_gap_weeks','condition_on_no_arrival','target_rul_weeks','censored_no_event_observed','event_known_by_query']
  csv_f=csv_path.open('w',newline='',encoding='utf-8');csv_w=csv.DictWriter(csv_f,fieldnames=fields,extrasaction='ignore');csv_w.writeheader();csv_f.flush()
  fail_path=out/'query_failures.jsonl';fail_f=fail_path.open('w',encoding='utf-8')
  def emit(row,arr):
   nonlocal shard_no
   csv_w.writerow(row);csv_f.flush();preds.append(row)
   if arr is not None:
    samples[row['query_id']]=arr
    shard_keys[row['query_id']]=arr
   if len(shard_keys)>=200:
    np.savez_compressed(out/f'samples_shard_{shard_no:03d}.npz',**shard_keys);shard_no+=1;shard_keys.clear()
   if len(preds)%25==0:
    r.update(queries=len(preds),samples=len(samples),failures=len(failures),known_zero_queries=known_zero_count,elapsed_seconds=time.time()-t0)
    atomicj(out/'progress.json',r)
  def emit_failure(rec):
   failures.append(rec);fail_f.write(json.dumps(rec,ensure_ascii=False)+'\n');fail_f.flush()
  def base_row(key,cid,cell,arm,qepoch,anchor,aidx,nvisible,variant,cond,last_gap,target,known):
   return {'query_id':key,'cell_id':cid,'group_id':str(cell.get('group_id','')),'arm':arm,
    'query_epoch':qepoch,'anchor_stop_epoch':float(anchor['stop_epoch']),'anchor_index':aidx,
    'visible_records':nvisible,'model':variant,'variant':variant,'condition':cond,
    'fixed_gap_weeks':(last_gap if cond=='fixed_gap' else ''),
    'target_rul_weeks':('' if target is None else float(target)),
    'censored_no_event_observed':bool(target is None),'event_known_by_query':bool(known)}
  # Arm-major order so a complete two-arm panel exists even if the delayed arm is
  # expensive; per-query wall-clock budget bounds pathological rejection loops.
  for arm in ('raw','sparse2','delay7d'):
   for cell in cells:
     cid=str(cell['cell_id'])
     rows=sorted(cell['records'],key=lambda x:(float(x['stop_epoch']),int(x['source_rpt_index'])))
     if len(rows)<4:continue
     if any(float(x['capacityAh'])<=0 for x in rows):raise ValueError('nonpositive source capacity '+cid)
     rpt_path=rpt_map[cid]['path']
     if sha(rpt_path)!=rpt_map[cid]['sha256']:raise ValueError('RPT feature asset hash mismatch '+cid)
     cache=TB._rpt_index(rpt_path,cid)
     event=next((x for x in rows if float(x['capacityAh'])<=THRESHOLD_AH),None)
     event_epoch=None if event is None else float(event['stop_epoch'])
     warmup_idx=int(rows[1]['source_rpt_index'])
     policy_rows=TB.data_protocol._arm_records(rows,1,arm)
     seen=set()
     for qrow in rows:
      qepoch=float(qrow['stop_epoch'])
      if qepoch<float(rows[1]['stop_epoch'])+WEEK:continue
      visible=[dict(x) for x in policy_rows if float(x['arrival_epoch'])<=qepoch]
      if len(visible)<3:continue
      anchor=visible[-1];aidx=int(anchor['source_rpt_index'])
      if (arm,aidx) in seen:continue
      seen.add((arm,aidx))
      last_gap=(float(visible[-1]['stop_epoch'])-float(visible[-2]['stop_epoch']))/WEEK
      target=None if event_epoch is None else max((event_epoch-qepoch)/WEEK,0.0)
      known=any(float(x['capacityAh'])<=THRESHOLD_AH for x in visible)
      if known:
       known_zero_count+=1
       for variant in models:
        for cond in qc['conditions']:
         query_no+=1;key=f'{query_no:06d}'
         samples[key]=np.zeros(int(qc['n_samples']),dtype=np.float32)
         row=base_row(key,cid,cell,arm,qepoch,anchor,aidx,len(visible),variant,cond,last_gap,target,True)
         row.update(n_samples=int(qc['n_samples']),rul_mean=0.0,rul_q10=0.0,rul_q50=0.0,rul_q90=0.0,rul_sd=0.0,
                    tail_gt_128w_mass=0.0,proposals=0,acceptance_rate=1.0,
                    effective_sample_size=float(qc['n_samples']),epoch_dtype='torch.float64',
                    condition_on_no_arrival=cond!='condition_off')
         emit(row,np.zeros(int(qc['n_samples']),dtype=np.float32))
       continue
      if time.monotonic()>=deadline:raise TimeoutError('deadline before query rollout')
      fixed=TB._f0_and_rpt_anchor(cell,visible,float(anchor['stop_epoch']),qepoch,cache)
      TB._dynamic_from_prefix(visible,float(anchor['stop_epoch']))
      out_query_start=time.monotonic()
      for variant,model in models.items():
       for cond in qc['conditions']:
        query_no+=1
        kw=dict(seed=int(qc['seed']),max_proposals=int(qc['max_proposals']),n_samples=int(qc['n_samples']),
                min_accept_rate=float(qc['min_accept_rate']),max_weeks=float(qc['max_weeks']),
                max_valid_checks=int(qc['max_valid_checks']),proposal_batch_size=64)
        if cond=='condition_off':kw['condition_on_no_arrival']=False
        if cond=='fixed_gap':kw['fixed_gap_weeks']=last_gap
        try:
         if time.monotonic()-out_query_start>max_seconds_per_query:
          raise TimeoutError(f'query wall-clock budget {max_seconds_per_query}s exceeded')
         res=forecast_rul(model,fixed,visible,qepoch,warmup_idx,arm,variant,**kw)
        except Exception as e:
         emit_failure({'cell_id':cid,'arm':arm,'query_epoch':qepoch,'anchor_index':aidx,'model':variant,'condition':cond,'error':repr(e)})
         continue
        key=f'{query_no:06d}'
        sv=res['samples']
        row=base_row(key,cid,cell,arm,qepoch,anchor,aidx,len(visible),variant,cond,last_gap,target,False)
        row.update(n_samples=len(sv),rul_mean=float(np.mean(sv)),rul_q10=qtl(sv,.10),rul_q50=qtl(sv,.50),rul_q90=qtl(sv,.90),
                   rul_sd=(float(np.std(sv,ddof=1)) if len(sv)>1 else float('nan')),
                   tail_gt_128w_mass=float(res['tail_mass']),proposals=int(res['proposals']),
                   acceptance_rate=float(res['acceptance_rate']),effective_sample_size=float(res['effective_sample_size']),
                  numerical_rejections=int(res.get('numerical_rejections',0)),
                   epoch_dtype=str(res['epoch_dtype']),condition_on_no_arrival=bool(res['condition_on_no_arrival']))
        emit(row,np.asarray(sv,dtype=np.float32))
      if time.monotonic()>=deadline:raise TimeoutError('deadline after query rollout')
  if shard_keys:
   np.savez_compressed(out/f'samples_shard_{shard_no:03d}.npz',**shard_keys);shard_no+=1;shard_keys.clear()
  csv_f.close();fail_f.close()
  if not preds:raise ValueError('no C3 queries produced any prediction')
  merged={}
  for i in range(shard_no):
   with np.load(out/f'samples_shard_{i:03d}.npz',allow_pickle=False) as z:
    for k in z.files:merged[k]=z[k]
  if len(merged)!=len(preds):raise ValueError(f'sample/prediction count mismatch {len(merged)} vs {len(preds)}')
  np.savez_compressed(out/'c3_rul_samples.npz',**merged)
  atomicj(out/'query_failures.json',{'failures':failures,'count':len(failures)})
  arms={a:sum(1 for p in preds if p['arm']==a) for a in ('raw','sparse2','delay7d')}
  conds={c:sum(1 for p in preds if p['condition']==c) for c in qc['conditions']}
  total_attempts=len(preds)+len(failures)
  failure_rate=(len(failures)/total_attempts) if total_attempts else 1.0
  if failure_rate>0.10:
   r.update(status='C3_INFERENCE_INCOMPLETE_TOO_MANY_FAILURES',failure_rate=failure_rate,
            failure_gate_note='More than 10% of query rollouts raised errors; partial output retained for diagnosis only and must not be used as a result.',
            queries=len(preds),samples=len(samples),arms=arms,conditions=conds,known_zero_queries=known_zero_count,
            prediction_rows=len(preds),failures=len(failures),C3_reads=len(cells),C4_reads=0,fit_count=0,
            query_contract=qc,elapsed_seconds=time.time()-t0,
            finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
   raise RuntimeError(f'inference failure rate {failure_rate:.3f} exceeds 0.10 gate; not a usable result')
  r.update(status='C3_INFERENCE_COMPLETE',failure_rate=failure_rate,queries=len(preds),samples=len(samples),arms=arms,conditions=conds,
           known_zero_queries=known_zero_count,prediction_rows=len(preds),failures=len(failures),
           C3_reads=len(cells),C4_reads=0,fit_count=0,query_contract=qc,
           elapsed_seconds=time.time()-t0,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 except BaseException as e:
  r.update(status='FAILED',error=repr(e),traceback=traceback.format_exc(),elapsed_seconds=time.time()-t0,
           finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 finally:
  if 'signal' in sys.modules:signal.setitimer(signal.ITIMER_REAL,0)
  if out and out.exists():atomicj(out/'receipt.json',r)
  for f in reversed(locks):
   try:fcntl.flock(f,fcntl.LOCK_UN);f.close()
   except Exception:pass
  if receipt:
   receipt.parent.mkdir(parents=True,exist_ok=True)
   with receipt.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,ensure_ascii=False,allow_nan=True)
 print(json.dumps(r,indent=2,ensure_ascii=False)[:3000]);return r
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--go',required=True);args=ap.parse_args();z=run(args.go);sys.exit(0 if z['status']=='C3_INFERENCE_COMPLETE' else 2)
