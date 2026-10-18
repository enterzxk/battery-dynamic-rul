from pathlib import Path
import csv,json,hashlib,math,statistics,zlib,base64
O=Path('/home/yndx/zxk/rul/experiments/capacity_endpoint_firstpassage_seed42_v2')
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
 cr=list(csv.DictReader((O/'capacity_calibration_predictions.csv').open()));assert len(cr)==4367
 cm={}
 for arm,col in [('persistence','persistence_delta_mSOH'),('robust20','robust20_delta_mSOH'),('old_preEOL_model','predicted_delta_mSOH'),('new_endpoint_model','endpoint_v2_delta_mSOH')]:cm[arm]=statistics.fmean(statistics.fmean(abs(float(r[col])-float(r['true_delta_mSOH'])) for r in cr if r['cell_id']==cid) for cid in ids)
 cc=json.loads((O/'capacity_comparison.json').read_text())['cell_equal_MAE_mSOH'];cd=max(abs(cm[k]-cc[k]) for k in cm);assert cd<1e-10;x.update(capacity_MAE_mSOH=cm,capacity_metric_delta=cd)
 payload=base64.b64encode(zlib.compress(json.dumps([float(r['endpoint_v2_delta_mSOH']) for r in cr],separators=(',',':')).encode(),9)).decode();capraw=(O/'capacity_calibration_predictions.csv').read_bytes();delta={'encoding':'zlib9+base64 JSON float vector appended to exact source CSV','source_archive':'../capacity20_forecast_seed42_v1/published_predictions.json','source_CSV_sha256':'835ef130cfeef6a81e9c6f5860065945260e253550a61f9f626fe71931d4e0c5','column':'endpoint_v2_delta_mSOH','rows':4367,'payload':payload,'restored_file':'capacity_calibration_predictions.csv','restored_bytes':len(capraw),'restored_sha256':hashlib.sha256(capraw).hexdigest()};(O/'capacity_prediction_delta.json').open('x').write(json.dumps(delta))
 (O/'independent_metrics.json').open('x').write(json.dumps(x,indent=2));payload=base64.b64encode(zlib.compress(raw,9)).decode();assert zlib.decompress(base64.b64decode(payload))==raw;(O/'published_predictions.json').open('x').write(json.dumps({'encoding':'zlib9+base64 exact derived calibration RUL forecast CSV','file':'calibration_predictions.csv','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'payload':payload}));print(json.dumps(x));print('ARCHIVE',(O/'published_predictions.json').stat().st_size)
if __name__=='__main__':main()
