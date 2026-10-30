from pathlib import Path
import collections,csv,datetime,fcntl,hashlib,json,statistics
R=Path('/home/yndx/zxk/rul');E=R/'experiments/rulaas_external_kit_20261030';O=E/'delay_diagnosis01';owner='01a17810-6ae6-7cf2-9729-5bfcaa8df5f4';W=604800.
def incsv(p):
 with p.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
paths=[O/'positive_alarm_per_query.csv',O/'reference_predictions.csv',E/'queue_value01/predictions.csv']
with (R/'automation/state/coordinator.lock').open('a+') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);cp=R/'automation/state/coordinator.json';co=json.loads(cp.read_text());assert co['owner']==owner and co['state']=='ACTIVE' and co['rulaas_20261029']['stage']=='EXTERNAL_KIT_DELAY_DIAGNOSIS_REVIEW_PASS'
 pairs=incsv(paths[0]);refs=incsv(paths[1]);old=incsv(paths[2]);m={(r['mode'],r['cell_id'],r['query_epoch']):r for r in refs};q={(r['cell_id'],r['query_epoch']):r for r in old if r['stations']=='1' and r['policy']=='pending_value'}
 result={}
 for cat in ['both_miss','a_miss_b_alarm','a_alarm_b_miss','both_alarm']:
  subset=[x for x in pairs if x['mode_a']=='queued1' and x['mode_b']=='immediate' and x['category']==cat];ages=[]
  for x in subset:
   z=q[x['cell_id'],x['query_epoch']];v=m['immediate',x['cell_id'],x['query_epoch']];ages.append(((float(x['query_epoch'])-float(z['latest_sample_epoch']))/W,(float(x['query_epoch'])-float(v['latest_sample_epoch']))/W))
  result[cat]=dict(queries=len(subset),cells=len({x['cell_id'] for x in subset}),groups=len({x['source_group'] for x in subset}),by_group=dict(collections.Counter(x['source_group'] for x in subset)),median_queued_age_weeks=statistics.median(x[0] for x in ages) if ages else None,median_immediate_age_weeks=statistics.median(x[1] for x in ages) if ages else None)
 assert result['both_miss']['queries']==5 and result['a_miss_b_alarm']['queries']==6 and result['both_alarm']['queries']==55
 out=dict(status='PASS',posthoc_descriptive_only=True,reference='one_station_pending_value_vs_immediate',categories=result,source_sha256={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},new_fits=0,new_predictions=0,new_queue_dispatches=0,C3_payload_reads=0,C4_payload_reads=0,confirmation_groups_opened=0)
 with (O/'POSTHOC_ALARM_GROUPS.json').open('x',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2,allow_nan=False)
 co['heartbeat_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();co['rulaas_20261029']['delay_group_diagnostic']=str((O/'POSTHOC_ALARM_GROUPS.json').relative_to(R));cp.write_text(json.dumps(co,ensure_ascii=False,indent=2)+'\n');fcntl.flock(lock,fcntl.LOCK_UN)
print(json.dumps(out,ensure_ascii=False))
