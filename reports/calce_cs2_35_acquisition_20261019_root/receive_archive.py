from pathlib import Path
import json,sys,hashlib,time,signal,fcntl
O=Path(__file__).resolve().parent
p=json.loads((O/'ROOT_ACQUISITION_GO.json').read_text());assert p['status']=='GO_ONE_CS2_35_ARCHIVE_STREAM_ONLY' and p['max_data_body_bytes']==37056519
lock=(Path('/home/yndx/zxk/rul')/'automation/state/online_survival_cpu.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
c=json.loads(Path('/home/yndx/zxk/rul/automation/state/coordinator.json').read_text());assert c['owner']==c['thread_id']==p['owner'] and c['takeover_verified'] and not c['new_fits_allowed']
D=Path(p['destination']);part=D.with_suffix('.zip.partial');start=time.monotonic();n=0;h=hashlib.sha256()
with (O/'receiver.claim').open('x') as f:f.write('one exclusive server stream')
def timeout(a,b):raise TimeoutError('Frozen180second bound')
signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,180)
try:
 with part.open('xb') as f:
  while n<p['max_data_body_bytes']:
   b=sys.stdin.buffer.read(min(1048576,p['max_data_body_bytes']-n))
   if not b:break
   f.write(b);h.update(b);n+=len(b)
 assert n==p['expected_Content_Length'], 'Truncated SSH stream'
 assert not D.exists();part.rename(D)
 result={'status':'COMPLETE_ARCHIVE_STREAM_ONLY_NOT_PARSED','path':str(D),'bytes':n,'sha256':h.hexdigest(),'elapsed_seconds':time.monotonic()-start,'archive_extracts':0,'spreadsheet_reads':0,'new_fits':0,'model_calls':0,'other_cell_reads':0,'source_url':p['source_url'],'GO_consumed':True}
 with (O/'receipt.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps(result));signal.setitimer(signal.ITIMER_REAL,0)
except BaseException as e:
 result={'status':'FAILED_STOP_NO_RETRY','received_bytes':n,'partial_sha256':h.hexdigest(),'error_type':type(e).__name__,'error':str(e),'partial_path':str(part),'GO_consumed':True}
 with (O/'failure.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps(result));raise
