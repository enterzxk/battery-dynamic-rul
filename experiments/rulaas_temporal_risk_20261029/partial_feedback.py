#!/usr/bin/env python3
"""Fixed F0 comparison: horizon-matured feedback vs stored full-EOL feedback."""
import os
os.environ['OMP_NUM_THREADS']='4';os.environ['MKL_NUM_THREADS']='4'
import pathlib,json,csv,hashlib,datetime,time,collections,fcntl,traceback,argparse,warnings
import numpy as np
from scipy.special import expit
R=pathlib.Path('/home/yndx/zxk/rul');H=R/'experiments/rulaas_temporal_risk_20261029';AUD=H/'audit02';HOR=H/'horizon_audit01';PREV=H/'run01';FORMAL=R/'experiments/multisource_factorial_20261021/run2_clocksafe';OWNER='01a17810-6ae6-7cf2-9729-5bfcaa8df5f4'
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def readj(p):return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def csvread(p):
 with pathlib.Path(p).open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def writej(p,x):
 with pathlib.Path(p).open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def csvout(p,rs):
 if not rs:raise ValueError('empty artifact '+str(p))
 with pathlib.Path(p).open('x',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
def prog(p,x):
 t=p/'progress.tmp';t.write_text(json.dumps(x,ensure_ascii=False),encoding='utf-8');os.replace(t,p/'progress.json')
def group(c):return c.rsplit('C',1)[0]
def weights_for(cids):
 c=collections.Counter(cids);w=np.asarray([1./c[x] for x in cids],float);return w*len(w)/w.sum()
def main(gpath):
 g=readj(gpath);out=R/g['output'];t0=time.time();locks=[]
 rec=dict(status='STARTED',request_id=g['request_id'],started_utc=stamp(),predictive_fits_started=0,predictive_fits_completed=0,preprocessor_components_fitted=0,model_prediction_rows=0,C3_payload_reads=0,C4_payload_reads=0,actual_coordinator_model_recorded=g['actual_model'])
 try:
  for p in [R/'automation/state/coordinator.lock',R/'automation/locks/isu_irregular_rul_cpu.lock']:
   f=p.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  c=readj(R/'automation/state/coordinator.json');hb=datetime.datetime.fromisoformat(c['heartbeat_utc'].replace('Z','+00:00'))
  if c.get('state')!='ACTIVE' or c.get('owner')!=OWNER or c.get('thread_id')!=OWNER or (datetime.datetime.now(datetime.timezone.utc)-hb).total_seconds()>1800:raise ValueError('owner or heartbeat')
  if g.get('status')!='APPROVED' or g.get('owner')!=OWNER or g.get('allow_fits') is not True or g.get('allow_C3') is not False or g.get('allow_C4') is not False or g['fit_cap']!=5 or g['model_row_cap']!=2500 or g['seed']!=42:raise ValueError('GO')
  for name,h in g['input_sha256'].items():
   if sha(R/name)!=h:raise ValueError('input hash '+name)
  if out.parent!=H or out.exists():raise ValueError('create-only output')
  writej(H/(g['request_id']+'.claim.json'),dict(GO_sha256=sha(gpath),utc=stamp()));out.mkdir();prog(out,rec)
  audit=readj(HOR/'INDEPENDENT_RECOMPUTE.json');hs=readj(HOR/'SUMMARY.json');prior=readj(PREV/'INDEPENDENT_RECOMPUTE_V2.json');prior_decision=readj(PREV/'ROOT_DECISION.json');split=readj(AUD/'split.json')
  if audit['status']!='PASS' or prior['status']!='PASS' or prior_decision['status']!='NO_GAIN_FIXED_F3_RISK_SCREEN':raise ValueError('predecessor audit or stop')
  cut=float(split['selected']['cutoff_epoch']);outertrain=set(split['outer_train_groups']);outerheld=set(split['outer_held_groups'])
  if len(outertrain)!=47 or len(outerheld)!=16 or outertrain&outerheld:raise ValueError('outer split')
  status=csvread(HOR/'training_label_status.csv');mature=[z for z in status if z['label_within4']!=''];unknown=[z for z in status if not z['label_within4']]
  if len(mature)!=1219 or len(unknown)!=374 or sum(z['label_within4']=='1' for z in mature)!=256 or sum(z['old_exact_event_matured']=='True' for z in mature)!=940:raise ValueError('horizon cohort')
  with (FORMAL/'train_targets.jsonl').open(encoding='utf-8') as f:
   meta=[]
   for line in f:
    z=json.loads(line);meta.append(dict(cell_id=z['cell_id'],arm=z['arm'],query_epoch=float(z['query_epoch']),known_event=bool(z['known_event'])))
  ti=[];yy=[]
  for z in mature:
   i=int(z['row_index']);x=meta[i];cid=x['cell_id'];q=x['query_epoch']
   if cid!=z['cell_id'] or x['arm']!=z['arm'] or q!=float(z['query_epoch']) or x['known_event'] or q>cut or group(cid) not in outertrain or group(cid) in outerheld or float(z['label_available_epoch'])>cut:raise ValueError('training as-of or key')
   ti.append(i);yy.append(int(z['label_within4']))
  if len(set(ti))!=1219:raise ValueError('duplicate training keys')
  ti=np.asarray(ti,int);y=np.asarray(yy,int);cids=np.asarray([meta[i]['cell_id'] for i in ti]);groups=np.asarray([group(cid) for cid in cids]);allgroups=sorted(set(groups));np.random.RandomState(42).shuffle(allgroups);folds=[set(allgroups[i::3]) for i in range(3)]
  if len(allgroups)!=19 or [len(f) for f in folds]!=[7,6,6] or set(allgroups)&outerheld:raise ValueError('training group folds')
  vi=np.asarray([i for i,z in enumerate(meta) if group(z['cell_id']) in outerheld and z['query_epoch']>=cut and not z['known_event']],int)
  if len(vi)!=536 or len({group(meta[i]['cell_id']) for i in vi})!=10:raise ValueError('held keys')
  X=np.load(FORMAL/'train_features.npz',allow_pickle=False)['F0']
  if X.shape!=(6870,74) or np.isinf(X).any():raise ValueError('feature panel')
  from sklearn.ensemble import HistGradientBoostingClassifier
  from sklearn.linear_model import LogisticRegression
  from sklearn.exceptions import ConvergenceWarning
  import sklearn,joblib
  def new_model():return HistGradientBoostingClassifier(max_iter=150,max_leaf_nodes=15,l2_regularization=1.,random_state=42,early_stopping=False)
  def fit(model,x,lab,w,name):
   rec['predictive_fits_started']+=1;prog(out,rec)
   if rec['predictive_fits_started']>g['fit_cap']:raise ValueError('fit cap')
   with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always');model.fit(x,lab,sample_weight=w)
   rec['predictive_fits_completed']+=1
   if any(issubclass(z.category,ConvergenceWarning) for z in caught):raise ValueError('convergence '+name)
   with (out/(name+'.joblib')).open('xb') as f:joblib.dump(model,f,compress=3)
   prog(out,rec);return model
  def margin(model,x):
   if rec['model_prediction_rows']+len(x)>g['model_row_cap']:raise ValueError('prediction cap')
   p=np.asarray(model.decision_function(x),float);rec['model_prediction_rows']+=len(x)
   if p.ndim!=1 or not np.isfinite(p).all():raise ValueError('margin')
   return p
  oof=np.full(len(ti),np.nan);foldman=[]
  for j,fold in enumerate(folds):
   tr=np.asarray([x not in fold for x in groups]);va=np.asarray([x in fold for x in groups])
   if len(set(y[tr]))!=2 or len(set(y[va]))!=2 or set(groups[tr])&set(groups[va]):raise ValueError('fold support')
   model=fit(new_model(),X[ti[tr]],y[tr],weights_for(cids[tr]),'partial_F0_fold'+str(j));oof[va]=margin(model,X[ti[va]])
   foldman.append(dict(fold=j,fit_groups=sorted(set(groups[tr])),oof_groups=sorted(set(groups[va])),fit_rows=int(tr.sum()),oof_rows=int(va.sum())))
  if not np.isfinite(oof).all():raise ValueError('incomplete OOF')
  final=fit(new_model(),X[ti],y,weights_for(cids),'partial_F0_final')
  cal=fit(LogisticRegression(C=1000.,max_iter=500,random_state=42,solver='lbfgs'),oof.reshape(-1,1),y,weights_for(cids),'partial_F0_platt')
  if rec['predictive_fits_completed']!=5:raise ValueError('fit count')
  rec['all_fits_before_held_scoring']=True;prog(out,rec)
  oofrows=[dict(cell_id=cids[j],source_group=groups[j],arm=meta[i]['arm'],query_epoch=meta[i]['query_epoch'],target_within4=int(y[j]),raw_margin=float(oof[j]),raw_probability=float(expit(oof[j]))) for j,i in enumerate(ti)]
  csvout(out/'training_oof.csv',oofrows)
  old=[z for z in csvread(PREV/'predictions.csv') if z['model'] in ['hgb_F0_raw','hgb_F0_platt']]
  oldmap={(z['model'],z['cell_id'],z['arm'],float(z['query_epoch'])):z for z in old}
  if len(oldmap)!=1072:raise ValueError('stored baseline keys')
  raw=margin(final,X[vi]);calmargin=margin(cal,raw.reshape(-1,1));rawprob=expit(raw);calprob=expit(calmargin)
  preds=[]
  for j,i in enumerate(vi):
   z=meta[i];cid=z['cell_id'];arm=z['arm'];q=z['query_epoch'];key=(cid,arm,q);a=oldmap.get(('hgb_F0_raw',)+key);b=oldmap.get(('hgb_F0_platt',)+key)
   if a is None or b is None or a['target_rul_weeks']!=b['target_rul_weeks'] or a['target_within4']!=b['target_within4'] or a['label_status']!=b['label_status']:raise ValueError('baseline target mismatch')
   if a['label_status']!='observed':raise ValueError('unexpected held censor drift')
   target=float(a['target_rul_weeks']);label=int(a['target_within4'])
   if label!=int(target<=4.):raise ValueError('held label identity')
   for name,prob,score in [('event_only_raw',float(a['prob_within4']),float(a['raw_margin'])),('event_only_platt',float(b['prob_within4']),float(b['raw_margin'])),('horizon_mature_raw',float(rawprob[j]),float(raw[j])),('horizon_mature_platt',float(calprob[j]),float(calmargin[j]))]:
    loss=float(np.logaddexp(0.,score)-label*score)
    if not np.isfinite(prob) or not np.isfinite(loss):raise ValueError('nonfinite scores')
    preds.append(dict(model=name,cell_id=cid,source_group=group(cid),arm=arm,query_epoch=q,target_rul_weeks=target,target_within4=label,prob_within4=prob,raw_margin=score,Brier4=(prob-label)**2,logloss=loss))
  by=collections.defaultdict(list)
  for z in preds:by[(z['model'],z['cell_id'])].append(z)
  names=['event_only_raw','event_only_platt','horizon_mature_raw','horizon_mature_platt'];per={};summ=[];arm=[];miss={}
  for name in names:
   rr=[z for z in preds if z['model']==name];cells=sorted({z['cell_id'] for z in rr});per[name]={cid:float(np.mean([z['Brier4'] for z in by[name,cid]])) for cid in cells};events=collections.defaultdict(list)
   for z in rr:
    if 0.<z['target_rul_weeks']<=4:events[(z['cell_id'],z['arm'])].append(z['prob_within4'])
   miss[name]=sum(not any(v>=.5 for v in x) for x in events.values());pos=[z for z in rr if z['target_within4']==1];neg=[z for z in rr if z['target_within4']==0]
   summ.append(dict(model=name,held_cells=len(cells),held_groups=len({group(cid) for cid in cells}),held_rows=len(rr),positive_rows=len(pos),negative_rows=len(neg),cell_macro_Brier4=float(np.mean(list(per[name].values()))),cell_macro_logloss=float(np.mean([np.mean([z['logloss'] for z in by[name,cid]]) for cid in cells])),false_negative_fraction=float(np.mean([z['prob_within4']<.5 for z in pos])),false_positive_fraction=float(np.mean([z['prob_within4']>=.5 for z in neg])),pre_event_episode_units=len(events),missed_pre_event_episode_units=miss[name]))
   for a in sorted({z['arm'] for z in rr}):
    zz=[z for z in rr if z['arm']==a];cc=collections.defaultdict(list)
    for z in zz:cc[z['cell_id']].append(z['Brier4'])
    arm.append(dict(model=name,arm=a,rows=len(zz),cells=len(cc),cell_macro_Brier4=float(np.mean([np.mean(x) for x in cc.values()]))))
  cells=sorted(per['event_only_platt']);groupids=sorted({group(cid) for cid in cells});idx=np.random.RandomState(42).randint(len(groupids),size=(5000,len(groupids)));comparisons=[];cellrows=[]
  for candidate,reference in [('horizon_mature_platt','event_only_platt'),('horizon_mature_raw','event_only_raw')]:
   delta=np.asarray([per[candidate][cid]-per[reference][cid] for cid in cells]);sums=np.asarray([sum(delta[i] for i,cid in enumerate(cells) if group(cid)==gr) for gr in groupids]);counts=np.asarray([sum(group(cid)==gr for cid in cells) for gr in groupids]);boot=sums[idx].sum(axis=1)/counts[idx].sum(axis=1);base=float(np.mean(list(per[reference].values())));cand=float(np.mean(list(per[candidate].values())))
   comparisons.append(dict(candidate=candidate,reference=reference,delta_Brier4=float(delta.mean()),CI_low=float(np.quantile(boot,.025)),CI_high=float(np.quantile(boot,.975)),relative_Brier_improvement=float((base-cand)/base),candidate_missed_episodes=miss[candidate],reference_missed_episodes=miss[reference],cells_better=int(sum(d< -1e-12 for d in delta)),cells_worse=int(sum(d>1e-12 for d in delta)),worst_cell=cells[int(np.argmax(delta))],worst_cell_delta=float(max(delta)),groups=len(groupids),cells=len(cells),bootstrap_replicates=5000,interpretation='Post-hoc data regime comparison on previously inspected groups; not independent confirmation.'))
   for i,cid in enumerate(cells):cellrows.append(dict(candidate=candidate,reference=reference,cell_id=cid,source_group=group(cid),candidate_Brier4=per[candidate][cid],reference_Brier4=per[reference][cid],delta_Brier4=float(delta[i])))
  main=comparisons[0];passed=main['CI_high']<0 and main['relative_Brier_improvement']>=.05 and main['candidate_missed_episodes']<=main['reference_missed_episodes']
  csvout(out/'predictions.csv',preds);csvout(out/'summary.csv',summ);csvout(out/'arm_metrics.csv',arm);csvout(out/'paired_contrasts.csv',comparisons);csvout(out/'paired_per_cell.csv',cellrows)
  writej(out/'fit_manifest.json',dict(folds=foldman,mature_groups=sorted(set(groups)),outer_held_groups=sorted(outerheld),cutoff_epoch=cut,training_rows=len(ti),old_full_event_rows=940,added_negative_rows=279,unmatured_rows=374))
  writej(out/'ROOT_DECISION.json',dict(status='PARTIAL_FEEDBACK_PROXY_SCREEN_PASS_NOT_SERVICE_VALIDATION' if passed else 'NO_GAIN_FIXED_PARTIAL_FEEDBACK_F0',paper_ready=False,prior_F3_risk_NO_GAIN_preserved=True,prior_pending_policy_NO_GO_preserved=True,criterion='>=5 percent relative Brier improvement and group-bootstrap 95 percent CI upper below zero; missed pre-event cell-arm episodes no worse.',limits=['Partial feedback is a hypothetical full-source registry, not measured online feedback.','Baseline and candidate have different train group counts and class balance; effects not attributable to one factor.','Same 10 held groups were previously inspected and cutoff is retrospective.','374 unknown labels remain unused; no event-distribution or service-budget outcome.']))
  rec.update(status='SUCCESS',finished_utc=stamp(),elapsed_seconds=time.time()-t0,GO_sha256=sha(gpath),input_sha256=g['input_sha256'],training_rows=len(ti),training_groups=len(set(groups)),held_rows=len(vi),held_groups=len(groupids),prior_reference_reused_without_refit=True,sklearn_version=sklearn.__version__)
  writej(out/'receipt.json',rec);prog(out,rec);print(json.dumps(dict(status='SUCCESS',fits=rec['predictive_fits_completed'],model_rows=rec['model_prediction_rows'],elapsed_seconds=rec['elapsed_seconds'],summary=summ,comparisons=comparisons,decision='PARTIAL_FEEDBACK_PROXY_SCREEN_PASS_NOT_SERVICE_VALIDATION' if passed else 'NO_GAIN_FIXED_PARTIAL_FEEDBACK_F0'),ensure_ascii=False))
 except BaseException as ex:
  rec.update(status='FAILED',error=repr(ex),traceback=traceback.format_exc(),finished_utc=stamp(),elapsed_seconds=time.time()-t0)
  if out.is_dir() and not (out/'failure_receipt.json').exists():writej(out/'failure_receipt.json',rec)
  print(json.dumps(rec));raise
 finally:
  for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--go',required=True);main(pathlib.Path(a.parse_args().go))
