#!/usr/bin/env python3
"""Independent saved-risk output, group-bootstrap and stronger-reference audit."""
import pathlib,json,csv,collections,hashlib,math
import numpy as np
from scipy.special import expit
import joblib
R=pathlib.Path('/home/yndx/zxk/rul');H=R/'experiments/rulaas_temporal_risk_20261029';D=H/'run01';AUD=H/'audit02';FORMAL=R/'experiments/multisource_factorial_20261021/run2_clocksafe'
def rows(p):
 with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def group(c):return c.rsplit('C',1)[0]
rec=read(D/'receipt.json');aud=read(AUD/'AUDIT.json');split=read(AUD/'split.json');fit=read(D/'fit_manifest.json');decision=read(D/'ROOT_DECISION.json');pred=rows(D/'predictions.csv');summ=rows(D/'summary.csv');contrast=rows(D/'paired_contrasts.csv');arm=rows(D/'arm_metrics.csv');bins=rows(D/'calibration_bins.csv')
assert rec['status']=='SUCCESS' and rec['predictive_fits_started']==rec['predictive_fits_completed']==15 and rec['preprocessor_components_fitted']==8 and rec['model_prediction_rows']==6036 and rec['C3_payload_reads']==rec['C4_payload_reads']==0 and rec['held_outcomes_used_in_fitting'] is False and rec['all_fits_before_held_scoring'] is True
assert aud['status']=='PASS_GROUP_AND_HYPOTHETICAL_ASOF_SUPPORT' and decision['status']=='NO_GAIN_FIXED_F3_RISK_SCREEN' and len(pred)==7*536
train=set(split['mature_train_groups']);held=set(split['outer_held_groups']);assert len(train)==15 and len(held)==16 and not train&held and len(fit['folds'])==9
for f in fit['folds']:
 a=set(f['fit_groups']);b=set(f['oof_groups']);assert len(a)==10 and len(b)==5 and a|b==train and not a&b and not (a|b)&held
with (FORMAL/'train_targets.jsonl').open(encoding='utf-8') as f:target=[json.loads(z) for z in f]
source={(z['cell_id'],z['arm'],float(z['query_epoch'])):z for z in target};assert len(source)==len(target)==6870
by=collections.defaultdict(list);keys=collections.defaultdict(dict)
for z in pred:
 name=z['model'];cid=z['cell_id'];q=float(z['query_epoch']);k=(cid,z['arm'],q);t=source[k]
 assert group(cid) in held and group(cid)==z['source_group'] and q>=split['selected']['cutoff_epoch'] and not t['known_event']
 truth=t['target_rul_weeks'];observed=truth is not None;assert (z['label_status']=='observed')==observed
 margin=float(z['raw_margin']);p=float(z['prob_within4']);assert math.isfinite(margin) and math.isfinite(p) and abs(float(expit(margin))-p)<1e-12
 if observed:
  y=int(float(truth)<=4.);assert int(z['target_within4'])==y and abs(float(z['target_rul_weeks'])-float(truth))<1e-10
  assert abs(float(z['Brier4'])-(p-y)**2)<1e-12 and abs(float(z['logloss'])-(float(np.logaddexp(0.,margin))-y*margin))<1e-10
  keys[name][k]=(float(truth),y);by[name,cid].append(z)
 else:assert not z['target_within4'] and not z['Brier4'] and not z['logloss'];keys[name][k]=(None,None)
names=sorted(keys);assert len(names)==7 and all(keys[n]==keys[names[0]] for n in names) and len(keys[names[0]])==536
percell={};misses={};maxerr=0.
for s in summ:
 name=s['model'];allrows=[z for z in pred if z['model']==name];obs=[z for z in allrows if z['label_status']=='observed'];cells=sorted({z['cell_id'] for z in obs});percell[name]={cid:float(np.mean([float(z['Brier4']) for z in by[name,cid]])) for cid in cells}
 err=abs(float(s['cell_macro_Brier4'])-float(np.mean(list(percell[name].values()))));maxerr=max(maxerr,err);assert err<1e-12
 assert abs(float(s['cell_macro_logloss'])-float(np.mean([np.mean([float(z['logloss']) for z in by[name,cid]]) for cid in cells])))<1e-10
 pos=[z for z in obs if z['target_within4']=='1'];neg=[z for z in obs if z['target_within4']=='0'];assert len(pos)==int(s['positive_rows']) and len(neg)==int(s['negative_rows'])
 assert abs(float(s['false_negative_fraction'])-np.mean([float(z['prob_within4'])<.5 for z in pos]))<1e-12 and abs(float(s['false_positive_fraction'])-np.mean([float(z['prob_within4'])>=.5 for z in neg]))<1e-12
 e=collections.defaultdict(list)
 for z in obs:
  y=float(z['target_rul_weeks'])
  if 0.<y<=4:e[(z['cell_id'],z['arm'])].append(float(z['prob_within4']))
 misses[name]=sum(not any(p>=.5 for p in vals) for vals in e.values());assert len(e)==int(s['pre_event_episode_units']) and misses[name]==int(s['missed_pre_event_episode_units'])
for a in arm:
 obs=[z for z in pred if z['model']==a['model'] and z['arm']==a['arm'] and z['label_status']=='observed'];c=collections.defaultdict(list)
 for z in obs:c[z['cell_id']].append(float(z['Brier4']))
 assert len(obs)==int(a['rows']) and len(c)==int(a['cells']) and abs(float(a['cell_macro_Brier4'])-float(np.mean([np.mean(v) for v in c.values()])))<1e-12
for b in bins:
 rows_model=[z for z in pred if z['model']==b['model'] and z['label_status']=='observed'];lo=float(b['lower']);hi=float(b['upper']);bid=int(b['bin'])
 z=[x for x in rows_model if float(x['prob_within4'])>=lo and (float(x['prob_within4'])<hi if bid<4 else float(x['prob_within4'])<=hi)];assert len(z)==int(b['rows'])
 if z:
  counts=collections.Counter(x['cell_id'] for x in rows_model);weights=[1./counts[x['cell_id']] for x in z]
  assert abs(float(b['cell_weighted_mean_probability'])-np.average([float(x['prob_within4']) for x in z],weights=weights))<1e-12 and abs(float(b['cell_weighted_event_rate'])-np.average([int(x['target_within4']) for x in z],weights=weights))<1e-12
cells=sorted({z['cell_id'] for z in pred});groups=sorted({group(cid) for cid in cells});rng=np.random.RandomState(42);idx=rng.randint(len(groups),size=(5000,len(groups)));assert len(cells)==18 and len(groups)==10
def comparison(candidate,reference,alpha):
 delta=np.asarray([percell[candidate][cid]-percell[reference][cid] for cid in cells]);sums=np.asarray([sum(delta[i] for i,cid in enumerate(cells) if group(cid)==gr) for gr in groups]);counts=np.asarray([sum(group(cid)==gr for cid in cells) for gr in groups]);boot=sums[idx].sum(axis=1)/counts[idx].sum(axis=1)
 return dict(candidate=candidate,reference=reference,delta_Brier4=float(delta.mean()),CI_low=float(np.quantile(boot,alpha/2)),CI_high=float(np.quantile(boot,1-alpha/2)),candidate_missed_episodes=misses[candidate],reference_missed_episodes=misses[reference],cells_better=int(sum(v< -1e-12 for v in delta)),cells_worse=int(sum(v>1e-12 for v in delta)),worst_cell=cells[int(np.argmax(delta))],worst_cell_delta=float(max(delta)))
for x in contrast:
 v=comparison(x['candidate'],x['reference'],.05/2)
 assert abs(float(x['delta_Brier4'])-v['delta_Brier4'])<1e-12 and abs(float(x['family_corrected_CI_low'])-v['CI_low'])<1e-12 and abs(float(x['family_corrected_CI_high'])-v['CI_high'])<1e-12 and int(x['candidate_missed_episodes'])==v['candidate_missed_episodes'] and int(x['reference_missed_episodes'])==v['reference_missed_episodes']
cal={}
for name in ['hgb_F0','hgb_F3','logit_F3']:
 model=joblib.load(D/(name+'_platt.joblib'));cal[name]=dict(slope=float(model.coef_[0,0]),intercept=float(model.intercept_[0]))
raw_scores=[float(z['prob_within4']) for z in pred if z['model']=='logit_F3_raw'];cal_scores=[float(z['prob_within4']) for z in pred if z['model']=='logit_F3_platt']
out=dict(status='PASS',new_fits=0,new_inference_rows=0,C3_payload_reads=0,C4_payload_reads=0,methods=len(names),held_queries=len(keys[names[0]]),held_cells=len(cells),held_groups=len(groups),common_keys_targets_and_censor_status=True,group_oof_fit_manifest='PASS',metrics_and_family_bootstrap='PASS',max_Brier_recompute_error=maxerr,platt_parameters=cal,logit_raw_scores_at_least_half=sum(x>=.5 for x in raw_scores),logit_calibrated_scores_at_least_half=sum(x>=.5 for x in cal_scores),logit_raw_pre_event_misses=misses['logit_F3_raw'],logit_calibrated_pre_event_misses=misses['logit_F3_platt'],posthoc_stronger_references=[comparison('hgb_F3_platt','logit_F3_raw',.05),comparison('hgb_F3_platt','hgb_F0_raw',.05)],posthoc_note='Raw-score references and their unadjusted intervals were added after results; they are not preregistered or independent.',limits=['Ten held operating groups; retrospective cutoff based on historical query support.','Synthetic event+14-day label availability, not measured feedback.','198 original censored training rows are not learned as negatives; censor-aware training remains unresolved.','No C3/C4, no online policy evaluation, no independent external test.'],input_sha256={str(p.relative_to(R)):sha(p) for p in [D/'predictions.csv',D/'summary.csv',D/'paired_contrasts.csv',D/'arm_metrics.csv',D/'calibration_bins.csv',D/'fit_manifest.json',D/'receipt.json',D/'ROOT_DECISION.json',AUD/'AUDIT.json',AUD/'split.json']})
with (D/'INDEPENDENT_RECOMPUTE_V2.json').open('x',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps(out,ensure_ascii=False))
