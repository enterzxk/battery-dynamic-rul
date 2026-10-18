from pathlib import Path
import json,csv,hashlib,datetime,collections
import numpy as np
R=Path('/home/yndx/zxk/rul');O=R/'reports/online_rate_harm_diagnosis_20261018_root';E=R/'experiments/online_survival_observed_pilot_seed42_v1';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,d):
 with (O/n).open('x',encoding='utf-8') as f:json.dump(d,f,indent=2,ensure_ascii=False);f.write('\n')
def writecsv(n,rows):
 with (O/n).open('x',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
 with (O/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
 p=json.loads((O/'protocol.json').read_text());co=json.loads((E/'cohort.json').read_text());rec=json.loads((E/'completion_receipt.json').read_text());assert sha(E/'cohort.json')==p['cohort_sha256'] and sha(E/'completion_receipt.json')==p['completion_sha256'];arrays={};trainratio=[];trainw=[]
 for c in co['cells']:
  qpath=R/c['cycle_summary_path'];assert sha(qpath)==c['cycle_summary_sha256'];q=np.array([z['capacity_Ah']/c['norm_Ah'] for z in json.loads(qpath.read_text())]);T=c['event_cycle'];ts=np.arange(100,T)
  def slopes(n):
   x=np.arange(n,dtype=float);v=(x-x.mean())/np.sum((x-x.mean())**2);return np.convolve(q,v[::-1],mode='valid')
  r20=slopes(20);r5=slopes(5);s20=r20[ts-20];s5=r5[ts-5];prev=r20[ts-40];rough=[]
  for t in ts:
   dq=np.diff(q[t-20:t]);mad=np.median(np.abs(dq-np.median(dq)));rough.append(mad/max(abs(r20[t-20]),1e-6))
  rough=np.array(rough);feat={'t':ts,'soh':q[ts-1],'slope20':s20,'slope5':s5,'previous20':prev,'roughness_ratio':rough}
  if c['split']=='train':trainratio.extend(rough.tolist());trainw.extend([1/len(ts)]*len(ts))
  else:arrays[c['cell_id']]=feat
 order=np.argsort(trainratio);vv=np.asarray(trainratio)[order];ww=np.asarray(trainw)[order];threshold=float(vv[np.searchsorted(np.cumsum(ww),.75*np.sum(ww),side='left')]);assert abs(sum(trainw)-52)<1e-8
 allrows=[];percell=[];intervals=[]
 for cid,f in sorted(arrays.items()):
  rel='validation_predictions/'+cid+'.csv';path=E/rel;assert sha(path)==rec['predictions_sha256'][rel];rr=[x for x in csv.DictReader(path.open()) if x['arm'] in ['F2_current_state','F3_state_rate']];aa={int(x['origin']):x for x in rr if x['arm']=='F2_current_state'};bb={int(x['origin']):x for x in rr if x['arm']=='F3_state_rate'};assert sorted(aa)==sorted(bb)==f['t'].tolist();N=len(aa);local=[]
  for j,t in enumerate(f['t']):
   a=aa[t];b=bb[t];true=float(a['true_RUL']);assert true==float(b['true_RUL']);pa=float(a['median_RUL']);pb=float(b['median_RUL']);ea=abs(pa-true);eb=abs(pb-true)
   z={'cell_id':cid,'t':int(t),'w':1/N,'state_abs_error':ea,'rate_abs_error':eb,'harm_cycles':eb-ea,'prediction_change':pb-pa,'soh':float(f['soh'][j]),'slope20':float(f['slope20'][j]),'roughness_ratio':float(f['roughness_ratio'][j]),'positive_slope20':bool(f['slope20'][j]>0),'short_long_sign_disagreement':bool(f['slope20'][j]*f['slope5'][j]<0),'high_roughness_ratio':bool(f['roughness_ratio'][j]>threshold),'recent_decline_twice_previous':bool(f['slope20'][j]<0 and f['previous20'][j]<0 and f['slope20'][j]<=2*f['previous20'][j]),'current_SOH_le85':bool(f['soh'][j]<=.85),'large_prediction_correction':abs(pb-pa)>20};local.append(z);allrows.append(z)
  d={'cell_id':cid,'origins':N,'state_MAE':float(np.mean([z['state_abs_error'] for z in local])),'rate_MAE':float(np.mean([z['rate_abs_error'] for z in local])),'harm_origin_fraction':float(np.mean([z['harm_cycles']>0 for z in local])),'harm_gt20_fraction':float(np.mean([z['harm_cycles']>20 for z in local])),'positive_slope20_fraction':float(np.mean([z['positive_slope20'] for z in local])),'high_roughness_fraction':float(np.mean([z['high_roughness_ratio'] for z in local]))};d['MAE_increase']=d['rate_MAE']-d['state_MAE'];percell.append(d)
  start=None
  for i in range(N+1):
   harm=i<N and local[i]['harm_cycles']>0
   if harm and start is None:start=i
   if not harm and start is not None:
    run=local[start:i]
    if len(run)>=10:intervals.append({'cell_id':cid,'start_origin':run[0]['t'],'end_origin':run[-1]['t'],'cycles':len(run),'mean_added_absolute_error':float(np.mean([z['harm_cycles'] for z in run])),'maximum_added_absolute_error':max(z['harm_cycles'] for z in run),'SOH_start':run[0]['soh'],'SOH_end':run[-1]['soh'],'positive_slope20_fraction':float(np.mean([z['positive_slope20'] for z in run])),'high_roughness_fraction':float(np.mean([z['high_roughness_ratio'] for z in run]))})
    start=None
 assert len(arrays)==19 and len(allrows)==10002;W=sum(z['w'] for z in allrows);assert abs(W-19)<1e-10
 def summary(rows):
  sw=sum(z['w'] for z in rows)
  if not rows:return {'origins':0,'cells':0,'population_query_weight_fraction':0}
  return {'origins':len(rows),'cells':len({z['cell_id'] for z in rows}),'population_query_weight_fraction':sw/19,'state_MAE_conditional':sum(z['w']*z['state_abs_error'] for z in rows)/sw,'rate_MAE_conditional':sum(z['w']*z['rate_abs_error'] for z in rows)/sw,'harm_probability_conditional':sum(z['w']*(z['harm_cycles']>0) for z in rows)/sw,'harm_gt20_probability_conditional':sum(z['w']*(z['harm_cycles']>20) for z in rows)/sw,'mean_added_abs_error_conditional':sum(z['w']*z['harm_cycles'] for z in rows)/sw,'contribution_to_total_MAE_increase':sum(z['w']*z['harm_cycles'] for z in rows)/19}
 overall=summary(allrows);assert abs(overall['state_MAE_conditional']-rec['metrics']['F2_current_state']['MAE'])<1e-9;assert abs(overall['rate_MAE_conditional']-rec['metrics']['F3_state_rate']['MAE'])<1e-9
 groups={}
 for tag in p['observable_tags']:
  yes=summary([z for z in allrows if z[tag]]);no=summary([z for z in allrows if not z[tag]]);assert abs(yes['contribution_to_total_MAE_increase']+no['contribution_to_total_MAE_increase']-overall['mean_added_abs_error_conditional'])<1e-9;groups[tag]={'true':yes,'false':no}
 save('tag_comparisons.json',groups);writecsv('per_cell_diagnosis.csv',percell);writecsv('harm_intervals.csv',intervals);harmcells=[z for z in percell if z['MAE_increase']>0];assert len(harmcells)==7
 result={'status':'COMPLETE_DESCRIPTIVE_RATE_HARM_DIAGNOSIS','at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'overall':overall,'high_roughness_train_weighted_q75':threshold,'training_threshold_cells':52,'training_threshold_queries':len(trainratio),'harmed_cells':harmcells,'improved_cells':12,'intervals_ge10':len(intervals),'worst_intervals':sorted(intervals,key=lambda x:x['mean_added_absolute_error'],reverse=True)[:8],'tags':groups,'training_only_descriptive_threshold_estimations':1,'predictive_fits':0,'optimizer_steps':0,'model_loads':0,'new_inference':0,'test_access':False,'causal_mechanism_or_gate_claim':False,'bindings':{n:sha(O/n) for n in ['protocol.json','diagnose.py']},'source_prediction_sha256':rec['predictions_sha256']};save('diagnosis.json',result);print(json.dumps({'overall':overall,'threshold':threshold,'harmed_cells':harmcells,'tags':groups,'worst_intervals':result['worst_intervals'][:3]}))
if __name__=='__main__':main()
