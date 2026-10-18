from pathlib import Path
import json,csv,math,statistics
from scipy.stats import norm
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent;p=json.loads((O/'protocol.json').read_text());src=list(csv.DictReader((R/p['sources']['point_predictions']['path']).open()));rows=list(csv.DictReader((O/'mixture_predictions.csv').open()));assert len(src)==len(rows)==4567
first={r['cell_id']:float(r['schedule_RUL_raw_log']) for r in src if int(r['origin'])==100};sigma=p['sigma'];vals={};cdferr=0.;riskerr=0.;cdf_functions=[]
for r,s in zip(rows,src):
 assert (r['cell_id'],r['origin'],r['true_RUL'])==(s['cell_id'],s['origin'],s['true_RUL'])
 cid=r['cell_id'];d=int(r['origin'])-100;m0=first[cid];mu=float(s['schedule_RUL_raw_log']);y=float(r['true_RUL']);ls=0. if d==0 else float(norm.logsf((math.log(d)-m0)/sigma))
 def cdf(x,d=d,m0=m0,mu=mu,ls=ls):return -.5*math.expm1(float(norm.logsf((math.log(d+x)-m0)/sigma))-ls)+.5*float(norm.cdf((math.log(x)-mu)/sigma))
 cdf_functions.append(cdf);lo,med,hi=[float(r[k]) for k in ['q10','q50','q90']];assert 0<lo<med<hi
 for q,z in zip([.1,.5,.9],[lo,med,hi]):cdferr=max(cdferr,abs(cdf(z)-q))
 risk={h:float(r['risk'+str(h)]) for h in [100,300]}
 for h,v in risk.items():riskerr=max(riskerr,abs(v-cdf(h)))
 e=med-y;v=dict(MAE=abs(e),bias=e,severe_over100=e>100,coverage80=lo<=y<=hi,width80=hi-lo,interval_score80=hi-lo+10*max(lo-y,0)+10*max(y-hi,0),Brier100=(risk[100]-(y<=100))**2,Brier300=(risk[300]-(y<=300))**2);vals.setdefault(cid,[]).append(v)
pc=[dict(cell_id=cid,**{k:statistics.mean(x[k] for x in v) for k in v[0]}) for cid,v in sorted(vals.items())];met={k:statistics.mean(r[k] for r in pc) for k in pc[0] if k!='cell_id'};ref=json.loads((O/'metrics.json').read_text())['fixed_half_CDF_mixture'];diff=max(abs(v-ref[k]) for k,v in met.items());assert diff<1e-9 and cdferr<1e-10 and riskerr<1e-10
bisect_error=0.;examples=[]
for j in [0,len(rows)//2,len(rows)-1]:
 cdf=cdf_functions[j];r=rows[j]
 for q,key in [(.1,'q10'),(.5,'q50'),(.9,'q90')]:
  a=0.;b=max(float(r['q90'])*10,10000.)
  while cdf(b)<q:b*=2
  for k in range(80):
   mid=(a+b)/2
   if cdf(mid)<q:a=mid
   else:b=mid
  val=(a+b)/2;err=abs(val-float(r[key]));bisect_error=max(bisect_error,err);examples.append(dict(cell_id=r['cell_id'],origin=int(r['origin']),quantile=q,difference=err))
assert bisect_error<1e-8
result=dict(status='PASS_ALL4567_INDEPENDENT_CDF_METRICS_AND_THREE_BISECTIONS',rows=4567,cells=10,maximum_metric_difference=diff,maximum_quantile_CDF_error=cdferr,maximum_risk_difference=riskerr,maximum_bisection_difference=bisect_error,metrics=met,examples=examples,new_fits=0,new_model_inference=0)
with (O/'independent_metrics.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['metrics','examples']}))
