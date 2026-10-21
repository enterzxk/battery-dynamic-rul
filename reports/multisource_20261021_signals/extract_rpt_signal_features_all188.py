#!/usr/bin/env python3
"""One-pass cached RPT signal feature extraction for frozen train+development cells."""
import argparse,hashlib,json,math,struct,sys,time,zlib
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
R=Path('/home/yndx/zxk/rul');D=R/'reports/multisource_20261021_signals'
RAW=R/'data/processed/ISU_ILCC_DataV2_v1/.raw_members';DATA=R/'data/processed/ISU_ILCC_DataV2_v1'
CD=R/'reports/isu_ilcc_clock_source_20261020_root/central_directory_receipt.json'
CO=R/'reports/isu_ilcc_capacity_probe_20261020_root/cohort.json'
DM=R/'reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json'
PILOT=D/'rpt_signal_features_v2.jsonl';GO=D/'ROOT_GO_ALL188.json'
OUT=D/'all188_rpt_features_v1';FAIL=D/'all188.failure_receipt.json'
MAX_COMP=704000000;MAX_UNCOMP=6000000000;MAX_MEMBER=268435456;MAX_OUT=134217728
V=np.linspace(3.,4.2,121);VSEL=list(range(0,121,5));STEP=.01
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def j(p):return json.loads(Path(p).read_text(encoding='utf8'))
def finite(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(float(x))
def fail(v):
 try:
  with FAIL.open('x',encoding='utf8') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
 except FileExistsError:pass
def gate():
 g=j(GO);members_hash=hashlib.sha256(json.dumps(sorted((x['name'],x['compressed_bytes'],x['bytes'],x['crc32']) for x in j(CD)['entries'] if x['name'].startswith('RPT_json/')),separators=(',',':')).encode()).hexdigest()
 want={'status':'GO_RPT_SIGNAL_FEATURES_ALL188','script_sha256':sha(Path(__file__).resolve()),
 'central_receipt_sha256':sha(CD),'cohort_sha256':sha(CO),'data_manifest_sha256':sha(DM),'pilot_feature_sha256':sha(PILOT),
 'rpt_member_inventory_sha256':members_hash,'member_count':188,'train_members':125,'development_members':63,'locked_members':0,
 'max_cached_compressed_bytes':MAX_COMP,'max_uncompressed_total_bytes':MAX_UNCOMP,'max_member_uncompressed_bytes':MAX_MEMBER,
 'max_feature_output_bytes':MAX_OUT,'network_gets':0,'locked_reads':0,'model_fits':0,'training_allowed':False,'max_workers':1}
 for k,v in want.items():
  if g.get(k)!=v:raise RuntimeError('GO_BINDING_MISMATCH:'+k)
 age=(datetime.now(timezone.utc)-datetime.fromisoformat(g['issued_utc'].replace('Z','+00:00'))).total_seconds()
 if age<0 or age>600:raise RuntimeError('GO_STALE')
 s=j(R/'automation/state/coordinator.json')
 if s.get('state')!='ACTIVE' or s.get('owner')!=g.get('owner') or s.get('thread_id')!=g.get('owner') or s.get('actual_cwd')!=str(R) or s.get('takeover_verified') is not True:raise RuntimeError('OWNER_STATE_STOP')
 if sha(R/'automation/state/coordinator.lock')!=g.get('coordinator_lock_sha256'):raise RuntimeError('LOCK_HASH_STOP')
 return g,members_hash
def structure(d):
 x={}
 for k,v in d.items():
  if isinstance(v,dict):x[str(k)]={str(a):{'type':type(b).__name__,'len':len(b)} for a,b in v.items() if isinstance(b,(list,dict,str))}
  elif isinstance(v,(list,str)):x[str(k)]={'type':type(v).__name__,'len':len(v)}
  else:x[str(k)]={'type':type(v).__name__}
 return x
def interp_curve(d,key,i):
 z=d.get(key)
 if not isinstance(z,dict) or not isinstance(z.get('Q'),list) or not isinstance(z.get('V'),list):return None,'field_missing'
 if i>=len(z['Q']) or i>=len(z['V']):return None,'index_missing'
 q=z['Q'][i];v=z['V'][i]
 if not isinstance(q,list) or not isinstance(v,list) or len(q)!=len(v):return None,'shape_invalid'
 q=np.asarray(q,dtype=np.float64);v=np.asarray(v,dtype=np.float64);ok=np.isfinite(q)&np.isfinite(v);q=q[ok];v=v[ok]
 if len(q)<3:return None,'too_few_finite_points'
 ix=np.argsort(v,kind='mergesort');v=v[ix];q=q[ix];x,inv=np.unique(v,return_inverse=True)
 if len(x)<3:return None,'too_few_unique_voltage_points'
 y=np.bincount(inv,weights=q)/np.bincount(inv);qv=np.interp(V,x,y,left=np.nan,right=np.nan)
 dq=np.full(qv.shape,np.nan)
 for k in range(1,len(qv)-1):
  if np.isfinite(qv[k-1]) and np.isfinite(qv[k+1]):dq[k]=(qv[k+1]-qv[k-1])/(2*STEP)
 return (qv,dq),'ok'
def pilot_cells():
 result={}
 for line in PILOT.read_text(encoding='utf8').splitlines():
  x=json.loads(line);result.setdefault(x['cell_id'],[]).append(x)
 return result
def valid_map(cell,manifest):
 p=DATA/(cell+'.json')
 rec=j(p).get('records',[])
 return {int(x['source_rpt_index']):x for x in rec if x.get('valid') is True}
def row_from_source(cell,role,member,data,rawsha,idx,start,stop):
 vals={};status={};missing={}
 n=max((len(v) for k,v in data.items() if 'capacity' in str(k).lower() and isinstance(v,list)),default=0)
 for k,v in data.items():
  if 'capacity' in str(k).lower() and isinstance(v,list):
   x=v[idx] if idx<len(v) else None
   if isinstance(x,list):x=None
   name='src_'+str(k);vals[name]=float(x) if finite(x) else None
   if vals[name] is None:missing[name]='source_scalar_missing_or_invalid'
 for rate in (2,5):
  for leg in ('charge','discharge'):
   name='C%d_%s'%(rate,leg);curve,st=interp_curve(data,'QV_%s_C_%d'%(leg,rate),idx)
   if curve is None:status[name]=st;continue
   qv,dq=curve
   for j in VSEL:
    volt=V[j];vals[name+'_Q_at_V%.2f'%volt]=float(qv[j]) if np.isfinite(qv[j]) else None
    vals[name+'_dQdV_at_V%.2f'%volt]=float(dq[j]) if np.isfinite(dq[j]) else None
   status[name]='ok'
 return {'cell_id':cell,'source_rpt_index':idx,'start':start,'stop':stop,'features_visible_at':'stop' if isinstance(stop,str) and stop not in ('','[]') else None,
 'data_v2_valid':True,'feature_names':list(vals),'values':vals,'status':status,'missing':missing,'source_member':member,'source_member_sha256':rawsha}
def raw_member(cell,member,meta):
 hp=RAW/(cell+'.json.header.bin');rp=RAW/(cell+'.json.range2.bin');h=hp.read_bytes();pair=rp.read_bytes()
 if len(h)!=30 or h[:4]!=b'PK\x03\x04':raise RuntimeError('HEADER_INVALID:'+cell)
 _,_,flags,method,_,_,_,_,_,nl,xl=struct.unpack('<4s5H3I2H',h)
 if flags!=meta['flags'] or method!=8 or method!=meta['method'] or nl+xl+meta['compressed_bytes']!=len(pair):raise RuntimeError('ZIP_METADATA_MISMATCH:'+cell)
 if pair[:nl].decode('utf8' if flags&2048 else 'cp437')!=member:raise RuntimeError('MEMBER_NAME_MISMATCH:'+cell)
 comp=pair[nl+xl:];dec=zlib.decompressobj(-15);raw=dec.decompress(comp,meta['bytes']+1)
 if len(raw)>meta['bytes'] or dec.unconsumed_tail:raise RuntimeError('MEMBER_INFLATE_LIMIT:'+cell)
 raw+=dec.flush(meta['bytes']+1-len(raw))
 if not dec.eof or len(raw)!=meta['bytes'] or zlib.crc32(raw)&0xffffffff!=int(meta['crc32'],16):raise RuntimeError('CRC_SIZE_FAILURE:'+cell)
 x=json.loads(raw.decode('utf-8-sig'));x=json.loads(x) if isinstance(x,str) else x
 if not isinstance(x,dict):raise RuntimeError('JSON_ROOT_INVALID:'+cell)
 st=x.get('start_stop_time')
 if not isinstance(st,dict) or not isinstance(st.get('stop'),list):raise RuntimeError('RPT_TIME_SCHEMA:'+cell)
 return x,raw,st
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--run',action='store_true');a=ap.parse_args()
 started=time.monotonic();compressed=uncompressed=outbytes=0;done=[];claim=None
 try:
  if not a.run:raise ValueError('REQUIRES_EXPLICIT_RUN')
  g,mh=gate()
  if OUT.exists():raise FileExistsError('OUTPUT_DIRECTORY_EXISTS')
  roles=j(CO)['roles'];cd={x['name']:x for x in j(CD)['entries']}
  dm=j(DM);filemeta=dm.get('files',{})
  pilots=pilot_cells()
  selected=[]
  for cell,role in roles.items():
   if role not in ('train','development'):continue
   member=next((x for x in cd if x.startswith('RPT_json/') and x.endswith('/'+cell+'.json')),None)
   if not member:raise RuntimeError('MEMBER_NOT_FOUND:'+cell)
   selected.append((cell,role,member,cd[member]))
  if len(selected)!=188 or sum(r=='train' for _,r,_,_ in selected)!=125 or sum(r=='development' for _,r,_,_ in selected)!=63:raise RuntimeError('ROLE_COUNTS_STOP')
  OUT.mkdir()
  inventory=[]
  for cell,role,member,meta in selected:
   expected=filemeta.get(cell,{}).get('sha256')
   source_records=[]
   if cell in pilots:
    if cell not in ('G1C1','G20C1'):raise RuntimeError('UNEXPECTED_PILOT_REUSE')
    if expected is None:raise RuntimeError('DATAV2_MANIFEST_MEMBER_MISSING')
    if sha(DATA/(cell+'.json'))!=expected:raise RuntimeError('DATAV2_FILE_HASH_MISMATCH:'+cell)
    vm=valid_map(cell,filemeta)
    for pr in pilots[cell]:
     idx=int(pr['source_rpt_index']);dr=vm.get(idx)
     if dr and dr.get('stop')==pr.get('stop'):
      names=[];values={}
      for k,v in pr['values'].items():
       if ('_Q_at_V' in k or '_dQdV_at_V' in k) and (float(k.rsplit('V',1)[1]) if False else True):
        # Keep only the baseline's 0.05 V key grid.
        import re
        m=re.search(r'_at_V([0-9]+\.[0-9]{2})$',k)
        if m and abs((float(m.group(1))-3.0)/.05-round((float(m.group(1))-3.0)/.05))<1e-7:
         names.append(k);values[k]=v
       elif k.startswith('src_capacity_'):
        names.append(k);values[k]=v
      source_records.append({'cell_id':cell,'source_rpt_index':idx,'start':pr.get('start'),'stop':pr.get('stop'),
       'features_visible_at':pr.get('features_visible_at'),'data_v2_valid':True,'feature_names':names,'values':values,
       'status':pr.get('status',{}),'missing':pr.get('missing',{}),'source_member':member,
       'source_member_sha256':pr.get('source_member_sha256')})
    rawsha=next((x.get('source_member_sha256') for x in pilots[cell]),None)
    structure=pilots[cell][0].get('source_top_level_structure',{})
    src_n=len(pilots[cell])
    if len(source_records)!=len(vm) or {r['source_rpt_index'] for r in source_records}!={int(k) for k in vm}:raise RuntimeError('VALID_RPT_JOIN_MISMATCH:'+cell)
    cbytes=0;ubytes=0;crc=meta['crc32']
   else:
    if meta['bytes']>MAX_MEMBER:raise RuntimeError('MEMBER_OVER_LIMIT:'+cell)
    if expected is None:raise RuntimeError('DATAV2_MANIFEST_MEMBER_MISSING:'+cell)
    if sha(DATA/(cell+'.json'))!=expected:raise RuntimeError('DATAV2_FILE_HASH_MISMATCH:'+cell)
    vm=valid_map(cell,filemeta)
    x,raw,st=raw_member(cell,member,meta);rawsha=hashlib.sha256(raw).hexdigest()
    for idx,dr in vm.items():
     if idx<len(st['stop']) and dr.get('stop')==st['stop'][idx]:
      source_records.append(row_from_source(cell,role,member,x,rawsha,idx,st.get('start',[None]*len(st['stop']))[idx],st['stop'][idx]))
    structure=structure_fn=globals()['structure'](x);src_n=len(st['stop'])
    if len(source_records)!=len(vm) or {r['source_rpt_index'] for r in source_records}!={int(k) for k in vm}:raise RuntimeError('VALID_RPT_JOIN_MISMATCH:'+cell)
    cbytes=(RAW/(cell+'.json.header.bin')).stat().st_size+(RAW/(cell+'.json.range2.bin')).stat().st_size;ubytes=len(raw);crc=meta['crc32']
   compressed+=cbytes;uncompressed+=ubytes
   if compressed>MAX_COMP or uncompressed>MAX_UNCOMP:raise RuntimeError('TOTAL_INPUT_CAP:'+cell)
   rec={'schema':'isu_ilcc_rpt_features_cell_v1','cell_id':cell,'role':role,'group_id':'G'+cell.split('C')[0][1:],
    'source_member':member,'source_member_sha256':rawsha,'source_crc32':crc,'source_records_total':src_n,
    'valid_data_v2_records':len(source_records),'source_top_level_structure':structure,'records':source_records}
   b=(json.dumps(rec,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf8')
   out=OUT/(cell+'.json')
   with out.open('xb') as f:f.write(b)
   outbytes+=len(b)
   if outbytes>MAX_OUT:raise RuntimeError('FEATURE_OUTPUT_CAP:'+cell)
   if cell not in pilots:del raw,x
   inventory.append({'cell_id':cell,'role':role,'path':str(out.relative_to(R)),'sha256':hashlib.sha256(b).hexdigest(),'records':len(source_records),'source_records_total':src_n,'cached_compressed_bytes':cbytes,'uncompressed_bytes':ubytes,'reused_pilot':cell in pilots})
   done.append(cell)
   if time.monotonic()-started>7200:raise RuntimeError('WALL_LIMIT')
  summary={'status':'ALL188_FEATURE_CACHE_COMPLETE','cells':len(inventory),'train':125,'development':63,'locked':0,
   'rows':sum(x['records'] for x in inventory),'cached_compressed_bytes':compressed,'uncompressed_bytes':uncompressed,
   'feature_output_bytes':outbytes,'network_gets':0,'model_fits':0,'inventory':inventory}
  p=OUT/'manifest.json';bb=(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode()
  if outbytes+len(bb)>MAX_OUT:raise RuntimeError('FEATURE_OUTPUT_CAP_MANIFEST')
  with p.open('xb') as f:f.write(bb)
  print(json.dumps({'status':summary['status'],'cells':summary['cells'],'rows':summary['rows'],'cache_bytes':compressed,
   'inflate_bytes':uncompressed,'feature_bytes':outbytes,'manifest_sha256':hashlib.sha256(bb).hexdigest()},ensure_ascii=False))
 except Exception as e:
  fail({'status':'FAILED_STOP_NO_RETRY','error_type':type(e).__name__,'error':str(e)[:300],
   'cells_written':len(done),'cached_compressed_bytes':compressed,'uncompressed_bytes':uncompressed,
   'feature_output_bytes':outbytes,'network_gets':0,'locked_reads':0,'fits':0})
  raise
if __name__=='__main__':main()
