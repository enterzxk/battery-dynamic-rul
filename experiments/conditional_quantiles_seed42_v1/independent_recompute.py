from pathlib import Path
import csv,json,math,statistics,hashlib
O=Path(__file__).resolve().parent;B=O.parent/'matr_raw_heldout_calibration_seed42_v1';s=json.loads((B/'fit_parameters.json').read_text())['sigmas']['A_fit_residual_scale'];rows=list(csv.DictReader((O/'calibration_predictions.csv').open()));assert len(rows)==4567;ids=sorted({r['cell_id'] for r in rows});assert len(ids)==10;nd=statistics.NormalDist();pc=[];cross=[0,0,0,0]
for cid in ids:
 rr=[r for r in rows if r['cell_id']==cid];vals={a:[] for a in ['saved_fixed_sigma','direct_conditional_quantiles']}
 for r in rr:
  y=float(r['true_RUL']);mu=float(r['mu_log_RUL']);m=math.exp(mu);lo=math.exp(float(r['q10_log_RUL']));hi=math.exp(float(r['q90_log_RUL']));bo=lo>=hi;cross[0]+=lo>m;cross[1]+=hi<m;cross[2]+=bo;cross[3]+=lo>m or hi<m or bo
  for a,l,h in [('saved_fixed_sigma',math.exp(mu+s*nd.inv_cdf(.1)),math.exp(mu+s*nd.inv_cdf(.9))),('direct_conditional_quantiles',lo,hi)]:vals[a].append(dict(MAE=abs(m-y),coverage80=float(l<=y<=h),width80=h-l,raw_formula_score_diagnostic_only=h-l+10*max(l-y,0)+10*max(y-h,0),lower_miss=float(y<l),upper_miss=float(y>h),bad=l>=h))
 for a,v in vals.items():
  z={k:statistics.mean(x[k] for x in v) for k in ['MAE','coverage80','width80','raw_formula_score_diagnostic_only','lower_miss','upper_miss']};z['interval_score80']=None if any(x['bad'] for x in v) else z['raw_formula_score_diagnostic_only'];pc.append(dict(cell_id=cid,arm=a,**z))
met={a:{k:statistics.mean(x[k] for x in pc if x['arm']==a) for k in ['MAE','coverage80','width80','raw_formula_score_diagnostic_only','lower_miss','upper_miss']} for a in vals}
for a in met:
 v=[x['interval_score80'] for x in pc if x['arm']==a];met[a]['interval_score80']=None if any(x is None for x in v) else statistics.mean(v)
ref=json.loads((O/'metrics.json').read_text());diff=0.
for a in ref:
 for k,v in ref[a].items():
  if v is None:assert met[a][k] is None
  else:diff=max(diff,abs(v-met[a][k]))
assert diff<1e-9;cmp=json.loads((O/'comparison.json').read_text());assert cross==[cmp[k] for k in ['lower_above_median','upper_below_median','lower_ge_upper','any_crossing_origins']]
out=dict(status='PASS_INDEPENDENT_CSV_RECOMPUTE',metrics=met,max_absolute_metric_difference=diff,crossing_counts=cross,prediction_sha256=hashlib.sha256((O/'calibration_predictions.csv').read_bytes()).hexdigest())
with (O/'independent_metrics.json').open('x') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(out))
