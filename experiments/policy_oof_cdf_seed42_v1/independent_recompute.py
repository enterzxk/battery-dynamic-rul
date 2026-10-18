from pathlib import Path
import json,csv,math,statistics,bisect,hashlib
from fractions import Fraction
from collections import Counter
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent
p=json.loads((O/'protocol.json').read_text());co=json.loads((O/'cohort.json').read_text());oo=list(csv.DictReader((O/'oof_predictions.csv').open()));assert len(oo)==22281
counts=Counter(r['cell_id'] for r in oo);assert len(counts)==42 and set(counts)=={c for c,role in co['roles'].items() if role=='fit'}
keys={(r['cell_id'],int(r['origin'])) for r in oo};assert len(keys)==22281
ledger=[json.loads(x) for x in (O/'fit_ledger.jsonl').read_text().splitlines()];starts=[x for x in ledger if x['event']=='fit_started'];assert len(starts)==3
for f in starts:
 assert not set(f['train_cells'])&set(f['held_cells']) and len(f['held_cells'])==14 and len(f['train_cells'])==28
 assert set(f['held_cells'])==set(p['fold_cells'][f['number']])
for r in oo:assert r['cell_id'] in p['fold_cells'][int(r['fold'])]
raw=sorted((math.log(float(r['true_RUL']))-float(r['oof_mu_log_RUL']),Fraction(1,42*counts[r['cell_id']])) for r in oo)
acc=Fraction();quant={};prefix=[]
for v,w in raw:
 acc+=w;prefix.append(acc)
 for q in [Fraction(1,10),Fraction(1,2),Fraction(9,10)]:
  if q not in quant and acc>=q:quant[q]=v
assert acc==1;center=quant[Fraction(1,2)];support=[v-center for v,w in raw];offset=[quant[q]-center for q in [Fraction(1,10),Fraction(1,2),Fraction(9,10)]]
rows=list(csv.DictReader((O/'calibration_distribution.csv').open()));source=list(csv.DictReader((R/'experiments/policy_context_point_seed42_v1/calibration_predictions.csv').open()));assert len(rows)==len(source)==4567
sig=json.loads((R/'experiments/matr_raw_heldout_calibration_seed42_v1/fit_parameters.json').read_text())['sigmas']['A_fit_residual_scale'];norm=statistics.NormalDist();values={};maxdiff=0.;cross=0
for r,s in zip(rows,source):
 assert (r['cell_id'],r['origin'],r['true_RUL'])==(s['cell_id'],s['origin'],s['true_RUL']) and float(r['saved_mu'])==float(s['context_RUL_raw_log'])
 cid=r['cell_id'];mu=float(r['saved_mu']);y=float(r['true_RUL']);med=math.exp(mu);l=math.exp(mu+offset[0]);h=math.exp(mu+offset[2]);risks={}
 for z in [100,300]:
  ix=bisect.bisect_right(support,math.log(z)-mu);risks[z]=float(prefix[ix-1]) if ix else 0.
 for k,v in dict(q10=l,q50=med,q90=h,risk100=risks[100],risk300=risks[300]).items():maxdiff=max(maxdiff,abs(float(r[k])-v))
 assert 0<l<med<h;cross+=not (float(r['q10'])<float(r['q50'])<float(r['q90']))
 for arm,lo,hi,rs in [('saved_fixed_sigma',math.exp(mu+sig*norm.inv_cdf(.1)),math.exp(mu+sig*norm.inv_cdf(.9)),{z:norm.cdf((math.log(z)-mu)/sig) for z in [100,300]}),('cell_OOF_empirical_CDF',l,h,risks)]:
  v=dict(MAE=abs(med-y),coverage80=lo<=y<=hi,width80=hi-lo,interval_score80=hi-lo+10*max(lo-y,0)+10*max(y-hi,0),Brier100=(rs[100]-(y<=100))**2,Brier300=(rs[300]-(y<=300))**2)
  values.setdefault((cid,arm),[]).append(v)
pc=[]
for (cid,arm),vv in sorted(values.items()):
 v=dict(cell_id=cid,arm=arm,**{k:statistics.mean(x[k] for x in vv) for k in vv[0]});v['absolute_coverage_error80']=abs(v['coverage80']-.8);pc.append(v)
met={arm:{k:statistics.mean(r[k] for r in pc if r['arm']==arm) for k in pc[0] if k not in ['cell_id','arm']} for arm in ['saved_fixed_sigma','cell_OOF_empirical_CDF']}
ref=json.loads((O/'metrics.json').read_text());md=max(abs(v-ref[a][k]) for a,m in met.items() for k,v in m.items());assert md<1e-9 and maxdiff<1e-9 and cross==0
out=dict(status='PASS_INDEPENDENT_OOF_CDF_ALL4567_METRICS',OOF_rows=22281,OOF_cells=42,folds=3,cell_exclusion_verified=True,rows=4567,cells=10,maximum_prediction_difference=maxdiff,maximum_metric_difference=md,zero_crossings=True,metrics=met,median_center=center,quantile_offsets=offset,new_fits=0,new_model_inference=0)
with (O/'independent_metrics.json').open('x') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in out.items() if k!='metrics'}))
