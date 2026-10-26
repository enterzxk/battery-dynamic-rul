#!/home/yndx/miniconda3/envs/a40_env/bin/python
"""Zero-fit postprocessing: B2 trajectory RUL vs saved same-input comparator.

Reads ONLY saved prediction/sample artifacts and one saved comparator CSV. No payload,
no checkpoint, no model forward, no fits. GO-gated with exact hashes and fresh paths.
"""
from __future__ import annotations
import argparse,csv,datetime,hashlib,json,math,pathlib,sys,time
import numpy as np
ROOT=pathlib.Path('/home/yndx/zxk/rul');HERE=ROOT/'experiments/trajectory_b2_joint_marked_renewal_20261021/candidate_v2'
OWNER='01a15c3a-1a06-7d61-8517-27b70b246183'
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def atomicj(p,x):
 t=pathlib.Path(str(p)+'.tmp');t.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=True),encoding='utf-8');os_replace=__import__('os').replace;os_replace(t,p)
def pinball(y,q,tau):
 d=y-q
 return float(np.mean(np.maximum(tau*d,(tau-1.0)*d)))
def crps_from_samples(y,s):
 s=np.sort(np.asarray(s,dtype=float));n=len(s)
 term1=np.mean(np.abs(s-y))
 term2=np.sum((2*np.arange(1,n+1)-n-1)*s)/(n*n)
 return float(term1-term2)
def cell_metrics(rows,y_key='target_rul_weeks'):
 by={}
 for r in rows:by.setdefault(r['cell_id'],[]).append(r)
 out={}
 for c,rs in by.items():
  y=np.asarray([r[y_key] for r in rs],float);m=np.asarray([r['rul_q50'] for r in rs],float)
  t90=np.asarray([r['rul_q90'] for r in rs],float);t10=np.asarray([r['rul_q10'] for r in rs],float)
  lower=np.asarray([r['rul_q10'] for r in rs],float);upper=np.asarray([r['rul_q90'] for r in rs],float)
  alpha=0.20;is80=float(np.mean((upper-lower)+(2/alpha)*np.maximum(lower-y,0)+(2/alpha)*np.maximum(y-upper,0)))
  out[c]={'n':len(rs),'mae':float(np.mean(np.abs(m-y))),'rmse':float(np.sqrt(np.mean((m-y)**2))),'is80':is80,
          'pin10':pinball(y,t10,.10),'pin50':pinball(y,m,.50),'pin90':pinball(y,t90,.90),
          'cov80':float(np.mean((y>=t10)&(y<=t90))),'cov_dist':float(abs(np.mean((y>=t10)&(y<=t90))-.80)),
          'severe4w':float(np.mean(np.abs(m-y)>4.0)),'severe8w':float(np.mean(np.abs(m-y)>8.0)),
          'width80':float(np.mean(t90-t10))}
 return out
def agg(rows):
 pc=cell_metrics(rows);cs=sorted(pc)
 if not cs:return {'n_queries':0,'n_cells':0}
 return {'n_queries':sum(pc[c]['n'] for c in cs),'n_cells':len(cs),
  'cell_MAE_weeks':float(np.mean([pc[c]['mae'] for c in cs])),
  'cell_RMSE_weeks':float(np.sqrt(np.mean([pc[c]['rmse']**2 for c in cs]))),
  'cell_pinball10':float(np.mean([pc[c]['pin10'] for c in cs])),
  'cell_pinball50':float(np.mean([pc[c]['pin50'] for c in cs])),
  'cell_pinball90':float(np.mean([pc[c]['pin90'] for c in cs])),
  'cell_cov80':float(np.mean([pc[c]['cov80'] for c in cs])),
  'cell_abs_cov80_from_80pct':float(np.mean([pc[c]['cov_dist'] for c in cs])),
  'cell_severe_gt4w':float(np.mean([pc[c]['severe4w'] for c in cs])),
  'cell_severe_gt8w':float(np.mean([pc[c]['severe8w'] for c in cs])),
  'cell_interval_score80':float(np.mean([pc[c]['is80'] for c in cs])),
  'cell_mean_width80_weeks':float(np.mean([pc[c]['width80'] for c in cs]))}
def bootstrap(a_rows,b_rows,field='mae',nboot=5000,seed=42):
 pa=cell_metrics(a_rows);pb=cell_metrics(b_rows)
 common=sorted(set(pa)&set(pb))
 if not common:return {'n_cells':0,'mean_delta':None,'ci95_low':None,'ci95_high':None}
 a=np.asarray([pa[c][field] for c in common]);b=np.asarray([pb[c][field] for c in common])
 d=a-b;rng=np.random.default_rng(seed);idx=rng.integers(0,len(common),size=(nboot,len(common)))
 z=d[idx].mean(axis=1)
 return {'n_cells':len(common),'mean_delta':float(d.mean()),'ci95_low':float(np.quantile(z,.025)),'ci95_high':float(np.quantile(z,.975))}
def run(go_path):
 t0=time.time();out=None;receipt=None
 r={'status':'PREFLIGHT_FAILED','fit_count':0,'raw_payload_reads':0,'model_weight_reads':0,'C4_reads':0}
 try:
  go=json.loads(pathlib.Path(go_path).read_text(encoding='utf-8'))
  req=('status','allow_read_only_postprocess','request_id','owner_thread_id','issued_utc','source_sha256','inputs','output_path','receipt_path','bootstrap_replicates')
  if any(k not in go for k in req):raise ValueError('GO missing required field')
  if go['status']!='APPROVED' or go['allow_read_only_postprocess'] is not True or go['owner_thread_id']!=OWNER:raise ValueError('GO not approved/owner mismatch')
  if go['source_sha256']!=source_map():raise ValueError('source hash mismatch')
  if json.loads(pathlib.Path(go_path).read_text(encoding='utf-8'))!=go:raise ValueError('GO changed')
  for n,p in go['inputs'].items():
   if not pathlib.Path(p).is_file() or sha(p)!=go['input_sha256'][n]:raise ValueError('input missing/hash mismatch '+n)
  out=pathlib.Path(go['output_path']);receipt=pathlib.Path(go['receipt_path'])
  if out.exists() or receipt.exists():raise ValueError('output/receipt path not fresh')
  rows=list(csv.DictReader(open(go['inputs']['b2_predictions'],encoding='utf-8')))
  comp=list(csv.DictReader(open(go['inputs']['comparator_predictions'],encoding='utf-8')))
  samples=np.load(go['inputs']['b2_samples'],allow_pickle=False)
  r.update(status='RUNNING',n_b2_rows=len(rows),n_comparator_rows=len(comp))
  keep=[x for x in rows if x['condition']=='main' and x['censored_no_event_observed']=='False' and x['event_known_by_query']=='False']
  for x in keep:
   x['target_rul_weeks']=float(x['target_rul_weeks']);x['rul_q50']=float(x['rul_q50'])
   x['rul_q10']=float(x['rul_q10']);x['rul_q90']=float(x['rul_q90'])
   x['query_epoch_r']=int(round(float(x['query_epoch'])))
  compm={}
  for c in comp:
   if str(c.get('model'))!='full':      # the comparator file also holds an 'independent' ablation
    continue                          # which must never overwrite the full mechanism model
   try:
    k=(c['cell_id'],c['arm'],int(round(float(c['query_epoch']))))
    compm[k]={'mean':float(c['rul_restricted_mean_128w']),'q10':float(c['rul_q10_128w']),
              'q50':float(c['rul_q50_128w']),'q90':float(c['rul_q90_128w']),
              'target':float(c['target_rul_weeks'])}
   except Exception:continue
  matched=[];unmatched=0
  for x in keep:
   c=compm.get((x['cell_id'],x['arm'],x['query_epoch_r']))
   if c is None:unmatched+=1;continue
   if abs(c['target']-x['target_rul_weeks'])>1e-6:
    raise ValueError(f'comparator target mismatch at {x["cell_id"]}/{x["arm"]}/{x["query_epoch_r"]}: {c["target"]} vs {x["target_rul_weeks"]}')
   matched.append({'cell_id':x['cell_id'],'arm':x['arm'],'model':x['model'],'query_epoch':x['query_epoch_r'],
                   'target_rul_weeks':x['target_rul_weeks'],'rul_q10':x['rul_q10'],'rul_q50':x['rul_q50'],'rul_q90':x['rul_q90'],
                   'rul_mean':float(x['rul_mean']),'tail':float(x['tail_gt_128w_mass']),'query_id':x['query_id'],
                   'comp_q50':c['q50'],'comp_q10':c['q10'],'comp_q90':c['q90'],'comp_mean':c['mean']})
  if not matched:raise ValueError('no matched B2/comparator queries')
  res={'status':'SUCCESS','matched_queries':len(matched),'unmatched_b2_queries':unmatched,
       'fit_count':0,'raw_payload_reads':0,'model_weight_reads':0,'C4_reads':0}
  by_model={}
  for m in sorted({x['model'] for x in matched}):by_model[m]=agg([x for x in matched if x['model']==m])
  _seen=set();comp_rows=[]
  for x in matched:
   k=(x['cell_id'],x['arm'],x['query_epoch'])
   if k in _seen:continue
   _seen.add(k)
   comp_rows.append({'cell_id':x['cell_id'],'arm':x['arm'],'target_rul_weeks':x['target_rul_weeks'],
                     'rul_q10':x['comp_q10'],'rul_q50':x['comp_q50'],'rul_q90':x['comp_q90']})
  res['b2_by_model']=by_model
  res['comparator_same_queries']=agg(comp_rows)
  res['comparator_same_queries_by_arm']={a:agg([x for x in comp_rows if x['arm']==a]) for a in sorted({x['arm'] for x in comp_rows})}
  res['b2_by_arm_model']={}
  for m in sorted({x['model'] for x in matched}):
   for a in sorted({x['arm'] for x in matched}):
    sub=[x for x in matched if x['model']==m and x['arm']==a]
    if sub:res['b2_by_arm_model'][f'{m}|{a}']=agg(sub)
  # paired bootstrap: B2 median vs comparator median, per model
  pair=[]
  for m in sorted({x['model'] for x in matched}):
   b2=[{'cell_id':x['cell_id'],'target_rul_weeks':x['target_rul_weeks'],'rul_q10':x['rul_q10'],'rul_q50':x['rul_q50'],'rul_q90':x['rul_q90']} for x in matched if x['model']==m]
   cp=[{'cell_id':x['cell_id'],'target_rul_weeks':x['target_rul_weeks'],'rul_q10':x['comp_q10'],'rul_q50':x['comp_q50'],'rul_q90':x['comp_q90']} for x in matched if x['model']==m]
   for f in ('mae','pin50','pin90','cov_dist','severe4w'):
    pair.append({'model':m,'metric':f,**bootstrap(b2,cp,f,int(go['bootstrap_replicates']))})
  res['paired_bootstrap']=pair
  # strata by target horizon
  bins=[('0-4w',lambda y:y<=4),('4-12w',lambda y:4<y<=12),('12-32w',lambda y:12<y<=32),('32w+',lambda y:y>32)]
  strata=[]
  for name,fn in bins:
   for m in sorted({x['model'] for x in matched}):
    sub=[x for x in matched if x['model']==m and fn(x['target_rul_weeks'])]
    if sub:strata.append({'stratum':name,'model':m,**agg(sub)})
   subc=[x for x in comp_rows if fn(x['target_rul_weeks'])]
   if subc:strata.append({'stratum':name,'model':'comparator',**agg(subc)})
  res['strata_target_horizon']=strata
  # --- predeclared contrasts: joint dependence and trajectory constraint ---
  # All contrasts are paired on the exact same (cell, arm, query) key and use the same
  # 256-sample trajectory engine; only the named factor differs.
  keyed={}
  for x in rows:
   if x['censored_no_event_observed']!='False' or x['event_known_by_query']!='False':continue
   k=(x['cell_id'],x['arm'],int(round(float(x['query_epoch']))),x['model'],x['condition'])
   keyed[k]={'target':float(x['target_rul_weeks']),'q50':float(x['rul_q50']),'q10':float(x['rul_q10']),'q90':float(x['rul_q90'])}
  contrasts=[]
  # explicit paired contrasts
  def paired(model_a,cond_a,model_b,cond_b,label):
   a=[];b=[]
   for (cid,arm,q,model,cond),v in keyed.items():
    if model!=model_a or cond!=cond_a:continue
    w=keyed.get((cid,arm,q,model_b,cond_b))
    if w is None:continue
    a.append({'cell_id':cid,'arm':arm,'target_rul_weeks':v['target'],'rul_q10':v['q10'],'rul_q50':v['q50'],'rul_q90':v['q90']})
    b.append({'cell_id':cid,'arm':arm,'target_rul_weeks':v['target'],'rul_q10':w['q10'],'rul_q50':w['q50'],'rul_q90':w['q90']})
   if not a:return None
   rec={'contrast':label,'n_queries':len(a),'A':agg(a),'B':agg(b)}
   for f in ('mae','pin50','pin90','cov_dist','severe4w'):
    rec[f+'_delta_A_minus_B']=bootstrap(a,b,f,int(go['bootstrap_replicates']))
   return rec
  for lab,ma,ca,mb,cb in [
    ('joint_vs_independent','joint','main','independent','main'),
    ('trajectory_constraint_on_vs_off','joint','main','joint','condition_off'),
    ('fixed_gap_vs_free_gap','joint','fixed_gap','joint','main')]:
   rec=paired(ma,ca,mb,cb,lab)
   if rec:contrasts.append(rec)
  res['predeclared_contrasts']=contrasts
  # tail mass vs censoring diagnostics (no clipping)
  res['tail_mass_mean']={m:float(np.mean([x['tail'] for x in matched if x['model']==m])) for m in sorted({x['model'] for x in matched})}
  out.mkdir(parents=True,exist_ok=False)
  def wr(name,rows_):
   if not rows_:return
   with (out/name).open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(rows_[0]));w.writeheader();w.writerows(rows_)
  wr('metrics_b2_by_model.csv',[{'model':m,**v} for m,v in res['b2_by_model'].items()])
  wr('metrics_comparator_same_queries.csv',[{'scope':'same_queries',**res['comparator_same_queries']}]+
     [{'scope':'arm:'+a,**v} for a,v in res['comparator_same_queries_by_arm'].items()])
  wr('metrics_b2_by_arm.csv',[{'key':k,**v} for k,v in res['b2_by_arm_model'].items()])
  wr('paired_bootstrap.csv',pair)
  wr('strata_target_horizon.csv',strata)
  atomicj(out/'summary.json',res);r.update(status='SUCCESS',summary=res,elapsed_seconds=time.time()-t0)
 except BaseException as e:
  r.update(status='FAILED',error=repr(e),traceback=__import__('traceback').format_exc())
 finally:
  if out and out.exists():atomicj(out/'receipt.json',r)
  if receipt:
   receipt.parent.mkdir(parents=True,exist_ok=True)
   with receipt.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,ensure_ascii=False,allow_nan=True)
 print(json.dumps({k:v for k,v in r.items() if k!='summary'},indent=2)[:1500]);return r
def source_map():
 return {str(pathlib.Path(__file__).resolve().relative_to(ROOT)):sha(__file__)}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--go',required=True);args=ap.parse_args();z=run(args.go);sys.exit(0 if z['status']=='SUCCESS' else 2)
