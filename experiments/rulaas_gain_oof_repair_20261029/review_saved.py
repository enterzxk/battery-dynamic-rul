#!/usr/bin/env python3
"""Independent arithmetic and split audit of saved OOF-label reconstruction."""
import csv,json,pathlib,collections,hashlib,math
import numpy as np
R=pathlib.Path('/home/yndx/zxk/rul');D=R/'experiments/rulaas_gain_oof_repair_20261029/run01';O=R/'experiments/rulaas_gain_identifiability_20261029/run02'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def rows(p):
 with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
old=rows(O/'cases.csv');new=rows(D/'cases.csv');points=rows(D/'crossfit_train_points.csv');split=read(O/'cell_split.json');folds=read(D/'fold_manifest.json')['folds'];receipt=read(D/'receipt.json')
assert receipt['status']=='SUCCESS' and receipt['predictive_fits_completed']==3 and receipt['predictive_fits_started']==3 and receipt['model_prediction_rows']==1395 and receipt['C3_payload_reads']==receipt['C4_payload_reads']==0
assert len(old)==len(new)==186 and len(points)==808
basefit=set(split['base_head_fit_cells']);held=set(split['base_head_unseen_cells']);heldselected=set(split['selected_kernel_held']);selected=set(split['selected_kernel_fit'])
assert len(basefit)==len(held)==60 and not basefit&held
cover=set()
for f in folds:
 train=set(f['train_cells']);excluded=set(f['excluded_oof_cells']);recorded_held=set(f['original_held_cells_excluded'])
 assert len(train)==40 and len(excluded)==20 and train|excluded==basefit and not train&excluded and not train&held and recorded_held==held
 assert not cover&excluded;cover|=excluded
assert cover==basefit
xo=np.load(O/'request_features.npz',allow_pickle=False)['X_request'];xn=np.load(D/'request_features.npz',allow_pickle=False)['X_request']
assert xo.shape==xn.shape==(186,711)
bycase=collections.defaultdict(list)
for z in points:bycase[int(z['case_id'])].append(z)
changes=collections.defaultdict(list);labels0=[];labels1=[];maxerr=0.;timing_checks=0
for i,(a,b) in enumerate(zip(old,new)):
 assert int(a['case_id'])==int(b['case_id'])==i and a['population']==b['population'] and a['cell_id']==b['cell_id']
 assert np.array_equal(xo[i,:710],xn[i,:710],equal_nan=True)
 if a['population']=='kernel_held':
  assert a==b and np.array_equal(xo[i],xn[i],equal_nan=True) and a['cell_id'] in heldselected
  continue
 assert a['population']=='kernel_fit' and a['cell_id'] in selected and len(bycase[i])==8
 assert np.float32(float(b['input_point_proxy_RUL']))==xn[i,710]
 f=next(x for x in folds if a['cell_id'] in x['excluded_oof_cells'])
 assert a['cell_id'] not in f['train_cells']
 g0=g7=0.;alive=0
 for k,z in enumerate(sorted(bycase[i],key=lambda x:int(x['slot'])),1):
  assert int(z['slot'])==k and int(z['fold'])==f['fold'] and z['cell_id']==a['cell_id'] and z['source_rpt_index']==a['source_rpt_index']
  q=float(a['request_epoch'])+k*.5*604800.;event=float(a['source_event_epoch']);stop=float(a['future_candidate_stop_epoch'])
  assert float(z['query_epoch'])==q
  if q<event:
   assert z['pre_reference_event']=='True';y=(event-q)/604800.;assert abs(float(z['true_RUL'])-y)<1e-10
   no=float(z['point_no_candidate']);now=float(z['point_stop_delivery']);delay=float(z['point_7day_delivery'])
   if q<stop:assert no==now;timing_checks+=1
   if q<stop+7*86400.:assert no==delay;timing_checks+=1
   v0=abs(no-y)-abs(now-y);v7=abs(no-y)-abs(delay-y);alive+=1
   assert abs(v0-float(z['gain_stop_delivery']))<1e-10 and abs(v7-float(z['gain_7day_delivery']))<1e-10
  else:
   assert z['pre_reference_event']=='False' and not z['point_no_candidate'] and not z['point_stop_delivery'] and not z['point_7day_delivery']
   assert float(z['gain_stop_delivery'])==float(z['gain_7day_delivery'])==0.;v0=v7=0.
  g0+=v0/8.;g7+=v7/8.
 assert alive==int(b['label_pre_event_slots'])
 e=max(abs(g0-float(b['label_gain_stop_delivery_weeks'])),abs(g7-float(b['label_gain_7day_delivery_weeks'])));maxerr=max(maxerr,e)
 assert e<1e-10
 original=float(a['label_gain_7day_delivery_weeks']);corrected=float(b['label_gain_7day_delivery_weeks']);labels0.append(original);labels1.append(corrected);changes[a['cell_id']].append(corrected-original)
assert len(labels0)==101 and len(changes)==24
percell=[dict(cell_id=cid,n_cases=len(d),mean_change_weeks=float(np.mean(d)),mean_absolute_change_weeks=float(np.mean(np.abs(d)))) for cid,d in sorted(changes.items())]
with (D/'per_cell_label_change.csv').open('x',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(percell[0]));w.writeheader();w.writerows(percell)
out=dict(status='PASS',new_fits=0,new_inference_rows=0,C3_payload_reads=0,C4_payload_reads=0,training_cases=101,held_cases=85,training_cells=24,held_cells=24,slot_checks=len(points),pre_arrival_prediction_identity_checks=timing_checks,max_recomputed_label_error=maxerr,all_training_710_input_values_and_held_711_inputs_unchanged=True,held_case_rows_unchanged=True,all_three_heads_exclude_all_60_original_held_cells=True,own_cell_excluded_from_its_training_head=True,case_weighted_old_gain_mean=float(np.mean(labels0)),case_weighted_crossfit_gain_mean=float(np.mean(labels1)),paired_absolute_mean_change=float(np.mean(np.abs(np.asarray(labels1)-np.asarray(labels0)))),cell_macro_change=float(np.mean([x['mean_change_weeks'] for x in percell])),old_negative=int((np.asarray(labels0)<-1e-9).sum()),crossfit_negative=int((np.asarray(labels1)<-1e-9).sum()),limits=['No change in held labels or input; this is a diagnostic, not a measured RUL improvement.','The 40-cell versus 60-cell head training sizes differ, so change cannot be attributed solely to removing in-sample optimism.','Splits are by physical cell; shared operating groups can cross folds.','Passive information-withholding and fixed 7-day hypothetical delivery; no pending variation.'],input_sha256={str(p.relative_to(R)):sha(p) for p in [O/'cases.csv',O/'request_features.npz',O/'cell_split.json',D/'cases.csv',D/'request_features.npz',D/'crossfit_train_points.csv',D/'fold_manifest.json',D/'receipt.json']})
with (D/'INDEPENDENT_RECOMPUTE.json').open('x',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps(out,ensure_ascii=False))
