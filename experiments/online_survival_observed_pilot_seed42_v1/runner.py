from pathlib import Path
import os,time,json,hashlib,csv,datetime,collections
os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1'
ROOT=Path('/home/yndx/zxk/rul');OUT=ROOT/'experiments/online_survival_observed_pilot_seed42_v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,d):
 with (OUT/n).open('x',encoding='utf-8') as f:json.dump(d,f,indent=2,ensure_ascii=False);f.write('\n')
def main():
 go=json.loads((OUT/'ROOT_GO.json').read_text());assert go['status']=='GO_OBSERVED_PROCESSED_EVENT_PILOT_ONLY' and go['runner_sha256']==sha(Path(__file__)) and go['protocol_sha256']==sha(OUT/'protocol.json') and go['cohort_sha256']==sha(OUT/'cohort.json') and go['max_predictive_fits']==3 and go['strict_online_claim'] is False and go['test_access'] is False
 with (OUT/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
 started=time.monotonic();fits=0
 try:
  import numpy as np
  from scipy.special import ndtr,ndtri,ndtri_exp
  from scipy.stats import norm
  from sklearn.linear_model import Ridge
  from sklearn.preprocessing import StandardScaler
  proto=json.loads((OUT/'protocol.json').read_text());co=json.loads((OUT/'cohort.json').read_text());assert sha(OUT/'cohort.json')==proto['cohort_sha256'];assert set(co['excluded_future_shift_cells'])==set(proto['known_future_shift_exclusions']);assert not {c['cell_id']+'.pkl' for c in co['cells']} & set(co['excluded_future_shift_cells']);data=[];cellidx={};early=[]
  for c in co['cells']:
   assert c['split'] in ['train','val'];p=ROOT/c['cycle_summary_path'];assert sha(p)==c['cycle_summary_sha256'];rr=json.loads(p.read_text());q=np.array([x['capacity_Ah']/c['norm_Ah'] for x in rr]);T=c['event_cycle'];assert np.flatnonzero(q<=0.8)[0]+1==T
   xx=np.arange(20,dtype=float);coef=(xx-xx.mean())/np.sum((xx-xx.mean())**2);rate=np.convolve(q,coef[::-1],mode='valid');t=np.arange(100,T);assert len(t)>0
   # q[t-1] and slope over q[t-20:t] use only completed cycles through t.
   curr=q[t-1];slopes=rate[t-20];N=len(t);b=float(c['batch']==4);Y=np.log(T-t)
   early.append({'id':c['cell_id'],'role':c['split'],'X':[q[99],rate[80],b],'Y':np.log(T)})
   idx=slice(len(data),len(data)+N);cellidx[c['cell_id']]=idx
   data.extend([{'id':c['cell_id'],'role':c['split'],'t':int(t[i]),'T':T,'soh':float(curr[i]),'rate':float(slopes[i]),'b4':b,'logr':float(Y[i])} for i in range(N)])
  assert len(data)<=200000;train=[x for x in data if x['role']=='train'];val=[x for x in data if x['role']=='val'];assert len({x['id'] for x in train})==52 and len({x['id'] for x in val})==19
  def weights(rows):
   count=collections.Counter(x['id'] for x in rows);return np.array([1/count[x['id']] for x in rows])
  def fit(name,X,y,w):
   nonlocal fits
   assert fits<3 and time.monotonic()-started<180;fits+=1
   with (OUT/'fit_ledger.jsonl').open('a') as f:f.write(json.dumps({'event':'fit_started','fit':fits,'arm':name})+'\n');f.flush();os.fsync(f.fileno())
   sc=StandardScaler().fit(X,sample_weight=w);m=Ridge(alpha=1.0).fit(sc.transform(X),y,sample_weight=w);res=y-m.predict(sc.transform(X));sigma=max(.05,float(np.sqrt(np.average(res**2,weights=w))))
   with (OUT/'fit_ledger.jsonl').open('a') as f:f.write(json.dumps({'event':'fit_completed','fit':fits,'arm':name,'sigma':sigma})+'\n')
   return sc,m,sigma
  tr0=[x for x in early if x['role']=='train'];X=np.array([x['X'] for x in tr0]);y=np.array([x['Y'] for x in tr0]);sc,m,sig0=fit('F0_shared_F1',X,y,np.ones(len(tr0)));vm={x['id']:float(m.predict(sc.transform([x['X']]))[0]) for x in early if x['role']=='val'}
  models={}
  for arm,cols in [('F2_current_state',['t','soh','b4']),('F3_state_rate',['t','soh','b4','rate'])]:
   X=np.array([[x[k] for k in cols] for x in train]);y=np.array([x['logr'] for x in train]);sc,m,sig=fit(arm,X,y,weights(train));V=np.array([[x[k] for k in cols] for x in val]);models[arm]=(m.predict(sc.transform(V)),sig)
  t=np.array([x['t'] for x in val],dtype=float);truth=np.array([x['T']-x['t'] for x in val],dtype=float);mu=np.array([vm[x['id']] for x in val]);z=(np.log(t)-mu)/sig0;logsf=norm.logsf(z);assert np.all(np.isfinite(logsf));arms={}
  q0=[np.maximum(0,np.exp(mu+sig0*ndtri(a))-t) for a in [.1,.5,.9]];p0=[ndtr((np.log(t+h)-mu)/sig0) for h in [100,300]];arms['F0_frozen']=(q0,p0)
  q1=[np.maximum(0,np.exp(mu-sig0*ndtri_exp(logsf+np.log1p(-a)))-t) for a in [.1,.5,.9]];p1=[-np.expm1(norm.logsf((np.log(t+h)-mu)/sig0)-logsf) for h in [100,300]];arms['F1_survival_only']=(q1,p1)
  for arm,(mm,ss) in models.items():arms[arm]=([np.exp(mm+ss*ndtri(a)) for a in [.1,.5,.9]],[ndtr((np.log(h)-mm)/ss) for h in [100,300]])
  assert all(np.all(np.isfinite(a)) for qs,ps in arms.values() for a in qs+ps);assert all(np.all((p>=-1e-12)&(p<=1+1e-12)) for qs,ps in arms.values() for p in ps)
  ids=sorted({x['id'] for x in val});metrics={};cellmetrics=[];(OUT/'validation_predictions').mkdir()
  byid={cid:np.array([i for i,x in enumerate(val) if x['id']==cid]) for cid in ids}
  for arm,(qs,ps) in arms.items():
   errs=qs[1]-truth;cc=[]
   for cid,idx in byid.items():
    v={'arm':arm,'cell_id':cid,'origins':len(idx),'MAE':float(np.mean(np.abs(errs[idx]))),'bias':float(np.mean(errs[idx])),'severe_over100':float(np.mean(errs[idx]>100)),'coverage80':float(np.mean((truth[idx]>=qs[0][idx])&(truth[idx]<=qs[2][idx]))),'width80':float(np.mean(qs[2][idx]-qs[0][idx])),'Brier100':float(np.mean((ps[0][idx]-(truth[idx]<=100))**2)),'Brier300':float(np.mean((ps[1][idx]-(truth[idx]<=300))**2))};cc.append(v);cellmetrics.append(v)
   metrics[arm]={k:float(np.mean([v[k] for v in cc])) for k in ['MAE','bias','severe_over100','coverage80','width80','Brier100','Brier300']}
  for cid,idx in byid.items():
   with (OUT/'validation_predictions'/ (cid+'.csv')).open('x',newline='') as f:
    w=csv.writer(f);w.writerow(['cell_id','origin','observed_event','true_RUL','arm','q10','median_RUL','q90','risk100','risk300'])
    for arm,(qs,ps) in arms.items():
     for i in idx:w.writerow([cid,int(t[i]),val[i]['T'],truth[i],arm,qs[0][i],qs[1][i],qs[2][i],ps[0][i],ps[1][i]])
  rng=np.random.default_rng(42);boot=rng.integers(0,len(ids),size=(2000,len(ids)));comparisons=[]
  for new,old in [('F1_survival_only','F0_frozen'),('F2_current_state','F1_survival_only'),('F3_state_rate','F2_current_state')]:
   aa=np.array([next(v['MAE'] for v in cellmetrics if v['arm']==old and v['cell_id']==cid) for cid in ids]);bb=np.array([next(v['MAE'] for v in cellmetrics if v['arm']==new and v['cell_id']==cid) for cid in ids]);gain=1-bb.mean()/aa.mean();ci=np.quantile(1-bb[boot].mean(axis=1)/aa[boot].mean(axis=1),[.025,.975]);delta=metrics[new]['severe_over100']-metrics[old]['severe_over100'];passed=bool(gain>=.05 and ci[0]>0 and delta<=.02);comparisons.append({'new':new,'old':old,'relative_MAE_reduction':float(gain),'paired_bootstrap95CI':ci.tolist(),'improved_cells':int(np.sum(bb<aa)),'severe_over100_increase':float(delta),'exploratory_gate':passed})
  assert fits==3 and time.monotonic()-started<180
  dump('per_cell_metrics.json',cellmetrics);dump('metrics.json',metrics);dump('comparisons.json',comparisons)
  predsha={str(p.relative_to(OUT)):sha(p) for p in (OUT/'validation_predictions').glob('*.csv')};dump('completion_receipt.json',{'status':'COMPLETE_OBSERVED_PROCESSED_EVENT_PILOT','at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'new_predictive_fits':fits,'optimizer_steps':0,'train_cells':52,'validation_cells':19,'train_origins':len(train),'validation_origins':len(val),'elapsed_seconds':time.monotonic()-started,'predictions_sha256':predsha,'metrics':metrics,'comparisons':comparisons,'strict_online_claim':False,'natural_censoring_benefit_claim':False,'independent_physical_generalization_claim':False,'test_access':False,'bindings':{n:sha(OUT/n) for n in ['runner.py','protocol.json','cohort.json','ROOT_GO.json']}})
  print(json.dumps({'status':'COMPLETE','fits':fits,'metrics':metrics,'comparisons':comparisons}))
 except BaseException as err:
  dump('failure_receipt.json',{'error':str(err),'type':type(err).__name__,'predictive_fit_attempts':fits,'elapsed_seconds':time.monotonic()-started,'status':'FAILED_STOP_NO_AUTOMATIC_RETRY'});raise
if __name__=='__main__':main()
