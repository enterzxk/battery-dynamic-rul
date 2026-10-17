"""Existing-prediction diagnostic: train-only file-group median with frozen global fallback; no fit."""
from pathlib import Path
import json,csv,statistics,hashlib,datetime,math
R=Path('/home/yndx/zxk/rul');E=R/'experiments/cpmlp_calb_recipe_adapt_seed2021_v1';O=R/'reports/calb_group_prior_diagnosis_20261018_root'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(n,d):
 with (O/n).open('x',encoding='utf-8') as f:json.dump(d,f,indent=2,ensure_ascii=False);f.write('\n')
cfg=json.loads((E/'config.json').read_text());rec=json.loads((E/'completion_receipt.json').read_text());reference=json.loads((E/'independent_metrics.json').read_text());pred=E/rec['selected_prediction_file'];assert sha(pred)==rec['predictions_sha256']
stage=Path(cfg['stage_root']);m=json.loads((stage/'stage_manifest.json').read_text());lp=stage/'Life labels/CALB_labels.json';assert sha(lp)==m['labels']['sha256']
group=lambda name:name.split('_')[1]
protocol=dict(status='FROZEN_BEFORE_THIS_DIAGNOSTIC_CALCULATION',at_utc=now(),rule='Median of fixed17 training-cell authorEOL labels within filename second token; unsupported group uses fixed global training median. No validation tuning or minimum-support sweep.',group_source='Official CALB filename token known before prediction; no independent causal/physical temperature attribution',train_ids=cfg['split_files']['train'],validation_ids=cfg['split_files']['val'],source_of_prior_task='Previous root_result_decision.json next_action fixed group-conditional comparison before reading outcomes',prior_decision_sha256=sha(E/'root_result_decision.json'),test_access=False,new_fits=0,optimizer_steps=0,selection_changed=False)
write('protocol.json',protocol)
labels=json.loads(lp.read_text());train=cfg['split_files']['train'];val=cfg['split_files']['val'];assert not set(train)&set(val)
train_groups={}
for n in train:train_groups.setdefault(group(n),[]).append(labels[n])
global_median=float(statistics.median(labels[n] for n in train));priors={g:dict(train_cells=len(v),median=float(statistics.median(v)),min=min(v),max=max(v)) for g,v in train_groups.items()}
assert global_median==reference['train_only_median_EOL']
rows=list(csv.DictReader(pred.open()));assert len(rows)==497 and {r['file_name'] for r in rows}==set(val)
per=[]
for n in val:
 rr=[r for r in rows if r['file_name']==n];k=group(n);supported=k in priors;p=priors[k]['median'] if supported else global_median;y=labels[n]
 model=statistics.mean(abs(float(x['prediction_total_life_cycles'])-y) for x in rr);gm=abs(global_median-y);cm=abs(p-y)
 per.append(dict(cell=n,file_group=k,prefixes=len(rr),group_train_support=priors[k]['train_cells'] if supported else 0,used_global_fallback=not supported,group_prior_prediction=p,model_exact_author_MAE=model,global_prior_MAE=gm,group_prior_MAE=cm,global_to_model_gain=gm-model,global_to_group_gain=gm-cm,group_to_model_gain=cm-model,global_to_model_contribution=(gm-model)/5,global_to_group_contribution=(gm-cm)/5,group_to_model_contribution=(cm-model)/5))
model=statistics.mean(x['model_exact_author_MAE'] for x in per);gm=statistics.mean(x['global_prior_MAE'] for x in per);cm=statistics.mean(x['group_prior_MAE'] for x in per)
assert abs(model-reference['exact_author_label_MAE'])<1e-8 and abs(gm-reference['train_median_cell_equal_MAE'])<1e-8
assert abs((gm-model)-((gm-cm)+(cm-model)))<1e-8
sub={}
for label,items in [('group_supported',[x for x in per if not x['used_global_fallback']]),('unsupported_fallback',[x for x in per if x['used_global_fallback']])]:
 if items:
  sub[label]=dict(cells=len(items),model_MAE=statistics.mean(x['model_exact_author_MAE'] for x in items),group_prior_MAE=statistics.mean(x['group_prior_MAE'] for x in items),global_prior_MAE=statistics.mean(x['global_prior_MAE'] for x in items),group_to_model_gain_contribution=sum(x['group_to_model_contribution'] for x in items),global_to_model_gain_contribution=sum(x['global_to_model_contribution'] for x in items))
largest=max(per,key=lambda x:x['global_to_model_gain'])
res=dict(status='TRAIN_ONLY_GROUP_PRIOR_DIAGNOSTIC_COMPLETE',at_utc=now(),global_train_median=global_median,training_group_priors=priors,cell_equal_MAE=dict(model_exact_author=model,model_original_roundtrip_native=reference['cell_equal_EOL_MAE_cycles'],global_prior=gm,group_prior_with_fallback=cm),relative_MAE_reduction_vs_group_prior=1-model/cm,improved_cells_vs_group_prior=sum(x['model_exact_author_MAE']<x['group_prior_MAE'] for x in per),global_to_model_gain=gm-model,global_to_group_gain=gm-cm,group_to_model_gain=cm-model,fraction_global_gain_explained_by_group_prior=(gm-cm)/(gm-model),largest_global_gain_cell=largest['cell'],largest_global_gain_share=largest['global_to_model_gain']/sum(x['global_to_model_gain'] for x in per),per_cell=per,subgroups=sub,scope='Existing selected5-cell validation predictions; exact author labels used for all three comparators. Original frozen native metric retained separately; no checkpoint re-selection.',new_fits=0,optimizer_steps=0,new_inference=0,model_loads=0,test_access=False,bindings={str(pred.relative_to(R)):sha(pred),str((E/'independent_metrics.json').relative_to(R)):sha(E/'independent_metrics.json'),str(lp.relative_to(R)):sha(lp),str((E/'config.json').relative_to(R)):sha(E/'config.json'),str((O/'protocol.json').relative_to(R)):sha(O/'protocol.json'),str(Path(__file__).relative_to(R)):sha(Path(__file__))},limitations=['5 development cells/one seed and same-data model selection, no independent significance or generalization claim','Filename grouping is a legal static prior here, not a proven causal temperature effect; no validation labels used to estimate priors','Group45 support1, group25 support0 uses global fallback; supported/unsupported results must be separate','Full2GPU/test fidelity, physical identity/generator/strict online RUL restrictions unchanged'])
write('group_prior_diagnosis.json',res)
with (O/'per_cell_comparison.csv').open('x',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(per[0]));w.writeheader();w.writerows(per)
print(json.dumps(res,ensure_ascii=True))
