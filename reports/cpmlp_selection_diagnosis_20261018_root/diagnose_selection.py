"""Audit existing epoch summaries; no model, inference, training or checkpoint selection."""
from pathlib import Path
import json,csv,statistics,math,hashlib,datetime
R=Path('/home/yndx/zxk/rul');O=R/'reports/cpmlp_selection_diagnosis_20261018_root'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
old=R/'experiments/cpmlp_hust_pilot_seed42/fit_runs/fit_20261016T034610_311103Z'
new=R/'experiments/cpmlp_hust_recipe_adapt_seed42_v2'
previous=R/'reports/cpmlp_recipe_error_diagnosis_20261018_root/diagnosis.json'
bindings={str(p.relative_to(R)):sha(p) for p in [old/'epoch_metrics.jsonl',new/'epoch_metrics.jsonl',old/'completion_receipt.json',new/'completion_receipt.json',previous,Path(__file__)]}
prev=json.loads(previous.read_text())
for p in [old/'completion_receipt.json',new/'completion_receipt.json']:assert sha(p)==prev['bindings'][str(p.relative_to(R))]
rows=[];runs={}
for name,p in [('old_pilot',old),('new_recipe',new)]:
 rec=json.loads((p/'completion_receipt.json').read_text());series=[]
 for l in (p/'epoch_metrics.jsonl').read_text().splitlines():
  x=json.loads(l);m=x.get('validation_metrics',x.get('validation_metrics_native_cycles'))
  cells=m['per_cell'];assert len(cells)==15 and len({c['file_name'] for c in cells})==15 and all(c['prefixes']==100 for c in cells)
  mae=statistics.mean(c['mae_cycles'] for c in cells);mape=statistics.mean(c['mape'] for c in cells)
  assert abs(mae-m['cell_equal_mae_cycles'])<1e-8 and abs(mape-m['prefix_mean_mape'])<1e-10
  batches=x.get('train_batches_completed',x.get('train_batches'));complete=x.get('epoch_complete',batches==146)
  z=dict(run=name,epoch=x['epoch'],steps=x['optimizer_steps_total'],train_batches=batches,epoch_complete=complete,MAE=mae,MAPE=mape);series.append(z);rows.append(z)
 selected=rec.get('best_epoch',rec.get('best_epoch_selected_by_validation_prefix_mape'))
 best_mape=min(series,key=lambda x:(x['MAPE'],x['epoch']));best_mae=min(series,key=lambda x:(x['MAE'],x['epoch']))
 full=[x for x in series if x['epoch_complete']]
 assert selected==best_mape['epoch']
 chosen=next(x for x in series if x['epoch']==selected)
 runs[name]=dict(recorded_validation_epochs=len(series),full_validation_epochs=len(full),frozen_selected_epoch=selected,minimum_MAPE_epoch=best_mape['epoch'],minimum_MAE_epoch=best_mae['epoch'],minimum_MAE_full_epoch=min(full,key=lambda x:x['MAE'])['epoch'],MAE_at_frozen_selection=chosen['MAE'],minimum_recorded_MAE=best_mae['MAE'],selection_MAE_penalty=chosen['MAE']-best_mae['MAE'],selected_MAPE=chosen['MAPE'])
assert len(rows)==13 and runs['old_pilot']['selection_MAE_penalty']==0 and runs['new_recipe']['selection_MAE_penalty']==0
a=next(x for x in rows if x['run']=='old_pilot' and x['steps']==292);b=next(x for x in rows if x['run']=='new_recipe' and x['steps']==292)
last=next(x for x in rows if x['run']=='new_recipe' and x['epoch']==10)
res=dict(status='NO_MAPE_MAE_SELECTION_DISCREPANCY_IN_RECORDED_EPOCHS',at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),runs=runs,same292steps=dict(old_MAE=a['MAE'],new_MAE=b['MAE'],new_minus_old=b['MAE']-a['MAE'],relative_increase=b['MAE']/a['MAE']-1),new_last_vs_selected=dict(last_epoch=10,last_MAE=last['MAE'],selected_epoch=3,selected_MAE=runs['new_recipe']['MAE_at_frozen_selection'],increase_cycles=last['MAE']-runs['new_recipe']['MAE_at_frozen_selection']),decision='NO_GAIN unchanged; frozen MAPE selections also minimize recorded MAE, so selection-objective mismatch does not explain the observed regression. No checkpoint reselection.',limitations=['Only recorded13 validation events; old epoch3 is partial8 batches and is explicitly labelled','Same development15 cells repeatedly used for selection; not independent/generalization/test evidence','Same optimizer-step count is descriptive only: LR and initialization RNG sequence differ; no isolated causal inference','HUST author total EOL recipe adaptation, not full CALB/MIX reproduction or strict online RUL'],new_fits=0,optimizer_steps=0,model_loads=0,new_inference=0,test_access=False,checkpoint_selection_changed=False,bindings=bindings)
with (O/'selection_diagnosis.json').open('x',encoding='utf-8') as f:json.dump(res,f,ensure_ascii=False,indent=2);f.write('\n')
with (O/'epoch_comparison.csv').open('x',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
md=['# CPMLP 冻结MAPE选模点与MAE最小点核查','','已完成旧3条与新10条验证事件的定向复算。旧epoch3仅8训练batch，为partial；新10个epoch均146batch完整。这里只读JSON和已存指标，无checkpoint/数据二进制或test。','',
'结论：已记录epoch中不存在MAPE与MAE选模点不一致。旧pilot均在epoch2最小，新recipe均在epoch3最小，MAE选模惩罚均为0循环；NO_GAIN保持，不能用改选checkpoint解释或修复当前回退。','',
'|运行|冻结选择epoch|MAPE最小epoch|MAE最小epoch|所选MAE|MAE惩罚|','|---|---:|---:|---:|---:|---:|']
for name,x in runs.items():md.append('|%s|%d|%d|%d|%.6f|%.6f|'%(name,x['frozen_selected_epoch'],x['minimum_MAPE_epoch'],x['minimum_MAE_epoch'],x['MAE_at_frozen_selection'],x['selection_MAE_penalty']))
md+=['','|运行|epoch|累计steps|完整epoch|MAE循环|MAPE|','|---|---:|---:|---|---:|---:|']
for x in rows:md.append('|%s|%d|%d|%s|%.6f|%.9f|'%(x['run'],x['epoch'],x['steps'],x['epoch_complete'],x['MAE'],x['MAPE']))
md+=['','相同292 optimizer steps处：旧MAE %.6f、新%.6f，差%+.6f（%.4f%%）。配方/初始化不同，不能解释为LR单独作用。新epoch10 MAE %.6f，比已选epoch3差%.6f，额外完成epoch没有带来已记录验证收益；这不证明一般性过拟合机理。'%(a['MAE'],b['MAE'],b['MAE']-a['MAE'],100*(b['MAE']/a['MAE']-1),last['MAE'],last['MAE']-runs['new_recipe']['MAE_at_frozen_selection']),'',
'最小验证：13个事件均15电池×100前缀；由per_cell重新求电池等权MAE和MAPE，吻合记录（MAE<1e-8、MAPE<1e-10）；记录的严格最小MAPE epoch吻合completion回执。源epoch JSONL、完成回执、前轮诊断和本脚本SHA见selection_diagnosis.json。未重跑旧独立复算或smoke，new_fits=0、optimizer_steps=0、new_inference=0。','',
'下一步：转回P1忠实复现缺口，只读官方CPMLP CALB脚本及已有数据/标签/拆分凭证、stat，确定最早缺失项；不加载数据、构造模型或训练，不重复HUST开发调参。']
with (O/'SELECTION_DIAGNOSIS_ZH.md').open('x',encoding='utf-8') as f:f.write('\n'.join(md)+'\n')
print(json.dumps({k:v for k,v in res.items() if k not in ['bindings','limitations']},ensure_ascii=True))
