from pathlib import Path
import json,csv,hashlib,math,time
import numpy as np
R=Path('/home/yndx/zxk/rul');O=R/'reports/policy_fixedearly_dynamic_20261018_root'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,x):
 with (O/n).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
def metric(e):return dict(MAE=float(np.abs(e).mean()),bias=float(e.mean()),severe_over100=float((e>100).mean()))
start=time.monotonic();p=json.loads((O/'protocol.json').read_text());sp=R/p['source'];assert sha(sp)==p['source_sha256'];rows=list(csv.DictReader(sp.open()));assert len(rows)==4567 and all(r['role']=='calibration' for r in rows)
ids=sorted({r['cell_id'] for r in rows});assert len(ids)==10;pc=[];trans=[];phase=[];examples=[];expired=0
for cid in ids:
 rr=sorted([r for r in rows if r['cell_id']==cid],key=lambda r:int(r['origin']));t=np.array([int(r['origin']) for r in rr]);y=np.array([float(r['true_RUL']) for r in rr]);z=np.exp([float(r['context_RUL_raw_log']) for r in rr]);assert t[0]==100 and np.all(np.diff(t)==1) and np.isfinite(z).all() and np.all(y>0) and np.all(y+t==int(rr[0]['event_cycle']))
 fixed=np.maximum(0,z[0]-(t-100));isexpired=fixed==0;expired+=int(isexpired.sum())
 for arm,pred in [('fixed_origin100_countdown',fixed),('dynamic_each_origin',z)]:pc.append(dict(cell_id=cid,arm=arm,origins=len(rr),**metric(pred-y),expired_count=int(isexpired.sum()) if arm=='fixed_origin100_countdown' else 0))
 carry=np.maximum(0,z[:-1]-np.diff(t));old=np.abs(carry-y[1:]);new=np.abs(z[1:]-y[1:]);gain=old-new;tol=1e-12;shift=z[1:]-carry
 trans.append(dict(cell_id=cid,transitions=len(gain),helpful_fraction=float((gain>tol).mean()),harmful_fraction=float((gain<-tol).mean()),tied_fraction=float((np.abs(gain)<=tol).mean()),mean_absolute_error_reduction_cycles=float(gain.mean()),mean_absolute_EOL_revision_cycles=float(abs(shift).mean()),expired_carried_forecast_count=int((carry==0).sum())))
 for name,mask in [('RUL_le100',y<=100),('RUL_100to300',(y>100)&(y<=300)),('RUL_gt300',y>300)]:
  if mask.any():
   for arm,pred in [('fixed_origin100_countdown',fixed),('dynamic_each_origin',z)]:phase.append(dict(cell_id=cid,phase=name,arm=arm,origins=int(mask.sum()),**metric(pred[mask]-y[mask])))
 for j in [0,len(rr)//2,len(rr)-1]:examples.append(dict(cell_id=cid,origin=int(t[j]),true_RUL=float(y[j]),anchor_RUL=float(z[0]),fixed_prediction=float(fixed[j]),dynamic_prediction=float(z[j])))
metrics={arm:{k:float(np.mean([r[k] for r in pc if r['arm']==arm])) for k in ['MAE','bias','severe_over100']} for arm in ['fixed_origin100_countdown','dynamic_each_origin']};u=np.array([r['MAE'] for r in pc if r['arm']=='fixed_origin100_countdown']);v=np.array([r['MAE'] for r in pc if r['arm']=='dynamic_each_origin']);bs=np.random.default_rng(42).integers(0,10,(2000,10));ci=np.quantile((u-v)[bs].mean(axis=1),[.025,.975]).tolist();cmp=dict(relative_MAE_reduction=1-metrics['dynamic_each_origin']['MAE']/metrics['fixed_origin100_countdown']['MAE'],cells_improved=int((v<u).sum()),pairedcell_MAE_difference_CI95=ci,severe_over100_increment=metrics['dynamic_each_origin']['severe_over100']-metrics['fixed_origin100_countdown']['severe_over100'],fixed_expired_origins_before_trueEOL=expired)
cmp['development_gate_pass']=bool(cmp['relative_MAE_reduction']>=.05 and cmp['cells_improved']>=7 and ci[0]>0 and cmp['severe_over100_increment']<=.01)
transition={k:float(np.mean([r[k] for r in trans])) for k in ['helpful_fraction','harmful_fraction','tied_fraction','mean_absolute_error_reduction_cycles','mean_absolute_EOL_revision_cycles']};summary=[]
for name in ['RUL_le100','RUL_100to300','RUL_gt300']:
 for arm in metrics:
  rs=[r for r in phase if r['phase']==name and r['arm']==arm];summary.append(dict(phase=name,arm=arm,cells=len(rs),origins=sum(r['origins'] for r in rs),**{k:float(np.mean([r[k] for r in rs])) for k in ['MAE','bias','severe_over100']}))
dump('metrics.json',metrics);dump('per_cell_metrics.json',pc);dump('comparison.json',cmp);dump('transition_audit.json',dict(cell_equal=transition,per_cell=trans,total_transitions=sum(r['transitions'] for r in trans)));dump('phase_metrics.json',dict(cell_equal=summary,per_cell=phase));dump('arithmetic_examples.json',examples);dump('completion.json',dict(status='COMPLETE_SAVED_PREDICTION_DIAGNOSTIC',new_fits=0,optimizer_steps=0,new_model_inference=0,checkpoint_loads=0,raw_feature_reads=0,development_reads=0,test_reads=0,source_sha256=sha(sp),protocol_sha256=sha(O/'protocol.json'),script_sha256=sha(Path(__file__)),rows=len(rows),cells=len(ids),elapsed_seconds=time.monotonic()-start));print(json.dumps(dict(metrics=metrics,comparison=cmp,transition=transition,phase=summary)))
