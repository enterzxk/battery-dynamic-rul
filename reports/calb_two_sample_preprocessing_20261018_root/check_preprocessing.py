"""Run only pinned unaugmented curve methods on two fixed CALB samples; no dataset/model initialization."""
from pathlib import Path
import ast,json,hashlib,io,pickle,struct,datetime,resource,sys
import numpy as np
import pandas as pd
R=Path('/home/yndx/zxk/rul');P=R/'repos/pinned/BatteryLife_3b17bb53202e10711deae0448c91f84144bb3dd9'
O=R/'reports/calb_two_sample_preprocessing_20261018_root';S=R/'data/source_audit/calb_v11_trainval_stage_20261018_root';PREV=R/'reports/calb_trainval_sample_audit_20261018_root_v2'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(n,d):
 with (O/n).open('x',encoding='utf-8') as f:json.dump(d,f,indent=2,ensure_ascii=False);f.write('\n')
calls=0
try:
 resource.setrlimit(resource.RLIMIT_CPU,(90,90))
 prev=json.loads((PREV/'sample_audit.json').read_text());manifest=json.loads((S/'stage_manifest.json').read_text())
 assert sha(S/'stage_manifest.json')==prev['stage_manifest_sha256']
 loader=P/'data_provider/data_loader.py';assert sha(loader)==json.loads((R/'reports/calb_trainval_sample_audit_20261018_root_v2/ROOT_TYPED_LOAD_REVIEW.json').read_text()).get('loader_sha256',sha(loader))
 decoder=PREV/'audit_typed_samples.py';assert sha(decoder)==prev['source_sha256']
 dtree=ast.parse(decoder.read_text());wanted={'InertF8','dtype_replacement','scalar_replacement','FixedUnpickler'}
 nodes=[n for n in dtree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in wanted];assert {n.name for n in nodes}==wanted
 env={'pickle':pickle,'struct':struct};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(decoder),'exec'),env)
 tree=ast.parse(loader.read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Dataset_original')
 methods=['read_cell_df','read_samples_from_one_cell','get_charge_discharge_curves','resample_charge_discharge_curves']
 nodes=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in methods];assert {n.name for n in nodes}==set(methods)
 cnode=ast.ClassDef(name='PinnedCurveMethods',bases=[],keywords=[],body=nodes,decorator_list=[])
 module=ast.fix_missing_locations(ast.Module(body=[cnode],type_ignores=[]));scope={'np':np,'pd':pd};exec(compile(module,str(loader),'exec'),scope)
 class IdentityAugOnly:
  def batch_aug(self,x):return x,x
 labels=json.loads((S/'Life labels/CALB_labels.json').read_text());names=[x['file_name'] for x in prev['samples']]
 assert names==['CALB_35_B229.pkl','CALB_0_B187.pkl']
 results=[]
 for name in names:
  p=S/'CALB'/name;expected=next(x for x in prev['samples'] if x['file_name']==name);assert sha(p)==expected['source_sha256']
  obj=env['FixedUnpickler'](io.BytesIO(p.read_bytes())).load()
  c=scope['PinnedCurveMethods']();c.need_keys=['current_in_A','voltage_in_V','charge_capacity_in_Ah','discharge_capacity_in_Ah','time_in_s'];c.early_cycle_threshold=100;c.charge_discharge_len=300;c.seq_len=1;c.eval_cycle_max=None;c.eval_cycle_min=None;c.ZN_coin_charge_first_file_names=[];c.aug_helper=IdentityAugOnly()
  c.read_cell_data_according_to_prefix=lambda requested, obj=obj,name=name:(obj,labels[name]) if requested==name else (_ for _ in ()).throw(PermissionError('sample outside fixed allowlist'))
  curves,masks,ys,eol,aug=c.read_samples_from_one_cell(name);calls+=1
  assert len(curves)==len(masks)==len(ys)==expected['eligible_prefix_count_from_pinned_rule']
  x=curves[0];assert x.shape==(100,3,300) and np.isfinite(x).all()
  nonzero=np.any(x!=0,axis=(1,2));available=len(obj['cycle_data']);assert np.all(nonzero[:available]) and not np.any(nonzero[available:])
  assert all(y==eol for y in ys)
  for i,(a,mask) in enumerate(zip(curves,masks),1):
   assert a.shape==(100,3,300) and mask.shape==(100,) and np.array_equal(mask[:i],np.ones(i)) and np.array_equal(mask[i:],np.zeros(100-i))
   masked=a*mask[:,None,None];assert np.all(masked[i:]==0)
  visible=x[:available];vmax=np.max(visible[:,0,:],axis=1);assert np.allclose(vmax,1.,rtol=0,atol=1e-12)
  # Independent first-cycle endpoint reconstruction validates the three normalized channel units.
  cy=obj['cycle_data'][0];df=pd.DataFrame({k:cy[k] for k in c.need_keys});df['cycle_number']=1
  voltage=df['voltage_in_V'].to_numpy();current=df['current_in_A'].to_numpy();charge=df['charge_capacity_in_Ah'].to_numpy();discharge=df['discharge_capacity_in_Ah'].to_numpy();nominal=obj['nominal_capacity_in_Ah']
  ce=np.nonzero(current/nominal>=.01)[0][-1];de=np.nonzero(current/nominal<=-.01)[0][-1]
  if name.startswith(('CALB_0_','CALB_25_','CALB_45_')):
   dv,di,dq=voltage[:de],current[:de],discharge[:de];qmask=np.abs(current[de:]/nominal)>.01;cv,ci,cq=voltage[de:][qmask],current[de:][qmask],charge[de:][qmask]
  else:
   dmask=np.abs(current[ce:]/nominal)>.01;dv,di,dq=voltage[ce:][dmask],current[ce:][dmask],discharge[ce:][dmask];cv,ci,cq=voltage[:ce],current[:ce],charge[:ce]
  bases=lambda a:np.linspace(1,len(a)+1,150,endpoint=True)
  interp=lambda a:np.interp(bases(a),np.arange(1,len(a)+1),a)
  v=np.concatenate([interp(cv),interp(dv)]);cur=np.concatenate([interp(ci),interp(di)]);cap=np.concatenate([interp(cq),interp(dq)])
  independent=np.stack([v/max(v),cur/nominal,cap/nominal])
  delta=float(np.max(np.abs(independent-x[0])));assert delta<=1e-12
  results.append(dict(file_name=name,role=expected['role'],stored_cycles=available,measured_curve_shape=list(x.shape),actual_prefix_samples=len(curves),mask_shape=[len(masks),100],missing_cycles_zero_filled=int(np.sum(~nonzero)),last_slot_nonzero=bool(nonzero[-1]),prefix_masks_exact=True,masked_future_slots_zero=True,all_curve_values_finite=True,per_real_cycle_voltage_max_error=float(np.max(np.abs(vmax-1))),channel_min=[float(visible[:,j,:].min()) for j in range(3)],channel_max=[float(visible[:,j,:].max()) for j in range(3)],first_cycle_independent_normalization_max_abs_delta=delta,curve_array_sha256=hashlib.sha256(x.tobytes()).hexdigest(),source_sha256=sha(p)))
 assert 'torch' not in sys.modules
 res=dict(status='PINNED_TWO_SAMPLE_CURVE_AND_MASK_CHECK_PASS',at_utc=now(),samples=results,pinned_method_calls=calls,source_methods=[dict(name=n.name,line=n.lineno,end_line=n.end_lineno) for n in nodes],augmentation_branch='Identity stub only for unused augmentation return; unaugmented curves/masks are exact pinned methods, not full Dataset_original construction',runtime=dict(python=sys.version.split()[0],numpy=np.__version__,pandas=pd.__version__),model_loads=0,torch_imported=False,new_fits=0,optimizer_steps=0,new_inference=0,scaler_fits=0,test_pkl_opened=0,test_label_values_decoded=0,bindings={str(loader):sha(loader),str(decoder):sha(decoder),str(S/'stage_manifest.json'):sha(S/'stage_manifest.json'),str(Path(__file__)):sha(Path(__file__))},limitations=['Only same two fixed samples; remaining20 not approved','Whole stored cycle inputs and author totalEOL; not strict online/asof proof or physical identity validation','No Dataset_original init, augmentation behavior, train-only label scaler fitting, model/backward/training/test or2GPU runtime check','Expected99/100 prefix imbalance requires explicit cell-equal reporting alongside official prefix aggregation'])
 write('preprocessing_check.json',res);print(json.dumps(res,ensure_ascii=True),flush=True)
except BaseException as e:
 write('failure_receipt.json',dict(status='FAILED_STOP_NO_RETRY',at_utc=now(),error_type=type(e).__name__,error=str(e),pinned_method_calls=calls,new_fits=0,optimizer_steps=0,test_access=False));raise
