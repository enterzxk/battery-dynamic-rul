"""Bounded NASA raw DataV1 pilot; original Capacity and common2.7V endpoint separate."""
from pathlib import Path
import io,json,zipfile,hashlib,csv,datetime
import numpy as np
from scipy.io import loadmat
R=Path('/home/yndx/zxk/rul');O=R/'reports/data_v1_raw_nasa_20261018_root'
P=R/'data/raw/NASA/original_2007/NASA_Battery_Data_Set.zip'
D=R/'data/processed/data_v1_nasa_fy08q4'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,d):
 with p.open('x',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False,indent=2);f.write('\n')
def cutoff_capacity(t,i,v):
 assert len(t)==len(i)==len(v) and len(t)>2
 assert np.isfinite(t).all() and np.isfinite(i).all() and np.isfinite(v).all()
 assert np.all(np.diff(t)>=0)
 active=np.flatnonzero(i<-.1)
 if not len(active) or v[active[0]]<=2.7:return None,{'reason':'no_load_or_begins_below_cutoff'}
 cross=np.flatnonzero((v<=2.7)&(i<-.1))
 if not len(cross):return None,{'reason':'common_cutoff_not_observed'}
 k=int(cross[0]);assert k>0 and v[k-1]>2.7
 a=float((v[k-1]-2.7)/(v[k-1]-v[k]))
 te=float(t[k-1]+a*(t[k]-t[k-1]));ie=float(i[k-1]+a*(i[k]-i[k-1]))
 tt=np.r_[t[:k],te];ii=np.r_[i[:k],ie]
 q=float(np.trapz(np.maximum(-ii,0),tt)/3600)
 if not (0<q<=4):return None,{'reason':'capacity_outside_physical_bound'}
 return q,{'crossing_sample_index':k,'cutoff_elapsed_seconds':te,'interpolation_fraction':a,'integral_interval_count':len(tt)-1}
def parse(raw,cid):
 d=loadmat(io.BytesIO(raw),squeeze_me=True,struct_as_record=False)[cid];ops=np.atleast_1d(d.cycle);rows=[];traces={}
 for opidx,op in enumerate(ops,1):
  if str(op.type)!='discharge':continue
  a=op.data;t=np.asarray(a.Time).reshape(-1);i=np.asarray(a.Current_measured).reshape(-1);v=np.asarray(a.Voltage_measured).reshape(-1)
  original=float(np.asarray(a.Capacity).reshape(-1)[0]);q,detail=cutoff_capacity(t,i,v)
  vdate=np.asarray(op.time).reshape(-1);start=datetime.datetime(*[int(x) for x in vdate[:5]],tzinfo=datetime.timezone.utc)+datetime.timedelta(seconds=float(vdate[5]))
  # Dataset does not state timezone; this string is a source calendar coordinate, not UTC.
  completion=(start+datetime.timedelta(seconds=float(t[-1]))).replace(tzinfo=None).isoformat()
  row={'discharge_ordinal':len(rows)+1,'source_operation_index':opidx,'source_completion_time_naive':completion,
       'Capacity_original_Ah':original,'capacity_to2p7V_Ah':q,'valid_common_cutoff':q is not None,
       'invalid_reason':detail.get('reason',''),'cutoff_elapsed_seconds':detail.get('cutoff_elapsed_seconds'),
       'ambient_temperature_C':float(op.ambient_temperature)}
  rows.append(row)
  if row['discharge_ordinal'] in [1,20]:traces[row['discharge_ordinal']]={'t':t,'i':i,'v':v,'q':q,'detail':detail}
 assert all(rows[j]['source_completion_time_naive']<rows[j+1]['source_completion_time_naive'] for j in range(len(rows)-1))
 return rows,traces,len(ops)
def first_event(rows,key,threshold):
 return next((r['discharge_ordinal'] for r in rows if r[key] is not None and np.isfinite(r[key]) and r[key]<=threshold),None)
def feature(rows,t):
 hist=[r for r in rows if r['discharge_ordinal']<=t]
 cur=hist[-1];assert cur['discharge_ordinal']==t and cur['valid_common_cutoff']
 out={'origin_discharge':t,'visible_through_discharge':t,'source_operation_index':cur['source_operation_index'],
      'source_completion_time_naive':cur['source_completion_time_naive'],'soh_common2p7V':cur['capacity_to2p7V_Ah']/2}
 for width in [20,100]:
  w=[r for r in hist if r['discharge_ordinal']>=t-width+1 and r['valid_common_cutoff']]
  x=np.array([r['discharge_ordinal'] for r in w]);y=np.array([r['capacity_to2p7V_Ah']/2 for r in w])
  enough=len(w)==width and np.all(np.diff(x)==1)
  if enough:
   a,b=np.triu_indices(width,1);rate=float(np.median((y[b]-y[a])/(x[b]-x[a])))
  else:rate=None
  out.update({f'rate{width}_per_discharge':rate,f'rate{width}_missing':not enough,f'rate{width}_count':len(w)})
 return out
def main():
 protocol=json.loads((O/'preprocessing_protocol_v2.json').read_text())
 assert protocol['roles']=={'B0005':'train','B0007':'train','B0006':'val','B0018':'locked_confirmation'}
 assert not D.exists()
 receipt=json.loads(P.with_suffix('.receipt.json').read_text());assert P.stat().st_size==receipt['bytes']==209708670
 inv=json.loads((O/'source_inventory_readme.json').read_text())
 with zipfile.ZipFile(P) as z:inner=z.read(inv['nested_name'])
 assert hashlib.sha256(inner).hexdigest()==inv['nested_sha256']
 with zipfile.ZipFile(io.BytesIO(inner)) as z:
  parsed={};sourcehash={};two=[]
  for cid in ['B0005','B0006']:
   raw=z.read(cid+'.mat');sourcehash[cid]=hashlib.sha256(raw).hexdigest();rows,traces,ops=parse(raw,cid);parsed[cid]=(rows,ops)
   checks=[]
   for n in [1,20]:
    tr=traces[n];k=tr['detail']['crossing_sample_index'];a=tr['detail']['interpolation_fraction'];t=tr['t'];i=tr['i']
    current=np.maximum(-i,0);te=tr['detail']['cutoff_elapsed_seconds']
    # Independent interval sum on the same raw samples; end current interpolated before rectification.
    end=max(-(i[k-1]+a*(i[k]-i[k-1])),0)
    manual=float(sum((current[j]+current[j+1])*(t[j+1]-t[j])/2 for j in range(k-1))+(current[k-1]+end)*(te-t[k-1])/2)/3600
    assert abs(manual-tr['q'])<1e-10
    checks.append({'discharge':n,'reported_Capacity_Ah':rows[n-1]['Capacity_original_Ah'],'common2p7V_Ah':tr['q'],'independent_integral_abs_error':abs(manual-tr['q']),'crossing_sample_index':k})
   assert feature(rows,20)==feature(rows[:20],20)
   assert feature(rows,20)['rate20_missing'] is False and feature(rows,20)['rate100_missing'] is True
   schema=next(a for a in json.loads((O/'two_cell_schema.json').read_text())['two_cell_schema_inspection'] if a['cell_id']==cid)
   assert first_event(rows,'Capacity_original_Ah',1.6)==schema['event80']
   two.append({'cell_id':cid,'MAT_sha256':sourcehash[cid],'independent_checks':checks,'past_only_prefix20_equality':True,
               'original80_event':first_event(rows,'Capacity_original_Ah',1.6),'common2p7V80_event':first_event(rows,'capacity_to2p7V_Ah',1.6)})
  dump(O/'two_cell_check.json',{'status':'PASS_TWO_REAL_CELLS_COMMON_CUTOFF_ENGINEERING','source_sha256':receipt['sha256'],'checks':two,'new_fits':0,'optimizer_steps':0,'test_cell_reads':0,'runner_sha256':sha(Path(__file__)),'protocol_sha256':sha(O/'preprocessing_protocol_v2.json')})
  # One full generation of the frozen 3-cell development population; B0018 MAT never read.
  raw=z.read('B0007.mat');sourcehash['B0007']=hashlib.sha256(raw).hexdigest();rr,_,nn=parse(raw,'B0007');parsed['B0007']=(rr,nn)
 D.mkdir();cells=[]
 for cid in ['B0005','B0007','B0006']:
  rows,ops=parsed[cid];event=first_event(rows,'capacity_to2p7V_Ah',1.6);last=max(r['discharge_ordinal'] for r in rows if r['valid_common_cutoff'])
  eligible=[r['discharge_ordinal'] for r in rows if r['valid_common_cutoff'] and r['discharge_ordinal']>=20 and (event is None or r['discharge_ordinal']<event)]
  fs=[feature(rows,t) for t in eligible];assert fs
  cp=D/(cid+'_canonical.csv');fp=D/(cid+'_prefix_features.csv')
  for p,table in [(cp,rows),(fp,fs)]:
   with p.open('x',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(table[0]));w.writeheader();w.writerows(table)
  cells.append({'cell_id':cid,'role':protocol['roles'][cid],'source_MAT_sha256':sourcehash[cid],
                'identity_scope':'NASA raw filename battery number; physical serial and cross-source aliases unverified',
                'source_operation_count':ops,'discharge_count':len(rows),'prefix_count':len(fs),'common2p7V80_event':event,
                'common2p7V80_censor':None if event is not None else last,
                'reported_Capacity80_event':first_event(rows,'Capacity_original_Ah',1.6),
                'reported_Capacity70_event':first_event(rows,'Capacity_original_Ah',1.4),
                'invalid_common_cutoff_count':sum(not r['valid_common_cutoff'] for r in rows),
                'capacity_rebound_pairs':sum(rows[k+1]['capacity_to2p7V_Ah']>rows[k]['capacity_to2p7V_Ah'] for k in range(len(rows)-1) if rows[k]['valid_common_cutoff'] and rows[k+1]['valid_common_cutoff']),
                'prefix_features_sha256':sha(fp),'canonical_sha256':sha(cp)})
 manifest={'status':'COMPLETE_BOUNDED_NASA_RAW_DATAV1_ENGINEERING','source_archive_sha256':receipt['sha256'],'nested_sha256':inv['nested_sha256'],
           'protocol_sha256':sha(O/'preprocessing_protocol_v2.json'),'runner_sha256':sha(Path(__file__)),'cells':cells,
           'locked_cell':'B0018','locked_MAT_reads':0,'new_predictive_fits':0,'optimizer_steps':0,'test_access':False,
           'feature_columns_for_future_models':['origin_discharge','soh_common2p7V','rate20_per_discharge','rate20_missing','rate100_per_discharge','rate100_missing'],
           'not_features':['source_operation_index','source_completion_time_naive','event/censor','reported_Capacity70/80 endpoints'],
           'limits':['2train1development importer pilot only','no generalization or performance claim','common2.7V discharge integral is project endpoint, not original NASA 1.4Ah reproduction','SOC span and raw physical serial unverified','other NASA packages and MATR raw not processed']}
 dump(D/'manifest.json',manifest)
 summary={**manifest,'manifest_path':str((D/'manifest.json').relative_to(R)),'manifest_sha256':sha(D/'manifest.json'),
          'total_prefixes':sum(c['prefix_count'] for c in cells),'counts':{r:{'cells':sum(c['role']==r for c in cells),'prefixes':sum(c['prefix_count'] for c in cells if c['role']==r)} for r in ['train','val']}}
 dump(O/'data_v1_summary.json',summary);print(json.dumps(summary))
if __name__=='__main__':main()
