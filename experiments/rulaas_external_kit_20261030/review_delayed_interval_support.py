#!/usr/bin/env python3
"""Independently reconstruct delayed visible prefixes and cutoff labels."""
from pathlib import Path
import collections,csv,datetime,fcntl,hashlib,json,math,statistics
R=Path('/home/yndx/zxk/rul');E=R/'experiments/rulaas_external_kit_20261030';O=E/'delayed_interval_support01';W=604800.;LAG=14*86400.;CUT=1674233100.;owner='01a17810-6ae6-7cf2-9729-5bfcaa8df5f4'
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def incsv(p):
 with p.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def out(p,x):
 with p.open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def close(a,b):return math.isclose(float(a),float(b),rel_tol=1e-11,abs_tol=1e-9)
locks=[]
try:
 for p in [R/'automation/state/coordinator.lock',R/'automation/locks/isu_irregular_rul_cpu.lock']:
  f=p.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
 cp=R/'automation/state/coordinator.json';co=read(cp);assert co['owner']==co['thread_id']==owner and co['state']=='ACTIVE' and co['rulaas_20261029']['stage']=='EXTERNAL_KIT_DELAYED_INTERVAL_SUPPORT_COMPLETE'
 assert read(O/'receipt.json')['status']=='SUCCESS';gp=E/'GO_DELAYED_INTERVAL_SUPPORT_REVIEW01.json';assert not gp.exists() and not (O/'INDEPENDENT_RECOMPUTE.json').exists()
 paths=['experiments/rulaas_external_kit_20261030/GO_DELAYED_INTERVAL_SUPPORT01.json','experiments/rulaas_external_kit_20261030/TRAIN_SPLIT.json',
  'experiments/rulaas_external_kit_20261030/development_audit01/development_candidates.csv','experiments/rulaas_external_kit_20261030/delayed_interval_support01/training_cases.csv',
  'experiments/rulaas_external_kit_20261030/delayed_interval_support01/SUPPORT.json','experiments/rulaas_external_kit_20261030/review_delayed_interval_support.py']
 out(gp,dict(status='APPROVED',owner=owner,issued_utc=now(),new_fits=0,new_predictions=0,allow_validation_outcomes=False,allow_C3=False,allow_C4=False,allow_confirmation_groups=False,input_sha256={p:sha(R/p) for p in paths}))
 split=read(E/'TRAIN_SPLIT.json');fit=set(split['fit_groups']);val=set(split['internal_validation_groups']);locked=set(split['external_confirmation_groups_locked']);assert not fit&(val|locked)
 raw=collections.defaultdict(list)
 with (E/'development_audit01/development_candidates.csv').open(newline='',encoding='utf-8') as f:
  for r in csv.DictReader(f):
   if r['source_group'] not in fit:continue
   if float(r['timestamp_s'])+LAG<=CUT:raw[r['cell_id']].append(r)
 for c in raw:raw[c].sort(key=lambda r:float(r['timestamp_s']))
 cases=incsv(O/'training_cases.csv');assert len(cases)==444 and len({(r['cell_id'],r['query_epoch']) for r in cases})==444
 expected=set();labels={};event_group=set();censor_group=set();event_cells=set();censor_cells=set()
 for c,rs in raw.items():
  if float(rs[0]['num_cycles_checkup'])>1:continue
  ts=[float(r['timestamp_s']) for r in rs];base=float(rs[0]['cap_aged_est_Ah']);threshold=.8*base
  j=next((i for i,r in enumerate(rs) if float(r['cap_aged_est_Ah'])<=threshold),None);end=len(rs) if j is None else j
  if end<2:continue
  if j is None:lower=ts[-1];upper=None;event=False;censor_cells.add(c);censor_group.add(rs[0]['source_group'])
  else:lower=ts[j-1];upper=ts[j];event=True;event_cells.add(c);event_group.add(rs[0]['source_group'])
  labels[c]=(lower,upper,ts[0],event)
  expected.update((c,ts[i]+LAG) for i in range(1,end))
 assert len(expected)==len(cases) and expected=={(r['cell_id'],float(r['query_epoch'])) for r in cases}
 statuses=collections.Counter();relations=collections.Counter();prefixes=0
 for r in cases:
  c=r['cell_id'];q=float(r['query_epoch']);rs=raw[c];visible=[x for x in rs if float(x['timestamp_s'])+LAG<=q];assert len(visible)>=2
  v0,v1=visible[-2:];s0=float(rs[0]['timestamp_s']);s=float(v1['timestamp_s']);previous=float(v0['timestamp_s']);base=float(rs[0]['cap_aged_est_Ah']);cap=float(v1['cap_aged_est_Ah']);pcap=float(v0['cap_aged_est_Ah']);gap=(s-previous)/W
  assert close(q,s+LAG) and close(r['latest_sample_epoch'],s) and close(r['previous_sample_epoch'],previous) and q<=CUT and r['source_group'] in fit
  assert all(float(x['cap_aged_est_Ah'])>.8*base for x in visible)
  for k,v in [('origin_age_query_weeks',(q-s0)/W),('capacity_baseline_Ah',base),('capacity_current_Ah',cap),('capacity_ratio',cap/base),('prior_gap_weeks',gap),('recent_capacity_slope_Ah_per_week',(cap-pcap)/gap),('sample_age_weeks',2.)]:assert close(r[k],v)
  assert int(r['visible_checkup_count'])==len(visible)
  for k in ['age_type','age_temp','age_soc','age_chg_rate','age_dischg_rate','age_profile']:assert close(r[k],v1[k])
  lower,upper,origin,event=labels[c];assert close(r['label_lower_absolute_age_weeks'],(lower-origin)/W)
  if event:
   assert r['label_status']=='interval_event' and close(r['label_upper_absolute_age_weeks'],(upper-origin)/W) and close(r['label_maturity_epoch'],upper+LAG) and upper+LAG<=CUT
   relation='before_or_at_last_healthy' if q<=lower else 'after_first_recorded_crossing' if q>=upper else 'within_crossing_interval'
  else:
   assert r['label_status']=='right_censored' and r['label_upper_absolute_age_weeks']=='' and close(r['label_maturity_epoch'],lower+LAG) and lower+LAG<=CUT
   relation='known_healthy_at_query_by_later_cutoff' if q<=lower else 'query_after_last_known_healthy'
  assert r['query_relation_to_label']==relation;statuses[r['label_status']]+=1;relations[relation]+=1;prefixes+=1
 support=read(O/'SUPPORT.json');assert dict(statuses)==support['label_status_counts'] and dict(relations)==support['query_relation_to_label_counts']
 assert len(event_cells)==support['interval_event_cells'] and len(event_group)==support['interval_event_groups'] and len(censor_cells)==support['right_censored_cells'] and len(censor_group)==support['right_censored_groups']
 result=dict(status='PASS',training_queries_independently_reconstructed=prefixes,source_query_key_coverage_exact=True,feature_prefix_and_report_delay_checked=True,
  absolute_interval_and_right_censor_labels_checked=True,label_maturity_before_cutoff_checked=True,training_group_isolation_checked=True,
  statuses=dict(statuses),query_relations=dict(relations),new_fits=0,new_predictions=0,validation_outcomes_parsed=0,C3_payload_reads=0,C4_payload_reads=0,confirmation_groups_opened=0,
  GO_sha256=sha(gp),finished_utc=now(),limit='14-day reporting delay and physical irreversibility remain assumptions; cutoff was selected retrospectively.')
 out(O/'INDEPENDENT_RECOMPUTE.json',result);co['heartbeat_utc']=now();co['rulaas_20261029'].update(stage='EXTERNAL_KIT_DELAYED_INTERVAL_SUPPORT_REVIEW_PASS',delayed_interval_support_review=str((O/'INDEPENDENT_RECOMPUTE.json').relative_to(R)));cp.write_text(json.dumps(co,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(dict(status='PASS',queries=prefixes,statuses=dict(statuses),query_relations=dict(relations)),ensure_ascii=False))
finally:
 for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
