from pathlib import Path
import json,csv,math,statistics
from scipy.stats import norm
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent;p=json.loads((O/'protocol.json').read_text());rows=list(csv.DictReader((O/'derived_distribution_predictions.csv').open()));src=list(csv.DictReader((R/p['source_predictions']).open()));assert len(src)==4567 and len(rows)==13701
sigma=p['sigma'];first={};source={}
for r in src:
 cid=r['cell_id'];t=int(r['origin']);source[(cid,t)]=r
 if t==100:first[cid]=float(r['schedule_RUL_raw_log'])
vals={};maxrisk=0.;maxcdf=0.
for r in rows:
 cid=r['cell_id'];t=int(r['origin']);y=float(r['true_RUL']);arm=r['arm'];s=source[(cid,t)];d=t-100;m=first[cid];logsurv=0. if d==0 else float(norm.logsf((math.log(d)-m)/sigma))
 def cdf(q):
  if arm=='lossless_early_survival_conditioned':return -math.expm1(float(norm.logsf((math.log(d+q)-m)/sigma))-logsurv)
  mu=float(s['schedule_RUL_raw_log'] if arm=='lossless_dynamic' else s['context_RUL_raw_log']);return float(norm.cdf((math.log(q)-mu)/sigma))
 lo,med,hi=[float(r[k]) for k in ['q10','q50','q90']];assert 0<lo<med<hi
 for q,z in zip([.1,.5,.9],[lo,med,hi]):maxcdf=max(maxcdf,abs(cdf(z)-q))
 risk={h:float(r['risk'+str(h)]) for h in [100,300]}
 for h,v in risk.items():maxrisk=max(maxrisk,abs(v-cdf(h)))
 e=med-y;v=dict(MAE=abs(e),bias=e,severe_over100=e>100,coverage80=lo<=y<=hi,width80=hi-lo,interval_score80=hi-lo+10*max(lo-y,0)+10*max(y-hi,0),lower_miss=y<lo,upper_miss=y>hi)
 for h,z in risk.items():v.update({f'Brier{h}':(z-(y<=h))**2,f'mean_risk{h}':z,f'observed_event_fraction{h}':y<=h})
 vals.setdefault((cid,arm),[]).append(v)
pc=[]
for (cid,arm),vv in sorted(vals.items()):pc.append(dict(cell_id=cid,arm=arm,**{k:statistics.mean(x[k] for x in vv) for k in vv[0]}))
met={a:{k:statistics.mean(x[k] for x in pc if x['arm']==a) for k in pc[0] if k not in ['cell_id','arm']} for a in p['arms']};ref=json.loads((O/'metrics.json').read_text());md=max(abs(v-ref[a][k]) for a,m in met.items() for k,v in m.items());assert md<1e-9 and maxrisk<1e-10 and maxcdf<1e-10
# Three representative conditional rows: independent bisection instead of inverse-normal formula.
cond=[r for r in rows if r['arm']=='lossless_early_survival_conditioned'];examples=[];maxbisect=0.
for r in [cond[0],cond[len(cond)//2],cond[-1]]:
 cid=r['cell_id'];d=int(r['origin'])-100;m=first[cid];ls=0. if d==0 else float(norm.logsf((math.log(d)-m)/sigma))
 for target,key in [(.1,'q10'),(.5,'q50'),(.9,'q90')]:
  a=0.;b=math.exp(m+8*sigma)+d
  for i in range(80):
   mid=(a+b)/2;F=-math.expm1(float(norm.logsf((math.log(d+mid)-m)/sigma))-ls)
   if F<target:a=mid
   else:b=mid
  z=(a+b)/2;dif=abs(z-float(r[key]));maxbisect=max(maxbisect,dif);examples.append(dict(cell_id=cid,origin=int(r['origin']),quantile=target,bisection=z,saved=float(r[key]),difference=dif))
assert maxbisect<1e-8
result=dict(status='PASS_ALL13701_METRICS_FORWARD_CDF_AND_THREE_BISECTION_CASES',source_rows=4567,derived_rows=13701,cells=10,maximum_metric_difference=md,maximum_risk_difference=maxrisk,maximum_quantile_CDF_error=maxcdf,maximum_bisection_difference=maxbisect,examples=examples,metrics=met,new_fits=0,new_model_inference=0)
with (O/'independent_metrics.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['metrics','examples']}))
