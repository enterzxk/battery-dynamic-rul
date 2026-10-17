"""Targeted official batch check from one real cell; preserve full-init failure; no repeated scaler fit."""
from pathlib import Path
import json,hashlib,ast,io,pickle,struct,sys,os,random,datetime
import numpy as np
import torch
from torch.utils.data import DataLoader
R=Path('/home/yndx/zxk/rul');P=R/'repos/pinned/BatteryLife_3b17bb53202e10711deae0448c91f84144bb3dd9';S=R/'data/source_audit/calb_v11_trainval_stage_20261018_root';OLD=R/'reports/calb_dataset_trainval_20261018_root';O=R/'reports/calb_dataset_trainval_20261018_root_v2';D=R/'reports/calb_trainval_sample_audit_20261018_root_v2'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(n,d):
 with (O/n).open('x',encoding='utf-8') as f:json.dump(d,f,indent=2,ensure_ascii=False);f.write('\n')
try:
 failure=json.loads((OLD/'failure_receipt.json').read_text());assert failure['phase']=='one_batch' and failure['datasets_created']==['train','validation'] and len(failure['restricted_reads'])==22
 script=(OLD/'check_dataset.py').read_text().splitlines();assert 'list(ys.shape)==[32]' in script[58]
 cohort=json.loads((R/'reports/calb_remaining20_audit_20261018_root/cohort_audit.json').read_text());m=json.loads((S/'stage_manifest.json').read_text())
 assert failure['scaler_fit_events'][0]['rows']==17 and failure['scaler_fit_events'][1]['rows']==1689 and all(x['phase']=='train_init' for x in failure['scaler_fit_events'])
 decoder=D/'audit_typed_samples.py';assert sha(decoder)==cohort['bindings'][str(decoder)]
 nodes=[n for n in ast.parse(decoder.read_text()).body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in {'InertF8','dtype_replacement','scalar_replacement','FixedUnpickler'}]
 env={'pickle':pickle,'struct':struct};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(decoder),'exec'),env)
 os.chdir(P);sys.path.insert(0,str(P));import data_provider.data_loader as dl
 assert sha(P/'data_provider/data_loader.py')==cohort['bindings'][str(P/'data_provider/data_loader.py')]
 name=m['train_cells'][0];p=S/'CALB'/name;expected=next(x for x in m['files'] if x['name']==name);assert sha(p)==expected['sha256']
 obj=env['FixedUnpickler'](io.BytesIO(p.read_bytes())).load();labels=json.loads((S/'Life labels/CALB_labels.json').read_text());eol=labels[name]
 random.seed(2021);np.random.seed(2021);torch.manual_seed(2021)
 view=dl.Dataset_original.__new__(dl.Dataset_original);view.need_keys=['current_in_A','voltage_in_V','charge_capacity_in_Ah','discharge_capacity_in_Ah','time_in_s'];view.early_cycle_threshold=100;view.charge_discharge_len=300;view.seq_len=1;view.eval_cycle_max=None;view.eval_cycle_min=None;view.ZN_coin_charge_first_file_names=[];view.aug_helper=dl.BatchAugmentation_battery_revised()
 view.read_cell_data_according_to_prefix=lambda requested:(obj,eol) if requested==name else (_ for _ in ()).throw(PermissionError('only fixed first train cell'))
 curves,masks,ys,total_eol,aug=view.read_samples_from_one_cell(name);assert len(curves)>=32
 classes=json.loads((P/'data_provider/life_classes.json').read_text());class_id=next(int(k) for k,v in classes.items() if eol>=v[0] and eol<v[1])
 stats=failure['scaler_fit_events'][0];mean=stats['mean'][0];scale=stats['scale'][0]
 # Recreate only the first32 official item fields using the prior fitted train-only parameters.
 view.total_charge_discharge_curves=curves[:32];view.total_curve_attn_masks=masks[:32];view.total_labels=(np.asarray(ys[:32],dtype=float).reshape(-1,1)-mean)/scale
 view.class_labels=[class_id]*32;view.scaled_life_classes=np.asarray(view.class_labels)-1;view.weights=np.ones(32);view.total_dataset_ids=[17]*32;view.total_cj_aug_charge_discharge_curves=aug[:32];view.total_seen_unseen_IDs=[1]*32
 batch=next(iter(DataLoader(view,batch_size=32,shuffle=False,collate_fn=dl.my_collate_fn_baseline,num_workers=0)));x,mask,y,life,scaled,weights,seen=batch
 shapes=[list(t.shape) for t in batch];assert list(x.shape)==[32,100,3,300] and list(mask.shape)==[32,100] and list(y.shape)==[32,1]
 assert all(torch.isfinite(t).all() for t in batch) and torch.all(x[mask[:,:,None,None].expand_as(x)==0]==0)
 assert np.allclose(y.numpy().reshape(-1)*scale+mean,eol,atol=1e-4,rtol=0)
 result=dict(status='PINNED_TRAINVAL_INIT_AND_TARGETED_BATCH_SHAPE_PASS',at_utc=now(),prior_full_dataset_init=dict(path=str(OLD/'failure_receipt.json'),sha256=sha(OLD/'failure_receipt.json'),datasets_created=failure['datasets_created'],train_examples_verified_before_failed_assertion=1689,validation_examples_verified_before_failed_assertion=497,restricted_unique_reads=22,shared_train_label_scaler_checks_passed_before_line59=True,scaler_fit_events=failure['scaler_fit_events'],failure='Local expected label shape32 was wrong; official collate is32x1. Old outputs retained.'),targeted_batch=dict(real_source_cell=name,source_sha256=sha(p),prefixes=list(range(1,33)),all_tensor_shapes=shapes,finite=True,masked_future_zero=True,scaled_label_inverse_check=True,batch_view_reconstructed_from_single_real_cell=True,Dataset_original_init_repeated=False),additional_preprocessing_scaler_fits=0,full_dataset_init_count_total=2,preprocessing_scaler_fits_total=2,label_scaler_fits_total=1,life_class_scaler_fits_total=1,new_fits=0,optimizer_steps=0,new_inference=0,model_instances=0,test_pkl_opened=0,test_label_values_decoded=0,source_bindings={str(P/'data_provider/data_loader.py'):sha(P/'data_provider/data_loader.py'),str(OLD/'check_dataset.py'):sha(OLD/'check_dataset.py'),str(decoder):sha(decoder),str(S/'stage_manifest.json'):sha(S/'stage_manifest.json'),str(Path(__file__)):sha(Path(__file__))},scope='Full train/val Dataset_original init and actual augmentation completed once; batch shape fixed with a single-cell official __getitem__/collate view, no full-cohort rerun or scaler refit',not_cleared=['model forward/backward and new exact fit budget','2GPU official test-entry fidelity','physical identity/source-generator/strict online RUL'])
 write('targeted_batch_check.json',result);print(json.dumps(result,ensure_ascii=True),flush=True)
except BaseException as e:
 write('failure_receipt.json',dict(status='FAILED_STOP_NO_RETRY',error_type=type(e).__name__,error=str(e),new_fits=0,optimizer_steps=0,test_access=False));raise
