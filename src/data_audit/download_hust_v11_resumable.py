#!/usr/bin/env python3
# Resumable official Zenodo artifact fetch; downloads only the requested public v11 HUST file.
import concurrent.futures, datetime, hashlib, json, os, pathlib, threading, time, urllib.error, urllib.request
ROOT=pathlib.Path('/home/yndx/zxk/rul')
DEST=ROOT/'data/raw/HUST/HUST_v11.zip'
PARTDIR=ROOT/'data/raw/HUST/.HUST_v11.zip.parts'
LOGDIR=ROOT/'reports/data_same_version_staging'
URL='https://zenodo.org/api/records/19688272/files/HUST.zip/content'
EXPECTED_SIZE=1393245274
EXPECTED_MD5='de6b6d1b0b20616fbb96c72f3231c082'
CHUNK_SIZE=16*1024*1024
MAX_WORKERS=4

def sha(path,kind='sha256'):
 h=hashlib.new(kind)
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(8*1024*1024),b''): h.update(block)
 return h.hexdigest()

def main():
 if DEST.exists(): raise RuntimeError('create-only target already exists: '+str(DEST))
 PARTDIR.mkdir(exist_ok=True); LOGDIR.mkdir(parents=True,exist_ok=True)
 runid=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
 logpath=LOGDIR/('download_v11_hust_'+runid+'.jsonl')
 failpath=LOGDIR/('download_v11_hust_'+runid+'_failure.json')
 lock=threading.Lock()
 def event(x):
  x['time_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
  with lock:
   with open(logpath,'a',encoding='utf-8') as f: f.write(json.dumps(x,ensure_ascii=False)+'\n')
 proxy=urllib.request.ProxyHandler({'http':'http://127.0.0.1:29137','https':'http://127.0.0.1:29137'})
 opener=urllib.request.build_opener(proxy)
 n=(EXPECTED_SIZE+CHUNK_SIZE-1)//CHUNK_SIZE
 def getpart(i):
  start=i*CHUNK_SIZE; end=min(EXPECTED_SIZE-1,start+CHUNK_SIZE-1)
  p=PARTDIR/('segment_%04d.part'%i); expected=end-start+1
  have=p.stat().st_size if p.exists() else 0
  if have>expected: raise RuntimeError('oversized partial segment %d (%d>%d)'%(i,have,expected))
  if have==expected:
   event({'segment':i,'state':'already_complete','bytes':have})
   return
  for attempt in range(1,9):
   cur=start+have
   req=urllib.request.Request(URL,headers={'User-Agent':'battery-rul-data-audit/1.0','Range':'bytes=%d-%d'%(cur,end),'Accept-Encoding':'identity'})
   try:
    with opener.open(req,timeout=120) as r:
     cr=r.headers.get('Content-Range','')
     if r.status!=206 or not cr.startswith('bytes %d-%d/'%(cur,end)):
      raise RuntimeError('unexpected range response status=%s content-range=%r'%(r.status,cr))
     data=r.read()
     if len(data)!=(end-cur+1): raise RuntimeError('range body byte count mismatch for segment %d'%i)
    mode='ab' if have else 'wb'
    with open(p,mode) as f: f.write(data); f.flush(); os.fsync(f.fileno())
    have=p.stat().st_size
    if have!=expected: raise RuntimeError('partial segment length mismatch after append')
    event({'segment':i,'state':'complete','bytes':have,'range':[start,end],'attempt':attempt})
    return
   except Exception as e:
    event({'segment':i,'state':'retry_or_failure','attempt':attempt,'bytes_already_saved':have,'error_type':type(e).__name__,'error':str(e)})
    if attempt==8: raise
    time.sleep(min(2**(attempt-1),20))
 with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
  list(pool.map(getpart,range(n)))
 # Assemble to create-only timestamped temporary path; do not replace failed artifacts.
 assembly=DEST.with_name(DEST.name+'.assembling.'+runid+'.part')
 with open(assembly,'xb') as out:
  for i in range(n):
   p=PARTDIR/('segment_%04d.part'%i)
   with open(p,'rb') as f:
    for block in iter(lambda:f.read(8*1024*1024),b''): out.write(block)
  out.flush(); os.fsync(out.fileno())
 size=assembly.stat().st_size; actual_md5=sha(assembly,'md5'); actual_sha=sha(assembly,'sha256')
 if size!=EXPECTED_SIZE or actual_md5!=EXPECTED_MD5:
  failure={'run_id':runid,'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'url':URL,'expected_size':EXPECTED_SIZE,'actual_size':size,'expected_md5':EXPECTED_MD5,'actual_md5':actual_md5,'assembly_part':str(assembly),'published':False}
  failpath.write_text(json.dumps(failure,indent=2)+'\n',encoding='utf-8')
  raise RuntimeError('final size/MD5 mismatch; assembly retained')
 if DEST.exists(): raise RuntimeError('create-only target appeared before publication')
 os.rename(assembly,DEST)
 result={'run_id':runid,'url':URL,'record_id':19688272,'license':'CC BY 4.0 (Zenodo metadata)','expected_size':EXPECTED_SIZE,'actual_size':DEST.stat().st_size,'expected_md5':EXPECTED_MD5,'actual_md5':actual_md5,'sha256':actual_sha,'download_log':str(logpath),'part_directory':str(PARTDIR),'published_path':str(DEST),'published':True,'single_artifact_budget_bytes':8589934592,'phase_total_budget_bytes':21474836480,'prior_phase_transfer_estimate_bytes':1563436601,'this_artifact_bytes':size,'combined_estimate_bytes':1563436601+size,'max_workers':MAX_WORKERS,'chunk_size_bytes':CHUNK_SIZE}
 resultpath=LOGDIR/('download_v11_hust_'+runid+'_result.json')
 resultpath.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':
 try: main()
 except Exception as e:
  print(json.dumps({'error_type':type(e).__name__,'error':str(e)},ensure_ascii=False))
  raise
