import pathlib,json,csv,hashlib,collections
import numpy as np
R=pathlib.Path('/home/yndx/zxk/rul');H=R/'experiments/rulaas_gain_learning_20261029';O=H/'run01';D=R/'experiments/rulaas_gain_identifiability_20261029/run02';A=R/'reports/rulaas_gain_review_20261029_terra'
def readcsv(p):
 with p.open() as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rec=json.loads((O/'receipt.json').read_text());audit=json.loads((A/'AUDIT.json').read_text());split=json.loads((D/'cell_split.json').read_text())
if rec['status']!='SUCCESS' or rec['predictive_estimator_fits_completed']!=5 or rec['preprocessor_components_fit']!=4 or not rec['all_fits_before_held_predictions'] or rec['C3_payload_reads'] or rec['C4_payload_reads'] or audit['status']!='PASS':raise ValueError('receipt')
for path,digest in rec['input_sha256'].items():
 if sha(R/path)!=digest:raise ValueError('input hash')
cases=readcsv(D/'cases.csv');raw=readcsv(O/'predictions.csv');summary=readcsv(O/'summary.csv');bycase={int(z['case_id']):z for z in cases}
train=[z for z in cases if z['population']=='kernel_fit'];val=[z for z in cases if z['population']=='kernel_held'];trainids={z['cell_id'] for z in train};valids={z['cell_id'] for z in val}
if len(train)!=101 or len(val)!=85 or len(trainids)!=24 or len(valids)!=24 or trainids&valids or not valids<=set(split['base_head_unseen_cells']) or valids&set(split['base_head_fit_cells']):raise ValueError('split')
counts=collections.Counter(z['cell_id'] for z in train);ys=np.asarray([float(z['label_gain_7day_delivery_weeks']) for z in train]);weights=np.asarray([1/counts[z['cell_id']] for z in train]);order=np.argsort(ys,kind='mergesort');median=float(ys[order][np.searchsorted(np.cumsum(weights[order]),weights.sum()/2,side='left')])
cell_errors=collections.defaultdict(lambda:collections.defaultdict(list));seen=collections.defaultdict(set)
for z in raw:
 cid=z['cell_id'];caseid=int(z['case_id']);model=z['model'];src=bycase[caseid]
 if src['population']!='kernel_held' or src['cell_id']!=cid or caseid in seen[model]:raise ValueError('evaluation key')
 y=float(src['label_gain_7day_delivery_weeks']);pred=float(z['predicted_gain_weeks']);error=abs(y-pred)
 if abs(float(z['observed_gain_weeks'])-y)>1e-10 or abs(float(z['absolute_gain_prediction_error'])-error)>1e-10:raise ValueError('prediction error')
 cell_errors[model][cid].append(error);seen[model].add(caseid)
expected={int(z['case_id']) for z in val}
if len(seen)!=6 or any(v!=expected for v in seen.values()):raise ValueError('common evaluation keys')
for z in val:
 y=float(z['label_gain_7day_delivery_weeks']);cell_errors['zero_gain'][z['cell_id']].append(abs(y));cell_errors['train_cell_weighted_median'][z['cell_id']].append(abs(y-median))
m={model:{cid:float(np.mean(v)) for cid,v in cells.items()} for model,cells in cell_errors.items()}
if any(set(cells)!=valids for cells in m.values()):raise ValueError('common cell metric')
scores={k:float(np.mean(list(v.values()))) for k,v in m.items()}
maxerror=max(abs(scores[z['model']]-float(z['cell_macro_gain_MAE'])) for z in summary)
if maxerror>1e-10:raise ValueError('summary discrepancy')
comparisons=[];groups=sorted({cid.rsplit('C',1)[0] for cid in valids});rng=np.random.RandomState(42);draw=rng.randint(len(groups),size=(5000,len(groups)))
for model in ['ridge_age_point','ridge_F2_point','hgb_F0_point','hgb_F2_point','hgb_F3_point']:
 ds={cid:m[model][cid]-m['zero_gain'][cid] for cid in valids}
 sums=np.asarray([sum(ds[cid] for cid in valids if cid.rsplit('C',1)[0]==g) for g in groups]);ns=np.asarray([sum(cid.rsplit('C',1)[0]==g for cid in valids) for g in groups])
 boot=sums[draw].sum(1)/ns[draw].sum(1)
 comparisons.append({'model':model,'reference':'zero_gain','delta_cell_macro_gain_MAE':float(np.mean(list(ds.values()))),'exploratory_group_bootstrap_95_CI':[float(np.quantile(boot,.025)),float(np.quantile(boot,.975))],'cells_better_than_zero':sum(x<0 for x in ds.values()),'cells_worse_than_zero':sum(x>0 for x in ds.values()),'worst_cell':max(ds,key=ds.get),'worst_cell_delta':float(max(ds.values())),'post_hoc':True})
out={'status':'PASS','actual_coordinator_model':'gpt-6.1-terra','model_choice':'User explicitly chose Terra after repository model preference was disclosed.','new_fits':0,'new_inference_rows':0,'C3_payload_reads':0,'C4_payload_reads':0,'original_predictive_estimator_fits':5,'original_preprocessing_fits':4,'held_cases':len(val),'held_cells':len(valids),'held_groups':len(groups),'all_models_share_case_keys':True,'recomputed_MAE_max_error':maxerror,'zero_gain_MAE':scores['zero_gain'],'training_cell_weighted_median':median,'weighted_median_gain_MAE':scores['train_cell_weighted_median'],'all_models_cell_macro_gain_MAE':scores,'post_hoc_zero_comparisons':comparisons,'limitations':['zero and median references were added after seeing the pilot and are exploratory','zero gain is a prediction baseline, not a recommended no-inspection policy','kernel-fit gain labels came from a head trained on those cells; held labels came from unseen cells','24 held historical cells are not an independent paper confirmation','no pending report, fleet replay or SLO validation'],'inputs_sha256':{str(x.relative_to(R)):sha(x) for x in [O/'predictions.csv',O/'summary.csv',O/'paired_contrasts.csv',O/'receipt.json',D/'cases.csv',D/'cell_split.json']}}
with (O/'INDEPENDENT_RECOMPUTE.json').open('x') as f:json.dump(out,f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps(out,ensure_ascii=False))
