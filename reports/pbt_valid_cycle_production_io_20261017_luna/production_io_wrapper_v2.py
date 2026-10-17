#!/usr/bin/env python3
"""Bounded one-use production IO wrapper; inactive until a matching root GO."""
import argparse, hashlib, importlib.util, json, os, pathlib, resource, stat, subprocess, sys, tempfile, uuid
from datetime import datetime, timezone
ROOT='/home/yndx/zxk/rul'
OUT=ROOT+'/reports/pbt_valid_cycle_production_io_20261017_luna'
SPEC=OUT+'/exact_spec_v2.json'
HELPER=ROOT+'/reports/pbt_valid_cycle_stage_v3_luna/valid_cycle_structure_scanner_v3.py'
GO=OUT+'/ROOT_GO.json'
CLAIM=OUT+'/shard1.invocation_v2.claim'
START=OUT+'/shard1.worker_v2.started'
WORKER_FAILURE=OUT+'/shard1.worker_v2_failure.json'
RECEIPT=OUT+'/shard1.v2.receipt.json'
RESULT=OUT+'/shard1.v2.result.json'
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

def worker_scan():
 specmod=importlib.util.spec_from_file_location('frozen_scanner',HELPER)
 helper=importlib.util.module_from_spec(specmod); specmod.loader.exec_module(helper)
 original_read=os.read
 consumed=0
 def capped_read(fd,n):
  nonlocal consumed
  if n<0 or consumed+n>MAX_TOTAL_READ: raise RuntimeError('aggregate_read_cap_exceeded')
  b=original_read(fd,n); consumed+=len(b)
  return b
 # helper 的所有生产读取及 EOF probe 共用同一计数器。
 helper.os.read=capped_read
 results=[]
 try:
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
  out={'status':'VALID_CYCLE_STRUCTURE_SCAN_PASS','proposal_shard_id':'VALID_CYCLE_PROPOSED_SHARD_1','cells':results,'bytes_read_including_eof_probes':consumed,'max_total_read_bytes':MAX_TOTAL_READ,'note':'仅结构计数，不解码数值，不做模型评估。'}
  publish_exclusive(RESULT,(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode())
  return consumed
 except BaseException as e:
  failure={'status':'WORKER_FAILED_STOP_NO_RETRY','run_id':ACTIVE_RUN_ID,'error_type':type(e).__name__,'error':str(e)[:2000],'binary_read_bytes':consumed}
  try: write_exclusive(WORKER_FAILURE,(json.dumps(failure,sort_keys=True,indent=2)+'\n').encode())
  except Exception: pass
  raise

def read_json_nofollow(path, cap=65536):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  if not stat.S_ISREG(os.fstat(fd).st_mode): raise RuntimeError('json_target_not_regular')
  raw=os.read(fd,cap+1)
 finally: os.close(fd)
 if len(raw)>cap: raise RuntimeError('json_too_large')
 return json.loads(raw)

def set_worker_limits():
 # 限制直接启动的 worker 本身；父 launcher 也对其子进程设置同样上限。
 resource.setrlimit(resource.RLIMIT_CPU,(120,120))
 resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
 resource.setrlimit(resource.RLIMIT_NOFILE,(32,32))
 resource.setrlimit(resource.RLIMIT_FSIZE,(2*1024**2,2*1024**2))

def worker_authorize(run_id, expected_go_sha):
 global ACTIVE_RUN_ID
 g=go_check()
 actual_go_sha=sha_file(GO)
 if actual_go_sha!=expected_go_sha: raise RuntimeError('worker_go_sha_parameter_mismatch')
 if not isinstance(run_id,str) or len(run_id)!=32: raise RuntimeError('worker_run_id_invalid')
 try: claim=read_json_nofollow(CLAIM)
 except FileNotFoundError: raise RuntimeError('parent_claim_missing')
 expected={'status':'CONSUMED_BEFORE_FIRST_CONTENT_BYTE','go_sha256':actual_go_sha,'run_id':run_id,'wrapper_sha256':sha_file(__file__),'spec_sha256':sha_file(SPEC),'helper_sha256':sha_file(HELPER)}
 for key,value in expected.items():
  if claim.get(key)!=value: raise RuntimeError('worker_parent_claim_'+key+'_mismatch')
 if os.path.exists(START): raise RuntimeError('worker_start_marker_already_exists')
 # 启动标记在 worker 设置资源上限、读取任何真实文件前 create-only + fsync。
 write_exclusive(START,(json.dumps({'status':'WORKER_STARTED','go_sha256':actual_go_sha,'run_id':run_id,'wrapper_sha256':expected['wrapper_sha256']},sort_keys=True)+'\n').encode())
 ACTIVE_RUN_ID=run_id
 set_worker_limits()
 return g

def worker_entry(run_id, go_sha):
 worker_authorize(run_id,go_sha)
 return worker_scan()
ACTIVE_RUN_ID='UNSET'

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
 ap=argparse.ArgumentParser(); ap.add_argument('--self-test',action='store_true'); ap.add_argument('--worker',action='store_true'); ap.add_argument('--run-id'); ap.add_argument('--go-sha256'); a=ap.parse_args()
 if a.self_test:
  # 只验证两个 worker 拒绝门；不调用 worker_scan、不打开任何生产曲线。
  with tempfile.TemporaryDirectory(prefix='pbt-worker-gate-synth-') as td:
   global OUT,GO,CLAIM,START,WORKER_FAILURE
   old=(OUT,GO,CLAIM,START,WORKER_FAILURE)
   try:
    OUT=td; os.makedirs(OUT,exist_ok=True); GO=OUT+'/ROOT_GO.json'; CLAIM=OUT+'/claim'; START=OUT+'/started'; WORKER_FAILURE=OUT+'/failure.json'
    rejected_no_go=False
    try: worker_authorize('1'*32,'0'*64)
    except Exception: rejected_no_go=True
    assert rejected_no_go and not os.path.exists(START)
    review=OUT+'/review.md'; write_exclusive(review,b'synthetic reviewer receipt')
    g={'status':'ROOT_GO','binary_execution_authorized':True,'proposal_shard_id':'VALID_CYCLE_PROPOSED_SHARD_1','cells':[c['cell'] for c in CELLS],'wrapper_sha256':sha_file(__file__),'spec_sha256':sha_file(SPEC),'helper_sha256':sha_file(HELPER),'review_path':review,'review_sha256':sha_file(review),'max_invocations':1,'max_total_read_bytes':MAX_TOTAL_READ,'max_file_bytes':MAX_FILE}
    write_exclusive(GO,(json.dumps(g,sort_keys=True)+'\n').encode()); go_sha=sha_file(GO)
    rejected_no_claim=False
    try: worker_authorize('2'*32,go_sha)
    except RuntimeError as e: rejected_no_claim=str(e)=='parent_claim_missing'
    assert rejected_no_claim and not os.path.exists(START)
   finally: OUT,GO,CLAIM,START,WORKER_FAILURE=old
  print('PASS synthetic worker gates: no-GO and valid-GO/no-parent-claim rejected before start marker; production files opened=0')
  return 0
 if a.worker:
  try:
   if not a.run_id or not a.go_sha256: raise RuntimeError('worker_parent_parameters_required')
   worker_entry(a.run_id,a.go_sha256); return 0
  except BaseException as e:
   print('STOP_WORKER:',type(e).__name__,str(e),file=sys.stderr); return 2
 try:
  go_check(); go_sha=sha_file(GO); run_id=uuid.uuid4().hex
  claim={'status':'CONSUMED_BEFORE_FIRST_CONTENT_BYTE','at_utc':datetime.now(timezone.utc).isoformat(),'proposal_shard_id':'VALID_CYCLE_PROPOSED_SHARD_1','go_sha256':go_sha,'run_id':run_id,'wrapper_sha256':sha_file(__file__),'spec_sha256':sha_file(SPEC),'helper_sha256':sha_file(HELPER)}
  write_exclusive(CLAIM,(json.dumps(claim,sort_keys=True)+'\n').encode())
  def limits():
   resource.setrlimit(resource.RLIMIT_CPU,(120,120)); resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3)); resource.setrlimit(resource.RLIMIT_NOFILE,(32,32)); resource.setrlimit(resource.RLIMIT_FSIZE,(2*1024**2,2*1024**2))
  cmd=[sys.executable,'-I','-S',os.path.abspath(__file__),'--worker','--run-id',run_id,'--go-sha256',go_sha]
  p=subprocess.run(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180,preexec_fn=limits,close_fds=True)
  if p.returncode!=0: raise RuntimeError('worker_exit_'+str(p.returncode)+':'+p.stderr.decode('utf-8','replace')[-2000:])
  result=read_json_nofollow(RESULT,2*1024**2)
  rec={'status':'SUCCESS','result_path':RESULT,'result_sha256':sha_file(RESULT),'binary_read_bytes':result['bytes_read_including_eof_probes'],'invocation_consumed':True,'run_id':run_id,'go_sha256':go_sha}
  write_exclusive(RECEIPT,(json.dumps(rec,sort_keys=True,indent=2)+'\n').encode()); return 0
 except BaseException as e:
  count='unknown_if_resource_killed'
  try:
   wf=read_json_nofollow(WORKER_FAILURE,16384); count=wf.get('binary_read_bytes','unknown_if_worker_failure')
  except Exception: pass
  rec={'status':'FAILED_STOP_NO_RETRY','error_type':type(e).__name__,'error':str(e)[:3000],'at_utc':datetime.now(timezone.utc).isoformat(),'invocation_consumed':os.path.exists(CLAIM),'binary_read_bytes':count}
  if os.path.exists(CLAIM):
   try: write_exclusive(RECEIPT,(json.dumps(rec,sort_keys=True,indent=2)+'\n').encode())
   except FileExistsError: pass
   except Exception: pass
  print('STOP:',type(e).__name__,str(e),file=sys.stderr); return 2
if __name__=='__main__': raise SystemExit(main())