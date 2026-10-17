import csv,json,pathlib,hashlib,statistics,random,datetime,math
r=pathlib.Path('/home/yndx/zxk/rul');out=r/'experiments/dynamic_A_matr_retrospective_seed42_v1';src=out/'validation_predictions.csv'
rows=list(csv.DictReader(src.open()));receipt=json.loads((out/'completion_receipt.json').read_text());models=sorted({x['model'] for x in rows})
mean=statistics.mean
q=lambda a,p: sorted(a)[min(len(a)-1,max(0,math.ceil(p*len(a))-1))]
result={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'Independent csv/stdlib recomputation, cell mean over fixed origins then equal-cell mean; errors prediction minus target; no fits','predictions_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'scores':{},'comparisons':{}}
for lane in ['author_EOL_all_validation','observed_crossing_validation_only']:
 subset=[x for x in rows if lane.startswith('author') or x['event_status']=='observed'];target='author_RUL' if lane.startswith('author') else None
 cellmaes={}
 for model in models:
  rr=[x for x in subset if x['model']==model];cells=sorted({x['cell_id'] for x in rr});errors={c:[] for c in cells}
  for x in rr:
   truth=float(x[target]) if target else float(x['observed_EOL'])-int(x['k']);pred=float(x['predicted_RUL']);assert math.isclose(pred,max(0,float(x['predicted_EOL'])-int(x['k'])),abs_tol=1e-8)
   errors[x['cell_id']].append(pred-truth)
  maes={c:mean(abs(v) for v in vv) for c,vv in errors.items()};cellmaes[model]=maes
  score={'cells':len(cells),'origins':len(rr),'cell_macro_Time_MAE_cycles':mean(maes.values()),'cell_macro_signed_bias_cycles':mean(mean(v) for v in errors.values()),'p90_cell_MAE_cycles':q(list(maes.values()),.9),'p90_cell_worst_overestimate_cycles':q([max(0,max(v)) for v in errors.values()],.9),'cells_any_overestimate_ge200_cycles':sum(max(v)>=200 for v in errors.values()),'by_origin':{}}
  for k in [50,100,150,200]:
   kk=[x for x in rr if int(x['k'])==k];errs=[float(x['predicted_RUL'])-(float(x['author_RUL']) if target else float(x['observed_EOL'])-k) for x in kk]
   score['by_origin'][str(k)]={'cells':len(kk),'Time_MAE_cycles':mean(abs(v) for v in errs),'bias_cycles':mean(errs)}
  result['scores'][model+'|'+lane]=score
  old=receipt['scores'][model+'|'+lane]
  assert math.isclose(score['cell_macro_Time_MAE_cycles'],old['cell_macro_Time_MAE_cycles'],rel_tol=1e-10,abs_tol=1e-8)
  assert math.isclose(score['cell_macro_signed_bias_cycles'],old['cell_macro_signed_bias_cycles'],rel_tol=1e-10,abs_tol=1e-8)
 for baseline,added in [('A0','A1'),('A1','A2'),('GBDT_A1','GBDT_A2')]:
  if baseline not in models or added not in models:continue
  cells=sorted(cellmaes[baseline]);base=[cellmaes[baseline][c] for c in cells];new=[cellmaes[added][c] for c in cells];delta=[a-b for a,b in zip(base,new)];rng=random.Random(42);boots=[]
  for _ in range(2000):
   ii=[rng.randrange(len(cells)) for _ in cells];boots.append(1-mean(new[i] for i in ii)/mean(base[i] for i in ii))
  positives=sorted([max(0,d) for d in delta],reverse=True)
  result['comparisons'][added+'_vs_'+baseline+'|'+lane]={'relative_Time_MAE_reduction':1-mean(new)/mean(base),'improved_cells':sum(v>0 for v in delta),'cells':len(cells),'improved_fraction':sum(v>0 for v in delta)/len(cells),'paired_mean_MAE_improvement_cycles':mean(delta),'paired_bootstrap_95pct_relative_reduction':[q(boots,.025),q(boots,.975)],'top2_share_of_positive_improvement':sum(positives[:2])/sum(positives) if sum(positives)>0 else None,'bootstrap_note':'exploratory only; serial and processed-generator unresolved; not independent confirmation'}
a=result['comparisons']['A2_vs_A1|author_EOL_all_validation'];g=result['comparisons'].get('GBDT_A2_vs_GBDT_A1|author_EOL_all_validation')
if a['relative_Time_MAE_reduction']>=.10 and a['improved_fraction']>=.60:
 verdict='EXPLORATORY_SIGNAL_REQUIRES_OBSERVED_LANE_AND_TAIL_REVIEW'
elif a['relative_Time_MAE_reduction']<.05 and g and (g['relative_Time_MAE_reduction']<=0 or g['improved_fraction']<.60):verdict='NO_GAIN_FOR_COMPLEX_HISTORY_EXPANSION_ON_THIS_DIAGNOSTIC'
else:verdict='INCONCLUSIVE_NO_COMPLEX_MODEL_EXPANSION'
result.update(preliminary_rule_verdict=verdict,checks='All saved primary/subgroup MAE and bias reproduced; prediction=clip(EOL-k) checked for every row',new_fits=0,optimizer_steps=0)
ledger=[json.loads(x) for x in (out/'fit_ledger.jsonl').read_text().splitlines()];result['fit_ledger_audit']={'started':sum(x['event']=='fit_started' for x in ledger),'completed':sum(x['event']=='fit_completed' for x in ledger),'model_counts':{m:sum(x.get('model')==m for x in ledger) for m in ['Ridge','HistGradientBoostingRegressor']}}
assert result['fit_ledger_audit']['started']==result['fit_ledger_audit']['completed']==receipt['new_predictive_fits']
with (out/'independent_metrics.json').open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in result.items() if k!='scores'},ensure_ascii=False));print('SCORES',json.dumps({k:{kk:vv for kk,vv in v.items() if kk!='by_origin'} for k,v in result['scores'].items()}))
