#!/usr/bin/env python3
"""Independent maturity, group split, common-key and risk metric recomputation."""
import pathlib,json,csv,collections,hashlib,math
import numpy as np
from scipy.special import expit
import joblib
R=pathlib.Path('/home/yndx/zxk/rul');H=R/'experiments/rulaas_temporal_risk_20261029';D=H/'partial_feedback01';HOR=H/'horizon_audit01';PREV=H/'run01';AUD=H/'audit02'
def rows(p):
 with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def group(cid):return cid.rsplit('C',1)[0]
rec=read(D/'receipt.json');dec=read(D/'ROOT_DECISION.json');fit=read(D/'fit_manifest.json');split=read(AUD/'split.json');audit=read(HOR/'INDEPENDENT_RECOMPUTE.json');status=rows(HOR/'training_label_status.csv');oof=rows(D/'training_oof.csv');pred=rows(D/'predictions.csv');old=rows(PREV/'predictions.csv');summ=rows(D/'summary.csv');arm=rows(D/'arm_metrics.csv');contrasts=rows(D/'paired_contrasts.csv');per=rows(D/'paired_per_cell.csv')
assert rec['status']=='SUCCESS' and rec['predictive_fits_started']==rec['predictive_fits_completed']==5 and rec['preprocessor_components_fitted']==0 and rec['model_prediction_rows']==2291 and rec['C3_payload_reads']==rec['C4_payload_reads']==0 and rec['all_fits_before_held_scoring'] and rec['prior_reference_reused_without_refit']
assert audit['status']=='PASS' and dec['status']=='NO_GAIN_FIXED_PARTIAL_FEEDBACK_F0' and rec['training_rows']==1219 and rec['training_groups']==19 and rec['held_rows']==536
outertrain=set(split['outer_train_groups']);outerheld=set(split['outer_held_groups']);cut=float(split['selected']['cutoff_epoch']);assert not outertrain&outerheld
mature=[z for z in status if z['label_within4']!=''];unknown=[z for z in status if not z['label_within4']];assert len(mature)==1219 and len(unknown)==374 and sum(z['old_exact_event_matured']=='True' for z in mature)==940 and sum(z['label_within4']=='1' for z in mature)==256
train={(z['cell_id'],z['arm'],float(z['query_epoch'])):z for z in mature};assert len(train)==len(mature)
for k,z in train.items():assert group(z['cell_id']) in outertrain and group(z['cell_id']) not in outerheld and float(z['query_epoch'])<=cut and float(z['label_available_epoch'])<=cut
groups=set(fit['mature_groups']);assert len(groups)==19 and groups=={z['source_group'] for z in mature} and not groups&outerheld and len(fit['folds'])==3
for f in fit['folds']:
 a=set(f['fit_groups']);b=set(f['oof_groups']);assert not a&b and a|b==groups and not (a|b)&outerheld
assert sorted(len(f['oof_groups']) for f in fit['folds'])==[6,6,7] and len(oof)==1219
for z in oof:
 k=(z['cell_id'],z['arm'],float(z['query_epoch']));x=train[k];assert z['source_group']==x['source_group'] and z['target_within4']==x['label_within4'] and abs(float(expit(float(z['raw_margin'])))-float(z['raw_probability']))<1e-12
names=['event_only_raw','event_only_platt','horizon_mature_raw','horizon_mature_platt'];assert len(pred)==4*536
oldmap={(z['model'],z['cell_id'],z['arm'],float(z['query_epoch'])):z for z in old if z['model'] in ['hgb_F0_raw','hgb_F0_platt']};by=collections.defaultdict(list);keys=collections.defaultdict(dict)
for z in pred:
 name=z['model'];cid=z['cell_id'];q=float(z['query_epoch']);k=(cid,z['arm'],q);assert group(cid) in outerheld and q>=cut and z['source_group']==group(cid)
 y=int(z['target_within4']);truth=float(z['target_rul_weeks']);p=float(z['prob_within4']);m=float(z['raw_margin']);assert y==int(truth<=4.) and math.isfinite(m) and abs(float(expit(m))-p)<1e-12 and abs(float(z['Brier4'])-(p-y)**2)<1e-12 and abs(float(z['logloss'])-(float(np.logaddexp(0.,m))-y*m))<1e-10
 if name.startswith('event_only_'):
  oldname='hgb_F0_raw' if name.endswith('raw') else 'hgb_F0_platt';a=oldmap[(oldname,)+k]
  assert p==float(a['prob_within4']) and m==float(a['raw_margin']) and y==int(a['target_within4']) and truth==float(a['target_rul_weeks'])
 by[name,cid].append(z);keys[name][k]=(truth,y)
assert all(len(keys[n])==536 and keys[n]==keys[names[0]] for n in names)
platt=joblib.load(D/'partial_F0_platt.joblib');coef=float(platt.coef_[0,0]);intercept=float(platt.intercept_[0]);lookup={(z['cell_id'],z['arm'],float(z['query_epoch'])):z for z in pred if z['model']=='horizon_mature_raw'};formulaerr=0.
for z in pred:
 if z['model']=='horizon_mature_platt':
  k=(z['cell_id'],z['arm'],float(z['query_epoch']));e=abs(float(z['raw_margin'])-(coef*float(lookup[k]['raw_margin'])+intercept));formulaerr=max(formulaerr,e);assert e<1e-10
cells=sorted({z['cell_id'] for z in pred});sourcegroups=sorted({group(cid) for cid in cells});assert len(cells)==18 and len(sourcegroups)==10
percell={};misses={};maxerr=0.
for s in summ:
 name=s['model'];rr=[z for z in pred if z['model']==name];percell[name]={cid:float(np.mean([float(z['Brier4']) for z in by[name,cid]])) for cid in cells};err=abs(float(s['cell_macro_Brier4'])-float(np.mean(list(percell[name].values()))));maxerr=max(maxerr,err);assert err<1e-12
 assert abs(float(s['cell_macro_logloss'])-float(np.mean([np.mean([float(z['logloss']) for z in by[name,cid]]) for cid in cells])))<1e-10
 pos=[z for z in rr if z['target_within4']=='1'];neg=[z for z in rr if z['target_within4']=='0'];assert len(pos)==179 and len(neg)==357 and abs(float(s['false_negative_fraction'])-float(np.mean([float(z['prob_within4'])<.5 for z in pos])))<1e-12 and abs(float(s['false_positive_fraction'])-float(np.mean([float(z['prob_within4'])>=.5 for z in neg])))<1e-12
 e=collections.defaultdict(list)
 for z in rr:
  if 0.<float(z['target_rul_weeks'])<=4:e[(z['cell_id'],z['arm'])].append(float(z['prob_within4']))
 misses[name]=sum(not any(p>=.5 for p in v) for v in e.values());assert len(e)==int(s['pre_event_episode_units']) and misses[name]==int(s['missed_pre_event_episode_units'])
for a in arm:
 rr=[z for z in pred if z['model']==a['model'] and z['arm']==a['arm']];b=collections.defaultdict(list)
 for z in rr:b[z['cell_id']].append(float(z['Brier4']))
 assert len(rr)==int(a['rows']) and len(b)==int(a['cells']) and abs(float(a['cell_macro_Brier4'])-np.mean([np.mean(x) for x in b.values()]))<1e-12
idx=np.random.RandomState(42).randint(len(sourcegroups),size=(5000,len(sourcegroups)))
for x in contrasts:
 candidate=x['candidate'];reference=x['reference'];delta=np.asarray([percell[candidate][cid]-percell[reference][cid] for cid in cells]);sums=np.asarray([sum(delta[i] for i,cid in enumerate(cells) if group(cid)==gr) for gr in sourcegroups]);counts=np.asarray([sum(group(cid)==gr for cid in cells) for gr in sourcegroups]);boot=sums[idx].sum(axis=1)/counts[idx].sum(axis=1)
 assert abs(float(x['delta_Brier4'])-float(delta.mean()))<1e-12 and abs(float(x['CI_low'])-float(np.quantile(boot,.025)))<1e-12 and abs(float(x['CI_high'])-float(np.quantile(boot,.975)))<1e-12 and int(x['candidate_missed_episodes'])==misses[candidate] and int(x['reference_missed_episodes'])==misses[reference]
 for i,cid in enumerate(cells):
  z=next(z for z in per if z['candidate']==candidate and z['reference']==reference and z['cell_id']==cid);assert abs(float(z['delta_Brier4'])-delta[i])<1e-12
main=next(x for x in contrasts if x['candidate']=='horizon_mature_platt');assert float(main['relative_Brier_improvement'])>=.05 and float(main['CI_high'])>=0. and dec['status']=='NO_GAIN_FIXED_PARTIAL_FEEDBACK_F0'
out=dict(status='PASS',new_fits=0,new_inference_rows=0,C3_payload_reads=0,C4_payload_reads=0,training_mature_rows=len(mature),training_unknown_rows=len(unknown),training_groups=len(groups),held_common_queries=536,held_cells=len(cells),held_groups=len(sourcegroups),all_models_same_keys_targets=True,old_baseline_predictions_unchanged=True,training_asof_and_group_isolation='PASS',oof_and_calibration_formula='PASS',max_calibrator_formula_error=formulaerr,max_Brier_recompute_error=maxerr,predeclared_gate='NO_GAIN because upper CI >= 0',limits=['Training group and class composition differ between label regimes.','Feedback registry is synthetic and includes recorded detections a deployed policy could skip.','Same ten held groups were previously inspected; no independent confirmation.','374 training labels remain unknown; no general censoring solution.'],input_sha256={str(p.relative_to(R)):sha(p) for p in [D/'training_oof.csv',D/'predictions.csv',D/'summary.csv',D/'arm_metrics.csv',D/'paired_contrasts.csv',D/'paired_per_cell.csv',D/'fit_manifest.json',D/'receipt.json',D/'ROOT_DECISION.json',HOR/'INDEPENDENT_RECOMPUTE.json',PREV/'INDEPENDENT_RECOMPUTE_V2.json']})
with (D/'INDEPENDENT_RECOMPUTE.json').open('x',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps(out,ensure_ascii=False))
