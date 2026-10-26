#!/home/yndx/miniconda3/envs/a40_env/bin/python
from __future__ import annotations
import argparse,datetime,hashlib,json,os,pathlib,sys,traceback,signal,time
ROOT=pathlib.Path('/home/yndx/zxk/rul'); HERE=ROOT/'experiments/trajectory_b2_joint_marked_renewal_20261021/candidate_v2'
OWNER='01a15c3a-1a06-7d61-8517-27b70b246183'
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def atomicj(p,x):
 t=pathlib.Path(str(p)+'.tmp');t.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8');os.replace(t,p)
def run(go_path):
 go=json.loads(pathlib.Path(go_path).read_text(encoding='utf-8'));out=None
 r={'status':'PREP_PREFLIGHT_FAILED','fits':0,'C3_reads':0,'C4_reads':0}
 try:
  req=('status','allow_prep','allow_fit','request_id','owner_thread_id','issued_utc','max_runtime_seconds','processed_manifest_path','processed_manifest_sha256','rpt_manifest_path','rpt_manifest_sha256','source_sha256','output_path','receipt_path','data_scope')
  if any(k not in go for k in req): raise ValueError('GO missing required field')
  if go['status']!='APPROVED_PREP_ONLY' or go['allow_prep'] is not True or go['allow_fit'] is not False: raise ValueError('GO is not prep-only')
  if go['owner_thread_id']!=OWNER or go['data_scope']!='train_C1_C2_processed_and_RPT_assets_only': raise ValueError('owner/data scope mismatch')
  coord=json.loads((ROOT/'automation/state/coordinator.json').read_text(encoding='utf-8'))
  if coord.get('owner')!=OWNER: raise ValueError('live coordinator owner changed')
  issued=datetime.datetime.fromisoformat(go['issued_utc'].replace('Z','+00:00'))
  if abs((datetime.datetime.now(datetime.timezone.utc)-issued).total_seconds())>86400: raise ValueError('stale PREP GO')
  runtime=int(go['max_runtime_seconds'])
  if not 60<=runtime<=7200: raise ValueError('PREP runtime out of bound')
  def alarm(signum,frame): raise TimeoutError('PREP GO runtime deadline reached')
  signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,runtime)
  sources={n:sha(HERE/n) for n in ('model.py','target_builder.py','prep_runner.py','fit_runner.py','rollout.py','PROTOCOL_V2.md','synthetic_check.py')}
  ext={
   'data_protocol.py':ROOT/'experiments/dart_rul_v18/data_protocol.py',
   'data_adapter.py':ROOT/'experiments/isu_irregular_rul_seed42_v1/data_adapter.py',
   'baselines.py':ROOT/'experiments/isu_irregular_rul_seed42_v1/baselines.py',
   'features.py':ROOT/'experiments/multisource_factorial_20261021/features.py',
   'cycle_asof_features.py':ROOT/'reports/multisource_20261021_signals/cycle_asof_features.py'}
  sources.update({n:sha(p) for n,p in ext.items()})
  if sources!=go['source_sha256']: raise ValueError('source hash mismatch')
  for k in ('processed_manifest','rpt_manifest'):
   path=go[k+'_path'];expected=go[k+'_sha256']
   if sha(path)!=expected: raise ValueError(k+' hash mismatch')
  out=(ROOT/go['output_path']).resolve()
  if HERE.resolve() not in out.parents or out.exists(): raise ValueError('output path must be fresh under candidate_v2')
  receipt=pathlib.Path(go['receipt_path'])
  if receipt.parent.resolve()!=(HERE/'receipts').resolve() or receipt.exists(): raise ValueError('receipt path invalid')
  out.mkdir(parents=True,exist_ok=False)
  from target_builder import build_train_examples
  data=build_train_examples(go['processed_manifest_path'],go['rpt_manifest_path'])
  import numpy as np
  np.savez_compressed(out/'train_anchor_suffixes.npz',**{k:v for k,v in data.items() if isinstance(v,np.ndarray)})
  metadata={k:v for k,v in data.items() if not isinstance(v,np.ndarray)}
  metadata.update({'status':'PREPARED_TRAIN_ONLY','fixed_dim':int(data['fixed'].shape[1]),'dynamic_dim':6,
                   'transition_rows':int(len(data['log_gap'])),'C3_reads':0,'C4_reads':0,'fits':0,
                   'processed_manifest_sha256':data['processed_manifest_sha256'],
                   'rpt_manifest_sha256':data['rpt_manifest_sha256'],
                   'source_sha256':sources,'go_sha256':sha(go_path),'request_id':go['request_id']})
  atomicj(out/'metadata.json',metadata);r.update(metadata,status='PREPARED_TRAIN_ONLY',output_path=str(out))
 except BaseException as e:
  r.update(status='PREP_FAILED',error=repr(e),traceback=traceback.format_exc())
 finally:
  signal.setitimer(signal.ITIMER_REAL,0)
  if out and out.exists(): atomicj(out/'receipt.json',r)
  if 'receipt' in locals():
   receipt.parent.mkdir(parents=True,exist_ok=True)
   with receipt.open('x',encoding='utf-8') as f: json.dump(r,f,indent=2,ensure_ascii=False)
 print(json.dumps(r,indent=2,ensure_ascii=False));return r
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--go',required=True);args=ap.parse_args();z=run(args.go);sys.exit(0 if z['status']=='PREPARED_TRAIN_ONLY' else 2)
