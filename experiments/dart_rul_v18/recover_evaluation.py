"""No-fit recovery: load the completed V18 models after scalar CDF adapter repair."""
from pathlib import Path
import sys,os,json,time,datetime,fcntl,signal,hashlib,traceback,csv
ROOT=Path('/home/yndx/zxk/rul');HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'experiments/isu_irregular_rul_seed42_v1'));sys.path.insert(0,str(HERE))
from benchmark import sha,maps,canonical,owner,COHORT,MANIFEST,DATA,SOURCES,ASSETS
def source_paths():return SOURCES+[HERE/'recover_evaluation.py']
def checkpoint_paths():
 out=[]
 for seed in [42,13,77]:
  h=HERE/'runs/run1'/('seed'+str(seed))/'hgb';n=h.parent/'neural'
  out.extend(h/x for x in ['hgb_fullwindow_full.joblib','hgb_fullwindow_distribution.joblib','hgb_hurdle_classifier_full.joblib','hgb_hurdle_positive_full.joblib','hgb_hurdle_distribution.joblib'])
  out.extend(n/(x+'.checkpoint.pt') for x in ['risk_query','joint_query','dart_joint','dart_split'])
 return out
def reference_rows():
 p=HERE/'runs/run1/reference/predictions.csv';rs=list(csv.DictReader(p.open()))
 strings={'model','cell_id','arm','history_key'}
 for r in rs:
  for k,v in list(r.items()):
   if k in strings:continue
   if k=='known_event':r[k]=(v=='True');continue
   if v!='':r[k]=float(v)
  r['seed']=int(r['seed']);r['y_event']=int(r['y_event'])
 return rs
def load_models(seed,rec):
 import joblib,numpy as np,torch
 from hgb_models import HGBFullWindow,HGBHurdle
 from neural_models import _make_model,_Predictor
 p=HERE/'runs/run1'/('seed'+str(seed));h=p/'hgb';n=p/'neural'
 def jl(name):rec['HGB_asset_loads']+=1;return joblib.load(h/name)
 a=jl('hgb_fullwindow_full.joblib');ad=jl('hgb_fullwindow_distribution.joblib')
 b=jl('hgb_hurdle_classifier_full.joblib');c=jl('hgb_hurdle_positive_full.joblib');bd=jl('hgb_hurdle_distribution.joblib')
 models={'hgb_fullwindow':HGBFullWindow(a,ad['residuals'],ad['residual_weights']),'hgb_hurdle':HGBHurdle(b,c,bd['residuals'],bd['residual_weights'])}
 for name in ['risk_query','joint_query','dart_joint','dart_split']:
  cp=torch.load(n/(name+'.checkpoint.pt'),map_location='cpu',weights_only=True);rec['neural_checkpoint_loads']+=1
  assert cp['complete'] is True and cp['step']==300 and cp['seed']==seed and cp['model']==name
  module,family,input_key=_make_model(name);module=module.to(dtype=torch.float64);module.load_state_dict(cp['model_state_dict'],strict=True)
  models[name]=_Predictor(name,module,cp['scalers'],input_key,family)
 return models
def run(gopath):
 started=time.time();rec={'status':'PREFLIGHT_FAILED','new_fits':0,'optimizer_steps':0,'inference_calls':0,'HGB_asset_loads':0,'neural_checkpoint_loads':0,'locked_payload_reads':0};held=[];out=None;receipt=HERE/'recovery_preflight_failure.json'
 try:
  g=json.loads(Path(gopath).read_text());receipt=Path(g['receipt_path'])
  assert g['status']=='APPROVED_SAVED_CHECKPOINT_EVALUATION_ONLY' and g['allow_fit'] is False and g['new_fits']==g['optimizer_steps']==0
  assert g['source_sha256']==maps(source_paths()) and g['checkpoint_sha256']==maps(checkpoint_paths())
  assert g['manifest_sha256']==sha(MANIFEST) and g['cohort_sha256']==sha(COHORT)
  prior=HERE/'run1_receipt.json';old=json.loads(prior.read_text());assert g['prior_receipt_sha256']==sha(prior) and old['CPU_fits_completed']==21 and old['neural_fits_completed']==12 and old['optimizer_steps']==3600
  assert g['reference_predictions_sha256']==sha(HERE/'runs/run1/reference/predictions.csv')
  assert g['code_manifest_sha256']==canonical({'source_sha256':maps(source_paths()),'checkpoint_sha256':maps(checkpoint_paths())})
  issued=datetime.datetime.fromisoformat(g['issued_utc']);assert -60<=(datetime.datetime.now(datetime.timezone.utc)-issued).total_seconds()<=86400
  out=Path(g['output_path']);assert out.parent==HERE and not out.exists() and not receipt.exists()
  assert 1<=g['max_inference_calls']<=90000 and 1<=g['max_runtime_seconds']<=1800
  owner(g['owner_thread_id'])
  for p in [ROOT/'automation/state/online_survival_cpu.lock',ROOT/'automation/locks/isu_irregular_rul_cpu.lock']:
   f=p.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);held.append(f)
  owner(g['owner_thread_id']);assert json.loads(Path(gopath).read_text())==g
  claim=ROOT/'automation/locks/dart_v18_claims'/g['request_id']
  with claim.open('x') as f:f.write(sha(gopath))
  def alarm(*_):raise TimeoutError('recovery inference runtime cap')
  signal.signal(signal.SIGALRM,alarm);signal.alarm(g['max_runtime_seconds'])
  rec.update(status='RUNNING',request_id=g['request_id'],GO_sha256=sha(gopath),prior_consumed_inference_calls=old['inference_calls'])
  from train_eval import load_split
  from data_protocol import make_examples
  from evaluate import evaluate_models,summarize,write_csv,temporal_consistency
  cells=load_split(COHORT,DATA,MANIFEST);dev=make_examples([c for c in cells if c['role']=='development']);assert len(dev)==3765
  refs=reference_rows();assert len(refs)==3765
  out.mkdir(exist_ok=False);rows=[];consistency=[]
  def count():
   rec['inference_calls']+=1
   if rec['inference_calls']>g['max_inference_calls']:raise RuntimeError('recovery inference cap')
  for seed in [42,13,77]:
   owner(g['owner_thread_id']);models=load_models(seed,rec);sd=out/('seed'+str(seed));sd.mkdir()
   rows.extend(evaluate_models(models,dev,seed,sd,count,refs))
   for x in temporal_consistency(models,dev,count):consistency.append(dict(x,seed=seed))
   (out/'progress.json').write_text(json.dumps(rec,indent=2))
  summary,cellmetrics,reliability=summarize(rows);write_csv(out/'arm_summary.csv',summary);write_csv(out/'cell_metrics.csv',cellmetrics);write_csv(out/'reliability_bins.csv',reliability)
  (out/'temporal_consistency.json').write_text(json.dumps(consistency,indent=2))
  assert rec['HGB_asset_loads']==15 and rec['neural_checkpoint_loads']==12
  rec.update(status='SUCCESS',prediction_rows=len(rows),existing_reference_predictions_reused=3765,all_prior_fits_preserved=True)
 except Exception as ex:rec.update(status='FAILED',error=repr(ex),traceback=traceback.format_exc())
 finally:
  signal.alarm(0);rec['elapsed_seconds']=time.time()-started
  if receipt.exists():receipt=receipt.with_name(receipt.stem+'_'+str(time.time_ns())+'.failure.json')
  with receipt.open('x') as f:json.dump(rec,f,indent=2,allow_nan=True)
  for f in reversed(held):fcntl.flock(f,fcntl.LOCK_UN);f.close()
 return rec
if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--go',required=True);a=ap.parse_args();z=run(a.go);print(json.dumps(z,indent=2));sys.exit(0 if z['status']=='SUCCESS' else 2)
