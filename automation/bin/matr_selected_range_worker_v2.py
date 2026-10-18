import sys,io,json,pathlib,hashlib,time
sys.path.insert(0,'/home/yndx/zxk/rul/runtime_deps/h5py_3_11')
import h5py,numpy as np
R=pathlib.Path('/home/yndx/zxk/rul');O=R/'reports/matr_raw_range_20261018_root';O.mkdir(exist_ok=True)
B={'source_url':'https://data.matr.io/assetstore/f7/eb/f7eb42ebc0584cba855a98d127fc6842','source_bytes':2007331155,'source_etag':'e350d061ae571ba32cf16b7962b40a71-120','max_bytes':33554432,'max_range_requests':32,'max_seconds':180,'cells':['MATR_b2c0','MATR_b2c22'],'fields':['summary.cycle','summary.QDischarge','barcode','policy_readable'],'new_fits':0,'test_cell_reads':0,'old_full_download_budget':'Consumed/stopped immutable; this is a distinct selected-field range-read protocol, not a full-download retry'}
assert json.loads((O/'range_budget.json').read_text())==B
start=time.monotonic();prior=json.loads((O/'failure.json').read_text());blocks={int(p.stem.split('_')[1]):p.read_bytes() for p in O.glob('block_*.bin')};receipts=prior['ranges'];used=sum(len(v) for v in blocks.values())
class RF(io.RawIOBase):
 def __init__(self):self.pos=0
 def readable(self):return True
 def seekable(self):return True
 def tell(self):return self.pos
 def seek(self,o,w=0):
  self.pos=o if w==0 else self.pos+o if w==1 else B['source_bytes']+o
  assert self.pos>=0
  return self.pos
 def read(self,n=-1):
  global used
  if n<0:n=B['source_bytes']-self.pos
  n=min(n,B['source_bytes']-self.pos);result=bytearray()
  while n>0:
   key=self.pos//1048576;offset=key*1048576
   if key not in blocks:
    size=min(1048576,B['source_bytes']-offset)
    assert used+size<=B['max_bytes'] and len(receipts)<B['max_range_requests'] and time.monotonic()-start<B['max_seconds']
    print(json.dumps({'request':True,'offset':offset,'size':size}),flush=True)
    data=sys.stdin.buffer.read(size);assert len(data)==size
    blocks[key]=data;used+=size
    p=O/('block_'+str(key)+'.bin');p.write_bytes(data)
    receipts.append({'offset':offset,'bytes':size,'sha256':hashlib.sha256(data).hexdigest()})
   block=blocks[key];k=self.pos-offset;take=min(n,len(block)-k);assert take>0
   result.extend(block[k:k+take]);self.pos+=take;n-=take
  return bytes(result)
 def readinto(self,b):
  data=self.read(len(b));b[:len(data)]=data;return len(data)
cells=[]
try:
 rf=RF()
 with h5py.File(rf,'r') as f:
  batch=f['batch']
  for i in [0,22]:
   s=f[batch['summary'][i,0]];cy=np.asarray(s['cycle'][:]).reshape(-1);q=np.asarray(s['QDischarge'][:]).reshape(-1)
   assert len(cy)==len(q) and np.isfinite(cy).all() and np.all(np.diff(cy)>0)
   valid=np.isfinite(q)&(q>0)&(q<=2.2)&(cy>=1)
   cross=np.flatnonzero(valid&(q<=.88));event=int(cy[cross[0]]) if len(cross) else None
   fields={}
   for name in ['barcode','policy_readable']:
    if name in batch:
     ds=f[batch[name][i,0]];a=np.asarray(ds[:]).reshape(-1);fields[name]=''.join(chr(int(x)) for x in a if x) if ds.attrs.get('MATLAB_class')==b'char' else {'matlab_class':str(ds.attrs.get('MATLAB_class')),'values':a.tolist()}
   cid='MATR_b2c'+str(i);out={'cell_id':cid,'fields':fields,'actual_cycles':cy.tolist(),'capacity_Ah':q.tolist(),'event80_actual_cycle':event,'valid_rows':int(valid.sum()),'first_actual_cycle':float(cy[0]),'invalid_rows':int((~valid).sum())}
   with (O/(cid+'_raw_summary.json')).open('x') as h:json.dump(out,h,indent=2)
   oldp=R/'reports/matr_schema_audit/run_v2_20261016T031830319822Z/cells'/(cid+'.pkl.cycles.json');old=json.loads(oldp.read_text());oq=np.array([x['capacity_Ah'] for x in old]);m=min(len(oq),len(q)-1)
   cells.append({k:v for k,v in out.items() if k not in ['actual_cycles','capacity_Ah']})
   cells[-1].update(old_processed_rows=len(oq),old_event_row_1based=next((j+1 for j,v in enumerate(oq) if v<=.88),None),capacity_difference_assuming_raw_shift1=float(np.max(abs(oq[:m]-q[1:1+m]))))
 d={'status':'COMPLETE_TWO_RAW_SUMMARIES','cells':cells,'bytes_read':used,'range_requests':len(receipts),'elapsed_seconds':time.monotonic()-start,'blocks':receipts,'full_raw_sha256':'UNKNOWN_NOT_FULLY_DOWNLOADED','source_etag':B['source_etag'],'new_fits':0,'test_cell_reads':0}
 with (O/'completion.json').open('x') as h:json.dump(d,h,indent=2)
 print(json.dumps({'done':True,'result':{k:v for k,v in d.items() if k!='blocks'}}),flush=True)
except BaseException as e:
 d={'status':'FAILED_STOP','error':str(e),'type':type(e).__name__,'bytes_read':used,'ranges':receipts,'elapsed_seconds':time.monotonic()-start}
 with (O/'repair_failure.json').open('x') as h:json.dump(d,h,indent=2)
 print(json.dumps({'done':True,'failure':d}),flush=True)
 raise
