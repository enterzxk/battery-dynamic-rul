from pathlib import Path
import json,csv,hashlib,time
import numpy as np
from scipy.special import log_ndtr,ndtri_exp,ndtr,ndtri
R=Path('/home/yndx/zxk/rul');O=R/'reports/frozen_probability_audit_20261018_root'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,x):
 with (O/n).open('x') as f:json.dump(x,f,separators=(',',':'));f.write('\n')
start=time.monotonic();p=json.loads((O/'protocol.json').read_text());sp=R/p['source_predictions'];fp=R/p['source_parameters'];assert sha(sp)==p['prediction_sha256'] and sha(fp)==p['parameter_sha256'];s=json.loads(fp.read_text())['sigmas'][p['sigma_key']];assert s==p['sigma'];rr=list(csv.DictReader(sp.open()));assert len(rr)==4567;ids=sorted({x['cell_id'] for x in rr});assert len(ids)==10 and all(x['role']=='calibration' for x in rr);pc=[];minq=float('inf');maxprob=-float('inf')
for cid in ids:
 rows=sorted([r for r in rr if r['cell_id']==cid],key=lambda r:int(r['origin']));t=np.array([int(x['origin']) for x in rows]);d=t-100;y=np.array([float(x['true_RUL']) for x in rows]);mu=np.array([float(x['mu_log_RUL']) for x in rows]);m=mu[0];assert t[0]==100 and np.all(y+t==int(rows[0]['event_cycle']));ls=np.zeros(len(d));z=d>0;ls[z]=log_ndtr(-(np.log(d[z])-m)/s)
 for arm in p['arms']:
  if arm=='early_survival_conditioned':
   lo=np.exp(m-s*ndtri_exp(ls+np.log(.9)))-d;hi=np.exp(m-s*ndtri_exp(ls+np.log(.1)))-d;med=np.exp(m-s*ndtri_exp(ls+np.log(.5)))-d;risks={h:-np.expm1(log_ndtr(-(np.log(d+h)-m)/s)-ls) for h in [100,300]}
  else:lo=np.exp(mu+s*ndtri(.1));hi=np.exp(mu+s*ndtri(.9));med=np.exp(mu);risks={h:ndtr((np.log(h)-mu)/s) for h in [100,300]}
  assert all(np.isfinite(a).all() for a in [lo,hi,med]+list(risks.values())) and (lo>0).all() and (hi>lo).all() and all(((v>=0)&(v<=1)).all() for v in risks.values());minq=min(minq,float(lo.min()));maxprob=max(maxprob,max(float(x.max()) for x in risks.values()));width=hi-lo;score=width+10*np.maximum(lo-y,0)+10*np.maximum(y-hi,0)
  r=dict(cell_id=cid,arm=arm,origins=len(y),MAE=float(abs(med-y).mean()),coverage80=float(((y>=lo)&(y<=hi)).mean()),width80=float(width.mean()),interval_score80=float(score.mean()),lower_miss=float((y<lo).mean()),upper_miss=float((y>hi).mean()))
  for h,zp in risks.items():r.update({f'Brier{h}':float(((zp-(y<=h))**2).mean()),f'mean_risk{h}':float(zp.mean()),f'observed_event_fraction{h}':float((y<=h).mean())})
  pc.append(r)
keys=[k for k in pc[0] if k not in ['cell_id','arm','origins']];met={a:{k:float(np.mean([x[k] for x in pc if x['arm']==a])) for k in keys} for a in p['arms']};a=met[p['arms'][0]];b=met[p['arms'][1]];improved=sum(abs(next(x['coverage80'] for x in pc if x['cell_id']==cid and x['arm']=='saved_dynamic')-.8)<abs(next(x['coverage80'] for x in pc if x['cell_id']==cid and x['arm']=='early_survival_conditioned')-.8) for cid in ids)
cmp=dict(point_MAE_reduction=1-b['MAE']/a['MAE'],interval_score_reduction=1-b['interval_score80']/a['interval_score80'],absolute_coverage_error_reduction=abs(a['coverage80']-.8)-abs(b['coverage80']-.8),width_ratio=b['width80']/a['width80'],mean_Brier_increment=(b['Brier100']+b['Brier300']-a['Brier100']-a['Brier300'])/2,cells_coverage_error_improved=improved)
cmp['joint_probability_gate']=bool(cmp['point_MAE_reduction']>=.05 and cmp['interval_score_reduction']>=.05 and cmp['absolute_coverage_error_reduction']>=.03 and cmp['width_ratio']<=2 and cmp['mean_Brier_increment']<=.002 and improved>=7)
dump('results.json',dict(metrics=met,per_cell=pc,comparison=cmp));dump('completion.json',dict(status='COMPLETE_FROZEN_DISTRIBUTION_RELIABILITY_AUDIT',rows=4567,cells=10,new_fits=0,optimizer_steps=0,new_model_inference=0,new_scalar_estimates=0,checkpoint_loads=0,dev_test_reads=0,prediction_sha256=sha(sp),parameter_sha256=sha(fp),script_sha256=sha(Path(__file__)),protocol_sha256=sha(O/'protocol.json'),minimum_lower_quantile=minq,maximum_horizon_probability=maxprob,elapsed_seconds=time.monotonic()-start));print(json.dumps(dict(metrics=met,comparison=cmp)))
