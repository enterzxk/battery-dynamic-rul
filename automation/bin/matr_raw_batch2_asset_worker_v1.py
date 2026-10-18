import sys,io,json,pathlib,hashlib,time,ast,csv,datetime
sys.path.insert(0,'/home/yndx/zxk/rul/runtime_deps/h5py_3_11')
import h5py,numpy as np
R=pathlib.Path('/home/yndx/zxk/rul');BASE=R/'reports/matr_raw_range_20261018_root';O=R/'reports/matr_raw_batch2_datav1_20261018_root';O.mkdir(exist_ok=False)
DATA=R/'data/processed/data_v1_matr_raw_batch2'
SPLIT=R/'repos/pinned/BatteryLife_3b17bb53202e10711deae0448c91f84144bb3dd9/data_provider/data_split_recorder.py'
roles={}
for n in ast.parse(SPLIT.read_text()).body[0].body:
 if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name):
  for role in ['train','val','test']:
   if n.targets[0].id=='MATR_'+role+'_files':
    for name in ast.literal_eval(n.value):
     if name.startswith('MATR_b2c'):roles[int(name.split('b2c')[1].split('.')[0])]=role
ids=sorted(i for i,r in roles.items() if r!='test' and i not in [12,44]);assert len(ids)==35
B={'source_url':'https://data.matr.io/assetstore/f7/eb/f7eb42ebc0584cba855a98d127fc6842','source_bytes':2007331155,'source_etag':'e350d061ae571ba32cf16b7962b40a71-120','max_new_network_bytes':33554432,'max_new_requests':32,'max_seconds':180,'source_indices':ids,'roles':{str(i):roles[i] for i in ids},'two_raw_cycle_checks':[[0,100],[22,100]],'test_indices_excluded':sorted(i for i,r in roles.items() if r=='test'),'special_shift_quarantine':[12,44],'continuation_aliases_not_in_cohort':[7,8,9,15,16],'nominal_Ah':1.1,'event':'first valid actual source cycle summary.QDischarge<=.88Ah; otherwise right censor at last valid cycle','origins':'all valid source cycles>=100 before event or <=censor','features':'age,currentSOH,past20 and past100 TheilSen using actual cycle denominator; masks if numeric window incomplete','no_imputation':True,'test_access':False,'predictive_fits':0}
def dump(p,d):
 with p.open('x') as f:json.dump(d,f,ensure_ascii=False,indent=2);f.write('\n')
dump(O/'protocol.json',B)
start=time.monotonic();old=json.loads((BASE/'completion.json').read_text());blocks={}
for r in old['blocks']:
 k=r['offset']//1048576;b=(BASE/('block_'+str(k)+'.bin')).read_bytes();assert hashlib.sha256(b).hexdigest()==r['sha256'];blocks[k]=b
new=[];used=0
class RF(io.RawIOBase):
 def __init__(self):self.pos=0
 def readable(self):return True
 def seekable(self):return True
 def tell(self):return self.pos
 def seek(self,o,w=0):
  self.pos=o if w==0 else self.pos+o if w==1 else B['source_bytes']+o;assert self.pos>=0;return self.pos
 def read(self,n=-1):
  global used
  if n<0:n=B['source_bytes']-self.pos
  n=min(n,B['source_bytes']-self.pos);result=bytearray()
  while n>0:
   key=self.pos//1048576;offset=key*1048576
   if key not in blocks:
    size=min(1048576,B['source_bytes']-offset)
    assert used+size<=B['max_new_network_bytes'] and len(new)<B['max_new_requests'] and time.monotonic()-start<B['max_seconds']
    print(json.dumps({'request':True,'offset':offset,'size':size}),flush=True);b=sys.stdin.buffer.read(size);assert len(b)==size
    blocks[key]=b;used+=size;(O/('block_'+str(key)+'.bin')).write_bytes(b);new.append({'offset':offset,'bytes':size,'sha256':hashlib.sha256(b).hexdigest()})
   b=blocks[key];k=self.pos-offset;take=min(n,len(b)-k);assert take>0;result.extend(b[k:k+take]);self.pos+=take;n-=take
  return bytes(result)
 def readinto(self,b):
  d=self.read(len(b));b[:len(d)]=d;return len(d)
def features(cy,q,valid,t):
 out={'origin_cycle':int(t),'visible_through_cycle':int(t),'soh':float(q[cy==t][0]/1.1)}
 for width in [20,100]:
  ix=np.flatnonzero(valid&(cy<=t)&(cy>=t-width+1));x=cy[ix];y=q[ix]/1.1;ok=len(ix)==width and np.all(np.diff(x)==1)
  if ok:
   a,b=np.triu_indices(width,1);rate=float(np.median((y[b]-y[a])/(x[b]-x[a])))
  else:rate=None
  out.update({f'rate{width}_per_cycle':rate,f'rate{width}_missing':not ok})
 return out
try:
 rf=RF();cells=[];summaries={};checks=[]
 with h5py.File(rf,'r') as f:
  batch=f['batch']
  for i,t in B['two_raw_cycle_checks']:
   s=f[batch['summary'][i,0]];cy=np.asarray(s['cycle'][:]).reshape(-1);q=np.asarray(s['QDischarge'][:]).reshape(-1);j=int(np.flatnonzero(cy==t)[0]);c=f[batch['cycles'][i,0]]
   qd=np.asarray(f[c['Qd'][j,0]][:]).reshape(-1);tm=np.asarray(f[c['t'][j,0]][:]).reshape(-1)
   delta=float(abs(qd.max()-q[j]));assert delta<1e-6 and np.isfinite(qd).all() and np.isfinite(tm).all() and np.all(np.diff(tm)>=0)
   valid=np.isfinite(q)&(q>0)&(q<=2.2)&(cy>=1);assert features(cy,q,valid,t)==features(cy[cy<=t],q[cy<=t],valid[cy<=t],t)
   checks.append({'cell_id':'MATR_b2c'+str(i),'actual_cycle':t,'raw_cycle_index':j,'summary_capacity_Ah':float(q[j]),'raw_Qd_max_Ah':float(qd.max()),'difference_Ah':delta,'raw_points':len(qd),'time_nondecreasing':True,'truncated_feature_equality':True})
  dump(O/'two_raw_cycle_check.json',{'status':'PASS','checks':checks,'source_etag':B['source_etag']})
  for i in ids:
   s=f[batch['summary'][i,0]];cy=np.asarray(s['cycle'][:]).reshape(-1);q=np.asarray(s['QDischarge'][:]).reshape(-1)
   assert len(cy)==len(q) and np.isfinite(cy).all() and np.all(cy==np.round(cy)) and np.all(np.diff(cy)>0);cy=cy.astype(int)
   valid=np.isfinite(q)&(q>0)&(q<=2.2)&(cy>=1);cross=np.flatnonzero(valid&(q<=.88));event=int(cy[cross[0]]) if len(cross) else None
   stop=event if event is not None else int(cy[valid][-1]);origin=cy[valid&(cy>=100)&((cy<stop) if event is not None else (cy<=stop))]
   policy=f[batch['policy_readable'][i,0]];policy=''.join(chr(int(x)) for x in np.asarray(policy[:]).reshape(-1) if x)
   cid='MATR_b2c'+str(i);meta={'cell_id':cid,'role':roles[i],'source_index':i,'raw_rows':len(q),'valid_rows':int(valid.sum()),'invalid_rows':int((~valid).sum()),'gap_count':int((np.diff(cy[valid])>1).sum()),'event_cycle':event,'censor_cycle':None if event is not None else stop,'censor_reason':'unknown' if event is None else 'not_applicable','prefix_count':len(origin),'policy':policy,'nominal_Ah':1.1,'identity_scope':'source batch/index only; MATLAB string barcode opaque, not physical serial'}
   oldp=R/'reports/matr_schema_audit/run_v2_20261016T031830319822Z/cells'/(cid+'.pkl.cycles.json')
   if oldp.exists():
    oq=np.array([r['capacity_Ah'] for r in json.loads(oldp.read_text())]);n=min(len(oq),len(q)-1);meta['max_capacity_delta_old_shift1']=float(abs(oq[:n]-q[1:1+n]).max());meta['old_summary_sha256']=hashlib.sha256(oldp.read_bytes()).hexdigest()
   summaries[cid]=(cy,q,valid,origin);cells.append(meta)
 DATA.mkdir(exist_ok=False)
 for m in cells:
  cid=m['cell_id'];cy,q,valid,origin=summaries[cid];p=DATA/(cid+'_cycles.csv')
  with p.open('x',newline='') as f:
   w=csv.writer(f);w.writerow(['actual_cycle','capacity_Ah','valid']);w.writerows(zip(cy,q,valid))
  m['cycles_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();rows=[features(cy,q,valid,int(t)) for t in origin];p=DATA/(cid+'_features.csv')
  with p.open('x',newline='') as f:
   w=csv.DictWriter(f,fieldnames=['origin_cycle','visible_through_cycle','soh','rate20_per_cycle','rate20_missing','rate100_per_cycle','rate100_missing']);w.writeheader();w.writerows(rows)
  m['features_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
 manifest={'status':'COMPLETE_RAW_SOURCE_BATCH2_TRAIN_DEVELOPMENT_ASSETS','cells':cells,'source_url':B['source_url'],'source_etag':B['source_etag'],'full_source_sha256':'UNKNOWN_NOT_FULL_FILE','cached_block_receipts':old['blocks'],'new_block_receipts':new,'protocol_sha256':hashlib.sha256((O/'protocol.json').read_bytes()).hexdigest(),'runner_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'split_sha256':hashlib.sha256(SPLIT.read_bytes()).hexdigest(),'new_predictive_fits':0,'optimizer_steps':0,'test_cell_reads':0,'limits':['development exposure inherited; not independent confirmation','batch2 only; no natural-censor benefit claim','source IDs do not prove global physical identity']}
 dump(DATA/'manifest.json',manifest)
 summary={'status':manifest['status'],'cells':len(cells),'counts':{r:{'cells':sum(m['role']==r for m in cells),'prefixes':sum(m['prefix_count'] for m in cells if m['role']==r),'observed_events':sum(m['event_cycle'] is not None for m in cells if m['role']==r)} for r in ['train','val']},'new_network_bytes':used,'new_requests':len(new),'elapsed_seconds':time.monotonic()-start,'two_raw_cycle_checks':'PASS','manifest_sha256':hashlib.sha256((DATA/'manifest.json').read_bytes()).hexdigest(),'maximum_delta_old_capacity_shift1':max(m.get('max_capacity_delta_old_shift1',0) for m in cells),'invalid_rows':sum(m['invalid_rows'] for m in cells),'gaps':sum(m['gap_count'] for m in cells),'new_fits':0,'test_cell_reads':0}
 dump(O/'completion.json',summary);print(json.dumps({'done':True,'result':summary}),flush=True)
except BaseException as e:
 dump(O/'failure.json',{'error':str(e),'type':type(e).__name__,'new_network_bytes':used,'new_requests':new,'elapsed_seconds':time.monotonic()-start});print(json.dumps({'done':True,'error':str(e),'type':type(e).__name__}),flush=True);raise
