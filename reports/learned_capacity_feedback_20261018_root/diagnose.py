from pathlib import Path
import json,csv,hashlib,math,datetime
import numpy as np
from scipy.stats import spearmanr
R=Path('/home/yndx/zxk/rul');O=R/'reports/learned_capacity_feedback_20261018_root';A=R/'experiments/capacity20_forecast_seed42_v1';B=R/'experiments/matr_raw_heldout_calibration_seed42_v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,x):
 with (O/n).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
def signals(r):
 return {'learned_innovation':float(r['true_delta_mSOH'])-float(r['predicted_delta_mSOH']),'slope_innovation':float(r['true_delta_mSOH'])-float(r['robust20_delta_mSOH']),'observed_delta':float(r['true_delta_mSOH'])}
def rho(x,y):
 if len(x)<3 or np.ptp(x)==0 or np.ptp(y)==0:return None
 return float(spearmanr(x,y).statistic)
def main():
 p=json.loads((O/'protocol.json').read_text());assert sha(A/'calibration_predictions.csv')==p['capacity_prediction_sha256'] and sha(B/'calibration_predictions.csv')==p['rul_prediction_sha256']
 with (O/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
 assert signals({'true_delta_mSOH':-2,'predicted_delta_mSOH':-3,'robust20_delta_mSOH':-1})=={'learned_innovation':1.,'slope_innovation':-1.,'observed_delta':-2.}
 co=json.loads((A/'cohort.json').read_text());ids=sorted(c for c,r in co['roles'].items() if r=='calibration');assert len(ids)==10
 rul={}
 for r in csv.DictReader((B/'calibration_predictions.csv').open()):
  assert r['role']=='calibration' and r['cell_id'] in ids;key=(r['cell_id'],int(r['origin']));assert key not in rul;rul[key]=r
 joined=[];keys=set()
 for r in csv.DictReader((A/'calibration_predictions.csv').open()):
  cid=r['cell_id'];s=int(r['forecast_origin']);t=int(r['target_cycle']);assert cid in ids and t-s==20 and int(r['features_visible_through'])==s<t;key=(cid,t);assert key not in keys;keys.add(key);z=rul[key];assert int(z['event_cycle'])-t==int(z['true_RUL'])
  joined.append({'cell_id':cid,'source_origin':s,'origin':t,'innovation_visible_through':t,**signals(r),'age':t,'retrospective_remaining_error':int(z['true_RUL'])-math.exp(float(z['mu_log_RUL']))})
 assert len(joined)==4367
 pc=[]
 for cid in ids:
  rr=[r for r in joined if r['cell_id']==cid];y=np.array([r['retrospective_remaining_error'] for r in rr]);pos=y>0;neg=y<0;nonzero=y!=0;v={'cell_id':cid,'origins':len(rr),'error_positive':int(pos.sum()),'error_negative':int(neg.sum()),'mean_remaining_error':float(y.mean()),'signals':{}}
  for k in ['learned_innovation','slope_innovation','observed_delta']:
   x=np.array([r[k] for r in rr]);v['signals'][k]={'mean_signal':float(x.mean()),'rho':rho(x,y),'sign_accuracy':float((np.sign(x[nonzero])==np.sign(y[nonzero])).mean()),'balanced_sign_accuracy':float(((x[pos]>0).mean()+(x[neg]<0).mean())/2) if pos.any() and neg.any() else None}
  v['age_rho']=rho([r['age'] for r in rr],y);v['rho_increment_vs_slope']=v['signals']['learned_innovation']['rho']-v['signals']['slope_innovation']['rho'];v['rho_increment_vs_observed_delta']=v['signals']['learned_innovation']['rho']-v['signals']['observed_delta']['rho'];pc.append(v)
 sm={}
 for k in ['learned_innovation','slope_innovation','observed_delta']:
  z=[r['signals'][k] for r in pc];b=[r['balanced_sign_accuracy'] for r in z if r['balanced_sign_accuracy'] is not None];sm[k]={'cell_equal_sign_accuracy':float(np.mean([r['sign_accuracy'] for r in z])),'cell_equal_balanced_sign_accuracy':float(np.mean(b)) if b else None,'both_error_sign_cells':len(b),'median_within_cell_rho':float(np.median([r['rho'] for r in z])),'positive_rho_cells':sum(r['rho']>0 for r in z)}
 sm['median_rho_increment_vs_slope']=float(np.median([r['rho_increment_vs_slope'] for r in pc]));sm['median_rho_increment_vs_observed_delta']=float(np.median([r['rho_increment_vs_observed_delta'] for r in pc]));s=sm['learned_innovation']
 sm['frozen_signal_screen_pass']=bool(s['both_error_sign_cells']>=5 and s['cell_equal_balanced_sign_accuracy']>=.6 and s['median_within_cell_rho']>=.2 and s['positive_rho_cells']>=7 and sm['median_rho_increment_vs_slope']>=.05 and sm['median_rho_increment_vs_observed_delta']>=.05)
 out={'status':'COMPLETE_FROZEN10CAL_LEARNED_CAPACITY_FEEDBACK_DIAGNOSTIC','origins':len(joined),'cells':10,'summary':sm,'per_cell':pc,'protocol_sha256':sha(O/'protocol.json'),'runner_sha256':sha(Path(__file__)),'capacity_prediction_sha256':p['capacity_prediction_sha256'],'rul_prediction_sha256':p['rul_prediction_sha256'],'new_fits':0,'new_model_forwards':0,'development_or_test_reads':0,'limits':'Already exposed cal10, correlated origins; association is not correction performance/novelty/independent confirmation. Capacity innovation observable only at target t, not at source s. TrueRUL residual solely retrospective outcome.'}
 dump('diagnostic.json',out);dump('minimal_validation.json',{'status':'PASS','manual_sign_case':'trueDelta-2 minus predictedDelta-3 = +1 mSOH; simple slopeDelta-1 gives residual-1','one_to_one_target_join':True,'horizon20_and_features_at_source':True,'innovation_visible_through_target_t':True,'all4367_rows_matched':True,'source_hashes_verified':True,'trueRUL_used_in_signal':False,'no_extra_feature_reads':True})
 with (O/'diagnostic_rows.csv').open('x',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(joined[0]));w.writeheader();w.writerows(joined)
 print(json.dumps(out))
if __name__=='__main__':main()
