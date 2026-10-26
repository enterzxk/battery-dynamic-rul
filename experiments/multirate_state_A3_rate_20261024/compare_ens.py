import pathlib,json,hashlib,csv,math,sys,time,traceback
import numpy as np
ROOT=pathlib.Path('/home/yndx/zxk/rul');HERE=pathlib.Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def dump(p,x):pathlib.Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False))
def pick(r,ks):
 for k in ks:
  if k in r and r[k]!='':return r[k]
 raise ValueError('no key '+str(ks)+' in '+str(list(r)))
def key(r):return (r['cell_id'],r['arm'],round(float(r['query_epoch']),5),round(float(pick(r,['gap_weeks','forecast_h_weeks','next_h_weeks','h_weeks'])),6))
def csvout(path,rows):
 with pathlib.Path(path).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def run(gpath):
 g=json.loads(pathlib.Path(gpath).read_text());assert g['status']=='APPROVED' and g['max_fits']==0
 assert sha(__file__)==g['source_sha256'];out=pathlib.Path(g['output']);assert not out.exists();out.mkdir()
 rec={'status':'STARTED','fits':0,'checkpoint_reads':0,'raw_archive_reads':0,'processed_payload_reads':0,'C4_reads':0,'GO_sha256':sha(gpath)};t=time.time()
 try:
  for a in g['inputs'].values():assert sha(a['path'])==a['sha256']
  models={};headers={}
  for kind,a in g['inputs'].items():
   with open(a['path'],newline='') as f:
    reader=csv.DictReader(f);headers[kind]=reader.fieldnames
    for r in reader:
     if kind in ['S42','S43']:
      if r.get('target_available')!='1' or not r.get('pred_mean_ah'):continue
      if r.get('model_key')!='full':continue
      name=kind+'_full';mu=float(r['pred_mean_ah']);sd=float(r['pred_sd_ah']);y=float(r['target_capacity_ah'])
     elif kind=='TIME':
      if r.get('target_available')!='1' or not r.get('pred_mean_ah'):continue
      if r.get('model_key')!='time':continue
      name='S42_time';mu=float(r['pred_mean_ah']);sd=float(r['pred_sd_ah']);y=float(r['target_capacity_ah'])
     else:
      model=r['model']
      if model not in ['hgb','catboost']:continue
      panel=r.get('panel','F0');name=panel+'_'+model
      mu=float(pick(r,['predicted_capacity_ah','pred_capacity_ah','pred_mean_ah','predicted_mean_ah']));sd=float(pick(r,['sigma_oof_ah','sigma_ah','pred_sd_ah','predicted_sigma_ah']));y=float(pick(r,['target_capacity_ah','next_capacity_ah','true_capacity_ah','target_next_capacity_ah']))
     k=key(r);bucket=models.setdefault(name,{})
     assert k not in bucket,('duplicate key',name,k)
     assert np.isfinite([mu,sd,y]).all() and sd>0
     bucket[k]=(mu,sd,y)
  dump(out/'schema.json',{'headers':headers,'model_row_counts':{k:len(v) for k,v in models.items()}})
  a3names=['S42_full','S43_full'];trees=sorted(n for n in models if n.startswith(('F0_','F1_','F2_','F3_')))
  for n in a3names+trees:assert n in models,('missing',n,sorted(models))
  common=set.intersection(*(set(models[n]) for n in a3names+trees));assert len(common)>0
  # ensemble: equal-weight 2-component Gaussian mixture (moment-matched mu/sd + exact mixture NLL)
  ens={}
  for k in common:
   m1,v1,y=models['S42_full'][k][0],models['S42_full'][k][1]**2,models['S42_full'][k][2]
   m2,v2,_=models['S43_full'][k][0],models['S43_full'][k][1]**2,models['S43_full'][k][2]
   mu=0.5*(m1+m2);var=0.5*(v1+m1*m1+v2+m2*m2)-mu*mu
   sd=math.sqrt(max(var,1e-12))
   # exact 2-component mixture NLL
   def lognc(x,m,s):
    z=(x-m)/s;return -0.5*z*z-math.log(s)-0.5*math.log(2*math.pi)
   nll_mix=-(math.log(0.5*math.exp(lognc(y,m1,math.sqrt(v1)))+0.5*math.exp(lognc(y,m2,math.sqrt(v2)))+1e-300))
   ens[k]=(mu,sd,y,nll_mix)
  results=[];cellrows=[];paired=[];rng=np.random.default_rng(20261101)
  fams={'S42_full':models,'S43_full':models,'S42_time':models,'ENS2_seed':None,'ENS2_moment':None}
  for arm in sorted(set(k[1] for k in common)):
   keys=sorted(k for k in common if k[1]==arm);cells=sorted(set(k[0] for k in keys));cmap={c:i for i,c in enumerate(cells)};ci=np.array([cmap[k[0]] for k in keys]);count=np.bincount(ci,minlength=len(cells));cm={}
   def v0(z,j):
    w=np.bincount(ci,weights=z[:,j],minlength=len(cells))/count
    return float(w.mean())
   def stats(name,vals):
    z=np.array(vals);v=np.stack([np.bincount(ci,weights=z[:,j],minlength=len(cells))/count for j in range(z.shape[1])],axis=1);cm[name]=v;return v
   for n in ['S42_full','S43_full']+trees:
    ar=np.array([models[n][k] for k in keys]);target=ar[:,2]
    ref=np.array([models['S42_full'][k][2] for k in keys]);assert abs(target-ref).max()<1e-7,(n,'target mismatch')
    e=ar[:,0]-target;v=ar[:,1]**2
    z=np.column_stack([np.abs(e),e**2,0.5*(e**2/v+np.log(2*np.pi*v)),np.abs(e)<=1.6448536269514722*ar[:,1],e>0.02,e>0.05])
    stats(n,z)
    results.append({'arm':arm,'model':n,'queries':len(keys),'cells':len(cells),'MAE_Ah':v0(z,0),'RMSE_Ah':math.sqrt(v0(z,1)),'NLL_per_Ah':v0(z,2),'coverage90':v0(z,3),'over_20mAh':v0(z,4),'over_50mAh':v0(z,5)})
   # ENS2 moment-matched (Gaussian approx) and exact-mixture NLL
   em=np.array([[ens[k][0],ens[k][3]] for k in keys]);et=np.array([ens[k][2] for k in keys]);es=np.array([ens[k][1] for k in keys])
   e=em[:,0]-et
   zm=np.column_stack([np.abs(e),e**2,0.5*(e**2/es**2+np.log(2*np.pi*es**2)),np.abs(e)<=1.6448536269514722*es,e>0.02,e>0.05])
   stats('ENS2_moment',zm)
   results.append({'arm':arm,'model':'ENS2_moment','queries':len(keys),'cells':len(cells),'MAE_Ah':v0(zm,0),'RMSE_Ah':math.sqrt(v0(zm,1)),'NLL_per_Ah':v0(zm,2),'coverage90':v0(zm,3),'over_20mAh':v0(zm,4),'over_50mAh':v0(zm,5)})
   zmix=np.column_stack([np.abs(e),e**2,em[:,1],np.abs(e)<=1.6448536269514722*es,e>0.02,e>0.05])
   stats('ENS2_exactmix',zmix)
   results.append({'arm':arm,'model':'ENS2_exactmix','queries':len(keys),'cells':len(cells),'MAE_Ah':v0(zmix,0),'RMSE_Ah':math.sqrt(v0(zmix,1)),'NLL_per_Ah':v0(zmix,2),'coverage90':v0(zmix,3),'over_20mAh':v0(zmix,4),'over_50mAh':v0(zmix,5)})
   for c,zv,num in zip(cells,cm['ENS2_moment'],count):cellrows.append(dict(arm=arm,model='ENS2_moment',cell_id=c,n=int(num),MAE_Ah=zv[0],MSE_Ah2=zv[1],NLL_per_Ah=zv[2],coverage90=zv[3],over_20mAh=zv[4],over_50mAh=zv[5]))
   bs=rng.integers(0,len(cells),(5000,len(cells)))
   cands=['S42_full','S43_full','ENS2_moment','ENS2_exactmix'];refs=trees+['S42_full','S43_full']
   for aa in cands:
    for bb in refs:
     if aa==bb:continue
     va,vb=cm[aa],cm[bb]
     for j,metric in enumerate(['MAE_Ah','RMSE_Ah','NLL_per_Ah','coverage90','over_20mAh','over_50mAh']):
      if j==1:p=float(np.sqrt(va[:,j].mean())-np.sqrt(vb[:,j].mean()));dist=np.sqrt(va[bs,j].mean(1))-np.sqrt(vb[bs,j].mean(1))
      else:p=float((va[:,j]-vb[:,j]).mean());dist=(va[:,j]-vb[:,j])[bs].mean(1)
      lo,hi=np.quantile(dist,[.025,.975]);paired.append(dict(arm=arm,candidate=aa,reference=bb,metric=metric,delta=p,ci_low=float(lo),ci_high=float(hi),cells=len(cells),improved_cell_fraction=float((va[:,j]<vb[:,j]).mean())))
  csvout(out/'all_model_metrics.csv',results);csvout(out/'per_cell_metrics.csv',cellrows);csvout(out/'paired_cell_bootstrap.csv',paired)
  summary={'common_query_keys':len(common),'models':sorted(models)+['ENS2_moment','ENS2_exactmix'],'metrics':results,'elapsed_seconds':time.time()-t}
  dump(out/'summary.json',summary)
  rec.update({'status':'SUCCESS','common_query_keys':len(common),'elapsed_seconds':time.time()-t})
 except Exception as exc:
  traceback.print_exc();rec.update({'status':'FAILED','error':repr(exc)})
 rec_path=g.get('receipt_path') or str(out/'receipt.json');dump(rec_path,rec)
 print(json.dumps({'status':rec['status'],'keys':rec.get('common_query_keys'),'output':str(out)}))

if __name__=='__main__':run(sys.argv[1])
