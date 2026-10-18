from pathlib import Path
import os,json,csv,hashlib,time
import numpy as np
R=Path('/home/yndx/zxk/rul');O=R/'reports/local_state_support_20261018_root'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,x):
 with (O/n).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
start=time.monotonic();p=json.loads((O/'protocol.json').read_text());cp=R/p['cohort'];sp=R/p['source_prediction'];assert sha(cp)==p['cohort_sha256'] and sha(sp)==p['prediction_sha256'];co=json.loads(cp.read_text());fit={};cal={};sourcehash={}
for dm in co['manifests']:
 mp=Path(dm['path']);assert sha(mp)==dm['sha256']
 for c in json.loads(mp.read_text())['cells']:
  cid=c['cell_id'];role=co['roles'][cid]
  if role!='fit' and cid not in p['cases']:continue
  assert c['role']=='train' and (role=='fit' or role=='calibration');fp=mp.parent/(cid+'_features.csv');assert sha(fp)==c['features_sha256'];sourcehash[str(fp)]=c['features_sha256'];rr=list(csv.DictReader(fp.open()));assert len(rr)==c['prefix_count']
  x=[];y=[];orig=[]
  for r in rr:
   t=int(r['origin_cycle']);assert int(r['visible_through_cycle'])==t<c['event_cycle'] and r['rate20_missing']=='False';x.append([t,float(r['soh']),float(r['rate20_per_cycle'])]);y.append(c['event_cycle']-t);orig.append(t)
  a=dict(X=np.array(x),Y=np.array(y),origin=np.array(orig));assert np.isfinite(a['X']).all()
  if role=='fit':fit[cid]=a
  else:cal[cid]=a
assert len(fit)==42 and set(cal)==set(p['cases']);F=np.concatenate([fit[c]['X'] for c in sorted(fit)]);assert len(F)==22281;med=np.median(F,axis=0);iqr=np.quantile(F,.75,axis=0)-np.quantile(F,.25,axis=0);assert (iqr>0).all();low=F.min(axis=0);high=F.max(axis=0);out=[];examples=[];records=[]
for cid in p['cases']:
 C=cal[cid];X=C['X'];T=C['Y'];all_d=[];all_y=[];all_o=[];sids=sorted(fit)
 for sid in sids:
  f=fit[sid];delta=(X[:,None,:]-f['X'][None,:,:])/iqr;dist=np.einsum('nmi,nmi->nm',delta,delta);j=dist.argmin(axis=1);all_d.append(np.sqrt(dist[np.arange(len(X)),j]));all_y.append(f['Y'][j]);all_o.append(f['origin'][j])
 D=np.array(all_d).T;Y=np.array(all_y).T;P=np.array(all_o).T;ix=np.argsort(D,axis=1,kind='stable')[:,:5];nearD=np.take_along_axis(D,ix,axis=1);nearY=np.take_along_axis(Y,ix,axis=1);minY=nearY.min(axis=1);maxY=nearY.max(axis=1);span=maxY-minY;gap=T-nearY[:,0];outside=(X<low)|(X>high);close=nearD[:,0]<=.1;outsideY=(T<minY)|(T>maxY)
 summary=dict(cell_id=cid,origins=len(X),outside_axisbox_origins=int(outside.any(axis=1).sum()),outside_axisbox_by_feature=dict(zip(p['features'],map(int,outside.sum(axis=0)))),nearest_IQR_L2_quantiles=dict(zip(['min','q25','median','q75','max'],map(float,np.quantile(nearD[:,0],[0,.25,.5,.75,1])))),near_reference_origins=int(close.sum()),truth_outside5label_range_origins=int(outsideY.sum()),truth_outside5label_range_fraction=float(outsideY.mean()),near_reference_truth_outside5range=int((close&outsideY).sum()),fivecell_labelspan_cycles_quantiles=list(map(float,np.quantile(span,[0,.5,1]))),truth_minus_nearest_train_label_quantiles=list(map(float,np.quantile(gap,[0,.5,1]))));out.append(summary)
 for i,t in enumerate(C['origin']):records.append(dict(cell_id=cid,origin=int(t),true_RUL=int(T[i]),nearest_IQR_L2=float(nearD[i,0]),nearest_training_cell=sids[ix[i,0]],nearest_training_origin=int(P[i,ix[i,0]]),nearest_training_RUL=int(nearY[i,0]),fivecell_min_RUL=int(minY[i]),fivecell_max_RUL=int(maxY[i]),outside_axisbox=bool(outside[i].any())))
 for i in [0,len(X)//2,len(X)-1]:examples.append(dict(cell_id=cid,origin=int(C['origin'][i]),visible_state=X[i].tolist(),true_RUL=int(T[i]),neighbors=[dict(training_cell=sids[j],training_origin=int(P[i,j]),IQR_L2=float(D[i,j]),training_state=fit[sids[j]]['X'][np.where(fit[sids[j]]['origin']==P[i,j])[0][0]].tolist(),training_RUL=int(Y[i,j])) for j in ix[i]]))
dump('summary.json',dict(fit_prefixes=len(F),fit_cells=42,fit_only_median=med.tolist(),fit_only_IQR=iqr.tolist(),fit_axis_min=low.tolist(),fit_axis_max=high.tolist(),cases=out));dump('examples.json',examples);dump('source_hashes.json',sourcehash)
with (O/'origin_label_support.csv').open('x',newline='') as f:w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
dump('completion.json',dict(status='COMPLETE_LOCAL_STATE_LABEL_SUPPORT_DIAGNOSTIC',new_fits=0,optimizer_steps=0,new_model_inference=0,normalization_statistics='fit-only descriptive median/IQR, not predictivefit',checkpoint_loads=0,dev_test_reads=0,feature_files_read=len(sourcehash),fit_origins=len(F),cal_origins=len(records),protocol_sha256=sha(O/'protocol.json'),script_sha256=sha(Path(__file__)),origin_audit_sha256=sha(O/'origin_label_support.csv'),elapsed_seconds=time.monotonic()-start));print(json.dumps(out))
