from pathlib import Path
import json,csv,math,statistics
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent
p=json.loads((O/'protocol.json').read_text());sigma=p['sigma'];rows=list(csv.DictReader((R/p['source_predictions']).open()));ids=sorted({r['cell_id'] for r in rows});metrics={a:[] for a in p['arms']};max_pred_diff=0.;checked=0
for cid in ids:
 rr=sorted([r for r in rows if r['cell_id']==cid],key=lambda r:int(r['origin']));mu=float(rr[0]['mu_log_RUL']);preds={a:[] for a in p['arms']}
 for r in rr:
  d=int(r['origin'])-100;truth=float(r['true_RUL'])
  if d==0:q=math.exp(mu)
  else:
   z=(math.log(d)-mu)/sigma;target=.5*.5*math.erfc(z/math.sqrt(2));lo=z;hi=max(1.,z+1.)
   while .5*math.erfc(hi/math.sqrt(2))>target:hi+=2
   for k in range(70):
    mid=(lo+hi)/2
    if .5*math.erfc(mid/math.sqrt(2))>target:lo=mid
    else:hi=mid
   q=math.exp(mu+sigma*(lo+hi)/2)
  values=[max(0.,math.exp(mu)-d),q-d,math.exp(float(r['mu_log_RUL']))];assert values[1]>0
  for a,zp in zip(p['arms'],values):preds[a].append(zp-truth)
  checked+=1
 for a,err in preds.items():metrics[a].append(dict(MAE=statistics.mean(abs(e) for e in err),bias=statistics.mean(err),severe_over100=statistics.mean(e>100 for e in err)))
met={a:{k:statistics.mean(r[k] for r in vv) for k in ['MAE','bias','severe_over100']} for a,vv in metrics.items()};ref=json.loads((O/'metrics.json').read_text());diff=max(abs(met[a][k]-ref[a][k]) for a in ref for k in ref[a]);assert diff<1e-9 and checked==4567
out=dict(status='PASS_ALL_ROWS_INDEPENDENT_ERFC_BISECTION',rows=checked,metrics=met,max_absolute_metric_difference=diff,new_fits=0,new_model_inference=0)
with (O/'independent_metrics.json').open('x') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(out))
