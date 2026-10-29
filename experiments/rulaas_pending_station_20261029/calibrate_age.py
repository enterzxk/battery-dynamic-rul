#!/usr/bin/env python3
"""Train-fleet-only station-hour matching of age rules, no models or held outcomes."""
import pathlib,sys,json,csv,collections,hashlib,datetime,time,fcntl,heapq,traceback,argparse
import numpy as np
R=pathlib.Path('/home/yndx/zxk/rul');H=R/'experiments/rulaas_pending_station_20261029';OLD=R/'experiments/rulaas_gain_identifiability_20261029/run02';FIRST=H/'run01'
OWNER='01a17810-6ae6-7cf2-9729-5bfcaa8df5f4';DAY=86400.;WEEK=604800.;LAG=14.;GRID=[2.,2.25,2.5,2.75,3.,3.25,3.5,4.,4.5,5.,6.,8.]
sys.path.insert(0,str(R/'experiments/isu_irregular_rul_seed42_v1'));from data_adapter import load_reviewed_cell
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def readj(p):return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def writej(p,x):
 with pathlib.Path(p).open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def start(row):return datetime.datetime.fromisoformat(row['start']).timestamp()
def report(row):return dict(row,arrival_epoch=float(row['stop_epoch'])+LAG*DAY)
def main(gpath):
 g=readj(gpath);out=R/g['output'];starttime=time.time();locks=[];rec=dict(status='STARTED',started_utc=stamp(),request_id=g['request_id'],new_fits=0,model_prediction_rows=0,training_source_cells_read=0,held_fleet_outcomes_used=0,C3_payload_reads=0,C4_payload_reads=0,actual_coordinator_model_recorded=g['actual_model'])
 try:
  for p in [R/'automation/state/coordinator.lock',R/'automation/locks/isu_irregular_rul_cpu.lock']:
   f=p.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  c=readj(R/'automation/state/coordinator.json');hb=datetime.datetime.fromisoformat(c['heartbeat_utc'].replace('Z','+00:00'))
  if c.get('state')!='ACTIVE' or c.get('owner')!=OWNER or c.get('thread_id')!=OWNER or (datetime.datetime.now(datetime.timezone.utc)-hb).total_seconds()>1800:raise ValueError('coordinator')
  if g.get('status')!='APPROVED' or g.get('owner')!=OWNER or g.get('allow_fits') is not False or g.get('allow_C3') is not False or g.get('allow_C4') is not False or g['age_grid_weeks']!=GRID or g['capacities']!=[2,4] or g['source_cell_cap']!=24:raise ValueError('GO')
  for rel,h in g['input_sha256'].items():
   if sha(R/rel)!=h:raise ValueError('input hash '+rel)
  if out.parent!=H or out.exists():raise ValueError('create-only')
  writej(H/(g['request_id']+'.claim.json'),dict(GO_sha256=sha(gpath),utc=stamp()));out.mkdir()
  split=readj(OLD/'cell_split.json');ids=split['selected_kernel_fit'];fit=set(split['base_head_fit_cells']);held=set(split['base_head_unseen_cells'])
  if len(ids)!=24 or not set(ids)<=fit or set(ids)&held:raise ValueError('train-only split')
  fleet=readj(FIRST/'fleet_world.json');targets=readj(H/'TRAIN_TARGET_ONLY.json')
  if targets['population']!='kernel_fit' or set(targets['station_hours'])!={'2','4'} or fleet['report_lag_days']!=14 or fleet['seed']!=42:raise ValueError('target or fleet')
  source=readj(OLD/'receipt.json');src={z['cell_id']:z for z in source['source_files'] if z['kind']=='DataV2'};cells={};timeline=[]
  for cid in sorted(ids):
   z=src[cid];p=R/z['path']
   if not cid.endswith(('C1','C2')) or sha(p)!=z['sha256']:raise ValueError('source hash or role')
   c=load_reviewed_cell(p,'train');rows=sorted(c['records'],key=lambda x:float(x['stop_epoch']))
   if c['cell_id']!=cid or len(rows)<3 or any(start(b)<float(a['stop_epoch']) for a,b in zip(rows,rows[1:])):raise ValueError('cell or overlap')
   warm=float(rows[2]['stop_epoch']);off=float(fleet['offset_seconds'][cid]);cells[cid]=dict(rows=rows,warm=warm,offset=off)
   for i,row in enumerate(rows):
    if i>=3:
     q=start(row);timeline.append((q-warm+off,cid,q,i))
   rec['training_source_cells_read']+=1
  timeline.sort();records=[]
  for M in [2,4]:
   target=float(targets['station_hours'][str(M)])
   for threshold in GRID:
    accepted={cid:[report(x) for x in c['rows'][:3]] for cid,c in cells.items()};busy=[];free=list(range(M));hours=0.;n=0;busyreject=0;knownskip=0;agereject=0
    for t,cid,q,i in timeline:
     while busy and busy[0][0]<=t:
      _,slot=heapq.heappop(busy);free.append(slot)
     vis=[z for z in accepted[cid] if float(z['arrival_epoch'])<=q]
     if any(float(z['capacityAh'])<=.20 for z in vis):knownskip+=1;continue
     if not free:busyreject+=1;continue
     if len(vis)>=3 and (q-float(vis[-1]['stop_epoch']))/WEEK<threshold:agereject+=1;continue
     row=cells[cid]['rows'][i];stop=float(row['stop_epoch']);duration=stop-q
     if duration<=0:raise ValueError('duration')
     slot=min(free);free.remove(slot);heapq.heappush(busy,(stop-cells[cid]['warm']+cells[cid]['offset'],slot));accepted[cid].append(report(row));hours+=duration/3600.;n+=1
     if len(busy)>M or len(busy)+len(free)!=M:raise ValueError('resource')
    records.append(dict(stations=M,age_threshold_weeks=threshold,training_admitted_tests=n,training_station_hours=hours,target_training_station_hours=target,absolute_station_hour_difference=abs(hours-target),relative_station_hour_difference=(hours-target)/target,busy_rejections=busyreject,known_event_skips=knownskip,age_rejections=agereject))
  chosen=[]
  for M in [2,4]:
   a=[x for x in records if x['stations']==M];best=min(a,key=lambda x:(x['absolute_station_hour_difference'],x['age_threshold_weeks']));chosen.append(best)
  with (out/'grid.csv').open('x',encoding='utf-8',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
  writej(out/'CALIBRATED.json',dict(status='TRAIN_ONLY_THRESHOLDS_FROZEN',selected=chosen,grid=GRID,tie_break='smallest threshold',uses_held_fleet_outcomes=False,uses_lifetime_labels=False,simulation_worlds=24,source_cells=24,request_events_per_world=len(timeline),limitation='Frozen after inspecting earlier held outcomes; this is a post-hoc stronger development comparator, not independent confirmation.'))
  rec.update(status='SUCCESS',finished_utc=stamp(),elapsed_seconds=time.time()-starttime,simulated_worlds=24,request_events_per_world=len(timeline),selected=chosen,GO_sha256=sha(gpath),input_sha256=g['input_sha256'])
  writej(out/'receipt.json',rec);print(json.dumps({k:v for k,v in rec.items() if k!='input_sha256'},ensure_ascii=False))
 except BaseException as ex:
  rec.update(status='FAILED',error=repr(ex),traceback=traceback.format_exc(),finished_utc=stamp(),elapsed_seconds=time.time()-starttime)
  if out.is_dir() and not (out/'failure_receipt.json').exists():writej(out/'failure_receipt.json',rec)
  print(json.dumps(rec));raise
 finally:
  for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--go',required=True);main(pathlib.Path(a.parse_args().go))
