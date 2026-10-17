"""One pinned Dataset_original train/val execution, restricted fixed22 inputs; no model or test."""
from pathlib import Path
from types import SimpleNamespace
import os,sys,json,hashlib,ast,io,pickle,struct,datetime,random
import numpy as np
import torch
from torch.utils.data import DataLoader
R=Path('/home/yndx/zxk/rul');P=R/'repos/pinned/BatteryLife_3b17bb53202e10711deae0448c91f84144bb3dd9';S=R/'data/source_audit/calb_v11_trainval_stage_20261018_root';O=R/'reports/calb_dataset_trainval_20261018_root'
D=R/'reports/calb_trainval_sample_audit_20261018_root_v2';C=R/'reports/calb_remaining20_audit_20261018_root'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(n,d):
 with (O/n).open('x',encoding='utf-8') as f:json.dump(d,f,indent=2,ensure_ascii=False);f.write('\n')
scaler_events=[];reads=[];stage='before_dataset';datasets_created=[]
try:
 co=json.loads((C/'cohort_audit.json').read_text());m=json.loads((S/'stage_manifest.json').read_text());decoder=D/'audit_typed_samples.py'
 for p in [S/'stage_manifest.json',P/'data_provider/data_loader.py',decoder]:assert sha(p)==co['bindings'][str(p)]
 allowed={str((S/'CALB'/x['name']).resolve()):x['sha256'] for x in m['files']};assert len(allowed)==22
 assert set(x.name for x in (S/'CALB').iterdir())==set(m['train_cells']+m['validation_cells'])
 assert sha(S/'Life labels/CALB_labels.json')==m['labels']['sha256']
 nodes=[n for n in ast.parse(decoder.read_text()).body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in {'InertF8','dtype_replacement','scalar_replacement','FixedUnpickler'}]
 scope={'pickle':pickle,'struct':struct};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(decoder),'exec'),scope)
 class RestrictedFacade:
  def load(self,fileobj):
   path=str(Path(fileobj.name).resolve())
   if path not in allowed:raise PermissionError('outside fixed22 pickle allowlist')
   raw=fileobj.read();assert len(raw)<=8*1024**2 and hashlib.sha256(raw).hexdigest()==allowed[path]
   obj=scope['FixedUnpickler'](io.BytesIO(raw)).load();reads.append(dict(path=path,sha256=allowed[path],phase=stage));return obj
 os.chdir(P);sys.path.insert(0,str(P))
 import data_provider.data_loader as dl
 dl.pickle=RestrictedFacade()
 OriginalScaler=dl.StandardScaler
 class TrackedScaler(OriginalScaler):
  def fit(self,X,y=None,sample_weight=None):
   if stage!='train_init':raise PermissionError('Scaler fit outside train phase')
   result=super().fit(X,y,sample_weight=sample_weight);scaler_events.append(dict(phase=stage,rows=int(len(X)),mean=self.mean_.tolist(),scale=self.scale_.tolist()));return result
 dl.StandardScaler=TrackedScaler
 class CountedDataset(dl.Dataset_original):
  def read_samples_from_one_cell(self,name):
   result=super().read_samples_from_one_cell(name)
   if not hasattr(self,'fixed_prefix_counts'):self.fixed_prefix_counts=[]
   self.fixed_prefix_counts.append(dict(file_name=name,prefixes=len(result[0]) if result[0] is not None else 0));return result
 random.seed(2021);np.random.seed(2021);torch.manual_seed(2021)
 args=SimpleNamespace(root_path=str(S),dataset='CALB',seq_len=1,charge_discharge_length=300,early_cycle_threshold=100,weighted_loss=False)
 stage='train_init';train=CountedDataset(args=args,flag='train');datasets_created.append('train')
 scaler=train.return_label_scaler();label_params_before=(scaler.mean_.copy(),scaler.scale_.copy())
 stage='validation_init';val=CountedDataset(args=args,flag='val',label_scaler=scaler,life_class_scaler=train.return_life_class_scaler());datasets_created.append('validation')
 assert len(train)==1689 and len(val)==497 and set(train.files)==set(m['train_cells']) and set(val.files)==set(m['validation_cells'])
 assert val.return_label_scaler() is scaler and val.return_life_class_scaler() is train.return_life_class_scaler()
 assert np.array_equal(label_params_before[0],scaler.mean_) and np.array_equal(label_params_before[1],scaler.scale_)
 assert np.allclose(scaler.mean_,co['scaler_readiness']['expected_StandardScaler_mean'],atol=1e-10,rtol=0) and np.allclose(scaler.scale_,co['scaler_readiness']['expected_scale'],atol=1e-10,rtol=0)
 assert len(scaler_events)==2 and [x['rows'] for x in scaler_events]==[17,1689]
 expected={x['file_name']:x['prefix_samples'] for x in co['rows']}
 assert {x['file_name']:x['prefixes'] for x in train.fixed_prefix_counts+val.fixed_prefix_counts}==expected
 assert len(reads)==22 and len({x['path'] for x in reads})==22
 stage='one_batch'
 loader=DataLoader(train,batch_size=32,shuffle=False,drop_last=False,collate_fn=dl.my_collate_fn_baseline,num_workers=0)
 batch=next(iter(loader));x,mask,ys,life,scaled,weights,seen=batch
 assert list(x.shape)==[32,100,3,300] and list(mask.shape)==[32,100] and list(ys.shape)==[32] and torch.isfinite(x).all() and torch.isfinite(ys).all()
 invisible=mask[:,:,None,None].expand_as(x)==0;assert torch.all(x[invisible]==0)
 assert set(reads[i]['phase'] for i in range(len(reads)))=={'train_init','validation_init'}
 res=dict(status='PINNED_CALB_TRAINVAL_DATASET_AND_BATCH_PASS',at_utc=now(),seed_for_augmentation_only=2021,datasets_created=datasets_created,train_examples=len(train),validation_examples=len(val),per_cell_prefix_counts=dict(train=train.fixed_prefix_counts,validation=val.fixed_prefix_counts),restricted_file_reads=reads,train_only_label_scaler=dict(fitted_on_unique_train_cells=17,mean=scaler.mean_.tolist(),scale=scaler.scale_.tolist(),shared_object_with_val=True,parameters_unchanged_by_val=True),preprocessing_scaler_fit_events=scaler_events,preprocessing_scaler_fit_count=2,predictive_model_fits=0,batch=dict(shape=list(x.shape),mask_shape=list(mask.shape),label_shape=list(ys.shape),dtype=str(x.dtype),finite=True,invisible_positions_zero=True),actual_augmentation_helper=type(train.aug_helper).__name__,identity_augmentation_stub_used=False,test_dataset_constructed=False,test_pkl_opened=0,test_label_values_decoded=0,model_instances=0,new_fits=0,optimizer_steps=0,new_inference=0,scope='CALB official Dataset_original train/val only with exact22 restricted pickle facade; no run_main/test/model',bindings={str(S/'stage_manifest.json'):sha(S/'stage_manifest.json'),str(P/'data_provider/data_loader.py'):sha(P/'data_provider/data_loader.py'),str(P/'utils/augmentation.py'):sha(P/'utils/augmentation.py'),str(decoder):sha(decoder),str(C/'cohort_audit.json'):sha(C/'cohort_audit.json'),str(Path(__file__)):sha(Path(__file__))},not_cleared=['official2GPU train/test entry fidelity','model forward/backward and independent new fit budget','physical serial/source generator/true-event strict online RUL claims'])
 write('dataset_check.json',res);print(json.dumps({k:v for k,v in res.items() if k not in ['restricted_file_reads','bindings','per_cell_prefix_counts']},ensure_ascii=True),flush=True)
except BaseException as e:
 write('failure_receipt.json',dict(status='FAILED_STOP_NO_RETRY',at_utc=now(),error_type=type(e).__name__,error=str(e),phase=stage,datasets_created=datasets_created,restricted_reads=reads,scaler_fit_events=scaler_events,new_fits=0,optimizer_steps=0,model_instances=0,test_access=False));raise
