#!/usr/bin/env python3
"""Audit 4-week labels available by a frozen cutoff from source-prefix follow-up."""
import pathlib,sys,json,csv,hashlib,datetime,time,collections,fcntl,traceback,argparse
import numpy as np
R=pathlib.Path('/home/yndx/zxk/rul');H=R/'experiments/rulaas_temporal_risk_20261029';AUD=H/'audit02';FORMAL=R/'experiments/multisource_factorial_20261021/run2_clocksafe';OWNER='01a17810-6ae6-7cf2-9729-5bfcaa8df5f4';DAY=86400.;WEEK=604800.
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
  if g.get('status')!='APPROVED' or g.get('owner')!=OWNER or g.get('allow_fits') is not False or g.get('allow_C3') is not False or g.get('allow_C4') is not False or g['source_cell_cap']!=92:raise ValueError('GO')
  for name,h in g['input_sha256'].items():
   if sha(R/name)!=h:raise ValueError('input hash '+name)
  if out.parent!=H or out.exists():raise ValueError('create-only')
  writej(H/(g['request_id']+'.claim.json'),dict(GO_sha256=sha(gpath),utc=stamp()));out.mkdir()
  split=readj(AUD/'split.json');aud=readj(AUD/'AUDIT.json');source=readj(AUD/'receipt.json');risk=readj(H/'run01/ROOT_DECISION.json')
  if aud['status']!='PASS_GROUP_AND_HYPOTHETICAL_ASOF_SUPPORT' or risk['status']!='NO_GAIN_FIXED_F3_RISK_SCREEN':raise ValueError('prior gates')
  train=set(split['outer_train_groups']);held=set(split['outer_held_groups']);cut=float(split['selected']['cutoff_epoch'])
  if len(train)!=47 or len(held)!=16 or train&held:raise ValueError('group split')
  targets=[]
  with (FORMAL/'train_targets.jsonl').open(encoding='utf-8') as f:
   for i,line in enumerate(f):
    z=json.loads(line)
    if group(z['cell_id']) in train:targets.append((i,z))
  ids=sorted({z['cell_id'] for _,z in targets});src={z['cell_id']:z for z in source['source_files']};records={};prefixes={};events={};sources=[]
  if len(ids)!=92:raise ValueError('training cell count')
  for cid in ids:
   it=src[cid];p=R/it['path']
   if not cid.endswith(('C1','C2')) or 'C3' in p.name or 'C4' in p.name or sha(p)!=it['sha256']:raise ValueError('source')
   cell=load_reviewed_cell(p,'train');rr=sorted(cell['records'],key=lambda z:float(z['stop_epoch']))
   if cell['cell_id']!=cid:raise ValueError('source identity')
   records[cid]=rr;prefixes[cid]=[z for z in rr if float(z['stop_epoch'])+14*DAY<=cut];events[cid]=next((float(z['stop_epoch']) for z in rr if float(z['capacityAh'])<=.20),None);sources.append(dict(cell_id=cid,path=it['path'],sha256=it['sha256']));rec['C1C2_source_cells_read']+=1
  if rec['C1C2_source_cells_read']!=g['source_cell_cap']:raise ValueError('source cap')
  result=[];stats=collections.Counter();max_future_change=0;old_indices=set()
  for i,z in targets:
   cid=z['cell_id'];q=float(z['query_epoch'])
   if group(cid) not in train or q>cut:continue
   if z['known_event']:
    stats['known_event_at_query']+=1;continue
   h=q+4*WEEK;pre=prefixes[cid];first_event=next((float(x['stop_epoch']) for x in pre if float(x['capacityAh'])<=.20),None)
   if first_event is not None and first_event<=h:status='mature_positive';label=1;availability=first_event+14*DAY
   else:
    after=next((float(x['stop_epoch']) for x in pre if float(x['stop_epoch'])>=h),None)
    if after is not None:status='mature_negative';label=0;availability=after+14*DAY
    else:status='unmatured_or_censored_at_cutoff';label=None;availability=None
   event=events[cid];old=event is not None and event+14*DAY<=cut and z['target_rul_weeks'] is not None
   if old:old_indices.add(i)
   if availability is not None and availability>cut+1e-6:raise ValueError('label used before assumed availability')
   if old and label is None:raise ValueError('lost old mature label')
   if label is not None and z['target_rul_weeks'] is not None and int(float(z['target_rul_weeks'])<=4.)!=label:raise ValueError('horizon truth disagreement')
   if label==1 and z['target_rul_weeks'] is None:raise ValueError('positive without reference event')
   stats[status]+=1;stats['old_mature_reference_event_rows']+=int(old)
   if label is not None and not old:stats['newly_matured_'+('positive' if label else 'negative')]+=1
   if label==0 and z['target_rul_weeks'] is None:stats['newly_labelled_negative_without_exact_EOL']+=1
   if availability is not None and availability<=q:stats['label_already_available_by_query_in_reference_registry']+=1
   # The decision uses only prefix; changing all later source values leaves it unchanged.
   mutated=[dict(x,capacityAh=(-99999. if float(x['stop_epoch'])+14*DAY>cut else x['capacityAh'])) for x in records[cid]]
   mp=[x for x in mutated if float(x['stop_epoch'])+14*DAY<=cut];me=next((float(x['stop_epoch']) for x in mp if float(x['capacityAh'])<=.20),None)
   if me is not None and me<=h:mstatus='mature_positive'
   elif any(float(x['stop_epoch'])>=h for x in mp):mstatus='mature_negative'
   else:mstatus='unmatured_or_censored_at_cutoff'
   if mstatus!=status:raise ValueError('future signal affects as-of label')
   max_future_change+=1
   result.append(dict(row_index=i,cell_id=cid,source_group=group(cid),arm=z['arm'],query_epoch=q,horizon_epoch=h,status=status,label_within4=label,label_available_epoch=availability,old_exact_event_matured=old,exact_event_reference_missing=z['target_rul_weeks'] is None))
  mature=[z for z in result if z['label_within4'] is not None];added=[z for z in mature if not z['old_exact_event_matured']];pending=[z for z in result if z['label_within4'] is None]
  if len(old_indices)!=940 or stats['old_mature_reference_event_rows']!=940:raise ValueError('old training population mismatch')
  if any(group(z['cell_id']) in held for z in result):raise ValueError('held group leak')
  with (out/'training_label_status.csv').open('x',encoding='utf-8',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(result[0]));w.writeheader();w.writerows(result)
  summary=dict(status='HORIZON_LABEL_SUPPORT_AUDITED_NOT_MODEL_GAIN',cutoff_epoch=cut,hypothetical_label_delay_days=14,training_unknown_status_rows=len(result),old_event_matured_rows=len(old_indices),mature_horizon_rows=len(mature),mature_horizon_cells=len({z['cell_id'] for z in mature}),mature_horizon_groups=len({z['source_group'] for z in mature}),mature_positive=sum(z['label_within4']==1 for z in mature),mature_negative=sum(z['label_within4']==0 for z in mature),newly_matured_rows=len(added),newly_matured_positive=sum(z['label_within4']==1 for z in added),newly_matured_negative=sum(z['label_within4']==0 for z in added),new_negative_without_exact_EOL=stats['newly_labelled_negative_without_exact_EOL'],label_already_available_by_query_in_reference_registry=stats['label_already_available_by_query_in_reference_registry'],unmatured_or_censored_at_cutoff=len(pending),unmatured_or_censored_groups=len({z['source_group'] for z in pending}),known_event_at_query=stats['known_event_at_query'],future_value_mutation_checks=max_future_change,new_fits=0,model_prediction_rows=0,C3_payload_reads=0,C4_payload_reads=0,limits=['Reference registry is assumed to receive every recorded RPT after 14 days, including tests a hypothetical policy might have skipped; not a measured feedback stream.','If reference registry labels were available to the service at query time, unknown-event inputs might need revision; the two channels have not been validated.','Unknown or incompletely followed horizons remain unlabeled; 0 is not imputed.','No model performance or independent validation is established.','Cutoff was selected retrospectively from input support.'])
  writej(out/'SUMMARY.json',summary);rec.update(status='SUCCESS',finished_utc=stamp(),elapsed_seconds=time.time()-t0,GO_sha256=sha(gpath),input_sha256=g['input_sha256'],source_files=sources);writej(out/'receipt.json',rec);print(json.dumps(summary,ensure_ascii=False))
 except BaseException as ex:
  rec.update(status='FAILED',error=repr(ex),traceback=traceback.format_exc(),finished_utc=stamp(),elapsed_seconds=time.time()-t0)
  if out.is_dir() and not (out/'failure_receipt.json').exists():writej(out/'failure_receipt.json',rec)
  print(json.dumps(rec));raise
 finally:
  for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--go',required=True);main(pathlib.Path(a.parse_args().go))
