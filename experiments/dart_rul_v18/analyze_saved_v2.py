"""No model load: frozen-protocol development comparisons from saved CSVs."""
from pathlib import Path
import csv,json,collections,statistics,hashlib
import numpy as np
H=Path(__file__).resolve().parent
E=H/'evaluation_recovery_v1';O=H/'analysis_v2'
def avg(xs):return statistics.mean(xs)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,rs):
 with p.open('x',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
def run():
 assert json.loads((H/'evaluation_recovery_v1_receipt.json').read_text())['status']=='SUCCESS'
 O.mkdir(exist_ok=False);rows=[]
 for seed in [42,13,77]:
  for r in csv.DictReader((E/('seed'+str(seed))/'predictions.csv').open()):
   r['seed']=int(r['seed']);r['known_event']=r['known_event']=='True';r['y_event']=int(r['y_event'])
   for k in ['event_brier','mean_abs_error','median_abs_error','severe_gt4w','IS80','coverage80','Brier4','Brier12','p_event','bin_logscore','event_logloss']:
    r[k]=float(r[k]) if r[k]!='' else None
   rows.append(r)
 models=sorted({r['model'] for r in rows});by=collections.defaultdict(list)
 for r in rows:
  if r['arm'] in ['sparse2','delay7d'] and not r['known_event']:
   by[r['model'],r['seed'],r['cell_id']].append(r['event_brier'])
 cell={k:avg(v) for k,v in by.items()}
 primary={m:avg([v for (mm,s,c),v in cell.items() if mm==m]) for m in models}
 seeds={m:{s:avg([v for (mm,ss,c),v in cell.items() if mm==m and ss==s]) for s in [42,13,77]} for m in models}
 refs=['existing_hgb','hgb_fullwindow','hgb_hurdle'];ref=min(refs,key=lambda m:primary[m])
 summary=list(csv.DictReader((E/'arm_summary.csv').open()))
 metrics=['event_brier','mean_abs_error','median_abs_error','severe_gt4w','IS80','coverage80','Brier4','Brier12','ECE10','bin_logscore','event_logloss']
 tables=[]
 for m in models:
  for arm in ['raw','sparse2','delay7d']:
   for stratum in ['all','unconfirmed','hidden_event','known_event']:
    ss=[r for r in summary if r['model']==m and r['arm']==arm and r['stratum']==stratum]
    z={'model':m,'arm':arm,'stratum':stratum,'n_rows_per_seed':int(ss[0]['n_rows']),'n_cells':int(ss[0]['n_cells'])}
    for metric in metrics:
     vals=[float(r[metric]) for r in ss if r[metric]!=''];z[metric]=avg(vals) if vals else ''
    tables.append(z)
 write(O/'three_seed_arm_summary.csv',tables)
 cells=sorted({c for m,s,c in cell if m=='dart_joint'})
 comparisons=[];percell=[]
 rng=np.random.default_rng(42)
 for m in models:
  if m=='dart_joint':continue
  deltas=np.asarray([avg([cell['dart_joint',s,c]-cell[m,s,c] for s in [42,13,77]]) for c in cells])
  boot=deltas[rng.integers(0,len(deltas),(2000,len(deltas)))].mean(1)
  comparisons.append({'candidate':'dart_joint','reference':m,'mean_Brier_difference':float(deltas.mean()),'paired_cell_bootstrap_95_low':float(np.quantile(boot,.025)),'paired_cell_bootstrap_95_high':float(np.quantile(boot,.975)),'cells':len(cells),'bootstrap_seed':42,'rounds':2000,'seeds_averaged_within_cell':True})
  for c,d in zip(cells,deltas):percell.append({'reference':m,'cell_id':c,'candidate_minus_reference_Brier':float(d)})
 write(O/'paired_primary_differences.csv',percell)
 def tab(m,a,s='all'):return next(x for x in tables if x['model']==m and x['arm']==a and x['stratum']==s)
 gates={}
 for a in ['raw','sparse2','delay7d']:
  d=tab('dart_joint',a);b=tab(ref,a)
  gates[a]={'MAE_relative_change':d['mean_abs_error']/b['mean_abs_error']-1,'severe_fraction_change':d['severe_gt4w']-b['severe_gt4w']}
 gain=1-primary['dart_joint']/primary[ref]
 passgate=gain>=.05 and all(x['MAE_relative_change']<=.02 and x['severe_fraction_change']<=.01 for x in gates.values())
 # Descriptive sensitivity: equal arms rather than frozen pooled within-cell weighting.
 sensitivity={m:avg([tab(m,a,'unconfirmed')['event_brier'] for a in ['sparse2','delay7d']]) for m in models}
 inf={m:{a:{seed:sum(r['bin_logscore'] is not None and not np.isfinite(r['bin_logscore']) for r in rows if r['model']==m and r['arm']==a and r['seed']==seed) for seed in [42,13,77]} for a in ['raw','sparse2','delay7d']} for m in models}
 decision={'status':'DEVELOPMENT_GATE_PASS_NOT_CONFIRMATION' if passgate else 'NO_GAIN_DEVELOPMENT_GATE_FAILED','frozen_primary':'Within each cell and seed, pool unconfirmed sparse2+delay7d queries; cell equal; then seed mean','primary_Brier':primary,'primary_by_seed':seeds,'strongest_prespecified_simple_reference':ref,'relative_improvement':gain,'safeguards_by_arm':gates,'paired_comparisons':comparisons,'equal_arm_sensitivity_Brier':sensitivity,'infinite_bin_logscore_rows_by_seed':inf,'worst10_cells_vs_strongest':sorted([x for x in percell if x['reference']==ref],key=lambda x:x['candidate_minus_reference_Brier'],reverse=True)[:10],'C4_payload_reads':0,'new_fits':0,'new_inference_calls':0,'limits':['source-observed endpoint only, not latent physical EOL','development cohort previously exposed','three optimization seeds are not three independent cohorts','hidden-event dev queries sparse33/delay61; not dense hidden-event calibration','noT future targets masked; no independent censoring assumption','standard risk here neural query-discrete-hazard comparator, not full longitudinal-event generative joint model'],'input_sha256':{str(p.relative_to(H)):sha(p) for p in [H/'protocol.json',H/'evaluation_recovery_v1_receipt.json']+[E/('seed'+str(s))/'predictions.csv' for s in [42,13,77]]}}
 (O/'root_decision.json').write_text(json.dumps(decision,indent=2,allow_nan=True))
 print(json.dumps({'primary':primary,'strongest_reference':ref,'relative_improvement':gain,'safeguards':gates,'status':decision['status']},indent=2))
if __name__=='__main__':run()
