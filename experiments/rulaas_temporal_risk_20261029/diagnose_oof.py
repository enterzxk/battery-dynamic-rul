#!/usr/bin/env python3
"""Reconstruct saved training group-OOF scores to diagnose Platt collapse; no fitting."""
import os
os.environ['OMP_NUM_THREADS']='4';os.environ['MKL_NUM_THREADS']='4'
import pathlib,sys,json,csv,hashlib,datetime,time,collections,fcntl,traceback,argparse
import numpy as np
from scipy.special import expit
R=pathlib.Path('/home/yndx/zxk/rul');H=R/'experiments/rulaas_temporal_risk_20261029';AUD=H/'audit02';RUN=H/'run01';FORMAL=R/'experiments/multisource_factorial_20261021/run2_clocksafe';OWNER='01a17810-6ae6-7cf2-9729-5bfcaa8df5f4';DAY=86400.;WEEK=604800.
sys.path.insert(0,str(R/'experiments/isu_irregular_rul_seed42_v1'));from data_adapter import load_reviewed_cell
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def readj(p):return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def writej(p,x):
 with pathlib.Path(p).open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def group(c):return c.rsplit('C',1)[0]
def main(gpath):
 g=readj(gpath);out=R/g['output'];t0=time.time();locks=[];rec=dict(status='STARTED',request_id=g['request_id'],started_utc=stamp(),new_fits=0,model_prediction_rows=0,C1C2_source_cells_read=0,C3_payload_reads=0,C4_payload_reads=0,actual_coordinator_model_recorded=g['actual_model'])
 try:
  for p in [R/'automation/state/coordinator.lock',R/'automation/locks/isu_irregular_rul_cpu.lock']:
   f=p.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  c=readj(R/'automation/state/coordinator.json');hb=datetime.datetime.fromisoformat(c['heartbeat_utc'].replace('Z','+00:00'))
  if c.get('state')!='ACTIVE' or c.get('owner')!=OWNER or c.get('thread_id')!=OWNER or (datetime.datetime.now(datetime.timezone.utc)-hb).total_seconds()>1800:raise ValueError('owner')
  if g.get('status')!='APPROVED' or g.get('owner')!=OWNER or g.get('allow_fits') is not False or g.get('allow_C3') is not False or g.get('allow_C4') is not False or g['model_row_cap']!=6000 or g['source_cell_cap']!=32:raise ValueError('GO')
  for name,h in g['input_sha256'].items():
   if sha(R/name)!=h:raise ValueError('input hash '+name)
  if out.parent!=H or out.exists():raise ValueError('create-only')
  writej(H/(g['request_id']+'.claim.json'),dict(GO_sha256=sha(gpath),utc=stamp()));out.mkdir()
  split=readj(AUD/'split.json');auditrec=readj(AUD/'receipt.json');review=readj(RUN/'INDEPENDENT_RECOMPUTE_V2.json');manifest=readj(RUN/'fit_manifest.json')
  if review['status']!='PASS' or readj(RUN/'ROOT_DECISION.json')['status']!='NO_GAIN_FIXED_F3_RISK_SCREEN':raise ValueError('prior review or stop')
  mature=set(split['mature_train_groups']);held=set(split['outer_held_groups']);folds=[set(x) for x in split['oof_folds']];cut=float(split['selected']['cutoff_epoch'])
  if len(mature)!=15 or len(held)!=16 or mature&held or set.union(*folds)!=mature:raise ValueError('groups')
  for x in manifest['folds']:
   if set(x['fit_groups'])&set(x['oof_groups']) or set(x['fit_groups'])|set(x['oof_groups'])!=mature or (set(x['fit_groups'])|set(x['oof_groups']))&held:raise ValueError('fold manifest')
  metadata=[];train_target={}
  with (FORMAL/'train_targets.jsonl').open(encoding='utf-8') as f:
   for i,line in enumerate(f):
    z=json.loads(line);cid=z['cell_id'];metadata.append(dict(cell_id=cid,arm=z['arm'],query_epoch=float(z['query_epoch']),known_event=bool(z['known_event'])))
    if group(cid) in mature:train_target[i]=z['target_rul_weeks']
  src={z['cell_id']:z for z in auditrec['source_files']};events={}
  for cid in sorted({z['cell_id'] for z in metadata if group(z['cell_id']) in mature}):
   item=src[cid];p=R/item['path']
   if not cid.endswith(('C1','C2')) or sha(p)!=item['sha256']:raise ValueError('source')
   cell=load_reviewed_cell(p,'train');rr=sorted(cell['records'],key=lambda z:float(z['stop_epoch']));events[cid]=next((float(z['stop_epoch']) for z in rr if float(z['capacityAh'])<=.20),None);rec['C1C2_source_cells_read']+=1
   if rec['C1C2_source_cells_read']>g['source_cell_cap']:raise ValueError('source cap')
  ti=[i for i,z in enumerate(metadata) if group(z['cell_id']) in mature and z['query_epoch']<=cut and events[z['cell_id']] is not None and events[z['cell_id']]+14*DAY<=cut and not z['known_event']]
  if len(ti)!=940 or any(train_target[i] is None for i in ti):raise ValueError('training population')
  cids=np.asarray([metadata[i]['cell_id'] for i in ti]);groups=np.asarray([group(x) for x in cids]);y=np.asarray([float(train_target[i])<=4. for i in ti],int)
  if int(y.sum())!=256:raise ValueError('training class')
  A=np.load(FORMAL/'train_features.npz',allow_pickle=False);X0=A['F0'];X3=A['F3'];import joblib
  saved=[];summary=[];pergroup=[]
  for name,X in [('hgb_F0',X0),('hgb_F3',X3),('logit_F3',X3)]:
   margins=np.full(len(ti),np.nan)
   for j,fold in enumerate(folds):
    mask=np.asarray([z in fold for z in groups]);inds=np.asarray(ti)[mask];model=joblib.load(RUN/(name+'_fold'+str(j)+'.joblib'))
    if rec['model_prediction_rows']+len(inds)>g['model_row_cap']:raise ValueError('prediction cap')
    margins[mask]=model.decision_function(X[inds]);rec['model_prediction_rows']+=len(inds)
   if not np.isfinite(margins).all():raise ValueError('oof scores')
   cal=joblib.load(RUN/(name+'_platt.joblib'))
   if rec['model_prediction_rows']+len(margins)>g['model_row_cap']:raise ValueError('prediction cap')
   cm=np.asarray(cal.decision_function(margins.reshape(-1,1)),float);rec['model_prediction_rows']+=len(cm)
   for mode,values in [('raw',margins),('platt_in_sample',cm)]:
    prob=expit(values);err=(prob-y)**2;loss=np.logaddexp(0.,values)-y*values;by=collections.defaultdict(list);episodes=collections.defaultdict(list)
    for j,i in enumerate(ti):
     z=metadata[i];b=float(err[j]);by[z['cell_id']].append(b)
     if 0.<float(train_target[i])<=4:episodes[(z['cell_id'],z['arm'])].append(float(prob[j]))
     saved.append(dict(model=name,mode=mode,cell_id=z['cell_id'],source_group=group(z['cell_id']),arm=z['arm'],query_epoch=z['query_epoch'],target_within4=int(y[j]),target_rul_weeks=float(train_target[i]),margin=float(values[j]),probability=float(prob[j]),Brier4=b))
    summary.append(dict(model=name,mode=mode,rows=len(ti),cells=len(by),groups=len(set(groups)),cell_macro_Brier4=float(np.mean([np.mean(v) for v in by.values()])),row_mean_logloss=float(np.mean(loss)),probability_at_least_half=int(np.sum(prob>=.5)),saturated_prob_lt_0p001_or_gt_0p999=int(np.sum((prob<.001)|(prob>.999))),raw_margin_abs_gt_10=int(np.sum(np.abs(values)>10.)),raw_margin_abs_gt_50=int(np.sum(np.abs(values)>50.)),pre_event_episode_units=len(episodes),missed_pre_event_episode_units=sum(not any(z>=.5 for z in ps) for ps in episodes.values()),calibration_evaluation='same OOF margins used to fit Platt; in-sample and optimistic' if mode=='platt_in_sample' else 'base score is source-group OOF'))
    for gr in sorted(set(groups)):
     idx=np.flatnonzero(groups==gr);pergroup.append(dict(model=name,mode=mode,source_group=gr,rows=len(idx),positives=int(y[idx].sum()),Brier4=float(np.mean(err[idx])),mean_probability=float(np.mean(prob[idx])),max_abs_margin=float(np.max(np.abs(values[idx])))))
  if rec['model_prediction_rows']!=5640:raise ValueError('row count')
  for name,rows in [('oof_scores.csv',saved),('per_group.csv',pergroup)]:
   with (out/name).open('x',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
  writej(out/'summary.json',dict(status='TRAIN_GROUP_OOF_SCORE_DIAGNOSIS_ONLY',summaries=summary,limits=['Base margins are group OOF; Platt was fitted and evaluated on these same OOF scores, so calibrated training metrics are optimistic.','No new classifier or calibration fit; no validation-dependent changes.','Synthetic label maturity and retrospective cutoff remain.']))
  rec.update(status='SUCCESS',finished_utc=stamp(),elapsed_seconds=time.time()-t0,GO_sha256=sha(gpath),input_sha256=g['input_sha256'],training_rows=len(ti),training_groups=len(set(groups)),calibrator_training_scores_reconstructed=True)
  writej(out/'receipt.json',rec);print(json.dumps(dict(status='SUCCESS',new_fits=0,model_rows=rec['model_prediction_rows'],elapsed_seconds=rec['elapsed_seconds'],summary=summary),ensure_ascii=False))
 except BaseException as ex:
  rec.update(status='FAILED',error=repr(ex),traceback=traceback.format_exc(),finished_utc=stamp(),elapsed_seconds=time.time()-t0)
  if out.is_dir() and not (out/'failure_receipt.json').exists():writej(out/'failure_receipt.json',rec)
  print(json.dumps(rec));raise
 finally:
  for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--go',required=True);main(pathlib.Path(a.parse_args().go))
