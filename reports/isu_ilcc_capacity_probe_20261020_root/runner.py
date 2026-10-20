from pathlib import Path
import json,csv,io,zipfile,hashlib,fcntl,math,time,signal,datetime
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
def dump(n,d):
 with (O/n).open('x') as f:json.dump(d,f,indent=2);f.write('\n')
def main():
 start=time.monotonic();p=json.loads((O/'protocol.json').read_text());g=json.loads((O/'ROOT_GO.json').read_text())
 assert g['status']=='GO_ONE_ARCHIVE_AND_TWO_TRAIN_SUMMARIES'
 for n in ['protocol.json','runner.py','receive_archive.py']:assert sha(O/n)==g[n+'_sha256']
 rv=Path(g['review_path']);assert sha(rv)==g['review_sha256'] and json.loads(rv.read_text())['status']=='PASS'
 with (R/'automation/state/online_survival_cpu.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);s=json.loads((R/'automation/state/coordinator.json').read_text());assert s['owner']==s['thread_id']==p['owner'] and s['takeover_verified'] and not s['new_fits_allowed']
  with (O/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
  def timeout(a,b):raise TimeoutError('Frozen30second limit exceeded')
  signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,p['max_seconds'])
  try:
   cf=O/'cohort.json';assert sha(cf)==p['cohort_sha256'];co=json.loads(cf.read_text())
   archive=R/'data/raw/ISU_ILCC/official_v2/capacity_fade.zip';b=archive.read_bytes();assert len(b)==p['max_archive_bytes'] and hashlib.md5(b).hexdigest()==p['acquisition']['computed_md5']
   receipt=json.loads((O/'acquisition_receipt.json').read_text());assert sha(archive)==receipt['sha256'];results=[];size=0
   with zipfile.ZipFile(io.BytesIO(b)) as z:
    info=[x for x in z.infolist() if not x.is_dir()];dump('archive_directory.json',{'entries':[{'name':x.filename,'bytes':x.file_size,'compressed_bytes':x.compress_size,'crc32':format(x.CRC,'08x')} for x in info],'member_payload_reads':0})
    for cid in p['probe_ids']:
     assert co['roles'][cid]=='train';matches=[x for x in info if Path(x.filename).name==cid+'.csv'];assert len(matches)==1
     item=matches[0];assert item.file_size<=p['max_member_bytes'];size+=item.file_size;assert size<=p['max_decompressed_total_bytes']
     raw=z.read(item);rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))));assert set(rows[0])=={'Time','Capacity'}
     times=[float(x['Time']) for x in rows];qs=[float(x['Capacity']) for x in rows];assert all(math.isfinite(x) for x in times+qs) and all(y>x for x,y in zip(times,times[1:])) and all(0<x<.5 for x in qs)
     event=next((i for i,q in enumerate(qs) if q<=p['candidate_threshold_Ah']),None)
     results.append({'cell_id':cid,'role':'train','source_member':item.filename,'source_sha256':hashlib.sha256(raw).hexdigest(),'rows':len(rows),'first_time':times[0],'last_time':times[-1],'first_capacity_Ah':qs[0],'last_capacity_Ah':qs[-1],'min_capacity_Ah':min(qs),'max_capacity_Ah':max(qs),'first_observed_nominal80_time':None if event is None else times[event],'first_observed_nominal80_row':None if event is None else event+1,'event_capacity_Ah':None if event is None else qs[event],'full_prefixes_before_observed_event':0 if event is None else event,'strict_asof_clock_verified':False,'interpretation':'Source-reported Time/Capacity only. First observed RPT threshold is not latent exact EOL; no legal right-censor assertion for no-event records.'})
   dump('probe_results.json',results);dump('completion.json',{'status':'COMPLETE_TWO_PRESELECTED_TRAIN_SUMMARIES','rows':sum(r['rows'] for r in results),'bytes_decoded':size,'archive_bytes':len(b),'member_payload_reads':2,'locked_member_reads':0,'development_member_reads':0,'new_fits':0,'model_inference':0,'elapsed_seconds':time.monotonic()-start});print(json.dumps(results))
  except BaseException as e:dump('failure.json',{'status':'FAILED_STOP_NO_RETRY','type':type(e).__name__,'error':str(e)});raise
  finally:signal.setitimer(signal.ITIMER_REAL,0)
if __name__=='__main__':main()
