from pathlib import Path
import json,zipfile,io,hashlib,time,importlib.util
import numpy as np
from scipy.io import loadmat
R=Path('/home/yndx/zxk/rul');O=R/'reports/nasa_remaining_source_inventory_20261018_root';P=R/'data/raw/NASA/original_2007/NASA_Battery_Data_Set.zip'
b=json.loads((O/'prospective_split.json').read_text());inv=json.loads((O/'inventory.json').read_text());start=time.monotonic()
total=json.loads((O/'two_reads_failure.json').read_text())['read_bytes'];result=[]
with (O/'two_reads_repair.claim').open('x') as f:f.write('Optional empty Capacity repair; cumulative bytes<=30MB; two same source IDs')
spec=importlib.util.spec_from_file_location('nasa_importer',R/'reports/data_v1_raw_nasa_20261018_root/import_nasa.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
with zipfile.ZipFile(P) as outer:
 for cid in b['next_two_reads']:
  assert cid not in b['roles']['locked']
  package=next(p for p in inv['packages'] if any(x['stem']==cid for x in p['mat_entries']))
  member=next(x for x in package['mat_entries'] if x['stem']==cid);total+=member['bytes'];assert total<=b['max_MAT_bytes']
  with zipfile.ZipFile(io.BytesIO(outer.read(package['outer_member']))) as z:raw=z.read(member['path'])
  d=loadmat(io.BytesIO(raw),squeeze_me=True,struct_as_record=False)[cid];rows=[]
  for k,op in enumerate(np.atleast_1d(d.cycle),1):
   if str(op.type)!='discharge':continue
   a=op.data;t=np.asarray(a.Time).reshape(-1);i=np.asarray(a.Current_measured).reshape(-1);v=np.asarray(a.Voltage_measured).reshape(-1)
   try:q,detail=mod.cutoff_capacity(t,i,v)
   except (AssertionError,ValueError):q=None;detail={'reason':'finite_shape_or_time_guard_failed'}
   active=i[i<-.1];cap=np.asarray(a.Capacity).reshape(-1) if hasattr(a,'Capacity') else np.array([])
   original=float(cap[0]) if cap.size and np.isfinite(cap[0]) else None
   rows.append({'discharge':len(rows)+1,'operation':k,'ambient_C':float(op.ambient_temperature),'median_active_current_A':float(np.median(active)) if len(active) else None,'capacity_common2p7V_Ah':q,'capacity_original_Ah':original,'valid':q is not None,'reason':detail.get('reason'),'min_voltage_V':float(np.min(v)) if v.size else None})
  event=next((r['discharge'] for r in rows if r['valid'] and r['capacity_common2p7V_Ah']<=1.6),None)
  valid=[r for r in rows if r['valid']];activevalues=[r['median_active_current_A'] for r in rows if r['median_active_current_A'] is not None]
  origins=[r for r in valid if r['discharge']>=20 and (event is None or r['discharge']<event)]
  result.append({'cell_id':cid,'source_SHA256':hashlib.sha256(raw).hexdigest(),'source_bytes':len(raw),'discharges':len(rows),'valid_common_cutoff':len(valid),'empty_author_capacity':sum(r['capacity_original_Ah'] is None for r in rows),'invalid_counts':{reason:sum(r['reason']==reason for r in rows) for reason in sorted({r['reason'] for r in rows if r['reason']})},'ambient_levels':sorted({r['ambient_C'] for r in rows}),'active_current_median_range_A':[min(activevalues),max(activevalues)] if activevalues else None,'first_valid_capacity_Ah':valid[0]['capacity_common2p7V_Ah'] if valid else None,'event80':event,'available_origins_ge20':len(origins),'source_rows':rows})
  assert time.monotonic()-start<b['max_wall_seconds']
d={'status':'COMPLETE_TWO_FROZEN_RAW_READS_AFTER_EMPTY_OPTIONAL_FIELD_REPAIR','cells':result,'cumulative_MAT_bytes_read':total,'elapsed_seconds':time.monotonic()-start,'new_fits':0,'optimizer_steps':0,'test_MAT_reads':0}
with (O/'two_raw_cells.json').open('x') as f:json.dump(d,f,indent=2)
summary={**d,'cells':[{k:v for k,v in c.items() if k!='source_rows'} for c in result]}
with (O/'two_raw_summary.json').open('x') as f:json.dump(summary,f,indent=2)
print(json.dumps(summary))
