import pathlib,json,csv,collections,datetime,hashlib,sys
import numpy as np
ROOT=pathlib.Path('/home/yndx/zxk/rul');HERE=ROOT/'experiments/rulaas_value_gate_20261029';OUT=HERE/'run02'
formal=ROOT/'experiments/multisource_factorial_20261021/run2_clocksafe'
schema=json.loads((formal/'feature_schema.json').read_text());idx=schema['feature_names']['F3'].index('query_gap_from_last_rpt_weeks')
arr=np.load(formal/'train_features.npz',allow_pickle=False)['F3'][:,idx];v=arr[np.isfinite(arr)]
thresholds={'p95':float(np.quantile(v,.95)),'max':float(v.max())}
groups=collections.defaultdict(list)
with (OUT/'predictions.csv').open() as f:
 for x in csv.DictReader(f):
  if x['primary_positive_rul']=='True':groups[x['policy']].append((x['cell_id'],(float(x['query_epoch'])-float(x['last_visible_RPT_stop']))/604800.,float(x['abs_error'])))
summary=[]
for policy,rows in sorted(groups.items()):
 z={'policy':policy,'n_queries':len(rows),'p50_staleness_weeks':float(np.median([x[1] for x in rows])),'max_staleness_weeks':max(x[1] for x in rows)}
 for key,t in thresholds.items():
  beyond=[x for x in rows if x[1]>t]
  z['query_fraction_above_train_'+key]=len(beyond)/len(rows)
  by=collections.defaultdict(list)
  for cid,gap,err in rows:
   if gap<=t:by[cid].append(err)
  z['cell_macro_MAE_within_train_'+key]=float(np.mean([np.mean(a) for a in by.values()])) if by else None
  z['cells_within_train_'+key]=len(by)
 summary.append(z)
sys.path.insert(0,str(ROOT/'experiments/isu_irregular_rul_seed42_v1'));from data_adapter import load_reviewed_cell
man=json.loads((ROOT/'reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json').read_text());roles=json.loads((ROOT/'reports/isu_ilcc_capacity_probe_20261020_root/cohort.json').read_text())['roles']
sources=[];dur=[];missing=[];overlap=[]
for cid in sorted(k for k,v in roles.items() if v=='development'):
 if not cid.endswith('C3'):raise ValueError('role gate')
 info=man['files'][cid];p=ROOT/info['path'];h=hashlib.sha256(p.read_bytes()).hexdigest()
 if h!=info['sha256']:raise ValueError('source hash mismatch')
 c=load_reviewed_cell(p,'development');sources.append({'cell_id':cid,'sha256':h,'path':info['path']})
 last=-float('inf')
 for row in sorted(c['records'],key=lambda x:float(x['stop_epoch'])):
  try:start=datetime.datetime.fromisoformat(row['start']).timestamp()
  except Exception:missing.append([cid,row['source_rpt_index']]);continue
  stop=float(row['stop_epoch']);hours=(stop-start)/3600.
  if hours<=0:missing.append([cid,row['source_rpt_index']]);continue
  dur.append(hours)
  if start<last:overlap.append([cid,row['source_rpt_index']])
  last=stop
result={'status':'COMPLETED_SAVED_SUPPORT_AND_SOURCE_TIMING_DIAGNOSIS','new_fits':0,'new_inference_rows':0,'C4_payload_reads':0,'train_staleness':dict(n_rows=len(v),**thresholds),'policy_staleness':summary,'RPT_timing':{'n_valid_durations':len(dur),'median_hours':float(np.median(dur)),'p95_hours':float(np.quantile(dur,.95)),'min_hours':float(min(dur)),'max_hours':float(max(dur)),'missing_or_invalid_start_stop':missing,'within_cell_overlapping_intervals':overlap},'sources':sources,'input_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [formal/'train_features.npz',formal/'feature_schema.json',OUT/'predictions.csv',pathlib.Path(__file__)]},'interpretation':['Frozen HGB support does not establish information-theoretic value; compare staleness regimes explicitly.','Within-support summaries use different row populations by policy and are descriptive only, not fair paired method comparisons.','Recorded start/stop supports actual occupied test intervals. Deferring physical sampling beyond its recorded interval would require an unobserved counterfactual outcome.','A faithful finite-station replay can admit/reject fixed recorded opportunities; a reporting/analysis queue after sampling must be named separately and cannot be claimed to save already incurred physical testing cost.']}
with (OUT/'SUPPORT_AND_TIMING_DIAGNOSIS.json').open('x') as f:json.dump(result,f,indent=2)
print(json.dumps({k:v for k,v in result.items() if k not in ['sources','input_sha256']},ensure_ascii=False))
