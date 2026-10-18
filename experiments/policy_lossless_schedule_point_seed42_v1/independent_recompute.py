from pathlib import Path
import json,csv,math,statistics
import numpy as np
O=Path(__file__).resolve().parent;rr=list(csv.DictReader((O/'calibration_predictions.csv').open()));assert len(rr)==4567;ids=sorted({r['cell_id'] for r in rr});assert len(ids)==10;pc=[]
for cid in ids:
 rows=[r for r in rr if r['cell_id']==cid]
 for arm,key in [('saved_compressed_policy','context_RUL_raw_log'),('lossless_schedule','schedule_RUL_raw_log')]:
  e=[math.exp(float(r[key]))-float(r['true_RUL']) for r in rows];pc.append(dict(cell_id=cid,arm=arm,MAE=statistics.mean(abs(x) for x in e),bias=statistics.mean(e),severe_over100=statistics.mean(x>100 for x in e)))
met={arm:{k:statistics.mean(r[k] for r in pc if r['arm']==arm) for k in ['MAE','bias','severe_over100']} for arm in ['saved_compressed_policy','lossless_schedule']};ref=json.loads((O/'metrics.json').read_text());diff=max(abs(v-ref[a][k]) for a,m in met.items() for k,v in m.items())
u,v=[np.array([r['MAE'] for r in pc if r['arm']==arm]) for arm in ['saved_compressed_policy','lossless_schedule']];ix=np.random.default_rng(42).integers(0,10,(2000,10));ci=np.quantile((u-v)[ix].mean(axis=1),[.025,.975]).tolist();cmp=json.loads((O/'comparison.json').read_text());assert max(abs(a-b) for a,b in zip(ci,cmp['pairedcell_MAE_difference_CI95']))<1e-9 and int((v<u).sum())==cmp['cells_improved'] and diff<1e-9
new=met['lossless_schedule'];old=met['saved_compressed_policy'];passed=bool(1-new['MAE']/old['MAE']>=.05 and (v<u).sum()>=7 and ci[0]>0 and new['severe_over100']-old['severe_over100']<=.01);assert passed==cmp['gate_pass']
out=dict(status='PASS_ALL4567_INDEPENDENT_POINT_METRICS_AND_GATE',rows=4567,cells=10,maximum_metric_difference=diff,pairedCI95=ci,gate_pass=passed,metrics=met,new_fits=0,new_model_inference=0)
with (O/'independent_metrics.json').open('x') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in out.items() if k!='metrics'}))
