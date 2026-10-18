from pathlib import Path
import os,json,csv,hashlib,math,time,datetime,fcntl,signal
from fractions import Fraction
from collections import Counter
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
import numpy as np
from scipy.special import ndtr,ndtri
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,x):
 with (O/n).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
def distribution(rows):
 counts=Counter(r['cell_id'] for r in rows);ordered=sorted((math.log(float(r['true_RUL']))-float(r['oof_mu_log_RUL']),r['cell_id'],int(r['origin'])) for r in rows);acc=Fraction();qs={};values=[];prefix=[]
 for value,cid,origin in ordered:
  acc+=Fraction(1,5*counts[cid]);values.append(value);prefix.append(float(acc))
  for q in [Fraction(1,10),Fraction(1,2),Fraction(9,10)]:
   if q not in qs and acc>=q:qs[q]=value
 assert len(counts)==5 and acc==1
 center=qs[Fraction(1,2)];offsets=[qs[q]-center for q in [Fraction(1,10),Fraction(1,2),Fraction(9,10)]];assert offsets[0]<offsets[1]==0<offsets[2]
 support=np.array(values)-center;cdf=np.array(prefix);assert cdf[-1]==1
 return center,offsets,support,cdf,counts
def main():
 start=time.monotonic();p=json.loads((O/'protocol.json').read_text());go=json.loads((O/'ROOT_GO.json').read_text())
 assert go['status']=='GO_ONE_FIXED5_POLICY_LOCAL_OOF_CDF_ZERO_FIT' and go['max_new_fits']==0 and go['max_model_inference']==0
 for n in ['runner.py','protocol.json']:assert sha(O/n)==go[n+'_sha256']
 review=Path(go['review_path']);assert sha(review)==go['review_sha256'] and json.loads(review.read_text())['status']=='PASS'
 with (R/'automation/state/online_survival_cpu.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);control=json.loads((R/'automation/state/coordinator.json').read_text());assert control['owner']==control['thread_id']==p['owner'] and control['takeover_verified'] and not control['new_fits_allowed']
  with (O/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
  def timeout(s,f):raise TimeoutError('30second frozen budget exceeded')
  signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,30)
  try:
   for item in p['sources'].values():assert sha(R/item['path'])==item['sha256']
   source=lambda k:R/p['sources'][k]['path']
   co=json.loads(source('cohort').read_text());pol=json.loads(source('policy').read_text());policy={r['cell_id']:r for r in pol};assert len(policy)==52
   oo=list(csv.DictReader(source('OOF').open()));cal=list(csv.DictReader(source('calibration').open()));assert len(oo)==22281 and len(cal)==4567
   fitids=sorted({r['cell_id'] for r in oo});calids=sorted({r['cell_id'] for r in cal});assert len(fitids)==42 and len(calids)==10 and not set(fitids)&set(calids)
   assert set(fitids)=={cid for cid,role in co['roles'].items() if role=='fit'} and set(calids)=={cid for cid,role in co['roles'].items() if role=='calibration'}
   assert all(policy[cid]['role']=='fit' for cid in fitids) and all(policy[cid]['role']=='calibration' for cid in calids)
   fields=p['policy_columns'];train=np.array([[float(policy[cid][k]) for k in fields] for cid in fitids]);targets=np.array([[float(policy[cid][k]) for k in fields] for cid in calids]);assert np.isfinite(train).all() and np.isfinite(targets).all()
   with (O/'estimate_ledger.jsonl').open('x') as f:f.write(json.dumps(dict(event='train_policy_transform_started',fit_cells=42,columns=4,mean_and_populationSD=True))+'\n')
   mean=train.mean(axis=0);sd=train.std(axis=0,ddof=0);active=sd>p['constant_SD_C_threshold'];assert active.any()
   if (~active).any():assert np.max(abs(targets[:,~active]-mean[~active]))<=p['constant_target_tolerance_C']
   # All statistics and distances below depend on known policy and fit rows only.
   Z=(train[:,active]-mean[active])/sd[active];T=(targets[:,active]-mean[active])/sd[active]
   dump('train_transform.json',dict(fit_ids=fitids,mean=mean.tolist(),population_SD=sd.tolist(),active_columns=[f for f,a in zip(fields,active) if a],zero_variance_rule=p['zero_variance_rule']))
   neighbors={};distros={};support_receipts=[]
   for cid,t in zip(calids,T):
    d=np.sum((Z-t)**2,axis=1);indices=sorted(range(42),key=lambda i:(float(d[i]),fitids[i]))[:5];chosen=[fitids[i] for i in indices];assert len(set(chosen))==5 and cid not in chosen
    rr=[r for r in oo if r['cell_id'] in chosen]
    with (O/'estimate_ledger.jsonl').open('a') as f:f.write(json.dumps(dict(event='local_CDF_started',target_cell=cid,source_cells=chosen,OOF_rows=len(rr)))+'\n')
    center,offset,support,cdf,counts=distribution(rr);distros[cid]=(offset,support,cdf)
    rec=dict(cell_id=cid,source_cells=chosen,squared_standardized_distances=[float(d[i]) for i in indices],median_center=center,quantile_offsets=offset,source_origin_counts=dict(counts),OOF_rows=len(rr));support_receipts.append(rec);neighbors[cid]=chosen
   dump('local_CDF_parameters.json',support_receipts)
   sigma=json.loads(source('parameters').read_text())['sigmas']['A_fit_residual_scale'];mus=np.array([float(r['saved_mu']) for r in cal]);y=np.array([float(r['true_RUL']) for r in cal]);med=np.exp(mus);assert np.isfinite(med).all() and (y>0).all()
   lo=np.empty(len(cal));hi=np.empty(len(cal));risks={h:np.empty(len(cal)) for h in [100,300]}
   for i,r in enumerate(cal):
    off,support,cdf=distros[r['cell_id']];mu=mus[i];lo[i]=math.exp(mu+off[0]);hi[i]=math.exp(mu+off[2])
    for h in [100,300]:
     ix=np.searchsorted(support,math.log(h)-mu,side='right');risks[h][i]=cdf[ix-1] if ix else 0.
   assert np.isfinite(lo).all() and np.isfinite(hi).all() and (lo>0).all() and (lo<med).all() and (med<hi).all()
   assert all(np.isfinite(v).all() and ((v>=0)&(v<=1)).all() for v in risks.values())
   base_l=np.exp(mus+sigma*ndtri(.1));base_h=np.exp(mus+sigma*ndtri(.9));base_r={h:ndtr((np.log(h)-mus)/sigma) for h in [100,300]};global_l=np.array([float(r['q10']) for r in cal]);global_h=np.array([float(r['q90']) for r in cal]);global_r={h:np.array([float(r['risk'+str(h)]) for r in cal]) for h in [100,300]}
   arms={'saved_fixed_sigma':(base_l,base_h,base_r),'global_OOF_CDF':(global_l,global_h,global_r),'policy_local_fixed5_CDF':(lo,hi,risks)};pc=[]
   for cid in calids:
    ix=np.array([i for i,r in enumerate(cal) if r['cell_id']==cid])
    for arm,(l,h,rs) in arms.items():
     wid=h[ix]-l[ix];score=wid+10*np.maximum(l[ix]-y[ix],0)+10*np.maximum(y[ix]-h[ix],0);error=med[ix]-y[ix]
     r=dict(cell_id=cid,arm=arm,origins=len(ix),MAE=float(abs(error).mean()),severe_over100=float((error>100).mean()),coverage80=float(((y[ix]>=l[ix])&(y[ix]<=h[ix])).mean()),lower_miss=float((y[ix]<l[ix]).mean()),upper_miss=float((y[ix]>h[ix]).mean()),width80=float(wid.mean()),interval_score80=float(score.mean()),Brier100=float(((rs[100][ix]-(y[ix]<=100))**2).mean()),Brier300=float(((rs[300][ix]-(y[ix]<=300))**2).mean()))
     r['absolute_coverage_error80']=abs(r['coverage80']-.8);pc.append(r)
   keys=[k for k in pc[0] if k not in ['cell_id','arm','origins']];met={a:{k:float(np.mean([r[k] for r in pc if r['arm']==a])) for k in keys} for a in arms};cmp={}
   for ref in ['saved_fixed_sigma','global_OOF_CDF']:
    a,b=met[ref],met['policy_local_fixed5_CDF'];u,v=[np.array([r['interval_score80'] for r in pc if r['arm']==arm]) for arm in [ref,'policy_local_fixed5_CDF']];bs=np.random.default_rng(42).integers(0,10,(2000,10));ci=np.quantile((u-v)[bs].mean(axis=1),[.025,.975]).tolist();improved=sum(next(r['absolute_coverage_error80'] for r in pc if r['cell_id']==cid and r['arm']=='policy_local_fixed5_CDF')<next(r['absolute_coverage_error80'] for r in pc if r['cell_id']==cid and r['arm']==ref) for cid in calids)
    x=dict(point_MAE_unchanged=a['MAE']==b['MAE'],interval_score_relative_reduction=1-b['interval_score80']/a['interval_score80'],pairedcell_score_difference_CI95=ci,mean_cell_absolute_coverage_error_reduction=a['absolute_coverage_error80']-b['absolute_coverage_error80'],aggregate_coverage_error_reduction=abs(a['coverage80']-.8)-abs(b['coverage80']-.8),coverage_error_cells_improved=improved,width_ratio=b['width80']/a['width80'],mean_Brier_increment=(b['Brier100']+b['Brier300']-a['Brier100']-a['Brier300'])/2,any_crossing_origins=0)
    checks=dict(point=x['point_MAE_unchanged'],score=x['interval_score_relative_reduction']>=.05,CI=ci[0]>0,cell_coverage=x['mean_cell_absolute_coverage_error_reduction']>=.03,aggregate=x['aggregate_coverage_error_reduction']>=-1e-12,cells=improved>=7,width=x['width_ratio']<=2,Brier=x['mean_Brier_increment']<=.002,coherence=True);x.update(checks=checks,gate_pass=all(checks.values()),primary_reference=ref=='saved_fixed_sigma');cmp[ref]=x
   with (O/'calibration_distribution.csv').open('x',newline='') as f:
    w=csv.writer(f);w.writerow(['cell_id','origin','true_RUL','saved_mu','q10','q50','q90','risk100','risk300'])
    for i,r in enumerate(cal):w.writerow([r['cell_id'],r['origin'],r['true_RUL'],float(mus[i]),float(lo[i]),float(med[i]),float(hi[i]),float(risks[100][i]),float(risks[300][i])])
   dump('metrics.json',met);dump('per_cell_metrics.json',pc);dump('comparisons.json',cmp)
   dump('completion.json',dict(status='COMPLETE_FIXED5_POLICY_LOCAL_OOF_CDF',new_fits=0,new_model_inference=0,checkpoint_loads=0,raw_feature_reads=0,dev_test_reads=0,train_policy_transform_estimates=1,local_CDF_estimates=10,OOF_rows=22281,calibration_rows=4567,runner_sha256=sha(Path(__file__)),protocol_sha256=sha(O/'protocol.json'),GO_sha256=sha(O/'ROOT_GO.json'),prediction_sha256=sha(O/'calibration_distribution.csv'),elapsed_seconds=time.monotonic()-start))
   signal.setitimer(signal.ITIMER_REAL,0);print(json.dumps(dict(metrics=met,comparisons=cmp)))
  except BaseException as e:
   dump('failure.json',dict(status='FAILED_STOP_NO_RETRY',type=type(e).__name__,error=str(e)));raise
if __name__=='__main__':main()
