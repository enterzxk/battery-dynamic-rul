from pathlib import Path
import csv,json,hashlib,time,datetime,fcntl,signal
import numpy as np
from scipy.special import log_ndtr,ndtri_exp
R=Path('/home/yndx/zxk/rul'); O=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,x):
 with (O/n).open('x') as f: json.dump(x,f,indent=2);f.write('\n')
def key(r):return r['cell_id'],int(r['origin'])
def main():
 start=time.monotonic(); p=json.loads((O/'protocol.json').read_text()); g=json.loads((O/'ROOT_GO.json').read_text())
 assert g['status']=='GO_ONCE_FIXED20_REPORTING_DELAY_ZERO_FIT' and g['max_runs']==1 and g['max_new_fits']==0
 for n in ['runner.py','protocol.json']:assert sha(O/n)==g[n+'_sha256']
 review=Path(g['review_path']); assert sha(review)==g['review_sha256'] and json.loads(review.read_text())['status']=='PASS'
 assert p['delay_cycles']==20 and p['sigma']==0.19898311654196568 and p['weight']==.5
 with (R/'automation/state/online_survival_cpu.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB); c=json.loads((R/'automation/state/coordinator.json').read_text()); assert c['owner']==c['thread_id']==p['owner'] and c['takeover_verified'] and not c['new_fits_allowed']
  with (O/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
  def timeout(a,b):raise TimeoutError('Frozen60second bound exceeded')
  signal.signal(signal.SIGALRM,timeout); signal.setitimer(signal.ITIMER_REAL,60)
  try:
   for src in p['sources'].values(): assert sha(R/src['path'])==src['sha256']
   def read(k):return list(csv.DictReader((R/p['sources'][k]['path']).open()))
   raw=read('point'); assert len(raw)==4567 and all(r['role']=='calibration' for r in raw)
   bykey={key(r):r for r in raw}; assert len(bykey)==len(raw)
   rows=sorted([r for r in raw if int(r['origin'])>=120],key=key); ids=sorted({r['cell_id'] for r in rows}); assert len(rows)==4367 and len(ids)==10 and len(raw)-len(rows)==200
   for cid in ids:
    rr=sorted([r for r in raw if r['cell_id']==cid],key=key); event=int(rr[0]['event_cycle']); assert [int(r['origin']) for r in rr]==list(range(100,event)) and all(int(r['event_cycle'])==event and float(r['true_RUL'])==event-int(r['origin']) for r in rr)
   lag=[bykey[(r['cell_id'],int(r['origin'])-20)] for r in rows]; assert all(int(a['origin'])==int(r['origin'])-20 and float(a['true_RUL'])==float(r['true_RUL'])+20 for a,r in zip(lag,rows))
   comp=read('components'); mix=read('mixture'); assert len(comp)==13701 and len(mix)==4567
   def align(rr):
    b={key(r):r for r in rr}; assert len(b)==len(rr)==4567 and set(b)==set(bykey)
    out=[b[key(r)] for r in rows]; assert all(float(a['true_RUL'])==float(r['true_RUL']) for a,r in zip(out,rows)); return out
   early=align([r for r in comp if r['arm']=='lossless_early_survival_conditioned']); dyn=align([r for r in comp if r['arm']=='lossless_dynamic']); mixed=align(mix)
   def arrays(rr):return {k:np.array([float(r[k]) for r in rr]) for k in ['q10','q50','q90','risk100','risk300']}
   arms={'early_survival':arrays(early),'current_dynamic':arrays(dyn),'current_half_CDF':arrays(mixed)}
   sigma=json.loads((R/p['sources']['parameters']['path']).read_text())['sigmas']['A_fit_residual_scale']; assert sigma==p['sigma']
   mu=np.array([float(r['schedule_RUL_raw_log']) for r in lag]); ls=log_ndtr(-(np.log(20.)-mu)/sigma)
   m0=np.array([float(bykey[(r['cell_id'],100)]['schedule_RUL_raw_log']) for r in rows]); d=np.array([int(r['origin'])-100 for r in rows],float); ls0=log_ndtr(-(np.log(d)-m0)/sigma)
   def lagcdf(x):return -np.expm1(log_ndtr(-(np.log(20+x)-mu)/sigma)-ls)
   def earlycdf(x):return -np.expm1(log_ndtr(-(np.log(d+x)-m0)/sigma)-ls0)
   def mixcdf(x):return .5*earlycdf(x)+.5*lagcdf(x)
   qerr=0.; qlag={}; qmix={}
   for q,k in [(.1,'q10'),(.5,'q50'),(.9,'q90')]:
    z=np.exp(mu-sigma*ndtri_exp(ls+np.log1p(-q)))-20; qlag[k]=z; qerr=max(qerr,float(np.max(abs(lagcdf(z)-q))))
    a=np.minimum(arms['early_survival'][k],z); b=np.maximum(arms['early_survival'][k],z); assert np.max(mixcdf(a)-q)<1e-10 and np.max(q-mixcdf(b))<1e-10
    for step in range(64):
     mid=(a+b)/2; left=mixcdf(mid)<q; a=np.where(left,mid,a); b=np.where(left,b,mid)
    qmix[k]=(a+b)/2; qerr=max(qerr,float(np.max(abs(mixcdf(qmix[k])-q))))
   for h in [100,300]: qlag['risk'+str(h)]=lagcdf(h); qmix['risk'+str(h)]=mixcdf(h)
   arms.update(lag20_dynamic_survival=qlag,lag20_half_CDF=qmix); assert list(arms)==p['arms'] and qerr<1e-10
   y=np.array([float(r['true_RUL']) for r in rows]); pc=[]
   for arm,z in arms.items():
    assert all(np.isfinite(v).all() for v in z.values()) and (z['q10']>0).all() and (z['q10']<z['q50']).all() and (z['q50']<z['q90']).all()
    assert all(((z['risk'+str(h)]>=0)&(z['risk'+str(h)]<=1)).all() for h in [100,300])
    for cid in ids:
     ix=np.array([i for i,r in enumerate(rows) if r['cell_id']==cid]); lo,med,hi=[z[k][ix] for k in ['q10','q50','q90']]; e=med-y[ix]
     rec=dict(cell_id=cid,arm=arm,origins=len(ix),MAE=float(abs(e).mean()),bias=float(e.mean()),severe_over100=float((e>100).mean()),coverage80=float(((lo<=y[ix])&(y[ix]<=hi)).mean()),width80=float((hi-lo).mean()),interval_score80=float((hi-lo+10*np.maximum(lo-y[ix],0)+10*np.maximum(y[ix]-hi,0)).mean()))
     for h in [100,300]:rec['Brier'+str(h)]=float(((z['risk'+str(h)][ix]-(y[ix]<=h))**2).mean())
     pc.append(rec)
   keys=[k for k in pc[0] if k not in ['cell_id','arm','origins']]; metrics={arm:{k:float(np.mean([v[k] for v in pc if v['arm']==arm])) for k in keys} for arm in arms}
   comparisons={}; gate=p['point_risk_retention_gate']
   for target,ref in [('lag20_half_CDF','early_survival'),('lag20_dynamic_survival','early_survival'),('lag20_half_CDF','current_half_CDF'),('lag20_dynamic_survival','current_dynamic')]:
    pairs=[next(v['MAE'] for v in pc if v['cell_id']==cid and v['arm']==ref)-next(v['MAE'] for v in pc if v['cell_id']==cid and v['arm']==target) for cid in ids]; delta=np.array(pairs); bs=np.random.default_rng(42).integers(0,10,(2000,10)); ci=np.quantile(delta[bs].mean(axis=1),[.025,.975]).tolist(); a,b=metrics[ref],metrics[target]
    v=dict(relative_MAE_reduction=1-b['MAE']/a['MAE'],cells_MAE_improved=int((delta>0).sum()),pairedcell_MAE_difference_CI95=ci,severe_over100_increment=b['severe_over100']-a['severe_over100'],coverage80_change=b['coverage80']-a['coverage80'],interval_score80_change=b['interval_score80']-a['interval_score80'])
    if ref=='early_survival':v['point_risk_retention_gate_pass']=bool(v['relative_MAE_reduction']>=gate['relative_MAE_reduction_min'] and v['cells_MAE_improved']>=gate['cells_MAE_improved_min'] and v['severe_over100_increment']<=gate['severe_over100_increment_max'] and ci[0]>gate['paired_bootstrap_CI_lower_strictly_above'])
    comparisons[target+'_vs_'+ref]=v
   with (O/'predictions.csv').open('x',newline='') as f:
    w=csv.writer(f); w.writerow(['cell_id','origin','history_through','true_RUL','arm','q10','q50','q90','risk100','risk300'])
    for arm,z in arms.items():
     for i,r in enumerate(rows):w.writerow([r['cell_id'],r['origin'],int(r['origin'])-20 if arm.startswith('lag20') else (100 if arm=='early_survival' else r['origin']),r['true_RUL'],arm]+[float(z[k][i]) for k in ['q10','q50','q90','risk100','risk300']])
   dump('metrics.json',metrics); dump('per_cell_metrics.json',pc); dump('comparisons.json',comparisons); dump('numeric_validation.json',dict(status='PASS',max_quantile_CDF_error=qerr,all_arms_same4367=True,cells=ids,excluded_rows=200,lag_actual_cycles=20,source_roles='calibration_only',labels_scoring_only=True))
   dump('completion.json',dict(status='COMPLETE_ONE_FIXED20_REPORTING_DELAY',rows_per_arm=4367,arms=5,new_fits=0,new_model_inference=0,checkpoint_loads=0,raw_feature_reads=0,dev_test_reads=0,new_scale_estimates=0,new_weight_estimates=0,elapsed_seconds=time.monotonic()-start,runner_sha256=sha(O/'runner.py'),protocol_sha256=sha(O/'protocol.json'),GO_sha256=sha(O/'ROOT_GO.json'),predictions_sha256=sha(O/'predictions.csv'))); signal.setitimer(signal.ITIMER_REAL,0);print(json.dumps(dict(metrics=metrics,comparisons=comparisons)))
  except BaseException as e:dump('failure.json',dict(status='FAILED_STOP_NO_RETRY',type=type(e).__name__,error=str(e)));raise
if __name__=='__main__':main()
