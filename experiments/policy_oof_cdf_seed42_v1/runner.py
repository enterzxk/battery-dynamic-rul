from pathlib import Path
import os,time,json,csv,hashlib,datetime,math,sys,pickle,fcntl,signal
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
from collections import Counter
import numpy as np,sklearn
from scipy.special import ndtri
from sklearn.ensemble import HistGradientBoostingRegressor
R=Path('/home/yndx/zxk/rul');O=R/'experiments/policy_oof_cdf_seed42_v1';B=R/'experiments/matr_raw_heldout_calibration_seed42_v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,x):
 with (O/n).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
def main():
 start=time.monotonic();p=json.loads((O/'protocol.json').read_text());co=json.loads((O/'cohort.json').read_text());go=json.loads((O/'ROOT_GO.json').read_text())
 assert go['status']=='GO_THREE_CELL_OOF_FITS_CAL_SAVED_ONLY' and go['max_new_fits']==3 and p['max_new_CPU_fits']==3 and p['quantiles']==[.1,.5,.9]
 for n in ['runner.py','protocol.json','cohort.json']:assert sha(O/n)==go[n+'_sha256']
 assert sha(O/'cohort.json')==p['source_cohort_sha256'] and sha(Path(go['review_path']))==go['review_sha256'] and json.loads(Path(go['review_path']).read_text())['status']=='PASS'
 assert sklearn.__version__=='1.6.1' and np.__version__=='1.26.4' and sys.version_info[:2]==(3,9) and not p['development_access'] and not p['test_access']
 fp=B/'fit_parameters.json';assert sha(fp)==p['source_parameters_sha256'];sigma=json.loads(fp.read_text())['sigmas']['A_fit_residual_scale']
 with open(R/'automation/state/online_survival_cpu.lock','r+') as lk:
  fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB);c=json.loads((R/'automation/state/coordinator.json').read_text());assert c['owner']==c['thread_id']==p['owner'] and c['takeover_verified'] and not c['new_fits_allowed']
  with (O/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
  fits=0
  def timeout(signum,frame):raise TimeoutError('240second total budget exceeded')
  signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,max(.001,240-(time.monotonic()-start)))
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
     if role != 'fit':continue
     assert cc['role']=='train' and cid in ids[role] and cid not in features
     fp=mp.parent/(cid+'_features.csv');assert sha(fp)==cc['features_sha256'];ff=list(csv.DictReader(fp.open()));assert len(ff)==cc['prefix_count']
     features[cid]={int(x['origin_cycle']):x for x in ff};assert len(features[cid])==len(ff);meta[cid]=cc
   arrays={}
   for role,rr in records.items():
    if role!='fit':continue
    xx=[];yy=[];counts=Counter(r['cell_id'] for r in rr)
    for r in rr:
     cid=r['cell_id'];t=int(r['origin']);x=features[cid][t];event=meta[cid]['event_cycle']
     assert co['roles'][cid]==r['role']==role and int(x['visible_through_cycle'])==t<event and x['rate20_missing']=='False'
     assert int(r['event_cycle'])==event and int(r['true_RUL'])==event-t and len(features[cid])==counts[cid]
     assert policy[cid]['role']==role
     xx.append([t,float(x['soh']),float(x['rate20_per_cycle'])]+[float(policy[cid][k]) for k in ['effective_C_0_20','effective_C_20_40','effective_C_40_60','effective_C_60_80']]);yy.append(event-t)
    X=np.array(xx);Y=np.array(yy,dtype=float);assert np.isfinite(X).all() and np.isfinite(Y).all();arrays[role]=(X,Y)

   fitrr=records['fit'];allids=sorted(ids['fit']);shuffled=np.random.default_rng(42).permutation(allids).tolist();folds=[shuffled[i:i+14] for i in range(0,42,14)];assert folds==p['fold_cells']
   cell=np.array([r['cell_id'] for r in fitrr]);oof=np.full(len(cell),np.nan);assignment=np.full(len(cell),-1,dtype=int);X,Y=arrays['fit'];logY=np.log(Y)
   cp=O/'checkpoints';cp.mkdir(exist_ok=False);hashes={}
   for number,held in enumerate(folds):
    test=np.isin(cell,held);train=~test;assert len(set(cell[train]))==28 and len(set(cell[test]))==14 and not set(cell[train])&set(cell[test])
    counts=Counter(cell[train]);W=np.array([1/counts[c] for c in cell[train]]);W*=len(W)/W.sum();assert abs(W.mean()-1)<1e-12
    fits+=1
    with (O/'fit_ledger.jsonl').open('x' if number==0 else 'a') as f:f.write(json.dumps(dict(event='fit_started',number=number,train_cells=sorted(counts),held_cells=held,train_origins=int(train.sum()),held_origins=int(test.sum())))+'\n');f.flush();os.fsync(f.fileno())
    model=HistGradientBoostingRegressor(loss='squared_error',**p['model_common']);model.fit(X[train],logY[train],sample_weight=W)
    with (O/'fit_ledger.jsonl').open('a') as f:f.write(json.dumps(dict(event='fit_completed',number=number))+'\n')
    path=cp/('fold'+str(number)+'.pkl')
    with path.open('xb') as f:pickle.dump(model,f,protocol=4)
    hashes[path.name]=sha(path);assert np.isnan(oof[test]).all();oof[test]=model.predict(X[test]);assignment[test]=number
   assert np.isfinite(oof).all() and (assignment>=0).all()
   with (O/'oof_predictions.csv').open('x',newline='') as f:
    w=csv.writer(f);w.writerow(['cell_id','origin','true_RUL','fold','oof_mu_log_RUL'])
    for r,fold,mu in zip(fitrr,assignment,oof):w.writerow([r['cell_id'],r['origin'],r['true_RUL'],int(fold),float(mu)])
   from fractions import Fraction
   residual=logY-oof;order=np.argsort(residual,kind='stable');ordered=residual[order];counts=Counter(cell);weights=np.array([1/(42*counts[c]) for c in cell[order]])
   acc=Fraction();qval={};targets=[Fraction(1,10),Fraction(1,2),Fraction(9,10)]
   for j in order:
    acc+=Fraction(1,42*counts[cell[j]])
    for q in targets:
     if q not in qval and acc>=q:qval[q]=float(residual[j])
   assert acc==1 and len(qval)==3
   center=qval[Fraction(1,2)];offsets=np.array([qval[q]-center for q in targets]);assert offsets[0]<offsets[1]==0<offsets[2]
   support=ordered-center;cdf=np.cumsum(weights);assert abs(cdf[-1]-1)<1e-12;cdf[-1]=1.
   dump('empirical_cdf.json',dict(convention=p['cdf_convention'],median_center=center,quantile_offsets=offsets.tolist(),support=support.tolist(),mass=weights.tolist(),fit_cells=42,OOF_rows=len(cell)))
   rr=records['calibration'];mu=np.array([float(r['context_RUL_raw_log']) for r in rr]);y=np.array([float(r['true_RUL']) for r in rr]);med=np.exp(mu);base_lo=np.exp(mu+sigma*ndtri(.1));base_hi=np.exp(mu+sigma*ndtri(.9));lo=np.exp(mu+offsets[0]);hi=np.exp(mu+offsets[2])
   assert np.isfinite(lo).all() and np.isfinite(hi).all() and (0<lo).all() and (lo<med).all() and (med<hi).all()
   def risk(h):
    ix=np.searchsorted(support,np.log(h)-mu,side='right');return np.where(ix>0,cdf[np.maximum(ix-1,0)],0.)
   from scipy.special import ndtr
   risks={h:risk(h) for h in [100,300]};base_risks={h:ndtr((np.log(h)-mu)/sigma) for h in [100,300]}
   with (O/'calibration_distribution.csv').open('x',newline='') as f:
    w=csv.writer(f);w.writerow(['cell_id','origin','true_RUL','saved_mu','q10','q50','q90','risk100','risk300'])
    for i,r in enumerate(rr):w.writerow([r['cell_id'],r['origin'],r['true_RUL'],float(mu[i]),float(lo[i]),float(med[i]),float(hi[i]),float(risks[100][i]),float(risks[300][i])])
   pc=[]
   for cid in sorted(ids['calibration']):
    ix=np.array([i for i,r in enumerate(rr) if r['cell_id']==cid])
    for arm,l,h,rs in [('saved_fixed_sigma',base_lo,base_hi,base_risks),('cell_OOF_empirical_CDF',lo,hi,risks)]:
     width=h[ix]-l[ix];score=width+10*np.maximum(l[ix]-y[ix],0)+10*np.maximum(y[ix]-h[ix],0)
     rec=dict(cell_id=cid,arm=arm,origins=len(ix),MAE=float(abs(med[ix]-y[ix]).mean()),coverage80=float(((y[ix]>=l[ix])&(y[ix]<=h[ix])).mean()),width80=float(width.mean()),interval_score80=float(score.mean()),Brier100=float(((rs[100][ix]-(y[ix]<=100))**2).mean()),Brier300=float(((rs[300][ix]-(y[ix]<=300))**2).mean()))
     rec['absolute_coverage_error80']=abs(rec['coverage80']-.8);pc.append(rec)
   arms=['saved_fixed_sigma','cell_OOF_empirical_CDF'];keys=[k for k in pc[0] if k not in ['cell_id','arm','origins']]
   met={arm:{k:float(np.mean([r[k] for r in pc if r['arm']==arm])) for k in keys} for arm in arms}
   a,b=[met[x] for x in arms];u,v=[np.array([r['interval_score80'] for r in pc if r['arm']==arm]) for arm in arms];bs=np.random.default_rng(42).integers(0,10,(2000,10));ci=np.quantile((u-v)[bs].mean(axis=1),[.025,.975]).tolist()
   improved=sum(next(r['absolute_coverage_error80'] for r in pc if r['cell_id']==cid and r['arm']==arms[1])<next(r['absolute_coverage_error80'] for r in pc if r['cell_id']==cid and r['arm']==arms[0]) for cid in ids['calibration'])
   cmp=dict(point_MAE_unchanged=a['MAE']==b['MAE'],interval_score_relative_reduction=1-b['interval_score80']/a['interval_score80'],pairedcell_score_difference_CI95=ci,mean_cell_absolute_coverage_error_reduction=a['absolute_coverage_error80']-b['absolute_coverage_error80'],aggregate_coverage_error_reduction=abs(a['coverage80']-.8)-abs(b['coverage80']-.8),coverage_error_cells_improved=improved,width_ratio=b['width80']/a['width80'],mean_Brier_increment=(b['Brier100']+b['Brier300']-a['Brier100']-a['Brier300'])/2,any_crossing_origins=0)
   checks=dict(point=cmp['point_MAE_unchanged'],score=cmp['interval_score_relative_reduction']>=.05,CI=ci[0]>0,cell_coverage=cmp['mean_cell_absolute_coverage_error_reduction']>=.03,aggregate=cmp['aggregate_coverage_error_reduction']>=-1e-12,cells=improved>=7,width=cmp['width_ratio']<=2,Brier=cmp['mean_Brier_increment']<=.002,coherence=True);cmp.update(checks=checks,gate_pass=all(checks.values()))
   dump('metrics.json',met);dump('per_cell_metrics.json',pc);dump('comparison.json',cmp)
   dump('completion.json',dict(status='COMPLETE_THREE_CELL_ISOLATED_OOF_FITS',new_CPU_predictive_fits=fits,optimizer_steps=0,development_reads=0,test_reads=0,new_calibration_predict_calls=0,checkpoint_loads=0,OOF_cells=42,OOF_origins=22281,calibration_origins=4567,checkpoint_sha256=hashes,oof_prediction_sha256=sha(O/'oof_predictions.csv'),distribution_prediction_sha256=sha(O/'calibration_distribution.csv'),runner_sha256=sha(Path(__file__)),protocol_sha256=sha(O/'protocol.json'),GO_sha256=sha(O/'ROOT_GO.json'),elapsed_seconds=time.monotonic()-start))
   signal.setitimer(signal.ITIMER_REAL,0);print(json.dumps(dict(metrics=met,comparison=cmp)))
  except BaseException as e:
   dump('failure.json',dict(status='FAILED_STOP_NO_RETRY',type=type(e).__name__,error=str(e),fit_starts=fits));raise
if __name__=='__main__':main()
