#!/usr/bin/env python3
"""Recompute train-only age calibration and held replay from saved source records."""
import pathlib,sys,json,csv,collections,heapq,datetime,hashlib
import numpy as np
R=pathlib.Path('/home/yndx/zxk/rul');H=R/'experiments/rulaas_pending_station_20261029';D=H/'age_comparator01';CAL=H/'calibration01';FIRST=H/'run01';OLD=R/'experiments/rulaas_gain_identifiability_20261029/run02'
sys.path.insert(0,str(R/'experiments/isu_irregular_rul_seed42_v1'));from data_adapter import load_reviewed_cell
DAY=86400.;WEEK=604800.;GRID=[2.,2.25,2.5,2.75,3.,3.25,3.5,4.,4.5,5.,6.,8.]
def rows(p):
 with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def start(z):return datetime.datetime.fromisoformat(z['start']).timestamp()
def report(z):return dict(z,arrival_epoch=float(z['stop_epoch'])+14*DAY)
receipt=read(D/'receipt.json');cal=read(CAL/'CALIBRATED.json');trainreceipt=read(CAL/'receipt.json');fleet=read(FIRST/'fleet_world.json');priorreview=read(FIRST/'INDEPENDENT_RECOMPUTE.json');split=read(OLD/'cell_split.json');orig=read(OLD/'receipt.json');targets=read(H/'TRAIN_TARGET_ONLY.json')
assert receipt['status']==trainreceipt['status']=='SUCCESS' and receipt['new_fits']==trainreceipt['new_fits']==0 and trainreceipt['model_prediction_rows']==0 and trainreceipt['held_fleet_outcomes_used']==0 and priorreview['status']=='PASS'
assert receipt['C3_payload_reads']==receipt['C4_payload_reads']==0 and cal['uses_held_fleet_outcomes'] is False and cal['grid']==GRID
fit=set(split['base_head_fit_cells']);held=set(split['base_head_unseen_cells']);trainids=split['selected_kernel_fit'];heldids=split['selected_kernel_held'];assert len(trainids)==len(heldids)==24 and set(trainids)<=fit and set(heldids)<=held and not fit&held
src={z['cell_id']:z for z in orig['source_files'] if z['kind']=='DataV2'};data={}
for cid in trainids+heldids:
 z=src[cid];p=R/z['path'];assert cid.endswith(('C1','C2')) and sha(p)==z['sha256'];cell=load_reviewed_cell(p,'train');rr=sorted(cell['records'],key=lambda x:float(x['stop_epoch']))
 assert cell['cell_id']==cid and len(rr)>=3 and all(start(b)>=float(a['stop_epoch']) for a,b in zip(rr,rr[1:]))
 data[cid]=dict(rows=rr,byid={int(z['source_rpt_index']):z for z in rr},warm=float(rr[2]['stop_epoch']),event=next((float(z['stop_epoch']) for z in rr if float(z['capacityAh'])<=.20),None))
timeline=[]
for cid in trainids:
 d=data[cid];off=float(fleet['offset_seconds'][cid])
 for i,z in enumerate(d['rows']):
  if i>=3:q=start(z);timeline.append((q-d['warm']+off,cid,q,i))
timeline.sort();grid=rows(CAL/'grid.csv');assert len(grid)==24
for M in [2,4]:
 for threshold in GRID:
  accepted={cid:[report(z) for z in data[cid]['rows'][:3]] for cid in trainids};busy=[];free=list(range(M));hours=0.;count=0
  for t,cid,q,i in timeline:
   while busy and busy[0][0]<=t:
    _,slot=heapq.heappop(busy);free.append(slot)
   vis=[z for z in accepted[cid] if z['arrival_epoch']<=q]
   if any(float(z['capacityAh'])<=.20 for z in vis) or not free:continue
   if len(vis)>=3 and (q-float(vis[-1]['stop_epoch']))/WEEK<threshold:continue
   z=data[cid]['rows'][i];stop=float(z['stop_epoch']);slot=min(free);free.remove(slot);heapq.heappush(busy,(stop-data[cid]['warm']+float(fleet['offset_seconds'][cid]),slot));accepted[cid].append(report(z));hours+=(stop-q)/3600.;count+=1
   assert len(busy)<=M and len(free)+len(busy)==M
  g=next(x for x in grid if int(x['stations'])==M and float(x['age_threshold_weeks'])==threshold)
  assert abs(float(g['training_station_hours'])-hours)<1e-7 and int(g['training_admitted_tests'])==count and abs(float(g['target_training_station_hours'])-float(targets['station_hours'][str(M)]))<1e-7
 chosen=next(z for z in cal['selected'] if z['stations']==M);best=min([z for z in grid if int(z['stations'])==M],key=lambda z:(float(z['absolute_station_hour_difference']),float(z['age_threshold_weeks'])))
 assert float(best['age_threshold_weeks'])==chosen['age_threshold_weeks'] and abs(float(best['training_station_hours'])-chosen['training_station_hours'])<1e-7
thresholds={z['stations']:z['age_threshold_weeks'] for z in cal['selected']};assert thresholds=={2:2.75,4:3.25}
jobs=rows(D/'age_decisions.csv');pred=rows(D/'age_predictions.csv');pc=rows(D/'paired_per_cell.csv');summary=rows(D/'summary.csv');oldpred=[z for z in rows(FIRST/'predictions.csv') if z['population']=='kernel_held' and z['policy']=='age_no_pending'];oldsum=[z for z in rows(FIRST/'summary.csv') if z['population']=='kernel_held' and z['policy']=='age_no_pending']
assert len(pred)==len(oldpred)==1794 and len(jobs)==802 and len(summary)==2
old={(int(z['stations']),z['cell_id'],float(z['query_epoch'])):z for z in oldpred};assert len(old)==len(oldpred)
byworld=collections.defaultdict(list)
for z in jobs:byworld[z['world']].append(z)
allaccepted={};decision_checks=0;slot_checks=0
for world,jj in byworld.items():
 M=int(jj[0]['stations']);accepted={cid:[report(z) for z in data[cid]['rows'][:3]] for cid in heldids};busy=[];free=list(range(M))
 for z in sorted(jj,key=lambda x:(float(x['fleet_request_seconds']),x['cell_id'],float(x['source_request_epoch']),int(x['source_rpt_index']))):
  cid=z['cell_id'];q=float(z['source_request_epoch']);t=float(z['fleet_request_seconds']);row=data[cid]['byid'][int(z['source_rpt_index'])]
  assert abs(start(row)-q)<1e-6 and abs(t-(q-data[cid]['warm']+float(fleet['offset_seconds'][cid])))<1e-6 and float(z['threshold_weeks'])==thresholds[M]
  while busy and busy[0][0]<=t:
   _,slot=heapq.heappop(busy);free.append(slot)
  vis=[x for x in accepted[cid] if x['arrival_epoch']<=q];pending=sum(x['arrival_epoch']>q for x in accepted[cid]);assert len(vis)==int(z['input_visible_count']) and pending==int(z['input_pending_count'])
  score=None
  if any(float(x['capacityAh'])<=.20 for x in vis):reason='known_event'
  elif not free:reason='station_busy'
  elif len(vis)<3:reason='admit_warmup_fallback'
  else:score=(q-float(vis[-1]['stop_epoch']))/WEEK;reason='admit' if score>=thresholds[M] else 'below_age_threshold'
  assert z['reason']==reason and (z['admitted']=='True')==reason.startswith('admit')
  if score is None:assert not z['input_staleness_weeks']
  else:assert abs(score-float(z['input_staleness_weeks']))<1e-10
  if reason.startswith('admit'):
   stop=float(row['stop_epoch']);slot=min(free);free.remove(slot);heapq.heappush(busy,(stop-data[cid]['warm']+float(fleet['offset_seconds'][cid]),slot));accepted[cid].append(report(row));slot_checks+=1
   assert int(z['station_slot'])==slot and abs(float(z['source_stop_epoch_if_admitted'])-stop)<1e-6 and abs(float(z['actual_station_hours'])-(stop-q)/3600.)<1e-8 and abs(float(z['arrival_epoch_if_admitted'])-(stop+14*DAY))<1e-6 and len(busy)<=M
  decision_checks+=1
 allaccepted[world]=accepted
paired=collections.defaultdict(list);matching_visibility=0
for z in pred:
 M=int(z['stations']);cid=z['cell_id'];q=float(z['query_epoch']);ref=old[(M,cid,q)];event=data[cid]['event'];vis=[x for x in allaccepted[z['world']][cid] if start(x)<=q and x['arrival_epoch']<=q];pending=sum(start(x)<=q and x['arrival_epoch']>q for x in allaccepted[z['world']][cid]);idx=[int(x['source_rpt_index']) for x in vis]
 assert idx==json.loads(z['visible_RPT_indices']) and len(vis)==int(z['visible_RPT_count']) and pending==int(z['input_pending_count'])
 assert (z['known_event']=='True')==any(float(x['capacityAh'])<=.20 for x in vis) and (z['primary_positive_rul']=='True')==(event is not None and q<event)
 assert z['source_event_epoch']==ref['source_event_epoch'] and z['target_rul_weeks']==ref['target_rul_weeks'] and z['primary_positive_rul']==ref['primary_positive_rul']
 if event is not None:
  y=max(0.,(event-q)/WEEK);assert abs(float(z['target_rul_weeks'])-y)<1e-10 and abs(float(z['absolute_error'])-abs(float(z['point_proxy_RUL'])-y))<1e-10
 if idx==json.loads(ref['visible_RPT_indices']) and z['known_event']==ref['known_event']:
  assert float(z['point_proxy_RUL'])==float(ref['point_proxy_RUL']);matching_visibility+=1
 paired[(M,cid)].append((z,ref))
assert len(paired)==48
maxerr=0.
for x in pc:
 M=int(x['stations']);rs=paired[(M,x['cell_id'])];positive=[(z,a) for z,a in rs if z['primary_positive_rul']=='True'];scored=[(z,a) for z,a in rs if z['absolute_error']];post=[(z,a) for z,a in rs if z['source_event_epoch'] and float(z['query_epoch'])>=float(z['source_event_epoch'])]
 assert len(rs)==int(x['n_queries']) and len(positive)==int(x['n_pre_event'])
 for name,vals in [('age_primary_MAE',[float(z['absolute_error']) for z,a in positive]),('pending_primary_MAE',[float(a['absolute_error']) for z,a in positive]),('age_all_MAE',[float(z['absolute_error']) for z,a in scored]),('pending_all_MAE',[float(a['absolute_error']) for z,a in scored])]:
  if vals:
   err=abs(float(x[name])-np.mean(vals));maxerr=max(maxerr,err);assert err<1e-10
  else:assert not x[name]
 if post:
  assert (x['age_confirmed_by_last_post_query']=='True')==any(z['known_event']=='True' for z,a in post) and (x['pending_confirmed_by_last_post_query']=='True')==any(a['known_event']=='True' for z,a in post)
for x in summary:
 M=int(x['stations']);cells=[z for z in pc if int(z['stations'])==M];ds=[z for z in jobs if int(z['stations'])==M];ref=next(z for z in oldsum if int(z['stations'])==M);v=[float(z['pending_primary_MAE'])-float(z['age_primary_MAE']) for z in cells if z['age_primary_MAE']]
 agehours=sum(float(z['actual_station_hours']) for z in ds if z['admitted']=='True');pendinghours=float(ref['station_hours']);assert abs(float(x['age_station_hours'])-agehours)<1e-7 and abs(float(x['pending_station_hours'])-pendinghours)<1e-7 and abs(float(x['age_relative_hours_minus_pending'])-(agehours-pendinghours)/pendinghours)<1e-10
 assert abs(float(x['pending_minus_age_MAE'])-float(np.mean(v)))<1e-10 and abs(float(x['worst_cell_delta_MAE'])-max(v))<1e-10 and int(x['pending_better_cells'])==sum(z< -1e-9 for z in v) and int(x['pending_worse_cells'])==sum(z>1e-9 for z in v)
 post=[z for z in cells if z['age_confirmed_by_last_post_query']];assert int(x['cells_with_post_queries'])==len(post) and int(x['age_unconfirmed_at_last_post_query'])==sum(z['age_confirmed_by_last_post_query']=='False' for z in post) and int(x['pending_unconfirmed_at_last_post_query'])==sum(z['pending_confirmed_by_last_post_query']=='False' for z in post)
result=dict(status='PASS',new_fits=0,new_inference_rows=0,C3_payload_reads=0,C4_payload_reads=0,training_calibration_worlds_recomputed=24,training_cells=24,held_cells=24,held_decisions_checked=decision_checks,held_station_allocations_checked=slot_checks,common_query_pairs_checked=len(pred),same_visible_input_equal_prediction_checks=matching_visibility,max_per_cell_MAE_recomputation_error=maxerr,age_thresholds_weeks=thresholds,limits=['Post-hoc comparator, calibrated on training fleet only after earlier held outcomes were inspected.','Same available stations; actual station hours differ, so not strictly equal-cost.','Single coupled fleet per population; no independent-fleet confidence interval.','Proxy excludes full event distribution, false-alarm metrics, real report delays and censored-label adaptation.'],input_sha256={str(p.relative_to(R)):sha(p) for p in [CAL/'grid.csv',CAL/'CALIBRATED.json',CAL/'receipt.json',D/'age_decisions.csv',D/'age_predictions.csv',D/'paired_per_cell.csv',D/'summary.csv',D/'receipt.json',FIRST/'INDEPENDENT_RECOMPUTE.json']})
with (D/'INDEPENDENT_RECOMPUTE.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps(result,ensure_ascii=False))
