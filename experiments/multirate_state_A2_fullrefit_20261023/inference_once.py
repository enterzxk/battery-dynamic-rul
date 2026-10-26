import sys,json,pathlib,hashlib,fcntl,contextlib,subprocess,os,datetime
p=pathlib.Path(sys.argv[1]);g=json.loads(p.read_text());r=pathlib.Path('/home/yndx/zxk/rul')
assert hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()==g['execution_wrapper']['sha256']
assert json.loads((r/'automation/state/coordinator.json').read_text())['owner']==g['owner_thread_id']
assert json.loads((r/'docs/CODEX_RETAKEOVER_20261023.json').read_text())['dsh_control_stopped'] is True
c=pathlib.Path(g['execution_claim']);c.parent.mkdir(exist_ok=True)
with c.open('x') as f:json.dump({'pid':os.getpid(),'GO_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},f)
with contextlib.ExitStack() as stack:
 for rel in ['automation/state/online_survival_cpu.lock','automation/locks/isu_irregular_rul_cpu.lock']:
  f=stack.enter_context((r/rel).open('a+'));fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 env=dict(os.environ,OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4')
 z=subprocess.run([sys.executable,'-u',str(r/'experiments/multirate_state_A2_20261022/a2_infer.py'),'--go',str(p),'--threads','4'],env=env)
 sys.exit(z.returncode)
