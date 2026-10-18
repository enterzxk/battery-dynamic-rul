from pathlib import Path
import json,csv,hashlib,time,fcntl
import numpy as np
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,x):
 with (O/n).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
p=json.loads((O/'protocol.json').read_text());start=time.monotonic();lk=open(R/'automation/state/online_survival_cpu.lock','a');fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB);c=json.loads((R/'automation/state/coordinator.json').read_text());assert c['owner']=='01a14e92-ea7a-7cc3-8007-67b4d16a873a' and not c['new_fits_allowed']
byrole={};ids={}
for role,key in [('fit','source_fit'),('calibration','source_cal')]:
 sp=R/p[key];assert sha(sp)==p[key+'_sha256'];rows=list(csv.DictReader(sp.open()));assert all(r['role']==role for r in rows);ids[role]=sorted({r['cell_id'] for r in rows});assert (len(rows),len(ids[role]))==((22281,42) if role=='fit' else (4567,10));tr=[]
 for cid in ids[role]:
  rr=sorted([r for r in rows if r['cell_id']==cid],key=lambda r:int(r['origin']));t=np.array([int(r['origin']) for r in rr]);z=np.exp([float(r['policy_mu_log_RUL']) for r in rr]) if role=='fit' else np.array([float(r['context_RUL_prediction']) for r in rr]);y=np.array([float(r['true_RUL']) for r in rr]);assert t[0]==100 and np.all(np.diff(t)==1) and np.all(t+y==int(rr[0]['event_cycle'])) and np.isfinite(z).all()
  D=np.diff(t+z);gain=abs(np.maximum(0,z[:-1]-1)-y[1:])-abs(z[1:]-y[1:])
  for j,(d,g) in enumerate(zip(D,gain)):tr.append(dict(cell_id=cid,origin=int(t[j+1]),revision=float(d),abs_revision=float(abs(d)),gain=float(g),harmful=bool(g<-1e-10),helpful=bool(g>1e-10),weight=1/(len(ids[role])*len(D))))
 byrole[role]=tr
assert not set(ids['fit'])&set(ids['calibration']);train=byrole['fit'];assert len(train)==22239 and len(byrole['calibration'])==4557
ordered=sorted(train,key=lambda r:r['abs_revision']);cum=0.;cutoff=None
for r in ordered:
 cum+=r['weight']
 if cum>=.9:cutoff=r['abs_revision'];break
assert cutoff is not None
# Freeze threshold file before any calibration outcome aggregation.
dump('train_cutoff.json',dict(cutoff=cutoff,quantile=.9,weighted_CDF_at_selected_order=cum,fit_cells=42,fit_transitions=22239,method=p['training_cutoff'],fit_prediction_sha256=p['source_fit_sha256'],no_calibration_labels_used=True))
pc=[];summaries={};examples=[]
for role,tr in byrole.items():
 for r in tr:r['size_bin']='large' if r['abs_revision']>cutoff+1e-10 else 'rest';r['direction']='positive' if r['revision']>1e-10 else ('negative' if r['revision']<-1e-10 else 'zero')
 for cid in ids[role]:
  cell=[r for r in tr if r['cell_id']==cid]
  for sb in ['all','large','rest']:
   for direction in ['all','positive','negative','zero']:
    group=[r for r in cell if (sb=='all' or r['size_bin']==sb) and (direction=='all' or r['direction']==direction)]
    if not group:continue
    pc.append(dict(role=role,cell_id=cid,size_bin=sb,direction=direction,transitions=len(group),harmful_fraction=float(np.mean([r['harmful'] for r in group])),helpful_fraction=float(np.mean([r['helpful'] for r in group])),mean_update_gain_cycles=float(np.mean([r['gain'] for r in group])),mean_abs_revision_cycles=float(np.mean([r['abs_revision'] for r in group]))))
 for sb in ['all','large','rest']:
  for direction in ['all','positive','negative','zero']:
   group=[r for r in pc if r['role']==role and r['size_bin']==sb and r['direction']==direction]
   if group:summaries[role+'_'+sb+'_'+direction]=dict(cells=len(group),transitions=sum(r['transitions'] for r in group),**{k:float(np.mean([r[k] for r in group])) for k in ['harmful_fraction','helpful_fraction','mean_update_gain_cycles','mean_abs_revision_cycles']})
 for r in sorted(tr,key=lambda r:r['abs_revision'],reverse=True)[:3]:examples.append(dict(role=role,**r))
paired=[]
for cid in ids['calibration']:
 a=[r for r in pc if r['role']=='calibration' and r['cell_id']==cid and r['direction']=='all'];a={r['size_bin']:r for r in a}
 if 'large' in a and 'rest' in a:paired.append(dict(cell_id=cid,harmful_large_minus_rest=a['large']['harmful_fraction']-a['rest']['harmful_fraction'],mean_gain_large=a['large']['mean_update_gain_cycles'],mean_gain_large_minus_rest=a['large']['mean_update_gain_cycles']-a['rest']['mean_update_gain_cycles'],large_transitions=a['large']['transitions'],rest_transitions=a['rest']['transitions']))
contrast=dict(matched_cells=len(paired),cell_equal_harmful_large_minus_rest=float(np.mean([r['harmful_large_minus_rest'] for r in paired])),cell_equal_large_mean_gain=float(np.mean([r['mean_gain_large'] for r in paired])),cell_equal_gain_large_minus_rest=float(np.mean([r['mean_gain_large_minus_rest'] for r in paired])),cells_negative_large_mean_gain=sum(r['mean_gain_large']<0 for r in paired));contrast['blind_large_suppression_support']=bool(len(paired)>=7 and contrast['cell_equal_harmful_large_minus_rest']>=.10 and contrast['cell_equal_large_mean_gain']<0 and contrast['cells_negative_large_mean_gain']>=7)
with (O/'transition_outcomes.csv').open('x',newline='') as f:
 fields=['role']+list(train[0]);w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
 for role,tr in byrole.items():w.writerows(dict(role=role,**r) for r in tr)
dump('summary.json',dict(cutoff=cutoff,cell_equal=summaries,paired_calibration_contrast=contrast));dump('per_cell_metrics.json',pc);dump('paired_calibration.json',paired);dump('examples.json',examples);dump('completion.json',dict(status='COMPLETE_TRAIN_FROZEN_REVISION_RELIABILITY_DIAGNOSIS',new_fits=0,optimizer_steps=0,new_model_inference=0,checkpoint_loads=0,new_train_only_quantile_cutpoints=1,dev_test_reads=0,fit_transitions=22239,calibration_transitions=4557,protocol_sha256=sha(O/'protocol.json'),script_sha256=sha(Path(__file__)),transition_csv_sha256=sha(O/'transition_outcomes.csv'),elapsed_seconds=time.monotonic()-start));print(json.dumps(dict(cutoff=cutoff,contrast=contrast,calibration={k:v for k,v in summaries.items() if k.startswith('calibration_')})))
