#!/usr/bin/env python3
"""Held-fleet evaluation of train-calibrated age comparator vs frozen pending policy."""
import os
os.environ['OMP_NUM_THREADS']='4';os.environ['MKL_NUM_THREADS']='4'
import pathlib,sys,json,csv,hashlib,datetime,time,collections,fcntl,traceback,argparse,heapq
import numpy as np
R=pathlib.Path('/home/yndx/zxk/rul');H=R/'experiments/rulaas_pending_station_20261029';FIRST=H/'run01';CAL=H/'calibration01';OLD=R/'experiments/rulaas_gain_identifiability_20261029/run02';FORMAL=R/'experiments/multisource_factorial_20261021/run2_clocksafe';SIG=R/'reports/multisource_20261021_signals'
OWNER='01a17810-6ae6-7cf2-9729-5bfcaa8df5f4';DAY=86400.;WEEK=604800.;LAG=14.;MAXSTALE=3.426952600479126
sys.path[:0]=[str(R/'experiments/rulaas_value_gate_20261029'),str(R/'experiments/multisource_factorial_20261021'),str(SIG),str(R/'experiments/isu_irregular_rul_seed42_v1'),str(R/'experiments/dart_rul_v18')]
from value_gate import vector,MemoCycle
from data_adapter import load_reviewed_cell
import cycle_asof_features as C
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def readj(p):return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def writej(p,x):
 with pathlib.Path(p).open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def csvout(p,rs):
 if not rs:raise ValueError('empty artifact')
 with pathlib.Path(p).open('x',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
def prog(p,x):
 t=p/'progress.tmp';t.write_text(json.dumps(x,ensure_ascii=False),encoding='utf-8');os.replace(t,p/'progress.json')
def start(z):return datetime.datetime.fromisoformat(z['start']).timestamp()
def report(z):return dict(z,arrival_epoch=float(z['stop_epoch'])+LAG*DAY)
def main(gpath):
 g=readj(gpath);out=R/g['output'];t0=time.time();locks=[];rec=dict(status='STARTED',request_id=g['request_id'],started_utc=stamp(),new_fits=0,model_prediction_rows=0,held_source_cells_read=0,C3_payload_reads=0,C4_payload_reads=0,actual_coordinator_model_recorded=g['actual_model'])
 try:
  for p in [R/'automation/state/coordinator.lock',R/'automation/locks/isu_irregular_rul_cpu.lock']:
   f=p.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  c=readj(R/'automation/state/coordinator.json');hb=datetime.datetime.fromisoformat(c['heartbeat_utc'].replace('Z','+00:00'))
  if c.get('state')!='ACTIVE' or c.get('owner')!=OWNER or c.get('thread_id')!=OWNER or (datetime.datetime.now(datetime.timezone.utc)-hb).total_seconds()>1800:raise ValueError('owner or heartbeat')
  if g.get('status')!='APPROVED' or g.get('owner')!=OWNER or g.get('allow_fits') is not False or g.get('allow_C3') is not False or g.get('allow_C4') is not False or g['model_row_cap']!=2500 or g['source_cell_cap']!=24 or g['capacities']!=[2,4]:raise ValueError('GO')
  for name,h in g['input_sha256'].items():
   if sha(R/name)!=h:raise ValueError('input hash '+name)
  if out.parent!=H or out.exists():raise ValueError('create-only output')
  writej(H/(g['request_id']+'.claim.json'),dict(GO_sha256=sha(gpath),utc=stamp()));out.mkdir();prog(out,rec)
  cal=readj(CAL/'CALIBRATED.json');split=readj(OLD/'cell_split.json');fleet=readj(FIRST/'fleet_world.json');review=readj(FIRST/'INDEPENDENT_RECOMPUTE.json')
  if cal['status']!='TRAIN_ONLY_THRESHOLDS_FROZEN' or cal['uses_held_fleet_outcomes'] or review['status']!='PASS':raise ValueError('calibration or review')
  thresholds={int(x['stations']):float(x['age_threshold_weeks']) for x in cal['selected']}
  if thresholds!={2:2.75,4:3.25}:raise ValueError('threshold identity')
  selected=split['selected_kernel_held'];held=set(split['base_head_unseen_cells']);fit=set(split['base_head_fit_cells'])
  if len(selected)!=24 or not set(selected)<=held or set(selected)&fit:raise ValueError('held split')
  import joblib
  model=joblib.load(FORMAL/'hgb_F3_oof0.joblib');orig=readj(OLD/'receipt.json');sources=collections.defaultdict(dict)
  for z in orig['source_files']:sources[z['cell_id']][z['kind']]=z
  cells={};qs={};timeline=[];source_files=[]
  for cid in sorted(selected):
   src=sources[cid]
   if not cid.endswith(('C1','C2')) or set(src)!={'DataV2','RPT','Cycling'}:raise ValueError('source')
   for kind in ['DataV2','RPT','Cycling']:
    it=src[kind];p=R/it['path']
    if 'C3' in p.name or 'C4' in p.name or sha(p)!=it['sha256']:raise ValueError('source hash')
    source_files.append(dict(cell_id=cid,kind=kind,path=it['path'],sha256=it['sha256']))
   cell=load_reviewed_cell(R/src['DataV2']['path'],'train');rows=sorted(cell['records'],key=lambda z:float(z['stop_epoch']))
   if cell['cell_id']!=cid or len(rows)<3 or any(start(b)<float(a['stop_epoch']) for a,b in zip(rows,rows[1:])):raise ValueError('source overlap')
   warm=float(rows[2]['stop_epoch']);end=float(rows[-1]['stop_epoch']);queries=[float(x) for x in np.arange(warm+14*DAY,end+1e-6,3.5*DAY)]
   if not queries:raise ValueError('query support')
   event=next((float(z['stop_epoch']) for z in rows if float(z['capacityAh'])<=.20),None)
   cells[cid]=dict(cell=cell,rows=rows,warm=warm,event=event);qs[cid]=queries;off=float(fleet['offset_seconds'][cid])
   for q in queries:timeline.append((q-warm+off,1,cid,q,-1))
   for i,row in enumerate(rows):
    if i>=3:
     q=start(row);timeline.append((q-warm+off,0,cid,q,i))
   rec['held_source_cells_read']+=1
  if rec['held_source_cells_read']!=24:raise ValueError('cell cap')
  timeline.sort();worlds=[]
  for M in [2,4]:worlds.append(dict(name='kernel_held_M'+str(M)+'_age_matched_train',M=M,threshold=thresholds[M],accepted={cid:[report(z) for z in cells[cid]['rows'][:3]] for cid in selected},busy=[],free=list(range(M)),max_concurrent=0))
  jobs=[];views=[]
  for n,(t,kind,cid,q,i) in enumerate(timeline):
   d=cells[cid]
   for w in worlds:
    while w['busy'] and w['busy'][0][0]<=t:
     _,slot=heapq.heappop(w['busy']);w['free'].append(slot)
    accepted=w['accepted'][cid];vis=[z for z in accepted if float(z['arrival_epoch'])<=q];pending=sum(float(z['arrival_epoch'])>q for z in accepted)
    if kind==0:
     score=None
     if any(float(z['capacityAh'])<=.20 for z in vis):reason='known_event'
     elif not w['free']:reason='station_busy'
     elif len(vis)<3:reason='admit_warmup_fallback'
     else:
      score=(q-float(vis[-1]['stop_epoch']))/WEEK;reason='admit' if score>=w['threshold'] else 'below_age_threshold'
     admit=reason.startswith('admit');row=d['rows'][i];hours=None;stop=None;slot=None
     if admit:
      stop=float(row['stop_epoch']);duration=stop-q
      if duration<=0:raise ValueError('duration')
      slot=min(w['free']);w['free'].remove(slot);heapq.heappush(w['busy'],(stop-d['warm']+fleet['offset_seconds'][cid],slot));accepted.append(report(row));hours=duration/3600.;w['max_concurrent']=max(w['max_concurrent'],len(w['busy']))
      if len(w['busy'])>w['M'] or len(w['busy'])+len(w['free'])!=w['M']:raise ValueError('resources')
     jobs.append(dict(world=w['name'],stations=w['M'],cell_id=cid,source_rpt_index=row['source_rpt_index'],source_request_epoch=q,fleet_request_seconds=t,admitted=admit,reason=reason,input_visible_count=len(vis),input_pending_count=pending,input_staleness_weeks=score,threshold_weeks=w['threshold'],actual_station_hours=hours,station_slot=slot,source_stop_epoch_if_admitted=stop,arrival_epoch_if_admitted=stop+LAG*DAY if stop is not None else None))
    else:
     if len(vis)<3 or any(float(z['arrival_epoch'])>q for z in vis):raise ValueError('query visibility')
     views.append(dict(world=w['name'],stations=w['M'],cell_id=cid,query_epoch=q,fleet_query_seconds=t,visible=vis,visible_RPT_indices=[int(z['source_rpt_index']) for z in vis],input_pending_count=pending,known_event=any(float(z['capacityAh'])<=.20 for z in vis)))
   if n%200==0:prog(out,dict(rec,phase='REPLAY',events_completed=n+1,total_events=len(timeline)))
  bycell=collections.defaultdict(list)
  for z in views:bycell[z['cell_id']].append(z)
  predictions=[]
  for n,cid in enumerate(sorted(selected),1):
   d=cells[cid];src=sources[cid];rpt=readj(R/src['RPT']['path']);cycle=MemoCycle(C.build_cycle_index(R/src['Cycling']['path']))
   if rpt['role']!='train' or rpt['cell_id']!=cid or cycle.role!='train' or cycle.cell_id!=cid:raise ValueError('derived source')
   cache={cid:{int(z['source_rpt_index']):z for z in rpt['records']}};unique={};matrix=[]
   for z in bycell[cid]:
    if z['known_event']:continue
    key=(z['query_epoch'],tuple(z['visible_RPT_indices']))
    if key not in unique:unique[key]=len(matrix);matrix.append(vector(d['cell'],z['visible'],z['query_epoch'],cache,cycle))
   if rec['model_prediction_rows']+len(matrix)>g['model_row_cap']:raise ValueError('model cap')
   pred=np.exp(model.predict(np.asarray(matrix,float))) if matrix else np.asarray([]);rec['model_prediction_rows']+=len(matrix)
   if not np.isfinite(pred).all():raise ValueError('nonfinite no clipping')
   for z in bycell[cid]:
    q=z['query_epoch'];event=d['event'];known=z['known_event'];point=0. if known else float(pred[unique[(q,tuple(z['visible_RPT_indices']))]])
    y=None if event is None else max(0.,(event-q)/WEEK);primary=event is not None and q<event;stale=(q-float(z['visible'][-1]['stop_epoch']))/WEEK
    predictions.append(dict(world=z['world'],stations=z['stations'],cell_id=cid,query_epoch=q,fleet_query_seconds=z['fleet_query_seconds'],source_event_epoch=event,target_rul_weeks=y,primary_positive_rul=primary,known_event=known,visible_RPT_count=len(z['visible']),visible_RPT_indices=json.dumps(z['visible_RPT_indices'],separators=(',',':')),input_pending_count=z['input_pending_count'],input_staleness_weeks=stale,input_stale_above_train_max=stale>MAXSTALE,point_proxy_RUL=point,absolute_error=None if y is None else abs(point-y)))
   prog(out,dict(rec,phase='SCORING',cells_completed=n))
  # Saved candidate rows and costs are read only after thresholds have been frozen.
  old=[]
  with (FIRST/'predictions.csv').open(encoding='utf-8',newline='') as f:
   for z in csv.DictReader(f):
    if z['population']=='kernel_held' and z['policy']=='age_no_pending':old.append(z)
  oldsummary=[]
  with (FIRST/'summary.csv').open(encoding='utf-8',newline='') as f:
   for z in csv.DictReader(f):
    if z['population']=='kernel_held' and z['policy']=='age_no_pending':oldsummary.append(z)
  if len(old)!=len(predictions) or len(oldsummary)!=2:raise ValueError('saved candidate rows')
  oldmap={(int(z['stations']),z['cell_id'],float(z['query_epoch'])):z for z in old}
  if len(oldmap)!=len(old):raise ValueError('duplicate saved candidate keys')
  pairs=collections.defaultdict(list)
  for z in predictions:
   key=(z['stations'],z['cell_id'],z['query_epoch']);a=oldmap.get(key)
   if a is None or bool(z['primary_positive_rul'])!=(a['primary_positive_rul']=='True') or str(z['source_event_epoch'])!=a['source_event_epoch'] or str(z['target_rul_weeks'])!=a['target_rul_weeks']:raise ValueError('candidate target mismatch')
   pairs[(z['stations'],z['cell_id'])].append((z,a))
  per=[]
  for (M,cid),rs in sorted(pairs.items()):
   positive=[(z,a) for z,a in rs if z['primary_positive_rul']];allsc=[(z,a) for z,a in rs if z['absolute_error'] is not None]
   post=[(z,a) for z,a in rs if z['source_event_epoch'] is not None and z['query_epoch']>=z['source_event_epoch']]
   matched_known=any(z['known_event'] for z,a in post);pending_known=any(a['known_event']=='True' for z,a in post)
   per.append(dict(stations=M,cell_id=cid,n_queries=len(rs),n_pre_event=len(positive),age_primary_MAE=float(np.mean([z['absolute_error'] for z,a in positive])) if positive else None,pending_primary_MAE=float(np.mean([float(a['absolute_error']) for z,a in positive])) if positive else None,age_all_MAE=float(np.mean([z['absolute_error'] for z,a in allsc])) if allsc else None,pending_all_MAE=float(np.mean([float(a['absolute_error']) for z,a in allsc])) if allsc else None,age_confirmed_by_last_post_query=matched_known if post else None,pending_confirmed_by_last_post_query=pending_known if post else None,age_stale_above_train_max_fraction=float(np.mean([z['input_stale_above_train_max'] for z,a in rs])),pending_stale_above_train_max_fraction=float(np.mean([a['input_stale_above_train_max']=='True' for z,a in rs]))))
  summaries=[]
  for w in worlds:
   M=w['M'];pp=[z for z in per if z['stations']==M];pos=[z for z in pp if z['age_primary_MAE'] is not None];post=[z for z in pp if z['age_confirmed_by_last_post_query'] is not None];ds=[z for z in jobs if z['stations']==M];oldsum=next(z for z in oldsummary if int(z['stations'])==M);agehours=float(sum(z['actual_station_hours'] for z in ds if z['admitted']));pendinghours=float(oldsum['station_hours']);d=[z['pending_primary_MAE']-z['age_primary_MAE'] for z in pos]
   summaries.append(dict(stations=M,held_cells=len(pp),common_queries=sum(z['n_queries'] for z in pp),age_threshold_weeks=w['threshold'],age_admitted_tests=sum(z['admitted'] for z in ds),pending_admitted_tests=int(oldsum['admitted_tests']),age_station_hours=agehours,pending_station_hours=pendinghours,age_relative_hours_minus_pending=(agehours-pendinghours)/pendinghours,age_primary_MAE=float(np.mean([z['age_primary_MAE'] for z in pos])),pending_primary_MAE=float(np.mean([z['pending_primary_MAE'] for z in pos])),pending_minus_age_MAE=float(np.mean(d)),pending_better_cells=sum(x< -1e-9 for x in d),pending_equal_cells=sum(abs(x)<=1e-9 for x in d),pending_worse_cells=sum(x>1e-9 for x in d),worst_cell=pos[int(np.argmax(d))]['cell_id'],worst_cell_delta_MAE=max(d),age_unconfirmed_at_last_post_query=sum(not z['age_confirmed_by_last_post_query'] for z in post),pending_unconfirmed_at_last_post_query=sum(not z['pending_confirmed_by_last_post_query'] for z in post),cells_with_post_queries=len(post),age_stale_above_train_max_cell_macro=float(np.mean([z['age_stale_above_train_max_fraction'] for z in pp])),pending_stale_above_train_max_cell_macro=float(np.mean([z['pending_stale_above_train_max_fraction'] for z in pp])),max_concurrent=w['max_concurrent'],strict_equal_cost=False,within_10pct_hours=abs((agehours-pendinghours)/pendinghours)<=.1,comparison_note='Post-hoc comparator selected on training fleet only; common capacity and queries; actual station hours differ.'))
  csvout(out/'age_predictions.csv',predictions);csvout(out/'age_decisions.csv',jobs);csvout(out/'paired_per_cell.csv',per);csvout(out/'summary.csv',summaries)
  rec.update(status='SUCCESS',finished_utc=stamp(),elapsed_seconds=time.time()-t0,GO_sha256=sha(gpath),age_prediction_rows=len(predictions),frozen_candidate_rows=len(old),common_query_and_target_keys='PASS',source_files=source_files,input_sha256=g['input_sha256'])
  writej(out/'receipt.json',rec);prog(out,rec);print(json.dumps(dict(status='SUCCESS',new_fits=0,model_rows=rec['model_prediction_rows'],age_prediction_rows=len(predictions),elapsed_seconds=rec['elapsed_seconds'],summary=summaries),ensure_ascii=False))
 except BaseException as ex:
  rec.update(status='FAILED',error=repr(ex),traceback=traceback.format_exc(),finished_utc=stamp(),elapsed_seconds=time.time()-t0)
  if out.is_dir() and not (out/'failure_receipt.json').exists():writej(out/'failure_receipt.json',rec)
  print(json.dumps(rec,ensure_ascii=False));raise
 finally:
  for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--go',required=True);main(pathlib.Path(a.parse_args().go))
