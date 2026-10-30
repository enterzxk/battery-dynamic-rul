#!/usr/bin/env python3
"""Frozen group-isolated, hypothetical-label-asof direct four-week risk pilot."""
import os
os.environ['OMP_NUM_THREADS']='4';os.environ['MKL_NUM_THREADS']='4'
import pathlib,sys,json,csv,hashlib,datetime,time,collections,fcntl,traceback,argparse,warnings
import numpy as np
R=pathlib.Path('/home/yndx/zxk/rul');H=R/'experiments/rulaas_temporal_risk_20261029';AUD=H/'audit02';FORMAL=R/'experiments/multisource_factorial_20261021/run2_clocksafe';OWNER='01a17810-6ae6-7cf2-9729-5bfcaa8df5f4';DAY=86400.;WEEK=604800.
sys.path.insert(0,str(R/'experiments/isu_irregular_rul_seed42_v1'));from data_adapter import load_reviewed_cell
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def readj(p):return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def writej(p,x):
 with pathlib.Path(p).open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def csvout(p,rows):
 if not rows:raise ValueError('empty artifact '+str(p))
 with pathlib.Path(p).open('x',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def prog(p,x):
 t=p/'progress.tmp';t.write_text(json.dumps(x,ensure_ascii=False),encoding='utf-8');os.replace(t,p/'progress.json')
def group(cid):return cid.rsplit('C',1)[0]
def weights_for(cids):
 c=collections.Counter(cids);w=np.asarray([1./c[x] for x in cids],float);return w*len(w)/w.sum()
def main(gpath):
 g=readj(gpath);out=R/g['output'];t0=time.time();locks=[]
 rec=dict(status='STARTED',request_id=g['request_id'],started_utc=stamp(),predictive_fits_started=0,predictive_fits_completed=0,preprocessor_components_fitted=0,model_prediction_rows=0,C1C2_source_cells_read=0,C3_payload_reads=0,C4_payload_reads=0,actual_coordinator_model_recorded=g['actual_model'])
 try:
  for p in [R/'automation/state/coordinator.lock',R/'automation/locks/isu_irregular_rul_cpu.lock']:
   f=p.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  c=readj(R/'automation/state/coordinator.json');hb=datetime.datetime.fromisoformat(c['heartbeat_utc'].replace('Z','+00:00'))
  if c.get('state')!='ACTIVE' or c.get('owner')!=OWNER or c.get('thread_id')!=OWNER or (datetime.datetime.now(datetime.timezone.utc)-hb).total_seconds()>1800:raise ValueError('owner or heartbeat')
  if g.get('status')!='APPROVED' or g.get('owner')!=OWNER or g.get('allow_fits') is not True or g.get('allow_C3') is not False or g.get('allow_C4') is not False:raise ValueError('GO')
  if g['fit_cap']!=15 or g['preprocessor_cap']!=8 or g['model_row_cap']!=6500 or g['source_cell_cap']!=32 or g['seed']!=42:raise ValueError('budget')
  for name,h in g['input_sha256'].items():
   if sha(R/name)!=h:raise ValueError('input hash '+name)
  if out.parent!=H or out.exists():raise ValueError('create-only output')
  writej(H/(g['request_id']+'.claim.json'),dict(GO_sha256=sha(gpath),utc=stamp()));out.mkdir();prog(out,rec)
  audit=readj(AUD/'AUDIT.json');split=readj(AUD/'split.json');auditrec=readj(AUD/'receipt.json')
  if audit['status']!='PASS_GROUP_AND_HYPOTHETICAL_ASOF_SUPPORT' or audit['C3_payload_reads'] or audit['C4_payload_reads']:raise ValueError('input audit')
  train=set(split['outer_train_groups']);held=set(split['outer_held_groups']);mature=set(split['mature_train_groups']);folds=[set(x) for x in split['oof_folds']];cut=float(split['selected']['cutoff_epoch'])
  if len(train)!=47 or len(held)!=16 or train&held or len(mature)!=15 or not mature<=train or len(folds)!=3 or any(len(x)!=5 for x in folds) or set.union(*folds)!=mature or any(folds[i]&folds[j] for i in range(3) for j in range(i)):raise ValueError('group split')
  if abs(cut-1649324336.2)>1e-6:raise ValueError('cutoff drift')
  # Do not retain or use held outcomes in fits; the separate support audit
  # previously checked labels, so this retrospective evaluation is not blind.
  visible=[];train_targets={}
  with (FORMAL/'train_targets.jsonl').open(encoding='utf-8') as f:
   for i,line in enumerate(f):
    z=json.loads(line);cid=z['cell_id'];visible.append(dict(cell_id=cid,arm=z['arm'],query_epoch=float(z['query_epoch']),known_event=bool(z['known_event'])))
    if group(cid) in mature:train_targets[i]=z['target_rul_weeks']
  sources={z['cell_id']:z for z in auditrec['source_files']};events={}
  for cid in sorted({z['cell_id'] for z in visible if group(z['cell_id']) in mature}):
   z=sources[cid];p=R/z['path']
   if not cid.endswith(('C1','C2')) or 'C3' in p.name or 'C4' in p.name or sha(p)!=z['sha256']:raise ValueError('training source')
   cell=load_reviewed_cell(p,'train');rows=sorted(cell['records'],key=lambda x:float(x['stop_epoch']));events[cid]=next((float(x['stop_epoch']) for x in rows if float(x['capacityAh'])<=.20),None);rec['C1C2_source_cells_read']+=1
   if rec['C1C2_source_cells_read']>g['source_cell_cap']:raise ValueError('source cell cap')
  ti=[];vi=[]
  for i,z in enumerate(visible):
   cid=z['cell_id'];gr=group(cid);q=z['query_epoch']
   if gr in mature and q<=cut and events[cid] is not None and events[cid]+14*DAY<=cut and not z['known_event']:
    y=train_targets.get(i)
    if y is None:raise ValueError('mature training label missing')
    if abs(float(y)-max(0.,(events[cid]-q)/WEEK))>1e-9:raise ValueError('training event identity')
    ti.append(i)
   if gr in held and q>=cut and not z['known_event']:vi.append(i)
  if len(ti)!=940 or len(vi)!=536 or len({visible[i]['cell_id'] for i in ti})!=27 or len({group(visible[i]['cell_id']) for i in vi})!=10:raise ValueError('audited population drift')
  ti=np.asarray(ti,int);vi=np.asarray(vi,int);cids=np.asarray([visible[i]['cell_id'] for i in ti]);grids=np.asarray([group(x) for x in cids]);y=np.asarray([float(train_targets[int(i)])<=4. for i in ti],int);weights=weights_for(cids)
  if int(y.sum())!=256 or len(y)-int(y.sum())!=684:raise ValueError('training class drift')
  A=np.load(FORMAL/'train_features.npz',allow_pickle=False);X0=A['F0'];X3=A['F3']
  if X0.shape!=(6870,74) or X3.shape!=(6870,710) or np.isinf(X3).any():raise ValueError('features')
  from sklearn.ensemble import HistGradientBoostingClassifier
  from sklearn.linear_model import LogisticRegression
  from sklearn.pipeline import Pipeline
  from sklearn.impute import SimpleImputer
  from sklearn.preprocessing import StandardScaler
  from sklearn.exceptions import ConvergenceWarning
  from scipy.special import expit
  import sklearn,joblib
  def new_hgb():return HistGradientBoostingClassifier(max_iter=150,max_leaf_nodes=15,l2_regularization=1.,random_state=42,early_stopping=False)
  def new_logit():return Pipeline([('impute',SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True)),('scale',StandardScaler()),('clf',LogisticRegression(C=.1,max_iter=500,random_state=42,solver='lbfgs'))])
  def fit_model(model,x,yy,ww,name,pipe=False):
   rec['predictive_fits_started']+=1;prog(out,rec)
   if rec['predictive_fits_started']>g['fit_cap']:raise ValueError('fit cap')
   with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always')
    if pipe:model.fit(x,yy,clf__sample_weight=ww)
    else:model.fit(x,yy,sample_weight=ww)
   rec['predictive_fits_completed']+=1
   if pipe:rec['preprocessor_components_fitted']+=2
   if rec['preprocessor_components_fitted']>g['preprocessor_cap']:raise ValueError('preprocessor cap')
   if any(issubclass(z.category,ConvergenceWarning) for z in caught):raise ValueError('convergence warning in '+name)
   with (out/(name+'.joblib')).open('xb') as f:joblib.dump(model,f,compress=3)
   prog(out,rec);return model
  def margin(model,x):
   if rec['model_prediction_rows']+len(x)>g['model_row_cap']:raise ValueError('prediction cap')
   v=np.asarray(model.decision_function(x),float);rec['model_prediction_rows']+=len(x)
   if v.ndim!=1 or not np.isfinite(v).all():raise ValueError('nonfinite model margin')
   return v
  specs=[('hgb_F0',X0,new_hgb,False),('hgb_F3',X3,new_hgb,False),('logit_F3',X3,new_logit,True)]
  oof={};final={};calibrators={};fitmanifest=[]
  for name,X,factory,pipe in specs:
   m=np.full(len(ti),np.nan)
   for j,fold in enumerate(folds):
    trainmask=np.asarray([x not in fold for x in grids]);valmask=np.asarray([x in fold for x in grids]);tr=ti[trainmask];va=ti[valmask]
    if not len(tr) or not len(va) or len(set(y[trainmask]))!=2 or len(set(y[valmask]))!=2 or set(grids[trainmask])&set(grids[valmask]):raise ValueError('fold class or group split')
    estimator=fit_model(factory(),X[tr],y[trainmask],weights_for(cids[trainmask]),name+'_fold'+str(j),pipe)
    m[valmask]=margin(estimator,X[va]);fitmanifest.append(dict(model=name,fold=j,fit_groups=sorted(set(grids[trainmask])),oof_groups=sorted(set(grids[valmask])),fit_rows=len(tr),oof_rows=len(va)))
   if not np.isfinite(m).all():raise ValueError('incomplete oof')
   oof[name]=m
   final[name]=fit_model(factory(),X[ti],y,weights,name+'_final',pipe)
  # Calibrate solely on group-isolated OOF margins; no held outcome is read here.
  for name in oof:
   cal=LogisticRegression(C=1000.,max_iter=500,random_state=42,solver='lbfgs')
   calibrators[name]=fit_model(cal,oof[name].reshape(-1,1),y,weights,name+'_platt',False)
  if rec['predictive_fits_completed']!=15 or rec['preprocessor_components_fitted']!=8:raise ValueError('fit count')
  rec['held_outcomes_used_in_fitting']=False;rec['all_fits_before_held_scoring']=True;prog(out,rec)
  held_targets={};viset=set(vi.tolist())
  with (FORMAL/'train_targets.jsonl').open(encoding='utf-8') as f:
   for i,line in enumerate(f):
    if i in viset:
     z=json.loads(line);held_targets[i]=z['target_rul_weeks']
  if len(held_targets)!=len(vi):raise ValueError('held target rows')
  status=[held_targets[int(i)] is not None for i in vi];observed=np.asarray(status,bool);censored=~observed
  if observed.sum()!=536 or censored.sum()!=0:raise ValueError('audited censor status changed')
  yval=np.asarray([float(held_targets[int(i)])<=4. if held_targets[int(i)] is not None else False for i in vi],int)
  if int(yval[observed].sum())!=179:raise ValueError('held class drift')
  base={}
  for name,X,_,_ in specs:
   raw=margin(final[name],X[vi]);platt=margin(calibrators[name],raw.reshape(-1,1));base[name]=(raw,platt)
  mean=float(np.dot(y,weights)/weights.sum())
  if not 0.<mean<1.:raise ValueError('constant probability')
  constant=float(np.log(mean/(1.-mean)));methodmargin={'constant_train_cell_mean':np.full(len(vi),constant)}
  for name,(raw,platt) in base.items():methodmargin[name+'_raw']=raw;methodmargin[name+'_platt']=platt
  cases=[];summaries=[];bincal=[];armmetrics=[];percell={};episodecount={};valcids=np.asarray([visible[i]['cell_id'] for i in vi]);valgroups=np.asarray([group(x) for x in valcids]);valarms=np.asarray([visible[i]['arm'] for i in vi]);valweights=weights_for(valcids)
  for name,m in methodmargin.items():
   prob=np.asarray(expit(m),float);loss=np.logaddexp(0.,m)-yval*m
   if not np.isfinite(prob).all() or not np.isfinite(loss[observed]).all() or (prob<0).any() or (prob>1).any():raise ValueError('invalid risk/logloss')
   by=collections.defaultdict(list);episodes=collections.defaultdict(list)
   for j,i in enumerate(vi):
    row=visible[int(i)];truth=held_targets[int(i)];known=truth is not None;yy=int(yval[j]) if known else None;err=(float(prob[j])-yy)**2 if known else None
    cases.append(dict(model=name,cell_id=row['cell_id'],source_group=group(row['cell_id']),arm=row['arm'],query_epoch=row['query_epoch'],label_status='observed' if known else 'censored',target_rul_weeks=truth,target_within4=yy,prob_within4=float(prob[j]),raw_margin=float(m[j]),Brier4=err,logloss=float(loss[j]) if known else None))
    if known:
     by[row['cell_id']].append((err,float(loss[j]),yy,float(prob[j]),row['arm']))
     if 0.<float(truth)<=4.:episodes[(row['cell_id'],row['arm'])].append(float(prob[j]))
   percell[name]={cid:float(np.mean([z[0] for z in rs])) for cid,rs in by.items()}
   missed=sum(not any(p>=.5 for p in ps) for ps in episodes.values());episodecount[name]=missed
   positive=observed & (yval==1);negative=observed & (yval==0)
   summaries.append(dict(model=name,held_cells=len(by),held_groups=len({group(z) for z in by}),observed_rows=int(observed.sum()),censored_rows=int(censored.sum()),positive_rows=int(positive.sum()),negative_rows=int(negative.sum()),cell_macro_Brier4=float(np.mean(list(percell[name].values()))),cell_macro_logloss=float(np.mean([np.mean([z[1] for z in v]) for v in by.values()])),false_negative_fraction=float(np.mean(prob[positive]<.5)),false_positive_fraction=float(np.mean(prob[negative]>=.5)),pre_event_episode_units=len(episodes),missed_pre_event_episode_units=missed,episode_unit='cell and arm; fixed 0.5 probability threshold'))
   for arm in sorted(set(valarms)):
    k=observed & (valarms==arm);byarm=collections.defaultdict(list)
    for j in np.flatnonzero(k):byarm[valcids[j]].append(float((prob[j]-yval[j])**2))
    armmetrics.append(dict(model=name,arm=arm,rows=int(k.sum()),cells=len(byarm),cell_macro_Brier4=float(np.mean([np.mean(v) for v in byarm.values()])),positive_rows=int(np.sum(k & (yval==1))),false_negative_fraction=float(np.mean(prob[k & (yval==1)]<.5)) if np.any(k & (yval==1)) else None))
   for binid in range(5):
    k=observed & (prob>=binid/5.) & ((prob<(binid+1)/5.) if binid<4 else (prob<=1.))
    bincal.append(dict(model=name,bin=binid,lower=binid/5.,upper=(binid+1)/5.,rows=int(k.sum()),cell_weighted_mean_probability=float(np.average(prob[k],weights=valweights[k])) if np.any(k) else None,cell_weighted_event_rate=float(np.average(yval[k],weights=valweights[k])) if np.any(k) else None))
  refs=['logit_F3_platt','hgb_F0_platt'];candidate='hgb_F3_platt';cells=sorted(set(valcids));groups=sorted(set(valgroups));rng=np.random.RandomState(42);idx=rng.randint(len(groups),size=(5000,len(groups)));contrasts=[]
  for ref in refs:
   delta=np.asarray([percell[candidate][cid]-percell[ref][cid] for cid in cells]);sums=np.asarray([sum(delta[i] for i,cid in enumerate(cells) if group(cid)==gr) for gr in groups]);counts=np.asarray([sum(group(cid)==gr for cid in cells) for gr in groups]);boot=sums[idx].sum(axis=1)/counts[idx].sum(axis=1)
   cand=float(np.mean(list(percell[candidate].values())));baseval=float(np.mean(list(percell[ref].values())))
   contrasts.append(dict(candidate=candidate,reference=ref,delta_Brier4=float(delta.mean()),family_corrected_CI_low=float(np.quantile(boot,.0125)),family_corrected_CI_high=float(np.quantile(boot,.9875)),relative_Brier_improvement=float((baseval-cand)/baseval),candidate_missed_episodes=episodecount[candidate],reference_missed_episodes=episodecount[ref],groups=len(groups),cells=len(cells),worst_cell=cells[int(np.argmax(delta))],worst_cell_delta=float(max(delta)),bootstrap_replicates=5000,interpretation='Conditional development bootstrap over ten source groups, not paper confirmation.'))
  passed=all(z['family_corrected_CI_high']<0 and z['relative_Brier_improvement']>=.05 and z['candidate_missed_episodes']<=z['reference_missed_episodes'] for z in contrasts)
  csvout(out/'predictions.csv',cases);csvout(out/'summary.csv',summaries);csvout(out/'arm_metrics.csv',armmetrics);csvout(out/'calibration_bins.csv',bincal);csvout(out/'paired_contrasts.csv',contrasts);writej(out/'fit_manifest.json',dict(folds=fitmanifest,outer_held_groups=sorted(held),mature_train_groups=sorted(mature),cutoff_epoch=cut))
  writej(out/'ROOT_DECISION.json',dict(status='F3_RISK_PROXY_SCREEN_PASS_NOT_SERVICE_VALIDATION' if passed else 'NO_GAIN_FIXED_F3_RISK_SCREEN',paper_ready=False,prior_pending_policy_stopped=True,primary_gate='F3 calibrated Brier improves >=5 percent vs both F3 logistic and F0 HGB, each family-corrected CI below zero, and misses no more pre-event cell/arm episodes.',limits=['Only 10 held groups and 15 mature training groups.','Hypothetical EOL+14d feedback, not measured label availability.','Retrospective cutoff selected on historical query support; same dataset has prior development exposure.','Censored train queries excluded from supervised loss, not solved.','Static probability component, no online scheduler, interval distribution, real service or independent dataset.']))
  rec.update(status='SUCCESS',finished_utc=stamp(),elapsed_seconds=time.time()-t0,GO_sha256=sha(gpath),input_sha256=g['input_sha256'],train_rows=len(ti),held_rows=len(vi),held_observed=int(observed.sum()),held_censored=int(censored.sum()),held_groups=len(groups),train_groups=len(mature),sklearn_version=sklearn.__version__,prior_failed_audit='experiments/rulaas_temporal_risk_20261029/audit01/failure_receipt.json')
  writej(out/'receipt.json',rec);prog(out,rec);print(json.dumps(dict(status='SUCCESS',fits=rec['predictive_fits_completed'],preprocessing=rec['preprocessor_components_fitted'],model_rows=rec['model_prediction_rows'],elapsed_seconds=rec['elapsed_seconds'],summaries=summaries,contrasts=contrasts,decision='F3_RISK_PROXY_SCREEN_PASS_NOT_SERVICE_VALIDATION' if passed else 'NO_GAIN_FIXED_F3_RISK_SCREEN'),ensure_ascii=False))
 except BaseException as ex:
  rec.update(status='FAILED',error=repr(ex),traceback=traceback.format_exc(),finished_utc=stamp(),elapsed_seconds=time.time()-t0,partial_preprocessing_may_have_fitted=rec['predictive_fits_started']>rec['predictive_fits_completed'])
  if out.is_dir() and not (out/'failure_receipt.json').exists():writej(out/'failure_receipt.json',rec)
  print(json.dumps(rec));raise
 finally:
  for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--go',required=True);main(pathlib.Path(a.parse_args().go))
