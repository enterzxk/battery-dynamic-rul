import pathlib,json,csv,collections,datetime,hashlib,sys,heapq,math
import numpy as np
ROOT=pathlib.Path('/home/yndx/zxk/rul');HERE=ROOT/'experiments/rulaas_station_admission_20261029';OUT=HERE/'run01'
sys.path.insert(0,str(ROOT/'experiments/isu_irregular_rul_seed42_v1'));from data_adapter import load_reviewed_cell
def rows(name):
 with (OUT/name).open() as f:return list(csv.DictReader(f))
receipt=json.loads((OUT/'receipt.json').read_text())
if receipt['status']!='SUCCESS' or receipt['new_fits'] or receipt['C4_payload_reads']:raise ValueError('receipt mismatch')
pred=rows('predictions.csv');decisions=rows('decisions.csv');summary=rows('summary.csv');per=rows('per_cell.csv')
world=json.loads((OUT/'fleet_world.json').read_text());thresholds=json.loads((OUT/'train_only_thresholds.json').read_text())
sources={x['cell_id']:x for x in receipt['source_files'] if x['kind']=='DataV2' and x['cell_id'].endswith('C3')}
cells={};accepted={};jobs=collections.defaultdict(list);queries=collections.defaultdict(set);cyclecounts=collections.defaultdict(set);agg=collections.defaultdict(list)
for cid,info in sources.items():
 p=ROOT/info['path']
 if hashlib.sha256(p.read_bytes()).hexdigest()!=info['sha256']:raise ValueError('source changed')
 c=load_reviewed_cell(p,'development');rr=sorted(c['records'],key=lambda z:float(z['stop_epoch']))
 cells[cid]={'rows':rr,'by_index':{int(z['source_rpt_index']):z for z in rr},'warm':float(rr[2]['stop_epoch']) if len(rr)>=3 else None}
for d in decisions:jobs[d['world']].append(d)
max_concurrent={};hours={}
for name,ds in jobs.items():
 M=int(ds[0]['stations']);busy=[];ad={cid:[int(z['source_rpt_index']) for z in c['rows'][:3]] for cid,c in cells.items()};hours[name]=0.;mx=0;last=-float('inf')
 for d in ds:
  t=float(d['fleet_request_seconds']);q=float(d['source_request_epoch']);cid=d['cell_id'];idx=int(d['source_rpt_index']);c=cells[cid];rr=c['by_index'][idx]
  if t<last:raise ValueError('request order')
  last=t
  actual_start=datetime.datetime.fromisoformat(rr['start']).timestamp()
  if abs(actual_start-q)>1e-7:raise ValueError('deferred sample time')
  if abs(t-(q-c['warm']+world['offset_seconds'][cid]))>1e-7:raise ValueError('fleet translation')
  while busy and busy[0][0]<=t:heapq.heappop(busy)
  vis=[c['by_index'][i] for i in ad[cid] if float(c['by_index'][i]['stop_epoch'])+604800<=q]
  known=any(float(z['capacityAh'])<=.20 for z in vis)
  admitted=d['admitted']=='True'
  if known and d['reason']!='known_event':raise ValueError('known-event handling')
  if not known and len(busy)>=M and d['reason']!='station_busy':raise ValueError('busy acceptance decision')
  if d['reason']=='below_threshold' and not float(d['score'])<float(d['threshold']):raise ValueError('threshold decision')
  if d['reason']=='admit' and d['policy']!='all' and not float(d['score'])>=float(d['threshold']):raise ValueError('threshold admission')
  if admitted:
   slot=int(d['station_slot'])
   if slot<0 or slot>=M or any(s==slot for stop,s in busy):raise ValueError('station double booking')
   stop=float(rr['stop_epoch']);duration=(stop-q)/3600.
   if abs(duration-float(d['actual_station_hours']))>1e-9:raise ValueError('cost duration mismatch')
   if abs(float(d['arrival_epoch_if_admitted'])-stop-604800)>1e-7:raise ValueError('arrival lag')
   heapq.heappush(busy,(stop-c['warm']+world['offset_seconds'][cid],slot));ad[cid].append(idx);hours[name]+=duration
  if len(busy)>M:raise ValueError('resource cap')
  mx=max(mx,len(busy))
 accepted[name]=ad;max_concurrent[name]=mx
for p in pred:
 name=p['world'];cid=p['cell_id'];q=float(p['query_epoch']);c=cells[cid];ids=json.loads(p['visible_RPT_indices'])
 expected=[i for i in accepted[name][cid] if float(c['by_index'][i]['stop_epoch'])+604800<=q]
 if ids!=expected:raise ValueError('visible selected reports mismatch')
 if (p['known_event']=='True')!=any(float(c['by_index'][i]['capacityAh'])<=.20 for i in expected):raise ValueError('known-event leakage')
 event=next((float(z['stop_epoch']) for z in c['rows'] if float(z['capacityAh'])<=.20),None)
 target=None if event is None else max(0.,(event-q)/604800.)
 if target is None:
  if p['target_rul_weeks']:raise ValueError('censored source target changed')
 elif not p['target_rul_weeks'] or abs(float(p['target_rul_weeks'])-target)>1e-10:raise ValueError('source RUL target mismatch')
 if (p['primary_positive_rul']=='True')!=(event is not None and event>q):raise ValueError('primary source population')
 key=(cid,p['query_epoch']);queries[key].add((p['source_event_epoch'],p['target_rul_weeks'],p['primary_positive_rul']))
 cyclecounts[key].add(p['cheap_cycle_count'])
 if float(p['last_arrival_epoch'])>q:raise ValueError('future report')
 if p['abs_error']:
  err=abs(float(p['mean_RUL'])-float(p['target_rul_weeks']))
  if abs(err-float(p['abs_error']))>1e-10:raise ValueError('row error')
 if p['primary_positive_rul']=='True':agg[name,cid].append(float(p['abs_error']))
if any(len(x)!=1 for x in queries.values()) or any(len(x)!=1 for x in cyclecounts.values()):raise ValueError('common world input/target mismatch')
nworld=len(jobs)
if len(pred)!=nworld*len(queries) or len({(p['world'],p['cell_id'],p['query_epoch']) for p in pred})!=len(pred):raise ValueError('different query supports or duplicates')
maxerr=0.
for s in summary:
 vv=[sum(v)/len(v) for (w,c),v in agg.items() if w==s['world']]
 got=sum(vv)/len(vv);maxerr=max(maxerr,abs(got-float(s['primary_MAE'])))
 if abs(hours[s['world']]-float(s['station_hours']))>1e-7 or max_concurrent[s['world']]!=int(s['max_concurrent']):raise ValueError('aggregate resource mismatch')
if maxerr>1e-10:raise ValueError('aggregate MAE')
contrasts=[];by={s['world']:s for s in summary}
for M in [2,4]:
 ref=by['M%d_all'%M]
 for policy in ['age','width','arrival_risk']:
  name='M%d_%s'%(M,policy);s=by[name]
  ds=[(cid,sum(v)/len(v)-np.mean(agg[ref['world'],cid])) for (w,cid),v in agg.items() if w==name]
  contrasts.append({'candidate':name,'reference':ref['world'],'MAE_delta_weeks':float(s['primary_MAE'])-float(ref['primary_MAE']),'station_hours_saved_fraction':1-float(s['station_hours'])/float(ref['station_hours']),'improved_cells':int(sum(d<0 for cid,d in ds)),'harmed_cells':int(sum(d>0 for cid,d in ds)),'worst_harmed_cell':max(ds,key=lambda z:z[1])[0],'worst_cell_delta_weeks':max(d for cid,d in ds),'missed_events':int(s['missed_events']),'reference_missed_events':int(ref['missed_events']),'coverage80_delta':float(s['primary_coverage80'])-float(ref['primary_coverage80']),'false_alarm_fraction_delta':float(s['false_alarm_fraction'])-float(ref['false_alarm_fraction']),'confidence_interval':None,'reason_no_CI':'One coupled fleet pilot; not independent cell or query replicates.'})
check={'status':'PASS','new_fits':0,'new_inference_rows':0,'C4_payload_reads':0,'prediction_rows':len(pred),'common_query_times':len(queries),'resource_worlds':nworld,'independent_MAE_max_difference':maxerr,'selected_report_prefix_reconstruction':'PASS_ALL_ROWS','original_source_sampling_start_preserved':'PASS_ALL_DECISIONS','station_overlap_and_duration_reconstruction':'PASS_ALL_ADMITTED','same_target_population_and_cheap_cycle_counts':'PASS','contrasts':contrasts}
with (OUT/'INDEPENDENT_RECOMPUTE.json').open('x') as f:json.dump(check,f,indent=2)
report=['# 固定检测窗口与有限检测站：首轮基线实验（2026-10-29）','','**实际完成，开发证据。0新拟合、0优化步、0C4数据读取。** 62电芯、2960共同查询、8个资源/策略配置，23680条预测；实际模型输入21730行（训练分位阈值6870、开发14860），同输入精确复用。','','本轮在原始检测 start/stop 窗口中接纳/拒绝，站满则拒绝，不把未测时刻的结果当成已知。报告在原检测 stop+7天可见。所有策略使用同一虚拟车队偏移、同一参考事件、廉价循环流和初始化。前三次检测不计本阶段资源成本。','','|检测站|策略|失效前MAE/周|占站小时|接纳次数|四周漏报事件/61|80%覆盖率|','|---:|---|---:|---:|---:|---:|---:|']
names={'all':'有空站即接纳','age':'陈旧程度阈值','width':'区间宽度阈值','arrival_risk':'预期报告时失效风险阈值'}
for s in summary:report.append('|%s|%s|%.4f|%.1f|%s|%s|%.4f|'%(s['stations'],names[s['policy']],float(s['primary_MAE']),float(s['station_hours']),s['admitted_tests'],s['missed_events'],float(s['primary_coverage80'])))
report+=['','## 实验改变了什么判断','1. 在M=4这一个预设车队场景，陈旧程度规则相对有空站即接纳，少用约30.7%占站时间，MAE增加约0.0303周；漏报事件同为2/61。但80%覆盖率降低约2.38个百分点，误报比例增加。它是简单基线的点估计权衡，不是已证明非劣，更不是新方法成果。','2. 在M=2场景，陈旧程度规则少用约23.5%占站时间，MAE增加约0.0196周，漏报事件6/61对11/61。共享站点改变了哪些电芯得到检测；只有一个车队，不能报电芯bootstrap作为拥塞不确定性的区间。','3. 绝对区间宽度门限失败：M=2/4漏报58/59个事件，MAE超过5周。该阈值把检测长期集中到少量高不确定性状态，不能把少占资源当成功。停止这个固定门限，不在C3调分位数挽救。','4. 预期报告时风险阈值几乎等于有空站即接纳（每场景只额外筛掉7至8次请求），M=2/4的误差变化方向不一致。它没有形成可作为创新的可靠选择效应。','5. 后续信息价值方法必须面对陈旧程度基线及其训练内调优版本；不能只胜过弱的全接纳或失败的宽度门限。','','## 必须保留的限制','- C3已多轮开发；单seed42、单个由真实轨迹整体平移构造的车队，两种预设容量；无独立确认。','- 当前分位阈值只由训练输入/冻结模型输出确定，未使用C3选择；但也不是已经优化到最强的策略。','- 资源容量相同，不代表实际消耗小时完全相同。这里报告前沿权衡，不称所有策略等消耗。','- 80%覆盖率并不达成原方案90%覆盖SLO；漏报比例须同时看置信区间、误报和事件数量，不能仅凭2/61宣称FN≤5%。','- 极端陈旧状态可超原预测器训练支持，不能把全部失败归为信息论缺失。','- 原始检测时长只由环境在接纳后用于真实资源占用；策略在决策时使用训练时长中位数18.6276小时，不读取新检测值或未来真实时长。','- 这是固定机会接纳，不是已验证可任意延期取样的物理队列，也没有完成在线寿命标签反馈控制。','','## 核对与下一步','从原始来源记录和接纳日志独立重建全部23680个可见报告前缀，逐站检查重叠/原始start/时长/报告延迟，独立重算电芯MAE；全部通过。逐电芯损害在INDEPENDENT_RECOMPUTE.json。','下一步先在训练电芯中构造“报告到达后实际预测损失改善”的可监督价值标签，并评估能否超出年龄/不确定性；标签只作历史训练监督，部署输入只含决策前已到达信息。学习或校准前需新合同/哈希GO；不在C3挑阈值、不解封C4、不把普通VoI或年龄门限包装成创新。']
with (OUT/'RESULTS_ZH.md').open('x',encoding='utf-8') as f:f.write('\n'.join(report))
root={'status':'BASELINE_PILOT_COMPLETE_PAPER_GATE_NOT_MET','fixed_width_threshold':'NO_GO_STARVATION_AND_MISSED_EVENTS_STOP_THIS_CONFIGURATION','fixed_arrival_risk_threshold':'NO_ESTABLISHED_GAIN_NEAR_ALL_ACCEPT','age_baseline':'RETAIN_STRONG_SIMPLE_REFERENCE_POINT_SIGNAL_NOT_NONINFERIORITY_PROOF','new_method_validated':False,'paper_ready':False,'independent_confirmation':False,'next_action':'Train-only identifiable acquisition-benefit construction and nearest-method conflict check; no C3 threshold rescue or new predictor scaling. Fresh exact GO required for fits/inference.'}
with (OUT/'ROOT_DECISION.json').open('x') as f:json.dump(root,f,indent=2)
print(json.dumps({'checks':check,'root_decision':root},ensure_ascii=False))
