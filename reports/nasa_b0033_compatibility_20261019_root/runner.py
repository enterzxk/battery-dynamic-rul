from pathlib import Path
import json,hashlib,zipfile,io,time,fcntl,signal,datetime,importlib.util
import numpy as np
from scipy.io import loadmat
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,x):
 with (O/n).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
def main():
 p=json.loads((O/'protocol.json').read_text());g=json.loads((O/'ROOT_GO.json').read_text());assert g['status']=='GO_ONE_NEW_B0033_TRAIN_COMPATIBILITY_ZERO_FIT' and g['max_runs']==1 and g['max_MAT_bytes']==11057919
 for n in ['runner.py','protocol.json']:assert sha(O/n)==g[n+'_sha256']
 rv=Path(g['review_path']);assert sha(rv)==g['review_sha256'] and json.loads(rv.read_text())['status']=='PASS'
 with (R/'automation/state/online_survival_cpu.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);c=json.loads((R/'automation/state/coordinator.json').read_text());assert c['owner']==c['thread_id']==p['owner'] and c['takeover_verified'] and not c['new_fits_allowed']
  with (O/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
  start=time.monotonic();consumed={'nested_container_bytes':0,'MAT_bytes':0,'MAT_cells':0,'locked_member_reads':0}
  def timeout(a,b):raise TimeoutError('Frozen30second limit')
  signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,30)
  try:
   for s in p['sources'].values():assert sha(R/s['path'])==s['sha256']
   sp=json.loads((R/p['sources']['split']['path']).read_text());assert p['read_cell']=='B0033' and p['read_cell'] in sp['roles']['train'] and p['read_cell'] not in sp['roles']['locked'] and p['member']['path']=='B0033.mat'
   ar=R/p['archive_path'];assert ar.stat().st_size==p['archive_expected_bytes']
   spec=importlib.util.spec_from_file_location('existing_nasa_importer',R/p['sources']['importer']['path']);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
   with zipfile.ZipFile(ar) as outer:
    zi=outer.getinfo(p['outer_member']);assert zi.file_size<=p['budget']['max_nested_container_bytes'];consumed['nested_container_bytes']=zi.file_size;inner=outer.read(zi)
   assert hashlib.sha256(inner).hexdigest()==p['nested_sha256']
   with zipfile.ZipFile(io.BytesIO(inner)) as z:
    entry=z.getinfo('B0033.mat');assert entry.file_size==p['member']['bytes']==p['budget']['max_MAT_bytes'] and format(entry.CRC,'08x')==p['member']['crc32'];consumed.update(MAT_bytes=entry.file_size,MAT_cells=1);raw=z.read(entry)
   data=loadmat(io.BytesIO(raw),squeeze_me=True,struct_as_record=False)['B0033'];rows=[]
   for opidx,op in enumerate(np.atleast_1d(data.cycle),1):
    if str(op.type)!='discharge':continue
    a=op.data;t=np.asarray(a.Time).reshape(-1);i=np.asarray(a.Current_measured).reshape(-1);v=np.asarray(a.Voltage_measured).reshape(-1)
    try:q,detail=m.cutoff_capacity(t,i,v)
    except (AssertionError,ValueError):q=None;detail={'reason':'finite_shape_or_time_guard_failed'}
    cap=np.asarray(a.Capacity).reshape(-1) if hasattr(a,'Capacity') else np.array([]);original=float(cap[0]) if cap.size and np.isfinite(cap[0]) else None
    active=i[i<-.1];rows.append({'discharge':len(rows)+1,'operation':opidx,'ambient_C':float(op.ambient_temperature),'median_active_current_A':float(np.median(active)) if len(active) else None,'capacity_common2p7V_Ah':q,'capacity_original_Ah':original,'valid':q is not None,'reason':detail.get('reason')})
   assert rows and all(rows[k]['operation']<rows[k+1]['operation'] for k in range(len(rows)-1))
   event=next((r['discharge'] for r in rows if r['valid'] and r['capacity_common2p7V_Ah']<=1.6),None);valid=[r for r in rows if r['valid']];eligible=lambda minimum:[r for r in valid if r['discharge']>=minimum and (event is None or r['discharge']<event)]
   decision='PASS_COMPATIBILITY_ONLY_NOT_CONFIRMATION' if len(eligible(100))>0 else 'STOP_NO_ORIGIN100_PREFIX_UNDER_FROZEN_ENDPOINT';active=[r['median_active_current_A'] for r in rows if r['median_active_current_A'] is not None]
   summary={'status':'COMPLETE_ONE_NEW_TRAIN_CELL_COMPATIBILITY','decision':decision,'cell_id':'B0033','role':'train','source_MAT_sha256':hashlib.sha256(raw).hexdigest(),'discharges':len(rows),'valid_common_cutoff':len(valid),'event80':event,'censor_at_last_valid':max(r['discharge'] for r in valid) if event is None and valid else None,'available_origins_ge100':len(eligible(100)),'available_origins_ge20_descriptive_only':len(eligible(20)),'first_valid_capacity_Ah':valid[0]['capacity_common2p7V_Ah'] if valid else None,'ambient_levels':sorted({r['ambient_C'] for r in rows}),'active_current_median_range_A':[min(active),max(active)] if active else None,'empty_author_capacity':sum(r['capacity_original_Ah'] is None for r in rows),'consumed':consumed,'new_fits':0,'new_model_inference':0,'checkpoint_loads':0,'new_downloads':0,'dev_cell_reads':0,'test_cell_reads':0,'locked_MAT_reads':0,'B0034_MAT_reads':0,'old_B0036_B0050_MAT_reads':0,'protocol_sha256':sha(O/'protocol.json'),'runner_sha256':sha(O/'runner.py'),'GO_sha256':sha(O/'ROOT_GO.json'),'elapsed_seconds':time.monotonic()-start}
   dump('canonical_rows.json',{'cell_id':'B0033','rows':rows});dump('summary.json',summary);signal.setitimer(signal.ITIMER_REAL,0);print(json.dumps(summary))
  except BaseException as e:dump('failure.json',{'status':'FAILED_STOP_NO_RETRY','type':type(e).__name__,'error':str(e),'consumed':consumed});raise
if __name__=='__main__':main()
