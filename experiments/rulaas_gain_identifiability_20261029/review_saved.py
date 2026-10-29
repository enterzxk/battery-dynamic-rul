#!/usr/bin/env python3
"""Independent audit of saved train-only proxy gains; no inference or fits."""
import pathlib,sys,csv,json,math,collections,copy,datetime,hashlib
import numpy as np
ROOT=pathlib.Path('/home/yndx/zxk/rul');OUT=ROOT/'experiments/rulaas_gain_identifiability_20261029/run02';HOME=ROOT/'reports/rulaas_gain_review_20261029_terra'
sys.path[:0]=[str(ROOT/'experiments/rulaas_value_gate_20261029'),str(ROOT/'experiments/multisource_factorial_20261021'),str(ROOT/'reports/multisource_20261021_signals'),str(ROOT/'experiments/isu_irregular_rul_seed42_v1'),str(ROOT/'experiments/dart_rul_v18')]
from value_gate import vector,MemoCycle
from data_adapter import load_reviewed_cell
import cycle_asof_features as C
WEEK=604800.;DAY=86400.
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def readcsv(n):
 with (OUT/n).open() as f:return list(csv.DictReader(f))
def fail(s):raise ValueError(s)
HOME.mkdir(exist_ok=False)
receipt=json.loads((OUT/'receipt.json').read_text());split=json.loads((OUT/'cell_split.json').read_text())
if receipt['status']!='SUCCESS' or any(receipt[k]!=0 for k in ['new_fits','C3_payload_reads','C4_payload_reads']):fail('receipt')
fit=set(split['base_head_fit_cells']);held=set(split['base_head_unseen_cells']);selectedfit=set(split['selected_kernel_fit']);selectedheld=set(split['selected_kernel_held'])
if len(fit)!=60 or len(held)!=60 or fit&held or len(selectedfit)!=24 or len(selectedheld)!=24 or not selectedfit<=fit or not selectedheld<=held or selectedfit&selectedheld:fail('split')
if split['residual_identity_max_error']>1e-8 or split['residuals_used_for_calibration'] is not False:fail('OOF provenance')
cases=readcsv('cases.csv');points=readcsv('counterfactual_points.csv');summ=readcsv('summary.csv');schema=json.loads((OUT/'feature_schema.json').read_text());X=np.load(OUT/'request_features.npz',allow_pickle=False)['X_request']
if X.shape!=(len(cases),711) or len(schema['features'])!=711 or schema['features'][-1]!='positive_head_point_proxy_RUL_weeks' or np.isinf(X).any():fail('feature contract')
features=set(schema['features'])
if any(z in features for z in ['future_candidate_stop_epoch','source_event_epoch','target_rul_weeks']):fail('future feature names')
by=collections.defaultdict(list)
for q in points:by[int(q['case_id'])].append(q)
source={x['cell_id']:x for x in receipt['source_files'] if x['kind']=='DataV2'}
cells={}
for cid in sorted(selectedfit|selectedheld):
 info=source[cid];p=ROOT/info['path']
 if not cid.endswith(('C1','C2')) or sha(p)!=info['sha256']:fail('source role/hash')
 c=load_reviewed_cell(p,'train');rr=sorted(c['records'],key=lambda z:float(z['stop_epoch']))
 overlaps=[]
 for j in range(1,len(rr)):
  if datetime.datetime.fromisoformat(rr[j]['start']).timestamp()<float(rr[j-1]['stop_epoch']):overlaps.append(int(rr[j]['source_rpt_index']))
 cells[cid]=(c,rr,overlaps)
max_gain_error=0.;max_feature_error=0.;pretest_overlaps=[];mutation_cells=set();cell_summary=collections.defaultdict(list);counts=collections.Counter()
for j,z in enumerate(cases):
 caseid=int(z['case_id']);cid=z['cell_id'];role=z['population'];c,rr,overlaps=cells[cid]
 if j!=caseid or cid not in (selectedfit if role=='kernel_fit' else selectedheld) or len(by[caseid])!=8:fail('case identity')
 pos=int(z['valid_ordinal']);candidate=rr[pos]
 if pos<3 or int(candidate['source_rpt_index'])!=int(z['source_rpt_index']):fail('candidate source identity')
 request=datetime.datetime.fromisoformat(candidate['start']).timestamp();stop=float(candidate['stop_epoch'])
 if abs(request-float(z['request_epoch']))>1e-6 or abs(stop-float(z['future_candidate_stop_epoch']))>1e-6:fail('original test timestamp')
 event=next((float(t['stop_epoch']) for t in rr if float(t['capacityAh'])<=.20),None)
 if event is None or abs(event-float(z['source_event_epoch']))>1e-6:fail('reference event identity')
 bg=[dict(t,arrival_epoch=float(t['stop_epoch'])+7*DAY) for i,t in enumerate(rr[:pos]) if i<3 or (i-3)%2==0]
 vis=[t for t in bg if float(t['arrival_epoch'])<=request]
 if len(vis)<3 or any(float(t['capacityAh'])<=.20 for t in vis):fail('request eligibility')
 if len(vis)!=int(z['input_arrived_RPT_count']) or sum(float(t['arrival_epoch'])>request for t in bg)!=int(z['input_pending_prior_reports']):fail('pending count')
 if pos>0 and float(rr[pos-1]['stop_epoch'])>request:pretest_overlaps.append({'cell_id':cid,'source_rpt_index':int(z['source_rpt_index'])})
 if abs(float(X[j,6])-float(z['input_staleness_weeks']))>1e-5 or abs(float(X[j,-1])-float(z['input_point_proxy_RUL']))>2e-5:fail('request feature alignment')
 score0=score7=0.;alive_count=0
 for k,p in enumerate(sorted(by[caseid],key=lambda v:int(v['slot'])),1):
  q=request+k*.5*WEEK;alive=q<event
  if int(p['slot'])!=k or abs(float(p['query_epoch'])-q)>1e-6 or (p['pre_reference_event']=='True')!=alive:fail('future slot')
  if alive:
   y=(event-q)/WEEK
   if abs(float(p['true_RUL'])-y)>1e-10:fail('target')
   a=float(p['point_no_candidate']);b=float(p['point_stop_delivery']);d=float(p['point_7day_delivery'])
   if q<stop and abs(a-b)>1e-9:fail('future immediate report leaked')
   if q<stop+7*DAY and abs(a-d)>1e-9:fail('future delayed report leaked')
   g0=abs(a-y)-abs(b-y);g7=abs(a-y)-abs(d-y);alive_count+=1
  else:
   if any(p[n] for n in ['point_no_candidate','point_stop_delivery','point_7day_delivery']):fail('postevent value should be unscored')
   g0=g7=0.
  max_gain_error=max(max_gain_error,abs(g0-float(p['gain_stop_delivery'])),abs(g7-float(p['gain_7day_delivery'])))
  score0+=g0/8;score7+=g7/8
 if max_gain_error>1e-10 or abs(score0-float(z['label_gain_stop_delivery_weeks']))>1e-10 or abs(score7-float(z['label_gain_7day_delivery_weeks']))>1e-10 or alive_count!=int(z['label_pre_event_slots']):fail('gain reconstruction')
 cell_summary[role,cid].append((score0,score7))
 counts[role+'_negative_delayed']+=int(score7 < -1e-9);counts[role+'_zero_delayed']+=int(abs(score7)<=1e-9);counts[role+'_positive_delayed']+=int(score7>1e-9);counts[role+'_immediate_hurts']+=int(score0 < -1e-9);counts[role+'_delay_improves_proxy_gain']+=int(score7>score0+1e-9)
 if role not in mutation_cells:
  inf={v['kind']:v for v in receipt['source_files'] if v['cell_id']==cid}
  for typ in ['RPT','Cycling']:
   if sha(ROOT/inf[typ]['path'])!=inf[typ]['sha256']:fail('derived hash')
  rpt=json.loads((ROOT/inf['RPT']['path']).read_text());cycle=MemoCycle(C.build_cycle_index(ROOT/inf['Cycling']['path']))
  cache={cid:{int(t['source_rpt_index']):t for t in rpt['records']}}
  x=vector(c,vis,request,cache,cycle)
  mask=np.isfinite(x)&np.isfinite(X[j,:710]);err=float(np.max(np.abs(x[mask]-X[j,:710][mask]))) if mask.any() else 0.
  if not np.allclose(x,X[j,:710],rtol=0,atol=1e-6,equal_nan=True):fail('feature reconstruction')
  mutated=copy.deepcopy(cache);mc=copy.deepcopy(c);mc['records'][pos]['capacityAh']=-999.
  for pending in [t for t in bg if float(t['arrival_epoch'])>request]+[candidate]:
   fr=mutated[cid][int(pending['source_rpt_index'])]
   if isinstance(fr.get('values'),list):fr['values']=[-99999.]*len(fr['values'])
   elif isinstance(fr.get('values'),dict):fr['values']={k:-99999. for k in fr['values']}
  if not np.allclose(vector(mc,vis,request,mutated,cycle),x,rtol=0,atol=0,equal_nan=True):fail('unarrived candidate/pending signals')
  mutation_cells.add(role);max_feature_error=max(max_feature_error,err)
if pretest_overlaps:fail('overlapping physical intervals at candidate times: '+repr(pretest_overlaps[:3]))
results=[]
for role in ['kernel_fit','kernel_held']:
 pairs=[(cid,np.mean(v,axis=0)) for (g,cid),v in cell_summary.items() if g==role]
 means=np.asarray([a for cid,a in pairs]);n=len(means);rng=np.random.RandomState(42);draw=means[rng.randint(n,size=(5000,n))]
 d=draw[:,:,0].mean(1)-draw[:,:,1].mean(1);val=means.mean(0)
 stored=next(x for x in summ if x['population']==role)
 if abs(val[0]-float(stored['gain_stop_delivery_cell_mean_weeks']))>1e-10 or abs(val[1]-float(stored['gain_7day_delivery_cell_mean_weeks']))>1e-10:fail('cell macro recompute')
 vals=[z for z in cases if z['population']==role];pending=[z for z in vals if int(z['input_pending_prior_reports'])>0]
 results.append({'population':role,'n_cells':n,'n_cases':len(vals),'immediate_gain_cell_macro':float(val[0]),'delay7d_gain_cell_macro':float(val[1]),'immediate_minus_delayed_cell_macro':float(val[0]-val[1]),'difference_bootstrap95_ci':[float(np.quantile(d,.025)),float(np.quantile(d,.975))],'CI_scope':'exploratory paired resampling by cell; conditional on fixed proxy and selected cases; same-group dependence not modeled','negative_delay_gain_cases':counts[role+'_negative_delayed'],'zero_delay_gain_cases':counts[role+'_zero_delayed'],'positive_delay_gain_cases':counts[role+'_positive_delayed'],'immediate_hurts_cases':counts[role+'_immediate_hurts'],'delay_improves_proxy_gain_cases':counts[role+'_delay_improves_proxy_gain'],'pending_prior_report_cases':len(pending),'max_case_harm_delay_weeks':float(min(float(z['label_gain_7day_delivery_weeks']) for z in vals)),'max_case_benefit_delay_weeks':float(max(float(z['label_gain_7day_delivery_weeks']) for z in vals))})
inputs=['cases.csv','counterfactual_points.csv','request_features.npz','feature_schema.json','cell_split.json','receipt.json','summary.csv']
out={'status':'PASS','model_used_for_this_audit':'gpt-6.1-terra (environment-selected; original project default gpt-6.1-sol/high)','new_fits':0,'new_inference_rows':0,'C3_payload_reads':0,'C4_payload_reads':0,'cases':len(cases),'slots':len(points),'split_and_original_OOF_identity':'PASS','source_events_and_recorded_test_windows':'PASS','gain_recomputation_max_error':max_gain_error,'request_feature_reconstruction_and_unarrived_mutation':{'populations_checked':sorted(mutation_cells),'max_feature_error':max_feature_error},'physical_interval_overlap_at_candidate':pretest_overlaps,'nonfinite_feature_values':int((~np.isfinite(X)).sum()),'results':results,'input_sha256':{n:sha(OUT/n) for n in inputs},'limits':['conditional positive-RUL proxy is not full hurdle service predictor','future supervised labels available retrospectively; never online inputs','48 selected historical source cells; not independent final confirmation','no value-learning fit, resource scheduling or SLO validation in this audit','passive observation replay does not establish skipped-test effect on physical health']}
with (HOME/'AUDIT.json').open('x') as f:json.dump(out,f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps(out,ensure_ascii=False))
