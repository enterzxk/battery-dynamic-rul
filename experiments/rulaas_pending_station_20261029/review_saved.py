#!/usr/bin/env python3
"""Independent saved-record replay audit, same-query and per-cell metrics."""
import pathlib,sys,json,csv,collections,heapq,datetime,math,hashlib
import numpy as np
R=pathlib.Path('/home/yndx/zxk/rul');D=R/'experiments/rulaas_pending_station_20261029/run01';OLD=R/'experiments/rulaas_gain_identifiability_20261029/run02'
sys.path.insert(0,str(R/'experiments/isu_irregular_rul_seed42_v1'));from data_adapter import load_reviewed_cell
DAY=86400.;WEEK=604800.;LAG=14.
def rows(p):
 with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def start(row):return datetime.datetime.fromisoformat(row['start']).timestamp()
def report(row):return dict(row,arrival_epoch=float(row['stop_epoch'])+LAG*DAY)
receipt=read(D/'receipt.json');fleet=read(D/'fleet_world.json');threshold=read(D/'train_only_threshold.json');dec=rows(D/'decisions.csv');pred=rows(D/'predictions.csv');per=rows(D/'per_cell.csv');summ=rows(D/'summary.csv');comparisons=rows(D/'comparisons.csv')
assert receipt['status']=='SUCCESS' and receipt['new_fits']==0 and receipt['C3_payload_reads']==receipt['C4_payload_reads']==0 and receipt['source_train_cells_read']==48
split=read(OLD/'cell_split.json');fit=set(split['base_head_fit_cells']);held=set(split['base_head_unseen_cells']);assert set(threshold['training_cells'])==fit and not fit&held and threshold['held_cells_excluded']==60
age=float(threshold['age_weeks']);assert abs(age-1.3254277288913727)<1e-12 and threshold['training_rows']==2504
orig=read(OLD/'receipt.json');src={z['cell_id']:z for z in orig['source_files'] if z['kind']=='DataV2'};all_ids=split['selected_kernel_fit']+split['selected_kernel_held'];data={}
for cid in all_ids:
 z=src[cid];p=R/z['path'];assert cid.endswith(('C1','C2')) and sha(p)==z['sha256'];cell=load_reviewed_cell(p,'train');rs=sorted(cell['records'],key=lambda x:float(x['stop_epoch']))
 assert cell['cell_id']==cid and len(rs)>=3 and all(start(b)>=float(a['stop_epoch']) for a,b in zip(rs,rs[1:]))
 data[cid]=dict(rows=rs,byid={int(x['source_rpt_index']):x for x in rs},warm=float(rs[2]['stop_epoch']),event=next((float(x['stop_epoch']) for x in rs if float(x['capacityAh'])<=.20),None))
decby=collections.defaultdict(list)
for z in dec:decby[z['world']].append(z)
acc={};policy_checks=0;slot_checks=0
for world,jobs in decby.items():
 pop=jobs[0]['population'];M=int(jobs[0]['stations']);policy=jobs[0]['policy'];selected=split['selected_kernel_fit'] if pop=='kernel_fit' else split['selected_kernel_held'];accepted={cid:[report(x) for x in data[cid]['rows'][:3]] for cid in selected};busy=[];free=list(range(M))
 for z in sorted(jobs,key=lambda x:(float(x['fleet_request_seconds']),x['cell_id'],float(x['source_request_epoch']),int(x['source_rpt_index']))):
  cid=z['cell_id'];q=float(z['source_request_epoch']);t=float(z['fleet_request_seconds']);row=data[cid]['byid'][int(z['source_rpt_index'])]
  assert abs(start(row)-q)<1e-6 and abs((q-data[cid]['warm']+fleet['offset_seconds'][cid])-t)<1e-6
  while busy and busy[0][0]<=t:
   _,slot=heapq.heappop(busy);free.append(slot)
  vis=[x for x in accepted[cid] if float(x['arrival_epoch'])<=q];pending=sum(float(x['arrival_epoch'])>q for x in accepted[cid])
  assert len(vis)==int(z['input_visible_count']) and pending==int(z['input_pending_count'])
  score=None
  if any(float(x['capacityAh'])<=.20 for x in vis):reason='known_event'
  elif not free:reason='station_busy'
  elif len(vis)<3:reason='admit_warmup_fallback'
  elif policy=='all':reason='admit'
  else:
   score=(q-float(vis[-1]['stop_epoch']))/WEEK
   if score<age:reason='below_age_threshold'
   elif policy=='age_no_pending' and pending>0:reason='pending_report'
   else:reason='admit'
  assert reason==z['reason'] and (z['admitted']=='True')==reason.startswith('admit')
  if score is None:assert z['input_staleness_weeks']==''
  else:assert abs(score-float(z['input_staleness_weeks']))<1e-10
  if reason.startswith('admit'):
   slot=min(free);free.remove(slot);stop=float(row['stop_epoch']);hours=(stop-q)/3600.
   assert int(z['station_slot'])==slot and abs(float(z['source_stop_epoch_if_admitted'])-stop)<1e-6 and abs(float(z['actual_station_hours'])-hours)<1e-8 and abs(float(z['arrival_epoch_if_admitted'])-(stop+LAG*DAY))<1e-6
   heapq.heappush(busy,(stop-data[cid]['warm']+fleet['offset_seconds'][cid],slot));accepted[cid].append(report(row));slot_checks+=1
   assert len(busy)<=M and len(free)+len(busy)==M
  else:assert not z['station_slot'] and not z['actual_station_hours']
  policy_checks+=1
 acc[world]=accepted
groups=collections.defaultdict(list);keys=collections.defaultdict(dict);points={};query_checks=0;maxerr=0.
for z in pred:
 world=z['world'];cid=z['cell_id'];q=float(z['query_epoch']);event=data[cid]['event'];known=z['known_event']=='True'
 vis=[x for x in acc[world][cid] if start(x)<=q and float(x['arrival_epoch'])<=q];pending=sum(start(x)<=q and float(x['arrival_epoch'])>q for x in acc[world][cid])
 ids=[int(x['source_rpt_index']) for x in vis];assert ids==json.loads(z['visible_RPT_indices']) and len(vis)==int(z['visible_RPT_count']) and pending==int(z['input_pending_count'])
 assert known==any(float(x['capacityAh'])<=.20 for x in vis)
 stale=(q-float(vis[-1]['stop_epoch']))/WEEK;assert abs(stale-float(z['input_staleness_weeks']))<1e-10 and (z['input_stale_above_train_max']=='True')==(stale>3.426952600479126)
 assert (z['primary_positive_rul']=='True')==(event is not None and q<event)
 if event is not None:
  assert abs(float(z['source_event_epoch'])-event)<1e-6;y=max(0.,(event-q)/WEEK);pt=float(z['point_proxy_RUL']);assert abs(float(z['target_rul_weeks'])-y)<1e-10 and abs(float(z['absolute_error'])-abs(pt-y))<1e-10
  if known:assert pt==0.
 else:assert not z['source_event_epoch'] and not z['target_rul_weeks'] and not z['absolute_error']
 k=(cid,q,tuple(ids),known);pt=float(z['point_proxy_RUL'])
 if k in points:assert points[k]==pt
 else:points[k]=pt
 groups[(world,cid)].append(z);keys[world][(cid,q)]=(event,float(z['target_rul_weeks']) if z['target_rul_weeks'] else None);query_checks+=1
for pop in ['kernel_fit','kernel_held']:
 worlds=sorted(w for w in keys if w.startswith(pop+'_'))
 assert len(worlds)==6 and all(keys[w]==keys[worlds[0]] for w in worlds)
for x in per:
 v=groups[(x['world'],x['cell_id'])];primary=[z for z in v if z['primary_positive_rul']=='True'];allscore=[z for z in v if z['absolute_error']];post=[z for z in v if z['source_event_epoch'] and float(z['query_epoch'])>=float(z['source_event_epoch'])];detected=[z for z in post if z['known_event']=='True']
 assert len(v)==int(x['n_queries']) and len(primary)==int(x['n_pre_event']) and len(post)==int(x['n_post_event'])
 for name,subset in [('primary_MAE',primary),('all_MAE',allscore)]:
  if subset:
   err=abs(float(x[name])-float(np.mean([float(z['absolute_error']) for z in subset])));maxerr=max(maxerr,err);assert err<1e-10
  else:assert not x[name]
 if post:
  assert (x['known_event_by_last_post_query']=='True')==bool(detected)
  if detected:assert abs(float(x['known_event_detection_delay_days'])-(min(float(z['query_epoch']) for z in detected)-float(post[0]['source_event_epoch']))/DAY)<1e-10
 else:assert not x['known_event_by_last_post_query']
 err=abs(float(x['stale_above_train_max_fraction'])-np.mean([z['input_stale_above_train_max']=='True' for z in v]));assert err<1e-10
for x in summ:
 world=x['world'];p=[z for z in per if z['world']==world];d=decby[world]
 assert int(x['cells'])==len(p) and int(x['query_count'])==sum(int(z['n_queries']) for z in p) and int(x['opportunities'])==len(d)
 assert int(x['admitted_tests'])==sum(z['admitted']=='True' for z in d) and int(x['pending_rejections'])==sum(z['reason']=='pending_report' for z in d) and int(x['busy_rejections'])==sum(z['reason']=='station_busy' for z in d)
 assert abs(float(x['station_hours'])-sum(float(z['actual_station_hours']) for z in d if z['admitted']=='True'))<1e-7
 for metric in ['primary_MAE','all_MAE']:
  vals=[float(z[metric]) for z in p if z[metric]]
  if vals:assert abs(float(x[metric])-float(np.mean(vals)))<1e-10
for c in comparisons:
 population=c['population'];M=int(c['stations']);p={(z['cell_id'],z['policy']):z for z in per if z['population']==population and int(z['stations'])==M};cells=sorted({z['cell_id'] for z in per if z['population']==population and int(z['stations'])==M});delta=[float(p[cid,'age_no_pending']['primary_MAE'])-float(p[cid,'age']['primary_MAE']) for cid in cells if p[cid,'age']['primary_MAE']]
 assert len(delta)==int(c['paired_primary_cells']) and abs(float(c['cell_macro_delta_MAE'])-float(np.mean(delta)))<1e-10 and abs(float(c['worst_cell_delta'])-max(delta))<1e-10
result=dict(status='PASS',new_fits=0,new_inference_rows=0,C3_payload_reads=0,C4_payload_reads=0,source_cells_checked=len(data),worlds_checked=len(decby),decisions_checked=policy_checks,station_allocations_checked=slot_checks,query_predictions_checked=query_checks,all_worlds_share_population_query_and_target_keys=True,resource_replay_and_visibility='PASS',same_visible_query_model_output_identity='PASS',max_per_cell_MAE_recomputation_error=maxerr,limits=['Hypothetical 14-day delay and one time-shifted fleet per population.','Equal available stations, not equal realized station hours.','Conditional point proxy without event probability or pre-event alarm metrics.','Held C1/C2 cells already used in development diagnosis; no independent paper confirmation.'],input_sha256={str(p.relative_to(R)):sha(p) for p in [D/'decisions.csv',D/'predictions.csv',D/'per_cell.csv',D/'summary.csv',D/'comparisons.csv',D/'fleet_world.json',D/'train_only_threshold.json',D/'receipt.json']})
with (D/'INDEPENDENT_RECOMPUTE.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps(result,ensure_ascii=False))
