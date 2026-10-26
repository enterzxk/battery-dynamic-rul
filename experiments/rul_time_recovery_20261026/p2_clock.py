import os
os.environ['OMP_NUM_THREADS']='4';os.environ['MKL_NUM_THREADS']='4';os.environ['OPENBLAS_NUM_THREADS']='4'
import sys,pathlib,json,datetime,fcntl,time,traceback,hashlib,collections,importlib.util,signal
import numpy as np
import joblib
from sklearn.ensemble import HistGradientBoostingRegressor
R=pathlib.Path('/home/yndx/zxk/rul');D=R/'experiments/rul_time_recovery_20261026';C=R/'experiments/multisource_factorial_20261021/run2_clocksafe'
spec=importlib.util.spec_from_file_location('p1',D/'runner.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
from hgb_models import HurdleRUL
def clock(x,floor,delay=True):
 rate=np.maximum(-x[:,8].astype(float),floor)
 tau0=np.maximum(x[:,1].astype(float)-.8,0.)/rate
 delta=x[:,6].astype(float) if delay else 0.
 tau=np.logaddexp(0.,tau0-delta)
 return np.log(np.maximum(tau,1e-8))
def floor_from(x):
 v=-x[:,8].astype(float);v=v[np.isfinite(v)&(v>0)]
 assert len(v)>0
 return max(float(np.quantile(v,.1)),1e-8)
def main(go):
 t=time.time();g=m.readj(go);locks=[];out=None
 rec=dict(request_id=g['request_id'],status='PREFLIGHT',started_utc=m.utc(),fits_started=0,fits_completed=0,C4_reads=0,development_fit_rows=0)
 try:
  assert g['max_fits']==9 and g['allow_fit'] is True
  c=m.readj(R/'automation/state/coordinator.json');assert c['owner']==c['thread_id']==g['owner_thread_id']
  for p,h in g['sha256'].items():assert m.sha(R/p)==h,p
  for p in ['automation/state/online_survival_cpu.lock','automation/locks/isu_irregular_rul_cpu.lock']:
   f=(R/p).open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  with (R/'experiments/state/consumed_gos.jsonl').open('a+') as f:
   fcntl.flock(f,fcntl.LOCK_EX);f.seek(0);assert all(json.loads(l).get('request_id')!=g['request_id'] for l in f if l.strip())
   m.createj(D/(g['request_id']+'.claim.json'),dict(pid=os.getpid(),go_sha256=m.sha(go),utc=m.utc()))
   f.write(json.dumps(dict(request_id=g['request_id'],go_sha256=m.sha(go),claimed_utc=m.utc()))+'\n');f.flush();os.fsync(f.fileno())
  out=R/g['output'];assert out.parent==D;out.mkdir(exist_ok=False)
  signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('1800s limit')));signal.alarm(1800)
  tr=m.jsonlines(C/'train_targets.jsonl');dr=m.jsonlines(C/'development_targets.jsonl');dm=m.jsonlines(C/'development_rows.jsonl')
  X=np.load(C/'train_features.npz',allow_pickle=False)['F3'];XD=np.load(C/'development_features.npz',allow_pickle=False)['F3']
  assert X.shape==(6870,710) and XD.shape==(3765,710)
  assert {r['cell_id'] for r in tr}.isdisjoint({r['cell_id'] for r in dr})
  assert all(r['cell_id'].endswith(('C1','C2')) for r in tr) and all(r['cell_id'].endswith('C3') for r in dr)
  ix=np.array([i for i,r in enumerate(tr) if r['target_rul_weeks'] is not None and r['target_rul_weeks']>0])
  X=X[ix];y=np.log([tr[i]['target_rul_weeks'] for i in ix]);cells=np.array([tr[i]['cell_id'] for i in ix]);assert len(ix)==4713
  ids=sorted(set(cells));np.random.RandomState(42).shuffle(ids);folds=[set(ids[::2]),set(ids[1::2])]
  models={};finfo=[]
  for variant in ['clock_feature','clock_offset','clock_no_delay_offset']:
   residual=np.empty(len(y));assigned=np.zeros(len(y),bool)
   for fi,held in list(enumerate(folds))+[(2,set())]:
    fit=np.array([c not in held for c in cells]);val=~fit;assert set(cells[fit]).isdisjoint(set(cells[val]))
    floor=floor_from(X[fit]);ct=clock(X,floor,variant!='clock_no_delay_offset')
    Z=np.column_stack([X,ct]);offset=ct if variant!='clock_feature' else np.zeros(len(ct))
    model=HistGradientBoostingRegressor(max_iter=150,max_leaf_nodes=15,l2_regularization=1.,random_state=42,early_stopping=False)
    rec['fits_started']+=1;assert rec['fits_started']<=9;rec['current_fit']=variant+'_fold'+str(fi);rec['status']='RUNNING';m.saveprogress(out,rec)
    print('FIT_START',rec['current_fit'],int(fit.sum()),'floor',floor,flush=True)
    model.fit(Z[fit],y[fit]-offset[fit],sample_weight=m.weights(cells[fit]))
    rec['fits_completed']+=1;joblib.dump(dict(model=model,rate_floor=floor,variant=variant),out/(rec['current_fit']+'.joblib'))
    finfo.append(dict(variant=variant,fold=fi,rate_floor=floor,fit_cells=sorted(set(cells[fit])),held_cells=sorted(held)))
    if fi<2:
     residual[val]=y[val]-(model.predict(Z[val])+offset[val]);assigned[val]=True
    else:
     assert assigned.all();models[variant]=(model,floor,residual.copy(),m.weights(cells))
     np.savez_compressed(out/(variant+'_OOF.npz'),residual=residual,cells=cells,source_train_indices=ix)
    m.saveprogress(out,rec);print('FIT_DONE',rec['current_fit'],flush=True)
  assert rec['fits_completed']==9
  rec['all_fits_before_C3_scoring']=True
  base={m.key(r):r for r in __import__('csv').DictReader((C/'predictions.csv').open()) if r['model']=='hgb_F3'}
  assert len(base)==len(dr)==len({m.key(r) for r in dr})
  for r in dr:
   b=base[m.key(r)];by=None if b['target_rul_weeks']=='' else float(b['target_rul_weeks']);assert by==r['target_rul_weeks']
   for n in ['mean_weeks','median_weeks']:b[n]=float(b[n])
  prediction=[]
  for variant in list(models)+['pure_clock']:
   if variant=='pure_clock':
    floor=floor_from(X);ct=clock(XD,floor);mu=ct;residual=np.array([0.]);w=np.array([1.])
   else:
    model,floor,residual,w=models[variant];ct=clock(XD,floor,variant!='clock_no_delay_offset')
    mu=model.predict(np.column_stack([XD,ct]))+(ct if variant!='clock_feature' else 0.)
   assert np.isfinite(mu).all() and np.isfinite(residual).all()
   for i,r in enumerate(dr):
    b=base[m.key(r)];p=float(b['unclosed_p_event'])
    support=np.exp(mu[i]+residual);assert np.isfinite(support).all() and np.min(support)>0
    dist=m.PointZero() if r['known_event'] else HurdleRUL(p,support,w)
    e=dict(r,last_arrival_epoch=max(dm[i]['visible_rpt_arrival_epochs']),delta_weeks=(r['query_epoch']-max(dm[i]['visible_rpt_arrival_epochs']))/604800.,history_key=dm[i]['history_key'])
    q=m.metric_row(e,dist,42,variant,0.)
    q.update(point_weeks=dist.quantile(.5),clock_log_tau=float(ct[i]),point_raw_unconstrained_weeks=float(np.exp(mu[i])),rate_floor=floor)
    prediction.append(q)
  m.write_csv(out/'predictions.csv',prediction)
  ss,cc,_=m.summarize(prediction);m.write_csv(out/'distribution_summary.csv',ss);m.write_csv(out/'distribution_per_cell.csv',cc)
  primary=m.point_report(prediction,base,out)
  rec.update(status='SUCCESS',finished_utc=m.utc(),wall_seconds=time.time()-t,predictions=len(prediction),cell_overlap=0,fold_info=finfo,
    primary=[p for p in primary if p['arm']=='raw' and p['stratum']=='unconfirmed'],novelty_claim=False)
  m.createj(out/'receipt.json',rec);m.saveprogress(out,rec);print('SUCCESS',json.dumps(rec['primary']),flush=True)
 except BaseException as e:
  rec.update(status='FAILED_STOP',error=repr(e),traceback=traceback.format_exc())
  m.createj((out if out else D)/(g['request_id']+'_failure.json'),rec);raise
 finally:
  for f in reversed(locks):f.close()
if __name__=='__main__':main(pathlib.Path(sys.argv[1]))
