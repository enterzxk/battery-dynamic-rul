from pathlib import Path
import os,json,csv,hashlib,datetime,time,fcntl,signal,pickle,sys,zlib,base64
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
from collections import Counter
import numpy as np,sklearn
from scipy.special import ndtr,ndtri
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,x):
 with (O/n).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
def main():
 start=time.monotonic();p=json.loads((O/'protocol.json').read_text());co=json.loads((O/'cohort.json').read_text());mp=json.loads((O/'point_model_protocol.json').read_text());g=json.loads((O/'ROOT_GO.json').read_text())
 assert g['status']=='GO_ONE_POLICY_FIT_ONLY_INFERENCE_AND_SCALE' and g['max_new_fits']==0 and g['max_predict_calls']==1 and g['max_checkpoint_loads']==1 and g['max_new_scalar_estimates']==1
 for n in ['runner.py','protocol.json','cohort.json','point_model_protocol.json']:assert sha(O/n)==g['reviewed_hashes'][str((O/n).relative_to(R))]
 assert sha(Path(g['review_path']))==g['review_sha256'];rv=json.loads(Path(g['review_path']).read_text());assert rv['status']=='PASS' and rv['reviewed_hashes']==g['reviewed_hashes']
 assert sha(O/'cohort.json')==p['cohort_sha256'] and sha(O/'point_model_protocol.json')==p['point_model_protocol_sha256']
 assert sys.version_info[:2]==(3,9) and sklearn.__version__=='1.6.1' and np.__version__=='1.26.4'
 with open(R/'automation/state/online_survival_cpu.lock','r+') as lk:
  fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB);c=json.loads((R/'automation/state/coordinator.json').read_text());assert c['owner']==c['thread_id']==p['owner'] and c['takeover_verified'] and not c['new_fits_allowed']
  assert c['policy_fit_scale_GO']['sha256']==sha(O/'ROOT_GO.json')
  with (O/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
  loads=calls=scalars=0
  def timeout(signum,frame):raise TimeoutError('180s one-shot budget exceeded')
  signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,max(.001,180-(time.monotonic()-start)))
  try:
   for name,hkey in [('source_fit_predictions','source_fit_sha256'),('source_calibration_predictions','source_calibration_sha256'),('checkpoint_provenance_completion_path','checkpoint_provenance_completion_sha256'),('source_old_parameters','source_old_parameters_sha256')]:assert sha(Path(p[name]))==p[hkey]
   rr=list(csv.DictReader(Path(p['source_fit_predictions']).open()));assert len(rr)==22281 and all(r['role']=='fit' for r in rr);ids=sorted({r['cell_id'] for r in rr});assert len(ids)==42 and set(ids)=={k for k,v in co['roles'].items() if v=='fit'}
   pf=Path(mp['policy_features_path']);assert sha(pf)==mp['policy_features_sha256'];pol={r['cell_id']:r for r in json.loads(pf.read_text())};features={};meta={}
   for manifest in co['manifests']:
    path=Path(manifest['path']);assert sha(path)==manifest['sha256']
    for cell in json.loads(path.read_text())['cells']:
     cid=cell['cell_id']
     if co['roles'][cid]!='fit':continue
     assert cell['role']=='train' and cid in ids and cid not in features
     fp=path.parent/(cid+'_features.csv');assert sha(fp)==cell['features_sha256'];ff=list(csv.DictReader(fp.open()));assert len(ff)==cell['prefix_count'];features[cid]={int(r['origin_cycle']):r for r in ff};meta[cid]=cell
   xx=[];yy=[];counts=Counter(r['cell_id'] for r in rr)
   for r in rr:
    cid=r['cell_id'];t=int(r['origin']);f=features[cid][t];event=meta[cid]['event_cycle'];assert int(f['visible_through_cycle'])==t<event and f['rate20_missing']=='False' and co['roles'][cid]==pol[cid]['role']=='fit'
    assert int(r['event_cycle'])==event and int(r['true_RUL'])==event-t and len(features[cid])==counts[cid]
    xx.append([t,float(f['soh']),float(f['rate20_per_cycle'])]+[float(pol[cid][k]) for k in ['effective_C_0_20','effective_C_20_40','effective_C_40_60','effective_C_60_80']]);yy.append(event-t)
   X=np.array(xx,dtype=float);y=np.array(yy,dtype=float);assert X.shape==(22281,7) and np.isfinite(X).all() and (y>0).all();dump('fit_input_receipt.json',dict(cells=ids,rows=len(y),shape=list(X.shape),array_sha256=hashlib.sha256(X.astype('<f8').tobytes()).hexdigest(),features_read_roles=['fit'],dev_test_reads=0))
   cp=Path(p['checkpoint_path']);assert sha(cp)==p['checkpoint_sha256'] and cp.resolve().is_relative_to(R/'experiments/policy_context_point_seed42_v1/checkpoints')
   assert json.loads(Path(p['checkpoint_provenance_completion_path']).read_text())['checkpoint_sha256']==p['checkpoint_sha256']
   with (O/'inference_ledger.jsonl').open('x') as f:f.write(json.dumps(dict(event='checkpoint_load_started',sha256=sha(cp)))+'\n');f.flush();os.fsync(f.fileno())
   loads=1
   with cp.open('rb') as f:model=pickle.load(f)
   assert type(model).__name__=='HistGradientBoostingRegressor' and model.n_features_in_==7 and all(model.get_params()[k]==v for k,v in mp['model'].items())
   with (O/'inference_ledger.jsonl').open('a') as f:f.write(json.dumps(dict(event='predict_started',role='fit',rows=22281,calls=1))+'\n');f.flush();os.fsync(f.fileno())
   calls=1;mu=model.predict(X);assert mu.shape==(22281,) and np.isfinite(mu).all()
   with (O/'inference_ledger.jsonl').open('a') as f:f.write(json.dumps(dict(event='predict_completed',rows=22281))+'\n')
   perfit=[]
   for cid in ids:
    ix=np.array([i for i,r in enumerate(rr) if r['cell_id']==cid]);perfit.append(dict(cell_id=cid,origins=len(ix),mean_squared_log_residual=float(np.mean((mu[ix]-np.log(y[ix]))**2))))
   scalars=1;sigma=max(.05,float(np.sqrt(np.mean([r['mean_squared_log_residual'] for r in perfit]))));assert np.isfinite(sigma) and sigma>=.05
   dump('fit_scale.json',dict(sigma=sigma,floor=.05,rule=p['scale_rule'],cells=42,origins=22281,new_scalar_estimates=1,per_cell=perfit))
   with (O/'fit_predictions.csv').open('x',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rr[0])+['policy_mu_log_RUL']);w.writeheader();w.writerows(dict(r,policy_mu_log_RUL=float(a)) for r,a in zip(rr,mu))
   packed=base64.b64encode(zlib.compress(np.asarray(mu,dtype='<f8').tobytes(),9)).decode();dump('fit_prediction_delta.json',dict(format='zlib-base64-float64le',base_predictions=p['source_fit_predictions'],base_sha256=p['source_fit_sha256'],rows=22281,column='policy_mu_log_RUL',data=packed,decoded_csv_sha256=sha(O/'fit_predictions.csv')))
   source=list(csv.DictReader(Path(p['source_calibration_predictions']).open()));assert len(source)==4567 and all(r['role']=='calibration' for r in source);calids=sorted({r['cell_id'] for r in source});assert len(calids)==10 and not set(calids)&set(ids) and set(calids)=={k for k,v in co['roles'].items() if v=='calibration'};pc=[]
   oldsigma=json.loads(Path(p['source_old_parameters']).read_text())['sigmas']['A_fit_residual_scale'];assert oldsigma==p['old_sigma']
   for cid in calids:
    rows=[r for r in source if r['cell_id']==cid];yt=np.array([float(r['true_RUL']) for r in rows]);mt=np.array([float(r['context_RUL_raw_log']) for r in rows]);med=np.exp(mt);assert np.max(abs(med-[float(r['context_RUL_prediction']) for r in rows]))<1e-10
    for arm,s in zip(p['arms'],[oldsigma,sigma]):
     lo=np.exp(mt+s*ndtri(.1));hi=np.exp(mt+s*ndtri(.9));e=med-yt;width=hi-lo;assert np.isfinite(lo).all() and np.isfinite(hi).all() and (lo<med).all() and (hi>med).all()
     z=dict(cell_id=cid,arm=arm,origins=len(yt),MAE=float(abs(e).mean()),bias=float(e.mean()),severe_over100=float((e>100).mean()),coverage80=float(((yt>=lo)&(yt<=hi)).mean()),width80=float(width.mean()),interval_score80=float((width+10*np.maximum(lo-yt,0)+10*np.maximum(yt-hi,0)).mean()),lower_miss=float((yt<lo).mean()),upper_miss=float((yt>hi).mean()))
     for h in [100,300]:risk=ndtr((np.log(h)-mt)/s);assert ((risk>=0)&(risk<=1)).all();z[f'Brier{h}']=float(((risk-(yt<=h))**2).mean())
     pc.append(z)
   keys=[k for k in pc[0] if k not in ['cell_id','arm','origins']];met={a:{k:float(np.mean([v[k] for v in pc if v['arm']==a])) for k in keys} for a in p['arms']};a,b=[met[x] for x in p['arms']];get=lambda arm,cid:next(r for r in pc if r['arm']==arm and r['cell_id']==cid);improved=sum(abs(get(p['arms'][1],cid)['coverage80']-.8)<abs(get(p['arms'][0],cid)['coverage80']-.8) for cid in calids)
   cmp=dict(sigma_ratio=sigma/oldsigma,interval_score_reduction=1-b['interval_score80']/a['interval_score80'],absolute_coverage_error_reduction=abs(a['coverage80']-.8)-abs(b['coverage80']-.8),cells_coverage_error_improved=improved,width_ratio=b['width80']/a['width80'],mean_Brier_increment=(b['Brier100']+b['Brier300']-a['Brier100']-a['Brier300'])/2,point_metrics_exactly_unchanged=all(a[k]==b[k] for k in p['point_metrics']))
   assert cmp['point_metrics_exactly_unchanged'];cmp['diagnostic_screen_pass']=bool(cmp['interval_score_reduction']>=.05 and cmp['absolute_coverage_error_reduction']>=0 and improved>=7 and cmp['width_ratio']<=2 and cmp['mean_Brier_increment']<=.002)
   dump('metrics.json',met);dump('per_cell_metrics.json',pc);dump('comparison.json',cmp)
   dump('completion.json',dict(status='COMPLETE_ONE_FIT_ONLY_PREDICT_AND_SCALE_NO_REFIT',new_fits=0,optimizer_steps=0,checkpoint_loads=loads,model_predict_calls=calls,fit_rows_predicted=22281,calibration_model_calls=0,new_scalar_estimates=scalars,dev_test_reads=0,checkpoint_sha256=sha(cp),source_calibration_sha256=sha(Path(p['source_calibration_predictions'])),fit_prediction_sha256=sha(O/'fit_predictions.csv'),runner_sha256=sha(Path(__file__)),protocol_sha256=sha(O/'protocol.json'),GO_sha256=sha(O/'ROOT_GO.json'),elapsed_seconds=time.monotonic()-start))
   signal.setitimer(signal.ITIMER_REAL,0);print(json.dumps(dict(sigma=sigma,metrics=met,comparison=cmp)))
  except BaseException as e:
   dump('failure.json',dict(status='FAILED_STOP_NO_RETRY',type=type(e).__name__,error=str(e),checkpoint_loads=loads,predict_calls=calls,new_scalar_estimates=scalars,new_fits=0));raise
if __name__=='__main__':main()
