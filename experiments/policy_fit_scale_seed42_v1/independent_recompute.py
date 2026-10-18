from pathlib import Path
import json,csv,math,statistics,hashlib
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent;p=json.loads((O/'protocol.json').read_text());rows=list(csv.DictReader((O/'fit_predictions.csv').open()));ids=sorted({r['cell_id'] for r in rows});assert len(ids)==42 and len(rows)==22281 and all(r['role']=='fit' for r in rows)
mses=[statistics.mean((float(r['policy_mu_log_RUL'])-math.log(float(r['true_RUL'])))**2 for r in rows if r['cell_id']==cid) for cid in ids];sigma=max(.05,math.sqrt(statistics.mean(mses)));sref=json.loads((O/'fit_scale.json').read_text())['sigma'];assert abs(sigma-sref)<1e-12
source=list(csv.DictReader(Path(p['source_calibration_predictions']).open()));calids=sorted({r['cell_id'] for r in source});assert len(calids)==10 and len(source)==4567 and not set(ids)&set(calids);norm=statistics.NormalDist();met={a:[] for a in p['arms']}
for cid in calids:
 rr=[r for r in source if r['cell_id']==cid]
 for arm,s in zip(p['arms'],[p['old_sigma'],sigma]):
  values=[]
  for r in rr:
   mu=float(r['context_RUL_raw_log']);y=float(r['true_RUL']);med=math.exp(mu);lo=math.exp(mu+s*norm.inv_cdf(.1));hi=math.exp(mu+s*norm.inv_cdf(.9));e=med-y;v=dict(MAE=abs(e),bias=e,severe_over100=e>100,coverage80=lo<=y<=hi,width80=hi-lo,interval_score80=hi-lo+10*max(lo-y,0)+10*max(y-hi,0),lower_miss=y<lo,upper_miss=y>hi)
   for h in [100,300]:risk=.5*math.erfc(-(math.log(h)-mu)/(s*math.sqrt(2)));v[f'Brier{h}']=(risk-(y<=h))**2
   values.append(v)
  met[arm].append({k:statistics.mean(v[k] for v in values) for k in values[0]})
met={a:{k:statistics.mean(v[k] for v in cells) for k in cells[0]} for a,cells in met.items()};ref=json.loads((O/'metrics.json').read_text());dif=max(abs(met[a][k]-ref[a][k]) for a in met for k in met[a]);assert dif<1e-9
out=dict(status='PASS_INDEPENDENT_FIT_RESIDUAL_SCALE_AND_CALIBRATION_METRICS',fit_rows=22281,cal_rows=4567,fit_cells=42,cal_cells=10,recomputed_sigma=sigma,sigma_difference=abs(sigma-sref),maximum_metric_difference=dif,new_fits=0,new_model_inference=0,checkpoint_loads=0,metrics=met,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
with (O/'independent_metrics.json').open('x') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in out.items() if k!='metrics'}))
