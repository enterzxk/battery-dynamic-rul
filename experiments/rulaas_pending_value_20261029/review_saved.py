#!/usr/bin/env python3
"""Independently recompute saved pending-information comparisons and timing."""
import pathlib,csv,json,collections,hashlib
import numpy as np
R=pathlib.Path('/home/yndx/zxk/rul');D=R/'experiments/rulaas_pending_value_20261029/run01'
def rows(p):
 with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
cases=rows(D/'cases.csv');pts=rows(D/'counterfactual_points.csv');summary=read(D/'summary.json');receipt=read(D/'receipt.json');per=rows(D/'per_cell.csv')
assert receipt['status']=='SUCCESS' and receipt['new_fits']==0 and receipt['C3_payload_reads']==receipt['C4_payload_reads']==0 and len(cases)==184 and len(pts)==1472
byid=collections.defaultdict(list)
for p in pts:byid[int(p['case_id'])].append(p)
check_new_before_arrival=check_old_before_arrival=check_no_pending=0;maxerr=0.;cell=collections.defaultdict(list)
for i,c in enumerate(cases):
 assert int(c['case_id'])==i and len(byid[i])==8
 t=float(c['request_epoch']);event=float(c['label_source_event_epoch']);stop=float(c['label_candidate_stop_epoch']);pending=int(c['input_pending_count'])
 assert (c['label_request_before_event']=='True')==(t<event)
 assert (c['input_stale_above_original_training_max']=='True')==(float(c['input_staleness_weeks'])>3.426952600479126)
 a=b=0.;alive=0
 for k,p in enumerate(sorted(byid[i],key=lambda x:int(x['slot'])),1):
  q=t+k*.5*604800.;assert float(p['query_epoch'])==q and int(p['slot'])==k and p['cell_id']==c['cell_id'] and p['population']==c['population'] and p['source_rpt_index']==c['source_rpt_index']
  if q<event:
   assert p['pre_reference_event']=='True';y=(event-q)/604800.;assert abs(float(p['true_RUL'])-y)<1e-10
   n=float(p['natural_no_candidate']);nc=float(p['natural_candidate']);s=float(p['suppress_pending_no_candidate']);sc=float(p['suppress_pending_candidate'])
   if q<stop+14*86400.:assert n==nc and s==sc;check_new_before_arrival+=1
   if pending==0:assert n==s and nc==sc;check_no_pending+=1
   elif q<t+float(c['input_next_pending_arrival_days'])*86400.-1e-6:assert n==s and nc==sc;check_old_before_arrival+=1
   ga=abs(n-y)-abs(nc-y);gb=abs(s-y)-abs(sc-y);alive+=1
   assert abs(ga-float(p['gain_pending_arrives']))<1e-10 and abs(gb-float(p['gain_suppress_pending']))<1e-10
  else:
   assert p['pre_reference_event']=='False' and all(not p[k] for k in ['natural_no_candidate','natural_candidate','suppress_pending_no_candidate','suppress_pending_candidate']) and float(p['gain_pending_arrives'])==float(p['gain_suppress_pending'])==0.
   ga=gb=0.
  a+=ga/8.;b+=gb/8.
 assert alive==int(c['label_pre_event_slots'])
 err=max(abs(a-float(c['label_gain_pending_arrives'])),abs(b-float(c['label_gain_suppress_pending'])),abs((b-a)-float(c['label_difference_suppressed_minus_natural'])));maxerr=max(maxerr,err);assert err<1e-10
 if pending:cell[(c['population'],c['cell_id'])].append((a,b))
out=[]
for s in summary['populations']:
 pop=s['population'];pairs={cid:v for (p,cid),v in cell.items() if p==pop};cells=sorted(pairs);groups=sorted({z.rsplit('C',1)[0] for z in cells})
 diff={cid:float(np.mean([b-a for a,b in pairs[cid]])) for cid in cells}
 val=float(np.mean(list(diff.values())));assert abs(val-s['difference_cell_macro_weeks'])<1e-10
 sums=np.asarray([sum(diff[c] for c in cells if c.rsplit('C',1)[0]==g) for g in groups]);counts=np.asarray([sum(c.rsplit('C',1)[0]==g for c in cells) for g in groups]);rng=np.random.RandomState(42);idx=rng.randint(len(groups),size=(5000,len(groups)));boot=sums[idx].sum(axis=1)/counts[idx].sum(axis=1);ci=[float(np.quantile(boot,.025)),float(np.quantile(boot,.975))]
 assert np.allclose(ci,s['group_bootstrap_95_CI'],rtol=0,atol=1e-10)
 for c in cells:
  row=next(z for z in per if z['population']==pop and z['cell_id']==c);assert abs(float(row['difference'])-diff[c])<1e-10
 out.append(dict(population=pop,n_pending_cases=sum(len(x) for x in pairs.values()),n_cells=len(cells),n_groups=len(groups),difference_cell_macro_weeks=val,group_bootstrap_95_CI=ci))
result=dict(status='PASS',new_fits=0,new_inference_rows=0,C3_payload_reads=0,C4_payload_reads=0,cases_checked=len(cases),slot_checks=len(pts),candidate_pre_arrival_checks=check_new_before_arrival,existing_pending_pre_arrival_checks=check_old_before_arrival,no_pending_identity_checks=check_no_pending,max_label_recomputation_error=maxerr,population_recomputations=out,limits=['Fixed 14-day delay is hypothetical.','Suppressed prior reports are an analytic information comparison, not a feasible matched-cost queue policy.','0 post-event time utility is not complete failure-detection reward.','Historical C1/C2 cells and a conditional RUL point proxy are not independent service confirmation.'],input_sha256={str(p.relative_to(R)):sha(p) for p in [D/'cases.csv',D/'counterfactual_points.csv',D/'summary.json',D/'per_cell.csv',D/'receipt.json']})
with (D/'INDEPENDENT_RECOMPUTE.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps(result,ensure_ascii=False))
