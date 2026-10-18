from pathlib import Path
import json,csv,hashlib,time,fcntl,datetime
import numpy as np
from scipy.special import log_ndtr,ndtri_exp,ndtr,ndtri
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent
sha=lambda x:hashlib.sha256(x.read_bytes()).hexdigest()
def dump(n,x):
 with (O/n).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
start=time.monotonic();p=json.loads((O/'protocol.json').read_text())
sp=R/p['source_predictions'];fp=R/p['source_parameters']
assert sha(sp)==p['prediction_sha256'] and sha(fp)==p['parameter_sha256']
s=json.loads(fp.read_text())['sigmas'][p['sigma_key']];assert s==p['sigma']
lock=open(R/'automation/state/online_survival_cpu.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
c=json.loads((R/'automation/state/coordinator.json').read_text());assert c['owner']=='01a14e92-ea7a-7cc3-8007-67b4d16a873a' and c['new_fits_allowed']==False
rr=list(csv.DictReader(sp.open()));assert len(rr)==4567 and all(r['role']=='calibration' for r in rr)
ids=sorted({r['cell_id'] for r in rr});assert len(ids)==10
pc=[];examples=[];minq=float('inf');conditional_quantile_error=0.
with (O/'derived_distribution_predictions.csv').open('x') as f:
 fields=['cell_id','origin','true_RUL','arm','q10','q50','q90','risk100','risk300'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
 for cid in ids:
  rows=sorted([r for r in rr if r['cell_id']==cid],key=lambda r:int(r['origin']))
  t=np.array([int(x['origin']) for x in rows]);d=t-100;y=np.array([float(x['true_RUL']) for x in rows]);mu=np.array([float(x['context_RUL_raw_log']) for x in rows]);oldmu=np.array([float(x['mu_log_RUL']) for x in rows]);m=mu[0]
  assert t[0]==100 and np.array_equal(t,np.arange(100,int(rows[0]['event_cycle']))) and np.all(y+t==int(rows[0]['event_cycle']))
  assert np.max(abs(np.exp(mu)-np.array([float(x['context_RUL_prediction']) for x in rows])))<1e-10
  ls=np.zeros(len(d));z=d>0;ls[z]=log_ndtr(-(np.log(d[z])-m)/s)
  for arm in p['arms']:
   if arm=='policy_early_survival_conditioned':
    lo,med,hi=[np.exp(m-s*ndtri_exp(ls+np.log(1-q)))-d for q in [.1,.5,.9]]
    risks={h:-np.expm1(log_ndtr(-(np.log(d+h)-m)/s)-ls) for h in p['horizons']}
    for q,qv in zip([.1,.5,.9],[lo,med,hi]):conditional_quantile_error=max(conditional_quantile_error,float(np.max(abs(np.exp(log_ndtr(-(np.log(d+qv)-m)/s)-ls)-(1-q)))))
   else:
    u=mu if arm=='policy_dynamic' else oldmu
    lo,med,hi=[np.exp(u+s*ndtri(q)) for q in [.1,.5,.9]];risks={h:ndtr((np.log(h)-u)/s) for h in p['horizons']}
   assert all(np.isfinite(v).all() for v in [lo,med,hi]+list(risks.values())) and (lo>0).all() and (lo<med).all() and (med<hi).all() and all(((v>=0)&(v<=1)).all() for v in risks.values())
   minq=min(minq,float(lo.min()));e=med-y;width=hi-lo;score=width+10*np.maximum(lo-y,0)+10*np.maximum(y-hi,0)
   rec=dict(cell_id=cid,arm=arm,origins=len(y),MAE=float(abs(e).mean()),bias=float(e.mean()),severe_over100=float((e>100).mean()),coverage80=float(((y>=lo)&(y<=hi)).mean()),width80=float(width.mean()),interval_score80=float(score.mean()),lower_miss=float((y<lo).mean()),upper_miss=float((y>hi).mean()))
   for h,risk in risks.items():rec.update({f'Brier{h}':float(((risk-(y<=h))**2).mean()),f'mean_risk{h}':float(risk.mean()),f'observed_event_fraction{h}':float((y<=h).mean())})
   pc.append(rec)
   for i in range(len(y)):
    r=dict(cell_id=cid,origin=int(t[i]),true_RUL=float(y[i]),arm=arm,q10=float(lo[i]),q50=float(med[i]),q90=float(hi[i]),risk100=float(risks[100][i]),risk300=float(risks[300][i]));w.writerow(r)
    if i in [0,len(y)//2,len(y)-1]:examples.append(r)
keys=[k for k in pc[0] if k not in ['cell_id','arm','origins']];met={a:{k:float(np.mean([x[k] for x in pc if x['arm']==a])) for k in keys} for a in p['arms']}
get=lambda a,cid:next(x for x in pc if x['cell_id']==cid and x['arm']==a)
comparisons={}
for ref in ['policy_early_survival_conditioned','three_state_dynamic_reference']:
 a=met[ref];b=met['policy_dynamic'];delta=np.array([get(ref,cid)['MAE']-get('policy_dynamic',cid)['MAE'] for cid in ids]);rng=np.random.default_rng(42);boot=np.mean(delta[rng.integers(0,10,size=(2000,10))],axis=1);ci=np.quantile(boot,[.025,.975]).tolist();improved=sum(abs(get('policy_dynamic',cid)['coverage80']-.8)<abs(get(ref,cid)['coverage80']-.8) for cid in ids)
 cmp=dict(point_MAE_reduction=1-b['MAE']/a['MAE'],cells_MAE_improved=int((delta>0).sum()),pairedcell_MAE_difference_CI95=ci,severe_over100_increment=b['severe_over100']-a['severe_over100'],interval_score_reduction=1-b['interval_score80']/a['interval_score80'],absolute_coverage_error_reduction=abs(a['coverage80']-.8)-abs(b['coverage80']-.8),width_ratio=b['width80']/a['width80'],mean_Brier_increment=(b['Brier100']+b['Brier300']-a['Brier100']-a['Brier300'])/2,cells_coverage_error_improved=improved)
 cmp['point_development_gate_pass']=bool(cmp['point_MAE_reduction']>=.05 and cmp['cells_MAE_improved']>=7 and ci[0]>0 and cmp['severe_over100_increment']<=.01)
 checks=dict(point_gate=cmp['point_development_gate_pass'],interval_score=cmp['interval_score_reduction']>=.05,coverage_error=cmp['absolute_coverage_error_reduction']>=.03,width=cmp['width_ratio']<=2,Brier=cmp['mean_Brier_increment']<=.002,cell_coverage=improved>=7)
 cmp['probability_checks']={k:bool(v) for k,v in checks.items()};cmp['joint_probability_gate_pass']=all(checks.values());comparisons['policy_dynamic_vs_'+ref]=cmp
assert conditional_quantile_error<1e-10
dump('metrics.json',met);dump('per_cell_metrics.json',pc);dump('comparisons.json',comparisons);dump('arithmetic_examples.json',examples)
dump('completion.json',dict(status='COMPLETE_FROZEN_POLICY_SURVIVAL_PROBABILITY_DIAGNOSTIC',cells=10,origins=4567,derived_rows=13701,new_fits=0,optimizer_steps=0,new_scalar_estimates=0,new_model_inference=0,checkpoint_loads=0,dev_test_reads=0,prediction_sha256=sha(sp),parameter_sha256=sha(fp),protocol_sha256=sha(O/'protocol.json'),script_sha256=sha(Path(__file__)),derived_predictions_sha256=sha(O/'derived_distribution_predictions.csv'),minimum_q10=minq,max_conditional_quantile_survival_error=conditional_quantile_error,elapsed_seconds=time.monotonic()-start,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
print(json.dumps(dict(metrics=met,comparisons=comparisons)))
