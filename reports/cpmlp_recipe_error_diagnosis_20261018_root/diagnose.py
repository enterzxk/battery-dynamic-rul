"""Paired attribution from two frozen validation prediction CSVs only; no model/data binary."""
from pathlib import Path
import csv,json,math,statistics,hashlib,datetime
ROOT=Path('/home/yndx/zxk/rul')
OUT=ROOT/'reports/cpmlp_recipe_error_diagnosis_20261018_root'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
mean=statistics.mean
def write(name,obj):
 with (OUT/name).open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n')
def wc(name,rows):
 with (OUT/name).open('x',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
newroot=ROOT/'experiments/cpmlp_hust_recipe_adapt_seed42_v2'
oldroot=ROOT/'experiments/cpmlp_hust_pilot_seed42/fit_runs/fit_20261016T034610_311103Z'
nr=json.loads((newroot/'completion_receipt.json').read_text())
orr=json.loads((oldroot/'completion_receipt.json').read_text())
np=newroot/nr['selected_prediction_file'];op=oldroot/('val_predictions_epoch_%03d.csv'%orr['best_epoch_selected_by_validation_prefix_mape'])
ref=json.loads((newroot/'independent_metrics.json').read_text())
assert sha(newroot/'independent_metrics.json')=='8a93a622d341ec0846ec1768c03ddb72d9b73ff77e15ec3f15aca8685ed5678c'
for p in [np,op]:assert sha(p)==ref['bindings'][str(p.relative_to(ROOT))]
def load(p):
 rows=list(csv.DictReader(p.open()));d={}
 for x in rows:
  k=(x['file_name'],int(x['prefix_index']));assert k not in d
  y=float(x['label_total_life_cycles']);pred=float(x['prediction_total_life_cycles'])
  assert all(math.isfinite(v) for v in [y,pred]) and y>0
  assert abs(abs(pred-y)-float(x['absolute_error_cycles']))<1e-8
  d[k]=(y,pred)
 return d
old,new=load(op),load(np);assert old.keys()==new.keys()
cells=sorted({k[0] for k in old});assert len(cells)==15 and len(old)==1500
assert set(cells)==set(orr['validation_cells'])
assert set(cells).isdisjoint(orr['train_cells'])
paired=[]
for c in cells:
 assert sorted(k[1] for k in old if k[0]==c)==list(range(1,101))
 for k in range(1,101):
  y,a=old[c,k];yn,b=new[c,k];assert y==yn
  ea,eb=a-y,b-y
  paired.append(dict(cell=c,prefix_index=k,label_EOL_cycles=y,old_prediction=a,new_prediction=b,old_error=ea,new_error=eb,old_AE=abs(ea),new_AE=abs(eb),delta_AE_new_minus_old=abs(eb)-abs(ea),prediction_shift=b-a))
def metric(rr):
 return dict(old_MAE=mean(x['old_AE'] for x in rr),new_MAE=mean(x['new_AE'] for x in rr),delta_MAE=mean(x['delta_AE_new_minus_old'] for x in rr),old_bias=mean(x['old_error'] for x in rr),new_bias=mean(x['new_error'] for x in rr),prediction_shift=mean(x['prediction_shift'] for x in rr),improved_prefixes=sum(x['new_AE']<x['old_AE'] for x in rr),prefix_count=len(rr))
per=[]
for c in cells:
 rr=[x for x in paired if x['cell']==c];m=metric(rr)
 per.append(dict(cell=c,label_EOL=rr[0]['label_EOL_cycles'],**m,global_delta_contribution_cycles=m['delta_MAE']/15))
per.sort(key=lambda x:x['delta_MAE'],reverse=True)
bins=[(1,20),(21,40),(41,60),(61,80),(81,100)]
segments=[];cross=[]
for lo,hi in bins:
 rr=[x for x in paired if lo<=x['prefix_index']<=hi];m=metric(rr)
 segments.append(dict(prefix_segment='%d-%d'%(lo,hi),**m,global_delta_contribution_cycles=m['delta_MAE']*(hi-lo+1)/100))
 for c in cells:
  rr=[x for x in paired if x['cell']==c and lo<=x['prefix_index']<=hi];m=metric(rr)
  cross.append(dict(cell=c,prefix_segment='%d-%d'%(lo,hi),**m,global_delta_contribution_cycles=m['delta_MAE']*(hi-lo+1)/1500))
overall=metric(paired)
assert abs(overall['old_MAE']-ref['old_pilot_descriptive_comparison']['old_MAE'])<1e-8
assert abs(overall['new_MAE']-ref['cell_macro_EOL_MAE_cycles'])<1e-8
assert abs(mean(x['delta_MAE'] for x in per)-overall['delta_MAE'])<1e-8
assert abs(sum(x['global_delta_contribution_cycles'] for x in segments)-overall['delta_MAE'])<1e-8
assert abs(sum(x['global_delta_contribution_cycles'] for x in cross)-overall['delta_MAE'])<1e-8
pos=[x for x in per if x['delta_MAE']>0];neg=[x for x in per if x['delta_MAE']<0]
gross=sum(x['delta_MAE'] for x in pos)/15;offset=-sum(x['delta_MAE'] for x in neg)/15
concentration={}
for name in ['old','new']:
 rank=sorted(per,key=lambda x:x[name+'_MAE'],reverse=True)
 total=sum(x[name+'_MAE'] for x in rank)
 concentration[name]=dict(top1_cell=rank[0]['cell'],top1_share=rank[0][name+'_MAE']/total,top3_cells=[x['cell'] for x in rank[:3]],top3_share=sum(x[name+'_MAE'] for x in rank[:3])/total,macro_absolute_cell_bias=mean(abs(x[name+'_bias']) for x in per))
res=dict(status='PAIRED_PREDICTION_ATTRIBUTION_PASS_NO_GAIN',at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='HUST author total EOL validation only; descriptive accounting attribution, not causal or strict online RUL',selected_epochs=dict(old=orr['best_epoch_selected_by_validation_prefix_mape'],new=nr['best_epoch']),cells=15,paired_prefixes=1500,overall=overall,relative_MAE_increase=overall['delta_MAE']/overall['old_MAE'],worsened_cells=len(pos),improved_cells=len(neg),gross_worsening_contribution=gross,offsetting_improvement_contribution=offset,top3_worsening_cells=[x['cell'] for x in pos[:3]],top3_share_of_gross_worsening=sum(x['delta_MAE'] for x in pos[:3])/15/gross,top3_worsening_global_contribution=sum(x['delta_MAE'] for x in pos[:3])/15,concentration=concentration,segments=segments,per_cell=per,boundary='prefix_index is stored within-cell ordinal1..100; this report does not newly certify physical-cycle/raw-asof semantics',limitations=['LR, initialization RNG sequence and training duration differ simultaneously; no isolated causal LR claim','Same15-cell development validation reused for model selection; no independent confirmation','No removal of outliers, label edits, new selection, ensemble, calibration or train/test access','Old budget600steps, total neural2060steps and MATR41CPUfits remain unchanged; consumed PBT gate not reopened'],new_fits=0,optimizer_steps=0,test_access=False,model_loads=0,bindings={str(p.relative_to(ROOT)):sha(p) for p in [op,np,oldroot/'completion_receipt.json',newroot/'completion_receipt.json',newroot/'independent_metrics.json',ROOT/'src/experiments/cpmlp_hust_pilot.py',Path(__file__)]},minimum_validation=dict(unique_exact_keys=True,identical_labels=True,train_val_disjoint_by_filename=True,per_cell100_prefixes=True,existing_metrics_reconciled=True,cell_and_segment_and_cross_contributions_reconstruct_delta=True))
wc('paired_prediction_deltas.csv',paired);wc('per_cell.csv',per);wc('per_cell_prefix_segment.csv',cross);write('diagnosis.json',res)
text=['# CPMLP 配方负面结果：同电池、同前缀误差分解','',
'仅使用两份已选验证预测；旧epoch2、新epoch3；15电池×100前缀完全对齐，标签一致。单位为循环，主指标先电池内平均再电池等权。prefix_index按CSV中1..100序号分段，不新增认证物理循环或raw-asof语义。','',
'全局MAE %.6f → %.6f，增加%.6f（%.4f%%）；%d电池恶化、%d改善。'%(overall['old_MAE'],overall['new_MAE'],overall['delta_MAE'],100*res['relative_MAE_increase'],len(pos),len(neg)),
'恶化贡献 +%.6f，改善抵消 -%.6f，精确重构净增加。恶化前三%s占全部正向恶化%.3f%%，贡献全局+%.6f循环；不能将占净增量超过100%%解释为概率。'%(gross,offset,','.join(res['top3_worsening_cells']),100*res['top3_share_of_gross_worsening'],res['top3_worsening_global_contribution']),'',
'|电池|旧MAE|新MAE|变化 新-旧|旧bias|新bias|全局净增贡献|','|---|---:|---:|---:|---:|---:|---:|']
for x in per:text.append('|%s|%.3f|%.3f|%+.3f|%+.3f|%+.3f|%+.3f|'%(x['cell'],x['old_MAE'],x['new_MAE'],x['delta_MAE'],x['old_bias'],x['new_bias'],x['global_delta_contribution_cycles']))
text+=['','|前缀序号段|旧MAE|新MAE|变化|对全局净增贡献|','|---|---:|---:|---:|---:|']
for x in segments:text.append('|%s|%.3f|%.3f|%+.3f|%+.3f|'%(x['prefix_segment'],x['old_MAE'],x['new_MAE'],x['delta_MAE'],x['global_delta_contribution_cycles']))
text+=['','全局bias %+.6f → %+.6f；电池绝对bias均值 %.6f → %.6f。全局正负抵消不能代替绝对误差判断。'%(overall['old_bias'],overall['new_bias'],concentration['old']['macro_absolute_cell_bias'],concentration['new']['macro_absolute_cell_bias']),
'旧/新top1误差占比 %.3f%%/%.3f%%，top3占比 %.3f%%/%.3f%%。'%(100*concentration['old']['top1_share'],100*concentration['new']['top1_share'],100*concentration['old']['top3_share'],100*concentration['new']['top3_share']),'',
'判定：NO_GAIN保持。这里定位的是误差的算术来源，不能孤立归因学习率；初始化RNG顺序、时长同时不同，同15电池已重复用于开发选模。HUST作者总EOL适配不等于CALB/MIX完整复现或严格在线动态RUL。不删离群电池、不改标签或指标、不新增seed/fit。','',
'最小验证：1500唯一配对键与相同标签、每cell100前缀、文件名train/val隔离；旧/新主指标与冻结independent_metrics吻合，cell/分段/交叉贡献均重构原净增，误差<1e-8。新fits=0，optimizer_steps=0，model_loads=0，test_access=false。原始CSV、完成回执、参考指标和本程序的SHA见diagnosis.json。','',
'复算命令：/home/yndx/miniconda3/envs/a40_env/bin/python /home/yndx/zxk/rul/reports/cpmlp_recipe_error_diagnosis_20261018_root/diagnose.py （本目录create-only；复算时需另设OUT，不覆盖原证据）。','',
'下一步：只读现有逐epoch验证预测与epoch_metrics，检查两个已冻结MAPE选模点相对各自MAE最小点的差异；不改变选择规则、不重选汇报checkpoint、不新推理或训练。']
with (OUT/'DIAGNOSIS_ZH.md').open('x',encoding='utf-8') as f:f.write('\n'.join(text)+'\n')
print(json.dumps({k:v for k,v in res.items() if k not in ['per_cell','bindings','limitations']},ensure_ascii=True))
