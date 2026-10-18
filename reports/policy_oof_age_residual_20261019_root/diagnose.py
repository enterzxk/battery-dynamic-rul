from pathlib import Path
import json,csv,hashlib,math,statistics,time,datetime,fcntl
from fractions import Fraction
from collections import defaultdict,Counter
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,x):
 with (O/n).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
def band(t):return '100_199' if t<200 else ('200_399' if t<400 else '400_plus')
def weighted_median(rows):
 counts=Counter(r['cell_id'] for r in rows);acc=Fraction()
 for r in sorted(rows,key=lambda r:r['reference_residual']):
  acc+=Fraction(1,len(counts)*counts[r['cell_id']])
  if acc>=Fraction(1,2):return r['reference_residual']
def summarize(rows):
 cells=defaultdict(list)
 for r in rows:cells[r['cell_id']].append(r)
 pc=[]
 for cid,v in sorted(cells.items()):
  pc.append(dict(cell_id=cid,rows=len(v),mean_raw_log_residual=statistics.mean(r['raw_residual'] for r in v),mean_reference_log_residual=statistics.mean(r['reference_residual'] for r in v),lower_miss=statistics.mean(r['lower_miss'] for r in v),upper_miss=statistics.mean(r['upper_miss'] for r in v),coverage80=statistics.mean(not(r['lower_miss'] or r['upper_miss']) for r in v)))
 return dict(rows=len(rows),cells=len(cells),mean_raw_log_residual=statistics.mean(r['mean_raw_log_residual'] for r in pc),mean_reference_log_residual=statistics.mean(r['mean_reference_log_residual'] for r in pc),median_reference_log_residual=weighted_median(rows),lower_miss=statistics.mean(r['lower_miss'] for r in pc),upper_miss=statistics.mean(r['upper_miss'] for r in pc),coverage80=statistics.mean(r['coverage80'] for r in pc)),pc
def main():
 start=time.monotonic();p=json.loads((O/'protocol.json').read_text());assert p['new_fits']==0 and p['age_boundaries']==[100,200,400] and p['owner']=='01a1508e-83e9-7232-a0e4-07606110b443'
 lock=open(R/'automation/state/online_survival_cpu.lock','a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 control=json.loads((R/'automation/state/coordinator.json').read_text());assert control['owner']==control['thread_id']==p['owner'] and not control['new_fits_allowed']
 with (O/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
 for name,item in p['sources'].items():assert sha(R/item['path'])==item['sha256']
 base=R/'experiments/policy_oof_cdf_seed42_v1';cdf=json.loads((base/'empirical_cdf.json').read_text());center=cdf['median_center'];low,zero,high=cdf['quantile_offsets'];assert low<zero==0<high
 allrows={}
 for role,n,muvar in [('OOF','oof_predictions.csv','oof_mu_log_RUL'),('calibration','calibration_distribution.csv','saved_mu')]:
  rr=list(csv.DictReader((base/n).open()));expected=22281 if role=='OOF' else 4567;assert len(rr)==expected
  rows=[]
  for r in rr:
   cid=r['cell_id'];t=int(r['origin']);y=float(r['true_RUL']);mu=float(r[muvar]);assert t>=100 and y>0
   raw=math.log(y)-mu;res=raw-center if role=='OOF' else raw
   rows.append(dict(cell_id=cid,origin=t,band=band(t),raw_residual=raw,reference_residual=res,lower_miss=res<low,upper_miss=res>high))
  assert len({(r['cell_id'],r['origin']) for r in rows})==expected;assert len({r['cell_id'] for r in rows})==(42 if role=='OOF' else 10)
  allrows[role]=rows
 summary={};percell=[];decomp={};common={}
 for role,rows in allrows.items():
  counts=Counter(r['cell_id'] for r in rows);ncell=len(counts);summary[role]={};decomp[role]={}
  for b in p['age_bands']:
   rr=[r for r in rows if r['band']==b];met,pc=summarize(rr);summary[role][b]=met;percell.extend(dict(r,role=role,band=b) for r in pc)
   mass=sum(Fraction(1,ncell*counts[r['cell_id']]) for r in rr);lm=sum(Fraction(int(r['lower_miss']),ncell*counts[r['cell_id']]) for r in rr);um=sum(Fraction(int(r['upper_miss']),ncell*counts[r['cell_id']]) for r in rr)
   decomp[role][b]=dict(population_weight=float(mass),lower_miss_contribution=float(lm),upper_miss_contribution=float(um),population_weighted_lower_miss_rate=float(lm/mass),population_weighted_upper_miss_rate=float(um/mass))
  assert sum(d['rows'] for d in summary[role].values())==len(rows)
  overall,_=summarize(rows);assert abs(sum(d['population_weight'] for d in decomp[role].values())-1)<1e-12
  assert abs(sum(d['lower_miss_contribution'] for d in decomp[role].values())-overall['lower_miss'])<1e-12
  assert abs(sum(d['upper_miss_contribution'] for d in decomp[role].values())-overall['upper_miss'])<1e-12
  decomp[role]['overall']=overall
  shared=set.intersection(*[{r['cell_id'] for r in rows if r['band']==b} for b in p['age_bands']]);stats={}
  for b in p['age_bands']:stats[b],_=summarize([r for r in rows if r['band']==b and r['cell_id'] in shared])
  differences=[]
  for cid in sorted(shared):
   a=next(r for r in percell if r['role']==role and r['cell_id']==cid and r['band']=='100_199');b=next(r for r in percell if r['role']==role and r['cell_id']==cid and r['band']=='400_plus')
   differences.append(dict(cell_id=cid,late_minus_early_mean_reference_log_residual=b['mean_reference_log_residual']-a['mean_reference_log_residual'],late_minus_early_lower_miss=b['lower_miss']-a['lower_miss'],late_minus_early_upper_miss=b['upper_miss']-a['upper_miss']))
  common[role]=dict(common_cells=len(shared),cell_ids=sorted(shared),bands=stats,cell_paired_differences=differences,mean_late_minus_early_reference_log_residual=statistics.mean(d['late_minus_early_mean_reference_log_residual'] for d in differences),mean_late_minus_early_lower_miss=statistics.mean(d['late_minus_early_lower_miss'] for d in differences),cells_lower_miss_increases=sum(d['late_minus_early_lower_miss']>0 for d in differences))
 # One targeted scalar example: fixed first calibration cell/ageband.
 v=[r for r in allrows['calibration'] if r['cell_id']=='MATR_b2c1' and r['band']=='100_199'];assert len(v)==48
 example=dict(cell_id='MATR_b2c1',band='100_199',rows=len(v),lower_miss_count=sum(r['lower_miss'] for r in v),upper_miss_count=sum(r['upper_miss'] for r in v))
 assert example['lower_miss_count']==44 and example['upper_miss_count']==0
 old=json.loads((base/'failure_description.json').read_text());assert abs(decomp['calibration']['overall']['lower_miss']-old['mean_cell_lower_miss'])<1e-12
 assert abs(decomp['calibration']['overall']['upper_miss']-old['mean_cell_upper_miss'])<1e-12
 dump('summary.json',summary);dump('per_cell_age_metrics.json',percell);dump('population_contribution.json',decomp);dump('common_cell_comparison.json',common);dump('minimal_validation.json',dict(status='PASS_COUNTS_EXACT_FRACTION_RECOMPOSITION_AND_ONE_SCALAR_CASE',example=example,OOF_rows=22281,cal_rows=4567,groups=6,raw_feature_reads=0,new_fits=0,new_model_inference=0,dev_test_reads=0))
 dump('completion.json',dict(status='COMPLETE_FROZEN_AGE_RESIDUAL_DIAGNOSTIC',new_fits=0,new_model_inference=0,checkpoint_loads=0,raw_feature_reads=0,dev_test_reads=0,new_scalar_calibration_estimates=0,protocol_sha256=sha(O/'protocol.json'),script_sha256=sha(Path(__file__)),elapsed_seconds=time.monotonic()-start))
 print(json.dumps(dict(summary=summary,common={k:{x:v[x] for x in ['common_cells','mean_late_minus_early_reference_log_residual','mean_late_minus_early_lower_miss','cells_lower_miss_increases']} for k,v in common.items()})))
if __name__=='__main__':main()
