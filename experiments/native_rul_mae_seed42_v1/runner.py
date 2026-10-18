from pathlib import Path
import os,time,json,csv,hashlib,datetime,math,sys,pickle,fcntl,signal
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
from collections import Counter
import numpy as np,sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
R=Path('/home/yndx/zxk/rul');O=R/'experiments/native_rul_mae_seed42_v1';B=R/'experiments/matr_raw_heldout_calibration_seed42_v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,x):
 with (O/n).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
def main():
 start=time.monotonic();p=json.loads((O/'protocol.json').read_text());co=json.loads((O/'cohort.json').read_text());go=json.loads((O/'ROOT_GO.json').read_text())
 assert go['status']=='GO_ONE_NATIVE_RUL_MAE_FIT_CAL_ONLY' and go['max_new_fits']==1
 for n in ['runner.py','protocol.json','cohort.json']:assert sha(O/n)==go[n+'_sha256']
 assert sha(O/'cohort.json')==p['source_cohort_sha256']
 assert sha(Path(go['review_path']))==go['review_sha256'] and json.loads(Path(go['review_path']).read_text())['status']=='PASS'
 assert sklearn.__version__=='1.6.1' and np.__version__=='1.26.4' and sys.version_info[:2]==(3,9)
 assert not p['development_access'] and not p['test_access'] and p['max_new_CPU_fits']==1
 with open(R/'automation/state/online_survival_cpu.lock','r+') as lk:
  fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB)
  c=json.loads((R/'automation/state/coordinator.json').read_text());assert c['owner']==c['thread_id']==p['owner'] and c['takeover_verified'] and not c['new_fits_allowed']
  with (O/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
  fits=0
  def timeout(signum,frame):raise TimeoutError('180 second one-shot budget exceeded')
  signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,max(.001,180-(time.monotonic()-start)))
  try:
   records={}
   for role,n in [('fit','fit_predictions.csv'),('calibration','calibration_predictions.csv')]:
    assert sha(B/n)==p['source_predictions'][n];records[role]=list(csv.DictReader((B/n).open()))
   assert [len(records[r]) for r in ['fit','calibration']]==[22281,4567]
   ids={r:{x['cell_id'] for x in rr} for r,rr in records.items()};assert len(ids['fit'])==42 and len(ids['calibration'])==10 and not ids['fit']&ids['calibration']
   features={};meta={}
   for d in co['manifests']:
    mp=Path(d['path']);assert sha(mp)==d['sha256']
    for cc in json.loads(mp.read_text())['cells']:
     cid=cc['cell_id'];role=co['roles'][cid]
     if role not in ['fit','calibration']:continue
     assert cc['role']=='train' and cid in ids[role] and cid not in features
     fp=mp.parent/(cid+'_features.csv');assert sha(fp)==cc['features_sha256'];ff=list(csv.DictReader(fp.open()));assert len(ff)==cc['prefix_count']
     features[cid]={int(x['origin_cycle']):x for x in ff};assert len(features[cid])==len(ff);meta[cid]=cc
   arrays={}
   for role,rr in records.items():
    xx=[];yy=[];counts=Counter(r['cell_id'] for r in rr)
    for r in rr:
     cid=r['cell_id'];t=int(r['origin']);x=features[cid][t];event=meta[cid]['event_cycle']
     assert co['roles'][cid]==r['role']==role and int(x['visible_through_cycle'])==t<event and x['rate20_missing']=='False'
     assert int(r['event_cycle'])==event and int(r['true_RUL'])==event-t and len(features[cid])==counts[cid]
     xx.append([t,float(x['soh']),float(x['rate20_per_cycle'])]);yy.append(event-t)
    X=np.array(xx);Y=np.array(yy,dtype=float);assert np.isfinite(X).all() and np.isfinite(Y).all();arrays[role]=(X,Y)
   W=np.array([1/len(features[r['cell_id']]) for r in records['fit']]);W*=len(W)/W.sum();assert abs(W.mean()-1)<1e-12
   assert time.monotonic()-start<180
   m=HistGradientBoostingRegressor(**p['model']);fits=1
   with (O/'fit_ledger.jsonl').open('x') as f:f.write(json.dumps({'event':'fit_started','number':1,'cells':42,'origins':22281})+'\n');f.flush();os.fsync(f.fileno())
   m.fit(*arrays['fit'],sample_weight=W)
   with (O/'fit_ledger.jsonl').open('a') as f:f.write(json.dumps({'event':'fit_completed','number':1})+'\n')
   cp=O/'checkpoints/native_mae_hgb.pkl';cp.parent.mkdir(exist_ok=False)
   with cp.open('xb') as f:pickle.dump(m,f,protocol=4)
   raw=m.predict(arrays['calibration'][0]);assert np.isfinite(raw).all();pred=np.maximum(0,raw);rr=records['calibration'];y=arrays['calibration'][1];base=np.exp([float(r['mu_log_RUL']) for r in rr]);pc=[]
   with (O/'calibration_predictions.csv').open('x',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rr[0])+['native_RUL_raw','native_RUL_prediction']);w.writeheader();w.writerows(dict(r,native_RUL_raw=float(a),native_RUL_prediction=float(b)) for r,a,b in zip(rr,raw,pred))
   for cid in sorted(ids['calibration']):
    ix=np.array([j for j,r in enumerate(rr) if r['cell_id']==cid])
    for arm,z in [('saved_log_squared',base),('native_absolute',pred)]:
     e=z[ix]-y[ix];pc.append(dict(cell_id=cid,arm=arm,origins=len(ix),MAE=float(abs(e).mean()),bias=float(e.mean()),severe_over100=float((e>100).mean())))
   met={a:{k:float(np.mean([r[k] for r in pc if r['arm']==a])) for k in ['MAE','bias','severe_over100']} for a in ['saved_log_squared','native_absolute']}
   u=np.array([r['MAE'] for r in pc if r['arm']=='saved_log_squared']);v=np.array([r['MAE'] for r in pc if r['arm']=='native_absolute']);ix=np.random.default_rng(42).integers(0,10,(2000,10));ci=np.quantile((u-v)[ix].mean(axis=1),[.025,.975]).tolist()
   cmp=dict(relative_MAE_reduction=1-met['native_absolute']['MAE']/met['saved_log_squared']['MAE'],cells_improved=int((v<u).sum()),pairedcell_MAE_difference_CI95=ci,severe_over100_increment=met['native_absolute']['severe_over100']-met['saved_log_squared']['severe_over100'],negative_raw_outputs=int((raw<0).sum()))
   cmp['gate_pass']=bool(cmp['relative_MAE_reduction']>=.05 and cmp['cells_improved']>=7 and ci[0]>0 and cmp['severe_over100_increment']<=.01)
   dump('per_cell_metrics.json',pc);dump('metrics.json',met);dump('comparison.json',cmp)
   assert time.monotonic()-start<180
   dump('completion.json',dict(status='COMPLETE',new_CPU_predictive_fits=fits,optimizer_steps=0,development_reads=0,test_reads=0,fit_origins=22281,calibration_origins=4567,checkpoint_sha256=sha(cp),prediction_sha256=sha(O/'calibration_predictions.csv'),source_prediction_sha256=p['source_predictions'],runner_sha256=sha(Path(__file__)),protocol_sha256=sha(O/'protocol.json'),GO_sha256=sha(O/'ROOT_GO.json'),elapsed_seconds=time.monotonic()-start,within_budget=time.monotonic()-start<180))
   signal.setitimer(signal.ITIMER_REAL,0)
   print(json.dumps(dict(metrics=met,comparison=cmp)))
  except BaseException as e:
   dump('failure.json',dict(status='FAILED_STOP_NO_RETRY',type=type(e).__name__,error=str(e),fit_starts=fits));raise
if __name__=='__main__':main()
