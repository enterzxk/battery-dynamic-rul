import pathlib,json,csv,hashlib,datetime,math
import numpy as np
from scipy.stats import spearmanr
P=pathlib.Path('/home/yndx/zxk/rul')
D=pathlib.Path(__file__).resolve().parent
sha=lambda f:hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest()
def dump(n,v):
 with (D/n).open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')
def rho(x,y):
 if len(x)<3 or len(set(x))<2 or len(set(y))<2:return None
 return float(spearmanr(x,y).statistic)
def ranks(x):
 order=sorted(range(len(x)),key=lambda i:x[i]);r=[0.]*len(x);i=0
 while i<len(order):
  j=i+1
  while j<len(order) and x[order[j]]==x[order[i]]:j+=1
  for k in range(i,j):r[order[k]]=(i+j+1)/2
  i=j
 return r
def independent_rho(x,y):
 a=ranks(x);b=ranks(y);am=sum(a)/len(a);bm=sum(b)/len(b)
 num=sum((u-am)*(v-bm) for u,v in zip(a,b));den=math.sqrt(sum((u-am)**2 for u in a)*sum((v-bm)**2 for v in b))
 return num/den if den else None
def main():
 pr=json.loads((D/'protocol.json').read_text());go=json.loads((D/'ROOT_GO.json').read_text())
 assert go['runner_sha256']==sha(__file__) and go['protocol_sha256']==sha(D/'protocol.json')
 for rel,h in pr['source_sha256'].items():assert sha(P/rel)==h
 roles=json.loads((P/pr['cohort']).read_text())['roles'];allowed={c for c,r in roles.items() if r=='calibration'};assert len(allowed)==10
 cap=list(csv.DictReader((P/pr['capacity']).open()));mix=list(csv.DictReader((P/pr['mixture']).open()))
 raw=list(csv.DictReader((P/pr['distributions']).open()));arms=sorted({r['arm'] for r in raw})
 dyn=[r for r in raw if r['arm']=='lossless_dynamic'];assert dyn,arms
 def index(rs,key):
  d={}
  for r in rs:
   assert r['cell_id'] in allowed
   k=(r['cell_id'],int(r[key]));assert k not in d;d[k]=r
  return d
 m=index(mix,'origin');v=index(dyn,'origin');assert set(m)==set(v)
 for k in m:assert float(m[k]['true_RUL'])==float(v[k]['true_RUL'])
 a=index(cap,'target_cycle');assert set(a)<=set(m)
 assert len(a)==4367 and len(m)==4567
 rows=[]
 for k,c in sorted(a.items()):
  cell,s=k;f=int(c['forecast_origin']);visible=int(c['features_visible_through'])
  assert s-f==20 and visible==f and visible<s
  t=float(m[k]['true_RUL']);assert t>0
  residual=abs(float(c['predicted_delta_mSOH'])-float(c['true_delta_mSOH']))
  dynamic=float(v[k]['q50']);mixture=float(m[k]['q50'])
  rows.append(dict(cell_id=cell,origin=s,forecast_origin=f,target_cycle=s,residual_available_through=s,abs_delayed_capacity_residual_mSOH=residual,true_RUL=t,dynamic_RUL=dynamic,mixture_RUL=mixture,absolute_RUL_loss_difference=abs(dynamic-t)-abs(mixture-t),over100_difference=int(dynamic-t>100)-int(mixture-t>100)))
 fields=list(rows[0])
 with (D/'aligned_diagnostic_rows.csv').open('x',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 pc=[];checks=[]
 for cell in sorted(allowed):
  z=[r for r in rows if r['cell_id']==cell];orig=[r['origin'] for r in z];assert all(b-a==1 for a,b in zip(orig,orig[1:]))
  missing=sorted(k[1] for k in set(m)-set(a) if k[0]==cell);assert missing==list(range(100,120))
  x=[r['abs_delayed_capacity_residual_mSOH'] for r in z];y=[r['absolute_RUL_loss_difference'] for r in z]
  dx=[b-a for a,b in zip(x,x[1:])];dy=[b-a for a,b in zip(y,y[1:])]
  primary=rho(x,y);diff=rho(dx,dy);secondary=rho(x,[r['over100_difference'] for r in z])
  pc.append(dict(cell_id=cell,n=len(z),min_origin=min(orig),max_origin=max(orig),primary_rho=primary,first_difference_rho=diff,over100_difference_rho=secondary))
  manual=independent_rho(x,y);manualdiff=independent_rho(dx,dy);assert abs(primary-manual)<1e-12 and abs(diff-manualdiff)<1e-12
  checks.append(max(abs(primary-manual),abs(diff-manualdiff)))
 metrics={'cells':len(pc),'matched_rows':len(rows),'RUL_rows_without_available_delayed_signal':len(m)-len(a),'excluded_origins_per_cell':'100..119; not imputed',
 'mean_cell_rho':float(np.mean([r['primary_rho'] for r in pc])),'median_cell_rho':float(np.median([r['primary_rho'] for r in pc])),'positive_primary_cells':sum(r['primary_rho']>0 for r in pc),
 'mean_cell_first_difference_rho':float(np.mean([r['first_difference_rho'] for r in pc])),'median_cell_first_difference_rho':float(np.median([r['first_difference_rho'] for r in pc])),'positive_first_difference_cells':sum(r['first_difference_rho']>0 for r in pc),
 'both_positive_cells':sum(r['primary_rho']>0 and r['first_difference_rho']>0 for r in pc),'undefined_secondary_cells':sum(r['over100_difference_rho'] is None for r in pc),'independence_or_pvalues_claimed':False}
 dump('per_cell_metrics.json',pc);dump('metrics.json',metrics)
 examples=[rows[0],rows[len(rows)//2],rows[-1]]
 for r in examples:
  c=a[(r['cell_id'],r['origin'])];r=dict(r);r['source_true_delta_mSOH']=float(c['true_delta_mSOH']);r['source_predicted_delta_mSOH']=float(c['predicted_delta_mSOH'])
  # Examples retain already-saved predictions; no newly evaluated model.
  checks.append(0.)
 dump('validation.json',{'status':'PASS','unique_keys_roles_labels_horizon_and_asof_checks':True,'max_independent_rank_correlation_difference':max(checks),'source_arms':arms,'new_fits':0,'new_model_inference':0,'checkpoint_loads':0,'dev_test_reads':0,'examples':examples,'aligned_rows_sha256':sha(D/'aligned_diagnostic_rows.csv')})
 support=metrics['positive_primary_cells']>=7 and metrics['positive_first_difference_cells']>=7 and metrics['both_positive_cells']>=7
 dump('root_decision.json',{'decision':'DESCRIPTIVE_SIGNAL_SCREEN_PASS_NO_GATE_AUTHORIZATION' if support else 'NO_GO_DELAYED_CAPACITY_RESIDUAL_GATE_FROM_CURRENT_DIAGNOSTIC','screen_pass':support,'metrics':metrics,'no_prediction_changed':True,'new_fits':0,'new_model_inference':0,'dev_test_reads':0,'GO_consumed':True,'CPUfits_unchanged':20,'limits':['Repeatedly exposed10cal; posthoc development only','Firstdifference only trend sensitivity; no independence or causality proof','RULtruth scoring only, never online input','Fixed20capacity model differs from losslessRUL inputs','No threshold/weight/fold/seed search or online gate implemented']})
 dump('completion.json',{'status':'COMPLETE_ONCE_SAVED_PREDICTION_DIAGNOSTIC','new_fits':0,'new_model_inference':0,'dev_test_reads':0,'runner_sha256':sha(__file__),'protocol_sha256':sha(D/'protocol.json'),'GO_sha256':sha(D/'ROOT_GO.json'),'rows_sha256':sha(D/'aligned_diagnostic_rows.csv'),'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
 print(json.dumps({'metrics':metrics,'decision':'PASS_SCREEN_ONLY' if support else 'NO_GO'}))
if __name__=='__main__':main()
