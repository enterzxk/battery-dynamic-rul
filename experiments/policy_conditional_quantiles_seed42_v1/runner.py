from pathlib import Path
import os,time,json,csv,hashlib,datetime,math,sys,pickle,fcntl,signal
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
from collections import Counter
import numpy as np,sklearn
from scipy.special import ndtri
from sklearn.ensemble import HistGradientBoostingRegressor
R=Path('/home/yndx/zxk/rul');O=R/'experiments/policy_conditional_quantiles_seed42_v1';B=R/'experiments/matr_raw_heldout_calibration_seed42_v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,x):
 with (O/n).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
def main():
 start=time.monotonic();p=json.loads((O/'protocol.json').read_text());co=json.loads((O/'cohort.json').read_text());go=json.loads((O/'ROOT_GO.json').read_text())
 assert go['status']=='GO_TWO_POLICY_CONDITIONAL_QUANTILE_FITS_CAL_ONLY' and go['max_new_fits']==2 and p['max_new_CPU_fits']==2 and p['quantiles']==[.1,.9]
 for n in ['runner.py','protocol.json','cohort.json']:assert sha(O/n)==go[n+'_sha256']
 assert sha(O/'cohort.json')==p['source_cohort_sha256'] and sha(Path(go['review_path']))==go['review_sha256'] and json.loads(Path(go['review_path']).read_text())['status']=='PASS'
 assert sklearn.__version__=='1.6.1' and np.__version__=='1.26.4' and sys.version_info[:2]==(3,9) and not p['development_access'] and not p['test_access']
 fp=B/'fit_parameters.json';assert sha(fp)==p['source_parameters_sha256'];sigma=json.loads(fp.read_text())['sigmas']['A_fit_residual_scale']
 with open(R/'automation/state/online_survival_cpu.lock','r+') as lk:
  fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB);c=json.loads((R/'automation/state/coordinator.json').read_text());assert c['owner']==c['thread_id']==p['owner'] and c['takeover_verified'] and not c['new_fits_allowed']
  with (O/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
  fits=0
  def timeout(signum,frame):raise TimeoutError('180second total budget exceeded')
  signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,max(.001,180-(time.monotonic()-start)))
  try:
   pf=Path(p['policy_features_path']);assert sha(pf)==p['policy_features_sha256'] and sha(Path(p['semantics_path']))==p['semantics_sha256'];policy={r['cell_id']:r for r in json.loads(pf.read_text())};assert len(policy)==52
   records={}
   for role,n in [('fit','fit_predictions.csv'),('calibration','calibration_predictions.csv')]:
    source=Path(p['source_prediction_paths'][n]);assert sha(source)==p['source_predictions'][n];records[role]=list(csv.DictReader(source.open()))
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
     assert policy[cid]['role']==role
     xx.append([t,float(x['soh']),float(x['rate20_per_cycle'])]+[float(policy[cid][k]) for k in ['effective_C_0_20','effective_C_20_40','effective_C_40_60','effective_C_60_80']]);yy.append(event-t)
    X=np.array(xx);Y=np.array(yy,dtype=float);assert np.isfinite(X).all() and np.isfinite(Y).all();arrays[role]=(X,Y)
   W=np.array([1/len(features[r['cell_id']]) for r in records['fit']]);W*=len(W)/W.sum();assert abs(W.mean()-1)<1e-12
   assert time.monotonic()-start<180
   assert np.all(arrays['fit'][1]>0);Y=np.log(arrays['fit'][1]);cp=O/'checkpoints';cp.mkdir(exist_ok=False);pred={};hashes={}
   for number,q in enumerate(p['quantiles'],1):
    model=HistGradientBoostingRegressor(loss='quantile',quantile=q,**p['model_common']);fits+=1
    with (O/'fit_ledger.jsonl').open('x' if number==1 else 'a') as f:f.write(json.dumps(dict(event='fit_started',number=number,quantile=q,cells=42,origins=22281))+'\n');f.flush();os.fsync(f.fileno())
    model.fit(arrays['fit'][0],Y,sample_weight=W)
    with (O/'fit_ledger.jsonl').open('a') as f:f.write(json.dumps(dict(event='fit_completed',number=number,quantile=q))+'\n')
    path=cp/('q10_hgb.pkl' if q==.1 else 'q90_hgb.pkl')
    with path.open('xb') as f:pickle.dump(model,f,protocol=4)
    hashes[path.name]=sha(path);pred[q]=model.predict(arrays['calibration'][0]);assert np.isfinite(pred[q]).all()
   rr=records['calibration'];y=arrays['calibration'][1];mu=np.array([float(r['context_RUL_raw_log']) for r in rr]);med=np.exp(mu);lo=np.exp(pred[.1]);hi=np.exp(pred[.9]);assert np.isfinite(lo).all() and np.isfinite(hi).all() and (lo>0).all() and (hi>0).all();base_lo=np.exp(mu+sigma*ndtri(.1));base_hi=np.exp(mu+sigma*ndtri(.9));cross_low=lo>med;cross_high=hi<med;cross_bounds=lo>=hi;cross=cross_low|cross_high|cross_bounds
   with (O/'calibration_predictions.csv').open('x',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rr[0])+['q10_log_RUL','q90_log_RUL']);w.writeheader();w.writerows(dict(r,q10_log_RUL=float(a),q90_log_RUL=float(b)) for r,a,b in zip(rr,pred[.1],pred[.9]))
   pc=[]
   for cid in sorted(ids['calibration']):
    ix=np.array([i for i,r in enumerate(rr) if r['cell_id']==cid])
    for arm,l,h in [('saved_fixed_sigma',base_lo,base_hi),('direct_conditional_quantiles',lo,hi)]:
     width=h[ix]-l[ix];score=width+10*np.maximum(l[ix]-y[ix],0)+10*np.maximum(y[ix]-h[ix],0);bad=bool((l[ix]>=h[ix]).any());r=dict(cell_id=cid,arm=arm,origins=len(ix),MAE=float(abs(med[ix]-y[ix]).mean()),coverage80=float(((y[ix]>=l[ix])&(y[ix]<=h[ix])).mean()),width80=float(width.mean()),interval_score80=None if bad else float(score.mean()),raw_formula_score_diagnostic_only=float(score.mean()),lower_miss=float((y[ix]<l[ix]).mean()),upper_miss=float((y[ix]>h[ix]).mean()));pc.append(r)
   met={a:{k:float(np.mean([r[k] for r in pc if r['arm']==a])) for k in ['MAE','coverage80','width80','raw_formula_score_diagnostic_only','lower_miss','upper_miss']} for a in ['saved_fixed_sigma','direct_conditional_quantiles']}
   for a in met:
    values=[r['interval_score80'] for r in pc if r['arm']==a];met[a]['interval_score80']=None if any(v is None for v in values) else float(np.mean(values))
   for arm in met:met[arm]['mean_cell_absolute_coverage_error80']=float(np.mean([abs(r['coverage80']-.8) for r in pc if r['arm']==arm]))
   a=met['saved_fixed_sigma'];b=met['direct_conditional_quantiles'];u=np.array([r['raw_formula_score_diagnostic_only'] for r in pc if r['arm']=='saved_fixed_sigma']);v=np.array([r['raw_formula_score_diagnostic_only'] for r in pc if r['arm']=='direct_conditional_quantiles']);bs=np.random.default_rng(42).integers(0,10,(2000,10));ci=np.quantile((u-v)[bs].mean(axis=1),[.025,.975]).tolist();improved=sum(abs(next(r['coverage80'] for r in pc if r['cell_id']==cid and r['arm']=='direct_conditional_quantiles')-.8)<abs(next(r['coverage80'] for r in pc if r['cell_id']==cid and r['arm']=='saved_fixed_sigma')-.8) for cid in ids['calibration'])
   cmp=dict(interval_score_relative_reduction=None if b['interval_score80'] is None else 1-b['interval_score80']/a['interval_score80'],absolute_coverage_error_reduction=abs(a['coverage80']-.8)-abs(b['coverage80']-.8),width_ratio=b['width80']/a['width80'],coverage_error_cells_improved=improved,point_MAE_unchanged=a['MAE']==b['MAE'],lower_above_median=int(cross_low.sum()),upper_below_median=int(cross_high.sum()),lower_ge_upper=int(cross_bounds.sum()),any_crossing_origins=int(cross.sum()),pairedcell_raw_score_difference_CI95=ci,valid_allorigin_interval_score=b['interval_score80'] is not None)
   cmp['mean_cell_absolute_coverage_error_reduction']=a['mean_cell_absolute_coverage_error80']-b['mean_cell_absolute_coverage_error80']
   cmp['gate_pass']=bool(not cross.any() and cmp['point_MAE_unchanged'] and cmp['interval_score_relative_reduction'] is not None and cmp['interval_score_relative_reduction']>=.05 and cmp['mean_cell_absolute_coverage_error_reduction']>=.03 and cmp['absolute_coverage_error_reduction']>=-1e-12 and cmp['width_ratio']<=2 and improved>=7 and ci[0]>0)
   dump('metrics.json',met);dump('per_cell_metrics.json',pc);dump('comparison.json',cmp);assert time.monotonic()-start<180
   dump('completion.json',dict(status='COMPLETE_TWO_QUANTILE_FITS',new_CPU_predictive_fits=fits,optimizer_steps=0,development_reads=0,test_reads=0,new_scalar_estimates=0,checkpoint_loads=0,fit_origins=22281,calibration_origins=4567,checkpoint_sha256=hashes,prediction_sha256=sha(O/'calibration_predictions.csv'),runner_sha256=sha(Path(__file__)),protocol_sha256=sha(O/'protocol.json'),GO_sha256=sha(O/'ROOT_GO.json'),elapsed_seconds=time.monotonic()-start));signal.setitimer(signal.ITIMER_REAL,0);print(json.dumps(dict(metrics=met,comparison=cmp)))
  except BaseException as e:
   dump('failure.json',dict(status='FAILED_STOP_NO_RETRY',type=type(e).__name__,error=str(e),fit_starts=fits));raise
if __name__=='__main__':main()
