from pathlib import Path
import json,csv,hashlib,time,datetime,fcntl,signal
import numpy as np
from scipy.special import log_ndtr,ndtr
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,x):
 with (O/n).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
def main():
 start=time.monotonic();p=json.loads((O/'protocol.json').read_text());go=json.loads((O/'ROOT_GO.json').read_text());assert go['status']=='GO_ONE_FIXED_HALF_CDF_MIXTURE_ZERO_FIT' and p['mixture_weight']==.5 and go['max_new_fits']==0
 for n in ['runner.py','protocol.json']:assert sha(O/n)==go[n+'_sha256']
 rev=Path(go['review_path']);assert sha(rev)==go['review_sha256'] and json.loads(rev.read_text())['status']=='PASS'
 with (R/'automation/state/online_survival_cpu.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);c=json.loads((R/'automation/state/coordinator.json').read_text());assert c['owner']==c['thread_id']==p['owner'] and c['takeover_verified'] and not c['new_fits_allowed']
  with (O/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
  def timeout(a,b):raise TimeoutError('60second frozen bound exceeded')
  signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,60)
  try:
   for r in p['sources'].values():assert sha(R/r['path'])==r['sha256']
   source=lambda k:R/p['sources'][k]['path'];src=list(csv.DictReader(source('point_predictions').open()));rows=list(csv.DictReader(source('component_predictions').open()));assert len(src)==4567 and len(rows)==13701
   by={arm:[r for r in rows if r['arm']==arm] for arm in ['lossless_early_survival_conditioned','lossless_dynamic']};early=by['lossless_early_survival_conditioned'];dynamic=by['lossless_dynamic'];assert len(early)==len(dynamic)==4567
   keys=lambda r:(r['cell_id'],int(r['origin']),float(r['true_RUL']));assert [keys(r) for r in src]==[keys(r) for r in early]==[keys(r) for r in dynamic]
   assert len(set(keys(r)[:2] for r in src))==4567;ids=sorted({r['cell_id'] for r in src});assert len(ids)==10
   first={r['cell_id']:float(r['schedule_RUL_raw_log']) for r in src if int(r['origin'])==100};assert set(first)==set(ids)
   d=np.array([int(r['origin'])-100 for r in src],float);mu=np.array([float(r['schedule_RUL_raw_log']) for r in src]);m0=np.array([first[r['cell_id']] for r in src]);sigma=json.loads(source('parameters').read_text())['sigmas']['A_fit_residual_scale'];assert sigma==p['sigma']
   ls=np.zeros(len(src));nz=d>0;ls[nz]=log_ndtr(-(np.log(d[nz])-m0[nz])/sigma)
   def cdf(x):return .5*(-np.expm1(log_ndtr(-(np.log(d+x)-m0)/sigma)-ls))+.5*ndtr((np.log(x)-mu)/sigma)
   quantiles=[];cdferror=0.;widthmax=0.
   for q,key in [(.1,'q10'),(.5,'q50'),(.9,'q90')]:
    a=np.minimum([float(r[key]) for r in early],[float(r[key]) for r in dynamic]);b=np.maximum([float(r[key]) for r in early],[float(r[key]) for r in dynamic]);assert (a>0).all() and np.max(cdf(a)-q)<1e-10 and np.max(q-cdf(b))<1e-10
    for step in range(64):
     mid=(a+b)/2;left=cdf(mid)<q;a=np.where(left,mid,a);b=np.where(left,b,mid)
    z=(a+b)/2;quantiles.append(z);cdferror=max(cdferror,float(np.max(abs(cdf(z)-q))));widthmax=max(widthmax,float(np.max(b-a)))
   lo,med,hi=quantiles;assert np.isfinite(lo).all() and np.isfinite(hi).all() and (lo<med).all() and (med<hi).all() and cdferror<1e-10
   risk={h:(np.array([float(r['risk'+str(h)]) for r in early])+np.array([float(r['risk'+str(h)]) for r in dynamic]))/2 for h in [100,300]};riskerr=max(float(np.max(abs(risk[h]-cdf(np.full(len(src),h))))) for h in [100,300]);assert riskerr<1e-10
   y=np.array([float(r['true_RUL']) for r in src]);arms={}
   for arm,rr in [('early_survival',early),('dynamic',dynamic)]:
    arms[arm]=([np.array([float(r[k]) for r in rr]) for k in ['q10','q50','q90']],{h:np.array([float(r['risk'+str(h)]) for r in rr]) for h in [100,300]})
   arms['fixed_half_CDF_mixture']=([lo,med,hi],risk);pc=[]
   for cid in ids:
    ix=np.array([i for i,r in enumerate(src) if r['cell_id']==cid])
    for arm,(qs,rs) in arms.items():
     l,m,h=[z[ix] for z in qs];e=m-y[ix];score=h-l+10*np.maximum(l-y[ix],0)+10*np.maximum(y[ix]-h,0)
     v=dict(cell_id=cid,arm=arm,origins=len(ix),MAE=float(abs(e).mean()),bias=float(e.mean()),severe_over100=float((e>100).mean()),coverage80=float(((y[ix]>=l)&(y[ix]<=h)).mean()),width80=float((h-l).mean()),interval_score80=float(score.mean()),Brier100=float(((rs[100][ix]-(y[ix]<=100))**2).mean()),Brier300=float(((rs[300][ix]-(y[ix]<=300))**2).mean()));pc.append(v)
   ks=[k for k in pc[0] if k not in ['cell_id','arm','origins']];met={a:{k:float(np.mean([r[k] for r in pc if r['arm']==a])) for k in ks} for a in arms};cmp={}
   for ref in ['early_survival','dynamic']:
    a,b=met[ref],met['fixed_half_CDF_mixture'];u,v=[np.array([r['MAE'] for r in pc if r['arm']==arm]) for arm in [ref,'fixed_half_CDF_mixture']];bs=np.random.default_rng(42).integers(0,10,(2000,10));ci=np.quantile((u-v)[bs].mean(axis=1),[.025,.975]).tolist();n=int((v<u).sum());inc=b['severe_over100']-a['severe_over100']
    x=dict(relative_MAE_reduction=1-b['MAE']/a['MAE'],cells_MAE_improved=n,pairedcell_MAE_difference_CI95=ci,severe_over100_increment=inc,interval_score_reduction=1-b['interval_score80']/a['interval_score80'],absolute_coverage_error_reduction=abs(a['coverage80']-.8)-abs(b['coverage80']-.8),width_ratio=b['width80']/a['width80'],mean_Brier_increment=(b['Brier100']+b['Brier300']-a['Brier100']-a['Brier300'])/2,cells_coverage_error_improved=sum(abs(next(r['coverage80'] for r in pc if r['cell_id']==cid and r['arm']=='fixed_half_CDF_mixture')-.8)<abs(next(r['coverage80'] for r in pc if r['cell_id']==cid and r['arm']==ref)-.8) for cid in ids))
    x['point_gate_pass']=bool(x['relative_MAE_reduction']>=.05 and n>=7 and ci[0]>0 and inc<=.01)
    x['probability_checks']=dict(point_gate=x['point_gate_pass'],interval_score=x['interval_score_reduction']>=.05,coverage_error=x['absolute_coverage_error_reduction']>=.03,width=x['width_ratio']<=2,Brier=x['mean_Brier_increment']<=.002,cell_coverage=x['cells_coverage_error_improved']>=7);x['joint_probability_gate_pass']=all(x['probability_checks'].values());x['primary_reference']=ref=='early_survival';cmp[ref]=x
   with (O/'mixture_predictions.csv').open('x',newline='') as f:
    w=csv.writer(f);w.writerow(['cell_id','origin','true_RUL','q10','q50','q90','risk100','risk300'])
    for i,r in enumerate(src):w.writerow([r['cell_id'],r['origin'],r['true_RUL'],float(lo[i]),float(med[i]),float(hi[i]),float(risk[100][i]),float(risk[300][i])])
   dump('metrics.json',met);dump('per_cell_metrics.json',pc);dump('comparisons.json',cmp);dump('numeric_validation.json',dict(status='PASS_COHERENT_MIXTURE_CDF_INVERSION',maximum_quantile_CDF_error=cdferror,maximum_bracket_width=widthmax,maximum_risk_difference=riskerr,positive_ordered_all4567=True,weight=.5,iterations=64))
   dump('completion.json',dict(status='COMPLETE_ONE_FIXED_HALF_CDF_MIXTURE',new_fits=0,new_model_inference=0,new_scale_estimates=0,new_weight_estimates=0,checkpoint_loads=0,raw_feature_reads=0,dev_test_reads=0,rows=4567,prediction_sha256=sha(O/'mixture_predictions.csv'),runner_sha256=sha(Path(__file__)),protocol_sha256=sha(O/'protocol.json'),GO_sha256=sha(O/'ROOT_GO.json'),elapsed_seconds=time.monotonic()-start))
   signal.setitimer(signal.ITIMER_REAL,0);print(json.dumps(dict(metrics=met,comparisons=cmp)))
  except BaseException as e:
   dump('failure.json',dict(status='FAILED_STOP_NO_RETRY',type=type(e).__name__,error=str(e)));raise
if __name__=='__main__':main()
