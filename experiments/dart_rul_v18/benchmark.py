"""Exact-GO serial V18 complete-window benchmark, immutable seeds and budgets."""
from pathlib import Path
import json,hashlib,datetime,fcntl,os,signal,time,traceback,sys
ROOT=Path('/home/yndx/zxk/rul');HERE=Path(__file__).resolve().parent;OLD=ROOT/'experiments/isu_irregular_rul_seed42_v1'
sys.path.insert(0,str(OLD));sys.path.insert(0,str(HERE))
SOURCES=[HERE/n for n in ['protocol.json','data_protocol.py','hgb_models.py','neural_models.py','distributions.py','evaluate.py','benchmark.py']]+[OLD/n for n in ['train_eval.py','baselines.py','data_adapter.py']]
ASSETS=[OLD/'run_20261020_main'/n for n in ['hgb_dynamic.joblib','hgb_dynamic_oof_residuals.npy','hgb_dynamic_oof_cell_equal_weights.npy']]
COHORT=ROOT/'reports/isu_ilcc_capacity_probe_20261020_root/cohort.json';MANIFEST=ROOT/'reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json';DATA=ROOT/'data/processed/ISU_ILCC_DataV2_v1';STATE=ROOT/'automation/state/coordinator.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def maps(paths):return {str(p.relative_to(ROOT)):sha(p) for p in paths}
def canonical(d):return hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def atomic(p,d):
 p=Path(p);q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(d,indent=2,allow_nan=True));os.replace(q,p)
def owner(who):
 from train_eval import validate_owner
 return validate_owner(STATE,who)
def run(go_path):
 start=time.time();rec={'status':'PREFLIGHT_FAILED','CPU_fits_started':0,'CPU_fits_completed':0,'neural_fits_started':0,'neural_fits_completed':0,'optimizer_steps':0,'inference_calls':0,'locked_payload_reads':0};locks=[];out=None;g={};receipt=HERE/'preflight_failure.json'
 try:
  g=json.loads(Path(go_path).read_text());receipt=Path(g['receipt_path'])
  assert g['status']=='APPROVED' and g['allow_fit'] is True and g['seeds']==[42,13,77]
  assert g['fit_budget']=={'CPU_estimators':21,'neural_fits':12,'optimizer_steps':3600}
  assert g['source_sha256']==maps(SOURCES) and g['asset_sha256']==maps(ASSETS)
  assert g['cohort_sha256']==sha(COHORT) and g['manifest_sha256']==sha(MANIFEST)
  assert g['code_manifest_sha256']==canonical({'source_sha256':maps(SOURCES),'asset_sha256':maps(ASSETS)})
  issued=datetime.datetime.fromisoformat(g['issued_utc']);assert -60<=(datetime.datetime.now(datetime.timezone.utc)-issued).total_seconds()<=86400
  assert g['max_runtime_seconds']<=10800 and g['max_inference_calls']<=120000
  out=Path(g['output_path']);assert out.parent==HERE/'runs' and not out.exists() and not receipt.exists()
  assert g['owner_thread_id']=='01a1598a-bcaa-7443-9579-c48ee2303172';owner(g['owner_thread_id'])
  for p in [ROOT/'automation/state/online_survival_cpu.lock',ROOT/'automation/locks/isu_irregular_rul_cpu.lock']:
   f=p.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  owner(g['owner_thread_id']);assert json.loads(Path(go_path).read_text())==g
  claim=ROOT/'automation/locks/dart_v18_claims'/g['request_id'];claim.parent.mkdir(parents=True,exist_ok=True)
  with claim.open('x') as f:f.write(sha(go_path))
  out.mkdir(parents=True,exist_ok=False)
  rec.update(status='RUNNING',request_id=g['request_id'],GO_sha256=sha(go_path),source_sha256=maps(SOURCES),asset_sha256=maps(ASSETS))
  def alarm(*_):raise TimeoutError('approved V18 runtime exhausted')
  signal.signal(signal.SIGALRM,alarm);signal.alarm(g['max_runtime_seconds'])
  from train_eval import load_split
  from data_protocol import make_examples,weight_cells
  from hgb_models import train_models as train_hgb,HGBFullWindow
  from neural_models import train_models as train_neural
  from evaluate import evaluate_models,summarize,write_csv,temporal_consistency
  import numpy as np,joblib
  cells=load_split(COHORT,DATA,MANIFEST)
  tr=make_examples([c for c in cells if c['role']=='train']);dev=make_examples([c for c in cells if c['role']=='development'])
  assert len(tr)==6870 and len(dev)==3765 and {x['cell_id'] for x in tr}.isdisjoint({x['cell_id'] for x in dev})
  assert all(x['x_query'].shape==(74,) and x['x_anchor'].shape==(74,) for x in tr+dev)
  assert all(abs(x['delta_weeks']-(x['query_epoch']-x['last_arrival_epoch'])/604800.)<1e-10 for x in tr+dev)
  rec['data']={'train_examples':len(tr),'dev_examples':len(dev),'train_cells':len({x['cell_id'] for x in tr}),'dev_cells':len({x['cell_id'] for x in dev})}
  ledger=[]
  def count(kind,event,name,seed):
   key=kind+'_fits_'+('started' if event=='start' else 'completed')
   rec[key]+=1;limit=g['fit_budget']['CPU_estimators' if kind=='CPU' else 'neural_fits']
   if rec[key]>limit:raise RuntimeError('exact fit cap exceeded')
   ledger.append({'kind':kind,'event':event,'name':name,'seed':seed,'elapsed':time.time()-start});atomic(out/'fit_ledger.json',ledger);atomic(out/'progress.json',rec)
  def step(name,n,loss,seed):
   rec['optimizer_steps']+=1
   if rec['optimizer_steps']>3600:raise RuntimeError('optimizer step cap exceeded')
   rec['last_step']={'seed':seed,'model':name,'step':int(n),'loss':float(loss)}
   if rec['optimizer_steps']%10==0:atomic(out/'progress.json',rec)
  all_models={}
  # Finish every predetermined fit before any development prediction.
  for seed in g['seeds']:
   assert maps(SOURCES)==g['source_sha256'];owner(g['owner_thread_id']);sd=out/('seed'+str(seed));sd.mkdir();(sd/'hgb').mkdir();(sd/'neural').mkdir()
   hm=train_hgb(tr,seed,sd/'hgb',on_fit=lambda ev,n,s=seed:count('CPU',ev,n,s))
   nm=train_neural(tr,seed,sd/'neural',epochs=300,on_fit=lambda ev,n,s=seed:count('neural',ev,n,s),on_step=lambda n,i,l,s=seed:step(n,i,l,s))
   all_models[seed]={**hm,**nm}
  assert rec['CPU_fits_completed']==21 and rec['neural_fits_completed']==12 and rec['optimizer_steps']==3600
  rec['all_fits_complete_before_dev_inference']=True;atomic(out/'progress.json',rec)
  def predcount():
   rec['inference_calls']+=1
   if rec['inference_calls']>g['max_inference_calls']:raise RuntimeError('inference cap exceeded')
  old=HGBFullWindow(joblib.load(ASSETS[0]),np.load(ASSETS[1]),np.load(ASSETS[2]))
  refdir=out/'reference';refdir.mkdir();ref=evaluate_models({'existing_hgb':old},dev,42,refdir,predcount)
  rows=[];consistency=[]
  for seed,models in all_models.items():
   sd=out/('seed'+str(seed));rr=evaluate_models(models,dev,seed,sd,predcount,ref)
   rows.extend(rr)
   for x in temporal_consistency(models,dev,predcount):consistency.append(dict(x,seed=seed))
  summary,cellmetrics,reliability=summarize(rows)
  write_csv(out/'arm_summary.csv',summary);write_csv(out/'cell_metrics.csv',cellmetrics);write_csv(out/'reliability_bins.csv',reliability);atomic(out/'temporal_consistency.json',consistency)
  rec.update(status='SUCCESS',prediction_rows=len(rows),source_role_C4_reads=0,elapsed_seconds=time.time()-start)
 except Exception as ex:
  rec.update(status='FAILED',error=repr(ex),traceback=traceback.format_exc(),elapsed_seconds=time.time()-start)
 finally:
  signal.alarm(0);rec['elapsed_seconds']=time.time()-start
  if receipt.exists():receipt=receipt.with_name(receipt.stem+'_'+str(time.time_ns())+'.failure.json')
  receipt.parent.mkdir(exist_ok=True)
  with receipt.open('x') as f:json.dump(rec,f,indent=2,allow_nan=True)
  for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
 return rec
if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--go',required=True);a=ap.parse_args();z=run(a.go);print(json.dumps(z,indent=2));sys.exit(0 if z['status']=='SUCCESS' else 2)
