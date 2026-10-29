#!/usr/bin/env python3
"""Independent causal station, common-key and probability-metric recomputation."""
import pathlib,sys,json,csv,collections,heapq,datetime,hashlib,math
import numpy as np
R=pathlib.Path('/home/yndx/zxk/rul');D=R/'experiments/rulaas_c3_fleets_20261029/run01';sys.path.insert(0,str(R/'experiments/isu_irregular_rul_seed42_v1'));from data_adapter import load_reviewed_cell
DAY=86400.;WEEK=604800.;GUARD=1.3254277288913727
def rows(p):
 with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def start(z):return datetime.datetime.fromisoformat(z['start']).timestamp()
def report(z):return dict(z,arrival_epoch=float(z['stop_epoch'])+14*DAY)
rec=read(D/'receipt.json');part=read(D/'fleet_partition.json');dec=rows(D/'decisions.csv');pred=rows(D/'predictions.csv');per=rows(D/'per_cell.csv');episodes=rows(D/'event_episodes.csv');summ=rows(D/'summary.csv');comp=rows(D/'comparisons.csv')
assert rec['status']=='SUCCESS' and rec['new_fits']==0 and rec['C3_source_cells_read']==63 and rec['C4_payload_reads']==0 and rec['unarrived_signal_mutation']=='PASS' and rec['worlds']==18
partition=part['fleet_by_cell'];ids=sorted(partition);assert len(ids)==63 and all(cid.endswith('C3') for cid in ids) and len({cid.rsplit('C',1)[0] for cid in ids})==63
assert all(partition[cid]=='F'+str(i%3+1) for i,cid in enumerate(ids)) and all(sum(x==fid for x in partition.values())==21 for fid in ['F1','F2','F3'])
source={z['cell_id']:z for z in rec['source_files'] if z['kind']=='DataV2'};assert set(source)==set(ids);data={}
for cid in ids:
 s=source[cid];p=R/s['path'];assert 'C4' not in p.name and sha(p)==s['sha256'];cell=load_reviewed_cell(p,'development');rr=sorted(cell['records'],key=lambda z:float(z['stop_epoch']))
 assert cell['cell_id']==cid
 if len(rr)>=3:
  assert all(start(b)>=float(a['stop_epoch']) for a,b in zip(rr,rr[1:]));data[cid]=dict(rows=rr,byid={int(z['source_rpt_index']):z for z in rr},warm=float(rr[2]['stop_epoch']),end=float(rr[-1]['stop_epoch']),event=next((float(z['stop_epoch']) for z in rr if float(z['capacityAh'])<=.20),None))
byworld=collections.defaultdict(list)
for z in dec:byworld[z['world']].append(z)
assert len(byworld)==18;allaccepted={};decision_checks=0;allocation_checks=0
for world,jobs in byworld.items():
 fid=jobs[0]['fleet'];M=int(jobs[0]['stations']);policy=jobs[0]['policy'];selected=sorted({z['cell_id'] for z in jobs});assert all(partition[cid]==fid for cid in selected)
 accepted={cid:[report(z) for z in data[cid]['rows'][:3]] for cid in selected};busy=[];free=list(range(M))
 for z in sorted(jobs,key=lambda x:(float(x['fleet_request_seconds']),x['cell_id'],float(x['source_request_epoch']),int(x['source_rpt_index']))):
  cid=z['cell_id'];q=float(z['source_request_epoch']);t=float(z['fleet_request_seconds']);row=data[cid]['byid'][int(z['source_rpt_index'])]
  assert abs(start(row)-q)<1e-6 and abs(t-(q-data[cid]['warm']+float(part['offset_seconds'][cid])))<1e-6
  while busy and busy[0][0]<=t:
   _,slot=heapq.heappop(busy);free.append(slot)
  vis=[x for x in accepted[cid] if x['arrival_epoch']<=q];pending=sum(x['arrival_epoch']>q for x in accepted[cid]);assert len(vis)==int(z['input_visible_count']) and pending==int(z['input_pending_count'])
  score=threshold=None
  if any(float(x['capacityAh'])<=.20 for x in vis):reason='known_event'
  elif not free:reason='station_busy'
  elif len(vis)<3:reason='admit_warmup_fallback'
  elif policy=='all':reason='admit'
  else:
   score=(q-float(vis[-1]['stop_epoch']))/WEEK;threshold=({2:2.75,4:3.25}[M] if policy=='age_calibrated' else GUARD)
   if score<threshold:reason='below_age_threshold'
   elif policy=='age_no_pending' and pending>0:reason='pending_report'
   else:reason='admit'
  assert z['reason']==reason and (z['admitted']=='True')==reason.startswith('admit')
  if score is None:assert not z['input_staleness_weeks'] and not z['threshold_weeks']
  else:assert abs(score-float(z['input_staleness_weeks']))<1e-10 and float(z['threshold_weeks'])==threshold
  if reason.startswith('admit'):
   stop=float(row['stop_epoch']);slot=min(free);free.remove(slot);heapq.heappush(busy,(stop-data[cid]['warm']+float(part['offset_seconds'][cid]),slot));accepted[cid].append(report(row));allocation_checks+=1
   assert int(z['station_slot'])==slot and abs(float(z['actual_station_hours'])-(stop-q)/3600.)<1e-8 and abs(float(z['source_stop_epoch_if_admitted'])-stop)<1e-6 and abs(float(z['arrival_epoch_if_admitted'])-(stop+14*DAY))<1e-6 and len(busy)<=M and len(free)+len(busy)==M
  decision_checks+=1
 allaccepted[world]=accepted
grouped=collections.defaultdict(list);keys=collections.defaultdict(dict);same_state={};same_count=0;max_point_error=0.;query_checks=0
for z in pred:
 world=z['world'];cid=z['cell_id'];q=float(z['query_epoch']);d=data[cid];event=d['event'];assert partition[cid]==z['fleet']
 vis=[x for x in allaccepted[world][cid] if start(x)<=q and x['arrival_epoch']<=q];pending=sum(start(x)<=q and x['arrival_epoch']>q for x in allaccepted[world][cid]);ix=[int(x['source_rpt_index']) for x in vis]
 assert ix==json.loads(z['visible_RPT_indices']) and len(vis)==int(z['visible_RPT_count']) and pending==int(z['input_pending_count'])
 known=any(float(x['capacityAh'])<=.20 for x in vis);assert (z['known_event']=='True')==known and (z['primary_positive_rul']=='True')==(event is not None and q<event)
 stale=(q-float(vis[-1]['stop_epoch']))/WEEK;assert abs(stale-float(z['input_staleness_weeks']))<1e-10 and (z['input_stale_above_train_max']=='True')==(stale>3.426952600479126)
 pt=float(z['mean_RUL']);lo=float(z['q10']);hi=float(z['q90']);p=float(z['p_RUL_le4w']);assert all(math.isfinite(x) for x in [pt,lo,hi,p]) and 0<=p<=1 and 0<=lo<=hi
 label4=1 if event is not None and event<=q+4*WEEK else (0 if d['end']>=q+4*WEEK else None)
 assert (int(z['label4']) if z['label4'] else None)==label4
 if label4 is None:assert not z['Brier4']
 else:assert abs(float(z['Brier4'])-(p-label4)**2)<1e-10
 if event is None:assert not z['source_event_epoch'] and not z['target_rul_weeks'] and not z['absolute_error'] and not z['coverage80'] and not z['IS80']
 else:
  y=max(0.,(event-q)/WEEK);assert abs(float(z['source_event_epoch'])-event)<1e-6 and abs(float(z['target_rul_weeks'])-y)<1e-10
  err=abs(float(z['absolute_error'])-abs(pt-y));max_point_error=max(max_point_error,err);assert err<1e-10 and float(z['coverage80'])==float(lo<=y<=hi)
  assert abs(float(z['IS80'])-(hi-lo+10*max(0.,lo-y)+10*max(0.,y-hi)))<1e-10
 if known:assert pt==lo==hi==0. and p==1.
 k=(cid,q,tuple(ix),known);values=(pt,lo,hi,p)
 if k in same_state:assert same_state[k]==values;same_count+=1
 else:same_state[k]=values
 grouped[(world,cid)].append(z);keys[world][(cid,q)]=(event,label4);query_checks+=1
for fid in ['F1','F2','F3']:
 ws=[x for x in keys if x.startswith(fid+'_')];assert len(ws)==6 and all(keys[w]==keys[ws[0]] for w in ws)
byepisode={(z['world'],z['cell_id']):z for z in episodes}
for x in per:
 rs=grouped[(x['world'],x['cell_id'])];positive=[z for z in rs if z['primary_positive_rul']=='True'];allscore=[z for z in rs if z['absolute_error']];bs=[z for z in rs if z['Brier4']];neg=[z for z in rs if z['label4']=='0'];lead=[z for z in positive if float(z['target_rul_weeks'])<=4.];post=[z for z in rs if z['source_event_epoch'] and float(z['query_epoch'])>=float(z['source_event_epoch'])];det=[z for z in post if z['known_event']=='True']
 assert len(rs)==int(x['n_queries']) and len(positive)==int(x['n_primary']) and len(bs)==int(x['n_Brier4']) and sum(not z['label4'] for z in rs)==int(x['n_censored4'])
 measures={'primary_MAE':[float(z['absolute_error']) for z in positive],'all_MAE':[float(z['absolute_error']) for z in allscore],'primary_coverage80':[float(z['coverage80']) for z in positive],'primary_IS80':[float(z['IS80']) for z in positive],'Brier4':[float(z['Brier4']) for z in bs],'false_alarm_fraction':[float(z['p_RUL_le4w'])>=.5 for z in neg],'stale_above_train_max_fraction':[z['input_stale_above_train_max']=='True' for z in rs]}
 for name,v in measures.items():
  if v:assert abs(float(x[name])-float(np.mean(v)))<1e-10
  else:assert not x[name]
 if post:assert (x['known_event_by_last_post_query']=='True')==bool(det)
 else:assert not x['known_event_by_last_post_query']
 e=byepisode[(x['world'],x['cell_id'])];assert (e['has_pre_event_4w_query']=='True')==bool(lead)
 if lead:assert (e['missed_episode']=='True')==(not any(float(z['p_RUL_le4w'])>=.5 for z in lead))
 else:assert not e['missed_episode']
for s in summ:
 world=s['world'];p=[z for z in per if z['world']==world];j=byworld[world];e=[z for z in episodes if z['world']==world and z['has_pre_event_4w_query']=='True'];post=[z for z in p if z['known_event_by_last_post_query']]
 assert len(p)==int(s['cells']) and sum(int(z['n_queries']) for z in p)==int(s['n_queries']) and sum(int(z['n_censored4']) for z in p)==int(s['n_censored4']) and sum(z['admitted']=='True' for z in j)==int(s['admitted_tests'])
 assert abs(float(s['station_hours'])-sum(float(z['actual_station_hours']) for z in j if z['admitted']=='True'))<1e-7 and len(e)==int(s['alarm_eligible_events']) and sum(z['missed_episode']=='True' for z in e)==int(s['missed_episodes'])
 assert len(post)==int(s['cells_with_post_queries']) and sum(z['known_event_by_last_post_query']=='False' for z in post)==int(s['cells_unconfirmed_at_last_post_query'])
 for name in ['primary_MAE','all_MAE','primary_coverage80','primary_IS80','Brier4','false_alarm_fraction','stale_above_train_max_fraction']:
  vals=[float(z[name]) for z in p if z[name]]
  if vals:assert abs(float(s[name])-float(np.mean(vals)))<1e-10
  else:assert not s[name]
for x in comp:
 fid=x['fleet'];M=int(x['stations']);p={(z['cell_id'],z['policy']):z for z in per if z['fleet']==fid and int(z['stations'])==M};cells=sorted({z['cell_id'] for z in per if z['fleet']==fid and int(z['stations'])==M});delta=[float(p[cid,'age_no_pending']['primary_MAE'])-float(p[cid,'age_calibrated']['primary_MAE']) for cid in cells if p[cid,'age_calibrated']['primary_MAE']]
 assert len(delta)==int(x['paired_cells']) and abs(float(x['delta_primary_MAE'])-float(np.mean(delta)))<1e-10 and abs(float(x['worst_cell_delta'])-max(delta))<1e-10
 age=next(s for s in summ if s['fleet']==fid and int(s['stations'])==M and s['policy']=='age_calibrated');pending=next(s for s in summ if s['fleet']==fid and int(s['stations'])==M and s['policy']=='age_no_pending')
 assert float(x['age_station_hours'])==float(age['station_hours']) and float(x['pending_station_hours'])==float(pending['station_hours']) and int(x['age_missed_episodes'])==int(age['missed_episodes']) and int(x['pending_missed_episodes'])==int(pending['missed_episodes'])
result=dict(status='PASS',new_fits=0,new_inference_rows=0,C3_source_cells_read=63,C4_payload_reads=0,fleet_partitions=3,worlds_checked=len(byworld),decisions_checked=decision_checks,station_allocations_checked=allocation_checks,query_predictions_checked=query_checks,same_visible_input_equal_prediction_checks=same_count,all_six_worlds_within_fleet_same_query_target_and_censor_keys=True,resource_visibility_probability_interval_episode_recomputation='PASS',max_absolute_error_recomputation_error=max_point_error,limits=['14-day reporting lag and fleet phases are synthetic.','Three non-overlapping fleets share one previously used C3 development dataset.','Same available stations do not imply equal station hours.','No independent-fleet CI; no C4 or external data confirmation.'],input_sha256={str(p.relative_to(R)):sha(p) for p in [D/'fleet_partition.json',D/'decisions.csv',D/'predictions.csv',D/'per_cell.csv',D/'event_episodes.csv',D/'summary.csv',D/'comparisons.csv',D/'receipt.json']})
with (D/'INDEPENDENT_RECOMPUTE.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps(result,ensure_ascii=False))
