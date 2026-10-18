from pathlib import Path
import json,csv,math,statistics
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent;p=json.loads((O/'protocol.json').read_text());src=list(csv.DictReader((R/p['source']).open()));derived={(r['cell_id'],int(r['origin'])):r for r in csv.DictReader((O/'derived_predictions.csv').open())};ids=sorted({r['cell_id'] for r in src});a=p['alpha'];b=1-a;met={arm:[] for arm in p['arms']};maxdiff=0.;expired=0
for cid in ids:
 rr=sorted([r for r in src if r['cell_id']==cid],key=lambda r:int(r['origin']));E=[int(r['origin'])+float(r['context_RUL_prediction']) for r in rr];err={arm:[] for arm in p['arms']}
 for j,r in enumerate(rr):
  t=int(r['origin']);y=float(r['true_RUL']);smooth=b**j*E[0]+a*math.fsum(b**(j-k)*E[k] for k in range(1,j+1));pred=max(0.,smooth-t);ref=derived[cid,t];maxdiff=max(maxdiff,abs(smooth-float(ref['EMA_absolute_EOL'])),abs(pred-float(ref['EMA_RUL'])));expired+=pred==0
  for arm,v in zip(p['arms'],[float(r['context_RUL_prediction']),pred]):err[arm].append(v-y)
 for arm,e in err.items():met[arm].append(dict(MAE=statistics.mean(abs(v) for v in e),bias=statistics.mean(e),severe_over100=statistics.mean(v>100 for v in e)))
met={arm:{k:statistics.mean(r[k] for r in cells) for k in cells[0]} for arm,cells in met.items()};ref=json.loads((O/'metrics.json').read_text());diff=max(abs(met[a][k]-ref[a][k]) for a in met for k in met[a]);assert len(derived)==4567 and maxdiff<1e-9 and diff<1e-9 and expired==json.loads((O/'comparison.json').read_text())['EMA_expired_count']
out=dict(status='PASS_ALL4567_INDEPENDENT_CLOSED_FORM_CONVOLUTION',rows=4567,maximum_prediction_difference=maxdiff,maximum_metric_difference=diff,expired_count=expired,metrics=met,new_fits=0,new_model_inference=0)
with (O/'independent_metrics.json').open('x') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in out.items() if k!='metrics'}))
