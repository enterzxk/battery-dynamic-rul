from pathlib import Path
import json,csv,hashlib,time,fcntl
import numpy as np
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,x):
 with (O/n).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
start=time.monotonic();p=json.loads((O/'protocol.json').read_text());sp=R/p['source'];assert sha(sp)==p['source_sha256'];rr=list(csv.DictReader(sp.open()));assert len(rr)==4567 and all(r['role']=='calibration' for r in rr);ids=sorted({r['cell_id'] for r in rr});assert len(ids)==10
lk=open(R/'automation/state/online_survival_cpu.lock','a');fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB);c=json.loads((R/'automation/state/coordinator.json').read_text());assert c['owner']=='01a14e92-ea7a-7cc3-8007-67b4d16a873a' and not c['new_fits_allowed'];pc=[];trans=[];examples=[];alpha=p['alpha']
with (O/'derived_predictions.csv').open('x',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['cell_id','origin','true_RUL','saved_RUL','EMA_absolute_EOL','EMA_RUL']);w.writeheader()
 for cid in ids:
  rows=sorted([r for r in rr if r['cell_id']==cid],key=lambda r:int(r['origin']));t=np.array([int(r['origin']) for r in rows]);z=np.array([float(r['context_RUL_prediction']) for r in rows]);y=np.array([float(r['true_RUL']) for r in rows]);assert t[0]==100 and np.all(np.diff(t)==1) and np.all(y+t==int(rows[0]['event_cycle']))
  E=t+z;sm=np.empty(len(E));sm[0]=E[0]
  for j in range(1,len(E)):sm[j]=(1-alpha)*sm[j-1]+alpha*E[j]
  pred=np.maximum(0,sm-t);assert np.isfinite(pred).all() and abs(pred[0]-z[0])<1e-10
  for arm,values in zip(p['arms'],[z,pred]):
   err=values-y;pc.append(dict(cell_id=cid,arm=arm,origins=len(y),MAE=float(abs(err).mean()),bias=float(err.mean()),severe_over100=float((err>100).mean()),expired_count=int((values==0).sum())))
   carry=np.maximum(0,values[:-1]-1);gain=abs(carry-y[1:])-abs(values[1:]-y[1:]);shift=values[1:]-carry
   trans.append(dict(cell_id=cid,arm=arm,transitions=len(gain),helpful_fraction=float((gain>1e-12).mean()),harmful_fraction=float((gain<-1e-12).mean()),tied_fraction=float((abs(gain)<=1e-12).mean()),mean_absolute_error_reduction_cycles=float(gain.mean()),mean_absolute_EOL_revision_cycles=float(abs(shift).mean()),mean_absolute_raw_EOL_step=float(abs(np.diff(E if arm==p['arms'][0] else sm)).mean()),mean_absolute_tracking_gap_to_current_model_EOL=0. if arm==p['arms'][0] else float(abs(sm-E).mean()),mean_signed_tracking_gap_to_current_model_EOL=0. if arm==p['arms'][0] else float((sm-E).mean())))
  for j in range(len(y)):
   rec=dict(cell_id=cid,origin=int(t[j]),true_RUL=float(y[j]),saved_RUL=float(z[j]),EMA_absolute_EOL=float(sm[j]),EMA_RUL=float(pred[j]));w.writerow(rec)
   if j in [0,len(y)//2,len(y)-1]:examples.append(rec)
metrics={a:{k:float(np.mean([r[k] for r in pc if r['arm']==a])) for k in ['MAE','bias','severe_over100']} for a in p['arms']};u=np.array([r['MAE'] for r in pc if r['arm']==p['arms'][0]]);v=np.array([r['MAE'] for r in pc if r['arm']==p['arms'][1]]);bs=np.random.default_rng(42).integers(0,10,(2000,10));ci=np.quantile((u-v)[bs].mean(axis=1),[.025,.975]).tolist();a,b=[metrics[x] for x in p['arms']];cmp=dict(relative_MAE_reduction=1-b['MAE']/a['MAE'],cells_improved=int((v<u).sum()),pairedcell_MAE_difference_CI95=ci,severe_over100_increment=b['severe_over100']-a['severe_over100'],EMA_expired_count=sum(r['expired_count'] for r in pc if r['arm']==p['arms'][1]));cmp['gate_pass']=bool(cmp['relative_MAE_reduction']>=.05 and cmp['cells_improved']>=7 and ci[0]>0 and cmp['severe_over100_increment']<=.01)
ks=[k for k in trans[0] if k not in ['cell_id','arm','transitions']];summary={arm:{k:float(np.mean([r[k] for r in trans if r['arm']==arm])) for k in ks} for arm in p['arms']}
dump('metrics.json',metrics);dump('per_cell_metrics.json',pc);dump('comparison.json',cmp);dump('transition_audit.json',dict(cell_equal=summary,per_cell=trans,transitions_per_arm=4557,theoretical_low_frequency_delay_cycles=9.5));dump('arithmetic_examples.json',examples);dump('completion.json',dict(status='COMPLETE_ONE_FIXED_CAUSAL_EMA20_DIAGNOSTIC',cells=10,rows=4567,new_fits=0,optimizer_steps=0,new_model_inference=0,new_scalar_estimates=0,checkpoint_loads=0,raw_feature_reads=0,dev_test_reads=0,source_sha256=sha(sp),script_sha256=sha(Path(__file__)),protocol_sha256=sha(O/'protocol.json'),derived_prediction_sha256=sha(O/'derived_predictions.csv'),elapsed_seconds=time.monotonic()-start));print(json.dumps(dict(metrics=metrics,comparison=cmp,transition=summary)))
