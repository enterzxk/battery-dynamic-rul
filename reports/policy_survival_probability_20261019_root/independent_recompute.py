from pathlib import Path
import csv,json,math,statistics,hashlib
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent;p=json.loads((O/'protocol.json').read_text());sigma=p['sigma'];src=list(csv.DictReader((R/p['source_predictions']).open()));ref=list(csv.DictReader((O/'derived_distribution_predictions.csv').open()));lookup={(r['cell_id'],int(r['origin']),r['arm']):r for r in ref};ids=sorted({r['cell_id'] for r in src});normal=statistics.NormalDist();maxpred=0.;computed={a:[] for a in p['arms']};maxz=-1e9;minsurv=1.
def survival(z):return .5*math.erfc(z/math.sqrt(2))
def conditional_q(mu,d,q):
 if d==0:return math.exp(mu+sigma*normal.inv_cdf(q))
 z=(math.log(d)-mu)/sigma;target=(1-q)*survival(z);assert target>0
 low=z;high=max(1.,z+1.)
 while survival(high)>target:high+=2
 for _ in range(70):
  mid=(low+high)/2
  if survival(mid)>target:low=mid
  else:high=mid
 return math.exp(mu+sigma*(low+high)/2)-d
for cid in ids:
 rr=sorted([r for r in src if r['cell_id']==cid],key=lambda r:int(r['origin']));m=float(rr[0]['context_RUL_raw_log']);values={a:[] for a in p['arms']}
 for row in rr:
  d=int(row['origin'])-100;y=float(row['true_RUL'])
  for arm in p['arms']:
   if arm=='policy_early_survival_conditioned':
    qs=[conditional_q(m,d,q) for q in [.1,.5,.9]];surv=1. if d==0 else survival((math.log(d)-m)/sigma);minsurv=min(minsurv,surv);risks=[1-survival((math.log(d+h)-m)/sigma)/surv for h in p['horizons']]
   else:
    mu=float(row['context_RUL_raw_log'] if arm=='policy_dynamic' else row['mu_log_RUL']);qs=[math.exp(mu+sigma*normal.inv_cdf(q)) for q in [.1,.5,.9]];risks=[.5*math.erfc(-(math.log(h)-mu)/(sigma*math.sqrt(2))) for h in p['horizons']]
   for k,v in zip(['q10','q50','q90','risk100','risk300'],qs+risks):maxpred=max(maxpred,abs(v-float(lookup[cid,int(row['origin']),arm][k])))
   lo,med,hi=qs;e=med-y;v=dict(MAE=abs(e),bias=e,severe_over100=e>100,coverage80=lo<=y<=hi,width80=hi-lo,interval_score80=hi-lo+10*max(lo-y,0)+10*max(y-hi,0),lower_miss=y<lo,upper_miss=y>hi)
   for h,risk in zip(p['horizons'],risks):v.update({f'Brier{h}':(risk-(y<=h))**2,f'mean_risk{h}':risk,f'observed_event_fraction{h}':y<=h})
   values[arm].append(v)
 for arm,vv in values.items():computed[arm].append({k:statistics.mean(v[k] for v in vv) for k in vv[0]})
met={a:{k:statistics.mean(v[k] for v in cells) for k in cells[0]} for a,cells in computed.items()};target=json.loads((O/'metrics.json').read_text());diff=max(abs(met[a][k]-target[a][k]) for a in met for k in met[a]);assert len(ref)==13701 and maxpred<1e-9 and diff<1e-9
out=dict(status='PASS_ALL_ROWS_INDEPENDENT_STANDARD_MATH_ERFC_BISECTION',origins=4567,distribution_rows=13701,new_fits=0,new_model_inference=0,new_scalar_estimates=0,maximum_prediction_difference=maxpred,maximum_metric_difference=diff,minimum_early_survival_probability=minsurv,metrics=met,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
with (O/'independent_metrics.json').open('x') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in out.items() if k!='metrics'}))
