from pathlib import Path
import json,csv,hashlib,math,datetime
import numpy as np
from scipy.stats import spearmanr
R=Path('/home/yndx/zxk/rul');O=R/'reports/causal_capacity_feedback_20261018_root';E=R/'experiments/matr_raw_heldout_calibration_seed42_v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(name,v):
 with (O/name).open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def signal(qs,qt,old_rul,h=20):
 drop=(qs-.8)*h/old_rul
 return {'innovation':qt-qs+drop,'observed_capacity_change':qt-qs,'model_only_implied_drop':drop}
def corr(a,b):
 if len(a)<3 or np.ptp(a)==0 or np.ptp(b)==0:return None
 return float(spearmanr(a,b).statistic)
def main():
 p=json.loads((O/'protocol.json').read_text());co=json.loads((E/'cohort.json').read_text());ids=sorted(c for c,r in co['roles'].items() if r=='calibration');assert len(ids)==10 and p['source_prediction_sha256']==sha(E/'calibration_predictions.csv')
 with (O/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
 # One hand-check, no estimator: implied decline .04, actual decline .02, innovation +.02.
 assert abs(signal(1.,.98,100.)['innovation']-.02)<1e-12
 pred={cid:{} for cid in ids}
 for r in csv.DictReader((E/'calibration_predictions.csv').open()):
  cid=r['cell_id'];assert cid in ids and r['role']=='calibration';t=int(r['origin']);assert int(r['event_cycle'])-t==int(r['true_RUL']);pred[cid][t]=r
 meta={}
 for x in co['manifests']:
  mp=Path(x['path']);assert sha(mp)==x['sha256']
  for c in json.loads(mp.read_text())['cells']:
   if c['cell_id'] in ids:assert c['role']=='train';meta[c['cell_id']]=(mp.parent,c)
 features={}
 for cid in ids:
  D,c=meta[cid];fp=D/(cid+'_features.csv');assert sha(fp)==c['features_sha256'];v={}
  for r in csv.DictReader(fp.open()):
   t=int(r['origin_cycle']);assert int(r['visible_through_cycle'])==t;v[t]=float(r['soh'])
  features[cid]=v
 rows=[];pc=[];checks=[]
 for cid in ids:
  f=features[cid];rr=[]
  for t,cur in sorted(pred[cid].items()):
   s=t-20
   if s not in pred[cid] or s not in f:continue
   assert s<t and t in f and t>=120
   old=pred[cid][s];old_rul=math.exp(float(old['mu_log_RUL']));now_rul=math.exp(float(cur['mu_log_RUL']));sig=signal(f[s],f[t],old_rul)
   r={'cell_id':cid,'origin':t,'source_origin':s,'visible_through_cycle':t,**sig,'age':t,'retrospective_remaining_error':int(cur['true_RUL'])-now_rul}
   assert all(math.isfinite(x) for x in sig.values());rr.append(r);rows.append(r)
  if rr:
   first=rr[0];t=first['origin'];s=first['source_origin'];cut={i:v for i,v in f.items() if i<=t};assert signal(cut[s],cut[t],math.exp(float(pred[cid][s]['mu_log_RUL'])))=={k:first[k] for k in ['innovation','observed_capacity_change','model_only_implied_drop']};checks.append({'cell_id':cid,'first_origin':t,'prefix_truncation_equal':True})
  y=np.array([r['retrospective_remaining_error'] for r in rr]);z=np.array([r['innovation'] for r in rr]);pos=y>0;neg=y<0;nonzero=y!=0
  acc=float(((np.sign(y[nonzero])==np.sign(z[nonzero]))).mean()) if nonzero.any() else None
  bacc=float(((z[pos]>0).mean()+(z[neg]<0).mean())/2) if pos.any() and neg.any() else None
  v={'cell_id':cid,'origins':len(rr),'error_positive':int(pos.sum()),'error_negative':int(neg.sum()),'sign_accuracy':acc,'balanced_sign_accuracy':bacc,'best_constant_hindsight_sign_accuracy':float(max(pos.sum(),neg.sum())/nonzero.sum()) if nonzero.any() else None,'mean_innovation':float(z.mean()),'mean_remaining_error':float(y.mean()),'rho':{k:corr([r[k] for r in rr],y) for k in ['innovation','observed_capacity_change','model_only_implied_drop','age']}}
  v['innovation_rho_minus_change']=None if v['rho']['innovation'] is None or v['rho']['observed_capacity_change'] is None else v['rho']['innovation']-v['rho']['observed_capacity_change'];v['innovation_rho_minus_model_control']=None if v['rho']['innovation'] is None or v['rho']['model_only_implied_drop'] is None else v['rho']['innovation']-v['rho']['model_only_implied_drop'];pc.append(v)
 out={'status':'COMPLETE_FROZEN10CAL_CAPACITY_PROXY_DIAGNOSTIC','calibration_cells':10,'origins':len(rows),'per_cell':pc,'summary':{}}
 def vals(k):return [r[k] for r in pc if r[k] is not None]
 def mean(x):return float(np.mean(x)) if len(x) else None
 sm=out['summary'];sm['cell_equal_sign_accuracy']=mean(vals('sign_accuracy'));sm['cell_equal_balanced_sign_accuracy']=mean(vals('balanced_sign_accuracy'));sm['both_error_sign_cells']=len(vals('balanced_sign_accuracy'));sm['cell_equal_hindsight_constant_accuracy']=mean(vals('best_constant_hindsight_sign_accuracy'));sm['rho_median']={k:float(np.median([r['rho'][k] for r in pc if r['rho'][k] is not None])) for k in ['innovation','observed_capacity_change','model_only_implied_drop','age']};sm['innovation_positive_rho_cells']=sum(r['rho']['innovation'] is not None and r['rho']['innovation']>0 for r in pc);sm['median_rho_increment_vs_observed_change']=float(np.median(vals('innovation_rho_minus_change')));sm['median_rho_increment_vs_model_control']=float(np.median(vals('innovation_rho_minus_model_control')))
 sm['frozen_support_screen_pass']=bool(sm['both_error_sign_cells']>=5 and sm['cell_equal_balanced_sign_accuracy']>=.6 and sm['rho_median']['innovation']>=.2 and sm['innovation_positive_rho_cells']>=7 and sm['median_rho_increment_vs_observed_change']>=.05 and sm['median_rho_increment_vs_model_control']>=.05)
 out.update(new_fits=0,model_constructions=0,model_forwards=0,optimizer_steps=0,development_or_test_reads=0,protocol_sha256=sha(O/'protocol.json'),runner_sha256=sha(Path(__file__)),source_prediction_sha256=sha(E/'calibration_predictions.csv'),interpretation='Local linear-capacity proxy, not a trained capacity forecast. Association is retrospective and may share algebra with old predicted RUL; controls explicitly included. Correlated origins are not independent samples; no pvalue or paper performance claim.')
 dump('diagnostic.json',out);dump('minimal_validation.json',{'synthetic_signal_innovation':.02,'synthetic_expected':.02,'real_prefix_checks':checks,'status':'PASS','label_used_in_signal':False})
 # Server-only audit rows include capacity-derived signals; do not export these as raw data.
 with (O/'diagnostic_rows.csv').open('x',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 print(json.dumps(out))
if __name__=='__main__':main()
