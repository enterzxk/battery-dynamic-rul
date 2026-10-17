#!/usr/bin/env python3
"""Bounded one-use production IO wrapper; inactive until a matching root GO."""
import argparse, hashlib, importlib.util, json, os, pathlib, resource, stat, subprocess, sys, tempfile, time, traceback
from datetime import datetime, timezone
ROOT='/home/yndx/zxk/rul'
OUT=ROOT+'/reports/pbt_valid_cycle_production_io_20261017_luna'
SPEC=OUT+'/exact_spec.json'
HELPER=ROOT+'/reports/pbt_valid_cycle_stage_v3_luna/valid_cycle_structure_scanner_v3.py'
GO=OUT+'/ROOT_GO.json'
CLAIM=OUT+'/shard1.invocation.claim'
RECEIPT=OUT+'/shard1.receipt.json'
RESULT=OUT+'/shard1.result.json'
MAX_FILE=64*1024*1024
MAX_TOTAL_READ=256*1024*1024
CELLS=[
{'cell':'HUST_6-8.pkl','declared_path':'/home/yndx/zxk/rul/data/source_audit/stage_v11_hust_v11_labels/HUST/HUST_6-8.pkl','canonical_target':'/home/yndx/zxk/rul/data/raw/HUST/extracted_v9/HUST/HUST_6-8.pkl','symlink_target':'/home/yndx/zxk/rul/data/raw/HUST/extracted_v9/HUST/HUST_6-8.pkl','sha256':'e8c61968847194e784e2eef6a43e91fcd675492460a7701fc4c50fff5eb8f19d','size':61269686,'st_dev':64517,'st_ino':42206954,'st_nlink':1,'st_mtime_ns':1792081780295299359,'st_ctime_ns':1792081780295299359},
{'cell':'HUST_3-8.pkl','declared_path':'/home/yndx/zxk/rul/data/source_audit/stage_v11_hust_v11_labels/HUST/HUST_3-8.pkl','canonical_target':'/home/yndx/zxk/rul/data/raw/HUST/extracted_v9/HUST/HUST_3-8.pkl','symlink_target':'/home/yndx/zxk/rul/data/raw/HUST/extracted_v9/HUST/HUST_3-8.pkl','sha256':'c541998118e4a245d8cd3c4c60f1057e38a56122cb463351b25dc51edf4f0f44','size':56036771,'st_dev':64517,'st_ino':42206932,'st_nlink':1,'st_mtime_ns':1792081776567370825,'st_ctime_ns':1792081776567370825},
{'cell':'HUST_2-3.pkl','declared_path':'/home/yndx/zxk/rul/data/source_audit/stage_v11_hust_v11_labels/HUST/HUST_2-3.pkl','canonical_target':'/home/yndx/zxk/rul/data/raw/HUST/extracted_v9/HUST/HUST_2-3.pkl','symlink_target':'/home/yndx/zxk/rul/data/raw/HUST/extracted_v9/HUST/HUST_2-3.pkl','sha256':'d11135feb78a51ad1279c379053eb37bdb96e3fd3b99234c331c6b80da8de0b9','size':53339775,'st_dev':64517,'st_ino':42206919,'st_nlink':1,'st_mtime_ns':1792081774607408399,'st_ctime_ns':1792081774607408399},
{'cell':'HUST_9-1.pkl','declared_path':'/home/yndx/zxk/rul/data/source_audit/stage_v11_hust_v11_labels/HUST/HUST_9-1.pkl','canonical_target':'/home/yndx/zxk/rul/data/raw/HUST/extracted_v9/HUST/HUST_9-1.pkl','symlink_target':'/home/yndx/zxk/rul/data/raw/HUST/extracted_v9/HUST/HUST_9-1.pkl','sha256':'d388bd0fdea2e8c25d251bdfcf7f64d1db4bd8b4670f95c07eb0f5ec3ea457fd','size':53792090,'st_dev':64517,'st_ino':42206971,'st_nlink':1,'st_mtime_ns':1792081783227243151,'st_ctime_ns':1792081783227243151}]

def sha_file(p):
 h=hashlib.sha256()
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  if not stat.S_ISREG(os.fstat(fd).st_mode): raise RuntimeError('hash_target_not_regular')
  with os.fdopen(fd,'rb',closefd=False) as f:
   for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 finally: os.close(fd)
 return h.hexdigest()
def write_exclusive(path, data):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:
  view=memoryview(data)
  while view:
   n=os.write(fd,view); view=view[n:]
  os.fsync(fd)
 finally: os.close(fd)
 d=os.open(os.path.dirname(path),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW); os.fsync(d); os.close(d)
def publish_exclusive(path, data):
 tmp=path+'.tmp.'+str(os.getpid())
 write_exclusive(tmp,data)
 os.link(tmp,path,follow_symlinks=False)
 os.unlink(tmp)
 d=os.open(os.path.dirname(path),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW); os.fsync(d); os.close(d)
def open_dir_path(path):
 """从 / 开始逐段以 dirfd + O_NOFOLLOW 打开 canonical 目录。"""
 parts=[x for x in pathlib.PurePosixPath(path).parts if x not in ('/','')]
 fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:
  for part in parts:
   n=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
   os.close(fd); fd=n
  return fd
 except:
  os.close(fd); raise
def parent_and_name(path):
 p=pathlib.PurePosixPath(path)
 return str(p.parent),p.name
def open_declared_symlink(cell):
 """先用 dirfd 核对指定符号链接，再只打开 canonical 无链接目标。"""
 dp,dn=parent_and_name(cell['declared_path'])
 dfd=open_dir_path(dp)
 try:
  st=os.stat(dn,dir_fd=dfd,follow_symlinks=False)
  if not stat.S_ISLNK(st.st_mode): raise RuntimeError('declared_entry_not_symlink')
  target=os.readlink(dn,dir_fd=dfd)
  if target!=cell['symlink_target']: raise RuntimeError('declared_symlink_target_mismatch')
 finally: os.close(dfd)
 cp,cn=parent_and_name(cell['canonical_target'])
 cfd=open_dir_path(cp)
 try:
  fd=os.open(cn,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=cfd)
 finally: os.close(cfd)
 st=os.fstat(fd)
 exp=(cell['st_dev'],cell['st_ino'],cell['size'],cell['st_mtime_ns'],cell['st_ctime_ns'],cell['st_nlink'])
 got=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns,st.st_nlink)
 if not stat.S_ISREG(st.st_mode) or st.st_size>MAX_FILE or got!=exp:
  os.close(fd); raise RuntimeError('canonical_fd_stat_identity_mismatch')
 return fd

def worker():
 specmod=importlib.util.spec_from_file_location('frozen_scanner',HELPER)
 helper=importlib.util.module_from_spec(specmod); specmod.loader.exec_module(helper)
 original_read=os.read
 consumed=0
 def capped_read(fd,n):
  nonlocal consumed
  if n<0 or consumed+n>MAX_TOTAL_READ: raise RuntimeError('aggregate_read_cap_exceeded')
  b=original_read(fd,n); consumed+=len(b)
  return b
 # helper's own reads, including its one-byte EOF probe, are counted globally.
 helper.os.read=capped_read
 results=[]
 for c in CELLS:
  fd=open_declared_symlink(c)
  try:
   before=os.fstat(fd)
   res=helper.structural_count(fd,c['size'],c['sha256'],'cycle_data')
   after=os.fstat(fd)
   ident=lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns,x.st_nlink)
   if ident(before)!=ident(after): raise RuntimeError('same_fd_stat_changed')
   if res['bytes']!=c['size'] or res['sha256']!=c['sha256']: raise RuntimeError('helper_receipt_mismatch')
   results.append({'cell':c['cell'],'valid_cycle_number':res['valid_cycle_number'],'bytes':res['bytes'],'sha256':res['sha256'],'stat_identity':list(ident(after))})
  finally: os.close(fd)
 if consumed>MAX_TOTAL_READ: raise RuntimeError('aggregate_read_cap_exceeded')
 out={'status':'VALID_CYCLE_STRUCTURE_SCAN_PASS','proposal_shard_id':'VALID_CYCLE_PROPOSED_SHARD_1','cells':results,'bytes_read_including_eof_probes':consumed,'max_total_read_bytes':MAX_TOTAL_READ,'note':'仅为结构计数；不解码数值、不做模型评估。'}
 publish_exclusive(RESULT,(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode())

def go_check():
 fd=os.open(GO,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  if not stat.S_ISREG(os.fstat(fd).st_mode): raise RuntimeError('go_not_regular')
  raw=os.read(fd,65537)
 finally: os.close(fd)
 if len(raw)>65536: raise RuntimeError('go_file_too_large')
 g=json.loads(raw)
 if g.get('status')!='ROOT_GO' or g.get('binary_execution_authorized') is not True or g.get('proposal_shard_id')!='VALID_CYCLE_PROPOSED_SHARD_1': raise RuntimeError('root_go_missing_or_inactive')
 if g.get('cells')!=[c['cell'] for c in CELLS]: raise RuntimeError('root_go_exact_cells_mismatch')
 expected={'wrapper_sha256':sha_file(__file__),'spec_sha256':sha_file(SPEC),'helper_sha256':sha_file(HELPER)}
 for k,v in expected.items():
  if g.get(k)!=v: raise RuntimeError('root_go_'+k+'_mismatch')
 rp=g.get('review_path'); rh=g.get('review_sha256')
 if not isinstance(rp,str) or not rp.startswith(OUT+'/') or not isinstance(rh,str) or sha_file(rp)!=rh: raise RuntimeError('root_review_binding_invalid')
 if g.get('max_invocations')!=1 or g.get('max_total_read_bytes')!=MAX_TOTAL_READ or g.get('max_file_bytes')!=MAX_FILE: raise RuntimeError('root_go_budget_mismatch')
 return g

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--self-test',action='store_true'); ap.add_argument('--worker',action='store_true'); a=ap.parse_args()
 if a.self_test:
  # 唯一合成验证：仅临时目录内造小型 protocol-4 结构样本并检查链接/FD/EOF/hash路径。
  import tempfile,shutil
  with tempfile.TemporaryDirectory(prefix='pbt-io-synth-') as td:
   os.makedirs(td+'/canonical/a'); os.makedirs(td+'/declared/a')
   raw=b'\x80\x04\x95\x11\x00\x00\x00\x00\x00\x00\x00}\x8c\x0acycle_data]\x94s.'
   real=td+'/canonical/a/sample.pkl'; open(real,'wb').write(raw)
   os.symlink(real,td+'/declared/a/sample.pkl')
   # 临时映射根只用于验证逐段目录打开与link target验证。
   c={'declared_path':td+'/declared/a/sample.pkl','canonical_target':real,'symlink_target':real,'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'st_dev':os.stat(real).st_dev,'st_ino':os.stat(real).st_ino,'st_nlink':1,'st_mtime_ns':os.stat(real).st_mtime_ns,'st_ctime_ns':os.stat(real).st_ctime_ns}
   fd=open_declared_symlink(c)
   try:
    specmod=importlib.util.spec_from_file_location('synthetic_scanner',HELPER); h=importlib.util.module_from_spec(specmod); specmod.loader.exec_module(h)
    got=h.structural_count(fd,len(raw),c['sha256'],'cycle_data')
   finally: os.close(fd)
   assert got['valid_cycle_number']==0 and got['bytes']==len(raw)
  print('PASS synthetic-only symlink-dirfd/same-FD/helper-hash/EOF-path; production files opened=0')
  return 0
 if a.worker:
  worker(); return 0
 charged=False
 try:
  go_check()
  # O_EXCL claim is durable and precedes worker startup, hence every failure consumes the one call.
  claim={'status':'CONSUMED_BEFORE_FIRST_CONTENT_BYTE','at_utc':datetime.now(timezone.utc).isoformat(),'proposal_shard_id':'VALID_CYCLE_PROPOSED_SHARD_1'}
  write_exclusive(CLAIM,(json.dumps(claim,sort_keys=True)+'\n').encode())
  # launcher 在独立受限子进程运行；worker 异常/超时均由父进程落失败收据。
  def limits():
   resource.setrlimit(resource.RLIMIT_CPU,(3600,3600)); resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3)); resource.setrlimit(resource.RLIMIT_NOFILE,(32,32)); resource.setrlimit(resource.RLIMIT_FSIZE,(2*1024**2,2*1024**2))
  p=subprocess.run([sys.executable,os.path.abspath(__file__),'--worker'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=7200,preexec_fn=limits,close_fds=True)
  if p.returncode!=0: raise RuntimeError('worker_exit_'+str(p.returncode)+':'+p.stderr.decode('utf-8','replace')[-2000:])
  # worker has atomically published result. Parent writes final success receipt create-only.
  r=json.load(open(RESULT,'r',encoding='utf-8'))
  rec={'status':'SUCCESS','result_path':RESULT,'result_sha256':sha_file(RESULT),'binary_read_bytes':r['bytes_read_including_eof_probes'],'invocation_consumed':True}
  write_exclusive(RECEIPT,(json.dumps(rec,sort_keys=True,indent=2)+'\n').encode()); return 0
 except BaseException as e:
  rec={'status':'FAILED_STOP_NO_RETRY','error_type':type(e).__name__,'error':str(e)[:3000],'at_utc':datetime.now(timezone.utc).isoformat(),'invocation_consumed':os.path.exists(CLAIM),'binary_read_bytes':'unknown_if_worker_failed'}
  if os.path.exists(CLAIM):
   try: write_exclusive(RECEIPT,(json.dumps(rec,sort_keys=True,indent=2)+'\n').encode())
   except FileExistsError: pass
   except Exception: pass
  print('STOP:',type(e).__name__,str(e),file=sys.stderr); return 2
if __name__=='__main__': raise SystemExit(main())

