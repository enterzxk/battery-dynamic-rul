import csv,json,math,statistics,hashlib
from pathlib import Path
import numpy as np
O=Path(__file__).resolve().parent
rows=list(csv.DictReader((O/'calibration_predictions.csv').open()));assert len(rows)==4567
ids=sorted({r['cell_id'] for r in rows});assert len(ids)==10
metrics={};per={};deltas=[]
for arm,col in [('saved_log_squared','mu_log_RUL'),('native_absolute','native_RUL_prediction')]:
 per[arm]={}
 for cid in ids:
  rr=[r for r in rows if r['cell_id']==cid];err=[]
  for r in rr:
   y=float(r['true_RUL']);assert int(r['event_cycle'])-int(r['origin'])==y and r['role']=='calibration'
   z=math.exp(float(r[col])) if arm=='saved_log_squared' else max(0,float(r['native_RUL_raw']));assert math.isfinite(z)
   if arm=='native_absolute':assert z==float(r[col])
   err.append(z-y)
  per[arm][cid]=dict(MAE=statistics.mean(map(abs,err)),bias=statistics.mean(err),severe_over100=statistics.mean(e>100 for e in err))
 metrics[arm]={k:statistics.mean(x[k] for x in per[arm].values()) for k in ['MAE','bias','severe_over100']}
ref=json.loads((O/'metrics.json').read_text());diff=max(abs(metrics[a][k]-ref[a][k]) for a in ref for k in ref[a]);assert diff<1e-10
for cid in ids:deltas.append(per['saved_log_squared'][cid]['MAE']-per['native_absolute'][cid]['MAE'])
ix=np.random.default_rng(42).integers(0,10,(2000,10));ci=np.quantile(np.array(deltas)[ix].mean(axis=1),[.025,.975]).tolist()
cmp=json.loads((O/'comparison.json').read_text());assert np.max(abs(np.array(ci)-cmp['pairedcell_MAE_difference_CI95']))<1e-10
result=dict(status='PASS_INDEPENDENT_CSV_RECOMPUTE',rows=len(rows),cells=len(ids),metrics=metrics,max_absolute_metric_difference=diff,pairedcell_MAE_difference_CI95=ci,prediction_sha256=hashlib.sha256((O/'calibration_predictions.csv').read_bytes()).hexdigest(),per_cell_MAE_improvement=dict(zip(ids,deltas)))
with (O/'independent_metrics.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result))
