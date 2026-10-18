from pathlib import Path
import json,csv,math,statistics
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent;p=json.loads((O/'protocol.json').read_text());rows=list(csv.DictReader((R/p['source']).open()));ids=sorted({x['cell_id'] for x in rows});acc={a:[] for a in ['fixed_origin100_countdown','dynamic_each_origin']};expire=0;harm=[]
for cid in ids:
 rr=sorted([r for r in rows if r['cell_id']==cid],key=lambda r:int(r['origin']));anchor=math.exp(float(rr[0]['context_RUL_raw_log']));assert int(rr[0]['origin'])==100;prev=None;hc=0
 for arm in acc:
  errors=[]
  for r in rr:
   d=int(r['origin'])-100;y=float(r['true_RUL']);z=max(0.,anchor-d) if arm.startswith('fixed') else math.exp(float(r['context_RUL_raw_log']));errors.append(z-y)
   if arm.startswith('fixed'):expire+=z==0
  acc[arm].append(dict(MAE=statistics.mean(abs(e) for e in errors),bias=statistics.mean(errors),severe_over100=statistics.mean(e>100 for e in errors)))
 for r in rr:
  t=int(r['origin']);z=math.exp(float(r['context_RUL_raw_log']));y=float(r['true_RUL'])
  if prev is not None:hc+=abs(max(0.,prev[1]-(t-prev[0]))-y)-abs(z-y)<-1e-12
  prev=(t,z)
 harm.append(hc/(len(rr)-1))
met={a:{k:statistics.mean(r[k] for r in vv) for k in vv[0]} for a,vv in acc.items()};ref=json.loads((O/'metrics.json').read_text());diff=max(abs(met[a][k]-ref[a][k]) for a in ref for k in ref[a]);assert diff<1e-10 and expire==647;tr=json.loads((O/'transition_audit.json').read_text());assert abs(statistics.mean(harm)-tr['cell_equal']['harmful_fraction'])<1e-12
out=dict(status='PASS_INDEPENDENT_ALL_ORIGIN_ARITHMETIC',rows=len(rows),metrics=met,max_absolute_metric_difference=diff,fixed_expired_origins=expire,harmful_transition_cell_equal=statistics.mean(harm),new_fits=0,new_model_inference=0)
with (O/'independent_metrics.json').open('x') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(out))
