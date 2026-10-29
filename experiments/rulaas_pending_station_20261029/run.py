#!/usr/bin/env python3
"""Finite recorded-window pending-aware admission comparison, no model fitting."""
import os
os.environ['OMP_NUM_THREADS']='4';os.environ['MKL_NUM_THREADS']='4'
import pathlib,sys,json,csv,hashlib,datetime,time,collections,fcntl,traceback,argparse,heapq
import numpy as np
R=pathlib.Path('/home/yndx/zxk/rul');H=R/'experiments/rulaas_pending_station_20261029';OLD=R/'experiments/rulaas_gain_identifiability_20261029/run02';OOF=R/'experiments/rulaas_gain_oof_repair_20261029/run01';FORMAL=R/'experiments/multisource_factorial_20261021/run2_clocksafe';SIG=R/'reports/multisource_20261021_signals'
OWNER='01a17810-6ae6-7cf2-9729-5bfcaa8df5f4';DAY=86400.;WEEK=604800.;LAG=14.;MAXSTALE=3.426952600479126;POLICIES=('all','age','age_no_pending')
sys.path[:0]=[str(R/'experiments/rulaas_value_gate_20261029'),str(R/'experiments/multisource_factorial_20261021'),str(SIG),str(R/'experiments/isu_irregular_rul_seed42_v1'),str(R/'experiments/dart_rul_v18')]
from value_gate import vector,MemoCycle
from data_adapter import load_reviewed_cell
import cycle_asof_features as C
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def readj(p):return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def writej(p,x):
 with pathlib.Path(p).open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def csvout(p,rows):
 if not rows:raise ValueError('empty artifact '+str(p))
 with pathlib.Path(p).open('x',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def prog(out,x):
 p=out/'progress.tmp';p.write_text(json.dumps(x,ensure_ascii=False),encoding='utf-8');os.replace(p,out/'progress.json')
def start(row):return datetime.datetime.fromisoformat(row['start']).timestamp()
def reported(row):return dict(row,arrival_epoch=float(row['stop_epoch'])+LAG*DAY)
def main(go_path):
 g=readj(go_path);out=R/g['output'];started=time.time();locks=[]
 rec=dict(status='STARTED',request_id=g['request_id'],started_utc=stamp(),new_fits=0,model_prediction_rows=0,source_train_cells_read=0,C3_payload_reads=0,C4_payload_reads=0,actual_coordinator_model_recorded=g['actual_model'],hypothetical_delay_days=LAG)
 try:
  for p in [R/'automation/state/coordinator.lock',R/'automation/locks/isu_irregular_rul_cpu.lock']:
   f=p.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  c=readj(R/'automation/state/coordinator.json');hb=datetime.datetime.fromisoformat(c['heartbeat_utc'].replace('Z','+00:00'))
  if c.get('state')!='ACTIVE' or c.get('owner')!=OWNER or c.get('thread_id')!=OWNER or (datetime.datetime.now(datetime.timezone.utc)-hb).total_seconds()>1800:raise ValueError('owner or heartbeat')
  if g.get('status')!='APPROVED' or g.get('owner')!=OWNER or g.get('allow_fits') is not False or g.get('allow_C3') is not False or g.get('allow_C4') is not False:raise ValueError('GO')
  if g['model_row_cap']!=12000 or g['source_cell_cap']!=48 or g['hypothetical_delay_days']!=14 or g['capacities']!=[2,4] or g['policies']!=list(POLICIES):raise ValueError('protocol budget')
  for rel,h in g['input_sha256'].items():
   if sha(R/rel)!=h:raise ValueError('input hash '+rel)
  if out.parent!=H or out.exists():raise ValueError('create-only output')
  writej(H/(g['request_id']+'.claim.json'),dict(GO_sha256=sha(go_path),utc=stamp()));out.mkdir();prog(out,rec)
  split=readj(OLD/'cell_split.json');folds=readj(OOF/'fold_manifest.json')['folds'];audit=readj(OOF/'INDEPENDENT_RECOMPUTE.json')
  if audit['status']!='PASS':raise ValueError('oof audit')
  fit=set(split['base_head_fit_cells']);held=set(split['base_head_unseen_cells'])
  if len(fit)!=60 or len(held)!=60 or fit&held:raise ValueError('fit/held split')
  with (FORMAL/'train_targets.jsonl').open(encoding='utf-8') as f:meta=[json.loads(x) for x in f]
  X=np.load(FORMAL/'train_features.npz',allow_pickle=False)['F3'];ids=np.asarray([z['cell_id'] for z in meta])
  if X.shape!=(len(meta),710):raise ValueError('threshold feature shape')
  mask=np.isin(ids,list(fit)) & (X[:,1]>.8) & np.isfinite(X[:,6])
  if set(ids[mask])!=fit or set(ids[mask])&held:raise ValueError('threshold split')
  age_threshold=float(np.quantile(X[mask,6],.95))
  if not np.isclose(age_threshold,1.3254277288913727,rtol=0,atol=1e-12):raise ValueError('training threshold mismatch')
  writej(out/'train_only_threshold.json',dict(age_weeks=age_threshold,quantile=.95,training_cells=sorted(fit),training_rows=int(mask.sum()),held_cells_excluded=len(held),health_filter='latest visible capacity fraction > 0.8',uses_lifetime_labels=False,new_fits=0))
  del X,meta,ids,mask
  import joblib
  models=[joblib.load(OOF/('nested_head_'+str(i)+'.joblib')) for i in range(3)];heldmodel=joblib.load(FORMAL/'hgb_F3_oof0.joblib')
  orig=readj(OLD/'receipt.json');sources=collections.defaultdict(dict)
  for z in orig['source_files']:sources[z['cell_id']][z['kind']]=z
  cells={};source_files=[];queries={};offsets={};worlds=[];all_decisions=[];views=[]
  for population,selected in [('kernel_fit',split['selected_kernel_fit']),('kernel_held',split['selected_kernel_held'])]:
   rng=np.random.RandomState(42)
   for cid in sorted(selected):offsets[cid]=float(rng.uniform(0.,14*DAY))
   for cid in sorted(selected):
    if not cid.endswith(('C1','C2')) or set(sources[cid])!={'DataV2','RPT','Cycling'}:raise ValueError('source role')
    fi=next((i for i,f in enumerate(folds) if cid in set(f['excluded_oof_cells'])),None) if population=='kernel_fit' else -1
    if population=='kernel_fit' and (fi is None or cid not in fit or cid in set(folds[fi]['train_cells'])):raise ValueError('oof leak')
    if population=='kernel_held' and (cid not in held or cid in fit):raise ValueError('held leak')
    src=sources[cid]
    for kind in ['DataV2','RPT','Cycling']:
     p=R/src[kind]['path']
     if 'C3' in p.name or 'C4' in p.name or sha(p)!=src[kind]['sha256']:raise ValueError('source hash')
     source_files.append(dict(cell_id=cid,kind=kind,path=src[kind]['path'],sha256=src[kind]['sha256']))
    cell=load_reviewed_cell(R/src['DataV2']['path'],'train');rows=sorted(cell['records'],key=lambda z:float(z['stop_epoch']))
    if cell['cell_id']!=cid or len(rows)<3:raise ValueError('cell or warmup')
    for a,b in zip(rows,rows[1:]):
     if start(b)<float(a['stop_epoch']):raise ValueError('overlapping per-cell windows')
    warm=float(rows[2]['stop_epoch']);end=float(rows[-1]['stop_epoch']);q=[float(x) for x in np.arange(warm+14*DAY,end+1e-6,3.5*DAY)]
    if not q:raise ValueError('no common query support')
    event=next((float(z['stop_epoch']) for z in rows if float(z['capacityAh'])<=.20),None)
    cells[cid]=dict(cell=cell,rows=rows,warm=warm,end=end,event=event,population=population,fold=fi);queries[cid]=q;rec['source_train_cells_read']+=1
   if rec['source_train_cells_read']>g['source_cell_cap']:raise ValueError('source cap')
   timeline=[]
   for cid in sorted(selected):
    c=cells[cid];warm=c['warm'];off=offsets[cid]
    for q in queries[cid]:timeline.append((q-warm+off,1,cid,q,-1))
    for i,row in enumerate(c['rows']):
     if i>=3:
      q=start(row);timeline.append((q-warm+off,0,cid,q,i))
   timeline.sort();popworld=[]
   for M in [2,4]:
    for policy in POLICIES:
     popworld.append(dict(name=population+'_M'+str(M)+'_'+policy,population=population,M=M,policy=policy,accepted={cid:[reported(z) for z in cells[cid]['rows'][:3]] for cid in selected},busy=[],free=list(range(M)),max_concurrent=0))
   for eventno,(t,kind,cid,q,i) in enumerate(timeline):
    d=cells[cid]
    for w in popworld:
     while w['busy'] and w['busy'][0][0]<=t:
      stop,slot=heapq.heappop(w['busy']);w['free'].append(slot)
     accepted=w['accepted'][cid];visible=[z for z in accepted if float(z['arrival_epoch'])<=q]
     pending=sum(float(z['arrival_epoch'])>q for z in accepted)
     if kind==0:
      score=None;reason=None
      if any(float(z['capacityAh'])<=.20 for z in visible):reason='known_event'
      elif not w['free']:reason='station_busy'
      elif len(visible)<3:reason='admit_warmup_fallback'
      elif w['policy']=='all':reason='admit'
      else:
       score=(q-float(visible[-1]['stop_epoch']))/WEEK
       if score<age_threshold:reason='below_age_threshold'
       elif w['policy']=='age_no_pending' and pending>0:reason='pending_report'
       else:reason='admit'
      admit=reason.startswith('admit');row=d['rows'][i];hours=None;slot=None;stop=None
      if admit:
       stop=float(row['stop_epoch']);duration=stop-q
       if duration<=0:raise ValueError('nonpositive duration')
       slot=min(w['free']);w['free'].remove(slot);heapq.heappush(w['busy'],(stop-d['warm']+offsets[cid],slot));accepted.append(reported(row));hours=duration/3600.
       w['max_concurrent']=max(w['max_concurrent'],len(w['busy']))
       if len(w['busy'])>w['M'] or len(w['free'])+len(w['busy'])!=w['M']:raise ValueError('resource conservation')
      all_decisions.append(dict(world=w['name'],population=population,stations=w['M'],policy=w['policy'],cell_id=cid,source_rpt_index=row['source_rpt_index'],source_request_epoch=q,fleet_request_seconds=t,admitted=admit,reason=reason,input_visible_count=len(visible),input_pending_count=pending,input_staleness_weeks=score,actual_station_hours=hours,station_slot=slot,source_stop_epoch_if_admitted=stop,arrival_epoch_if_admitted=stop+LAG*DAY if stop is not None else None))
     else:
      if len(visible)<3:raise ValueError('query lacks common initialization')
      if any(float(z['arrival_epoch'])>q for z in visible):raise ValueError('future report visible')
      views.append(dict(world=w['name'],population=population,stations=w['M'],policy=w['policy'],cell_id=cid,query_epoch=q,fleet_query_seconds=t,visible=visible,visible_RPT_indices=[int(z['source_rpt_index']) for z in visible],input_pending_count=pending,known_event=any(float(z['capacityAh'])<=.20 for z in visible)))
    if eventno%200==0:prog(out,dict(rec,phase='ADMISSION_REPLAY',population=population,events_completed=eventno+1,total_events=len(timeline),query_views=len(views)))
   worlds.extend(popworld)
  if rec['source_train_cells_read']!=48:raise ValueError('cell count')
  bycell=collections.defaultdict(list)
  for z in views:bycell[z['cell_id']].append(z)
  predictions=[]
  for j,cid in enumerate(sorted(cells),1):
   d=cells[cid];src=sources[cid];rpt=readj(R/src['RPT']['path']);cycle=MemoCycle(C.build_cycle_index(R/src['Cycling']['path']))
   if rpt['role']!='train' or rpt['cell_id']!=cid or cycle.role!='train' or cycle.cell_id!=cid:raise ValueError('derived identity')
   cache={cid:{int(z['source_rpt_index']):z for z in rpt['records']}};model=models[d['fold']] if d['fold']>=0 else heldmodel
   unique={};matrix=[]
   for z in bycell[cid]:
    if z['known_event']:continue
    key=(z['query_epoch'],tuple(z['visible_RPT_indices']))
    if key not in unique:unique[key]=len(matrix);matrix.append(vector(d['cell'],z['visible'],z['query_epoch'],cache,cycle))
   if rec['model_prediction_rows']+len(matrix)>g['model_row_cap']:raise ValueError('prediction cap')
   if matrix:
    pred=np.exp(model.predict(np.asarray(matrix,float)));rec['model_prediction_rows']+=len(matrix)
    if not np.isfinite(pred).all():raise ValueError('nonfinite no clipping')
   else:pred=np.asarray([])
   for z in bycell[cid]:
    q=z['query_epoch'];event=d['event'];known=z['known_event'];point=0. if known else float(pred[unique[(q,tuple(z['visible_RPT_indices']))]])
    y=None if event is None else max(0.,(event-q)/WEEK);primary=event is not None and q<event
    stale=(q-float(z['visible'][-1]['stop_epoch']))/WEEK
    predictions.append(dict(world=z['world'],population=z['population'],stations=z['stations'],policy=z['policy'],cell_id=cid,query_epoch=q,fleet_query_seconds=z['fleet_query_seconds'],source_event_epoch=event,target_rul_weeks=y,primary_positive_rul=primary,known_event=known,visible_RPT_count=len(z['visible']),visible_RPT_indices=json.dumps(z['visible_RPT_indices'],separators=(',',':')),input_pending_count=z['input_pending_count'],input_staleness_weeks=stale,input_stale_above_train_max=stale>MAXSTALE,point_proxy_RUL=point,absolute_error=None if y is None else abs(point-y)))
   prog(out,dict(rec,phase='BATCH_SCORING',cells_completed=j,query_views=len(views)))
  grouped=collections.defaultdict(list)
  for z in predictions:grouped[(z['world'],z['cell_id'])].append(z)
  per=[]
  for (world,cid),rr in sorted(grouped.items()):
   pos=[z for z in rr if z['primary_positive_rul']];allsc=[z for z in rr if z['absolute_error'] is not None];post=[z for z in rr if z['source_event_epoch'] is not None and z['query_epoch']>=z['source_event_epoch']]
   detected=[z for z in post if z['known_event']];delay=(min(z['query_epoch'] for z in detected)-post[0]['source_event_epoch'])/DAY if detected else None
   per.append(dict(world=world,population=rr[0]['population'],stations=rr[0]['stations'],policy=rr[0]['policy'],cell_id=cid,n_queries=len(rr),n_pre_event=len(pos),n_post_event=len(post),primary_MAE=float(np.mean([z['absolute_error'] for z in pos])) if pos else None,all_MAE=float(np.mean([z['absolute_error'] for z in allsc])) if allsc else None,known_event_by_last_post_query=bool(detected) if post else None,known_event_detection_delay_days=delay,stale_above_train_max_fraction=float(np.mean([z['input_stale_above_train_max'] for z in rr]))))
  summaries=[]
  for w in worlds:
   rr=[z for z in per if z['world']==w['name']];ds=[z for z in all_decisions if z['world']==w['name']];post=[z for z in rr if z['known_event_by_last_post_query'] is not None];pos=[z for z in rr if z['primary_MAE'] is not None];alls=[z for z in rr if z['all_MAE'] is not None]
   summaries.append(dict(world=w['name'],population=w['population'],stations=w['M'],policy=w['policy'],cells=len(rr),query_count=sum(z['n_queries'] for z in rr),primary_cells=len(pos),primary_MAE=float(np.mean([z['primary_MAE'] for z in pos])) if pos else None,all_MAE=float(np.mean([z['all_MAE'] for z in alls])) if alls else None,stale_above_train_max_cell_macro=float(np.mean([z['stale_above_train_max_fraction'] for z in rr])),opportunities=len(ds),admitted_tests=sum(z['admitted'] for z in ds),station_hours=float(sum(z['actual_station_hours'] for z in ds if z['admitted'])),busy_rejections=sum(z['reason']=='station_busy' for z in ds),age_rejections=sum(z['reason']=='below_age_threshold' for z in ds),pending_rejections=sum(z['reason']=='pending_report' for z in ds),known_event_skips=sum(z['reason']=='known_event' for z in ds),max_concurrent=w['max_concurrent'],cells_with_post_event_queries=len(post),cells_not_confirmed_at_last_post_query=sum(not z['known_event_by_last_post_query'] for z in post)))
  comparisons=[]
  for population in ['kernel_fit','kernel_held']:
   for M in [2,4]:
    by={(z['cell_id'],z['policy']):z for z in per if z['population']==population and z['stations']==M}
    ids=sorted({z['cell_id'] for z in per if z['population']==population and z['stations']==M})
    ds=[]
    for cid in ids:
     a=by[cid,'age'];b=by[cid,'age_no_pending']
     if a['n_queries']!=b['n_queries'] or a['n_pre_event']!=b['n_pre_event']:raise ValueError('unequal queries')
     if a['primary_MAE'] is not None:ds.append((cid,b['primary_MAE']-a['primary_MAE']))
    comparisons.append(dict(population=population,stations=M,candidate='age_no_pending',reference='age',paired_primary_cells=len(ds),cell_macro_delta_MAE=float(np.mean([x[1] for x in ds])),cells_improved=sum(x[1]<-1e-9 for x in ds),cells_unchanged=sum(abs(x[1])<=1e-9 for x in ds),cells_worse=sum(x[1]>1e-9 for x in ds),worst_cell=max(ds,key=lambda x:x[1])[0],worst_cell_delta=max(x[1] for x in ds),paired_uncertainty='Not estimated from a single coupled fleet.'))
  csvout(out/'predictions.csv',predictions);csvout(out/'decisions.csv',all_decisions);csvout(out/'per_cell.csv',per);csvout(out/'summary.csv',summaries);csvout(out/'comparisons.csv',comparisons)
  writej(out/'fleet_world.json',dict(seed=42,offset_seconds=offsets,report_lag_days=LAG,stations=[2,4],policies=list(POLICIES),warmup_RPTs_free=3,queue_waiting_for_physical_sampling=False,age_threshold=age_threshold,threshold_training_cells=60,threshold_held_cells_excluded=60))
  rec.update(status='SUCCESS',finished_utc=stamp(),elapsed_seconds=time.time()-started,GO_sha256=sha(go_path),query_views=len(predictions),decisions=len(all_decisions),source_files=source_files,input_sha256=g['input_sha256'],resource_conservation='PASS',common_queries_by_cell='PASS')
  writej(out/'receipt.json',rec);prog(out,rec)
  print(json.dumps(dict(status='SUCCESS',new_fits=0,model_rows=rec['model_prediction_rows'],query_views=len(predictions),elapsed_seconds=rec['elapsed_seconds'],summary=summaries,comparisons=comparisons),ensure_ascii=False))
 except BaseException as ex:
  rec.update(status='FAILED',error=repr(ex),traceback=traceback.format_exc(),finished_utc=stamp(),elapsed_seconds=time.time()-started)
  if out.is_dir() and not (out/'failure_receipt.json').exists():writej(out/'failure_receipt.json',rec)
  print(json.dumps(rec,ensure_ascii=False));raise
 finally:
  for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--go',required=True);main(pathlib.Path(a.parse_args().go))
