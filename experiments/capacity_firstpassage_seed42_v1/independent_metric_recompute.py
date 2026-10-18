from pathlib import Path
import csv,json,hashlib,math,statistics,zlib,base64
O=Path('/home/yndx/zxk/rul/experiments/capacity_firstpassage_seed42_v1')
def main():
 f=O/'calibration_predictions.csv';raw=f.read_bytes();d=json.loads((O/'completion.json').read_text());assert hashlib.sha256(raw).hexdigest()==d['prediction_sha256'];rr=list(csv.DictReader(f.open()));assert len(rr)==4567
 co=json.loads((O/'cohort.json').read_text());ids=sorted({r['cell_id'] for r in rr});assert set(ids)=={c for c,x in co['roles'].items() if x=='calibration'};pc=[]
 for cid in ids:
  rows=[r for r in rr if r['cell_id']==cid]
  for arm,col in [('direct_RUL_saved','direct_RUL_prediction'),('capacity_firstpassage','noncross_lower_bound_cap_for_diagnostic')]:
   e=[float(r[col])-float(r['true_RUL']) for r in rows];pc.append({'cell_id':cid,'arm':arm,'MAE':statistics.fmean(abs(x) for x in e),'bias':statistics.fmean(e),'severe_over100':statistics.fmean(float(x>100) for x in e)})
  for r in rows:
   if r['rollout_status']=='CROSSED':assert abs(float(r['rollout_RUL_prediction'])-float(r['noncross_lower_bound_cap_for_diagnostic']))<1e-12
   else:assert r['rollout_RUL_prediction']=='' and float(r['noncross_lower_bound_cap_for_diagnostic'])==2000
 saved=json.loads((O/'metrics.json').read_text());m={a:{k:statistics.fmean(r[k] for r in pc if r['arm']==a) for k in ['MAE','bias','severe_over100']} for a in saved};delta=max(abs(saved[a][k]-m[a][k]) for a in saved for k in saved[a]);assert delta<1e-9
 x={'status':'PASS_ORIGINAL_CSV_METRIC_RECOMPUTATION_NO_MODEL','metrics':m,'maximum_delta':delta,'noncross_or_invalid':sum(r['rollout_status']!='CROSSED' for r in rr),'all_origins_retained':True,'new_fits':0,'new_forwards':0,'warning':'Noncross lowerbound cap is diagnostic only, any noncross fails gate'}
 (O/'independent_metrics.json').open('x').write(json.dumps(x,indent=2));payload=base64.b64encode(zlib.compress(raw,9)).decode();assert zlib.decompress(base64.b64decode(payload))==raw;(O/'published_predictions.json').open('x').write(json.dumps({'encoding':'zlib9+base64 exact derived calibration RUL forecast CSV','file':'calibration_predictions.csv','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'payload':payload}));print(json.dumps(x));print('ARCHIVE',(O/'published_predictions.json').stat().st_size)
if __name__=='__main__':main()
