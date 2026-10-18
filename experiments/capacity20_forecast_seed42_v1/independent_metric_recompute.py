from pathlib import Path
import csv,json,math,statistics,hashlib,zlib,base64
O=Path('/home/yndx/zxk/rul/experiments/capacity20_forecast_seed42_v1')
mean=statistics.fmean
def main():
 f=O/'calibration_predictions.csv';raw=f.read_bytes();done=json.loads((O/'completion.json').read_text());assert hashlib.sha256(raw).hexdigest()==done['prediction_sha256'];rows=list(csv.DictReader(f.open()));assert len(rows)==done['calibration_pairs'];ids=sorted({r['cell_id'] for r in rows});assert len(ids)==10;co=json.loads((O/'cohort.json').read_text());assert set(ids)=={c for c,v in co['roles'].items() if v=='calibration'}
 for r in rows:assert int(r['target_cycle'])-int(r['forecast_origin'])==20 and int(r['features_visible_through'])==int(r['forecast_origin'])
 pc=[]
 for cid in ids:
  a=[r for r in rows if r['cell_id']==cid]
  for arm,col in [('persistence','persistence_delta_mSOH'),('robust20_extrapolation','robust20_delta_mSOH'),('learned_capacity20','predicted_delta_mSOH')]:
   e=[float(r[col])-float(r['true_delta_mSOH']) for r in a];pc.append({'cell_id':cid,'arm':arm,'MAE_mSOH':mean(abs(x) for x in e),'bias_mSOH':mean(e),'RMSE_mSOH':math.sqrt(mean(x*x for x in e))})
 metrics={arm:{k:mean(x[k] for x in pc if x['arm']==arm) for k in ['MAE_mSOH','bias_mSOH','RMSE_mSOH']} for arm in ['persistence','robust20_extrapolation','learned_capacity20']};old=json.loads((O/'metrics.json').read_text());delta=max(abs(old[a][k]-metrics[a][k]) for a in old for k in old[a]);assert delta<1e-10
 res={'status':'PASS_FROM_ORIGINAL_FORECAST_CSV_NO_MODEL','metrics':metrics,'maximum_metric_delta':delta,'forecasts':len(rows),'cells':10,'one_mSOH_in_Ah':.0011,'no_future_feature_index':True,'new_fits':0}
 (O/'independent_metrics.json').open('x').write(json.dumps(res,indent=2));enc=base64.b64encode(zlib.compress(raw,9)).decode();assert zlib.decompress(base64.b64decode(enc))==raw;(O/'published_predictions.json').open('x').write(json.dumps({'encoding':'zlib9+base64 exact derived calibration forecast CSV, not raw curves','file':'calibration_predictions.csv','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'payload':enc}));print(json.dumps(res));print('ARCHIVE',(O/'published_predictions.json').stat().st_size)
if __name__=='__main__':main()
