from pathlib import Path
import json,csv,statistics,math,hashlib,datetime,subprocess,fcntl
r=Path('/home/yndx/zxk/rul');o=r/'experiments/dynamic_A_matr_retrospective_seed42_v1';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();state=r/'automation/state/coordinator.json';me='01a14a80-7add-70c2-b412-5f0ae4be2c80'
c=json.loads(state.read_text());assert c['owner']==c['thread_id']==me;assert sha(Path(c['handoff_file']))==c['handoff_sha256'];status=json.loads(subprocess.run(['./rul.sh','status'],cwd=str(r),capture_output=True,text=True,check=True).stdout);ps=subprocess.run(['ps','-eo','pid,args'],capture_output=True,text=True).stdout;assert not [x for x in ps.splitlines() if 'dynamic_A_matr_retrospective_seed42_v1/runner.py' in x]
p=o/'validation_predictions.csv';orig=json.loads((o/'completion_receipt.json').read_text());assert sha(p)==orig['predictions_sha256'];rr=list(csv.DictReader(p.open()));features=list(csv.DictReader((r/'reports/dynamic_A_eligible_20261017_root/candidate_features.csv').open()));labels={x['cell_id']:float(x['author_EOL']) for x in features if x['split']=='train'};lo,hi=min(labels.values()),max(labels.values());models=sorted({x['model'] for x in rr});cells=sorted({x['cell_id'] for x in rr});assert len(cells)==34
records=[]
for cid in cells:
 cr=[x for x in rr if x['cell_id']==cid];assert len({float(x['author_EOL']) for x in cr})==1;eol=float(cr[0]['author_EOL']);event=cr[0]['event_status'];record={'cell_id':cid,'author_EOL':eol,'observation_status':event,'training_EOL_support':'below_train_min' if eol<lo else ('above_train_max' if eol>hi else 'within_train_range'),'models':{}}
 for model in models:
  mr=[x for x in cr if x['model']==model];assert sorted(int(x['k']) for x in mr)==[50,100,150,200];errors=[float(x['predicted_RUL'])-float(x['author_RUL']) for x in mr];record['models'][model]={'MAE':statistics.mean(abs(e) for e in errors),'bias':statistics.mean(errors)}
 records.append(record)
partitions={'train_EOL_support':lambda x:x['training_EOL_support'],'observed_or_censored':lambda x:x['observation_status'],'support_x_observation':lambda x:x['training_EOL_support']+'|'+x['observation_status']};parts={}
for name,key in partitions.items():
 groups={}
 for group in sorted({key(x) for x in records}):
  gr=[x for x in records if key(x)==group];n=len(gr);metrics={}
  for model in models:
   mae=statistics.mean(x['models'][model]['MAE'] for x in gr);bias=statistics.mean(x['models'][model]['bias'] for x in gr);total=orig['scores'][model+'|author_EOL_all_validation']['cell_macro_Time_MAE_cycles'];metrics[model]={'MAE_cycles':mae,'bias_cycles':bias,'contribution_to_all34_MAE_cycles':mae*n/34,'share_of_all34_absolute_error':mae*n/(34*total)}
  comparisons={}
  for a,b in [('A0','A1'),('A1','A2'),('GBDT_A1','GBDT_A2')]:
   base=metrics[a]['MAE_cycles'];added=metrics[b]['MAE_cycles'];delta=base-added;fulldelta=orig['scores'][a+'|author_EOL_all_validation']['cell_macro_Time_MAE_cycles']-orig['scores'][b+'|author_EOL_all_validation']['cell_macro_Time_MAE_cycles'];comparisons[b+'_vs_'+a]={'relative_MAE_reduction_in_group':1-added/base,'improved_cells':sum(x['models'][b]['MAE']<x['models'][a]['MAE'] for x in gr),'contribution_to_all34_MAE_improvement_cycles':delta*n/34,'share_of_all34_net_improvement':delta*n/(34*fulldelta) if fulldelta else None}
  groups[group]={'cells':n,'cell_ids':[x['cell_id'] for x in gr],'models':metrics,'comparisons':comparisons}
 for model in models:
  assert math.isclose(sum(g['models'][model]['contribution_to_all34_MAE_cycles'] for g in groups.values()),orig['scores'][model+'|author_EOL_all_validation']['cell_macro_Time_MAE_cycles'],abs_tol=1e-8)
 assert sum(g['cells'] for g in groups.values())==34;parts[name]=groups
out={'status':'COMPLETE_FIXED_COHORT_ERROR_CONTRIBUTION','at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'training_author_EOL_range':[lo,hi],'fixed_validation_cells':34,'fixed_origins_per_cell':4,'partitions':parts,'per_cell':records,'verification':'Every partition covers same34 cells and weighted contributions reconstruct original all34 MAE for all5 models. No cell omitted or new main metric selected.','interpretation':'Groups use retrospective outcomes for explanation only, never to filter train/evaluation origins or features. In-range means target-label range only, not feature distribution, physical independence or online safety. Censored author-label MAE is label agreement, not true-event MAE. Original primary metrics and NO_GAIN remain.','new_fits':0,'optimizer_steps':0,'test_access':False,'binary_reads':0,'bindings':{str(p.relative_to(r)):sha(p),str((o/'completion_receipt.json').relative_to(r)):sha(o/'completion_receipt.json'),str((r/'reports/dynamic_A_eligible_20261017_root/candidate_features.csv').relative_to(r)):sha(r/'reports/dynamic_A_eligible_20261017_root/candidate_features.csv')}}
with (o/'error_contribution.json').open('x') as f:json.dump(out,f,ensure_ascii=False,indent=2)
print(json.dumps({'support':parts['train_EOL_support'],'observed_censored':parts['observed_or_censored']},ensure_ascii=False))
