from pathlib import Path
import json,csv,math,statistics,bisect
from fractions import Fraction
from collections import Counter
import numpy as np
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent
p=json.loads((O/'protocol.json').read_text());src=lambda k:R/p['sources'][k]['path']
oo=list(csv.DictReader(src('OOF').open()));cal=list(csv.DictReader(src('calibration').open()));out=list(csv.DictReader((O/'calibration_distribution.csv').open()));pars=json.loads((O/'local_CDF_parameters.json').read_text());transform=json.loads((O/'train_transform.json').read_text());policy={r['cell_id']:r for r in json.loads(src('policy').read_text())};fitids=sorted({r['cell_id'] for r in oo});assert len(fitids)==42 and len(pars)==10 and len(out)==len(cal)==4567
fields=p['policy_columns'];mean=transform['mean'];sd=transform['population_SD'];active=[i for i,s in enumerate(sd) if s>1e-12];diff=0.
for j,k in enumerate(fields):
 v=[float(policy[c][k]) for c in fitids];diff=max(diff,abs(statistics.mean(v)-mean[j]),abs(statistics.pstdev(v)-sd[j]))
assert diff<1e-12
Z=np.array([[(float(policy[c][fields[j]])-mean[j])/sd[j] for j in active] for c in fitids]);distros={}
for q in pars:
 cid=q['cell_id'];t=np.array([(float(policy[cid][fields[j]])-mean[j])/sd[j] for j in active]);d=np.sum((Z-t)**2,axis=1);indices=sorted(range(42),key=lambda i:(float(d[i]),fitids[i]))[:5];assert q['source_cells']==[fitids[i] for i in indices] and cid not in q['source_cells']
 rr=[r for r in oo if r['cell_id'] in q['source_cells']];counts=Counter(r['cell_id'] for r in rr);values=sorted((math.log(float(r['true_RUL']))-float(r['oof_mu_log_RUL']),r['cell_id'],int(r['origin'])) for r in rr);acc=Fraction();quant={};prefix=[]
 for v,c,o in values:
  acc+=Fraction(1,5*counts[c]);prefix.append(acc)
  for z in [Fraction(1,10),Fraction(1,2),Fraction(9,10)]:
   if z not in quant and acc>=z:quant[z]=v
 assert acc==1
 center=quant[Fraction(1,2)];off=[quant[z]-center for z in [Fraction(1,10),Fraction(1,2),Fraction(9,10)]];assert max(abs(a-b) for a,b in zip(off,q['quantile_offsets']))<1e-12 and abs(center-q['median_center'])<1e-12
 distros[cid]=(off,[v-center for v,c,o in values],prefix)
sigma=json.loads(src('parameters').read_text())['sigmas']['A_fit_residual_scale'];normal=statistics.NormalDist();vals={};pdiff=0.;cross=0
for r,s in zip(out,cal):
 assert (r['cell_id'],r['origin'],r['true_RUL'],r['saved_mu'])==(s['cell_id'],s['origin'],s['true_RUL'],s['saved_mu'])
 cid=r['cell_id'];mu=float(s['saved_mu']);y=float(s['true_RUL']);m=math.exp(mu);off,support,prefix=distros[cid];lo=math.exp(mu+off[0]);hi=math.exp(mu+off[2]);risk={}
 for h in [100,300]:
  ix=bisect.bisect_right(support,math.log(h)-mu);risk[h]=float(prefix[ix-1]) if ix else 0.
 for k,v in dict(q10=lo,q50=m,q90=hi,risk100=risk[100],risk300=risk[300]).items():pdiff=max(pdiff,abs(float(r[k])-v))
 assert 0<lo<m<hi;cross+=not(float(r['q10'])<float(r['q50'])<float(r['q90']))
 arms=[('saved_fixed_sigma',math.exp(mu+sigma*normal.inv_cdf(.1)),math.exp(mu+sigma*normal.inv_cdf(.9)),{h:normal.cdf((math.log(h)-mu)/sigma) for h in [100,300]}),('global_OOF_CDF',float(s['q10']),float(s['q90']),{h:float(s['risk'+str(h)]) for h in [100,300]}),('policy_local_fixed5_CDF',lo,hi,risk)]
 for arm,l,h,rs in arms:
  e=m-y;v=dict(MAE=abs(e),severe_over100=e>100,coverage80=l<=y<=h,lower_miss=y<l,upper_miss=y>h,width80=h-l,interval_score80=h-l+10*max(l-y,0)+10*max(y-h,0),Brier100=(rs[100]-(y<=100))**2,Brier300=(rs[300]-(y<=300))**2);vals.setdefault((cid,arm),[]).append(v)
pc=[]
for (cid,arm),vv in sorted(vals.items()):
 v=dict(cell_id=cid,arm=arm,**{k:statistics.mean(x[k] for x in vv) for k in vv[0]});v['absolute_coverage_error80']=abs(v['coverage80']-.8);pc.append(v)
met={a:{k:statistics.mean(r[k] for r in pc if r['arm']==a) for k in pc[0] if k not in ['cell_id','arm']} for a in ['saved_fixed_sigma','global_OOF_CDF','policy_local_fixed5_CDF']};ref=json.loads((O/'metrics.json').read_text());mdiff=max(abs(v-ref[a][k]) for a,m in met.items() for k,v in m.items());assert mdiff<1e-9 and pdiff<1e-9 and cross==0
result=dict(status='PASS_TRAIN_ONLY_TRANSFORM_NEIGHBORS_CDF_AND_ALL4567_METRICS',cells=10,rows=4567,source_OOF_cells=42,maximum_transform_difference=diff,maximum_prediction_difference=pdiff,maximum_metric_difference=mdiff,zero_crossings=True,metrics=met,new_fits=0,new_model_inference=0)
with (O/'independent_metrics.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in result.items() if k!='metrics'}))
