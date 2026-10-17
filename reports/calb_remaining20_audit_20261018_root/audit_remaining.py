"""One-pass remaining20 CALB audit. Reuse prior2; no model/test/fit."""
from pathlib import Path
import json,ast,hashlib,pickletools,pickle,struct,io,datetime,resource,sys,math,csv
import numpy as np
import pandas as pd
R=Path('/home/yndx/zxk/rul');P=R/'repos/pinned/BatteryLife_3b17bb53202e10711deae0448c91f84144bb3dd9'
O=R/'reports/calb_remaining20_audit_20261018_root';S=R/'data/source_audit/calb_v11_trainval_stage_20261018_root'
D=R/'reports/calb_trainval_sample_audit_20261018_root_v2';B=R/'reports/calb_two_sample_preprocessing_20261018_root'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(n,d):
 with (O/n).open('x',encoding='utf-8') as f:json.dump(d,f,indent=2,ensure_ascii=False);f.write('\n')
rows=[];scans=[];loads=0;current=None
try:
 resource.setrlimit(resource.RLIMIT_CPU,(120,120))
 manifest=json.loads((S/'stage_manifest.json').read_text());base=json.loads((B/'preprocessing_check.json').read_text());sample=json.loads((D/'sample_audit.json').read_text())
 assert sha(S/'stage_manifest.json')==sample['stage_manifest_sha256']==base['bindings'][str(S/'stage_manifest.json')]
 decoder=D/'audit_typed_samples.py';loader=P/'data_provider/data_loader.py';assert sha(decoder)==base['bindings'][str(decoder)] and sha(loader)==base['bindings'][str(loader)]
 wanted={'InertF8','dtype_replacement','scalar_replacement','FixedUnpickler'};ns=[n for n in ast.parse(decoder.read_text()).body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in wanted]
 env={'pickle':pickle,'struct':struct};exec(compile(ast.Module(body=ns,type_ignores=[]),str(decoder),'exec'),env)
 cls=next(n for n in ast.parse(loader.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='Dataset_original')
 names={'read_cell_df','read_samples_from_one_cell','get_charge_discharge_curves','resample_charge_discharge_curves'};methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in names]
 cnode=ast.ClassDef(name='PinnedCurveMethods',bases=[],keywords=[],body=methods,decorator_list=[]);scope={'np':np,'pd':pd};exec(compile(ast.fix_missing_locations(ast.Module(body=[cnode],type_ignores=[])),str(loader),'exec'),scope)
 class IdentityAugOnly:
  def batch_aug(self,x):return x,x
 labels=json.loads((S/'Life labels/CALB_labels.json').read_text());allowed=set(manifest['train_cells']+manifest['validation_cells']);assert len(allowed)==22 and set(labels)==allowed and sha(S/'Life labels/CALB_labels.json')==manifest['labels']['sha256']
 prior_ids={x['file_name'] for x in base['samples']};assert len(prior_ids)==2
 for x in base['samples']:
  s=next(y for y in sample['samples'] if y['file_name']==x['file_name'])
  rows.append(dict(file_name=x['file_name'],role=x['role'],evidence='REUSED_PRIOR_TWO_NO_RERUN',stored_cycles=x['stored_cycles'],prefix_samples=x['actual_prefix_samples'],zero_padded_slots=x['missing_cycles_zero_filled'],tensor_shape='100x3x300',finite=True,mask_exact=True,voltage_max_error=x['per_real_cycle_voltage_max_error'],raw_nonfinite_total=sum(s['nonfinite_by_required_field'].values()),raw_negative_capacity_points=sum(s['negative_capacity_points'].values()),cell_id_matches=True,source_sha256=x['source_sha256']))
 remaining=sorted(allowed-prior_ids);assert len(remaining)==20
 banned={'GLOBAL','NEWOBJ','NEWOBJ_EX','INST','OBJ','EXT1','EXT2','EXT4','PERSID','BINPERSID','NEXT_BUFFER','READONLY_BUFFER'}
 for name in remaining:
  current=name;p=S/'CALB'/name;expected=next(x for x in manifest['files'] if x['name']==name);raw=p.read_bytes();assert len(raw)<=8*1024**2 and hashlib.sha256(raw).hexdigest()==expected['sha256']
  counts={};total=0;last=None
  for op,arg,pos in pickletools.genops(raw):
   total+=1;assert total<=2000000;last=(op.name,pos)
   if op.name in banned:raise RuntimeError('Forbidden static opcode:'+op.name)
   if op.name in ['STACK_GLOBAL','REDUCE','BUILD']:counts[op.name]=counts.get(op.name,0)+1
  assert last==('STOP',len(raw)-1)
  scans.append(dict(file_name=name,opcodes=total,constructor_opcodes=counts,stop_exact=True,sha256=expected['sha256']))
  # No actual external symbols are imported/called: the same fixed2 local mappings reject all others.
  obj=env['FixedUnpickler'](io.BytesIO(raw)).load();loads+=1
  assert type(obj) is dict and obj['cell_id']==name[:-4] and type(obj['cycle_data']) is list and len(obj['cycle_data'])<=500
  need=['current_in_A','voltage_in_V','charge_capacity_in_Ah','discharge_capacity_in_Ah','time_in_s'];nf=0;neg=0
  for cy in obj['cycle_data']:
   lengths=[len(cy[k]) for k in need];assert len(set(lengths))==1 and lengths[0]>0
   for k in need:
    arr=np.asarray(cy[k],dtype=float);assert arr.ndim==1;nf+=int(np.sum(~np.isfinite(arr)))
    if k in ['charge_capacity_in_Ah','discharge_capacity_in_Ah']:neg+=int(np.sum(arr<0))
  c=scope['PinnedCurveMethods']();c.need_keys=need;c.early_cycle_threshold=100;c.charge_discharge_len=300;c.seq_len=1;c.eval_cycle_max=None;c.eval_cycle_min=None;c.ZN_coin_charge_first_file_names=[];c.aug_helper=IdentityAugOnly()
  c.read_cell_data_according_to_prefix=lambda requested,obj=obj,name=name:(obj,labels[name]) if requested==name else (_ for _ in ()).throw(PermissionError('outside fixed current sample'))
  curves,masks,ys,eol,aug=c.read_samples_from_one_cell(name);expected_n=min(100,len(obj['cycle_data'])) if labels[name]>100 else 0
  assert expected_n>0 and len(curves)==len(masks)==len(ys)==expected_n
  x=curves[0];assert x.shape==(100,3,300) and np.isfinite(x).all()
  real=min(100,len(obj['cycle_data']));nonzero=np.any(x!=0,axis=(1,2));assert np.all(nonzero[:real]) and not np.any(nonzero[real:])
  err=float(np.max(np.abs(np.max(x[:real,0,:],axis=1)-1)));assert err<=1e-12
  for i,(a,mask) in enumerate(zip(curves,masks),1):
   assert np.array_equal(mask[:i],np.ones(i)) and np.array_equal(mask[i:],np.zeros(100-i)) and np.all((a*mask[:,None,None])[i:]==0)
  rows.append(dict(file_name=name,role=expected['role'],evidence='NEW_REMAINING20_ONE_PASS',stored_cycles=len(obj['cycle_data']),prefix_samples=expected_n,zero_padded_slots=100-real,tensor_shape='100x3x300',finite=True,mask_exact=True,voltage_max_error=err,raw_nonfinite_total=nf,raw_negative_capacity_points=neg,cell_id_matches=True,source_sha256=expected['sha256']))
  with (O/'progress.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(file_name=name,status='PASS',remaining_loaded=loads))+'\n')
 assert len(rows)==22 and loads==20 and {x['file_name'] for x in rows}==allowed
 cohort={}
 for role,ids in [('train',manifest['train_cells']),('validation',manifest['validation_cells'])]:
  rr=[x for x in rows if x['file_name'] in ids];vals=[labels[n] for n in ids]
  cohort[role]=dict(cells=len(rr),prefix_samples=sum(x['prefix_samples'] for x in rr),stored_cycle_min=min(x['stored_cycles'] for x in rr),stored_cycle_max=max(x['stored_cycles'] for x in rr),prefix_count_histogram={str(v):sum(x['prefix_samples']==v for x in rr) for v in sorted({x['prefix_samples'] for x in rr})},author_EOL_min=min(vals),author_EOL_max=max(vals),raw_nonfinite_total=sum(x['raw_nonfinite_total'] for x in rr),raw_negative_capacity_total=sum(x['raw_negative_capacity_points'] for x in rr))
 train_labels=np.asarray([labels[n] for n in manifest['train_cells']],dtype=float);mean=float(train_labels.mean());var=float(train_labels.var());scale=math.sqrt(var);assert scale>0
 scaler=dict(status='TRAIN17_UNIQUE_LABEL_STATISTICS_ONLY_NOT_SCALER_FIT',source_role='train only',sample_count=17,expected_StandardScaler_mean=mean,expected_population_variance=var,expected_scale=scale,validation_used_to_estimate=False,test_used_to_estimate=False,scaler_fit_calls=0,official_source_lines='data_loader.py:241-254 uses unique train labels then shared label_scaler for validation')
 result=dict(status='CALB_FIXED22_FIELD_AND_PINNED_PREPROCESSING_AUDIT_PASS_SCOPED',at_utc=now(),cohort=cohort,scaler_readiness=scaler,new_restricted_loads=loads,prior_two_reused_without_reload=True,static_gate=dict(new_scans=len(scans),forbidden_constructor_imports=False,resolved_symbols='Same fixed2 inert local numeric mappings only; unknown globals/dtype/payload rejected'),rows=rows,new_fits=0,optimizer_steps=0,model_loads=0,new_inference=0,scaler_fits=0,test_pkl_opened=0,test_label_values_decoded=0,torch_imported='torch' in sys.modules,bindings={str(S/'stage_manifest.json'):sha(S/'stage_manifest.json'),str(loader):sha(loader),str(decoder):sha(decoder),str(B/'preprocessing_check.json'):sha(B/'preprocessing_check.json'),str(D/'sample_audit.json'):sha(D/'sample_audit.json'),str(Path(__file__)):sha(Path(__file__))},not_cleared=['physical identity/source-generator/strict online EOL and raw-asof claims','Full Dataset_original init/augmentation/shared train-only scaler execution','Official run_main loads/evaluates test during training;test remains locked','2GPU faithful runtime and any new fit/model/backward authorization'])
 write('static_scan_remaining20.json',dict(status='PASS_FIXED_MAPPING_PREFLIGHT',scans=scans))
 with (O/'cohort_inventory.csv').open('x',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 write('cohort_audit.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ['rows','bindings']},ensure_ascii=True),flush=True)
except BaseException as e:
 write('failure_receipt.json',dict(status='FAILED_STOP_NO_MAPPING_EXPANSION',at_utc=now(),cell=current,error_type=type(e).__name__,error=str(e),new_restricted_loads=loads,completed_rows=rows,new_fits=0,optimizer_steps=0,test_access=False));raise
