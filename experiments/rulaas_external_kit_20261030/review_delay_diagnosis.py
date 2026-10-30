#!/usr/bin/env python3
"""Reconstruct reference prefixes incrementally and check the diagnostic."""
from pathlib import Path
import collections,csv,datetime,fcntl,hashlib,json,math,statistics
R=Path('/home/yndx/zxk/rul');E=R/'experiments/rulaas_external_kit_20261030';O=E/'delay_diagnosis01';W=604800.;LAG=14*86400.;owner='01a17810-6ae6-7cf2-9729-5bfcaa8df5f4'
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def incsv(p):
 with p.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def out(p,x):
 with p.open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def num(x):return None if x=='' or x is None else float(x)
def close(a,b):return a is None and b is None or a is not None and b is not None and math.isclose(a,b,rel_tol=1e-11,abs_tol=1e-9)
locks=[]
try:
 for p in [R/'automation/state/coordinator.lock',R/'automation/locks/isu_irregular_rul_cpu.lock']:
  f=p.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
 cp=R/'automation/state/coordinator.json';co=read(cp);assert co['owner']==co['thread_id']==owner and co['state']=='ACTIVE' and co['rulaas_20261029']['stage']=='EXTERNAL_KIT_DELAY_DIAGNOSIS_COMPLETE'
 assert read(O/'receipt.json')['status']=='SUCCESS';gp=E/'GO_DELAY_DIAGNOSIS_REVIEW01.json';assert not gp.exists() and not (O/'INDEPENDENT_RECOMPUTE.json').exists()
 paths=['experiments/rulaas_external_kit_20261030/GO_DELAY_DIAGNOSIS01.json','experiments/rulaas_external_kit_20261030/TRAIN_SPLIT.json','experiments/rulaas_external_kit_20261030/development_audit01/development_candidates.csv',
  'experiments/rulaas_external_kit_20261030/anchor_day100_01/fit_manifest.json','experiments/rulaas_external_kit_20261030/queue_value01/predictions.csv',
  'experiments/rulaas_external_kit_20261030/delay_diagnosis01/reference_predictions.csv','experiments/rulaas_external_kit_20261030/delay_diagnosis01/summary.csv',
  'experiments/rulaas_external_kit_20261030/delay_diagnosis01/positive_alarm_crosses.csv','experiments/rulaas_external_kit_20261030/review_delay_diagnosis.py']
 out(gp,dict(status='APPROVED',owner=owner,issued_utc=now(),new_model_fits=0,reconstruction_queries_cap=3440,allow_C3=False,allow_C4=False,allow_confirmation_groups=False,input_sha256={p:sha(R/p) for p in paths}))
 split=read(E/'TRAIN_SPLIT.json');val=set(split['internal_validation_groups']);locked=set(split['external_confirmation_groups_locked']);assert not val&locked
 refs=incsv(O/'reference_predictions.csv');old=incsv(E/'queue_value01/predictions.csv');base={(x['cell_id'],float(x['query_epoch'])):x for x in old if x['stations']=='1' and x['policy']=='pending_value'};queued2={(x['cell_id'],float(x['query_epoch'])):x for x in old if x['stations']=='2' and x['policy']=='pending_value'}
 assert len(refs)==3440 and len(base)==len(queued2)==1720 and set(base)==set(queued2);cells={c for c,q in base};hist=collections.defaultdict(list)
 for r in incsv(E/'development_audit01/development_candidates.csv'):
  if r['cell_id'] in cells:
   assert r['source_group'] in val and r['source_group'] not in locked;hist[r['cell_id']].append((float(r['timestamp_s']),float(r['cap_aged_est_Ah'])))
 for c in cells:hist[c].sort()
 fallback=float(read(E/'anchor_day100_01/fit_manifest.json')['fallback_median_weeks']);by=collections.defaultdict(list)
 for r in refs:by[r['mode'],r['cell_id']].append(r)
 results={};checked=0
 for mode,delay in [('immediate',0.),('delay14_noqueue',LAG)]:
  for cid in cells:
   source=hist[cid];idx=0;visible=[]
   for r in sorted(by[mode,cid],key=lambda x:float(x['query_epoch'])):
    q=float(r['query_epoch'])
    while idx<len(source) and source[idx][0]+delay<=q:
     visible.append(source[idx]);idx+=1
    assert len(visible)>=2 and float(r['latest_sample_epoch'])==visible[-1][0] and float(r['second_latest_sample_epoch'])==visible[-2][0]
    known=any(v<=.8*source[0][1] for _,v in visible);assert (r['detected_event']=='True')==known
    if known:pred=None
    else:
     (t0,c0),(t1,c1)=visible[-2:];rate=(c1-c0)/((t1-t0)/W);lifetime=(c1-.8*source[0][1])/(-rate) if rate<0 else fallback;pred=(t1+lifetime*W-q)/W
    assert close(pred,num(r['predicted_rul_weeks']))
    x=base[cid,q];assert r['label_status']==x['label_status'] and close(num(r['target_rul_weeks']),num(x['target_rul_weeks'])) and close(num(r['target_within4']),num(x['target_within4']))
    results[mode,cid,q]=pred;checked+=1
 assert checked==3440
 for m,table in [('queued1',base),('queued2',queued2)]:
  for (cid,q),r in table.items():results[m,cid,q]=num(r['predicted_rul_weeks'])
 summary={x['mode']:x for x in incsv(O/'summary.csv')};cross=incsv(O/'positive_alarm_crosses.csv');recomputed={}
 for mode in ['immediate','delay14_noqueue','queued1','queued2']:
  conf=collections.Counter();error=collections.defaultdict(list)
  for (cid,q),r in base.items():
   pred=results[mode,cid,q];target=num(r['target_rul_weeks']);h=num(r['target_within4'])
   if target is not None:assert pred is not None;error[cid].append(abs(pred-target))
   if h is not None:
    assert pred is not None;alarm=pred<=4;conf['TP' if alarm and h==1 else 'FP' if alarm else 'FN' if h==1 else 'TN']+=1
  mae=statistics.mean(statistics.mean(x) for x in error.values());assert close(mae,float(summary[mode]['event_cell_macro_MAE_weeks']))
  for x in ['TP','FP','TN','FN']:assert conf[x]==int(summary[mode][x])
  recomputed[mode]=dict(MAE=mae,**conf)
 for row in cross:
  a,b=row['mode_a'],row['mode_b'];count=collections.Counter()
  for (cid,q),r in base.items():
   if num(r['target_within4'])!=1:continue
   xa=results[a,cid,q]<=4;ya=results[b,cid,q]<=4;key='both_alarm' if xa and ya else 'both_miss' if not xa and not ya else 'a_miss_b_alarm' if not xa else 'a_alarm_b_miss';count[key]+=1
  for k in ['both_alarm','both_miss','a_miss_b_alarm','a_alarm_b_miss']:assert count[k]==int(row[k])
  assert sum(count.values())==66
 result=dict(status='PASS',reference_predictions_independently_reconstructed=checked,method='incremental available-prefix stream',same_key_targets_checked=True,
  summary_and_positive_alarm_crosses_checked=True,metrics=recomputed,new_global_fits=0,new_queue_dispatches=0,C3_payload_reads=0,C4_payload_reads=0,confirmation_groups_opened=0,
  GO_sha256=sha(gp),finished_utc=now(),limit='Retrospective development data; ideal availability arms do not match queue resources.')
 out(O/'INDEPENDENT_RECOMPUTE.json',result);co['heartbeat_utc']=now();co['rulaas_20261029'].update(stage='EXTERNAL_KIT_DELAY_DIAGNOSIS_REVIEW_PASS',delay_diagnosis_review=str((O/'INDEPENDENT_RECOMPUTE.json').relative_to(R)));cp.write_text(json.dumps(co,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(dict(status='PASS',checked=checked,metrics=recomputed),ensure_ascii=False))
finally:
 for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
