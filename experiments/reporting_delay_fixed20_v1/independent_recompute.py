from pathlib import Path
import csv,json,math,hashlib
from collections import defaultdict
from statistics import fmean
from scipy.stats import lognorm
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent
rows=list(csv.DictReader((O/'predictions.csv').open())); assert len(rows)==21835
p=json.loads((O/'protocol.json').read_text()); original=list(csv.DictReader((R/p['sources']['point']['path']).open())); by={(r['cell_id'],int(r['origin'])):r for r in original}
groups=defaultdict(list)
for r in rows:groups[(r['cell_id'],r['arm'])].append(r)
ks=['MAE','bias','severe_over100','coverage80','width80','interval_score80','Brier100','Brier300']; per=[]
for (cid,arm),rr in groups.items():
 agg={k:[] for k in ks}
 for r in rr:
  y=float(r['true_RUL']); l,m,h=[float(r[k]) for k in ['q10','q50','q90']]; e=m-y
  vals=[abs(e),e,float(e>100),float(l<=y<=h),h-l,h-l+10*max(l-y,0)+10*max(y-h,0)]+[(float(r['risk'+str(t)])-float(y<=t))**2 for t in [100,300]]
  for k,v in zip(ks,vals):agg[k].append(v)
 per.append(dict(cell_id=cid,arm=arm,origins=len(rr),**{k:fmean(v) for k,v in agg.items()}))
metrics=json.loads((O/'metrics.json').read_text()); error=max(abs(fmean(r[k] for r in per if r['arm']==a)-metrics[a][k]) for a in metrics for k in ks); assert error<1e-10
example_errors=[]
for cid in sorted({r['cell_id'] for r in rows}):
 rr=[r for r in rows if r['cell_id']==cid and r['arm']=='lag20_dynamic_survival']
 for r in [rr[0],rr[len(rr)//2],rr[-1]]:
  mu=float(by[(cid,int(r['origin'])-20)]['schedule_RUL_raw_log']); dist=lognorm(s=p['sigma'],scale=math.exp(mu)); norm=dist.sf(20)
  for q,k in [(.1,'q10'),(.5,'q50'),(.9,'q90')]:example_errors.append(abs((1-dist.sf(20+float(r[k]))/norm)-q))
  for t in [100,300]:example_errors.append(abs((1-dist.sf(20+t)/norm)-float(r['risk'+str(t)])))
assert max(example_errors)<1e-10
primary=json.loads((O/'comparisons.json').read_text())['lag20_half_CDF_vs_early_survival']; passed=1-metrics['lag20_half_CDF']['MAE']/metrics['early_survival']['MAE']>=.05 and sum(next(r['MAE'] for r in per if r['arm']=='lag20_half_CDF' and r['cell_id']==cid)<next(r['MAE'] for r in per if r['arm']=='early_survival' and r['cell_id']==cid) for cid in sorted({r['cell_id'] for r in rows}))>=7 and metrics['lag20_half_CDF']['severe_over100']-metrics['early_survival']['severe_over100']<=.01 and primary['pairedcell_MAE_difference_CI95'][0]>0
assert bool(passed)==primary['point_risk_retention_gate_pass']
v={'status':'PASS_INDEPENDENT_SAVED_OUTPUT_RECOMPUTE','rows':len(rows),'groups':len(groups),'maximum_macro_metric_difference':error,'scalar_lognormal_CDF_examples':len(example_errors),'maximum_scalar_CDF_difference':max(example_errors),'primary_gate_agrees':True,'new_fit_or_model_inference':0,'raw_features_or_devtest':0}
with (O/'independent_validation.json').open('x') as f:json.dump(v,f,indent=2);f.write('\n')
print(json.dumps(v))
