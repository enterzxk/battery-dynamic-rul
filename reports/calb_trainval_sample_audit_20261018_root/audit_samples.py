"""Create fixed22 stage and audit two primitive samples; no ordinary unpickle/model/test."""
from pathlib import Path
import ast,json,hashlib,zipfile,re,pickletools,pickle,io,math,datetime,resource
R=Path('/home/yndx/zxk/rul');O=R/'reports/calb_trainval_sample_audit_20261018_root';S=R/'data/source_audit/calb_v11_trainval_stage_20261018_root'
A=R/'reports/calb_acquisition_20261018_root_v2'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(name,obj):
 with (O/name).open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n')
counters=dict(extracted_trainval_files=0,static_scans=0,restricted_sample_loads=0,test_pkl_opened=0,test_label_values_decoded=0,new_fits=0,optimizer_steps=0,model_loads=0)
try:
 resource.setrlimit(resource.RLIMIT_AS,(768*1024**2,768*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(90,90))
 rec=json.loads((A/'acquisition_receipt.json').read_text());cov=json.loads((A/'archive_coverage.json').read_text())
 archive=Path(rec['archive_path']);assert sha(archive)==rec['sha256']
 P=R/'repos/pinned/BatteryLife_3b17bb53202e10711deae0448c91f84144bb3dd9'
 splits={}
 for n in ast.walk(ast.parse((P/'data_provider/data_split_recorder.py').read_text())):
  if isinstance(n,ast.Assign):
   for t in n.targets:
    if isinstance(t,ast.Name) and t.id in ['CALB_train_files','CALB_val_files','CALB_test_files']:splits[t.id]=ast.literal_eval(n.value)
 allowed=set(splits['CALB_train_files']+splits['CALB_val_files']);test=set(splits['CALB_test_files']);assert len(allowed)==22 and not allowed&test
 assert set(x['file_name'] for x in cov['selected_members'])==allowed
 S.mkdir(exist_ok=False);(S/'CALB').mkdir();(S/'Life labels').mkdir()
 files=[]
 with zipfile.ZipFile(archive) as z:
  for x in cov['selected_members']:
   assert x['file_name'] in allowed and x['bytes']<=8*1024**2
   raw=z.read(x['member']);assert len(raw)==x['bytes'] and hashlib.sha256(raw).hexdigest()==x['sha256']
   p=S/'CALB'/x['file_name']
   with p.open('xb') as f:f.write(raw)
   files.append(dict(name=x['file_name'],role=x['role'],path=str(p),bytes=len(raw),sha256=x['sha256']));counters['extracted_trainval_files']+=1
 labels_archive=Path(cov['labels']['archive_path']);assert sha(labels_archive)==cov['labels']['archive_sha256']
 with zipfile.ZipFile(labels_archive) as z:raw=z.read(cov['labels']['member'])
 labels={}
 for name in sorted(allowed):
  matches=re.findall(rb'"'+re.escape(name.encode('ascii'))+rb'"\s*:\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*[,}]',raw)
  assert len(matches)==1;val=json.loads(matches[0]);assert type(val) in [int,float] and math.isfinite(val) and val>0;labels[name]=val
 lp=S/'Life labels/CALB_labels.json'
 with lp.open('x',encoding='utf-8') as f:json.dump(labels,f,indent=2);f.write('\n')
 manifest=dict(status='FIXED22_STAGE_CREATED_NOT_DATA_AUDIT_PASS',created_utc=now(),root=str(S),record_id=19688272,train_cells=splits['CALB_train_files'],validation_cells=splits['CALB_val_files'],test_files_present=False,test_label_keys_present=False,files=files,labels=dict(path=str(lp),sha256=sha(lp),keys=sorted(labels),trainval_numeric_labels_decoded=22,test_values_decoded=0),source_archive=dict(path=str(archive),sha256=rec['sha256']),source_coverage_sha256=sha(A/'archive_coverage.json'),new_fits_allowed=False)
 with (S/'stage_manifest.json').open('x',encoding='utf-8') as f:json.dump(manifest,f,indent=2);f.write('\n')
 targets=[splits['CALB_train_files'][0],splits['CALB_val_files'][0]]
 blocked={'GLOBAL','STACK_GLOBAL','REDUCE','NEWOBJ','NEWOBJ_EX','BUILD','INST','OBJ','EXT1','EXT2','EXT4','PERSID','BINPERSID','NEXT_BUFFER','READONLY_BUFFER'}
 scans=[];raws={}
 for name in targets:
  p=S/'CALB'/name;raw=p.read_bytes();assert len(raw)<=8*1024**2;bad={};ops=0;last=None
  for op,arg,pos in pickletools.genops(raw):
   ops+=1;assert ops<=2000000;last=(op.name,pos)
   if op.name in blocked:bad[op.name]=bad.get(op.name,0)+1
  scans.append(dict(file_name=name,bytes=len(raw),opcodes=ops,last_opcode=last[0],stop_at_exact_end=last[0]=='STOP' and last[1]==len(raw)-1,blocked_opcode_counts=bad,sha256=hashlib.sha256(raw).hexdigest()));counters['static_scans']+=1;raws[name]=raw
 write('serialization_gate.json',dict(status='PASS' if all(not x['blocked_opcode_counts'] and x['stop_at_exact_end'] for x in scans) else 'STOP_NO_LOAD',scans=scans,ordinary_unpickle_allowed=False,scope='Two selected samples only; remaining20 not statically scanned'))
 assert all(not x['blocked_opcode_counts'] and x['stop_at_exact_end'] for x in scans),'Unsupported serialization; do not expand allowlist'
 class DenyAllUnpickler(pickle.Unpickler):
  def find_class(self,module,name):raise pickle.UnpicklingError('GLOBAL_DENIED')
  def persistent_load(self,pid):raise pickle.UnpicklingError('PERSISTENT_DENIED')
 samples=[]
 need=['current_in_A','voltage_in_V','charge_capacity_in_Ah','discharge_capacity_in_Ah','time_in_s']
 for name in targets:
  obj=DenyAllUnpickler(io.BytesIO(raws[name])).load();counters['restricted_sample_loads']+=1
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
  assert type(obj) is dict and isinstance(obj['cycle_data'],list)
  nominal=obj['nominal_capacity_in_Ah'];assert type(nominal) in [int,float] and nominal>0
  cycles=obj['cycle_data'];assert 0<len(cycles)<=500
  lengths=[];nonfinite={k:0 for k in need};negative={k:0 for k in ['charge_capacity_in_Ah','discharge_capacity_in_Ah']};time_decreases=0
  for cy in cycles:
   assert type(cy) is dict and all(k in cy for k in need)
   lens={k:len(cy[k]) for k in need};assert len(set(lens.values()))==1 and next(iter(lens.values()))>0
   lengths.append(lens[need[0]])
   for k in need:
    assert type(cy[k]) in [list,tuple] and all(type(v) in [int,float] for v in cy[k])
    nonfinite[k]+=sum(not math.isfinite(v) for v in cy[k])
   for k in negative:negative[k]+=sum(v<0 for v in cy[k] if math.isfinite(v))
   time_decreases+=sum(b<a for a,b in zip(cy['time_in_s'],cy['time_in_s'][1:]) if math.isfinite(a) and math.isfinite(b))
  eol=labels[name]
  prefixes=[i for i in range(1,101) if i<eol and i<=len(cycles)] if eol>100 else []
  sample=dict(file_name=name,role='train' if name in splits['CALB_train_files'] else 'validation',cell_id=obj.get('cell_id'),top_level_keys=sorted(obj),nominal_capacity_Ah=nominal,stored_cycle_count=len(cycles),cycle_keys_first=sorted(cycles[0]),points_per_cycle_min=min(lengths),points_per_cycle_max=max(lengths),nonfinite_by_required_field=nonfinite,negative_capacity_points=negative,within_cycle_time_decreases=time_decreases,author_EOL_cycles=eol,eligible_prefix_count_from_pinned_integer_rule=len(prefixes),prefix_first=prefixes[0] if prefixes else None,prefix_last=prefixes[-1] if prefixes else None,curve_tensor_shape_not_yet_executed='[100,3,300] expected from source, not measured',mask_rule='first i positions visible; effective prefix bounded by stored cycles',raw_fields_shape_aligned=True,sha256=sha(S/'CALB'/name))
  samples.append(sample)
 assert all(all(v==0 for v in x['nonfinite_by_required_field'].values()) for x in samples),'nonfinite input fields found'
 result=dict(status='FIXED22_STAGE_AND_TWO_PRIMITIVE_SAMPLE_AUDIT_PASS',at_utc=now(),samples=samples,counters=counters,stage_manifest_path=str(S/'stage_manifest.json'),stage_manifest_sha256=sha(S/'stage_manifest.json'),serialization_gate_sha256=sha(O/'serialization_gate.json'),sample_selection='First pinned official train and validation IDs; two different temperature groups, fixed before load',measured_tensor_preprocessing_executed=False,normalization='No scaler fit this action; later train-only label scaler must be reused for validation. Official per-cycle voltage/current/capacity normalization still requires bounded preprocessing verification.',limits=['Only2 of22 cells decoded; no full-cohort semantic/asof approval','Stored complete-cycle curves and author totalEOL are not strict online true-event RUL','Filename split is not verified physical identity; actual generator binding unverified','Official test-evaluation entry conflict and two-process runtime remain; no fit/model authorization'],bindings={str(P/'data_provider/data_loader.py'):sha(P/'data_provider/data_loader.py'),str(P/'data_provider/data_split_recorder.py'):sha(P/'data_provider/data_split_recorder.py'),str(Path(__file__)):sha(Path(__file__))},new_fits_allowed=False)
 write('sample_audit.json',result);print(json.dumps(result,ensure_ascii=True),flush=True)
except BaseException as e:
 write('failure_receipt.json',dict(status='FAILED_STOP_PRESERVE_STAGE',at_utc=now(),error_type=type(e).__name__,error=str(e),counters=counters));raise
