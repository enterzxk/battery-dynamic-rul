import pathlib,sys,json,datetime,hashlib,collections
import numpy as np
R=pathlib.Path('/home/yndx/zxk/rul');OLD=R/'experiments/rulaas_gain_identifiability_20261029/run02';OUT=R/'reports/rulaas_pending_lag_support_20261029_terra'
sys.path.insert(0,str(R/'experiments/isu_irregular_rul_seed42_v1'));from data_adapter import load_reviewed_cell
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dt(z):return datetime.datetime.fromisoformat(z).timestamp()
OUT.mkdir(exist_ok=False)
protocol={'source_indices':[4,8,12,16,20,24,28,32],'synthetic_report_lags_days':[7,14,21],'same_48_training_source_cells':True,'models_loaded':0,'models_fitted':0,'only_valid_recorded_opportunities':True,'diagnostic_purpose':'Assess support for a future pending-report test across explicit hypothetical reporting lags; do not claim any measured real-world arrival delay or predictive benefit.','fixed_train_staleness_max_weeks':3.426952600479126}
with (OUT/'PROTOCOL.json').open('x') as f:json.dump(protocol,f,indent=2)
split=json.loads((OLD/'cell_split.json').read_text());rec=json.loads((OLD/'receipt.json').read_text())
sources={z['cell_id']:z for z in rec['source_files'] if z['kind']=='DataV2'}
cases=[];skips=[]
for pop,ids in [('kernel_fit',split['selected_kernel_fit']),('kernel_held',split['selected_kernel_held'])]:
 for cid in ids:
  z=sources[cid];p=R/z['path']
  if not cid.endswith(('C1','C2')) or sha(p)!=z['sha256']:raise ValueError('role/source')
  c=load_reviewed_cell(p,'train');rows=sorted(c['records'],key=lambda z:float(z['stop_epoch']))
  event=next((float(z['stop_epoch']) for z in rows if float(z['capacityAh'])<=.20),None)
  for pos,x in enumerate(rows):
   idx=int(x['source_rpt_index'])
   if idx not in protocol['source_indices'] or pos<3:continue
   request=dt(x['start'])
   for lag in protocol['synthetic_report_lags_days']:
    bg=[dict(z,arrival_epoch=float(z['stop_epoch'])+lag*86400.) for j,z in enumerate(rows[:pos]) if j<3 or (j-3)%2==0]
    vis=[z for z in bg if z['arrival_epoch']<=request];pending=[z for z in bg if z['arrival_epoch']>request]
    reason='no_exact_source_event' if event is None else ('less_than_3_visible' if len(vis)<3 else ('known_event' if any(float(z['capacityAh'])<=.20 for z in vis) else ('previous_test_not_completed' if any(float(z['stop_epoch'])>request for z in bg) else None)))
    if reason:skips.append({'population':pop,'lag_days':lag,'reason':reason});continue
    gap=(request-float(vis[-1]['stop_epoch']))/604800.
    rem=[(float(z['arrival_epoch'])-request)/86400. for z in pending]
    cases.append({'population':pop,'cell_id':cid,'source_rpt_index':idx,'lag_days':lag,'n_pending':len(pending),'pending_remaining_days':min(rem) if rem else None,'staleness_weeks':gap,'past_train_max':gap>protocol['fixed_train_staleness_max_weeks'],'before_reference_event':request<event})
summary=[]
for pop in ['kernel_fit','kernel_held']:
 for lag in protocol['synthetic_report_lags_days']:
  a=[z for z in cases if z['population']==pop and z['lag_days']==lag];b=[z for z in a if z['n_pending']>0];rb=[z['pending_remaining_days'] for z in b]
  summary.append({'population':pop,'lag_days':lag,'eligible_cases':len(a),'eligible_cells':len({z['cell_id'] for z in a}),'pending_cases':len(b),'pending_cells':len({z['cell_id'] for z in b}),'pending_remaining_median_days':float(np.median(rb)) if rb else None,'pending_remaining_gt_3_5days':sum(x>3.5 for x in rb),'staleness_exceeds_train_max_cases':sum(z['past_train_max'] for z in a),'pre_reference_event_cases':sum(z['before_reference_event'] for z in a),'skipped_by_reason':dict(collections.Counter(z['reason'] for z in skips if z['population']==pop and z['lag_days']==lag))})
out={'status':'COMPLETE_EXPLORATORY_METADATA','new_fits':0,'new_model_rows':0,'C3_payload_reads':0,'C4_payload_reads':0,'summary':summary,'limits':['report arrival lag is hypothetical, not measured','selected successful recorded opportunities only','staleness support metric is descriptive, not a coverage guarantee','no paired gains, resource-scheduling evaluation or policy fit']}
with (OUT/'AUDIT.json').open('x') as f:json.dump(out,f,indent=2,allow_nan=False)
print(json.dumps(out))
