import pathlib,json,csv,collections,sys,fcntl,os,datetime
import numpy as np
import joblib
R=pathlib.Path('/home/yndx/zxk/rul');D=R/'experiments/rul_time_recovery_20261026'
def key(r):return r['cell_id'],r['arm'],float(r['query_epoch'])
def readcsv(p):return list(csv.DictReader(p.open()))
def sha(p):return __import__('hashlib').sha256(p.read_bytes()).hexdigest()
def newj(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2,allow_nan=False)
g=json.loads(pathlib.Path(sys.argv[1]).read_text());assert g['max_fits']==0
for p,h in g['sha256'].items():assert sha(R/p)==h,p
with (R/'experiments/state/consumed_gos.jsonl').open('a+') as f:
 fcntl.flock(f,fcntl.LOCK_EX);f.seek(0);assert all(json.loads(l).get('request_id')!=g['request_id'] for l in f if l.strip())
 newj(D/(g['request_id']+'.claim.json'),dict(pid=os.getpid(),go_sha256=sha(pathlib.Path(sys.argv[1]))))
 f.write(json.dumps(dict(request_id=g['request_id'],go_sha256=sha(pathlib.Path(sys.argv[1]))))+'\n');f.flush()
out=R/g['output'];out.mkdir(exist_ok=False)
p3=readcsv(D/'p3_calibration_run1/predictions.csv');p1=readcsv(D/'p1_run1/predictions.csv')
lookup={m:{key(r):r for r in p3 if r['model']==m} for m in sorted({r['model'] for r in p3})}
refs={('F3_mean','mean_weeks'):lookup['global_control'],('F3_median','median_weeks'):lookup['global_control']}
refs.update({(m,'point_weeks'):{key(r):r for r in p1 if r['model']==m} for m in ['direct_squared_error','direct_absolute_error']})
refs[('hgb_mu_only','median_weeks')]=lookup['hgb_mu_only']
assert all(len(v)==3765 for v in list(lookup.values())+list(refs.values()))
contrasts=[]
for model,rs in lookup.items():
 for arm in ['raw','sparse2','delay7d']:
  for point in ['mean_weeks','median_weeks']:
   for (refname,refpoint),ref in refs.items():
    cells=collections.defaultdict(list)
    for k,r in rs.items():
     assert ref[k]['target_rul_weeks']==r['target_rul_weeks']
     if r['arm']!=arm or r['known_event']!='False' or r['target_rul_weeks']=='':continue
     y=float(r['target_rul_weeks']);cells[r['cell_id']].append((abs(float(r[point])-y),abs(float(ref[k][refpoint])-y)))
    a=np.array([np.mean(v,axis=0) for c,v in sorted(cells.items())]);delta=a[:,0]-a[:,1]
    bs=np.random.default_rng(42).integers(0,len(delta),(5000,len(delta)));lo,hi=np.quantile(delta[bs].mean(1),[.025,.975])
    contrasts.append(dict(model=model,point=point,reference=refname,reference_point=refpoint,arm=arm,stratum='unconfirmed',candidate_mae=float(a[:,0].mean()),reference_mae=float(a[:,1].mean()),delta=float(delta.mean()),ci_low=float(lo),ci_high=float(hi),n_cells=len(delta),improved_fraction=float(np.mean(delta<0))))
obj=joblib.load(D/'p3_calibration_run1/ridge_context.joblib')
names=['base_log_prediction','calendar_age','capacity_fraction','last_capacity_slope','visible_reports','report_age','theilsen_slope','cycling_count','throughput']
coefs=[dict(feature=n,standardized_coefficient=float(v)) for n,v in zip(names,obj['model'].coef_)]
newj(out/'comparisons.json',dict(status='PASS',contrasts=contrasts,ridge_coefficients=coefs,new_fits=0,C4_reads=0,scope='Exploratory C3 comparisons, no independent confirmation'))
print(json.dumps(dict(ridge_raw=[c for c in contrasts if c['model']=='ridge_context' and c['arm']=='raw'],coefficients=coefs)))
