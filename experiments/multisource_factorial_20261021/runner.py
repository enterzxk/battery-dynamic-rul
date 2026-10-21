#!/usr/bin/env python3
"""GO-gated complete factorial HGB/CatBoost runner. Never reads C4."""
from __future__ import annotations
import argparse, collections, csv, datetime, fcntl, hashlib, json, math, os, pathlib, signal, sys, time, traceback
os.environ.setdefault('OMP_NUM_THREADS','4'); os.environ.setdefault('MKL_NUM_THREADS','4')
import numpy as np
ROOT=pathlib.Path('/home/yndx/zxk/rul'); HERE=ROOT/'experiments/multisource_factorial_20261021'
RPT_DIR=ROOT/'reports/multisource_20261021_signals/all188_rpt_features_v1'
RPT_MAN=RPT_DIR/'manifest.json'; DATA_MAN=ROOT/'reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json'
COHORT=ROOT/'reports/isu_ilcc_capacity_probe_20261020_root/cohort.json'
V18=ROOT/'experiments/dart_rul_v18'; OLD=ROOT/'experiments/isu_irregular_rul_seed42_v1'
SIGNALS=ROOT/'reports/multisource_20261021_signals'
sys.path[:0]=[str(HERE),str(SIGNALS),str(OLD),str(V18)]
import features as factorial
import cycle_asof_features as cycle_asof
from evaluate import PointZero, metric_row, summarize, write_csv
from data_protocol import make_examples
from train_eval import load_split
from hgb_models import HurdleRUL
PANELS=('F0','F1','F2','F3','control_rpt_scalar_only','control_capacity_normalized_shape_only','control_rpt_scalar_plus_shape','control_rpt_scalar_plus_shape_cycle','control_rpt_full_vi_e_time','control_cycle_vi_e_time_only')
MODEL_KINDS=('hgb','catboost')
EXPECTED_DIMS={'F0':74,'F1':686,'F2':98,'F3':710,'control_rpt_scalar_only':86,'control_capacity_normalized_shape_only':674,'control_rpt_scalar_plus_shape':686,'control_rpt_scalar_plus_shape_cycle':710,'control_rpt_full_vi_e_time':704,'control_cycle_vi_e_time_only':92}
FIT_BUDGET=len(PANELS)*len(MODEL_KINDS)*4

def sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def readj(p):return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def writej(p,x):
 with pathlib.Path(p).open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def write_json_progress(p,x):
 tmp=pathlib.Path(str(p)+'.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=True));os.replace(tmp,p)
def source_hashes():
 paths=[HERE/'runner.py',HERE/'protocol.json',HERE/'features.py',SIGNALS/'cycle_asof_features.py',
        V18/'data_protocol.py',V18/'hgb_models.py',V18/'evaluate.py',OLD/'train_eval.py',
        OLD/'baselines.py',OLD/'data_adapter.py',ROOT/'experiments/multisource_information_20261021/runner.py']
 return {str(p.relative_to(ROOT)):sha(p) for p in paths}
def cell_weights(rows):
 c=collections.Counter(e['cell_id'] for e in rows)
 return np.asarray([1.0/c[e['cell_id']] for e in rows],float)
def folds(rows):
 ids=sorted({str(e['cell_id']) for e in rows});np.random.RandomState(42).shuffle(ids)
 out=[set(ids[::2]),set(ids[1::2])]
 if not all(out):raise ValueError('empty cell-isolated fold')
 return out
def new_model(kind,task):
 if kind=='hgb':
  from sklearn.ensemble import HistGradientBoostingClassifier,HistGradientBoostingRegressor
  cls=HistGradientBoostingClassifier if task=='event' else HistGradientBoostingRegressor
  return cls(max_iter=150,max_leaf_nodes=15,l2_regularization=1.0,random_state=42,early_stopping=False)
 from catboost import CatBoostClassifier,CatBoostRegressor
 cls=CatBoostClassifier if task=='event' else CatBoostRegressor
 return cls(iterations=400,depth=5,learning_rate=.04,l2_leaf_reg=3,random_seed=42,thread_count=4,
            verbose=False,allow_writing_files=False,loss_function='Logloss' if task=='event' else 'RMSE')
class CachedCycleIndex:
 def __init__(self,index):self.index=index;self.rows=index.rows;self.memo={}
 def features_at(self,q,subset='full'):
  key=(float(q),subset)
  if key not in self.memo:self.memo[key]=self.index.features_at(q,subset)
  return self.memo[key]
 def visible_records_at(self,q):
  key=('rows',float(q))
  if key not in self.memo:self.memo[key]=self.index.visible_records_at(q)
  return self.memo[key]
def inventory(manifest_path,expected_sha,role_counts):
 if sha(manifest_path)!=expected_sha:raise ValueError('feature manifest hash mismatch: '+str(manifest_path))
 m=readj(manifest_path);items=m.get('inventory')
 if not isinstance(items,list):raise ValueError('manifest inventory absent')
 by={}
 for it in items:
  cid=str(it['cell_id']);role=str(it['role'])
  if cid.endswith('C4') or cid in by or role not in ('train','development'):raise ValueError('invalid/duplicate/locked manifest cell')
  by[cid]=it
 counts=collections.Counter(v['role'] for v in by.values())
 if dict(counts)!=role_counts:raise ValueError('source cell role counts mismatch '+repr(dict(counts)))
 return m,by
def build_matrices(examples,rpt_inventory,cycle_inventory,rec,input_files):
 names=None;meta=[None]*len(examples)
 mats={p:np.full((len(examples),EXPECTED_DIMS[p]),np.nan,dtype=np.float32) for p in PANELS}
 grouped=collections.defaultdict(list)
 for i,e in enumerate(examples):grouped[str(e['cell_id'])].append((i,e))
 for cid,items in sorted(grouped.items()):
  ri=rpt_inventory[cid];ci=cycle_inventory[cid]
  rp=ROOT/ri['path'];cp=ROOT/ci['path']
  if sha(rp)!=ri['sha256'] or sha(cp)!=ci['sha256']:raise ValueError('feature file hash mismatch '+cid)
  rpt=readj(rp);idx=cycle_asof.build_cycle_index(cp);cycle=CachedCycleIndex(idx)
  if rpt.get('cell_id')!=cid or rpt.get('role')!=ri['role'] or idx.cell_id!=cid or idx.role!=ci['role']:
   raise ValueError('source cell identity/role mismatch '+cid)
  rcache={cid:{int(r['source_rpt_index']):r for r in rpt['records']}}
  input_files.extend([{'cell_id':cid,'role':ri['role'],'source':'RPT','path':ri['path'],'sha256':ri['sha256'],'valid_records':len(rpt['records'])},
                      {'cell_id':cid,'role':ci['role'],'source':'Cycling','path':ci['path'],'sha256':ci['sha256'],
                       'source_cycles_total':idx.source_cycle_count,'source_cycles_used':len(idx.rows),
                       'source_cycles_excluded_clock_count':idx.excluded_clock_count,
                       'source_cycles_excluded_clock_indices':idx.excluded_clock_cycle_indices,'units':idx.units}])
  for rowi,e in items:
   vectors=factorial.feature_sets(e,rcache,cycle)
   if names is None:names=factorial.feature_names(e['group_id'])
   for panel in PANELS:
    v=np.asarray(vectors[panel],dtype=np.float32)
    if v.shape!=(EXPECTED_DIMS[panel],):raise ValueError('bad '+panel+' vector shape')
    mats[panel][rowi]=v
   meta[rowi]=factorial.source_end_metadata(e,cycle,rcache)
  del rcache,rpt,idx,cycle
 if any(x is None for x in meta):raise ValueError('row metadata missing')
 return mats,names,meta

def write_jsonl(path,rows):
 with pathlib.Path(path).open('x',encoding='utf-8') as f:
  for r in rows:f.write(json.dumps(r,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
def as_array(v):
 a=np.asarray(v,float)
 if a.ndim!=2 or len(a)==0:raise ValueError('empty feature matrix')
 if np.isinf(a).any():raise ValueError('infinite features')
 return a
def fit_and_score(g,train,dev,train_x,dev_x,train_meta,dev_meta,out,rec):
 targets=np.asarray([int(e['y_event']) for e in train],int)
 positive=[i for i,e in enumerate(train) if e['target_rul_weeks'] is not None and float(e['target_rul_weeks'])>0]
 if not positive:raise ValueError('no positive known RUL rows')
 posrows=[train[i] for i in positive];ypos=np.log([float(e['target_rul_weeks']) for e in posrows]);fold=folds(posrows)
 models={};fitlog=[]
 def fit(model,x,y,w,name):
  rec['CPU_fits_started']+=1
  if rec['CPU_fits_started']>FIT_BUDGET:raise ValueError('fit budget exceeded')
  fitlog.append({'name':name,'status':'started','n_rows':len(y),'n_features':x.shape[1]});write_json_progress(out/'progress.json',rec)
  model.fit(x,y,sample_weight=w)
  rec['CPU_fits_completed']+=1;fitlog[-1]['status']='complete';write_json_progress(out/'progress.json',rec)
  import joblib;joblib.dump(model,out/(name+'.joblib'),compress=3)
  return model
 for kind in MODEL_KINDS:
  for panel in PANELS:
   X=as_array(train_x[panel]);XD=as_array(dev_x[panel]);name=kind+'_'+panel
   clf=fit(new_model(kind,'event'),X,targets,cell_weights(train),name+'_event')
   XP=X[positive];res=[];rrows=[]
   for fi,held in enumerate(fold):
    ixfit=np.asarray([i for i,e in enumerate(posrows) if e['cell_id'] not in held],int)
    ixval=np.asarray([i for i,e in enumerate(posrows) if e['cell_id'] in held],int)
    if not len(ixfit) or not len(ixval):raise ValueError('empty OOF cell split')
    model=fit(new_model(kind,'rul'),XP[ixfit],ypos[ixfit],cell_weights([posrows[i] for i in ixfit]),name+'_oof'+str(fi))
    res.extend((ypos[ixval]-model.predict(XP[ixval])).tolist());rrows.extend([posrows[i] for i in ixval])
   reg=fit(new_model(kind,'rul'),XP,ypos,cell_weights(posrows),name+'_positive')
   rw=cell_weights(rrows);rw/=rw.sum()
   import joblib;joblib.dump({'residuals':np.asarray(res,float),'weights':rw},out/(name+'_distribution.joblib'),compress=3)
   models[name]=(clf,reg,np.asarray(res,float),rw,panel)
 if rec['CPU_fits_completed']!=FIT_BUDGET:raise ValueError('fit count did not equal declared exact budget')
 rec['all_fits_completed_before_dev_inference']=True;write_json_progress(out/'progress.json',rec)
 rows=[];pred_index={}
 for name,(clf,reg,res,rw,panel) in models.items():
  XD=as_array(dev_x[panel]);classes=np.asarray(clf.classes_);where=np.flatnonzero(classes==1)
  if len(where)!=1:raise ValueError('event classifier missing class 1')
  t=time.perf_counter();probs=clf.predict_proba(XD)[:,where[0]];mu=reg.predict(XD);wall=(time.perf_counter()-t)*1000/len(dev)
  for i,e in enumerate(dev):
   raw=HurdleRUL(float(probs[i]),np.exp(float(mu[i])+res),rw)
   dist=PointZero() if e['known_event'] else raw
   row=metric_row(e,dist,42,name,wall);row['unclosed_p_event']=float(probs[i]);row['unclosed_mean_weeks']=raw.mean()
   row['source_indices']=json.dumps([int(x['source_rpt_index']) for x in e['visible_records']],separators=(',',':'))
   rows.append(row);pred_index[name,i]=(float(probs[i]),float(mu[i]),res,rw)
 rec['prediction_rows']=len(rows)
 write_csv(out/'predictions.csv',rows);summary,cellmetrics,reliability=summarize(rows)
 write_csv(out/'arm_summary.csv',summary);write_csv(out/'cell_metrics.csv',cellmetrics);write_csv(out/'reliability_bins.csv',reliability)
 write_csv(out/'factorial_interactions.csv',interaction_rows(cellmetrics))
 pairrows=no_new_rpt_pairs(dev,dev_meta,pred_index,models);write_csv(out/'no_new_rpt_pairs.csv',pairrows);write_csv(out/'no_new_rpt_summary.csv',summarize_no_new_rpt(pairrows))
 return rows,summary,cellmetrics

def paired_panel_deltas(cellmetrics):
 panels=('F0','F1','F2','F3','control_rpt_scalar_only','control_capacity_normalized_shape_only','control_rpt_scalar_plus_shape','control_rpt_scalar_plus_shape_cycle','control_rpt_full_vi_e_time','control_cycle_vi_e_time_only')
 pairs=(('F1_minus_F0','F1','F0'),('F2_minus_F0','F2','F0'),('F3_minus_F1','F3','F1'),('F3_minus_F2','F3','F2'),
        ('scalar_only_minus_F0','control_rpt_scalar_only','F0'),('shape_only_minus_F0','control_capacity_normalized_shape_only','F0'),
        ('scalar_plus_shape_minus_F1','control_rpt_scalar_plus_shape','F1'),('scalar_plus_shape_cycle_minus_F3','control_rpt_scalar_plus_shape_cycle','F3'),
        ('fullRPT_VI_E_time_minus_F1','control_rpt_full_vi_e_time','F1'),('VI_E_time_only_minus_F0','control_cycle_vi_e_time_only','F0'))
 metrics=('event_brier','event_logloss','mean_abs_error','median_abs_error','severe_gt4w','IS80','coverage80','Brier4','Brier12','bin_logscore')
 ix={(r['seed'],r['model'].split('_',1)[0],r['model'].split('_',1)[1],r['arm'],r['stratum'],r['cell_id']):r for r in cellmetrics}
 out=[];rng=np.random.RandomState(42)
 for modeltype in sorted({r['model'].split('_',1)[0] for r in cellmetrics}):
  cells=sorted({r['cell_id'] for r in cellmetrics if r['model'].startswith(modeltype+'_')})
  arms=sorted({r['arm'] for r in cellmetrics if r['model'].startswith(modeltype+'_')})
  strata=sorted({r['stratum'] for r in cellmetrics if r['model'].startswith(modeltype+'_')})
  for arm in arms:
   for st in strata:
    for label,p1,p0 in pairs:
     for metric in metrics:
      diffs=[]
      for cid in cells:
       try:
        a=float(ix[(42,modeltype,p1,arm,st,cid)][metric]);b=float(ix[(42,modeltype,p0,arm,st,cid)][metric])
        if math.isfinite(a) and math.isfinite(b):diffs.append(a-b)
       except (KeyError,TypeError,ValueError):pass
      if diffs:
       v=np.asarray(diffs,float);boot=np.mean(rng.choice(v,(2000,len(v)),replace=True),axis=1)
       out.append({'model':modeltype,'arm':arm,'stratum':st,'contrast':label,'n_cells':len(v),'metric':metric,'paired_cell_mean_delta':float(v.mean()),'bootstrap95_low':float(np.quantile(boot,.025)),'bootstrap95_high':float(np.quantile(boot,.975)),'lower_is_better':metric not in ('coverage80',)})
 return out

def interaction_rows(cellmetrics):
 by={(r['seed'],r['model'].split('_',1)[0],r['model'].split('_',1)[1],r['arm'],r['stratum'],r['cell_id']):r for r in cellmetrics}
 out=[];metrics=('event_brier','event_logloss','mean_abs_error','median_abs_error','severe_gt4w','IS80','coverage80','Brier4','Brier12','bin_logscore')
 modeltypes=sorted({r['model'].split('_',1)[0] for r in cellmetrics})
 for mt in modeltypes:
  cells=sorted({r['cell_id'] for r in cellmetrics if r['model'].startswith(mt+'_')})
  arms=sorted({r['arm'] for r in cellmetrics if r['model'].startswith(mt+'_')})
  strata=sorted({r['stratum'] for r in cellmetrics if r['model'].startswith(mt+'_')})
  for arm in arms:
   for st in strata:
    for metric in metrics:
     vals=[]
     for cid in cells:
      try:
       f0=float(by[(42,mt,'F0',arm,st,cid)][metric]);f1=float(by[(42,mt,'F1',arm,st,cid)][metric]);f2=float(by[(42,mt,'F2',arm,st,cid)][metric]);f3=float(by[(42,mt,'F3',arm,st,cid)][metric])
       if all(map(math.isfinite,(f0,f1,f2,f3))):vals.append((cid,(f3-f1)-(f2-f0)))
      except (KeyError,ValueError,TypeError):pass
     if vals:
      arr=np.asarray([v for _,v in vals],float);rng=np.random.RandomState(42);boot=np.mean(rng.choice(arr,(2000,len(arr)),replace=True),axis=1)
      out.append({'model':mt,'arm':arm,'stratum':st,'metric':metric,'n_cells':len(arr),'difference_in_differences_F3_F1_minus_F2_F0':float(arr.mean()),'bootstrap95_low':float(np.quantile(boot,.025)),'bootstrap95_high':float(np.quantile(boot,.975))})
 return out

def summarize_no_new_rpt(rows):
 groups=collections.defaultdict(list)
 for r in rows:groups[(r['model'],r['factor_pair'],r['cell_id'])].append(r)
 cells=collections.defaultdict(list)
 for (model,pair,cid),rs in groups.items():
  for metric in ('mean_abs_error','event_brier'):
   vals=[]
   for r in rs:
    a=r['source_updated_'+metric];b=r['time_shifted_'+metric]
    if a!='' and b!='' and math.isfinite(float(a)) and math.isfinite(float(b)):vals.append(float(a)-float(b))
   if vals:cells[model,pair,metric].append((cid,float(np.mean(vals)),len(vals)))
 out=[];rng=np.random.RandomState(42)
 for (model,pair,metric),vals in sorted(cells.items()):
  a=np.asarray([v for _,v,_ in vals],float);boot=np.mean(rng.choice(a,(2000,len(a)),replace=True),axis=1)
  out.append({'model':model,'factor_pair':pair,'outcome_metric':metric,'n_cells':len(a),'n_pairs':sum(n for _,_,n in vals),'mean_cell_paired_delta_source_minus_time_shift':float(a.mean()),'bootstrap95_low':float(np.quantile(boot,.025)),'bootstrap95_high':float(np.quantile(boot,.975)),'negative_favors_source_update':True})
 return out

def shift_distribution(dist,gap):
 p=float(dist.zero_mass);values=np.asarray(dist.positive.values,float);weights=np.asarray(dist.positive.weights,float)
 shifted=np.maximum(0.,values-float(gap));positive=shifted>0
 pnew=p+(1.-p)*float(weights[~positive].sum())
 if pnew>=1. or not positive.any():return PointZero()
 w=weights[positive];w=w/w.sum()
 return HurdleRUL(pnew,shifted[positive],w)

def no_new_rpt_pairs(dev,meta,pred_index,models):
 groups=collections.defaultdict(list)
 for i,e in enumerate(dev):groups[(e['cell_id'],e['arm'],e['history_key'])].append((i,e))
 out=[];tau=np.asarray([0.,1.,4.,12.,32.])
 pair_panels=(('F0','F2'),('F1','F3'))
 for key,seq in sorted(groups.items()):
  seq=sorted(seq,key=lambda x:x[1]['query_epoch'])
  for (ia,a),(ib,b) in zip(seq,seq[1:]):
   if a['known_event'] or b['known_event']:continue
   cycle_a=meta[ia]['cycle_source_asof_count'];cycle_b=meta[ib]['cycle_source_asof_count']
   if cycle_a==cycle_b:continue
   gap=(float(b['query_epoch'])-float(a['query_epoch']))/604800.
   if gap<=0:continue
   for mt in MODEL_KINDS:
    for basepanel,sourcepanel in pair_panels:
     na=mt+'_'+basepanel;nb=mt+'_'+sourcepanel
     pa,mua,resa,rwa=pred_index[na,ia];pb,_,resb,rwb=pred_index[na,ib]
     _,_,_,_=pred_index[nb,ia]
     psrc,musrc,ressrc,rwsrc=pred_index[nb,ib]
     da=HurdleRUL(pa,np.exp(mua+resa),rwa)
     dtime=shift_distribution(da,gap)
     dbase_b=HurdleRUL(pb,np.exp(pred_index[na,ib][1]+resb),rwb)
     dsource_b=HurdleRUL(psrc,np.exp(musrc+ressrc),rwsrc)
     target=b['target_rul_weeks'];target_known=target is not None
     time_row=metric_row(b,dtime,42,'time_shifted_'+basepanel,0.)
     base_row=metric_row(b,dbase_b,42,'recomputed_'+basepanel,0.)
     source_row=metric_row(b,dsource_b,42,'source_updated_'+sourcepanel,0.)
     shifted_cdf=np.asarray(dtime.cdf(tau),float);source_cdf=np.asarray(dsource_b.cdf(tau),float)
     out.append({'cell_id':key[0],'role':b['role'],'arm':key[1],'history_key':key[2],
       'query_a':float(a['query_epoch']),'query_b':float(b['query_epoch']),'gap_weeks':gap,
       'visible_rpt_source_indices':json.dumps([int(x['source_rpt_index']) for x in b['visible_records']],separators=(',',':')),
       'cycle_count_a':cycle_a,'cycle_count_b':cycle_b,
       'cycle_source_index_a':meta[ia]['cycle_latest_source_index'],'cycle_source_index_b':meta[ib]['cycle_latest_source_index'],
       'model':mt,'factor_pair':basepanel+'_time_only_to_'+sourcepanel+'_updated',
       'target_rul_weeks_at_b':'' if not target_known else float(target),'y_event_at_b':int(b['y_event']),
       'time_shifted_event_probability':float(dtime.cdf(0.)),'source_updated_event_probability':float(dsource_b.cdf(0.)),
       'time_shifted_event_brier':time_row['event_brier'],'source_updated_event_brier':source_row['event_brier'],
       'time_shifted_mean_abs_error':time_row['mean_abs_error'],'source_updated_mean_abs_error':source_row['mean_abs_error'],
       'recomputed_base_mean_abs_error':base_row['mean_abs_error'],
       'time_shifted_mean_weeks':dtime.mean(),'recomputed_base_mean_weeks':dbase_b.mean(),'source_updated_mean_weeks':dsource_b.mean(),
       'time_shifted_cdf_transport_vs_source_update':float(np.max(np.abs(shifted_cdf-source_cdf))),
       'source_arrival':'cycle arrival unobserved; assumed available at completion'})
 return out

def run(go_path):
 go_path=pathlib.Path(go_path);g=readj(go_path);D=HERE
 rec={'status':'PREFLIGHT','request_id':g.get('request_id'),'CPU_fits_started':0,'CPU_fits_completed':0,'fit_budget_required':FIT_BUDGET,'C4_payload_reads':0,'old_model_loads':0,'prediction_rows':0,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 locks=[];out=None;start=time.time();receipt=D/(str(g.get('request_id'))+'_receipt.json')
 try:
  if g.get('status')!='APPROVED' or g.get('allow_fit') is not True or g.get('fit_budget')!=FIT_BUDGET:raise ValueError('GO approval or exact fit budget mismatch')
  coord=readj(ROOT/'automation/state/coordinator.json')
  if g.get('owner_thread_id')!=coord.get('owner') or coord.get('thread_id')!=g.get('owner_thread_id'):raise ValueError('owner mismatch')
  if coord.get('state')!='ACTIVE' or coord.get('actual_cwd')!='/home/yndx/zxk/rul' or coord.get('takeover_verified') is not True:raise ValueError('coordinator ownership/cwd verification failed')
  hb=datetime.datetime.fromisoformat(coord['heartbeat_utc'].replace('Z','+00:00'))
  if (datetime.datetime.now(datetime.timezone.utc)-hb).total_seconds()>1800:raise ValueError('coordinator heartbeat stale')
  issued=datetime.datetime.fromisoformat(g['issued_utc'].replace('Z','+00:00'))
  if (datetime.datetime.now(datetime.timezone.utc)-issued).total_seconds()>86400:raise ValueError('stale GO')
  if g.get('source_sha256')!=source_hashes():raise ValueError('source SHA mismatch')
  if sha(DATA_MAN)!=g.get('manifest_sha256') or sha(COHORT)!=g.get('cohort_sha256'):raise ValueError('frozen cohort/source manifest SHA mismatch')
  _,rptinv=inventory(RPT_MAN,g.get('rpt_feature_manifest_sha256'),{'train':125,'development':63})
  cyclepath=ROOT/g['cycling_feature_manifest'];_,cycinv=inventory(cyclepath,g.get('cycling_feature_manifest_sha256'),{'train':125,'development':63})
  if set(rptinv)!=set(cycinv):raise ValueError('RPT/Cycling cell inventories differ')
  for lp in ('automation/state/online_survival_cpu.lock','automation/locks/isu_irregular_rul_cpu.lock'):
   f=(ROOT/lp).open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  claim=D/(g['request_id']+'.claim.json');writej(claim,{'GO_sha256':sha(go_path),'claimed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
  out=(ROOT/g['output']).resolve()
  if HERE.resolve() not in out.parents:raise ValueError('output path must stay within formal factorial directory')
  out.mkdir(parents=False,exist_ok=False)
  signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('GO runtime budget')));signal.alarm(int(g['max_runtime_seconds']))
  cells=load_split(COHORT,ROOT/'data/processed/ISU_ILCC_DataV2_v1',DATA_MAN)
  roles=collections.Counter(c['role'] for c in cells);ids={c['cell_id'] for c in cells}
  if roles!={'train':125,'development':63} or len(ids)!=188 or any(cid.endswith('C4') for cid in ids):raise ValueError('locked cohort source count/role mismatch')
  if ids!=set(rptinv) or ids!=set(cycinv):raise ValueError('feature cells do not exactly match cohort')
  for cid in ids:
   if cid[-2:] not in ('C1','C2','C3'):raise ValueError('unexpected cell condition')
  tr=make_examples([c for c in cells if c['role']=='train']);dv=make_examples([c for c in cells if c['role']=='development'])
  if len(tr)!=int(g['expected_train_queries']) or len(dv)!=int(g['expected_development_queries']):raise ValueError('query count differs from GO')
  train_qcells=sorted({e['cell_id'] for e in tr});dev_qcells=sorted({e['cell_id'] for e in dv})
  if len(train_qcells)!=int(g['expected_train_query_cells']) or len(dev_qcells)!=int(g['expected_development_query_cells']):raise ValueError('eligible query-cell count differs from GO')
  input_files=[]
  # Source-time visibility is checked for every selected RPT record; cycle payloads stream one cell at a time.
  xt,nt,mt=build_matrices(tr,rptinv,cycinv,rec,input_files)
  xd,nd,md=build_matrices(dv,rptinv,cycinv,rec,input_files)
  if nt!=nd or {p:x.shape[1] for p,x in xt.items()}!=EXPECTED_DIMS or {p:x.shape[1] for p,x in xd.items()}!=EXPECTED_DIMS:raise ValueError('formal feature dimensions mismatch')
  arms=('raw','sparse2','delay7d')
  rec['data']={'train_queries':len(tr),'development_queries':len(dv),'train_source_cells':125,'development_source_cells':63,'train_query_cells':len(train_qcells),'development_query_cells':len(dev_qcells),'train_query_cell_ids':train_qcells,'development_query_cell_ids':dev_qcells,'query_rows_by_arm':{a:{'train':sum(e['arm']==a for e in tr),'development':sum(e['arm']==a for e in dv)} for a in arms},'known_target_rows_by_arm':{a:{'train':sum(e['arm']==a and e["target_rul_weeks"] is not None for e in tr),'development':sum(e['arm']==a and e["target_rul_weeks"] is not None for e in dv)} for a in arms},'rpt_visible_record_rows_by_arm':{a:{'train':sum(e['arm']==a for e in tr for _r in e['visible_records']),'development':sum(e['arm']==a for e in dv for _r in e['visible_records'])} for a in arms},'arms':list(arms)}
  # Store numeric feature caches and source-linked per-row metadata before any fits.
  for split,mat in (('train',xt),('development',xd)):
   with (out/(split+'_features.npz')).open('xb') as f:np.savez_compressed(f,**mat)
  write_jsonl(out/'train_rows.jsonl',mt);write_jsonl(out/'development_rows.jsonl',md)
  write_jsonl(out/'train_targets.jsonl',[{'cell_id':e['cell_id'],'arm':e['arm'],'query_epoch':e['query_epoch'],'known_event':e['known_event'],'y_event':e['y_event'],'target_rul_weeks':e['target_rul_weeks']} for e in tr])
  write_jsonl(out/'development_targets.jsonl',[{'cell_id':e['cell_id'],'arm':e['arm'],'query_epoch':e['query_epoch'],'known_event':e['known_event'],'y_event':e['y_event'],'target_rul_weeks':e['target_rul_weeks']} for e in dv])
  cell_meta=[]
  for cid in sorted(ids):
   role=next(c['role'] for c in cells if c['cell_id']==cid)
   src=[x for x in input_files if x['cell_id']==cid]
   cell_meta.append({'cell_id':cid,'role':role,'queries':sum(e['cell_id']==cid for e in tr+dv),'sources':src})
  writej(out/'cell_metadata.json',cell_meta)
  writej(out/'feature_schema.json',{'panels':list(PANELS),'dimensions':EXPECTED_DIMS,'feature_names':nt,'input_files':input_files,'source_manifest_sha256':g['manifest_sha256'],'cohort_sha256':g['cohort_sha256'],'rpt_manifest_sha256':g['rpt_feature_manifest_sha256'],'cycling_manifest_sha256':g['cycling_feature_manifest_sha256'],'cycle_source_arrival':'unobserved; assumed available at source completion','RPT_arrival':'protocol arm arrival; RPT source stop <= arrival <= query'})
  def coverage(rows,meta):
   visible={(e['cell_id'],int(r['source_rpt_index'])) for e in rows for r in e['visible_records']}
   cycle_rows=sum(int(m['cycle_source_asof_count'])>0 for m in meta)
   return {'rows':len(rows),'eligible_cells':len({e['cell_id'] for e in rows}),'visible_rpt_source_cell_records':len(visible),'cycle_visible_rows':cycle_rows,'cycle_visible_fraction':cycle_rows/len(rows) if rows else 0.0,'max_visible_cycles_per_row':max([int(m['cycle_source_asof_count']) for m in meta] or [0])}
  rec['source_coverage']={'train':coverage(tr,mt),'development':coverage(dv,md),'feature_cache_cells':len(input_files)//2,'rpt_valid_records_total':sum(x['valid_records'] for x in input_files if x['source']=='RPT'),'cycling_source_cycles_total':sum(x['source_cycles_total'] for x in input_files if x['source']=='Cycling'),
   'cycling_source_cycles_used':sum(x['source_cycles_used'] for x in input_files if x['source']=='Cycling'),
   'cycling_source_cycles_excluded_clock_count':sum(x['source_cycles_excluded_clock_count'] for x in input_files if x['source']=='Cycling')}
  rec['dimensions']=EXPECTED_DIMS;rec['train_nonfinite_fraction']={k:float(np.isnan(v).mean()) for k,v in xt.items()};rec['development_nonfinite_fraction']={k:float(np.isnan(v).mean()) for k,v in xd.items()};rec['features_cached_before_fit']=True
  rows,summary,cellscores=fit_and_score(g,tr,dv,xt,xd,mt,md,out,rec)
  rec['status']='SUCCESS';rec['output']=str(out)
 except BaseException as ex:
  rec.update(status='FAILED',error=repr(ex),traceback=traceback.format_exc())
 finally:
  signal.alarm(0);rec['elapsed_seconds']=time.time()-start;rec['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
  writej(receipt,rec)
  for f in locks:f.close()
 print(json.dumps(rec,ensure_ascii=False,indent=2));return rec
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--go',required=True);a=ap.parse_args();r=run(a.go);sys.exit(0 if r['status']=='SUCCESS' else 2)
