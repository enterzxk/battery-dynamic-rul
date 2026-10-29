#!/usr/bin/env python3
"""Frozen pending/age rules on three disjoint C3 development fleets; no fits."""
import os
os.environ['OMP_NUM_THREADS']='4';os.environ['MKL_NUM_THREADS']='4'
import pathlib,sys,json,csv,hashlib,datetime,time,collections,fcntl,traceback,argparse,heapq,copy,math
import numpy as np
R=pathlib.Path('/home/yndx/zxk/rul');H=R/'experiments/rulaas_c3_fleets_20261029';FORMAL=R/'experiments/multisource_factorial_20261021/run2_clocksafe';SIG=R/'reports/multisource_20261021_signals';CAL=R/'experiments/rulaas_pending_station_20261029/calibration01';OWNER='01a17810-6ae6-7cf2-9729-5bfcaa8df5f4'
DAY=86400.;WEEK=604800.;LAG=14.;MAXSTALE=3.426952600479126;GUARD_AGE=1.3254277288913727;POLICIES=('all','age_calibrated','age_no_pending')
sys.path[:0]=[str(R/'experiments/rulaas_value_gate_20261029'),str(R/'experiments/multisource_factorial_20261021'),str(SIG),str(R/'experiments/isu_irregular_rul_seed42_v1'),str(R/'experiments/dart_rul_v18')]
from value_gate import vector,MemoCycle,metrics
from data_adapter import load_reviewed_cell
import cycle_asof_features as C
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def readj(p):return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def writej(p,x):
 with pathlib.Path(p).open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def csvout(p,rs):
 if not rs:return
 with pathlib.Path(p).open('x',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
def prog(p,x):
 t=p/'progress.tmp';t.write_text(json.dumps(x,ensure_ascii=False),encoding='utf-8');os.replace(t,p/'progress.json')
def start(z):return datetime.datetime.fromisoformat(z['start']).timestamp()
def report(z):return dict(z,arrival_epoch=float(z['stop_epoch'])+LAG*DAY)
def main(gpath):
 g=readj(gpath);out=R/g['output'];t0=time.time();locks=[]
 rec=dict(status='STARTED',request_id=g['request_id'],started_utc=stamp(),new_fits=0,model_prediction_rows=0,C3_source_cells_read=0,C3_logical_payload_loads=0,C4_payload_reads=0,actual_coordinator_model_recorded=g['actual_model'],hypothetical_report_delay_days=14)
 try:
  for p in [R/'automation/state/coordinator.lock',R/'automation/locks/isu_irregular_rul_cpu.lock']:
   f=p.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  c=readj(R/'automation/state/coordinator.json');hb=datetime.datetime.fromisoformat(c['heartbeat_utc'].replace('Z','+00:00'))
  if c.get('state')!='ACTIVE' or c.get('owner')!=OWNER or c.get('thread_id')!=OWNER or (datetime.datetime.now(datetime.timezone.utc)-hb).total_seconds()>1800:raise ValueError('owner or heartbeat')
  if g.get('status')!='APPROVED' or g.get('owner')!=OWNER or g.get('allow_fits') is not False or g.get('allow_C3') is not True or g.get('allow_C4') is not False:raise ValueError('GO')
  if g['model_row_cap']!=25000 or g['source_cell_cap']!=63 or g['capacities']!=[2,4] or g['policies']!=list(POLICIES) or g['seed']!=42 or g['hypothetical_delay_days']!=14:raise ValueError('budget')
  for name,h in g['input_sha256'].items():
   if sha(R/name)!=h:raise ValueError('input hash '+name)
  if out.parent!=H or out.exists():raise ValueError('create-only output')
  writej(H/(g['request_id']+'.claim.json'),dict(GO_sha256=sha(gpath),utc=stamp()));out.mkdir();prog(out,rec)
  cal=readj(CAL/'CALIBRATED.json');review=readj(R/'experiments/rulaas_pending_station_20261029/age_comparator01/INDEPENDENT_RECOMPUTE.json')
  if cal['status']!='TRAIN_ONLY_THRESHOLDS_FROZEN' or cal['uses_held_fleet_outcomes'] or review['status']!='PASS':raise ValueError('calibration identity')
  thresholds={int(x['stations']):float(x['age_threshold_weeks']) for x in cal['selected']}
  if thresholds!={2:2.75,4:3.25}:raise ValueError('threshold drift')
  man=readj(R/'reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json');roles=readj(R/'reports/isu_ilcc_capacity_probe_20261020_root/cohort.json')['roles']
  ids=sorted(k for k,v in roles.items() if v=='development')
  if len(ids)!=63 or any(not cid.endswith('C3') for cid in ids) or len({cid.rsplit('C',1)[0] for cid in ids})!=63:raise ValueError('development cohort or groups')
  groups={cid:'F'+str(i%3+1) for i,cid in enumerate(ids)};rng=np.random.RandomState(42);offsets={cid:float(rng.uniform(0.,14*DAY)) for cid in ids}
  writej(out/'fleet_partition.json',dict(method='sorted development cell IDs round-robin into three fleets',seed=42,fleet_by_cell=groups,offset_seconds=offsets,cohort_role='development',C4_included=False,physical_cell_and_source_group_disjoint=True))
  ri={x['cell_id']:x for x in readj(SIG/'all188_rpt_features_v1/manifest.json')['inventory']};ci={x['cell_id']:x for x in readj(SIG/'cycling_all188_feature_manifest.json')['inventory']}
  import joblib
  clf=joblib.load(FORMAL/'hgb_F3_event.joblib');reg=joblib.load(FORMAL/'hgb_F3_positive.joblib');dist=joblib.load(FORMAL/'hgb_F3_distribution.joblib')
  residual=np.asarray(dist['residuals']);weights=np.asarray(dist['weights']);order=np.argsort(residual,kind='mergesort');residual=residual[order];weights=weights[order]
  if not np.isfinite(residual).all() or not np.isfinite(weights).all() or (weights<0).any() or abs(weights.sum()-1)>1e-8:raise ValueError('residual distribution')
  cum=np.cumsum(weights);cum[-1]=1.;expmean=float(np.dot(np.exp(residual),weights));one=int(np.flatnonzero(np.asarray(clf.classes_)==1)[0])
  cells={};queries={};excluded=[];source_files=[]
  for cid in ids:
   info=man['files'][cid];p=R/info['path']
   if info['role']!='development' or not p.name.startswith(cid) or 'C4' in p.name or sha(p)!=info['sha256']:raise ValueError('source role')
   source_files.append(dict(cell_id=cid,kind='DataV2',path=info['path'],sha256=info['sha256']));cell=load_reviewed_cell(p,'development');rec['C3_source_cells_read']+=1;rec['C3_logical_payload_loads']+=1
   rows=sorted(cell['records'],key=lambda z:float(z['stop_epoch']))
   if cell['cell_id']!=cid:raise ValueError('cell identity')
   if len(rows)<3:excluded.append(dict(cell_id=cid,fleet=groups[cid],reason='fewer_than_three_RPTs'));continue
   if any(start(b)<float(a['stop_epoch']) for a,b in zip(rows,rows[1:])):raise ValueError('overlapping per-cell windows')
   warm=float(rows[2]['stop_epoch']);end=float(rows[-1]['stop_epoch']);q=[float(x) for x in np.arange(warm+14*DAY,end+1e-6,3.5*DAY)]
   if not q:excluded.append(dict(cell_id=cid,fleet=groups[cid],reason='no_common_query_support'));continue
   for inv,kind in [(ri,'RPT'),(ci,'Cycling')]:
    item=inv[cid];p=R/item['path']
    if item['role']!='development' or 'C4' in p.name or sha(p)!=item['sha256']:raise ValueError('derived role')
    source_files.append(dict(cell_id=cid,kind=kind,path=item['path'],sha256=item['sha256']))
   event=next((float(z['stop_epoch']) for z in rows if float(z['capacityAh'])<=.20),None)
   cells[cid]=dict(cell=cell,rows=rows,warm=warm,end=end,event=event,fleet=groups[cid]);queries[cid]=q
  if rec['C3_source_cells_read']!=63 or not cells:raise ValueError('source cap')
  jobs=[];views=[];worlds=[]
  for fid in ['F1','F2','F3']:
   selected=sorted(cid for cid in cells if cells[cid]['fleet']==fid)
   if not selected:raise ValueError('empty fleet')
   timeline=[]
   for cid in selected:
    d=cells[cid]
    for q in queries[cid]:timeline.append((q-d['warm']+offsets[cid],1,cid,q,-1))
    for i,z in enumerate(d['rows']):
     if i>=3:
      q=start(z);timeline.append((q-d['warm']+offsets[cid],0,cid,q,i))
   timeline.sort();fw=[]
   for M in [2,4]:
    for policy in POLICIES:
     fw.append(dict(name=fid+'_M'+str(M)+'_'+policy,fleet=fid,M=M,policy=policy,accepted={cid:[report(z) for z in cells[cid]['rows'][:3]] for cid in selected},busy=[],free=list(range(M)),max_concurrent=0))
   for n,(t,kind,cid,q,i) in enumerate(timeline):
    d=cells[cid]
    for w in fw:
     while w['busy'] and w['busy'][0][0]<=t:
      _,slot=heapq.heappop(w['busy']);w['free'].append(slot)
     accepted=w['accepted'][cid];vis=[z for z in accepted if float(z['arrival_epoch'])<=q];pending=sum(float(z['arrival_epoch'])>q for z in accepted)
     if kind==0:
      score=None;threshold=None
      if any(float(z['capacityAh'])<=.20 for z in vis):reason='known_event'
      elif not w['free']:reason='station_busy'
      elif len(vis)<3:reason='admit_warmup_fallback'
      elif w['policy']=='all':reason='admit'
      else:
       score=(q-float(vis[-1]['stop_epoch']))/WEEK;threshold=thresholds[w['M']] if w['policy']=='age_calibrated' else GUARD_AGE
       if score<threshold:reason='below_age_threshold'
       elif w['policy']=='age_no_pending' and pending>0:reason='pending_report'
       else:reason='admit'
      admit=reason.startswith('admit');row=d['rows'][i];hours=None;stop=None;slot=None
      if admit:
       stop=float(row['stop_epoch']);duration=stop-q
       if duration<=0:raise ValueError('nonpositive duration')
       slot=min(w['free']);w['free'].remove(slot);heapq.heappush(w['busy'],(stop-d['warm']+offsets[cid],slot));accepted.append(report(row));hours=duration/3600.;w['max_concurrent']=max(w['max_concurrent'],len(w['busy']))
       if len(w['busy'])>w['M'] or len(w['busy'])+len(w['free'])!=w['M']:raise ValueError('resource conservation')
      jobs.append(dict(world=w['name'],fleet=fid,stations=w['M'],policy=w['policy'],cell_id=cid,source_rpt_index=row['source_rpt_index'],source_request_epoch=q,fleet_request_seconds=t,admitted=admit,reason=reason,input_visible_count=len(vis),input_pending_count=pending,input_staleness_weeks=score,threshold_weeks=threshold,actual_station_hours=hours,station_slot=slot,source_stop_epoch_if_admitted=stop,arrival_epoch_if_admitted=stop+LAG*DAY if stop is not None else None))
     else:
      if len(vis)<3 or any(float(z['arrival_epoch'])>q for z in vis):raise ValueError('query visibility')
      views.append(dict(world=w['name'],fleet=fid,stations=w['M'],policy=w['policy'],cell_id=cid,query_epoch=q,fleet_query_seconds=t,visible=vis,visible_RPT_indices=[int(z['source_rpt_index']) for z in vis],input_pending_count=pending,known_event=any(float(z['capacityAh'])<=.20 for z in vis)))
    if n%200==0:prog(out,dict(rec,phase='ADMISSION_REPLAY',fleet=fid,events_completed=n+1,total_events=len(timeline)))
   worlds.extend(fw)
  bycell=collections.defaultdict(list)
  for z in views:bycell[z['cell_id']].append(z)
  predictions=[];mutation=False
  for n,cid in enumerate(sorted(cells),1):
   d=cells[cid];rpt=readj(R/ri[cid]['path']);cycle=MemoCycle(C.build_cycle_index(R/ci[cid]['path']));rec['C3_logical_payload_loads']+=2
   if rpt['role']!='development' or rpt['cell_id']!=cid or cycle.role!='development' or cycle.cell_id!=cid:raise ValueError('derived identity')
   cache={cid:{int(z['source_rpt_index']):z for z in rpt['records']}};unique={};matrix=[]
   for z in bycell[cid]:
    if z['known_event']:continue
    key=(z['query_epoch'],tuple(z['visible_RPT_indices']))
    if key not in unique:
     x=vector(d['cell'],z['visible'],z['query_epoch'],cache,cycle);unique[key]=len(matrix);matrix.append(x)
     if not mutation:
      nonvis=set(cache[cid])-set(z['visible_RPT_indices']);mut=copy.deepcopy(cache);nmut=0
      for ix in nonvis:
       fr=mut[cid][ix]
       if isinstance(fr.get('values'),list):fr['values']=[-99999.]*len(fr['values']);nmut+=1
       elif isinstance(fr.get('values'),dict):fr['values']={k:-99999. for k in fr['values']};nmut+=1
      if nmut and not np.allclose(x,vector(d['cell'],z['visible'],z['query_epoch'],mut,cycle),rtol=0,atol=0,equal_nan=True):raise ValueError('unarrived input mutation')
      if nmut:mutation=True
   if rec['model_prediction_rows']+len(matrix)>g['model_row_cap']:raise ValueError('prediction cap')
   if matrix:
    X=np.asarray(matrix,float);p=clf.predict_proba(X)[:,one];mu=reg.predict(X);rec['model_prediction_rows']+=len(matrix)
    if not np.isfinite(p).all() or not np.isfinite(mu).all():raise ValueError('nonfinite output')
   else:p=mu=np.asarray([])
   for z in bycell[cid]:
    q=z['query_epoch'];event=d['event'];known=z['known_event'];k=None if known else unique[(q,tuple(z['visible_RPT_indices']))]
    point,lo,hi,b4=metrics(0. if known else float(mu[k]),1. if known else float(p[k]),known,residual,weights,cum,expmean)
    y=None if event is None else max(0.,(event-q)/WEEK);primary=event is not None and q<event
    label4=1 if event is not None and event<=q+4*WEEK else (0 if d['end']>=q+4*WEEK else None)
    stale=(q-float(z['visible'][-1]['stop_epoch']))/WEEK
    predictions.append(dict(world=z['world'],fleet=z['fleet'],stations=z['stations'],policy=z['policy'],cell_id=cid,query_epoch=q,fleet_query_seconds=z['fleet_query_seconds'],source_event_epoch=event,target_rul_weeks=y,primary_positive_rul=primary,known_event=known,visible_RPT_count=len(z['visible']),visible_RPT_indices=json.dumps(z['visible_RPT_indices'],separators=(',',':')),input_pending_count=z['input_pending_count'],input_staleness_weeks=stale,input_stale_above_train_max=stale>MAXSTALE,mean_RUL=point,q10=lo,q90=hi,p_RUL_le4w=b4,label4=label4,absolute_error=None if y is None else abs(point-y),coverage80=None if y is None else float(lo<=y<=hi),IS80=None if y is None else hi-lo+10*max(0.,lo-y)+10*max(0.,y-hi),Brier4=None if label4 is None else (b4-label4)**2))
   prog(out,dict(rec,phase='BATCH_SCORING',cells_completed=n,query_views=len(views)))
  if not mutation:raise ValueError('future-signal mutation not exercised')
  grouped=collections.defaultdict(list)
  for z in predictions:grouped[(z['world'],z['cell_id'])].append(z)
  per=[];episodes=[]
  for (world,cid),rr in sorted(grouped.items()):
   pos=[z for z in rr if z['primary_positive_rul']];allsc=[z for z in rr if z['absolute_error'] is not None];bs=[z for z in rr if z['Brier4'] is not None];neg=[z for z in rr if z['label4']==0];lead=[z for z in pos if z['target_rul_weeks']<=4.];post=[z for z in rr if z['source_event_epoch'] is not None and z['query_epoch']>=z['source_event_epoch']];det=[z for z in post if z['known_event']]
   per.append(dict(world=world,fleet=rr[0]['fleet'],stations=rr[0]['stations'],policy=rr[0]['policy'],cell_id=cid,n_queries=len(rr),n_primary=len(pos),n_Brier4=len(bs),n_censored4=sum(z['label4'] is None for z in rr),primary_MAE=float(np.mean([z['absolute_error'] for z in pos])) if pos else None,all_MAE=float(np.mean([z['absolute_error'] for z in allsc])) if allsc else None,primary_coverage80=float(np.mean([z['coverage80'] for z in pos])) if pos else None,primary_IS80=float(np.mean([z['IS80'] for z in pos])) if pos else None,Brier4=float(np.mean([z['Brier4'] for z in bs])) if bs else None,false_alarm_fraction=float(np.mean([z['p_RUL_le4w']>=.5 for z in neg])) if neg else None,stale_above_train_max_fraction=float(np.mean([z['input_stale_above_train_max'] for z in rr])),known_event_by_last_post_query=bool(det) if post else None))
   episodes.append(dict(world=world,fleet=rr[0]['fleet'],stations=rr[0]['stations'],policy=rr[0]['policy'],cell_id=cid,has_pre_event_4w_query=bool(lead),missed_episode=None if not lead else not any(z['p_RUL_le4w']>=.5 for z in lead)))
  summaries=[]
  for w in worlds:
   pp=[z for z in per if z['world']==w['name']];ee=[z for z in episodes if z['world']==w['name'] and z['has_pre_event_4w_query']];dd=[z for z in jobs if z['world']==w['name']];post=[z for z in pp if z['known_event_by_last_post_query'] is not None]
   s=dict(world=w['name'],fleet=w['fleet'],stations=w['M'],policy=w['policy'],cells=len(pp),n_queries=sum(z['n_queries'] for z in pp),n_censored4=sum(z['n_censored4'] for z in pp),admitted_tests=sum(z['admitted'] for z in dd),station_hours=float(sum(z['actual_station_hours'] for z in dd if z['admitted'])),busy_rejections=sum(z['reason']=='station_busy' for z in dd),pending_rejections=sum(z['reason']=='pending_report' for z in dd),age_rejections=sum(z['reason']=='below_age_threshold' for z in dd),max_concurrent=w['max_concurrent'],alarm_eligible_events=len(ee),missed_episodes=sum(bool(z['missed_episode']) for z in ee),cells_with_post_queries=len(post),cells_unconfirmed_at_last_post_query=sum(not z['known_event_by_last_post_query'] for z in post))
   for k in ['primary_MAE','all_MAE','primary_coverage80','primary_IS80','Brier4','false_alarm_fraction','stale_above_train_max_fraction']:
    x=[z[k] for z in pp if z[k] is not None];s[k]=float(np.mean(x)) if x else None
   summaries.append(s)
  comparisons=[]
  for fid in ['F1','F2','F3']:
   for M in [2,4]:
    rs=[z for z in per if z['fleet']==fid and z['stations']==M];a={z['cell_id']:z for z in rs if z['policy']=='age_calibrated'};b={z['cell_id']:z for z in rs if z['policy']=='age_no_pending'}
    if set(a)!=set(b):raise ValueError('cell matching')
    delta=[]
    for cid in sorted(a):
     if a[cid]['n_queries']!=b[cid]['n_queries'] or a[cid]['n_primary']!=b[cid]['n_primary']:raise ValueError('query matching')
     if a[cid]['primary_MAE'] is not None:delta.append((cid,b[cid]['primary_MAE']-a[cid]['primary_MAE']))
    x=next(z for z in summaries if z['fleet']==fid and z['stations']==M and z['policy']=='age_calibrated');y=next(z for z in summaries if z['fleet']==fid and z['stations']==M and z['policy']=='age_no_pending')
    comparisons.append(dict(fleet=fid,stations=M,paired_cells=len(delta),candidate='age_no_pending',reference='age_calibrated',delta_primary_MAE=float(np.mean([z[1] for z in delta])),cells_improved=sum(z[1]<-1e-9 for z in delta),cells_unchanged=sum(abs(z[1])<=1e-9 for z in delta),cells_worse=sum(z[1]>1e-9 for z in delta),worst_cell=max(delta,key=lambda z:z[1])[0],worst_cell_delta=max(z[1] for z in delta),age_station_hours=x['station_hours'],pending_station_hours=y['station_hours'],age_relative_hours_minus_pending=(x['station_hours']-y['station_hours'])/y['station_hours'] if y['station_hours'] else None,age_missed_episodes=x['missed_episodes'],pending_missed_episodes=y['missed_episodes'],age_coverage80=x['primary_coverage80'],pending_coverage80=y['primary_coverage80'],independent_fleet_CI='Not estimated; three same-source development fleets.'))
  for name,rs in [('predictions.csv',predictions),('decisions.csv',jobs),('per_cell.csv',per),('event_episodes.csv',episodes),('summary.csv',summaries),('comparisons.csv',comparisons),('excluded_cells.csv',excluded)]:csvout(out/name,rs)
  rec.update(status='SUCCESS',finished_utc=stamp(),elapsed_seconds=time.time()-t0,GO_sha256=sha(gpath),source_files=source_files,input_sha256=g['input_sha256'],scored_cells=len(cells),excluded_cells=len(excluded),query_views=len(predictions),decisions=len(jobs),fleets=3,worlds=len(worlds),resource_conservation='PASS',unarrived_signal_mutation='PASS',prior_development_not_independent=True)
  writej(out/'receipt.json',rec);prog(out,rec);print(json.dumps(dict(status='SUCCESS',model_rows=rec['model_prediction_rows'],C3_source_cells_read=rec['C3_source_cells_read'],C3_logical_payload_loads=rec['C3_logical_payload_loads'],scored_cells=len(cells),query_views=len(predictions),elapsed_seconds=rec['elapsed_seconds'],comparisons=comparisons),ensure_ascii=False))
 except BaseException as ex:
  rec.update(status='FAILED',error=repr(ex),traceback=traceback.format_exc(),finished_utc=stamp(),elapsed_seconds=time.time()-t0)
  if out.is_dir() and not (out/'failure_receipt.json').exists():writej(out/'failure_receipt.json',rec)
  print(json.dumps(rec,ensure_ascii=False));raise
 finally:
  for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--go',required=True);main(pathlib.Path(a.parse_args().go))
