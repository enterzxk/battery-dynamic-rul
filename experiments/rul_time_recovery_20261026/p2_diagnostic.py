import os
os.environ['OMP_NUM_THREADS']='4'
os.environ['MKL_NUM_THREADS']='4'
os.environ['OPENBLAS_NUM_THREADS']='4'
import pathlib,json,csv,collections,datetime,hashlib,fcntl,sys,traceback,time
import numpy as np
import joblib
from scipy.stats import spearmanr
R=pathlib.Path('/home/yndx/zxk/rul');D=R/'experiments/rul_time_recovery_20261026'
C=R/'experiments/multisource_factorial_20261021/run2_clocksafe'
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def utc():return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def newj(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2,allow_nan=False)
def rows(p):return [json.loads(l) for l in p.open()]
def key(r):return r['cell_id'],r['arm'],float(r['query_epoch'])
def writecsv(p,rs):
 if not rs:return
 with p.open('x',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rs for k in r)));w.writeheader();w.writerows(rs)
def wmean(v,c):
 n=collections.Counter(c);w=np.array([1/n[x] for x in c]);return float(np.dot(w,v)/w.sum())
def main(go):
 start=time.time();g=json.loads(go.read_text());locks=[];out=None
 rec=dict(request_id=g['request_id'],started_utc=utc(),status='PREFLIGHT',predictor_fits=0,C4_reads=0)
 try:
  assert g['max_predictor_fits']==0
  c=json.loads((R/'automation/state/coordinator.json').read_text())
  assert c['owner']==c['thread_id']==g['owner_thread_id']
  for p,h in g['sha256'].items():assert sha(R/p)==h,p
  for p in ['automation/state/online_survival_cpu.lock','automation/locks/isu_irregular_rul_cpu.lock']:
   f=(R/p).open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  with (R/'experiments/state/consumed_gos.jsonl').open('a+') as f:
   fcntl.flock(f,fcntl.LOCK_EX);f.seek(0);assert all(json.loads(l).get('request_id')!=g['request_id'] for l in f if l.strip())
   newj(D/(g['request_id']+'.claim.json'),dict(pid=os.getpid(),go_sha256=sha(go),utc=utc()))
   f.write(json.dumps(dict(request_id=g['request_id'],go_sha256=sha(go),claimed_utc=utc()))+'\n');f.flush();os.fsync(f.fileno())
  out=R/g['output'];assert out.parent==D;out.mkdir(exist_ok=False)
  tr=rows(C/'train_targets.jsonl');dr=rows(C/'development_targets.jsonl')
  tm=rows(C/'train_rows.jsonl');dm=rows(C/'development_rows.jsonl')
  xt=np.load(C/'train_features.npz',allow_pickle=False)['F3'];xd=np.load(C/'development_features.npz',allow_pickle=False)['F3']
  assert {r['cell_id'] for r in tr}.isdisjoint({r['cell_id'] for r in dr})
  assert all(key(a)==key(b) for a,b in zip(tr,tm)) and all(key(a)==key(b) for a,b in zip(dr,dm))
  assert len(tr)==len(tm)==len(xt)==6870 and len(dr)==len(dm)==len(xd)==3765
  positive=np.array([i for i,r in enumerate(tr) if r['target_rul_weeks'] is not None and r['target_rul_weeks']>0])
  yc=np.log(np.array([tr[i]['target_rul_weeks'] for i in positive]))
  cells=np.array([tr[i]['cell_id'] for i in positive]);ids=sorted(set(cells));np.random.RandomState(42).shuffle(ids)
  folds=[set(ids[::2]),set(ids[1::2])];oof=np.empty(len(yc));saved_order=[]
  for i,held in enumerate(folds):
   ix=np.array([c in held for c in cells]);model=joblib.load(C/('hgb_F3_oof%d.joblib'%i))
   oof[ix]=model.predict(xt[positive[ix]]);saved_order.extend(np.flatnonzero(ix))
  resid=yc-oof;saved=joblib.load(C/'hgb_F3_distribution.joblib')['residuals']
  assert np.max(abs(resid[saved_order]-saved))<1e-12
  records=[];correlations=[]
  features={0:'calendar_age',1:'capacity_fraction',3:'last_capacity_slope',4:'visible_report_count',6:'report_age',8:'theilsen_slope',686:'cycling_count',687:'cumulative_throughput'}
  for j,label in features.items():
   v=xt[positive,j];finite=np.isfinite(v)
   for e,name in [(resid,'signed_log_residual'),(abs(resid),'absolute_log_residual')]:
    rho=float(spearmanr(v[finite],e[finite]).statistic)
    correlations.append(dict(feature=label,error=name,spearman_rho=rho if np.isfinite(rho) else None,scope='TRAIN_CELL_OOF_ONLY',n=int(finite.sum())))
   cuts=np.unique(np.quantile(v[finite],[0,.25,.5,.75,1]))
   for k in range(len(cuts)-1):
    ix=finite&(v>=cuts[k])&((v<=cuts[k+1]) if k==len(cuts)-2 else (v<cuts[k+1]))
    if not ix.any():continue
    records.append(dict(feature=label,bin=k,lower=float(cuts[k]),upper=float(cuts[k+1]),n=int(ix.sum()),n_cells=len(set(cells[ix])),
      signed_log_residual=wmean(resid[ix],cells[ix]),absolute_log_residual=wmean(abs(resid[ix]),cells[ix]),
      residual_sd=float(np.std(resid[ix])),scope='TRAIN_CELL_OOF_ONLY'))
  writecsv(out/'train_oof_error_bins.csv',records);writecsv(out/'train_oof_correlations.csv',correlations)
  base={key(r):r for r in csv.DictReader((C/'predictions.csv').open()) if r['model']=='hgb_F3'}
  direct={(r['model'],)+key(r):r for r in csv.DictReader((D/'p1_run1/predictions.csv').open())}
  order=collections.defaultdict(list)
  for i,r in enumerate(dr):order[r['cell_id'],r['arm']].append(i)
  prediction=[]
  # Eq9 linear label Y=theta-t gives theta=mean(pred_j+t_j); no target labels used.
  # Apply causally to saved forecasts, with all-prefix and fixed recent-three variants.
  for (cid,arm),indices in sorted(order.items()):
   indices.sort(key=lambda i:float(dr[i]['query_epoch']))
   history=collections.defaultdict(list)
   for i in indices:
    r=dr[i];epoch=float(r['query_epoch'])/604800.
    b=base[key(r)];assert ('' if r['target_rul_weeks'] is None else float(b['target_rul_weeks']))==('' if r['target_rul_weeks'] is None else r['target_rul_weeks'])
    values={'F3_mean':float(b['mean_weeks']),'F3_median':float(b['median_weeks'])}
    values.update({m:float(direct[(m,)+key(r)]['point_weeks']) for m in ['direct_squared_error','direct_absolute_error']})
    for name,p in values.items():
     if not r['known_event']:history[name].append((epoch,p+epoch))
     for mode,n in [('PR_all',None),('PR_recent3',3)]:
      h=history[name] if n is None else history[name][-n:]
      q=0. if r['known_event'] else max(0.,float(np.mean([v for _,v in h]))-epoch)
      prediction.append(dict(cell_id=cid,arm=arm,query_epoch=r['query_epoch'],known_event=r['known_event'],y_event=r['y_event'],
        target_rul_weeks=r['target_rul_weeks'],model=name+'_'+mode,pred_weeks=q,
        history_predictions=len(h),max_history_query_epoch=max([v[0]*604800. for v in h],default=0.)))
      assert prediction[-1]['max_history_query_epoch']<=r['query_epoch']+1e-6
  writecsv(out/'predictions_PR.csv',prediction)
  summary=[];percell=[]
  for model in sorted({p['model'] for p in prediction}):
   for arm in ['raw','sparse2','delay7d']:
    for stratum in ['all','unconfirmed','early_gt12w','near_le4w','hidden_event']:
     ss=[p for p in prediction if p['model']==model and p['arm']==arm and p['target_rul_weeks'] is not None and
       (stratum=='all' or stratum=='unconfirmed' and not p['known_event'] or stratum=='early_gt12w' and p['target_rul_weeks']>12 or
       stratum=='near_le4w' and 0<p['target_rul_weeks']<=4 or stratum=='hidden_event' and p['y_event']==1 and not p['known_event'])]
     by=collections.defaultdict(list)
     for p in ss:by[p['cell_id']].append(p)
     a=[];b=[]
     for cid,rs in sorted(by.items()):
      cmae=float(np.mean([abs(p['pred_weeks']-p['target_rul_weeks']) for p in rs]));bmae=float(np.mean([abs(float(base[key(p)]['mean_weeks'])-p['target_rul_weeks']) for p in rs]))
      a.append(cmae);b.append(bmae);percell.append(dict(model=model,arm=arm,stratum=stratum,cell_id=cid,mae=cmae,baseline_mean_mae=bmae,delta=cmae-bmae,n=len(rs)))
     if not a:continue
     v=np.array(a)-b;rg=np.random.default_rng(42);bs=v[rg.integers(0,len(v),(5000,len(v)))].mean(1);lo,hi=np.quantile(bs,[.025,.975])
     summary.append(dict(model=model,arm=arm,stratum=stratum,mae_weeks=float(np.mean(a)),baseline_mae=float(np.mean(b)),delta=float(v.mean()),ci_low=float(lo),ci_high=float(hi),n_cells=len(a),n_queries=len(ss),improved_fraction=float(np.mean(v<0))))
  writecsv(out/'PR_summary.csv',summary);writecsv(out/'PR_per_cell.csv',percell)
  rec.update(status='SUCCESS',finished_utc=utc(),wall_seconds=time.time()-start,OOF_residual_identity_max_error=float(np.max(abs(resid[saved_order]-saved))),
    train_oof_model_predictions=len(positive),PR_predictions=len(prediction),analytic_query_rectifications=len(prediction),
    chronological_prefix_assertion=True,novelty_claim=False,PR_scope='Eq9 linear rectification adapted to existing HGBs; not full neural reproduction',
    primary=[s for s in summary if s['arm']=='raw' and s['stratum']=='unconfirmed'],
    top_correlations=sorted(correlations,key=lambda x:abs(x['spearman_rho'] or 0),reverse=True)[:8])
  newj(out/'receipt.json',rec);print(json.dumps(rec))
 except BaseException as e:
  rec.update(status='FAILED_STOP',error=repr(e),traceback=traceback.format_exc())
  newj((out if out is not None else D)/(g['request_id']+'_failure.json'),rec);raise
 finally:
  for f in reversed(locks):f.close()
if __name__=='__main__':main(pathlib.Path(sys.argv[1]))
