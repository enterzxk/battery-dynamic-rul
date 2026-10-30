#!/usr/bin/env python3
"""Fixed-key information-availability analysis of saved queue replay."""
from pathlib import Path
import bisect,collections,csv,datetime,fcntl,hashlib,json,math,statistics,time,traceback
R=Path('/home/yndx/zxk/rul');E=R/'experiments/rulaas_external_kit_20261030';O=E/'delay_diagnosis01';W=604800.;LAG=14*86400.;owner='01a17810-6ae6-7cf2-9729-5bfcaa8df5f4';gp=E/'GO_DELAY_DIAGNOSIS01.json'
stamp=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def incsv(p):
 with p.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def out(p,x):
 with p.open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def csvout(p,rows):
 assert rows
 with p.open('x',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def num(x):return None if x=='' or x is None else float(x)
locks=[];started=time.time();rec=dict(status='STARTED',new_global_fits=0,new_local_fits=0,new_queue_dispatches=0,new_reference_queries=0,C3_payload_reads=0,C4_payload_reads=0,confirmation_groups_opened=0,actual_coordinator_model_recorded='gpt-6.1-terra')
try:
 for p in [R/'automation/state/coordinator.lock',R/'automation/locks/isu_irregular_rul_cpu.lock']:
  f=p.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
 cp=R/'automation/state/coordinator.json';co=read(cp)
 assert co['owner']==co['thread_id']==owner and co['state']=='ACTIVE' and co['rulaas_20261029']['stage']=='EXTERNAL_KIT_QUEUE_VALUE_NO_GAIN_REVIEW_PASS' and co['rulaas_20261029']['github_sync_pending'] is False
 assert read(E/'queue_value01/INDEPENDENT_RECOMPUTE.json')['status']=='PASS' and read(E/'queue_value01/ROOT_DECISION.json')['status']=='NO_GAIN_FIXED_QUEUE_VALUE'
 split=read(E/'TRAIN_SPLIT.json');val=set(split['internal_validation_groups']);locked=set(split['external_confirmation_groups_locked']);assert not val&locked
 assert not gp.exists() and not O.exists()
 paths=['AGENTS.md','experiments/rulaas_external_kit_20261030/TRAIN_SPLIT.json','experiments/rulaas_external_kit_20261030/development_audit01/development_candidates.csv',
        'experiments/rulaas_external_kit_20261030/anchor_day100_01/fit_manifest.json','experiments/rulaas_external_kit_20261030/queue_value01/predictions.csv',
        'experiments/rulaas_external_kit_20261030/queue_value01/INDEPENDENT_RECOMPUTE.json','experiments/rulaas_external_kit_20261030/DELAY_DIAGNOSIS_PROTOCOL_ZH.md',
        'experiments/rulaas_external_kit_20261030/delay_diagnosis.py']
 go=dict(status='APPROVED',request_id='KIT_DELAY_DIAGNOSIS_20261030_01',owner=owner,issued_utc=stamp(),actual_model='gpt-6.1-terra',
  allow_fits=False,queue_dispatch_cap=0,reference_query_cap=3440,allow_C3=False,allow_C4=False,allow_confirmation_groups=False,input_sha256={p:sha(R/p) for p in paths})
 out(gp,go);O.mkdir();out(E/'KIT_DELAY_DIAGNOSIS_20261030_01.claim.json',dict(GO_sha256=sha(gp),claimed_utc=stamp()))
 co['heartbeat_utc']=stamp();co['rulaas_20261029'].update(stage='EXTERNAL_KIT_DELAY_DIAGNOSIS_ACTIVE',current_GO=str(gp.relative_to(R)),max_new_fits=0,max_prediction_rows=3440);cp.write_text(json.dumps(co,ensure_ascii=False,indent=2)+'\n')
 saved=incsv(E/'queue_value01/predictions.csv');base={(r['cell_id'],float(r['query_epoch'])):r for r in saved if r['stations']=='1' and r['policy']=='pending_value'};other={(r['cell_id'],float(r['query_epoch'])):r for r in saved if r['stations']=='2' and r['policy']=='pending_value'}
 assert len(base)==len(other)==1720 and set(base)==set(other);cells={c for c,q in base};assert len(cells)==40
 histories=collections.defaultdict(list);meta={}
 for r in incsv(E/'development_audit01/development_candidates.csv'):
  cid=r['cell_id']
  if cid in cells:
   assert r['source_group'] in val and r['source_group'] not in locked
   histories[cid].append((float(r['timestamp_s']),float(r['cap_aged_est_Ah'])));meta[cid]=r['source_group']
 for c in cells:
  histories[c].sort();assert len(histories[c])>=2 and all(a[0]<b[0] for a,b in zip(histories[c],histories[c][1:]))
 fallback=float(read(E/'anchor_day100_01/fit_manifest.json')['fallback_median_weeks']);new=[]
 for cid,q in sorted(base):
  h=histories[cid];times=[s for s,c in h];cap0=h[0][1]
  for mode,delay in [('immediate',0.),('delay14_noqueue',LAG)]:
   j=bisect.bisect_right(times,q-delay);prefix=h[:j];assert j>=2 and all(s+delay<=q for s,c in prefix)
   visible={s for s,c in prefix}
   for queued in (base[cid,q],other[cid,q]):
    assert float(queued['latest_sample_epoch']) in visible and float(queued['second_latest_sample_epoch']) in visible
   known=any(c<=.8*cap0 for s,c in prefix)
   if known:prediction=None
   else:
    (t0,c0),(t1,c1)=prefix[-2:];slope=(c1-c0)/((t1-t0)/W);rem=(c1-.8*cap0)/(-slope) if slope<0 else fallback;prediction=(t1+rem*W-q)/W;assert math.isfinite(prediction)
   new.append(dict(mode=mode,cell_id=cid,source_group=meta[cid],query_epoch=q,latest_sample_epoch=prefix[-1][0],second_latest_sample_epoch=prefix[-2][0],detected_event=known,predicted_rul_weeks=prediction));rec['new_reference_queries']+=1;assert rec['new_reference_queries']<=go['reference_query_cap']
 assert rec['new_reference_queries']==3440
 # Reuse previously audited outcomes only after reference predictions have been formed.
 allrows=[]
 for r in new:
  k=(r['cell_id'],r['query_epoch']);x=base[k];y=other[k]
  assert all(x[z]==y[z] for z in ['source_group','label_status','target_rul_weeks','target_within4'])
  r.update(label_status=x['label_status'],target_rul_weeks=num(x['target_rul_weeks']),target_within4=num(x['target_within4']));allrows.append(r)
 for mode,source in [('queued1',base),('queued2',other)]:
  for k,x in source.items():
   allrows.append(dict(mode=mode,cell_id=k[0],source_group=x['source_group'],query_epoch=k[1],latest_sample_epoch=float(x['latest_sample_epoch']),second_latest_sample_epoch=float(x['second_latest_sample_epoch']),detected_event=x['detected_event']=='True',predicted_rul_weeks=num(x['predicted_rul_weeks']),label_status=x['label_status'],target_rul_weeks=num(x['target_rul_weeks']),target_within4=num(x['target_within4'])))
 modes=['immediate','delay14_noqueue','queued1','queued2'];summ=[];rowmap={(r['mode'],r['cell_id'],r['query_epoch']):r for r in allrows};assert len(rowmap)==6880
 for mode in modes:
  rr=[x for x in allrows if x['mode']==mode];assert len(rr)==1720;event=collections.defaultdict(list);h=collections.Counter();percell=collections.defaultdict(list)
  for x in rr:
   if x['target_rul_weeks'] is not None:
    assert x['predicted_rul_weeks'] is not None;event[x['cell_id']].append(abs(x['predicted_rul_weeks']-x['target_rul_weeks']))
   if x['target_within4'] is not None:
    assert x['predicted_rul_weeks'] is not None;alarm=x['predicted_rul_weeks']<=4;truth=x['target_within4']==1
    h['TP' if alarm and truth else 'FP' if alarm else 'FN' if truth else 'TN']+=1
    if truth:percell[x['cell_id']].append(alarm)
  assert len(event)==17 and h['TP']+h['FN']==66
  summ.append(dict(mode=mode,queries=len(rr),event_cells=len(event),event_cell_macro_MAE_weeks=statistics.mean(statistics.mean(v) for v in event.values()),
   TP=h['TP'],FP=h['FP'],TN=h['TN'],FN=h['FN'],positive_episode_cells=len(percell),missed_episode_cells=sum(not any(v) for v in percell.values()),
   mean_latest_sample_age_weeks=statistics.mean((x['query_epoch']-x['latest_sample_epoch'])/W for x in rr)))
 positive=[k for k,x in base.items() if num(x['target_within4'])==1];assert len(positive)==66
 comparisons=[];pairs=[]
 for a,b in [('queued1','immediate'),('queued1','delay14_noqueue'),('queued2','immediate'),('queued2','delay14_noqueue'),('delay14_noqueue','immediate')]:
  count=collections.Counter()
  for cid,q in positive:
   x=rowmap[a,cid,q];y=rowmap[b,cid,q];assert x['predicted_rul_weeks'] is not None and y['predicted_rul_weeks'] is not None
   xa=x['predicted_rul_weeks']<=4;ya=y['predicted_rul_weeks']<=4
   category=('both_alarm' if xa and ya else 'both_miss' if not xa and not ya else 'a_miss_b_alarm' if not xa else 'a_alarm_b_miss');count[category]+=1
   pairs.append(dict(mode_a=a,mode_b=b,cell_id=cid,source_group=meta[cid],query_epoch=q,category=category))
  comparisons.append(dict(mode_a=a,mode_b=b,positive_queries=len(positive),both_alarm=count['both_alarm'],both_miss=count['both_miss'],a_miss_b_alarm=count['a_miss_b_alarm'],a_alarm_b_miss=count['a_alarm_b_miss']))
 csvout(O/'reference_predictions.csv',new);csvout(O/'summary.csv',summ);csvout(O/'positive_alarm_crosses.csv',comparisons);csvout(O/'positive_alarm_per_query.csv',pairs)
 out(O/'DECISION.json',dict(status='DESCRIPTIVE_FIXED_AVAILABILITY_DIAGNOSTIC',paper_ready=False,queue_value_NO_GAIN_preserved=True,
  ideal_references_not_resource_matched=True,more_information_not_assumed_better=True,limits=['retrospective development data','synthetic delay and queue','six event groups','recorded event not physical failure','no independent confirmation']))
 rec.update(status='SUCCESS',finished_utc=stamp(),elapsed_seconds=time.time()-started,GO_sha256=sha(gp),input_sha256=go['input_sha256'],
  shared_grid_queries=1720,positive_horizon_queries=66,reference_predictions_made_before_reusing_outcomes=True,queued_history_nested_in_both_reference_prefixes=True)
 out(O/'receipt.json',rec);co['heartbeat_utc']=stamp();co['rulaas_20261029'].update(stage='EXTERNAL_KIT_DELAY_DIAGNOSIS_COMPLETE',delay_diagnosis=str((O/'DECISION.json').relative_to(R)),github_sync_pending=True);cp.write_text(json.dumps(co,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(dict(status='SUCCESS',summary=summ,positive_alarm_crosses=comparisons),ensure_ascii=False))
except BaseException as e:
 rec.update(status='FAILED',error=repr(e),traceback=traceback.format_exc(),finished_utc=stamp())
 if O.exists() and not (O/'failure_receipt.json').exists():out(O/'failure_receipt.json',rec)
 print(json.dumps(rec,ensure_ascii=False));raise
finally:
 for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
