from pathlib import Path
import os,time,json,csv,hashlib,datetime,pickle,sys
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
import numpy as np,sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
R=Path('/home/yndx/zxk/rul');O=R/'experiments/capacity20_forecast_seed42_v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,v):
 with (O/n).open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def main():
 start=time.monotonic();p=json.loads((O/'protocol.json').read_text());co=json.loads((O/'cohort.json').read_text());go=json.loads((O/'ROOT_GO.json').read_text())
 assert go['status']=='GO_ONE_AUX_CAPACITY_CPU_FIT_CAL_ONLY'
 for n in ['runner.py','protocol.json','cohort.json']:assert sha(O/n)==go[n+'_sha256']
 with (O/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
 fits=0
 try:
  rows=[]
  for d in co['manifests']:
   mp=Path(d['path']);assert sha(mp)==d['sha256'];D=mp.parent
   for c in json.loads(mp.read_text())['cells']:
    cid=c['cell_id'];role=co['roles'][cid]
    if role=='development':continue
    assert role in ['fit','calibration'] and c['role']=='train'
    fp=D/(cid+'_features.csv');assert sha(fp)==c['features_sha256'];ft={int(x['origin_cycle']):x for x in csv.DictReader(fp.open())};rr=[]
    for s,x in sorted(ft.items()):
     t=s+20
     if t not in ft:continue
     z=ft[t];assert int(x['visible_through_cycle'])==s and int(z['visible_through_cycle'])==t and x['rate20_missing']=='False' and t<c['event_cycle']
     rr.append({'cell_id':cid,'role':role,'forecast_origin':s,'target_cycle':t,'features_visible_through':s,'x':[s,float(x['soh']),float(x['rate20_per_cycle'])*1000],'true_delta_mSOH':(float(z['soh'])-float(x['soh']))*1000,'slope_delta_mSOH':20*float(x['rate20_per_cycle'])*1000})
    assert len(rr)>0
    for x in rr:x['weight']=1/len(rr)
    rows.extend(rr)
  tr=[r for r in rows if r['role']=='fit'];ca=[r for r in rows if r['role']=='calibration'];assert len({r['cell_id'] for r in tr})==42 and len({r['cell_id'] for r in ca})==10;assert not {r['cell_id'] for r in tr}&{r['cell_id'] for r in ca}
  X=np.array([r['x'] for r in tr]);y=np.array([r['true_delta_mSOH'] for r in tr]);C=np.array([r['x'] for r in ca]);W=np.array([r['weight'] for r in tr]);W*=len(W)/W.sum();assert all(np.isfinite(z).all() for z in [X,y,C,W]) and time.monotonic()-start<180
  m=HistGradientBoostingRegressor(**p['model']);fits=1
  with (O/'fit_ledger.jsonl').open('a') as f:f.write(json.dumps({'event':'fit_started','number':1,'rows':len(tr),'role':'auxiliary_capacity_forecast'})+'\n');f.flush();os.fsync(f.fileno())
  m.fit(X,y,sample_weight=W)
  with (O/'fit_ledger.jsonl').open('a') as f:f.write(json.dumps({'event':'fit_completed','number':1})+'\n')
  cp=O/'checkpoints';cp.mkdir(exist_ok=False)
  with (cp/'auxiliary_hgb.pkl').open('xb') as f:pickle.dump(m,f,protocol=4)
  out=m.predict(C);assert np.isfinite(out).all() and time.monotonic()-start<180
  predictions=[];pc=[]
  for r,a in zip(ca,out):
   truth=r['true_delta_mSOH'];predictions.append({'cell_id':r['cell_id'],'forecast_origin':r['forecast_origin'],'target_cycle':r['target_cycle'],'features_visible_through':r['forecast_origin'],'true_delta_mSOH':truth,'predicted_delta_mSOH':float(a),'persistence_delta_mSOH':0.,'robust20_delta_mSOH':r['slope_delta_mSOH']})
  with (O/'calibration_predictions.csv').open('x',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(predictions[0]));w.writeheader();w.writerows(predictions)
  for cid in sorted({r['cell_id'] for r in ca}):
   q=[r for r in predictions if r['cell_id']==cid]
   for arm,col in [('persistence','persistence_delta_mSOH'),('robust20_extrapolation','robust20_delta_mSOH'),('learned_capacity20','predicted_delta_mSOH')]:
    err=np.array([r[col]-r['true_delta_mSOH'] for r in q]);pc.append({'cell_id':cid,'arm':arm,'origins':len(q),'MAE_mSOH':float(abs(err).mean()),'bias_mSOH':float(err.mean()),'RMSE_mSOH':float(np.sqrt((err**2).mean()))})
  metrics={a:{k:float(np.mean([r[k] for r in pc if r['arm']==a])) for k in ['MAE_mSOH','bias_mSOH','RMSE_mSOH']} for a in ['persistence','robust20_extrapolation','learned_capacity20']};best=min(['persistence','robust20_extrapolation'],key=lambda a:metrics[a]['MAE_mSOH']);gain={a:1-metrics['learned_capacity20']['MAE_mSOH']/metrics[a]['MAE_mSOH'] for a in ['persistence','robust20_extrapolation']};improve=sum(next(r['MAE_mSOH'] for r in pc if r['cell_id']==cid and r['arm']=='learned_capacity20')<next(r['MAE_mSOH'] for r in pc if r['cell_id']==cid and r['arm']==best) for cid in {r['cell_id'] for r in ca})
  decision={'best_simple_baseline':best,'relative_MAE_reduction':gain,'cells_improved_vs_best_simple':int(improve),'capability_gate_passed':bool(min(gain.values())>=.05 and improve>=6),'not_RUL_gain_or_novelty_evidence':True}
  dump('metrics.json',metrics);dump('per_cell_metrics.json',pc);dump('comparison.json',decision)
  dump('completion.json',{'status':'COMPLETE_ONE_AUX_CAPACITY_FIT_CAL_ONLY','new_CPU_predictive_fits':fits,'optimizer_steps':0,'fit_cells':42,'calibration_cells':10,'fit_pairs':len(tr),'calibration_pairs':len(ca),'development_or_test_reads':0,'runner_sha256':sha(Path(__file__)),'protocol_sha256':sha(O/'protocol.json'),'cohort_sha256':sha(O/'cohort.json'),'GO_sha256':sha(O/'ROOT_GO.json'),'prediction_sha256':sha(O/'calibration_predictions.csv'),'checkpoint_sha256':sha(cp/'auxiliary_hgb.pkl'),'checkpoint_scope':'self-trained trusted auxiliary estimator saved only; no model deserialization or old RUL refit','versions':{'python':sys.version,'numpy':np.__version__,'sklearn':sklearn.__version__},'elapsed_seconds':time.monotonic()-start})
  print(json.dumps({'metrics':metrics,'comparison':decision,'fits':1}))
 except BaseException as e:
  dump('failure.json',{'error':str(e),'type':type(e).__name__,'fit_starts':fits,'status':'STOP_NO_AUTO_RETRY'});raise
if __name__=='__main__':main()
