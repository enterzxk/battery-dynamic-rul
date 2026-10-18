from pathlib import Path
import json,csv,math,statistics,hashlib
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent;p=json.loads((O/'protocol.json').read_text());rows=list(csv.DictReader((O/'calibration_predictions.csv').open()));assert len(rows)==4567 and all(r['role']=='calibration' for r in rows);ids=sorted({r['cell_id'] for r in rows});assert len(ids)==10;norm=statistics.NormalDist();sigma=json.loads((R/'experiments/matr_raw_heldout_calibration_seed42_v1/fit_parameters.json').read_text())['sigmas']['A_fit_residual_scale'];pc=[];cross=[0,0,0,0]
for cid in ids:
 rr=[r for r in rows if r['cell_id']==cid];values={a:[] for a in ['saved_fixed_sigma','direct_conditional_quantiles']}
 for r in rr:
  mu=float(r['context_RUL_raw_log']);med=math.exp(mu);y=float(r['true_RUL']);lo=math.exp(float(r['q10_log_RUL']));hi=math.exp(float(r['q90_log_RUL']));flags=[lo>med,hi<med,lo>=hi];cross=[a+int(b) for a,b in zip(cross,flags+[any(flags)])]
  for arm,l,h in [('saved_fixed_sigma',math.exp(mu+sigma*norm.inv_cdf(.1)),math.exp(mu+sigma*norm.inv_cdf(.9))),('direct_conditional_quantiles',lo,hi)]:values[arm].append(dict(MAE=abs(med-y),coverage80=l<=y<=h,width80=h-l,raw_formula_score_diagnostic_only=h-l+10*max(l-y,0)+10*max(y-h,0),lower_miss=y<l,upper_miss=y>h,bad=l>=h))
 for arm,vv in values.items():
  r=dict(cell_id=cid,arm=arm,**{k:statistics.mean(v[k] for v in vv) for k in vv[0] if k!='bad'});r['interval_score80']=None if any(v['bad'] for v in vv) else r['raw_formula_score_diagnostic_only'];pc.append(r)
met={}
for arm in ['saved_fixed_sigma','direct_conditional_quantiles']:
 vals=[r for r in pc if r['arm']==arm];met[arm]={k:statistics.mean(r[k] for r in vals) for k in ['MAE','coverage80','width80','raw_formula_score_diagnostic_only','lower_miss','upper_miss']};met[arm]['interval_score80']=None if any(r['interval_score80'] is None for r in vals) else statistics.mean(r['interval_score80'] for r in vals);met[arm]['mean_cell_absolute_coverage_error80']=statistics.mean(abs(r['coverage80']-.8) for r in vals)
ref=json.loads((O/'metrics.json').read_text());dif=0.
for a in met:
 for k in met[a]:
  if met[a][k] is None:assert ref[a][k] is None
  else:dif=max(dif,abs(met[a][k]-ref[a][k]))
c=json.loads((O/'comparison.json').read_text());assert cross==[c[k] for k in ['lower_above_median','upper_below_median','lower_ge_upper','any_crossing_origins']] and dif<1e-9
out=dict(status='PASS_ALL4567_INDEPENDENT_RAW_CSV_INTERVAL_METRICS',rows=4567,cells=10,maximum_metric_difference=dif,crossing_counts=cross,metrics=met,new_fits=0,new_model_inference=0)
with (O/'independent_metrics.json').open('x') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in out.items() if k!='metrics'}))
