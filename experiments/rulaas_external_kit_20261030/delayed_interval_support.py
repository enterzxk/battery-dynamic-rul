#!/usr/bin/env python3
"""Build training-only delayed interval/right-censor labels at the fixed cutoff."""
from pathlib import Path
import collections,csv,datetime,fcntl,hashlib,json,math,statistics,time,traceback
R=Path('/home/yndx/zxk/rul');E=R/'experiments/rulaas_external_kit_20261030';O=E/'delayed_interval_support01';W=604800.;LAG=14*86400.;CUT=1674233100.;owner='01a17810-6ae6-7cf2-9729-5bfcaa8df5f4';gp=E/'GO_DELAYED_INTERVAL_SUPPORT01.json'
stamp=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def out(p,x):
 with p.open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def csvout(p,rows):
 assert rows
 with p.open('x',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
locks=[];t0=time.time();rec=dict(status='STARTED',new_global_fits=0,new_local_fits=0,new_model_predictions=0,validation_outcomes_parsed=0,C3_payload_reads=0,C4_payload_reads=0,confirmation_groups_opened=0,actual_coordinator_model_recorded='gpt-6.1-terra')
try:
 for p in [R/'automation/state/coordinator.lock',R/'automation/locks/isu_irregular_rul_cpu.lock']:
  f=p.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
 cp=R/'automation/state/coordinator.json';co=read(cp);assert co['owner']==co['thread_id']==owner and co['state']=='ACTIVE' and co['rulaas_20261029']['stage']=='EXTERNAL_KIT_INTERVAL_IDENTIFIABILITY_REVIEW_PASS' and co['rulaas_20261029']['github_sync_pending'] is False
 assert read(E/'interval_identifiability01/INDEPENDENT_RECOMPUTE.json')['status']=='PASS'
 split=read(E/'TRAIN_SPLIT.json');fit=set(split['fit_groups']);val=set(split['internal_validation_groups']);locked=set(split['external_confirmation_groups_locked']);assert len(fit)==45 and len(val)==15 and len(locked)==16 and not fit&val and not(fit|val)&locked
 selection=read(E/'cutoff_support01/SELECTION.json');assert selection['selected']['cutoff_epoch']==CUT
 assert not gp.exists() and not O.exists()
 paths=['AGENTS.md','experiments/rulaas_external_kit_20261030/TRAIN_SPLIT.json','experiments/rulaas_external_kit_20261030/cutoff_support01/SELECTION.json',
  'experiments/rulaas_external_kit_20261030/development_audit01/development_candidates.csv','experiments/rulaas_external_kit_20261030/interval_identifiability01/INDEPENDENT_RECOMPUTE.json',
  'experiments/rulaas_external_kit_20261030/DELAYED_INTERVAL_SUPPORT_PROTOCOL_ZH.md','experiments/rulaas_external_kit_20261030/delayed_interval_support.py']
 go=dict(status='APPROVED',request_id='KIT_DELAYED_INTERVAL_SUPPORT_20261030_01',owner=owner,issued_utc=stamp(),actual_model='gpt-6.1-terra',
  new_fit_cap=0,new_model_prediction_cap=0,training_row_cap=5000,cutoff_epoch=CUT,assumed_report_delay_seconds=LAG,
  allow_validation_outcomes=False,allow_confirmation_groups=False,allow_C3=False,allow_C4=False,input_sha256={p:sha(R/p) for p in paths})
 out(gp,go);O.mkdir();out(E/'KIT_DELAYED_INTERVAL_SUPPORT_20261030_01.claim.json',dict(GO_sha256=sha(gp),claimed_utc=stamp()))
 co['heartbeat_utc']=stamp();co['rulaas_20261029'].update(stage='EXTERNAL_KIT_DELAYED_INTERVAL_SUPPORT_ACTIVE',current_GO=str(gp.relative_to(R)),max_new_fits=0,max_prediction_rows=0);cp.write_text(json.dumps(co,ensure_ascii=False,indent=2)+'\n')
 cells=collections.defaultdict(list)
 with (E/'development_audit01/development_candidates.csv').open(newline='',encoding='utf-8') as f:
  for r in csv.DictReader(f):
   g=r['source_group']
   if g not in fit:continue
   assert g not in val and g not in locked
   s=float(r['timestamp_s'])
   if s+LAG<=CUT:cells[r['cell_id']].append(r)
 cases=[];ex=collections.Counter();event_cells=set();censor_cells=set();event_groups=set();censor_groups=set();interval_widths=[]
 for cid,rs in sorted(cells.items()):
  rs.sort(key=lambda x:float(x['timestamp_s']));times=[float(x['timestamp_s']) for x in rs];assert all(a<b for a,b in zip(times,times[1:])) and all(s+LAG<=CUT for s in times)
  if float(rs[0]['num_cycles_checkup'])>1:ex['initial_baseline_unavailable']+=1;continue
  cap0=float(rs[0]['cap_aged_est_Ah']);assert math.isfinite(cap0) and cap0>0;threshold=.8*cap0
  fail=next((i for i,r in enumerate(rs) if float(r['cap_aged_est_Ah'])<=threshold),None);end=fail if fail is not None else len(rs)
  if end<2:ex['fewer_than_two_healthy_reports_before_event_or_cutoff']+=1;continue
  if fail is not None:
   lower,upper=times[fail-1],times[fail];mature=upper+LAG;status='interval_event';assert lower<upper and mature<=CUT
  else:
   lower,upper=times[-1],None;mature=lower+LAG;status='right_censored';assert mature<=CUT
  widths=[]
  for i in range(1,end):
   s=times[i];q=s+LAG;prev=times[i-1];v=float(rs[i]['cap_aged_est_Ah']);pv=float(rs[i-1]['cap_aged_est_Ah']);gap=(s-prev)/W
   assert prev<s<=q<=CUT and gap>0 and int(float(rs[i]['timestamp_origin']))==1 and v>threshold and pv>threshold
   lo=(lower-times[0])/W;hi=(upper-times[0])/W if upper is not None else None
   assert lo>=0 and (hi is None or hi>lo)
   if status=='interval_event':relation='before_or_at_last_healthy' if q<=lower else 'after_first_recorded_crossing' if q>=upper else 'within_crossing_interval'
   else:relation='known_healthy_at_query_by_later_cutoff' if q<=lower else 'query_after_last_known_healthy'
   feature=dict(source_group=rs[i]['source_group'],cell_id=cid,query_epoch=q,latest_sample_epoch=s,previous_sample_epoch=prev,
      origin_age_query_weeks=(q-times[0])/W,capacity_baseline_Ah=cap0,capacity_current_Ah=v,capacity_ratio=v/cap0,
      prior_gap_weeks=gap,recent_capacity_slope_Ah_per_week=(v-pv)/gap,visible_checkup_count=i+1,
      sample_age_weeks=LAG/W,age_type=float(rs[i]['age_type']),age_temp=float(rs[i]['age_temp']),age_soc=float(rs[i]['age_soc']),
      age_chg_rate=float(rs[i]['age_chg_rate']),age_dischg_rate=float(rs[i]['age_dischg_rate']),age_profile=float(rs[i]['age_profile']))
   feature.update(label_status=status,label_lower_absolute_age_weeks=lo,label_upper_absolute_age_weeks=hi,label_maturity_epoch=mature,query_relation_to_label=relation)
   assert all(math.isfinite(feature[k]) for k in ['origin_age_query_weeks','capacity_baseline_Ah','capacity_current_Ah','capacity_ratio','prior_gap_weeks','recent_capacity_slope_Ah_per_week','sample_age_weeks','age_type','age_temp','age_soc','age_chg_rate','age_dischg_rate','age_profile'])
   cases.append(feature);assert len(cases)<=go['training_row_cap'] and feature['source_group'] in fit
  if fail is not None:event_cells.add(cid);event_groups.add(rs[0]['source_group']);interval_widths.append((upper-lower)/W)
  else:censor_cells.add(cid);censor_groups.add(rs[0]['source_group'])
 assert len({(x['cell_id'],x['query_epoch']) for x in cases})==len(cases) and cases
 counts=collections.Counter(x['label_status'] for x in cases);relations=collections.Counter(x['query_relation_to_label'] for x in cases)
 interval_rows=[x for x in cases if x['label_status']=='interval_event'];right=[x for x in cases if x['label_status']=='right_censored']
 assert all(x['label_maturity_epoch']<=CUT for x in cases) and all(x['label_upper_absolute_age_weeks'] is None for x in right)
 support=dict(status='TRAINING_ONLY_DELAYED_INTERVAL_SUPPORT_AUDITED',cutoff_epoch=CUT,assumed_report_delay_days=14,training_groups_allowed=len(fit),
  cells_with_any_available_record=len(cells),eligible_cells=len(event_cells|censor_cells),eligible_groups=len(event_groups|censor_groups),
  training_queries=len(cases),label_status_counts=dict(counts),query_relation_to_label_counts=dict(relations),
  interval_event_cells=len(event_cells),interval_event_groups=len(event_groups),right_censored_cells=len(censor_cells),right_censored_groups=len(censor_groups),
  zero_lower_interval_queries=sum(x['label_lower_absolute_age_weeks']==0 for x in interval_rows),zero_lower_censor_queries=sum(x['label_lower_absolute_age_weeks']==0 for x in right),
  event_interval_width_median_weeks=statistics.median(interval_widths) if interval_widths else None,excluded=dict(ex),
  labels_use_absolute_age=True,arrival_delay_is_simulated=True,cutoff_chosen_retrospectively=True,physical_crossing_interval_assumption_unverified=True)
 csvout(O/'training_cases.csv',cases);out(O/'SUPPORT.json',support)
 out(O/'DECISION.json',dict(status='TRAINING_ONLY_DELAYED_INTERVAL_LABELS_BUILT_NOT_MODEL_GAIN',paper_ready=False,
  labels_available_by_cutoff_only=True,no_assumed_alive_at_query=True,prior_no_gain_preserved=True,
  limits=['first recorded crossing brackets a latent crossing only under unverified irreversibility','14-day report delay simulated','informative censoring possible','cutoff choice retrospective','no validation performance']))
 rec.update(status='SUCCESS',finished_utc=stamp(),elapsed_seconds=time.time()-t0,GO_sha256=sha(gp),input_sha256=go['input_sha256'],training_rows=len(cases),
  eligible_cells=len(event_cells|censor_cells),validation_outcomes_parsed=0,all_labels_and_features_available_by_cutoff=True)
 out(O/'receipt.json',rec);co['heartbeat_utc']=stamp();co['rulaas_20261029'].update(stage='EXTERNAL_KIT_DELAYED_INTERVAL_SUPPORT_COMPLETE',delayed_interval_support=str((O/'SUPPORT.json').relative_to(R)),github_sync_pending=True);cp.write_text(json.dumps(co,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(dict(status='SUCCESS',support=support),ensure_ascii=False))
except BaseException as e:
 rec.update(status='FAILED',error=repr(e),traceback=traceback.format_exc(),finished_utc=stamp())
 if O.exists() and not (O/'failure_receipt.json').exists():out(O/'failure_receipt.json',rec)
 print(json.dumps(rec,ensure_ascii=False));raise
finally:
 for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
