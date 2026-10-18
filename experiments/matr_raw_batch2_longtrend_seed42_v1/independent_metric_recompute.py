from pathlib import Path
import csv,json,math,hashlib,collections
R=Path('/home/yndx/zxk/rul');O=R/'experiments/matr_raw_batch2_longtrend_seed42_v1'
mean=lambda a:sum(a)/len(a)
groups=collections.defaultdict(list);seen=set()
manifest=json.loads((R/'data/processed/data_v1_matr_raw_batch2/manifest.json').read_text());val={c['cell_id']:c for c in manifest['cells'] if c['role']=='val'}
for r in csv.DictReader((O/'development_predictions.csv').open()):
 cid=r['cell_id'];arm=r['arm'];t=int(r['origin']);assert cid in val
 key=(cid,arm,t);assert key not in seen;seen.add(key)
 truth=float(r['true_RUL']);assert truth==val[cid]['event_cycle']-t and int(r['event_cycle'])==val[cid]['event_cycle']
 q10,p,q90=[float(r[k]) for k in ['q10','median_RUL','q90']];p100,p300=[float(r[k]) for k in ['risk100','risk300']]
 assert all(math.isfinite(v) for v in [q10,p,q90,p100,p300]) and 0<q10<=p<=q90 and 0<=p100<=p300<=1
 groups[cid,arm].append((t,truth,q10,p,q90,p100,p300))
cells=[];arms=['A_robust_linear','B_robust_nonlinear','C_add_long_rate']
for cid,c in sorted(val.items()):
 expected=set(range(100,c['event_cycle']))
 for arm in arms:
  rr=groups[cid,arm];assert {r[0] for r in rr}==expected and len(rr)==c['prefix_count']
  e=[r[3]-r[1] for r in rr]
  cells.append({'cell_id':cid,'arm':arm,'MAE':mean([abs(x) for x in e]),'bias':mean(e),'severe_over100':mean([float(x>100) for x in e]),'coverage80':mean([float(r[2]<=r[1]<=r[4]) for r in rr]),'width80':mean([r[4]-r[2] for r in rr]),'Brier100':mean([(r[5]-float(r[1]<=100))**2 for r in rr]),'Brier300':mean([(r[6]-float(r[1]<=300))**2 for r in rr])})
metrics={a:{k:mean([r[k] for r in cells if r['arm']==a]) for k in cells[0] if k not in ['cell_id','arm']} for a in arms}
reported=json.loads((O/'metrics.json').read_text());diff=max(abs(metrics[a][k]-reported[a][k]) for a in arms for k in metrics[a]);assert diff<1e-9
out={'status':'PASS_INDEPENDENT_CSV_RECOMPUTE','prediction_rows':len(seen),'cells':9,'arms':3,'metrics':metrics,'maximum_absolute_difference':diff,'prediction_sha256':hashlib.sha256((O/'development_predictions.csv').read_bytes()).hexdigest(),'new_fits':0,'optimizer_steps':0,'test_cell_reads':0}
with (O/'independent_metrics.json').open('x') as f:json.dump(out,f,indent=2)
print(json.dumps(out))
