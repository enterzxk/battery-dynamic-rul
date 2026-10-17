from pathlib import Path
import json,csv,math,statistics,hashlib,datetime
r=Path('/home/yndx/zxk/rul');o=r/'experiments/dynamic_A_matr_retrospective_seed42_v1';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();f=r/'reports/dynamic_A_eligible_20261017_root/candidate_features.csv';rows=list(csv.DictReader(f.open()));train=[x for x in rows if x['split']=='train'];targets=['MATR_b1c2','MATR_b3c38'];fields=['soh','cumulative_discharge_Ah','capacity_slope_last20_Ah_per_cycle'];byid={x['cell_id']:x for x in rows};recp=r/'reports/matr_label_reconstruction_audit/per_cell_with_diff.jsonl';code=r/'repos/pinned/BatteryLife_3b17bb53202e10711deae0448c91f84144bb3dd9/process_scripts/Extract_life_labels.py';entries={}
for line in recp.open():
 x=json.loads(line);c=x['source_cell_id']
 if c in byid:entries[c]=x
assert len(entries)==133
boundary={}
for c in targets:
 x=entries[c];assert x['pinned_script_sha256']==sha(code);assert int(x['regression_float_before_int'])==x['author_v11_label'];boundary[c]={k:x[k] for k in ['cycle_rows','last_cycle_soh','rule','regression_float_before_int','reconstructed_label','author_v11_label','first_crossing_row','metadata_sha256','cycle_summary_sha256']};boundary[c]['float_minus_followup']=x['regression_float_before_int']-x['cycle_rows']
labelstats={}
for role in ['train','val']:
 cc=[c for c in entries if byid[c]['split']==role and entries[c]['rule'].startswith('last20')];gaps=[entries[c]['author_v11_label']-entries[c]['cycle_rows'] for c in cc];labelstats[role]={'tail_regression_cells':len(cc),'author_EOL_at_or_before_observed_end':sum(g<=0 for g in gaps),'author_minus_followup_range':[min(gaps),max(gaps)],'warning':'These are author regression targets, not guaranteed future failure events; no label edits or test role evaluated.'}
result={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'COMPLETE_EXISTING_TEXT_LABEL_AND_SUPPORT_DIAGNOSIS','label_boundary':boundary,'eligible_train_val_label_boundary':labelstats,'training_author_EOL_range':[min(float(x['author_EOL']) for x in train),max(float(x['author_EOL']) for x in train)],'feature_support':[],'method':'Within each fixed k, compare target to training-only marginal ranges and nearest same-batch training cells in 3D (SOH,cumulativeAh,rate), standardized using all train cells at that k. Neighbors chosen by features only, labels shown after selection; descriptive, no predictive model fitted.','bindings':{str(p.relative_to(r)):sha(p) for p in [f,recp,code,o/'validation_predictions.csv']},'new_fits':0,'optimizer_steps':0,'label_reconstructions_rerun':0,'binary_reads':0,'test_inference':False,'strict_online_claim':False}
for c in targets:
 for target in [x for x in rows if x['cell_id']==c]:
  k=int(target['k']);tt=[x for x in train if int(x['k'])==k];same=[x for x in tt if [x[b] for b in ['batch2','batch3','batch4']]==[target[b] for b in ['batch2','batch3','batch4']]];assert same
  sd={name:statistics.pstdev(float(x[name]) for x in tt) for name in fields};detail={}
  for name in fields:
   vv=[float(x[name]) for x in tt];v=float(target[name]);ss=[float(x[name]) for x in same];detail[name]={'target':v,'all_train_min':min(vv),'all_train_max':max(vv),'all_train_percentile_le':sum(z<=v for z in vv)/len(vv),'outside_all_train_range':v<min(vv) or v>max(vv),'same_batch_min':min(ss),'same_batch_max':max(ss),'outside_same_batch_range':v<min(ss) or v>max(ss)}
  dist=lambda x:math.sqrt(sum(((float(x[name])-float(target[name]))/sd[name])**2 for name in fields if sd[name]>0));nearest=sorted(same,key=lambda x:(dist(x),x['cell_id']))[:3]
  result['feature_support'].append({'cell_id':c,'k':k,'train_cells':len(tt),'same_batch_train_cells':len(same),'feature_marginals':detail,'nearest_same_batch':[{'cell_id':x['cell_id'],'distance_train_sd_units':dist(x),'author_EOL':float(x['author_EOL'])} for x in nearest],'target_author_EOL':float(target['author_EOL'])})
result['interpretation']='The b3c38 float target is already before observed followup (1932.623<1933); int() further truncates to1932. This is consistent with unconstrained inverse tail-SOH regression, not simply one-based indexing or rounding alone. Code consistency does not validate event semantics or actual v11 provenance. Feature marginals/neighbor labels diagnose support and ambiguity, not causal explanation or a new predictive gain.'
with (o/'label_boundary_feature_support.json').open('x') as out:json.dump(result,out,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in result.items() if k not in ['feature_support','bindings']},ensure_ascii=False))
for x in result['feature_support']:print(json.dumps({'cell':x['cell_id'],'k':x['k'],'outside_all':[n for n,v in x['feature_marginals'].items() if v['outside_all_train_range']],'outside_samebatch':[n for n,v in x['feature_marginals'].items() if v['outside_same_batch_range']],'neighbors':x['nearest_same_batch']},ensure_ascii=False))
