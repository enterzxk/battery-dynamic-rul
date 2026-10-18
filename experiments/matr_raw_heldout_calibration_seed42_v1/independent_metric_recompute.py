from pathlib import Path
import json,csv,math,statistics,hashlib,zlib,base64
O=Path('/home/yndx/zxk/rul/experiments/matr_raw_heldout_calibration_seed42_v1')
mean=statistics.fmean
def main():
 co=json.loads((O/'cohort.json').read_text());p=json.loads((O/'fit_parameters.json').read_text());done=json.loads((O/'completion.json').read_text());rows={}
 for role in ['fit','calibration','development']:
  f=O/(role+'_predictions.csv');assert hashlib.sha256(f.read_bytes()).hexdigest()==done['prediction_sha256'][role];rows[role]=list(csv.DictReader(f.open()))
  ids={x['cell_id'] for x in rows[role]};assert ids=={c for c,r in co['roles'].items() if r==role}
  for x in rows[role]:assert int(x['event_cycle'])-int(x['origin'])==int(x['true_RUL'])>0
 sig={}
 for arm,role in [('A_fit_residual_scale','fit'),('B_heldout_cell_scale','calibration')]:
  ids=sorted({x['cell_id'] for x in rows[role]})
  sig[arm]=max(.05,math.sqrt(mean([mean([(math.log(float(x['true_RUL']))-float(x['mu_log_RUL']))**2 for x in rows[role] if x['cell_id']==cid]) for cid in ids])))
  assert abs(sig[arm]-p['sigmas'][arm])<1e-12
 q=statistics.NormalDist().inv_cdf(.9);v=rows['development'];metrics={};per=[]
 for arm,s in sig.items():
  for cid in sorted({x['cell_id'] for x in v}):
   vals=[]
   for x in v:
    if x['cell_id']!=cid:continue
    y=float(x['true_RUL']);mu=float(x['mu_log_RUL']);pred=math.exp(mu);lo=math.exp(mu-s*q);hi=math.exp(mu+s*q);err=pred-y
    br=[(.5*(1+math.erf((math.log(h)-mu)/(s*math.sqrt(2))))-int(y<=h))**2 for h in [100,300]]
    vals.append([abs(err),err,float(err>100),float(lo<=y<=hi),hi-lo,hi-lo+(10*(lo-y) if y<lo else 10*(y-hi) if y>hi else 0),*br])
   keys=['MAE','bias','severe_over100','coverage80','width80','interval_score80','Brier100','Brier300'];per.append({'arm':arm,'cell_id':cid,**{k:mean(a[i] for a in vals) for i,k in enumerate(keys)}})
  metrics[arm]={k:mean(x[k] for x in per if x['arm']==arm) for k in keys}
 saved=json.loads((O/'metrics.json').read_text());delta=max(abs(metrics[a][k]-saved[a][k]) for a in metrics for k in metrics[a]);assert delta<1e-9
 assert metrics['A_fit_residual_scale']['MAE']==metrics['B_heldout_cell_scale']['MAE']
 result={'status':'PASS_FROM_ORIGINAL_CSV_NO_MODEL_NO_FIT','sigmas':sig,'metrics':metrics,'maximum_metric_delta':delta,'origin_counts':{k:len(v) for k,v in rows.items()},'distribution_reconstruction':'mu_log_RUL CSV + fit_parameters sigma uniquely specify every lognormal CDF/quantile; NormalDist/erf independent of runner scipy','new_fits':0,'optimizer_steps':0}
 (O/'independent_metrics.json').open('x').write(json.dumps(result,indent=2))
 archive={'encoding':'zlib9+base64, exact CSV bytes','files':{}}
 for role in rows:
  f=O/(role+'_predictions.csv');raw=f.read_bytes();enc=base64.b64encode(zlib.compress(raw,9)).decode();assert zlib.decompress(base64.b64decode(enc))==raw;archive['files'][f.name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'payload':enc}
 (O/'published_predictions.json').open('x').write(json.dumps(archive))
 print(json.dumps(result));print('ARCHIVE_BYTES',(O/'published_predictions.json').stat().st_size)
if __name__=='__main__':main()
