#!/usr/bin/env python3
"""C1/C2-only group/time label-support audit; no model fits or inference."""
import pathlib,sys,json,csv,hashlib,datetime,time,collections,fcntl,traceback,argparse,re
import numpy as np
R=pathlib.Path('/home/yndx/zxk/rul');H=R/'experiments/rulaas_temporal_risk_20261029';FORMAL=R/'experiments/multisource_factorial_20261021/run2_clocksafe';OWNER='01a17810-6ae6-7cf2-9729-5bfcaa8df5f4';WEEK=604800.;DAY=86400.;CUTOFF_QUANTILES=[.2,.25,.3,.35,.4,.5]
sys.path.insert(0,str(R/'experiments/isu_irregular_rul_seed42_v1'));from data_adapter import load_reviewed_cell
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def readj(p):return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def writej(p,x):
 with pathlib.Path(p).open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def group(cid):return cid.rsplit('C',1)[0]
def isoepoch(s):
 # Python 3.9 accepts at most six fractional digits; preserve the timestamp
 # to microsecond precision and compare with the explicit one-microsecond tolerance.
 s=re.sub(r'(\.\d{6})\d+',r'\1',s.replace('Z','+00:00'))
 x=datetime.datetime.fromisoformat(s)
 if x.tzinfo is None:x=x.replace(tzinfo=datetime.timezone.utc)
 return x.timestamp()
def main(gpath):
 g=readj(gpath);out=R/g['output'];t0=time.time();locks=[];rec=dict(status='STARTED',request_id=g['request_id'],started_utc=stamp(),new_fits=0,model_prediction_rows=0,C1C2_source_cells_read=0,C3_payload_reads=0,C4_payload_reads=0,actual_coordinator_model_recorded=g['actual_model'])
 try:
  for p in [R/'automation/state/coordinator.lock',R/'automation/locks/isu_irregular_rul_cpu.lock']:
   f=p.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  c=readj(R/'automation/state/coordinator.json');hb=datetime.datetime.fromisoformat(c['heartbeat_utc'].replace('Z','+00:00'))
  if c.get('state')!='ACTIVE' or c.get('owner')!=OWNER or c.get('thread_id')!=OWNER or (datetime.datetime.now(datetime.timezone.utc)-hb).total_seconds()>1800:raise ValueError('owner')
  if g.get('status')!='APPROVED' or g.get('owner')!=OWNER or g.get('allow_fits') is not False or g.get('allow_C3') is not False or g.get('allow_C4') is not False or g['source_cell_cap']!=124 or g['cutoff_quantiles']!=CUTOFF_QUANTILES or g['seed']!=42:raise ValueError('GO')
  for name,h in g['input_sha256'].items():
   if sha(R/name)!=h:raise ValueError('input hash '+name)
  if out.parent!=H or out.exists():raise ValueError('create-only output')
  writej(H/(g['request_id']+'.claim.json'),dict(GO_sha256=sha(gpath),utc=stamp()));out.mkdir()
  with (FORMAL/'train_targets.jsonl').open(encoding='utf-8') as f:targets=[json.loads(z) for z in f]
  with (FORMAL/'train_rows.jsonl').open(encoding='utf-8') as f:meta=[json.loads(z) for z in f]
  A=np.load(FORMAL/'train_features.npz',allow_pickle=False);X0=A['F0'];X3=A['F3']
  if X0.shape!=(6870,74) or X3.shape!=(6870,710) or len(meta)!=len(targets) or len(meta)!=6870 or np.isinf(X0).any() or np.isinf(X3).any() or not np.array_equal(X0,X3[:,:74],equal_nan=True):raise ValueError('feature shape or panels')
  ids=sorted({z['cell_id'] for z in targets});groups=sorted({group(c) for c in ids})
  if len(ids)!=124 or len(groups)!=63 or any(not c.endswith(('C1','C2')) for c in ids):raise ValueError('cohort')
  np.random.RandomState(42).shuffle(groups);held=set(groups[:16]);train=set(groups[16:])
  if len(held)!=16 or len(train)!=47 or held&train:raise ValueError('group split')
  man=readj(R/'reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json');events={};source_records={};sources=[]
  for cid in ids:
   item=man['files'][cid];p=R/item['path']
   if item['role']!='train' or 'C3' in p.name or 'C4' in p.name or sha(p)!=item['sha256']:raise ValueError('source role or hash')
   cell=load_reviewed_cell(p,'train');rr=sorted(cell['records'],key=lambda z:float(z['stop_epoch']))
   if cell['cell_id']!=cid or not rr:raise ValueError('source identity')
   events[cid]=next((float(z['stop_epoch']) for z in rr if float(z['capacityAh'])<=.20),None);source_records[cid]={int(z['source_rpt_index']):z for z in rr};sources.append(dict(cell_id=cid,path=item['path'],sha256=item['sha256']));rec['C1C2_source_cells_read']+=1
  keyset=set();maxerr=0.;cycle_checked=0
  for t,m in zip(targets,meta):
   cid=t['cell_id'];q=float(t['query_epoch']);key=(cid,t['arm'],q)
   if key in keyset or m['cell_id']!=cid or m['arm']!=t['arm'] or float(m['query_epoch'])!=q or m['role']!='train':raise ValueError('row identity or duplicate')
   keyset.add(key);indices=m['visible_rpt_source_indices'];arrival=m['visible_rpt_arrival_epochs'];stops=m['visible_rpt_source_stops']
   if len(indices)!=len(arrival) or len(indices)!=len(stops):raise ValueError('visible lengths')
   vis=[]
   for i,a,st in zip(indices,arrival,stops):
    row=source_records[cid][int(i)];actual=float(row['stop_epoch']);a=float(a)
    if abs(isoepoch(st)-actual)>1e-6 or actual>a or a>q:raise ValueError('RPT source/arrival/clock')
    vis.append(row)
   if any(float(v['capacityAh'])<=.20 for v in vis)!=bool(t['known_event']):raise ValueError('known event visibility')
   visible=m.get('cycle_latest_source_visible_at')
   if visible:
    if isoepoch(visible)>q+1e-6:raise ValueError('future cycle')
    cycle_checked+=1
   event=events[cid];y=t['target_rul_weeks']
   if event is None:
    if y is not None or int(t['y_event'])!=0:raise ValueError('censored event')
   else:
    expected=max(0.,(event-q)/WEEK)
    if y is None or int(t['y_event'])!=int(event<=q):raise ValueError('event label')
    err=abs(float(y)-expected);maxerr=max(maxerr,err)
    if err>1e-9:raise ValueError('RUL label mismatch')
  available=[e+14*DAY for cid,e in events.items() if e is not None and group(cid) in train]
  if not available:raise ValueError('no matured labels')
  grid=[]
  for quantile in CUTOFF_QUANTILES:
   cut=float(np.quantile(available,quantile))
   trainidx=[i for i,z in enumerate(targets) if group(z['cell_id']) in train and float(z['query_epoch'])<=cut and events[z['cell_id']] is not None and events[z['cell_id']]+14*DAY<=cut and not z['known_event']]
   # Only held query time and currently observable known-event state choose support, not held outcomes.
   heldidx=[i for i,z in enumerate(targets) if group(z['cell_id']) in held and float(z['query_epoch'])>=cut and not z['known_event']]
   tg={group(targets[i]['cell_id']) for i in trainidx};hg={group(targets[i]['cell_id']) for i in heldidx}
   grid.append(dict(training_maturity_quantile=quantile,cutoff_epoch=cut,cutoff_utc=datetime.datetime.fromtimestamp(cut,datetime.timezone.utc).isoformat(),mature_training_groups=len(tg),mature_training_cells=len({targets[i]['cell_id'] for i in trainidx}),mature_training_rows=len(trainidx),held_groups_with_unconfirmed_query=len(hg),held_cells_with_unconfirmed_query=len({targets[i]['cell_id'] for i in heldidx}),held_unconfirmed_query_rows=len(heldidx),meets_metadata_support=len(tg)>=15 and len(hg)>=10))
  candidates=[z for z in grid if z['meets_metadata_support']]
  if not candidates:raise ValueError('no cutoff with preregistered minimum group support')
  chosen=max(candidates,key=lambda z:z['cutoff_epoch']);cut=chosen['cutoff_epoch']
  ti=[i for i,z in enumerate(targets) if group(z['cell_id']) in train and float(z['query_epoch'])<=cut and events[z['cell_id']] is not None and events[z['cell_id']]+14*DAY<=cut and not z['known_event']]
  vi=[i for i,z in enumerate(targets) if group(z['cell_id']) in held and float(z['query_epoch'])>=cut and not z['known_event']]
  censored=[i for i in vi if targets[i]['target_rul_weeks'] is None];observed=[i for i in vi if targets[i]['target_rul_weeks'] is not None]
  if any(targets[i]['target_rul_weeks'] is None for i in ti):raise ValueError('mature training label unexpectedly missing')
  mature=sorted({group(targets[i]['cell_id']) for i in ti});np.random.RandomState(42).shuffle(mature);folds=[set(mature[i::3]) for i in range(3)]
  def labelcounts(ix):
   pos=sum(float(targets[i]['target_rul_weeks'])<=4 for i in ix if targets[i]['target_rul_weeks'] is not None)
   return dict(rows=len(ix),cells=len({targets[i]['cell_id'] for i in ix}),groups=len({group(targets[i]['cell_id']) for i in ix}),within4=pos,after4=sum(float(targets[i]['target_rul_weeks'])>4 for i in ix if targets[i]['target_rul_weeks'] is not None),no_exact_label=sum(targets[i]['target_rul_weeks'] is None for i in ix))
  foldstats=[labelcounts([i for i in ti if group(targets[i]['cell_id']) in fold]) for fold in folds]
  if any(z['groups']<3 or z['within4']==0 or z['after4']==0 for z in foldstats):raise ValueError('fold class support')
  rowstatus=collections.Counter()
  for z in targets:
   cid=z['cell_id'];role='outer_train' if group(cid) in train else 'outer_held'
   if z['target_rul_weeks'] is None:rowstatus[role+'_no_exact_event_label']+=1
   if role=='outer_train' and events[cid] is not None and events[cid]+14*DAY>cut:rowstatus['outer_train_event_not_mature_by_cutoff']+=1
  split=dict(seed=42,outer_train_groups=sorted(train),outer_held_groups=sorted(held),mature_train_groups=sorted(mature),oof_folds=[sorted(x) for x in folds],candidate_quantiles=CUTOFF_QUANTILES,selection_rule='latest cutoff with >=15 mature training groups and >=10 held groups having an unconfirmed query; only held input metadata',selected=chosen,hypothetical_label_availability='source first EOL measurement stop + 14 days',feedback_arrival_observed=False)
  writej(out/'split.json',split)
  audit=dict(status='PASS_GROUP_AND_HYPOTHETICAL_ASOF_SUPPORT',new_fits=0,model_prediction_rows=0,C1C2_source_cells_read=rec['C1C2_source_cells_read'],C3_payload_reads=0,C4_payload_reads=0,total_rows=len(targets),source_cells=len(ids),source_groups=len(set(groups)),common_key_duplicates=0,F0_F3_first74_identical=True,RPT_visibility_and_known_event='PASS',cycle_timestamp_checks=cycle_checked,source_event_and_censor_label='PASS',max_RUL_label_error=maxerr,cutoff_grid=grid,selected_cutoff=chosen,training=labelcounts(ti),held_observed=labelcounts(observed),held_censored=labelcounts(censored),training_group_oof_folds=foldstats,row_status_counts=dict(rowstatus),limits=['Retrospective support-driven cutoff, no blind independent confirmation.','Event label availability is assumed at source EOL measurement plus 14 days; real service feedback is not measured.','Filtering to exact event labels excludes censored training rows; censor-aware learning remains unresolved.','Held query support is selected from historical input metadata and previous experiments used this source.'])
  writej(out/'AUDIT.json',audit);rec.update(status='SUCCESS',finished_utc=stamp(),elapsed_seconds=time.time()-t0,GO_sha256=sha(gpath),input_sha256=g['input_sha256'],source_files=sources,audit='PASS_GROUP_AND_HYPOTHETICAL_ASOF_SUPPORT');writej(out/'receipt.json',rec)
  print(json.dumps(dict(status=audit['status'],selected=chosen,training=audit['training'],held_observed=audit['held_observed'],held_censored=audit['held_censored'],folds=foldstats,row_status_counts=dict(rowstatus),max_RUL_label_error=maxerr),ensure_ascii=False))
 except BaseException as ex:
  rec.update(status='FAILED',error=repr(ex),traceback=traceback.format_exc(),finished_utc=stamp(),elapsed_seconds=time.time()-t0)
  if out.is_dir() and not (out/'failure_receipt.json').exists():writej(out/'failure_receipt.json',rec)
  print(json.dumps(rec,ensure_ascii=False));raise
 finally:
  for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--go',required=True);main(pathlib.Path(a.parse_args().go))
