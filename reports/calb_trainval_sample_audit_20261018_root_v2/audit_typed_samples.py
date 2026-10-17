"""Fixed two-sample restricted load; NumPy symbols mapped to inert local numeric replacements."""
from pathlib import Path
import json,hashlib,io,pickle,struct,resource,math,datetime
R=Path('/home/yndx/zxk/rul');P=R/'repos/pinned/BatteryLife_3b17bb53202e10711deae0448c91f84144bb3dd9'
O=R/'reports/calb_trainval_sample_audit_20261018_root_v2';S=R/'data/source_audit/calb_v11_trainval_stage_20261018_root';OLD=R/'reports/calb_trainval_sample_audit_20261018_root'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(n,d):
 with (O/n).open('x',encoding='utf-8') as f:json.dump(d,f,indent=2,ensure_ascii=False);f.write('\n')
resource.setrlimit(resource.RLIMIT_AS,(768*1024**2,768*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(90,90))
manifest=json.loads((S/'stage_manifest.json').read_text());gate=json.loads((OLD/'serialization_gate.json').read_text());failure=json.loads((OLD/'failure_receipt.json').read_text())
assert failure['counters']['restricted_sample_loads']==0
names=[manifest['train_cells'][0],manifest['validation_cells'][0]];assert names==['CALB_35_B229.pkl','CALB_0_B187.pkl']
for name in names:
 p=S/'CALB'/name;expected=next(x for x in gate['scans'] if x['file_name']==name)
 assert sha(p)==expected['sha256'] and expected['stop_at_exact_end']
write('ROOT_TYPED_LOAD_REVIEW.json',dict(status='GO_FIXED_TWO_CALB_SAMPLES_WITH_INERT_F8_REPLACEMENTS',at_utc=now(),source_sha256=sha(Path(__file__)),prior_failure_sha256=sha(OLD/'failure_receipt.json'),prior_gate_sha256=sha(OLD/'serialization_gate.json'),scope=names,observed_validation_globals=['numpy.core.multiarray.scalar','numpy.dtype'],numeric_contract='Only exact dtype(f8,False,True), state(3,little-endian,None,None,None,-1,-1,0), scalar8bytes -> struct-unpacked Pythonfloat. Never import/call NumPy.',unrestricted_unpickle_allowed=False,ordinary_global_imports=False,max_bytes_per_sample=8*1024**2,max_nodes_per_sample=2000000,max_loaded_samples=2,test_access=False,model_allowed=False,fits_allowed=False))
class InertF8:
 def __init__(self):self.built=False
 def __setstate__(self,state):
  if type(state) is not tuple or state!=(3,'<',None,None,None,-1,-1,0):raise pickle.UnpicklingError('dtype state denied')
  self.built=True
def dtype_replacement(*args):
 if args!=('f8',False,True):raise pickle.UnpicklingError('dtype args denied')
 return InertF8()
def scalar_replacement(dtype,payload):
 if type(dtype) is not InertF8 or not dtype.built or type(payload) is not bytes or len(payload)!=8:raise pickle.UnpicklingError('scalar payload denied')
 return struct.unpack('<d',payload)[0]
class FixedUnpickler(pickle.Unpickler):
 def find_class(self,module,name):
  if (module,name)==('numpy.core.multiarray','scalar'):return scalar_replacement
  if (module,name)==('numpy','dtype'):return dtype_replacement
  raise pickle.UnpicklingError('global denied:'+module+'.'+name)
 def persistent_load(self,pid):raise pickle.UnpicklingError('persistent denied')
loads=0;out=[]
try:
 for name in names:
  p=S/'CALB'/name;raw=p.read_bytes();assert len(raw)<=8*1024**2;obj=FixedUnpickler(io.BytesIO(raw)).load();loads+=1
  todo=[obj];seen=set();nodes=0
  while todo:
   v=todo.pop();nodes+=1;assert nodes<=2000000
   if type(v) in [str,bytes,int,float,bool,type(None)]:continue
   assert type(v) in [dict,list,tuple,set,frozenset]
   if id(v) in seen:continue
   seen.add(id(v))
   if type(v) is dict:
    assert all(type(k) in [str,bytes,int,float,bool,type(None)] for k in v);todo.extend(v.values())
   else:todo.extend(v)
  assert type(obj) is dict and type(obj['cycle_data']) is list
  cycles=obj['cycle_data'];nominal=obj['nominal_capacity_in_Ah'];assert type(nominal) in [int,float] and math.isfinite(nominal) and nominal>0
  assert 0<len(cycles)<=500;need=['current_in_A','voltage_in_V','charge_capacity_in_Ah','discharge_capacity_in_Ah','time_in_s']
  lengths=[];nonfinite={k:0 for k in need};negative={k:0 for k in ['charge_capacity_in_Ah','discharge_capacity_in_Ah']};time_decreases=0
  for cy in cycles:
   assert type(cy) is dict and all(k in cy for k in need)
   lens={k:len(cy[k]) for k in need};assert len(set(lens.values()))==1 and next(iter(lens.values()))>0;lengths.append(lens[need[0]])
   for k in need:
    assert type(cy[k]) in [list,tuple] and all(type(v) in [int,float] for v in cy[k]);nonfinite[k]+=sum(not math.isfinite(v) for v in cy[k])
   for k in negative:negative[k]+=sum(v<0 for v in cy[k] if math.isfinite(v))
   time_decreases+=sum(b<a for a,b in zip(cy['time_in_s'],cy['time_in_s'][1:]) if math.isfinite(a) and math.isfinite(b))
  # Stage label file contains only fixed train/validation IDs; test labels absent.
  labels=json.loads((S/'Life labels/CALB_labels.json').read_text());assert set(labels)==set(manifest['labels']['keys']) and len(labels)==22
  eol=labels[name];prefixes=[i for i in range(1,101) if i<eol and i<=len(cycles)] if eol>100 else []
  assert obj['cell_id']==name[:-4]
  out.append(dict(file_name=name,role='train' if name in manifest['train_cells'] else 'validation',cell_id=obj['cell_id'],top_keys=sorted(obj),cycle_keys=sorted(cycles[0]),nominal_capacity_Ah=nominal,stored_cycle_count=len(cycles),points_per_cycle_min=min(lengths),points_per_cycle_max=max(lengths),nonfinite_by_required_field=nonfinite,negative_capacity_points=negative,within_cycle_time_decreases=time_decreases,author_EOL_cycles=eol,eligible_prefix_count_from_pinned_rule=len(prefixes),first_prefix=prefixes[0] if prefixes else None,last_prefix=prefixes[-1] if prefixes else None,raw_fields_shape_aligned=True,resampled_tensor_measured=False,resampled_tensor_expected_from_source=[100,3,300],source_sha256=sha(p)))
 assert all(all(v==0 for v in x['nonfinite_by_required_field'].values()) for x in out),'nonfinite input found'
 result=dict(status='FIXED22_STAGE_AND_TWO_TYPED_SAMPLE_FIELD_AUDIT_PASS',at_utc=now(),samples=out,restricted_sample_loads=loads,numpy_imports=0,original_numpy_constructors_called=0,test_pkl_opened=0,test_label_values_decoded=0,new_fits=0,optimizer_steps=0,new_inference=0,model_loads=0,stage_manifest=str(S/'stage_manifest.json'),stage_manifest_sha256=sha(S/'stage_manifest.json'),source_sha256=sha(Path(__file__)),data_semantics_gate='PARTIAL_TWO_SAMPLES_ONLY_NOT_FULL_COHORT_APPROVAL',normalization_gate='NOT_RUN: train-only fitted label scaler required; per-cycle normalized curve path not executed',limitations=['Remaining20 serializations and actual fields not decoded/audited','Only stored complete early cycles, author totalEOL and filename split; not strict online RUL or physical identity confirmation','99-cycle CALB rule based on actual stored count; expected tensor shape is source-derived, not a successful loader run','Official test-entry conflict and two-process runtime remain; all train/model/test gates unchanged'])
 write('sample_audit.json',result);print(json.dumps(result,ensure_ascii=True),flush=True)
except BaseException as e:
 write('failure_receipt.json',dict(status='FAILED_STOP_NO_RETRY',at_utc=now(),error_type=type(e).__name__,error=str(e),restricted_sample_loads=loads,new_fits=0,optimizer_steps=0,test_access=False));raise
