from pathlib import Path
from fractions import Fraction
import csv,json,math,statistics,argparse,hashlib
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent;p=json.loads((O/'protocol.json').read_text());tt={};ids={};parser=argparse.ArgumentParser();parser.add_argument('--fit',required=True);parser.add_argument('--cal',required=True);args=parser.parse_args();fitpath=Path(args.fit);calpath=Path(args.cal);assert hashlib.sha256(fitpath.read_bytes()).hexdigest()=='f1d7cb4f43c94cc8265159253013b6b3323f57a607624d6c6b52e262a012f870';assert hashlib.sha256(calpath.read_bytes()).hexdigest()==p['source_cal_sha256']
for role,source in [('fit','source_fit'),('calibration','source_cal')]:
 rows=list(csv.DictReader((fitpath if role=='fit' else calpath).open()));ids[role]=sorted({r['cell_id'] for r in rows});tr=[]
 for cid in ids[role]:
  rr=sorted([r for r in rows if r['cell_id']==cid],key=lambda r:int(r['origin']));prev=None
  for r in rr:
   t=int(r['origin']);pred=math.exp(float(r['policy_mu_log_RUL'])) if role=='fit' else float(r['context_RUL_prediction']);y=float(r['true_RUL'])
   if prev is not None:
    oldt,oldpred=prev;assert t-oldt==1;delta=t+pred-(oldt+oldpred);gain=abs(max(0.,oldpred-1)-y)-abs(pred-y);tr.append(dict(cell_id=cid,origin=t,revision=delta,abs_revision=abs(delta),gain=gain,harmful=gain<-1e-10,helpful=gain>1e-10,weight=Fraction(1,len(ids[role])*(len(rr)-1))))
   prev=(t,pred)
 tt[role]=tr
cum=Fraction(0)
for r in sorted(tt['fit'],key=lambda r:r['abs_revision']):
 cum+=r['weight']
 if cum>=Fraction(9,10):cut=r['abs_revision'];break
refcut=json.loads((O/'train_cutoff.json').read_text())['cutoff'];assert abs(cut-refcut)<1e-9;pc=[];counts={}
for role,tr in tt.items():
 for r in tr:r['size_bin']='large' if r['abs_revision']>cut+1e-10 else 'rest';r['direction']='positive' if r['revision']>1e-10 else ('negative' if r['revision']<-1e-10 else 'zero')
 counts[role]={sb:sum(r['size_bin']==sb for r in tr) for sb in ['large','rest']}
 for cid in ids[role]:
  for sb in ['all','large','rest']:
   for dr in ['all','positive','negative','zero']:
    v=[r for r in tr if r['cell_id']==cid and (sb=='all' or r['size_bin']==sb) and (dr=='all' or r['direction']==dr)]
    if v:pc.append(dict(role=role,cell_id=cid,size_bin=sb,direction=dr,transitions=len(v),harmful_fraction=statistics.mean(r['harmful'] for r in v),helpful_fraction=statistics.mean(r['helpful'] for r in v),mean_update_gain_cycles=statistics.mean(r['gain'] for r in v),mean_abs_revision_cycles=statistics.mean(r['abs_revision'] for r in v)))
ref=json.loads((O/'per_cell_metrics.json').read_text());lookup={(r['role'],r['cell_id'],r['size_bin'],r['direction']):r for r in ref};maxdiff=0.
for r in pc:
 v=lookup[r['role'],r['cell_id'],r['size_bin'],r['direction']];assert r['transitions']==v['transitions']
 for k in ['harmful_fraction','helpful_fraction','mean_update_gain_cycles','mean_abs_revision_cycles']:maxdiff=max(maxdiff,abs(r[k]-v[k]))
assert len(pc)==len(ref) and maxdiff<1e-9 and len(tt['fit'])==22239 and len(tt['calibration'])==4557
out=dict(status='PASS_INDEPENDENT_FRACTION_WEIGHTED_CDF_AND_SCALAR_TRANSITIONS',cutoff=cut,cutoff_difference=abs(cut-refcut),maximum_per_cell_metric_difference=maxdiff,fit_transitions=22239,calibration_transitions=4557,counts=counts,per_cell_groups=len(pc),new_fits=0,new_model_inference=0,new_cutpoint_estimates=0)
with (O/'public_independent_validation.json').open('x') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(out))
