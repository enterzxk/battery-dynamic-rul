import os
os.environ['OMP_NUM_THREADS']='4';os.environ['OPENBLAS_NUM_THREADS']='4'
import pathlib,json,sys,fcntl,time,collections,importlib.util,traceback,signal
import numpy as np
R=pathlib.Path('/home/yndx/zxk/rul');D=R/'experiments/rul_time_recovery_20261026';C=R/'experiments/multisource_factorial_20261021/run2_clocksafe'
spec=importlib.util.spec_from_file_location('p1',D/'runner.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def group(cid):return cid.split('C')[0]
def main(go):
 g=m.readj(go);out=None;locks=[];t=time.time();rec=dict(status='PREFLIGHT',request_id=g['request_id'],predictor_fits=0,reference_library_estimations=0,C4_reads=0)
 try:
  assert g['max_predictor_fits']==0 and g['max_reference_library_estimations']==1
  c=m.readj(R/'automation/state/coordinator.json');assert c['owner']==c['thread_id']==g['owner_thread_id']
  for p,h in g['sha256'].items():assert m.sha(R/p)==h,p
  for p in ['automation/state/online_survival_cpu.lock','automation/locks/isu_irregular_rul_cpu.lock']:
   f=(R/p).open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  with (R/'experiments/state/consumed_gos.jsonl').open('a+') as f:
   fcntl.flock(f,fcntl.LOCK_EX);f.seek(0);assert all(json.loads(l).get('request_id')!=g['request_id'] for l in f if l.strip())
   m.createj(D/(g['request_id']+'.claim.json'),dict(pid=os.getpid(),go_sha256=m.sha(go)))
   f.write(json.dumps(dict(request_id=g['request_id'],go_sha256=m.sha(go)))+'\n');f.flush()
  out=R/g['output'];assert out.parent==D;out.mkdir(exist_ok=False)
  signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('600 second bound')));signal.alarm(600)
  tr=m.jsonlines(C/'train_targets.jsonl');dr=m.jsonlines(C/'development_targets.jsonl');dm=m.jsonlines(C/'development_rows.jsonl')
  xt=np.load(C/'train_features.npz',allow_pickle=False)['F3'];xd=np.load(C/'development_features.npz',allow_pickle=False)['F3']
  assert len(tr)==len(xt)==6870 and len(dr)==len(dm)==len(xd)==3765
  assert {r['cell_id'] for r in tr}.isdisjoint({r['cell_id'] for r in dr})
  assert all(r['cell_id'].endswith(('C1','C2')) for r in tr) and all(r['cell_id'].endswith('C3') for r in dr)
  assert all(m.key(r)==m.key(z) for r,z in zip(dr,dm))
  for x,rs in [(xt,tr),(xd,dr)]:
   for i,r in enumerate(rs):
    assert int(np.argmax(x[i,10:74]))+1==int(group(r['cell_id'])[1:])
  lib=collections.defaultdict(list);event_ages=collections.defaultdict(list)
  for i,r in enumerate(tr):
   if r['arm']!='raw' or r['target_rul_weeks'] is None:continue
   cid=r['cell_id'];lib[cid].append((float(xt[i,1]),float(xt[i,0]),float(r['target_rul_weeks'])))
   if r['target_rul_weeks']>0:event_ages[cid].append(float(xt[i,0])+r['target_rul_weeks'])
  valid=sorted(set(event_ages));lib={cid:np.array(sorted(lib[cid],key=lambda z:z[1])) for cid in valid}
  ages={cid:float(np.median(event_ages[cid])) for cid in valid}
  spread=max(max(v)-min(v) for v in event_ages.values());assert spread<1e-4
  bygroup=collections.defaultdict(list)
  for cid in valid:bygroup[group(cid)].append(cid)
  rec.update(reference_library_estimations=1,reference_cells=len(valid),reference_groups=len(bygroup),event_age_reconstruction_spread_max=spread,reference_ids=valid,reference_populations='C1/C2 only; unknown-event cells excluded without invented lifetimes')
  base={m.key(r):r for r in __import__('csv').DictReader((C/'predictions.csv').open()) if r['model']=='hgb_F3'}
  pred=[];fallbacks=0
  for name in ['group_EOL_prior','group_capacity_analog']:
   for i,r in enumerate(dr):
    peers=bygroup.get(group(r['cell_id']),valid);fallback=group(r['cell_id']) not in bygroup;fallbacks+=int(fallback)
    assert r['cell_id'] not in peers
    if name=='group_EOL_prior':support=np.array([max(0.,ages[cid]-float(xd[i,0])) for cid in peers])
    else:
     support=[]
     for cid in peers:
      a=lib[cid];j=int(np.argmin(abs(a[:,0]-float(xd[i,1]))));support.append(max(0.,float(a[j,2])-float(xd[i,6])))
     support=np.array(support)
    dist=m.PointZero() if r['known_event'] else m.EmpiricalRUL(support)
    e=dict(r,last_arrival_epoch=max(dm[i]['visible_rpt_arrival_epochs']),delta_weeks=(r['query_epoch']-max(dm[i]['visible_rpt_arrival_epochs']))/604800.,history_key=dm[i]['history_key'])
    q=m.metric_row(e,dist,42,name,0.);q.update(point_weeks=dist.quantile(.5),reference_count=len(peers),reference_fallback=fallback)
    pred.append(q)
  m.write_csv(out/'predictions.csv',pred);ss,cc,_=m.summarize(pred);m.write_csv(out/'distribution_summary.csv',ss);m.write_csv(out/'distribution_per_cell.csv',cc)
  for r in dr:
   b=base[m.key(r)];assert (None if b['target_rul_weeks']=='' else float(b['target_rul_weeks']))==r['target_rul_weeks']
   for n in ['mean_weeks','median_weeks']:b[n]=float(b[n])
  ps=m.point_report(pred,base,out)
  rec.update(status='SUCCESS',wall_seconds=time.time()-t,predictions=len(pred),fallback_query_model_pairs=fallbacks,novelty_claim=False,primary=[p for p in ps if p['arm']=='raw' and p['stratum']=='unconfirmed'])
  m.createj(out/'receipt.json',rec);print(json.dumps(rec))
 except BaseException as e:
  rec.update(status='FAILED_STOP',error=repr(e),traceback=traceback.format_exc());m.createj((out if out else D)/(g['request_id']+'_failure.json'),rec);raise
 finally:
  for f in reversed(locks):f.close()
if __name__=='__main__':main(pathlib.Path(sys.argv[1]))
