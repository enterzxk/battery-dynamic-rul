"""Saved distribution evaluation; label fields are never predictor inputs."""
from pathlib import Path
import csv,json,math,time,collections,statistics
import numpy as np
EDGES=np.asarray([0,.25,.5,1,2,3,4,6,8,12,16,24,32,48,64,96,128],float)
class PointZero:
 def cdf(self,t):
  a=np.asarray(t,float);z=(a>=0).astype(float);return float(z) if z.ndim==0 else z
 def mean(self):return 0.
 def quantile(self,p):return 0.
def metric_row(e,dist,seed,model,wall):
 vals=np.asarray(dist.cdf(EDGES),float);p=float(vals[0]);mu=float(dist.mean());med=float(dist.quantile(.5));lo=float(dist.quantile(.1));hi=float(dist.quantile(.9))
 if not np.all(np.isfinite(vals)) or not all(math.isfinite(x) for x in [mu,med,lo,hi]):raise FloatingPointError('nonfinite distribution')
 if vals.min() < -1e-10 or vals.max()>1+1e-10 or np.any(np.diff(vals)<-1e-10) or lo<0 or hi<lo or mu<0:raise ValueError('invalid CDF/quantile')
 y=int(e['y_event']);target=e['target_rul_weeks'];known=target is not None
 probs=np.r_[p,np.diff(vals),1-vals[-1]]
 if abs(probs.sum()-1)>1e-9:raise ValueError('mass normalization failure')
 logscore=''
 if known:
  mass=p if target==0 else (probs[1+min(len(EDGES)-1,int(np.searchsorted(EDGES,target,side='left'))-1)] if target<=EDGES[-1] else probs[-1])
  logscore=-math.log(mass) if mass>0 else float('inf')
 f4=float(dist.cdf(4.));f12=float(dist.cdf(12.))
 row={'seed':seed,'model':model,'cell_id':e['cell_id'],'arm':e['arm'],'query_epoch':e['query_epoch'],'arrival_anchor_epoch':e['last_arrival_epoch'],'delta_weeks':e['delta_weeks'],'history_key':e['history_key'],'known_event':bool(e['known_event']),'y_event':y,'target_rul_weeks':'' if target is None else target,'p_event':p,'F4':f4,'F12':f12,'Splus4':'' if p>=1 else (1-f4)/(1-p),'Splus12':'' if p>=1 else (1-f12)/(1-p),'mean_weeks':mu,'median_weeks':med,'q10':lo,'q90':hi,'event_brier':(p-y)**2,'event_logloss':(-math.log(p) if p>0 else float('inf')) if y else (-math.log1p(-p) if p<1 else float('inf')),'mean_abs_error':abs(mu-target) if known else '','median_abs_error':abs(med-target) if known else '','severe_gt4w':float(mu-target>4) if known else '','IS80':hi-lo+10*(max(lo-target,0)+max(target-hi,0)) if known else '','coverage80':float(lo<=target<=hi) if known else '','Brier4':(f4-float(target<=4))**2 if known else '','Brier12':(f12-float(target<=12))**2 if known else '','bin_logscore':logscore,'predict_wall_ms':wall}
 return row
def write_csv(path,rows):
 if not rows:return
 fields=list(dict.fromkeys(k for r in rows for k in r))
 with Path(path).open('x',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def evaluate_models(models,dev,seed,output,on_predict,reference_rows=None):
 rows=[]
 for name,predictor in models.items():
  for e in dev:
   on_predict();t=time.perf_counter();raw=predictor.predict(e);dist=PointZero() if e['known_event'] else raw
   row=metric_row(e,dist,seed,name,(time.perf_counter()-t)*1000);row['unclosed_p_event']=float(raw.cdf(0.));row['unclosed_mean_weeks']=float(raw.mean());rows.append(row)
 if reference_rows is not None:
  for r in reference_rows:rows.append(dict(r,seed=seed))
 write_csv(Path(output)/'predictions.csv',rows)
 return rows
def summarize(rows):
 groups=collections.defaultdict(list)
 for r in rows:groups[r['seed'],r['model'],r['arm']].append(r)
 summary=[];cells=[];reliability=[]
 metrics=['event_brier','event_logloss','mean_abs_error','median_abs_error','severe_gt4w','IS80','coverage80','Brier4','Brier12','bin_logscore']
 for key,rs in sorted(groups.items()):
  for stratum,select in [('all',lambda r:True),('unconfirmed',lambda r:not r['known_event']),('known_event',lambda r:r['known_event']),('hidden_event',lambda r:r['y_event']==1 and not r['known_event'])]:
   ss=[r for r in rs if select(r)];by=collections.defaultdict(list)
   for r in ss:by[r['cell_id']].append(r)
   entries=[]
   for cid,cr in sorted(by.items()):
    ce={'seed':key[0],'model':key[1],'arm':key[2],'stratum':stratum,'cell_id':cid,'n_queries':len(cr)}
    for m in metrics:
     v=[float(r[m]) for r in cr if r[m]!=''];ce[m]=statistics.mean(v) if v else ''
    cells.append(ce);entries.append(ce)
   s={'seed':key[0],'model':key[1],'arm':key[2],'stratum':stratum,'n_rows':len(ss),'n_cells':len(by)}
   for m in metrics:
    v=[float(x[m]) for x in entries if x[m]!=''];s[m]=statistics.mean(v) if v else '';s[m+'_infinite_cells']=sum(not math.isfinite(x) for x in v)
   # Fixed ten bins, each cell total weight one within this stratum.
   bins=[[] for _ in range(10)]
   for cid,cr in by.items():
    for r in cr:bins[min(9,int(r['p_event']*10))].append((r['p_event'],r['y_event'],1./len(cr)))
   ece=0.;tot=float(len(by))
   for i,b in enumerate(bins):
    w=sum(x[2] for x in b);pred=sum(x[0]*x[2] for x in b)/w if w else '';obs=sum(x[1]*x[2] for x in b)/w if w else ''
    reliability.append({'seed':key[0],'model':key[1],'arm':key[2],'stratum':stratum,'bin':i,'row_count':len(b),'cell_weight':w,'mean_predicted':pred,'observed_fraction':obs})
    if w:ece+=w/tot*abs(pred-obs)
   s['ECE10']=ece if tot else '';summary.append(s)
 return summary,cells,reliability
def temporal_consistency(models,dev,on_predict):
 # Only adjacent source queries with identical arrived history; no T based selection.
 group=collections.defaultdict(list)
 for e in dev:group[e['cell_id'],e['arm'],e['history_key']].append(e)
 out=[]
 for name,model in models.items():
  errs=[]
  for key,es in group.items():
   es=sorted(es,key=lambda e:e['query_epoch'])
   for a,b in zip(es,es[1:]):
    if a['known_event'] or b['known_event']:continue
    on_predict();da=model.predict(a);on_predict();db=model.predict(b);elapsed=(b['query_epoch']-a['query_epoch'])/604800.
    tau=np.asarray([0.,1.,4.,12.,32.]);err=float(np.max(np.abs(np.asarray(db.cdf(tau))-np.asarray(da.cdf(tau+elapsed)))))
    errs.append(err)
  out.append({'model':name,'no_new_report_pairs':len(errs),'max_CDF_transport_error':max(errs) if errs else None,'mean_CDF_transport_error':statistics.mean(errs) if errs else None})
 return out
