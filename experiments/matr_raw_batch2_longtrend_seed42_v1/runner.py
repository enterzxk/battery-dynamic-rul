from pathlib import Path
import os,time,json,csv,hashlib,datetime
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
from scipy.special import ndtr,ndtri
R=Path('/home/yndx/zxk/rul');O=R/'experiments/matr_raw_batch2_longtrend_seed42_v1';D=R/'data/processed/data_v1_matr_raw_batch2'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(name,x):
 with (O/name).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
def main():
 start=time.monotonic();p=json.loads((O/'protocol.json').read_text());go=json.loads((O/'ROOT_GO.json').read_text())
 assert go['status']=='GO_THREE_CPU_FITS_ONLY' and go['runner_sha256']==sha(Path(__file__)) and go['protocol_sha256']==sha(O/'protocol.json')
 assert go['manifest_sha256']==sha(D/'manifest.json')==p['manifest_sha256']
 with (O/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
 fits=0
 try:
  manifest=json.loads((D/'manifest.json').read_text());rows=[]
  for c in manifest['cells']:
   cid=c['cell_id'];assert c['role'] in ['train','val'] and c['event_cycle'] is not None
   fp=D/(cid+'_features.csv');assert sha(fp)==c['features_sha256']
   rr=list(csv.DictReader(fp.open()));assert len(rr)==c['prefix_count']
   for r in rr:
    t=int(r['origin_cycle']);assert int(r['visible_through_cycle'])==t and t<c['event_cycle'] and r['rate20_missing']=='False' and r['rate100_missing']=='False'
    rows.append({'cell':cid,'role':c['role'],'origin':t,'T':c['event_cycle'],'x':[t,float(r['soh']),float(r['rate20_per_cycle']),float(r['rate100_per_cycle'])],'weight':1/len(rr)})
  tr=[r for r in rows if r['role']=='train'];va=[r for r in rows if r['role']=='val'];assert len(tr)==9445 and len(va)==3586
  assert len({r['cell'] for r in tr})==26 and len({r['cell'] for r in va})==9 and not {r['cell'] for r in tr}&{r['cell'] for r in va}
  X=np.array([r['x'] for r in tr]);V=np.array([r['x'] for r in va]);Y=np.log([r['T']-r['origin'] for r in tr]);truth=np.array([r['T']-r['origin'] for r in va],float)
  W=np.array([r['weight'] for r in tr]);W*=len(W)/W.sum()
  assert np.isfinite(X).all() and np.isfinite(V).all() and np.isfinite(Y).all()
  predictions=[];pc=[];params={}
  for arm in ['A_robust_linear','B_robust_nonlinear','C_add_long_rate']:
   assert fits<3 and time.monotonic()-start<180;fits+=1
   with (O/'fit_ledger.jsonl').open('a') as f:f.write(json.dumps({'event':'fit_started','number':fits,'arm':arm})+'\n');f.flush();os.fsync(f.fileno())
   cols=[0,1,2] if arm!='C_add_long_rate' else [0,1,2,3]
   xx=X[:,cols];vv=V[:,cols]
   if arm=='A_robust_linear':
    sc=StandardScaler().fit(xx,sample_weight=W);xx=sc.transform(xx);vv=sc.transform(vv);m=Ridge(alpha=1.)
   else:m=HistGradientBoostingRegressor(max_iter=150,max_leaf_nodes=7,max_depth=3,learning_rate=.05,min_samples_leaf=50,l2_regularization=1.,early_stopping=False,random_state=42)
   m.fit(xx,Y,sample_weight=W);mu=m.predict(vv);res=Y-m.predict(xx);sigma=max(.05,float(np.sqrt(np.average(res**2,weights=W))))
   assert time.monotonic()-start<180
   qs=[np.exp(mu+sigma*ndtri(q)) for q in [.1,.5,.9]];risk=[ndtr((np.log(h)-mu)/sigma) for h in [100,300]];assert all(np.isfinite(v).all() for v in qs+risk)
   params[arm]={'sigma_train_only':sigma,'columns':cols,'params':m.get_params(),'scaler_mean':sc.mean_.tolist() if arm=='A_robust_linear' else None}
   with (O/'fit_ledger.jsonl').open('a') as f:f.write(json.dumps({'event':'fit_completed','number':fits,'arm':arm})+'\n')
   for cid in sorted({r['cell'] for r in va}):
    ix=np.array([i for i,r in enumerate(va) if r['cell']==cid]);err=qs[1][ix]-truth[ix]
    pc.append({'cell_id':cid,'arm':arm,'MAE':float(abs(err).mean()),'bias':float(err.mean()),'severe_over100':float((err>100).mean()),'coverage80':float(((truth[ix]>=qs[0][ix])&(truth[ix]<=qs[2][ix])).mean()),'width80':float((qs[2][ix]-qs[0][ix]).mean()),'Brier100':float(((risk[0][ix]-(truth[ix]<=100))**2).mean()),'Brier300':float(((risk[1][ix]-(truth[ix]<=300))**2).mean())})
    for i in ix:predictions.append({'cell_id':cid,'origin':va[i]['origin'],'event_cycle':va[i]['T'],'true_RUL':truth[i],'arm':arm,'q10':qs[0][i],'median_RUL':qs[1][i],'q90':qs[2][i],'risk100':risk[0][i],'risk300':risk[1][i]})
  with (O/'development_predictions.csv').open('x',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(predictions[0]));w.writeheader();w.writerows(predictions)
  metrics={a:{k:float(np.mean([r[k] for r in pc if r['arm']==a])) for k in pc[0] if k not in ['cell_id','arm']} for a in params}
  boot=np.random.default_rng(42).integers(0,9,(2000,9));comparisons=[]
  for base,new in [('A_robust_linear','B_robust_nonlinear'),('B_robust_nonlinear','C_add_long_rate')]:
   ids=sorted({r['cell_id'] for r in pc});a=np.array([next(r['MAE'] for r in pc if r['arm']==base and r['cell_id']==c) for c in ids]);b=np.array([next(r['MAE'] for r in pc if r['arm']==new and r['cell_id']==c) for c in ids]);gain=float(1-b.mean()/a.mean());ci=np.quantile(1-b[boot].mean(1)/a[boot].mean(1),[.025,.975]);harm=metrics[new]['severe_over100']-metrics[base]['severe_over100'];cal=metrics[new]['coverage80']-metrics[base]['coverage80']
   comparisons.append({'base':base,'new':new,'relative_Time_MAE_reduction':gain,'paired_cell_bootstrap95':ci.tolist(),'improved_cells':int((b<a).sum()),'severe_over100_increase':harm,'coverage80_change':cal,'development_gate':bool(gain>=.05 and ci[0]>0 and (b<a).sum()>=6 and harm<=.01 and cal>=-.02)})
  dump('metrics.json',metrics);dump('per_cell_metrics.json',pc);dump('comparisons.json',comparisons);dump('fit_parameters.json',params)
  dump('completion.json',{'status':'COMPLETE_RAW_BATCH2_DEVELOPMENT_COMPARISON','new_CPU_predictive_fits':fits,'optimizer_steps':0,'train_cells':26,'development_cells':9,'train_origins':9445,'development_origins':3586,'test_cell_reads':0,'runner_sha256':sha(Path(__file__)),'protocol_sha256':sha(O/'protocol.json'),'GO_sha256':sha(O/'ROOT_GO.json'),'manifest_sha256':sha(D/'manifest.json'),'prediction_sha256':sha(O/'development_predictions.csv'),'elapsed_seconds':time.monotonic()-start})
  print(json.dumps({'status':'COMPLETE','metrics':metrics,'comparisons':comparisons,'fits':fits}))
 except BaseException as e:
  dump('failure.json',{'status':'FAILED_STOP_NO_AUTO_RETRY','error':str(e),'type':type(e).__name__,'fit_starts':fits});raise
if __name__=='__main__':main()
