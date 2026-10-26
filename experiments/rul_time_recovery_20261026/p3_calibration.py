import os
os.environ['OMP_NUM_THREADS']='4';os.environ['MKL_NUM_THREADS']='4';os.environ['OPENBLAS_NUM_THREADS']='4'
import pathlib,json,sys,fcntl,signal,time,traceback,collections,importlib.util
import numpy as np
import joblib
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
R=pathlib.Path('/home/yndx/zxk/rul');D=R/'experiments/rul_time_recovery_20261026';C=R/'experiments/multisource_factorial_20261021/run2_clocksafe'
spec=importlib.util.spec_from_file_location('p1',D/'runner.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
from hgb_models import HurdleRUL
COLS=[0,1,3,4,6,8,686,687]
def contexts(x,mu):return np.column_stack([mu,x[:,COLS].astype(float)])
def main(go):
 t=time.time();g=m.readj(go);locks=[];out=None
 rec=dict(request_id=g['request_id'],status='PREFLIGHT',started_utc=m.utc(),calibrator_fits_started=0,calibrator_fits_completed=0,base_fits=0,neural_fits=0,C4_reads=0,development_fit_rows=0)
 try:
  assert g['max_calibrator_fits']==3 and g['max_base_fits']==0
  c=m.readj(R/'automation/state/coordinator.json');assert c['owner']==c['thread_id']==g['owner_thread_id']
  assert c['takeover_verified'] is True and c['actual_cwd']==str(R)
  for p,h in g['sha256'].items():assert m.sha(R/p)==h,p
  for p in ['automation/state/online_survival_cpu.lock','automation/locks/isu_irregular_rul_cpu.lock']:
   f=(R/p).open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  with (R/'experiments/state/consumed_gos.jsonl').open('a+') as f:
   fcntl.flock(f,fcntl.LOCK_EX);f.seek(0);assert all(json.loads(l).get('request_id')!=g['request_id'] for l in f if l.strip())
   m.createj(D/(g['request_id']+'.claim.json'),dict(pid=os.getpid(),go_sha256=m.sha(go),utc=m.utc()))
   f.write(json.dumps(dict(request_id=g['request_id'],go_sha256=m.sha(go),claimed_utc=m.utc()))+'\n');f.flush();os.fsync(f.fileno())
  out=R/g['output'];assert out.parent==D;out.mkdir(exist_ok=False)
  signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('600 second bound')));signal.alarm(600)
  tr=m.jsonlines(C/'train_targets.jsonl');dr=m.jsonlines(C/'development_targets.jsonl');dm=m.jsonlines(C/'development_rows.jsonl')
  xt=np.load(C/'train_features.npz',allow_pickle=False)['F3'];xd=np.load(C/'development_features.npz',allow_pickle=False)['F3']
  assert len(tr)==len(xt)==6870 and len(dr)==len(dm)==len(xd)==3765
  assert {r['cell_id'] for r in tr}.isdisjoint({r['cell_id'] for r in dr})
  assert all(r['cell_id'].endswith(('C1','C2')) for r in tr) and all(r['cell_id'].endswith('C3') for r in dr)
  assert all(m.key(r)==m.key(z) for r,z in zip(dr,dm))
  ix=np.array([i for i,r in enumerate(tr) if r['target_rul_weeks'] is not None and r['target_rul_weeks']>0])
  y=np.log([tr[i]['target_rul_weeks'] for i in ix]);cells=np.array([tr[i]['cell_id'] for i in ix]);assert len(ix)==4713
  ids=sorted(set(cells));np.random.RandomState(42).shuffle(ids);folds=[set(ids[::2]),set(ids[1::2])]
  mu=np.empty(len(y));resorder=[]
  for fi,held in enumerate(folds):
   val=np.array([c in held for c in cells]);model=joblib.load(C/('hgb_F3_oof%d.joblib'%fi))
   mu[val]=model.predict(xt[ix[val]]);resorder.extend(np.flatnonzero(val))
  residual=y-mu;law=joblib.load(C/'hgb_F3_distribution.joblib')
  err=float(np.max(abs(residual[resorder]-law['residuals'])));assert err<1e-12
  full=joblib.load(C/'hgb_F3_positive.joblib');mud=full.predict(xd)
  z=contexts(xt[ix],mu);zd=contexts(xd,mud);assert np.isfinite(z).all() and np.isfinite(zd).all()
  w=m.weights(cells);wn=w/w.sum();mean=np.sum(wn[:,None]*z,axis=0);sd=np.sqrt(np.sum(wn[:,None]*(z-mean)**2,axis=0));sd=np.maximum(sd,1e-12)
  savedr=np.array(law['residuals']);savedw=np.array(law['weights']);center=float(np.dot(savedr,savedw)/savedw.sum())
  models={}
  for name in ['ridge_context','hgb_context','hgb_mu_only']:
   model=Ridge(alpha=10.) if name=='ridge_context' else HistGradientBoostingRegressor(max_iter=50,max_leaf_nodes=4,max_depth=2,min_samples_leaf=50,l2_regularization=10.,random_state=42,early_stopping=False)
   a=(z-mean)/sd if name=='ridge_context' else (z[:,:1] if name=='hgb_mu_only' else z)
   b=(zd-mean)/sd if name=='ridge_context' else (zd[:,:1] if name=='hgb_mu_only' else zd)
   rec['current_fit']=name;rec['calibrator_fits_started']+=1;assert rec['calibrator_fits_started']<=3;m.saveprogress(out,rec)
   print('FIT_START',name,flush=True);model.fit(a,residual,sample_weight=w);rec['calibrator_fits_completed']+=1
   joblib.dump(dict(model=model,columns=COLS,mean=mean,sd=sd),out/(name+'.joblib'))
   models[name]=model.predict(b);print('FIT_DONE',name,flush=True)
  assert rec['calibrator_fits_completed']==3;rec['all_fits_before_C3_scoring']=True
  models['global_control']=np.full(len(dr),center)
  base={m.key(r):r for r in __import__('csv').DictReader((C/'predictions.csv').open()) if r['model']=='hgb_F3'}
  assert len(base)==len(dr)==len({m.key(r) for r in dr})
  for r in dr:
   b=base[m.key(r)];assert (None if b['target_rul_weeks']=='' else float(b['target_rul_weeks']))==r['target_rul_weeks']
   for n in ['mean_weeks','median_weeks']:b[n]=float(b[n])
  pred=[];max_identity_error=0.
  for name,shift in models.items():
   for i,r in enumerate(dr):
    dist=m.PointZero() if r['known_event'] else HurdleRUL(float(base[m.key(r)]['unclosed_p_event']),np.exp(mud[i]+shift[i]+savedr-center),savedw)
    e=dict(r,last_arrival_epoch=max(dm[i]['visible_rpt_arrival_epochs']),delta_weeks=(r['query_epoch']-max(dm[i]['visible_rpt_arrival_epochs']))/604800.,history_key=dm[i]['history_key'])
    q=m.metric_row(e,dist,42,name,0.);q.update(point_weeks=dist.quantile(.5),point_raw_unconstrained_weeks=float(np.exp(mud[i]+shift[i])),conditional_log_shift=float(shift[i]-center))
    pred.append(q)
    if name=='global_control':
     b=base[m.key(r)]
     for n in ['mean_weeks','median_weeks','p_event','F4','F12']:
      max_identity_error=max(max_identity_error,abs(float(q[n])-float(b[n])))
  assert max_identity_error<1e-9
  m.write_csv(out/'predictions.csv',pred);summary,per,_=m.summarize(pred)
  m.write_csv(out/'distribution_summary.csv',summary);m.write_csv(out/'distribution_per_cell.csv',per)
  points=m.point_report(pred,base,out)
  rec.update(status='SUCCESS',finished_utc=m.utc(),wall_seconds=time.time()-t,predictions=len(pred),OOF_residual_identity_error=err,global_control_identity_error=max_identity_error,cell_overlap=0,
   primary=[p for p in points if p['arm']=='raw' and p['stratum']=='unconfirmed'],novelty_claim=False,scope='Posthoc train-cell-OOF calibration diagnostic; adaptive C3 development only')
  m.createj(out/'receipt.json',rec);m.saveprogress(out,rec);print('SUCCESS',json.dumps(rec['primary']),flush=True)
 except BaseException as e:
  rec.update(status='FAILED_STOP',error=repr(e),traceback=traceback.format_exc())
  m.createj((out if out else D)/(g['request_id']+'_failure.json'),rec);raise
 finally:
  for f in reversed(locks):f.close()
if __name__=='__main__':main(pathlib.Path(sys.argv[1]))
