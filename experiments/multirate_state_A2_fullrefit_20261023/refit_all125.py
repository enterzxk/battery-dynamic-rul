"""A2 final all-C1/C2 refit; frozen selected steps, no new model selection."""
import argparse,contextlib,datetime,fcntl,hashlib,json,os,pathlib,signal,sys,time,traceback
ROOT=pathlib.Path('/home/yndx/zxk/rul')
HERE=pathlib.Path(__file__).resolve().parent
OLD=ROOT/'experiments/multirate_state_A2_20261022'
OWNER='01a15c3a-1a06-7d61-8517-27b70b246183'
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def write(p,x):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False));os.replace(t,p)
def all_fit_indices(data,np):
 idx=np.arange(data.n_cells,dtype=np.int64)
 assert len(set(data.train_index.tolist())|set(data.val_index.tolist()))==data.n_cells
 assert not(set(data.train_index.tolist())&set(data.val_index.tolist()))
 return idx

def run(go_path):
 g=json.loads(pathlib.Path(go_path).read_text());assert g['status']=='APPROVED' and g['allow_fit'] is True
 assert g['owner_thread_id']==OWNER and g['max_fits']==3 and g['allow_C4'] is False
 assert g['steps']=={'full':550,'time':100,'noRPTupdate':550}
 recpath=pathlib.Path(g['receipt_path']);out=pathlib.Path(g['output_dir'])
 assert not recpath.exists() and not out.exists()
 for rel,h in g['code_sha256'].items():assert sha(ROOT/rel)==h,rel
 assert sha(g['prepared_manifest'])==g['prepared_manifest_sha256']
 hand=json.loads((ROOT/'docs/CODEX_RETAKEOVER_20261023.json').read_text())
 assert hand['dsh_control_stopped'] is True and hand['owner_thread_id']==OWNER
 owner=json.loads((ROOT/'automation/state/coordinator.json').read_text());assert owner['owner']==OWNER
 age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(owner['heartbeat_utc'])).total_seconds()
 assert 0<=age<1800,'coordinator heartbeat stale'
 claim=pathlib.Path(g['claim_path']);claim.parent.mkdir(parents=True,exist_ok=True)
 with claim.open('x') as f:json.dump({'GO_sha256':sha(go_path),'pid':os.getpid()},f)
 rec={'status':'STARTED','GO_sha256':sha(go_path),'fits_started':0,'fits_completed':0,'optimizer_steps':0,'C4_reads':0,'C3_reads':0,'raw_archive_reads':0,'checkpoint_reads':0,'pid':os.getpid(),'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 write(recpath,rec);start=time.time()
 def timeout(*_):raise TimeoutError('GO runtime budget expired')
 signal.signal(signal.SIGALRM,timeout);signal.alarm(int(g['max_seconds']))
 try:
  with contextlib.ExitStack() as stack:
   for rel in ['automation/state/online_survival_cpu.lock','automation/locks/isu_irregular_rul_cpu.lock']:
    f=stack.enter_context((ROOT/rel).open('a+'));fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
   import numpy as np,torch
   sys.path.insert(0,str(OLD));import a2_fastdata as fd
   from a2_model import build_model
   import random
   torch.set_num_threads(4);torch.set_num_interop_threads(1)
   man=json.loads(pathlib.Path(g['prepared_manifest']).read_text());assert sha(man['prepared_npz'])==g['prepared_npz_sha256']
   data=fd.load_prepared_fast(g['prepared_manifest'])
   assert set(data.cell_ids)==set(g['train_cell_ids']) and data.n_cells==125
   assert all(c.endswith(('C1','C2')) for c in data.cell_ids)
   indices=all_fit_indices(data,np);std=fd.fit_control_standardizer(data,indices)
   out.mkdir();rec['prepared_cache_bytes']=pathlib.Path(man['prepared_npz']).stat().st_size
   cfgs={'full':(True,True),'time':(False,True),'noRPTupdate':(True,False)}
   for arm,n_steps in g['steps'].items():
    rec['fits_started']+=1;write(recpath,rec)
    model=build_model(seed=42);model.set_control_standardizer(std['mean'],std['scale'])
    opt=torch.optim.AdamW(model.parameters(),lr=0.001,weight_decay=0.0001)
    sampler=fd.WindowSampler(data,indices,256,burn_in='exact',burn_in_events=128,batch_cells=8)
    rng=random.Random(43);losses=[];t=time.time()
    for step in range(1,n_steps+1):
     batch=sampler.sample(rng);z=fd.replay_windows(model,batch,use_cycle=cfgs[arm][0],use_rpt=cfgs[arm][1]);loss=z['loss_cell_macro']
     if not torch.isfinite(loss):raise RuntimeError('non-finite loss: '+arm+':'+str(step))
     opt.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);opt.step();rec['optimizer_steps']+=1
     if step%50==0 or step==n_steps:losses.append({'step':step,'loss':float(loss.detach())})
    target=out/arm;target.mkdir();torch.save(model.state_dict(),target/'model_state_dict.pt')
    info={'arm':arm,'n_fit_cells':125,'fit_cell_ids':data.cell_ids,'selected_steps':n_steps,'selection_repeated':False,'optimizer_steps':n_steps,'seed':42,'sampling_seed':43,'use_cycle':cfgs[arm][0],'use_rpt':cfgs[arm][1],'loss_history':losses,'last_loss':float(loss.detach()),'seconds':time.time()-t,'state_dict_sha256':sha(target/'model_state_dict.pt'),'standardizer_fit_cells':data.cell_ids,'standardizer_mean':std['mean'].tolist(),'standardizer_scale':std['scale'].tolist(),'GO_sha256':sha(go_path)}
    write(target/'fit_report.json',info);rec['fits_completed']+=1;write(recpath,rec)
    print(json.dumps({'arm':arm,'fit_cells':125,'steps':n_steps,'seconds':info['seconds']}),flush=True)
   rec['status']='SUCCESS'
 except BaseException as e:
  rec.update(status='FAILED',error=repr(e),traceback=traceback.format_exc());raise
 finally:
  signal.alarm(0);rec['elapsed_seconds']=time.time()-start;write(recpath,rec)
  if out.exists():write(out/'receipt.json',rec)
 return rec
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--go');p.add_argument('--self-check',action='store_true');a=p.parse_args()
 if a.self_check:
  import numpy as np
  class D:n_cells=125;train_index=np.arange(100);val_index=np.arange(100,125)
  assert all_fit_indices(D,np).tolist()==list(range(125));print('PASS: refit includes internal validation cells; 0 payload/fit/optimizer/checkpoint reads')
 elif a.go:print(json.dumps(run(a.go),indent=2))
 else:p.error('--go or --self-check required')
