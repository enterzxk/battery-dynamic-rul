"""Inactive root launcher: exact independent review + separate root decision required."""
import os,stat,json,hashlib,pathlib,subprocess,fcntl,time,datetime,sys
R=pathlib.Path('/home/yndx/zxk/rul');REL='reports/pbt_stage1_dkp_keys_v4_root';ME='01a1474d-7d3f-7113-b428-8ab465fac02e'
CODE_SHA='c2c8600cb990203da33542f271f0a5d679f8b5df70037ac4ee05d7a98d417bcb'
SPEC_SHA='9d3df69e12a78a6bdadec937b1aafa1cf4dede2375f97979a6ca46af5972f403'
PY='/home/yndx/miniconda3/envs/a40_env/bin/python'
def sha(b):return hashlib.sha256(b).hexdigest()
def sig(st):return (st.st_dev,st.st_ino,st.st_mode,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
def open_parent(p):
 p=pathlib.Path(p);assert p.is_absolute() and '..' not in p.parts
 fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:
  for part in p.parts[1:-1]:
   nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=nxt
  return fd,p.name
 except BaseException:os.close(fd);raise
def read(p,cap=65536):
 parent,leaf=open_parent(p);fd=None
 try:
  fd=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent);st=os.fstat(fd);assert stat.S_ISREG(st.st_mode) and st.st_size<=cap
  out=b''
  while True:
   b=os.read(fd,min(65536,cap-len(out)+1))
   if not b:break
   out+=b;assert len(out)<=cap
  assert len(out)==st.st_size and sig(os.fstat(fd))==sig(st) and sig(os.stat(leaf,dir_fd=parent,follow_symlinks=False))==sig(st)
  return out
 finally:
  if fd is not None:os.close(fd)
  os.close(parent)
def create_only(p,obj):
 raw=(json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode();assert len(raw)<=65536
 parent,leaf=open_parent(p);fd=None
 try:
  fd=os.open(leaf,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
  v=memoryview(raw)
  while v:
   n=os.write(fd,v);assert n>0;v=v[n:]
  os.fsync(fd);os.fsync(parent)
 finally:
  if fd is not None:os.close(fd)
  os.close(parent)
 return sha(raw)
def main():
 assert sys.version_info[:2]==(3,9) and sys.flags.isolated==1 and sys.flags.no_site==1
 assert __file__==str(R/REL/'root_single_run_launcher_v4.py')
 p=R/REL;code=read(p/'stage1_dkp_key_scanner_v4.py');spec=read(p/'pbt_stage1_dkp_key_spec_v4.json');go=read(p/'root_go.json');template=read(p/'root_go_template_v4.json');decision_b=read(p/'root_execution_decision.json');decision=json.loads(decision_b)
 assert sha(code)==CODE_SHA and sha(spec)==SPEC_SHA and go==template
 review_path=R/'reports/pbt_stage1_dkp_independent_v4_luna/review.json';review_b=read(review_path);review=json.loads(review_b)
 assert review['status']=='PASS_BOUNDED_DKP_METADATA_STAGE' and review['scanner_sha256']==CODE_SHA and review['spec_sha256']==SPEC_SHA
 want={'stage_id':'PBT_STAGE1_DKP_KEYS_V4','decision':'GO_ONE_DKP_METADATA_SCANNER_INVOCATION_ONLY','owner':ME,'scanner_sha256':CODE_SHA,'spec_sha256':SPEC_SHA,'root_go_sha256':sha(go),'launcher_sha256':sha(read(p/'root_single_run_launcher_v4.py')),'independent_review_sha256':sha(review_b),'single_run_budget':1,'model_gates_remain_closed':True,'retry_after_any_invocation':False}
 assert decision==want
 lock=R/'automation/state/coordinator.lock';start=time.monotonic();result=None;failure=None
 with lock.open('a') as f:
  fcntl.flock(f,fcntl.LOCK_EX);state=json.loads(read(R/'automation/state/coordinator.json'));assert state['owner']==ME and state['takeover_verified'] is True
  # This immutable, fsynced claim consumes the invocation even if exec never starts.
  claim={'stage_id':'PBT_STAGE1_DKP_KEYS_V4','status':'INVOCATION_BUDGET_CONSUMED_BEFORE_CHILD_START','invocation_budget_remaining':0,'candidate_member_reads_max':1,'scanner_sha256':CODE_SHA,'spec_sha256':SPEC_SHA,'go_sha256':sha(go),'decision_sha256':sha(decision_b),'independent_review_sha256':sha(review_b),'claimed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'retry_allowed':False}
  claim_sha=create_only(p/'root_invocation_budget_claim.json',claim)
  try:result=subprocess.run([PY,'-I','-S',str(p/'stage1_dkp_key_scanner_v4.py')],cwd=str(R),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=25)
  except BaseException as e:failure={'type':type(e).__name__,'message':str(e)[:1000]}
  output=None
  try:
   b=read(p/'output/key_presence_manifest.json',32768);output={'path':str(p/'output/key_presence_manifest.json'),'sha256':sha(b),'bytes':len(b),'status':json.loads(b)['status']}
  except (OSError,ValueError,KeyError,AssertionError) as e:output={'status':'OUTPUT_NOT_VALIDATED','error':type(e).__name__}
  outcome={'stage_id':'PBT_STAGE1_DKP_KEYS_V4','claim_sha256':claim_sha,'returncode':result.returncode if result is not None else None,'launcher_exception':failure,'elapsed_seconds':round(time.monotonic()-start,6),'output':output,'stdout':result.stdout.decode('utf-8','replace') if result else '', 'stderr':result.stderr.decode('utf-8','replace') if result else '', 'invocation_budget_remaining':0,'retry_allowed':False,'new_fits':0,'optimizer_steps':0,'PBT_forward':0,'metrics':0,'test':0,'scientific_acceptance':False}
  create_only(p/'root_execution_receipt.json',outcome)
  print(json.dumps(outcome));return 0 if result is not None and result.returncode==0 and output['status']=='STATIC_DKP_ROOT_KEY_PRESENCE_AND_ARRAY_BUILD_OFFSETS_ONLY' else 2
if __name__=='__main__':raise SystemExit(main())

