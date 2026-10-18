from pathlib import Path
import os,time,json,csv,hashlib,datetime
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from scipy.special import ndtr,ndtri
R=Path('/home/yndx/zxk/rul');O=R/'experiments/matr_raw_heldout_calibration_seed42_v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(name,x):
 with (O/name).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
def savecsv(name,rows):
 with (O/name).open('x',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def metric(y,mu,sigma):
 lo=np.exp(mu+sigma*ndtri(.1));med=np.exp(mu);hi=np.exp(mu+sigma*ndtri(.9));risk=[ndtr((np.log(h)-mu)/sigma) for h in [100,300]];err=med-y
 assert all(np.isfinite(x).all() for x in [lo,med,hi]+risk)
 return {'MAE':float(abs(err).mean()),'bias':float(err.mean()),'severe_over100':float((err>100).mean()),'coverage80':float(((y>=lo)&(y<=hi)).mean()),'width80':float((hi-lo).mean()),'interval_score80':float((hi-lo+10*np.maximum(lo-y,0)+10*np.maximum(y-hi,0)).mean()),'Brier100':float(((risk[0]-(y<=100))**2).mean()),'Brier300':float(((risk[1]-(y<=300))**2).mean())}
def main():
 start=time.monotonic();p=json.loads((O/'protocol.json').read_text());co=json.loads((O/'cohort.json').read_text());go=json.loads((O/'ROOT_GO.json').read_text())
 assert go['status']=='GO_ONE_CPU_FIT_AND_TWO_SCALAR_RESIDUAL_ESTIMATES_ONLY'
 for name in ['runner.py','protocol.json','cohort.json']:assert go[name+'_sha256']==sha(O/name)
 assert p['max_predictive_fits']==1 and not p['test_access']
 with (O/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
 fits=0
 try:
  rows=[];seen=set()
  for d in co['manifests']:
   D=Path(d['path']).parent;assert sha(D/'manifest.json')==d['sha256'];manifest=json.loads((D/'manifest.json').read_text())
   for c in manifest['cells']:
    cid=c['cell_id'];assert cid not in seen;seen.add(cid);role=co['roles'][cid]
    assert role in ['fit','calibration','development'] and c['role']==('val' if role=='development' else 'train') and c['event_cycle'] is not None
    fp=D/(cid+'_features.csv');assert sha(fp)==c['features_sha256'];rr=list(csv.DictReader(fp.open()));assert len(rr)==c['prefix_count'] and len(rr)>0
    for r in rr:
     t=int(r['origin_cycle']);assert int(r['visible_through_cycle'])==t and t<c['event_cycle'] and r['rate20_missing']=='False'
     rows.append({'cell_id':cid,'role':role,'origin':t,'event_cycle':c['event_cycle'],'true_RUL':c['event_cycle']-t,'x':[t,float(r['soh']),float(r['rate20_per_cycle'])],'weight':1/len(rr)})
  assert len(seen)==70
  sets={role:{r['cell_id'] for r in rows if r['role']==role} for role in ['fit','calibration','development']}
  assert [len(sets[x]) for x in sets]==[42,10,18]
  assert not (sets['fit']&sets['calibration'] or sets['fit']&sets['development'] or sets['calibration']&sets['development'])
  grouped={role:[r for r in rows if r['role']==role] for role in sets};tr=grouped['fit'];X=np.array([r['x'] for r in tr]);Y=np.log([r['true_RUL'] for r in tr]);W=np.array([r['weight'] for r in tr]);W*=len(W)/W.sum()
  assert np.isfinite(X).all() and np.isfinite(Y).all() and time.monotonic()-start<180
  m=HistGradientBoostingRegressor(**p['model']);fits=1
  with (O/'fit_ledger.jsonl').open('a') as f:f.write(json.dumps({'event':'fit_started','number':1,'cells':42,'origins':len(tr)})+'\n');f.flush();os.fsync(f.fileno())
  m.fit(X,Y,sample_weight=W)
  with (O/'fit_ledger.jsonl').open('a') as f:f.write(json.dumps({'event':'fit_completed','number':1})+'\n')
  pp={};residualstats=[]
  for role,rr in grouped.items():
   xx=np.array([r['x'] for r in rr]);mu=m.predict(xx);truth=np.array([r['true_RUL'] for r in rr],float);assert np.isfinite(mu).all();pp[role]=(mu,truth)
   savecsv(role+'_predictions.csv',[{k:r[k] for k in ['cell_id','role','origin','event_cycle','true_RUL']}|{'mu_log_RUL':float(a)} for r,a in zip(rr,mu)])
   if role!='development':
    for cid in sorted(sets[role]):
     ix=np.array([i for i,r in enumerate(rr) if r['cell_id']==cid]);res=np.log(truth[ix])-mu[ix];residualstats.append({'cell_id':cid,'role':role,'origins':len(ix),'mean_log_residual':float(res.mean()),'mean_squared_log_residual':float((res**2).mean())})
  sigmas={arm:max(.05,float(np.sqrt(np.mean([r['mean_squared_log_residual'] for r in residualstats if r['role']==role])))) for arm,role in [('A_fit_residual_scale','fit'),('B_heldout_cell_scale','calibration')]}
  assert time.monotonic()-start<180
  dump('fit_parameters.json',{'model':p['model'],'sigmas':sigmas,'distribution':'lognormal CDF with common mu_log_RUL and arm-specific sigma; shared median exp(mu), no mean/bias calibration','calibration_rule':'sqrt(equal-cell mean squared log residual), floor .05; no dev fitting','predictive_fits':1,'scalar_residual_estimates':2,'cohort_sha256':sha(O/'cohort.json')})
  dump('residual_cell_statistics.json',residualstats)
  rr=grouped['development'];mu,y=pp['development'];pc=[]
  for arm,sigma in sigmas.items():
   for cid in sorted(sets['development']):
    ix=np.array([i for i,r in enumerate(rr) if r['cell_id']==cid]);pc.append({'cell_id':cid,'arm':arm,**metric(y[ix],mu[ix],sigma)})
  keys=[k for k in pc[0] if k not in ['cell_id','arm']];metrics={a:{k:float(np.mean([r[k] for r in pc if r['arm']==a])) for k in keys} for a in sigmas};a=metrics['A_fit_residual_scale'];b=metrics['B_heldout_cell_scale']
  improve=sum(abs(next(x['coverage80'] for x in pc if x['cell_id']==c and x['arm']=='B_heldout_cell_scale')-.8)<abs(next(x['coverage80'] for x in pc if x['cell_id']==c and x['arm']=='A_fit_residual_scale')-.8) for c in sets['development'])
  cmp={'coverage80_absolute_error_reduction':abs(a['coverage80']-.8)-abs(b['coverage80']-.8),'interval_score_relative_reduction':1-b['interval_score80']/a['interval_score80'],'width_ratio':b['width80']/a['width80'],'mean_Brier_increase':(b['Brier100']+b['Brier300']-a['Brier100']-a['Brier300'])/2,'cell_calibration_error_improved':int(improve),'shared_point_MAE_exact':a['MAE']==b['MAE']}
  cmp['predeclared_development_gate']=bool(cmp['coverage80_absolute_error_reduction']>=.03 and cmp['interval_score_relative_reduction']>=.05 and cmp['width_ratio']<=2 and cmp['mean_Brier_increase']<=.002 and improve>=12 and cmp['shared_point_MAE_exact'])
  dump('metrics.json',metrics);dump('per_cell_metrics.json',pc);dump('comparison.json',cmp)
  dump('completion.json',{'status':'COMPLETE_ONE_FIT_HELDOUT_CALIBRATION_DEVELOPMENT_COMPARISON','new_CPU_predictive_fits':fits,'scalar_residual_estimates':2,'optimizer_steps':0,'role_cells':{k:len(v) for k,v in sets.items()},'role_origins':{k:len(v) for k,v in grouped.items()},'test_reads':0,'runner_sha256':sha(Path(__file__)),'protocol_sha256':sha(O/'protocol.json'),'cohort_sha256':sha(O/'cohort.json'),'GO_sha256':sha(O/'ROOT_GO.json'),'prediction_sha256':{role:sha(O/(role+'_predictions.csv')) for role in sets},'elapsed_seconds':time.monotonic()-start})
  print(json.dumps({'status':'COMPLETE','metrics':metrics,'comparison':cmp,'sigmas':sigmas,'fits':1}))
 except BaseException as e:
  dump('failure.json',{'status':'FAILED_STOP_NO_AUTO_RETRY','type':type(e).__name__,'error':str(e),'fit_starts':fits});raise
if __name__=='__main__':main()
