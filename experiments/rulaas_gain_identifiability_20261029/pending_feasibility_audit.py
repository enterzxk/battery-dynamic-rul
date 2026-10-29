import json,csv,collections,datetime,pathlib,hashlib,sys,math
import numpy as np
ROOT=pathlib.Path('/home/yndx/zxk/rul');SRC=ROOT/'experiments/rulaas_gain_identifiability_20261029/run02';OUT=ROOT/'reports/rulaas_pending_feasibility_20261029_terra'
sys.path.insert(0,str(ROOT/'experiments/isu_irregular_rul_seed42_v1'));from data_adapter import load_reviewed_cell
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dt(s):return datetime.datetime.fromisoformat(s).timestamp()
def quantiles(a):
 return {'n':len(a),'min':float(np.min(a)),'median':float(np.median(a)),'p95':float(np.quantile(a,.95)),'max':float(np.max(a))} if a else {'n':0}
OUT.mkdir(exist_ok=False)
protocol='训练源同一48电芯，检测候选source_rpt_index预定为4/8/12/16/20/24/28/32；先前三个有效检测固定保留，其后仅选择有效记录序号3、5、7……。报告在检测stop后7天到达；候选起始只看先前已到报告，区分已有报告等待和无等待。原始化健康状态、站点资源不在本元数据审计中模拟；已确认失效和少于3条已到报告的候选排除。仅有有效记录的机会可计算，未来可测性/失败机制未识别。不训练或推断模型。'
(OUT/'PROTOCOL_ZH.md').write_text(protocol,encoding='utf-8')
split=json.loads((SRC/'cell_split.json').read_text());receipt=json.loads((SRC/'receipt.json').read_text())
sources={z['cell_id']:z for z in receipt['source_files'] if z['kind']=='DataV2'}
candidates={4,8,12,16,20,24,28,32};results=[];reject=[];cellrows=[]
for pop,ids in [('kernel_fit',split['selected_kernel_fit']),('kernel_held',split['selected_kernel_held'])]:
 for cid in ids:
  info=sources[cid];path=ROOT/info['path']
  if not cid.endswith(('C1','C2')) or sha(path)!=info['sha256']:raise ValueError('source identity')
  c=load_reviewed_cell(path,'train');rows=sorted(c['records'],key=lambda x:float(x['stop_epoch']))
  event=next((float(z['stop_epoch']) for z in rows if float(z['capacityAh'])<=.2),None)
  seen=[]
  for pos,row in enumerate(rows):
   idx=int(row['source_rpt_index'])
   if idx not in candidates or pos<3:continue
   t=dt(row['start']);bg=[dict(z,arrival_epoch=float(z['stop_epoch'])+7*86400.) for j,z in enumerate(rows[:pos]) if j<3 or (j-3)%2==0]
   vis=[z for z in bg if float(z['arrival_epoch'])<=t];pending=[z for z in bg if float(z['arrival_epoch'])>t]
   reason='no_source_event' if event is None else ('fewer_than_three_reports' if len(vis)<3 else ('known_failure' if any(float(z['capacityAh'])<=.2 for z in vis) else ('prior_test_still_running' if any(float(z['stop_epoch'])>t for z in bg) else None)))
   if reason:reject.append(dict(cell_id=cid,population=pop,index=idx,reason=reason));continue
   remaining=[(float(z['arrival_epoch'])-t)/86400. for z in pending]
   seen.append(dict(cell_id=cid,population=pop,index=idx,valid_ordinal=pos,request_epoch=t,pending_count=len(pending),earliest_pending_arrival_days=min(remaining) if remaining else None,before_reference_event=t<event))
  cellrows.extend(seen)
for pop in ['kernel_fit','kernel_held']:
 a=[z for z in cellrows if z['population']==pop];b=[z for z in a if z['pending_count']>0]
 results.append({'population':pop,'n_eligible':len(a),'n_cells':len({z['cell_id'] for z in a}),'n_pending':len(b),'n_cells_pending':len({z['cell_id'] for z in b}),'pending_fraction':len(b)/len(a) if a else None,'pending_remaining_days':quantiles([z['earliest_pending_arrival_days'] for z in b]),'candidate_before_reference_event':sum(z['before_reference_event'] for z in a),'rejections_by_reason':dict(collections.Counter(z['reason'] for z in reject if z['population']==pop))})
audit={'status':'COMPLETED_METADATA_ONLY','execution_model':'gpt-6.1-terra (environment selected; model preference requested)','new_fits':0,'new_inference_rows':0,'C3_payload_reads':0,'C4_payload_reads':0,'prior_original_186_candidates_with_pending':0,'proposed_candidate_source_indices':sorted(candidates),'data_source_cells':48,'results':results,'input_sha256':{'cell_split.json':sha(SRC/'cell_split.json'),'receipt.json':sha(SRC/'receipt.json')},'limitations':['only successfully recorded valid opportunities; missing/invalid opportunity mechanism not identified','source event used solely as retrospective eligibility metadata, not a model feature','pending-count support is not evidence of predictive gain','no resource queue or physical intervention replay']}
with (OUT/'AUDIT.json').open('x') as f:json.dump(audit,f,ensure_ascii=False,indent=2,allow_nan=False)
if cellrows:
 with (OUT/'opportunities.csv').open('x',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(cellrows[0]));w.writeheader();w.writerows(cellrows)
print(json.dumps(audit,ensure_ascii=False))
