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
def metrics(mu,sd,y):
 e=mu-y;v=sd**2
 return np.column_stack([abs(e),e**2,0.5*(e**2/v+np.log(2*np.pi*v)),abs(e)<=1.6448536269514722*sd,e>0.02,e>0.05])
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
     if kind in ['A3','A2','A2_old','A2_v3']:
      if r.get('target_available')!='1' or not r.get('pred_mean_ah'):continue
      prefix={'A3':'A3_','A2':'A2_','A2_old':'Old_A2_','A2_v3':'A2v3_'}[kind]
      name=prefix+r['model_key'];mu=float(r['pred_mean_ah']);sd=float(r['pred_sd_ah']);y=float(r['target_capacity_ah'])
     else:
      model=r['model'];
      if model not in ['hgb','catboost']:continue
      panel=r.get('panel','F0');name=panel+'_'+model
      mu=float(pick(r,['predicted_capacity_ah','pred_capacity_ah','pred_mean_ah','predicted_mean_ah']));sd=float(pick(r,['sigma_oof_ah','sigma_ah','pred_sd_ah','predicted_sigma_ah']));y=float(pick(r,['target_capacity_ah','next_capacity_ah','true_capacity_ah','target_next_capacity_ah']))
     k=key(r);bucket=models.setdefault(name,{})
     assert k not in bucket,('duplicate explicit model key',name,k)
     assert np.isfinite([mu,sd,y]).all() and sd>0
     bucket[k]=(mu,sd,y)
  dump(out/'schema.json',{'headers':headers,'model_row_counts':{k:len(v) for k,v in models.items()}})
  a3=['A3_full','A3_time','A3_noRateUpdate','A3_noEll'];a2=['A2_full','A2_time','A2_noRPTupdate'];v3=['A2v3_full','A2v3_time','A2v3_noRPTupdate']
  required=a3+a2+v3;oldnames=['Old_'+n for n in a2]
  for n in required:assert n in models,('missing required model',n,sorted(models))
  old_in=[n for n in oldnames if n in models]
  trees=sorted(n for n in models if n not in required+oldnames);assert len(trees)==8,('expected F0/F1/F2/F3 x 2 trees',trees)
  common=set.intersection(*(set(models[n]) for n in required+trees+old_in));assert len(common)>0
  results=[];cellrows=[];paired=[];rng=np.random.default_rng(20261025)
  for arm in sorted(set(k[1] for k in common)):
   keys=sorted(k for k in common if k[1]==arm);cells=sorted(set(k[0] for k in keys));cmap={c:i for i,c in enumerate(cells)};ci=np.array([cmap[k[0]] for k in keys]);count=np.bincount(ci,minlength=len(cells));cm={}
   for n in required+trees+old_in:
    ar=np.array([models[n][k] for k in keys]);target=ar[:,2]
    ref=np.array([models[required[0]][k][2] for k in keys]);assert abs(target-ref).max()<1e-7,(n,'target mismatch')
    z=metrics(ar[:,0],ar[:,1],target);v=np.stack([np.bincount(ci,weights=z[:,j],minlength=len(cells))/count for j in range(z.shape[1])],axis=1);cm[n]=v
    results.append({'arm':arm,'model':n,'queries':len(keys),'cells':len(cells),'MAE_Ah':v[:,0].mean(),'RMSE_Ah':np.sqrt(v[:,1].mean()),'NLL_per_Ah':v[:,2].mean(),'coverage90':v[:,3].mean(),'over_20mAh':v[:,4].mean(),'over_50mAh':v[:,5].mean()})
    for c,zv,num in zip(cells,v,count):cellrows.append(dict(arm=arm,model=n,cell_id=c,n=int(num),MAE_Ah=zv[0],MSE_Ah2=zv[1],NLL_per_Ah=zv[2],coverage90=zv[3],over_20mAh=zv[4],over_50mAh=zv[5]))
   bs=rng.integers(0,len(cells),(5000,len(cells)))
   cands=required;refs=trees+old_in+['A2_full','A2_time','A3_full','A3_time']
   for aa in cands:
    for bb in refs:
     if aa==bb:continue
     va,vb=cm[aa],cm[bb]
     for j,metric in enumerate(['MAE_Ah','RMSE_Ah','NLL_per_Ah','coverage90','over_20mAh','over_50mAh']):
      if j==1:p=float(np.sqrt(va[:,j].mean())-np.sqrt(vb[:,j].mean()));dist=np.sqrt(va[bs,j].mean(1))-np.sqrt(vb[bs,j].mean(1))
      else:p=float((va[:,j]-vb[:,j]).mean());dist=(va[:,j]-vb[:,j])[bs].mean(1)
      lo,hi=np.quantile(dist,[.025,.975]);paired.append(dict(arm=arm,candidate=aa,reference=bb,metric=metric,delta=p,ci_low=float(lo),ci_high=float(hi),cells=len(cells),improved_cell_fraction=float((va[:,j]<vb[:,j]).mean())))
  csvout(out/'all_model_metrics.csv',results);csvout(out/'per_cell_metrics.csv',cellrows);csvout(out/'paired_cell_bootstrap.csv',paired)
  summary={'common_query_keys':len(common),'models':sorted(models),'arms':sorted(set(k[1] for k in common)),'metrics':results,'paired_comparisons':len(paired),'elapsed_seconds':time.time()-t}
  dump(out/'summary.json',summary)
  rec.update({'status':'SUCCESS','common_query_keys':len(common),'elapsed_seconds':time.time()-t,'inputs_sha256':{k:a['sha256'] for k,a in g['inputs'].items()}})
 except Exception as exc:
  traceback.print_exc();rec.update({'status':'FAILED','error':repr(exc),'elapsed_seconds':time.time()-t})
 rec_path=g.get('receipt_path') or str(out/'receipt.json');dump(rec_path,rec)
 print(json.dumps({'status':rec['status'],'common_query_keys':rec.get('common_query_keys'),'output':str(out)}))
if __name__=='__main__':run(sys.argv[1])
