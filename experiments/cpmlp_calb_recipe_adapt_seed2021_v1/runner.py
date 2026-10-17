"""One-use CALB author-EOL recipe adaptation; old runs are never resumed."""
from pathlib import Path
import argparse,csv,datetime,fcntl,hashlib,importlib.util,json,math,os,random,sys,time
ROOT=Path('/home/yndx/zxk/rul');OUT=ROOT/'experiments/cpmlp_calb_recipe_adapt_seed2021_v1'
BASE=ROOT/'src/experiments/cpmlp_hust_pilot.py';CFG=OUT/'config.json'
VIEW=ROOT/'data/source_audit/calb_v11_trainval_stage_20261018_root';CODE=ROOT/'repos/pinned/BatteryLife_3b17bb53202e10711deae0448c91f84144bb3dd9'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(name,obj):
 with (OUT/name).open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def stopping(best,counter,value,epoch,patience=5,least=5):
 if not math.isfinite(value):raise ValueError('nonfinite validation selection metric')
 if best is None:return value,0,False
 if value>best:
  counter+=int(epoch>least)
  return best,counter,counter>=patience
 return value,0,False  # exact official tie semantics

def checkpoint_meta(epoch,batches,expected,steps):
 return {'epoch':epoch,'epoch_complete':batches==expected,'train_batches_completed':batches,'train_batches_expected':expected,'optimizer_steps_total':steps,'validation_complete':False,'exact_mid_epoch_resume_supported':False}
def check_stopping():
 best=None;counter=0;observed=[]
 for epoch,value in enumerate([1.,2.,2.,2.,2.,2.,2.,2.,2.,2.],1):
  best,counter,stop=stopping(best,counter,value,epoch);observed.append((epoch,counter,stop))
 assert next(e for e,c,s in observed if s)==10
 assert stopping(1.,4,1.,9)==(1.,0,False)
 assert not checkpoint_meta(3,8,146,300)['epoch_complete']
 assert checkpoint_meta(2,146,146,292)['epoch_complete']
 write('stopping_check.json',{'status':'PASS_SINGLE_TARGETED_BOUNDARY_CHECK','worsening_stop_epoch':10,'tie_resets_counter':True,'partial8of146_marked_incomplete':True,'model_imports':0,'data_reads':0,'new_fits':0,'optimizer_steps':0})
 print('PASS targeted stopping/partial-checkpoint check; data/model imports=0')

class WallBudgetStop(RuntimeError):pass
def bounded_batches(loader,deadline,clock=time.monotonic):
 if clock()>=deadline:raise WallBudgetStop('wall budget before validation')
 for batch in loader:
  if clock()>=deadline:raise WallBudgetStop('wall budget before validation batch')
  yield batch
  if clock()>=deadline:raise WallBudgetStop('wall budget after validation batch')


def install_calb_restricted(dl,view):
 import ast,io,pickle,struct
 decoder=ROOT/'reports/calb_trainval_sample_audit_20261018_root_v2/audit_typed_samples.py'
 wanted={'InertF8','dtype_replacement','scalar_replacement','FixedUnpickler'}
 nodes=[n for n in ast.parse(decoder.read_text()).body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in wanted]
 assert {n.name for n in nodes}==wanted
 scope={'pickle':pickle,'struct':struct};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(decoder),'exec'),scope)
 allowed={str((VIEW/'CALB'/x['name']).resolve()):x['sha256'] for x in view['files']}
 class Facade:
  def __init__(self):self.reads=[]
  def load(self,f):
   path=str(Path(f.name).resolve());expected=allowed.get(path)
   if expected is None:raise PermissionError('Outside fixed22 CALB trainval allowlist')
   raw=f.read();assert len(raw)<=8*1024**2 and hashlib.sha256(raw).hexdigest()==expected
   obj=scope['FixedUnpickler'](io.BytesIO(raw)).load();self.reads.append({'path':path,'sha256':expected});return obj
 obj=Facade();dl.pickle=obj;return obj

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check-stopping',action='store_true');ap.add_argument('--fit',action='store_true');a=ap.parse_args()
 if a.check_stopping:return check_stopping()
 if not a.fit:raise RuntimeError('Use explicit --fit after matching root GO')
 go=json.loads((OUT/'ROOT_GO.json').read_text());cfg=json.loads(CFG.read_text());assert go['status']=='GO_CALB_AUTHOR_EOL_RECIPE_ADAPTATION_ONLY';assert go['strict_online_claim'] is False and go['test_access'] is False
 bindings={str(Path(__file__).resolve()):sha(Path(__file__)),str(CFG):sha(CFG),str(BASE):sha(BASE),str(VIEW/'stage_manifest.json'):sha(VIEW/'stage_manifest.json'),str(ROOT/'reports/calb_trainval_sample_audit_20261018_root_v2/audit_typed_samples.py'):sha(ROOT/'reports/calb_trainval_sample_audit_20261018_root_v2/audit_typed_samples.py'),str(ROOT/'reports/calb_dataset_trainval_20261018_root_v2/targeted_batch_check.json'):sha(ROOT/'reports/calb_dataset_trainval_20261018_root_v2/targeted_batch_check.json'),str(CODE/'models/CPMLP.py'):sha(CODE/'models/CPMLP.py'),str(CODE/'data_provider/data_loader.py'):sha(CODE/'data_provider/data_loader.py')}
 assert go['bindings']==bindings;assert go['max_predictive_fits']==1;assert cfg['fit_budget']['max_optimizer_steps']==5200 and cfg['fit_budget']['max_wall_seconds']==1200
 assert cfg['status']=='FROZEN_RECIPE_ADAPTATION' and cfg['training_authorized'] is True and cfg['fit_budget']['test_access']=='LOCKED_NO_TEST_DATASET_NO_TEST_INFERENCE'
 with (ROOT/'automation/state/coordinator.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);co=json.loads((ROOT/'automation/state/coordinator.json').read_text());assert co['owner']==co['thread_id']==go['owner']
 gpu_lock=(ROOT/'automation/locks/cpmlp_hust_pilot_gpu.lock').open('a+');fcntl.flock(gpu_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 write('invocation.claim',{'at_utc':now(),'go_sha256':sha(OUT/'ROOT_GO.json'),'max_invocations':1})
 start=time.monotonic();steps=0;fit_started=False;last_epoch=0;status='FAILED_STOP';best_epoch=None;best_mape=float('inf');epoch_records=[]
 try:
  os.environ.setdefault('OMP_NUM_THREADS','2');os.environ.setdefault('MKL_NUM_THREADS','2')
  import numpy as np
  import torch
  from torch.utils.data import DataLoader
  from types import SimpleNamespace
  sp=importlib.util.spec_from_file_location('frozen_cp_base',BASE);base=importlib.util.module_from_spec(sp);sp.loader.exec_module(base)
  torch.set_num_threads(2);random.seed(cfg['seed']);np.random.seed(cfg['seed']);torch.manual_seed(cfg['seed']);torch.cuda.manual_seed_all(cfg['seed'])
  torch.backends.cudnn.deterministic=True;torch.backends.cudnn.benchmark=False
  sys.path.insert(0,str(CODE));os.chdir(CODE)
  import data_provider.data_loader as dl
  view=json.loads((VIEW/'stage_manifest.json').read_text());train_names=set(cfg['split_files']['train']);val_names=set(cfg['split_files']['val']);test_names=set(cfg['split_files']['test']);allowed=train_names|val_names
  assert len(train_names)==17 and len(val_names)==5 and not train_names&val_names and not allowed&test_names
  assert {p.name for p in (VIEW/'CALB').iterdir()}==allowed and view['test_files_present'] is False and view['test_label_keys_present'] is False
  assert sha(VIEW/'Life labels/CALB_labels.json')==view['labels']['sha256'] and set(json.loads((VIEW/'Life labels/CALB_labels.json').read_text()))==allowed
  restricted=install_calb_restricted(dl,view);base.tracked_dataset_class(dl)
  for key in ['seq_len','charge_discharge_length','early_cycle_threshold','d_model','d_ff','e_layers','d_layers','dropout']:cfg[key]=cfg['model'][key]
  args=SimpleNamespace(root_path=str(VIEW),dataset='CALB',seq_len=cfg['seq_len'],charge_discharge_length=cfg['charge_discharge_length'],early_cycle_threshold=cfg['early_cycle_threshold'],weighted_loss=False);train=dl.Dataset_original(args=args,flag='train');val=dl.Dataset_original(args=args,flag='val',label_scaler=train.return_label_scaler(),life_class_scaler=train.return_life_class_scaler())
  assert set(train.files)==train_names and set(val.files)==val_names and train.return_label_scaler() is val.return_label_scaler();assert {Path(x['path']).name for x in restricted.reads}<=allowed
  trainloader=DataLoader(train,batch_size=32,shuffle=True,drop_last=True,collate_fn=base.mask_collate(dl),num_workers=0);valloader=DataLoader(val,batch_size=32,shuffle=False,drop_last=False,collate_fn=base.mask_collate(dl),num_workers=0);expected=len(trainloader);assert expected==52 and len(train)==1689 and len(val)==497
  from models.CPMLP import Model
  device=torch.device('cuda');model=Model(SimpleNamespace(**{key:cfg[key] for key in ['seq_len','charge_discharge_length','early_cycle_threshold','d_model','d_ff','e_layers','d_layers','dropout']})).to(device)
  optimizer=torch.optim.Adam(model.parameters(),lr=.00005,betas=(.9,.999),eps=1e-8,weight_decay=0);fit_started=True
  ledger=OUT/'budget_ledger.jsonl';base.append_jsonl(ledger,{'event':'fit_started','at_utc':now(),'budget':cfg['fit_budget'],'old600steps_untouched':True})
  stop_best=None;counter=0;status='MAX_EPOCHS_COMPLETED';selection=None
  write('run_manifest.json',{'at_utc':now(),'bindings':bindings,'seed':2021,'protocol_id':cfg['protocol_id'],'training_labels':'CALB_v11 author total EOL','train_cells':sorted(train_names),'val_cells':sorted(val_names),'test_access':False,'train_batches_per_epoch':expected,'train_samples':len(train),'validation_samples':len(val),'runtime':{'python':sys.version.split()[0],'torch':torch.__version__,'numpy':np.__version__},'determinism':'seed2021; cudnn deterministic, benchmark false; no cross-environment bitwise claim','scaler_mean':train.return_label_scaler().mean_.tolist(),'scaler_scale':train.return_label_scaler().scale_.tolist()})
  for epoch in range(1,101):
   if steps+expected>5200:status='STEP_BUDGET_STOP_BEFORE_EPOCH';break
   if time.monotonic()-start>=1200:status='WALL_BUDGET_STOP_BEFORE_EPOCH';break
   model.train();batches=0;total_loss=0.;interrupted=False
   for batch in trainloader:
    if time.monotonic()-start>=1200:interrupted=True;break
    x,mask,y,life_class,scaled_life,weights,seen=batch;x=x.to(device);mask=mask.to(device);y=y.to(device).reshape(-1,1);weights=weights.to(device).reshape(-1,1)
    assert tuple(x.shape[2:])==(3,300)
    optimizer.zero_grad(set_to_none=True);pred=model(x,mask);assert pred.shape==y.shape
    loss=(torch.nn.functional.mse_loss(pred,y,reduction='none')*weights).mean()
    if not torch.isfinite(loss):raise RuntimeError('nonfinite loss')
    loss.backward();
    if not all(p.grad is None or torch.isfinite(p.grad).all() for p in model.parameters()):raise RuntimeError('nonfinite gradient')
    optimizer.step();steps+=1;batches+=1;total_loss+=float(loss.detach().cpu());base.append_jsonl(ledger,{'event':'optimizer_step','optimizer_step':steps,'epoch':epoch,'batch':batches,'loss':float(loss.detach().cpu()),'elapsed_seconds':time.monotonic()-start})
   meta=checkpoint_meta(epoch,batches,expected,steps);last_epoch=epoch
   if not meta['epoch_complete']:
    cp=OUT/('checkpoint_partial_epoch_%03d.pt'%epoch);torch.save({'model_state_dict':model.state_dict(),'optimizer_state_dict':optimizer.state_dict(),**meta},cp);base.append_jsonl(ledger,{'event':'partial_checkpoint_saved',**meta,'checkpoint':cp.name});status='WALL_BUDGET_STOP_PARTIAL_EPOCH';break
   try:
    predictions=base.compute_val_predictions(val,bounded_batches(valloader,start+1200),model,val.return_label_scaler(),device);metrics=base.metrics(predictions)
    if time.monotonic()-start>=1200:raise WallBudgetStop('wall budget after validation metrics')
   except WallBudgetStop:
    cp=OUT/('checkpoint_train_complete_unvalidated_epoch_%03d.pt'%epoch)
    torch.save({'model_state_dict':model.state_dict(),'optimizer_state_dict':optimizer.state_dict(),**meta},cp)
    base.append_jsonl(ledger,{'event':'train_epoch_complete_validation_incomplete',**meta,'checkpoint':cp.name})
    status='WALL_BUDGET_STOP_VALIDATION_INCOMPLETE';break
   meta['validation_complete']=True;value=metrics['prefix_mean_mape']
   stop_best,counter,stop=stopping(stop_best,counter,value,epoch)
   if value<best_mape:
    best_mape=value;best_epoch=epoch;selection=metrics;best_prediction_file='validation_predictions_epoch_%03d.csv'%epoch;base.write_prediction_csv(OUT/best_prediction_file,predictions)
   cp=OUT/('checkpoint_complete_epoch_%03d.pt'%epoch)
   torch.save({'model_state_dict':model.state_dict(),'optimizer_state_dict':optimizer.state_dict(),**meta,'rng_python_state':random.getstate(),'rng_numpy_state':[np.random.get_state()[0],np.random.get_state()[1].tolist(),int(np.random.get_state()[2]),int(np.random.get_state()[3]),float(np.random.get_state()[4])],'rng_torch_cpu_state':torch.get_rng_state(),'rng_torch_cuda_states':torch.cuda.get_rng_state_all(),'config_sha256':sha(CFG)},cp)
   record={'epoch':epoch,**meta,'mean_train_loss':total_loss/batches,'validation_metrics':metrics,'early_stop_counter':counter,'best_epoch':best_epoch,'checkpoint':cp.name,'checkpoint_sha256':base.sha_file(cp),'elapsed_seconds':time.monotonic()-start};epoch_records.append(record);base.append_jsonl(OUT/'epoch_metrics.jsonl',record);base.append_jsonl(ledger,{'event':'complete_epoch_saved','epoch':epoch,'optimizer_steps_total':steps,'checkpoint':cp.name});print(json.dumps({'epoch':epoch,'steps':steps,'val_cell_MAE':metrics['cell_equal_mae_cycles'],'val_prefix_MAPE':value,'early_stop_counter':counter}),flush=True)
   if stop:status='EARLY_STOP_COMPLETED';break
  if selection is None:raise RuntimeError('No completed validation epoch; STOP')
  receipt={'status':status,'at_utc':now(),'new_predictive_fits':1,'optimizer_steps':steps,'completed_full_epochs':len(epoch_records),'last_epoch':last_epoch,'best_epoch':best_epoch,'selection_metric':'validation prefix-MAPE, strict best; early-stop ties reset counter','best_validation_metrics':selection,'selected_prediction_file':best_prediction_file,'predictions_sha256':sha(OUT/best_prediction_file),'elapsed_seconds':time.monotonic()-start,'seed':2021,'test_access':False,'strict_online_claim':False,'full_paper_reproduction':False,'checkpoint_resume_supported':False,'scope':cfg['scope'],'deviations':cfg['deviations'],'bindings':bindings,'legacy_fits':3,'legacy_optimizer_steps':2060,'MATR_direction_A_closed_NO_GAIN_unchanged':True}
  write('completion_receipt.json',receipt);base.append_jsonl(ledger,{'event':'fit_finished','status':status,'optimizer_steps':steps});print(json.dumps(receipt),flush=True)
 except BaseException as e:
  write('failure_receipt.json',{'status':'FAILED_STOP_NO_RETRY','at_utc':now(),'error_type':type(e).__name__,'error':str(e),'new_predictive_fit_attempts':int(fit_started),'optimizer_steps':steps,'last_epoch':last_epoch,'test_access':False});raise
if __name__=='__main__':main()
