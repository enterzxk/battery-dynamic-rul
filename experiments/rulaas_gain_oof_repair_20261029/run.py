#!/usr/bin/env python3
"""One bounded cross-fitted training-label reconstruction, C1/C2 only."""
import os
os.environ['OMP_NUM_THREADS']='4'
os.environ['MKL_NUM_THREADS']='4'
import sys, json, csv, pathlib, hashlib, datetime, collections, fcntl, time, traceback, argparse
import numpy as np

ROOT=pathlib.Path('/home/yndx/zxk/rul')
HERE=ROOT/'experiments/rulaas_gain_oof_repair_20261029'
OLD=ROOT/'experiments/rulaas_gain_identifiability_20261029/run02'
FORMAL=ROOT/'experiments/multisource_factorial_20261021/run2_clocksafe'
SIGNALS=ROOT/'reports/multisource_20261021_signals'
OWNER='01a17810-6ae6-7cf2-9729-5bfcaa8df5f4'
WEEK=604800.;DAY=86400.
sys.path[:0]=[str(ROOT/'experiments/rulaas_value_gate_20261029'),str(ROOT/'experiments/multisource_factorial_20261021'),str(SIGNALS),str(ROOT/'experiments/isu_irregular_rul_seed42_v1'),str(ROOT/'experiments/dart_rul_v18')]
from value_gate import vector, MemoCycle
from data_adapter import load_reviewed_cell
import cycle_asof_features as C

def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def readj(p):return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def writej(p,x):
 with pathlib.Path(p).open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def csvout(p,rows):
 with pathlib.Path(p).open('x',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def progress(p,rec):
 tmp=p/'progress.tmp';tmp.write_text(json.dumps(rec,ensure_ascii=False),encoding='utf-8');os.replace(tmp,p/'progress.json')
def report(row,lag=7.):return dict(row,arrival_epoch=float(row['stop_epoch'])+lag*DAY)
def arrive(rows,q):return [z for z in rows if float(z['arrival_epoch'])<=q]

def main(gpath):
 g=readj(gpath);out=ROOT/g['output'];started=time.time();locks=[]
 rec=dict(status='STARTED',request_id=g['request_id'],started_utc=stamp(),predictive_fits_started=0,predictive_fits_completed=0,model_prediction_rows=0,source_train_cells_read=0,C3_payload_reads=0,C4_payload_reads=0,actual_coordinator_model_recorded=g['actual_model'])
 try:
  for p in [ROOT/'automation/state/coordinator.lock',ROOT/'automation/locks/isu_irregular_rul_cpu.lock']:
   f=p.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  coord=readj(ROOT/'automation/state/coordinator.json')
  if coord.get('state')!='ACTIVE' or coord.get('owner')!=OWNER or coord.get('thread_id')!=OWNER:raise ValueError('coordinator owner')
  heartbeat=datetime.datetime.fromisoformat(coord['heartbeat_utc'].replace('Z','+00:00'))
  if (datetime.datetime.now(datetime.timezone.utc)-heartbeat).total_seconds()>1800:raise ValueError('stale heartbeat')
  if g.get('status')!='APPROVED' or g.get('owner')!=OWNER or g.get('allow_fits') is not True or g.get('allow_C3') is not False or g.get('allow_C4') is not False:raise ValueError('GO')
  if g['fit_cap']!=3 or g['prediction_row_cap']!=4000 or g['source_cell_cap']!=24 or g['seed']!=42:raise ValueError('budget')
  for rel,expected in g['input_sha256'].items():
   if sha(ROOT/rel)!=expected:raise ValueError('input hash drift: '+rel)
  if out.parent!=HERE or out.exists():raise ValueError('output not create-only')
  writej(HERE/(g['request_id']+'.claim.json'),dict(GO_sha256=sha(gpath),utc=stamp()))
  out.mkdir();progress(out,rec)
  split=readj(OLD/'cell_split.json')
  fit=set(split['base_head_fit_cells']);held=set(split['base_head_unseen_cells'])
  selected=set(split['selected_kernel_fit']);heldselected=set(split['selected_kernel_held'])
  if len(fit)!=60 or len(held)!=60 or fit&held or len(selected)!=24 or len(heldselected)!=24 or not selected<=fit or not heldselected<=held:raise ValueError('split')
  ids=sorted(fit);np.random.RandomState(42).shuffle(ids)
  folds=[set(ids[i::3]) for i in range(3)]
  if any(len(s)!=20 for s in folds) or set.union(*folds)!=fit or any(folds[i]&folds[j] for i in range(3) for j in range(i)):raise ValueError('fold')
  with (FORMAL/'train_targets.jsonl').open(encoding='utf-8') as f:target=[json.loads(x) for x in f]
  X=np.load(FORMAL/'train_features.npz',allow_pickle=False)['F3']
  if X.shape!=(len(target),710):raise ValueError('base training feature shape')
  pos=np.asarray([z['target_rul_weeks'] is not None and float(z['target_rul_weeks'])>0 for z in target])
  cid=np.asarray([z['cell_id'] for z in target])
  if any(not c.endswith(('C1','C2')) for c in set(cid)):raise ValueError('nontrain ids')
  from sklearn.ensemble import HistGradientBoostingRegressor
  import sklearn,joblib
  models=[];fold_manifest=[]
  for i,foof in enumerate(folds):
   traincells=fit-foof;idx=np.flatnonzero(pos & np.isin(cid,list(traincells)))
   if len(traincells)!=40 or set(cid[idx])!=traincells or set(cid[idx])&held or set(cid[idx])&foof:raise ValueError('fold leak')
   cnt=collections.Counter(cid[idx]);weights=np.asarray([1./cnt[c] for c in cid[idx]],float)
   y=np.asarray([float(target[j]['target_rul_weeks']) for j in idx],float)
   if not np.isfinite(y).all() or np.isinf(X[idx]).any():raise ValueError('invalid base training values')
   model=HistGradientBoostingRegressor(max_iter=150,max_leaf_nodes=15,l2_regularization=1.0,random_state=42,early_stopping=False)
   rec['predictive_fits_started']+=1;progress(out,rec)
   if rec['predictive_fits_started']>g['fit_cap']:raise ValueError('fit cap')
   model.fit(X[idx],np.log(y),sample_weight=weights)
   rec['predictive_fits_completed']+=1;models.append(model)
   with (out/('nested_head_'+str(i)+'.joblib')).open('xb') as f:joblib.dump(model,f,compress=3)
   fold_manifest.append(dict(fold=i,train_cells=sorted(traincells),excluded_oof_cells=sorted(foof),original_held_cells_excluded=sorted(held),positive_training_rows=len(idx)))
   progress(out,rec)
  if rec['predictive_fits_completed']!=3:raise ValueError('incomplete base fits')
  writej(out/'fold_manifest.json',dict(seed=42,cell_grouping='physical cell, not independent operating group',folds=fold_manifest,sklearn_version=sklearn.__version__))
  with (OLD/'cases.csv').open(encoding='utf-8',newline='') as f:cases=list(csv.DictReader(f))
  Xold=np.load(OLD/'request_features.npz',allow_pickle=False)['X_request']
  if len(cases)!=186 or Xold.shape!=(186,711):raise ValueError('case count')
  for j,c in enumerate(cases):
   if int(c['case_id'])!=j:raise ValueError('case order')
  traincases=[x for x in cases if x['population']=='kernel_fit'];testcases=[x for x in cases if x['population']=='kernel_held']
  if len(traincases)!=101 or len(testcases)!=85 or {z['cell_id'] for z in traincases}!=selected or {z['cell_id'] for z in testcases}!=heldselected:raise ValueError('population')
  bycell=collections.defaultdict(list)
  for c in traincases:bycell[c['cell_id']].append(c)
  man=readj(ROOT/'reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json')
  roles=readj(ROOT/'reports/isu_ilcc_capacity_probe_20261020_root/cohort.json')['roles']
  ri={x['cell_id']:x for x in readj(SIGNALS/'all188_rpt_features_v1/manifest.json')['inventory']}
  ci={x['cell_id']:x for x in readj(SIGNALS/'cycling_all188_feature_manifest.json')['inventory']}
  newX=Xold.copy();newcases=[dict(z) for z in cases];points=[];source_manifest=[];seen=set()
  for cell_id in sorted(selected):
   fold=next(i for i,s in enumerate(folds) if cell_id in s)
   if cell_id in set(fold_manifest[fold]['train_cells']) or roles[cell_id]!='train' or not cell_id.endswith(('C1','C2')):raise ValueError('cell or role')
   info=man['files'][cell_id]
   for kind,it in [('DataV2',info),('RPT',ri[cell_id]),('Cycling',ci[cell_id])]:
    p=ROOT/it['path']
    if it.get('role')!='train' or 'C3' in p.name or 'C4' in p.name or sha(p)!=it['sha256']:raise ValueError('source identity '+cell_id)
    source_manifest.append(dict(cell_id=cell_id,kind=kind,path=it['path'],sha256=it['sha256']))
   cell=load_reviewed_cell(ROOT/info['path'],'train');rows=sorted(cell['records'],key=lambda z:float(z['stop_epoch']))
   rpt=readj(ROOT/ri[cell_id]['path']);cycle=MemoCycle(C.build_cycle_index(ROOT/ci[cell_id]['path']))
   if cell['cell_id']!=cell_id or cycle.cell_id!=cell_id or cycle.role!='train' or rpt['role']!='train':raise ValueError('derived identity')
   cache={cell_id:{int(z['source_rpt_index']):z for z in rpt['records']}}
   event=next((float(z['stop_epoch']) for z in rows if float(z['capacityAh'])<=.20),None)
   matrix=[];index={};drafts=[]
   def add(x):
    raw=np.asarray(x,np.float32).tobytes()
    if raw not in index:index[raw]=len(matrix);matrix.append(np.asarray(x,np.float32))
    return index[raw]
   for old in bycell[cell_id]:
    j=int(old['case_id']);posi=int(old['valid_ordinal']);row=rows[posi];idx=int(row['source_rpt_index']);t=datetime.datetime.fromisoformat(row['start']).timestamp()
    if idx!=int(old['source_rpt_index']) or t!=float(old['request_epoch']) or event!=float(old['source_event_epoch']) or float(row['stop_epoch'])!=float(old['future_candidate_stop_epoch']):raise ValueError('source event / case identity')
    bg=[report(z) for k,z in enumerate(rows[:posi]) if k<3 or (k-3)%2==0];vis=arrive(bg,t)
    if sum(float(z['arrival_epoch'])>t for z in bg)!=int(old['input_pending_prior_reports']):raise ValueError('pending mismatch')
    current=vector(cell,vis,t,cache,cycle)
    if not np.allclose(current,Xold[j,:710],rtol=0,atol=0,equal_nan=True):raise ValueError('current features mismatch')
    current_ix=add(current);slots=[]
    for k in range(1,9):
     q=t+k*.5*WEEK
     if q>=event:
      slots.append(dict(q=q,alive=False,y=0.,none=None,now=None,delay=None));continue
     if q>float(rows[-1]['stop_epoch']):raise ValueError('pre-event unsupported')
     prior=arrive(bg,q);zero=add(vector(cell,prior,q,cache,cycle));more=[]
     for lag in [0.,7.]:
      v=list(prior)
      if float(row['stop_epoch'])+lag*DAY<=q:v.append(report(row,lag))
      v.sort(key=lambda z:(float(z['stop_epoch']),int(z['source_rpt_index'])))
      more.append(add(vector(cell,v,q,cache,cycle)))
     slots.append(dict(q=q,alive=True,y=(event-q)/WEEK,none=zero,now=more[0],delay=more[1]))
    drafts.append(dict(old=old,current=current_ix,slots=slots))
   if rec['model_prediction_rows']+len(matrix)>g['prediction_row_cap']:raise ValueError('inference cap')
   mu=models[fold].predict(np.asarray(matrix,float));rec['model_prediction_rows']+=len(matrix)
   pred=np.exp(mu)
   if not np.isfinite(pred).all():raise ValueError('nonfinite model output; no clipping')
   for d in drafts:
    old=d['old'];j=int(old['case_id']);g0=g7=0.;alive=0
    for k,s in enumerate(d['slots'],1):
     if s['alive']:
      y=s['y'];a=float(pred[s['none']]);b=float(pred[s['now']]);c=float(pred[s['delay']]);now=abs(a-y)-abs(b-y);delay=abs(a-y)-abs(c-y);alive+=1
     else:y=0.;a=b=c=None;now=delay=0.
     g0+=now/8.;g7+=delay/8.
     points.append(dict(case_id=j,cell_id=cell_id,fold=fold,source_rpt_index=int(old['source_rpt_index']),slot=k,query_epoch=s['q'],pre_reference_event=s['alive'],true_RUL=y,point_no_candidate=a,point_stop_delivery=b,point_7day_delivery=c,gain_stop_delivery=now,gain_7day_delivery=delay))
    if alive!=int(old['label_pre_event_slots']):raise ValueError('slot support mismatch')
    point=float(pred[d['current']]);newX[j,710]=point
    newcases[j].update(input_point_proxy_RUL=point,label_gain_stop_delivery_weeks=g0,label_gain_7day_delivery_weeks=g7,label_delay_penalty_weeks=g0-g7,label_pre_event_slots=alive)
    seen.add(j)
   rec['source_train_cells_read']+=1;rec['cases_completed']=len(seen);progress(out,rec)
  if seen!={int(z['case_id']) for z in traincases} or rec['source_train_cells_read']!=24:raise ValueError('lost or duplicate cases')
  valindex=[int(z['case_id']) for z in testcases]
  if not np.array_equal(newX[valindex],Xold[valindex],equal_nan=True) or any(newcases[j]!=cases[j] for j in valindex):raise ValueError('held case mutated')
  csvout(out/'cases.csv',newcases);csvout(out/'crossfit_train_points.csv',points)
  with (out/'request_features.npz').open('xb') as f:np.savez_compressed(f,X_request=newX)
  trainindex=sorted(seen)
  old_gain=np.asarray([float(cases[j]['label_gain_7day_delivery_weeks']) for j in trainindex])
  new_gain=np.asarray([float(newcases[j]['label_gain_7day_delivery_weeks']) for j in trainindex])
  d=new_gain-old_gain
  by_delta=collections.defaultdict(list)
  for j in trainindex:by_delta[cases[j]['cell_id']].append(float(newcases[j]['label_gain_7day_delivery_weeks'])-float(cases[j]['label_gain_7day_delivery_weeks']))
  summary=dict(n_train_cases=len(trainindex),n_train_cells=len(by_delta),n_held_cases=len(valindex),n_held_cells=len(heldselected),old_train_case_mean_gain=float(old_gain.mean()),crossfit_train_case_mean_gain=float(new_gain.mean()),paired_label_change_case_mean=float(d.mean()),paired_label_change_median=float(np.median(d)),paired_label_change_absolute_mean=float(np.mean(np.abs(d))),paired_label_change_cell_macro=float(np.mean([np.mean(x) for x in by_delta.values()])),old_train_negative_cases=int((old_gain< -1e-9).sum()),crossfit_train_negative_cases=int((new_gain< -1e-9).sum()),held_inputs_and_labels_bitwise_unchanged=True,full_held_fold_excluded_from_all_three_fits=True,all_training_requests_reconstructed_exactly=True)
  writej(out/'label_change_summary.json',summary)
  rec.update(status='SUCCESS',finished_utc=stamp(),elapsed_seconds=time.time()-started,GO_sha256=sha(gpath),sklearn_version=sklearn.__version__,source_files=source_manifest,input_sha256=g['input_sha256'],train_cases=len(trainindex),held_cases=len(valindex),held_cases_unchanged=True,fold_train_cells=40,held_head_train_cells=60)
  writej(out/'receipt.json',rec);progress(out,rec)
  print(json.dumps(dict(status=rec['status'],fits=rec['predictive_fits_completed'],prediction_rows=rec['model_prediction_rows'],elapsed_seconds=rec['elapsed_seconds'],summary=summary),ensure_ascii=False))
 except BaseException as ex:
  rec.update(status='FAILED',error=repr(ex),traceback=traceback.format_exc(),finished_utc=stamp(),elapsed_seconds=time.time()-started)
  if out.is_dir() and not (out/'failure_receipt.json').exists():writej(out/'failure_receipt.json',rec)
  print(json.dumps(rec,ensure_ascii=False));raise
 finally:
  for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--go',required=True);main(pathlib.Path(a.parse_args().go))
