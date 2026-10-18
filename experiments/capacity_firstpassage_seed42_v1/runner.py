from pathlib import Path
import os,time,json,csv,hashlib,datetime,math,sys,pickle
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
import numpy as np,sklearn
R=Path('/home/yndx/zxk/rul');O=R/'experiments/capacity_firstpassage_seed42_v1';A=R/'experiments/capacity20_forecast_seed42_v1';B=R/'experiments/matr_raw_heldout_calibration_seed42_v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,x):
 with (O/n).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
def roll(model,X,fit_max_age,start):
 n=len(X);state=X.copy();alive=np.ones(n,bool);pred=np.full(n,np.nan);status=np.array(['MAX_HORIZON']*n,dtype=object);ageex=np.zeros(n,bool);calls=0;rowforwards=0
 qmin=float(state[:,1].min());qmax=float(state[:,1].max());ratemin=float(state[:,2].min());ratemax=float(state[:,2].max())
 for step in range(100):
  ix=np.flatnonzero(alive)
  if not len(ix):break
  assert time.monotonic()-start<180
  ageex[ix]|=state[ix,0]>fit_max_age
  delta=model.predict(state[ix]);calls+=1;rowforwards+=len(ix)
  oldq=state[ix,1].copy();newq=oldq+delta/1000
  invalid=~np.isfinite(delta)|~np.isfinite(newq)|(newq>2)|(newq<0)
  if invalid.any():status[ix[invalid]]='INVALID_GENERATED_STATE';alive[ix[invalid]]=False
  cross=(~invalid)&(delta<0)&(newq<=.8)
  if cross.any():
   frac=(oldq[cross]-.8)/(oldq[cross]-newq[cross]);assert np.all((frac>=0)&(frac<=1));pred[ix[cross]]=step*20+frac*20;status[ix[cross]]='CROSSED';alive[ix[cross]]=False
  keep=(~invalid)&(~cross)
  state[ix[keep],0]+=20;state[ix[keep],1]=newq[keep];state[ix[keep],2]=delta[keep]/20
  qmin=min(qmin,float(newq[~invalid].min()) if (~invalid).any() else qmin);qmax=max(qmax,float(newq[~invalid].max()) if (~invalid).any() else qmax)
  ratemin=min(ratemin,float((delta[~invalid]/20).min()) if (~invalid).any() else ratemin);ratemax=max(ratemax,float((delta[~invalid]/20).max()) if (~invalid).any() else ratemax)
 assert calls<=100 and rowforwards<=n*100 and time.monotonic()-start<180
 return pred,status,ageex,{'batch_forward_calls':calls,'row_forwards':rowforwards,'generated_SOH_min_max':[qmin,qmax],'generated_rate_mSOH_per_cycle_min_max':[ratemin,ratemax]}
def main():
 start=time.monotonic();p=json.loads((O/'protocol.json').read_text());go=json.loads((O/'ROOT_GO.json').read_text());assert go['status']=='GO_ONE_TRUSTED_CHECKPOINT_LOAD_CAL_ROLLOUT_NO_FIT'
 for n in ['runner.py','protocol.json','cohort.json']:assert sha(O/n)==go[n+'_sha256']
 cp=A/'checkpoints/auxiliary_hgb.pkl';assert sha(cp)==p['checkpoint_sha256'];assert sklearn.__version__=='1.6.1' and np.__version__=='1.26.4' and sys.version_info[:2]==(3,9);assert sha(B/'calibration_predictions.csv')==p['source_RUL_prediction_sha256']
 with (O/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
 loads=0
 try:
  co=json.loads((O/'cohort.json').read_text());ids={c for c,r in co['roles'].items() if r=='calibration'};assert len(ids)==10;features={};fit_event=[]
  for d in co['manifests']:
   mp=Path(d['path']);assert sha(mp)==d['sha256']
   for c in json.loads(mp.read_text())['cells']:
    cid=c['cell_id'];role=co['roles'][cid]
    if role=='fit':fit_event.append(c['event_cycle']);continue
    if cid not in ids:continue
    fp=mp.parent/(cid+'_features.csv');assert sha(fp)==c['features_sha256'];features[cid]={int(r['origin_cycle']):r for r in csv.DictReader(fp.open())}
  rr=list(csv.DictReader((B/'calibration_predictions.csv').open()));assert len(rr)==4567;X=[];truth=[];base=[]
  for r in rr:
   cid=r['cell_id'];t=int(r['origin']);assert cid in ids and r['role']=='calibration';x=features[cid][t];assert int(x['visible_through_cycle'])==t and x['rate20_missing']=='False' and float(x['soh'])>.8;X.append([t,float(x['soh']),float(x['rate20_per_cycle'])*1000]);truth.append(float(r['true_RUL']));base.append(math.exp(float(r['mu_log_RUL'])));assert int(r['event_cycle'])-t==int(r['true_RUL'])
  X=np.array(X);truth=np.array(truth);base=np.array(base);assert np.isfinite(X).all();assert abs((1.-.8)/.02*20-200)<1e-10
  # One verified load of our own trained estimator, never any external/PBT/old RUL object.
  loads=1
  with cp.open('rb') as f:model=pickle.load(f)
  pred,status,ageex,usage=roll(model,X,max(fit_event)-21,start);capped=np.where(status=='CROSSED',pred,2000.);pc=[];records=[]
  for cid in sorted(ids):
   ix=np.array([j for j,r in enumerate(rr) if r['cell_id']==cid])
   for arm,z in [('direct_RUL_saved',base),('capacity_firstpassage',capped)]:
    e=z[ix]-truth[ix];pc.append({'cell_id':cid,'arm':arm,'MAE':float(abs(e).mean()),'bias':float(e.mean()),'severe_over100':float((e>100).mean()),'noncross_origins':int((status[ix]!='CROSSED').sum()) if arm=='capacity_firstpassage' else 0})
  for j,r in enumerate(rr):records.append({'cell_id':r['cell_id'],'origin':int(r['origin']),'true_RUL':truth[j],'direct_RUL_prediction':base[j],'rollout_RUL_prediction':float(pred[j]) if status[j]=='CROSSED' else None,'rollout_status':str(status[j]),'noncross_lower_bound_cap_for_diagnostic':capped[j],'future_age_beyond_fit_source_support':bool(ageex[j])})
  with (O/'calibration_predictions.csv').open('x',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
  metrics={a:{k:float(np.mean([r[k] for r in pc if r['arm']==a])) for k in ['MAE','bias','severe_over100']} for a in ['direct_RUL_saved','capacity_firstpassage']};u=np.array([next(r['MAE'] for r in pc if r['cell_id']==c and r['arm']=='direct_RUL_saved') for c in sorted(ids)]);v=np.array([next(r['MAE'] for r in pc if r['cell_id']==c and r['arm']=='capacity_firstpassage') for c in sorted(ids)]);b=np.random.default_rng(42).integers(0,10,(2000,10));ci=np.quantile(1-v[b].mean(1)/u[b].mean(1),[.025,.975]);gain=float(1-v.mean()/u.mean());noncross=int((status!='CROSSED').sum());harm=metrics['capacity_firstpassage']['severe_over100']-metrics['direct_RUL_saved']['severe_over100'];cmp={'relative_Time_MAE_reduction':gain,'paired_cell_bootstrap95':ci.tolist(),'improved_cells':int((v<u).sum()),'noncross_or_invalid_origins':noncross,'future_age_support_exceeded_origins':int(ageex.sum()),'severe_over100_increase':harm,'frozen_calibration_gate_passed':bool(noncross==0 and gain>=.05 and ci[0]>0 and (v<u).sum()>=7 and harm<=.01),'metric_warning':'Any noncross/invalid uses2000cycle lower-bound cap ONLY for diagnostic all-origin MAE, not valid point estimate; any such case fails gate. No subset filtering.'}
  dump('metrics.json',metrics);dump('per_cell_metrics.json',pc);dump('comparison.json',cmp);dump('completion.json',{'status':'COMPLETE_CAL_ONLY_FIXED_FIRSTPASSAGE_ROLLOUT','new_fits':0,'checkpoint_loads':1,'calibration_cells':10,'origins':len(rr),'optimizer_steps':0,'development_or_test_reads':0,**usage,'checkpoint_sha256':sha(cp),'runner_sha256':sha(Path(__file__)),'protocol_sha256':sha(O/'protocol.json'),'GO_sha256':sha(O/'ROOT_GO.json'),'prediction_sha256':sha(O/'calibration_predictions.csv'),'elapsed_seconds':time.monotonic()-start,'uncertainty_distribution_implemented':False,'source_support_note':'Age support marker only; full covariate/joint support unverified; generated future slopes use piecewise-linear model path.'})
  print(json.dumps({'metrics':metrics,'comparison':cmp,'usage':usage}))
 except BaseException as e:dump('failure.json',{'error':str(e),'type':type(e).__name__,'status':'STOP_NO_RETRY','checkpoint_load_attempts':loads,'invocation_consumed':True});raise
if __name__=='__main__':main()
