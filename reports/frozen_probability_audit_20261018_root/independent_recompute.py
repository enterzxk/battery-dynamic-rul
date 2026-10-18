from pathlib import Path
import json,csv,math,statistics
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent;p=json.loads((O/'protocol.json').read_text());s=p['sigma'];rows=list(csv.DictReader((R/p['source_predictions']).open()));acc={a:[] for a in p['arms']};sq=math.sqrt(2)
def sf(z):return .5*math.erfc(z/sq)
def quantile(z,target):
 lo=z;hi=max(1.,z+1)
 while sf(hi)>target:hi+=2
 for _ in range(70):
  m=(lo+hi)/2
  if sf(m)>target:lo=m
  else:hi=m
 return (lo+hi)/2
for cid in sorted({r['cell_id'] for r in rows}):
 rr=sorted([r for r in rows if r['cell_id']==cid],key=lambda r:int(r['origin']));m=float(rr[0]['mu_log_RUL']);tmp={a:[] for a in acc}
 for r in rr:
  d=int(r['origin'])-100;y=float(r['true_RUL']);mu=float(r['mu_log_RUL']);z=(math.log(d)-m)/s if d else -40.;Sd=sf(z)
  for a in acc:
   if a=='early_survival_conditioned':
    lo=math.exp(m+s*quantile(z,.9*Sd))-d;hi=math.exp(m+s*quantile(z,.1*Sd))-d;risks={h:1-sf((math.log(d+h)-m)/s)/Sd for h in [100,300]}
   else:
    nd=statistics.NormalDist();lo=math.exp(mu+s*nd.inv_cdf(.1));hi=math.exp(mu+s*nd.inv_cdf(.9));risks={h:1-sf((math.log(h)-mu)/s) for h in [100,300]}
   score=hi-lo+10*max(lo-y,0)+10*max(y-hi,0);tmp[a].append(dict(coverage80=float(lo<=y<=hi),width80=hi-lo,interval_score80=score,Brier100=(risks[100]-(y<=100))**2,Brier300=(risks[300]-(y<=300))**2))
 for a,rrr in tmp.items():acc[a].append({k:statistics.mean(x[k] for x in rrr) for k in rrr[0]})
met={a:{k:statistics.mean(x[k] for x in r) for k in r[0]} for a,r in acc.items()};ref=json.loads((O/'results.json').read_text())['metrics'];diff=max(abs(met[a][k]-ref[a][k]) for a in met for k in met[a]);assert diff<1e-9
out=dict(status='PASS_INDEPENDENT_ERFC_BISECTION_ALL4567',max_absolute_metric_difference=diff,metrics=met,new_fits=0,new_model_inference=0)
with (O/'independent_metrics.json').open('x') as f:json.dump(out,f,separators=(',',':'));f.write('\n')
print(json.dumps(out))
