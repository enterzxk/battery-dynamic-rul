"""Matched information-value benchmark. Server-only execution; fresh exact GO."""
import os
os.environ.setdefault('OMP_NUM_THREADS','4')
os.environ.setdefault('MKL_NUM_THREADS','4')
import sys,json,pathlib,hashlib,datetime,fcntl,time,traceback,signal,collections
import numpy as np
R=pathlib.Path('/home/yndx/zxk/rul')
D=R/'experiments/multisource_information_20261021'
OLD=R/'experiments/isu_irregular_rul_seed42_v1';V18=R/'experiments/dart_rul_v18'
sys.path.insert(0,str(OLD));sys.path.insert(0,str(V18))
MAN=R/'reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json'
CO=R/'reports/isu_ilcc_capacity_probe_20261020_root/cohort.json'
SCALAR=['src_capacity_charge_C_2','src_capacity_discharge_C_2','src_capacity_charge_C_5','src_capacity_discharge_C_5']
CURVE=[f'C{rate}_{leg}_{kind}_at_V{v:.2f}' for rate in [2,5] for leg in ['charge','discharge'] for kind in ['Q','dQdV'] for v in np.linspace(3,4.2,25)]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def j(p):return json.loads(pathlib.Path(p).read_text())
def write(p,x):
 with pathlib.Path(p).open('x') as f:json.dump(x,f,indent=2,allow_nan=True)
def mapped_sources():
 paths=[pathlib.Path(__file__).resolve(),D/'protocol.json',V18/'data_protocol.py',V18/'hgb_models.py',V18/'evaluate.py',OLD/'train_eval.py',OLD/'baselines.py',OLD/'data_adapter.py']
 return {str(p.relative_to(R)):sha(p) for p in paths}
def features(e,cache,level):
 x=np.array(e['x_query'],float)
 if level=='F0':return x
 rr=e['visible_records'];cid=e['cell_id'];first=cache[cid][rr[0]['source_rpt_index']];last=cache[cid][rr[-1]['source_rpt_index']]
 assert float(rr[-1]['arrival_epoch'])<=e['query_epoch']
 keys=SCALAR+(CURVE if level=='F2' else [])
 def vector(d):
  f=d['values'];a=np.asarray([np.nan if f.get(k) is None else f[k] for k in keys],float)
  return a/.25
 a=vector(last);b=vector(first)
 dt=(rr[-1]['stop_epoch']-rr[0]['stop_epoch'])/604800.
 # Capacity magnitude, evolution from the first actually visible inspection.
 return np.r_[x,a,a-b,(a-b)/max(dt,1e-6)]
def foldsets(rows):
 ids=sorted({e['cell_id'] for e in rows});np.random.RandomState(42).shuffle(ids)
 return [set(ids[::2]),set(ids[1::2])]
def weights(rows):
 c=collections.Counter(e['cell_id'] for e in rows)
 return np.asarray([1/c[e['cell_id']] for e in rows])
def new(kind,task):
 if kind=='hgb':
  from sklearn.ensemble import HistGradientBoostingRegressor,HistGradientBoostingClassifier
  cls=HistGradientBoostingClassifier if task=='event' else HistGradientBoostingRegressor
  return cls(max_iter=150,max_leaf_nodes=15,l2_regularization=1.,random_state=42,early_stopping=False)
 from catboost import CatBoostRegressor,CatBoostClassifier
 cls=CatBoostClassifier if task=='event' else CatBoostRegressor
 return cls(iterations=400,depth=5,learning_rate=.04,l2_leaf_reg=3,random_seed=42,thread_count=4,verbose=False,allow_writing_files=False,loss_function='Logloss' if task=='event' else 'RMSE')
def run(gp):
 g=j(gp);rec={'status':'PREFLIGHT','CPU_fits_started':0,'CPU_fits_completed':0,'old_model_loads':0,'prediction_rows':0,'C4_payload_reads':0};locks=[];start=time.time();out=None
 try:
  assert g['status']=='APPROVED' and g['allow_fit'] is True and g['fit_budget']==20
  assert g['source_sha256']==mapped_sources() and g['manifest_sha256']==sha(MAN) and g['cohort_sha256']==sha(CO)
  assert sha(pathlib.Path(g['feature_cache'])/'manifest.json')==g['feature_cache_sha256']
  assert g['owner_thread_id']==j(R/'automation/state/coordinator.json')['owner']
  assert (datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(g['issued_utc'])).total_seconds()<86400
  for lp in ['automation/state/online_survival_cpu.lock','automation/locks/isu_irregular_rul_cpu.lock']:
   f=(R/lp).open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  out=pathlib.Path(g['output']);out.mkdir(exist_ok=False)
  write(D/(g['request_id']+'.claim.json'),{'GO_sha256':sha(gp),'claimed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
  signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('runtime budget')));signal.alarm(g['max_runtime_seconds'])
  cache={};fm=j(pathlib.Path(g['feature_cache'])/'manifest.json')
  assert fm['status']=='ALL188_FEATURE_CACHE_COMPLETE' and fm['cells']==188
  for item in fm['inventory']:
   p=R/item['path'];assert sha(p)==item['sha256'];cell=j(p);cid=cell['cell_id']
   assert cell['role'] in ['train','development'] and cid.endswith(('C1','C2','C3')) and not cid.endswith('C4')
   assert cid not in cache;cache[cid]={}
   for d in cell['records']:
    assert d['source_rpt_index'] not in cache[cid]
    cache[cid][d['source_rpt_index']]=d
  from train_eval import load_split
  from data_protocol import make_examples
  from hgb_models import HurdleRUL
  from evaluate import PointZero,metric_row,write_csv,summarize
  cells=load_split(CO,R/'data/processed/ISU_ILCC_DataV2_v1',MAN)
  assert set(cache)=={c['cell_id'] for c in cells}
  tr=make_examples([c for c in cells if c['role']=='train']);dv=make_examples([c for c in cells if c['role']=='development'])
  assert len(tr)==6870 and len(dv)==3765
  for e in tr+dv:
   for r in e['visible_records']:
    z=cache[e['cell_id']][r['source_rpt_index']]
    assert z['stop']==r['stop'] or abs(__import__('data_adapter')._dt(z['stop']).timestamp()-r['stop_epoch'])<1e-6
  rec['data']={'train_queries':len(tr),'development_queries':len(dv),'train_cells':len({e['cell_id'] for e in tr}),'dev_cells':len({e['cell_id'] for e in dv})}
  positive=[i for i,e in enumerate(tr) if e['target_rul_weeks'] is not None and e['target_rul_weeks']>0]
  pos=[tr[i] for i in positive];yp=np.log([e['target_rul_weeks'] for e in pos]);ye=np.asarray([e['y_event'] for e in tr]);folds=foldsets(pos)
  matrices={level:(np.stack([features(e,cache,level) for e in tr]),np.stack([features(e,cache,level) for e in dv])) for level in ['F0','F1','F2']}
  rec['dimensions']={k:a.shape[1] for k,(a,b) in matrices.items()}
  rec['nonfinite_fraction']={k:float(np.isnan(a).mean()) for k,(a,b) in matrices.items()}
  import joblib
  models={}
  def fit(m,x,y,w,name):
   rec['CPU_fits_started']+=1;assert rec['CPU_fits_started']<=20
   m.fit(x,y,sample_weight=w);rec['CPU_fits_completed']+=1
   joblib.dump(m,out/(name+'.joblib'))
   (out/'progress.json').write_text(json.dumps(rec,indent=2));return m
  # F0 HGB already fitted in V18; preserve it rather than repeat the fit.
  p=V18/'runs/run1/seed42/hgb'
  if not p.exists():
   candidates=list((V18/'runs').glob('*/seed42/hgb'));assert len(candidates)==1;p=candidates[0]
  for name in ['hgb_hurdle_classifier_full','hgb_hurdle_positive_full','hgb_hurdle_distribution']:
   assert g['old_assets'][str((p/(name+'.joblib')).relative_to(R))]==sha(p/(name+'.joblib'))
  cl=joblib.load(p/'hgb_hurdle_classifier_full.joblib');reg=joblib.load(p/'hgb_hurdle_positive_full.joblib');rd=joblib.load(p/'hgb_hurdle_distribution.joblib');rec['old_model_loads']=3
  models['hgb_F0']=(cl,reg,rd['residuals'],rd['residual_weights'],'F0')
  for kind,level in [('hgb','F1'),('hgb','F2'),('catboost','F0'),('catboost','F1'),('catboost','F2')]:
   x=matrices[level][0];xp=x[positive];name=kind+'_'+level
   classifier=fit(new(kind,'event'),x,ye,weights(tr),name+'_event')
   residuals=[];rrows=[]
   for fi,held in enumerate(folds):
    a=np.array([i for i,e in enumerate(pos) if e['cell_id'] not in held]);b=np.array([i for i,e in enumerate(pos) if e['cell_id'] in held])
    m=fit(new(kind,'rul'),xp[a],yp[a],weights([pos[i] for i in a]),name+'_oof'+str(fi))
    residuals.extend(yp[b]-m.predict(xp[b]));rrows.extend([pos[i] for i in b])
   regressor=fit(new(kind,'rul'),xp,yp,weights(pos),name+'_positive')
   rw=weights(rrows);rw=rw/rw.sum();models[name]=(classifier,regressor,np.array(residuals),rw,level)
   joblib.dump({'residuals':residuals,'weights':rw},out/(name+'_distribution.joblib'))
  assert rec['CPU_fits_completed']==20
  rec['all_fits_completed_before_dev_prediction']=True
  rows=[]
  for name,(classifier,regressor,residuals,rw,level) in models.items():
   x=matrices[level][1];t=time.perf_counter();p=classifier.predict_proba(x)[:,list(classifier.classes_).index(1)];mu=regressor.predict(x);ms=(time.perf_counter()-t)*1000/len(dv)
   for i,e in enumerate(dv):
    raw=HurdleRUL(p[i],np.exp(mu[i]+residuals),rw);dist=PointZero() if e['known_event'] else raw
    row=metric_row(e,dist,42,name,ms);row['unclosed_p_event']=p[i];row['unclosed_mean_weeks']=raw.mean();rows.append(row)
  rec['prediction_rows']=len(rows)
  write_csv(out/'predictions.csv',rows);ss,cc,rr=summarize(rows)
  write_csv(out/'arm_summary.csv',ss);write_csv(out/'cell_metrics.csv',cc);write_csv(out/'reliability_bins.csv',rr)
  rec['status']='SUCCESS';rec['output']=str(out)
 except BaseException as ex:
  rec.update(status='FAILED',error=repr(ex),traceback=traceback.format_exc())
 finally:
  signal.alarm(0);rec['elapsed_seconds']=time.time()-start
  write(D/(g['request_id']+'_receipt.json'),rec)
  for f in locks:f.close()
 print(json.dumps(rec,indent=2));return rec
if __name__=='__main__':
 z=run(sys.argv[1]);sys.exit(0 if z['status']=='SUCCESS' else 2)
