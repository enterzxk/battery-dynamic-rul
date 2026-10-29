#!/usr/bin/env python3
"""Prespecified 14-day pending-report counterfactual diagnosis; no estimator fits."""
import os
os.environ['OMP_NUM_THREADS']='4';os.environ['MKL_NUM_THREADS']='4'
import pathlib,sys,json,csv,hashlib,datetime,time,collections,fcntl,traceback,argparse,copy
import numpy as np
R=pathlib.Path('/home/yndx/zxk/rul');H=R/'experiments/rulaas_pending_value_20261029';OLD=R/'experiments/rulaas_gain_identifiability_20261029/run02';OOF=R/'experiments/rulaas_gain_oof_repair_20261029/run01';FORMAL=R/'experiments/multisource_factorial_20261021/run2_clocksafe';SIG=R/'reports/multisource_20261021_signals'
OWNER='01a17810-6ae6-7cf2-9729-5bfcaa8df5f4';DAY=86400.;WEEK=604800.;LAG=14.;MAXSTALE=3.426952600479126;CAND={4,8,12,16,20,24,28,32}
sys.path[:0]=[str(R/'experiments/rulaas_value_gate_20261029'),str(R/'experiments/multisource_factorial_20261021'),str(SIG),str(R/'experiments/isu_irregular_rul_seed42_v1'),str(R/'experiments/dart_rul_v18')]
from value_gate import vector,MemoCycle
from data_adapter import load_reviewed_cell
import cycle_asof_features as C
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def readj(p):return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def writej(p,x):
 with pathlib.Path(p).open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def csvout(p,rows):
 if not rows:raise ValueError('empty artifact '+str(p))
 with pathlib.Path(p).open('x',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def prog(out,x):
 tmp=out/'progress.tmp';tmp.write_text(json.dumps(x,ensure_ascii=False),encoding='utf-8');os.replace(tmp,out/'progress.json')
def report(row):return dict(row,arrival_epoch=float(row['stop_epoch'])+LAG*DAY)
def arrive(rows,q):return [z for z in rows if float(z['arrival_epoch'])<=q]
def result_summary(cases,pop):
 group=[z for z in cases if z['population']==pop];pending=[z for z in group if z['input_pending_count']>0]
 by=collections.defaultdict(list)
 for z in pending:by[z['cell_id']].append(z)
 cells=sorted(by);groups=sorted({z.rsplit('C',1)[0] for z in cells});diff={cid:float(np.mean([z['label_gain_suppress_pending']-z['label_gain_pending_arrives'] for z in v])) for cid,v in by.items()}
 sums=np.asarray([sum(diff[c] for c in cells if c.rsplit('C',1)[0]==g) for g in groups]);counts=np.asarray([sum(c.rsplit('C',1)[0]==g for c in cells) for g in groups])
 rng=np.random.RandomState(42);idx=rng.randint(len(groups),size=(5000,len(groups)));boot=sums[idx].sum(axis=1)/counts[idx].sum(axis=1)
 def cm(k):return float(np.mean([np.mean([z[k] for z in by[c]]) for c in cells]))
 delta=[z['label_gain_suppress_pending']-z['label_gain_pending_arrives'] for z in pending]
 result=dict(population=pop,eligible_cases=len(group),eligible_cells=len({z['cell_id'] for z in group}),pending_cases=len(pending),pending_cells=len(cells),pending_source_groups=len(groups),unknown_post_event_cases=sum(z['label_request_before_event'] is False for z in group),input_stale_above_original_training_max_cases=sum(z['input_stale_above_original_training_max'] for z in group),pending_realistic_gain_cell_macro_weeks=cm('label_gain_pending_arrives'),pending_suppressed_gain_cell_macro_weeks=cm('label_gain_suppress_pending'),difference_cell_macro_weeks=float(np.mean(list(diff.values()))),group_bootstrap_95_CI=[float(np.quantile(boot,.025)),float(np.quantile(boot,.975))],difference_positive_cases=sum(x>1e-9 for x in delta),difference_zero_cases=sum(abs(x)<=1e-9 for x in delta),difference_negative_cases=sum(x< -1e-9 for x in delta),cells_positive=sum(x>1e-9 for x in diff.values()),cells_zero=sum(abs(x)<=1e-9 for x in diff.values()),cells_negative=sum(x< -1e-9 for x in diff.values()),interpretation='Fixed-proxy informational overlap; hypothetical suppressed-inflight world is not a deployable equal-resource policy.')
 per=[dict(population=pop,cell_id=c,n_pending_cases=len(by[c]),gain_pending_arrives=float(np.mean([z['label_gain_pending_arrives'] for z in by[c]])),gain_suppress_pending=float(np.mean([z['label_gain_suppress_pending'] for z in by[c]])),difference=float(diff[c])) for c in cells]
 return result,per
def main(go_path):
 g=readj(go_path);out=R/g['output'];started=time.time();locks=[]
 rec=dict(status='STARTED',request_id=g['request_id'],started_utc=stamp(),new_fits=0,model_prediction_rows=0,source_train_cells_read=0,C3_payload_reads=0,C4_payload_reads=0,actual_coordinator_model_recorded=g['actual_model'],hypothetical_delay_days=LAG)
 try:
  for p in [R/'automation/state/coordinator.lock',R/'automation/locks/isu_irregular_rul_cpu.lock']:
   f=p.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  coord=readj(R/'automation/state/coordinator.json')
  if coord.get('state')!='ACTIVE' or coord.get('owner')!=OWNER or coord.get('thread_id')!=OWNER:raise ValueError('owner')
  hb=datetime.datetime.fromisoformat(coord['heartbeat_utc'].replace('Z','+00:00'))
  if (datetime.datetime.now(datetime.timezone.utc)-hb).total_seconds()>1800:raise ValueError('heartbeat')
  if g.get('status')!='APPROVED' or g.get('owner')!=OWNER or g.get('allow_fits') is not False or g.get('allow_C3') is not False or g.get('allow_C4') is not False:raise ValueError('GO')
  if g['model_row_cap']!=8000 or g['source_cell_cap']!=48 or g['hypothetical_delay_days']!=14 or g['candidate_source_indices']!=sorted(CAND):raise ValueError('budget')
  for rel,expected in g['input_sha256'].items():
   if sha(R/rel)!=expected:raise ValueError('input hash '+rel)
  if out.parent!=H or out.exists():raise ValueError('create-only output')
  writej(H/(g['request_id']+'.claim.json'),dict(GO_sha256=sha(go_path),utc=stamp()));out.mkdir();prog(out,rec)
  split=readj(OLD/'cell_split.json');folds=readj(OOF/'fold_manifest.json')['folds'];audit=readj(OOF/'INDEPENDENT_RECOMPUTE.json')
  if audit['status']!='PASS' or not audit['all_three_heads_exclude_all_60_original_held_cells']:raise ValueError('crossfit audit')
  fit=set(split['base_head_fit_cells']);held=set(split['base_head_unseen_cells'])
  if len(fit)!=60 or len(held)!=60 or fit&held:raise ValueError('head split')
  for f in folds:
   if set(f['train_cells'])&held or set(f['train_cells'])&set(f['excluded_oof_cells']):raise ValueError('fold leak')
  import joblib
  models=[joblib.load(OOF/('nested_head_'+str(i)+'.joblib')) for i in range(3)]
  heldmodel=joblib.load(FORMAL/'hgb_F3_oof0.joblib')
  orig=readj(OLD/'receipt.json');sources=collections.defaultdict(dict)
  for z in orig['source_files']:sources[z['cell_id']][z['kind']]=z
  cases=[];points=[];skips=[];mutation_tested=False;source_files=[];out_of_support_predictions=0
  for population,ids in [('kernel_fit',split['selected_kernel_fit']),('kernel_held',split['selected_kernel_held'])]:
   for cid in ids:
    if not cid.endswith(('C1','C2')) or set(sources[cid])!={'DataV2','RPT','Cycling'}:raise ValueError('source role')
    if population=='kernel_fit':
     fi=next(i for i,f in enumerate(folds) if cid in set(f['excluded_oof_cells']))
     if cid not in fit or cid in set(folds[fi]['train_cells']):raise ValueError('oof leak')
     model=models[fi]
    else:
     if cid not in held or cid in fit:raise ValueError('held leak')
     fi=-1;model=heldmodel
    src=sources[cid]
    for kind in ['DataV2','RPT','Cycling']:
     item=src[kind];p=R/item['path']
     if 'C3' in p.name or 'C4' in p.name or sha(p)!=item['sha256']:raise ValueError('source hash')
     source_files.append(dict(cell_id=cid,kind=kind,path=item['path'],sha256=item['sha256']))
    cell=load_reviewed_cell(R/src['DataV2']['path'],'train');rows=sorted(cell['records'],key=lambda z:float(z['stop_epoch']))
    rpt=readj(R/src['RPT']['path']);cycle=MemoCycle(C.build_cycle_index(R/src['Cycling']['path']))
    if cell['cell_id']!=cid or cycle.cell_id!=cid or cycle.role!='train' or rpt['role']!='train':raise ValueError('source identity')
    cache={cid:{int(z['source_rpt_index']):z for z in rpt['records']}};event=next((float(z['stop_epoch']) for z in rows if float(z['capacityAh'])<=.20),None)
    matrix=[];index={};draft=[]
    def add(x):
     raw=np.asarray(x,np.float32).tobytes()
     if raw not in index:index[raw]=len(matrix);matrix.append(np.asarray(x,np.float32))
     return index[raw]
    for pos,row in enumerate(rows):
     idx=int(row['source_rpt_index'])
     if idx not in CAND or pos<3:continue
     request=datetime.datetime.fromisoformat(row['start']).timestamp()
     bg=[report(z) for j,z in enumerate(rows[:pos]) if j<3 or (j-3)%2==0];vis=arrive(bg,request);pending=[z for z in bg if float(z['arrival_epoch'])>request]
     reason='no_exact_source_event' if event is None else ('less_than_3_visible' if len(vis)<3 else ('known_event' if any(float(z['capacityAh'])<=.20 for z in vis) else ('previous_test_not_completed' if any(float(z['stop_epoch'])>request for z in bg) else None)))
     if reason:skips.append(dict(population=population,cell_id=cid,source_rpt_index=idx,reason=reason));continue
     x=vector(cell,vis,request,cache,cycle);current=add(x)
     if pending and not mutation_tested:
      mutated=copy.deepcopy(cache);nchanged=0
      for xidx in [idx]+[int(z['source_rpt_index']) for z in pending]:
       fr=mutated[cid][xidx]
       if isinstance(fr.get('values'),list):fr['values']=[-99999.]*len(fr['values']);nchanged+=1
       elif isinstance(fr.get('values'),dict):fr['values']={k:-99999. for k in fr['values']};nchanged+=1
      if nchanged<2 or not np.allclose(x,vector(cell,vis,request,mutated,cycle),rtol=0,atol=0,equal_nan=True):raise ValueError('unarrived signal mutation')
      mutation_tested=True
     stale=(request-float(vis[-1]['stop_epoch']))/WEEK
     if not np.isclose(float(x[6]),stale,rtol=0,atol=1e-6):raise ValueError('stale feature')
     rem=[(float(z['arrival_epoch'])-request)/DAY for z in pending];slots=[]
     for k in range(1,9):
      q=request+k*.5*WEEK
      if q>=event:slots.append(dict(q=q,alive=False,y=0.,a=None,b=None,c=None,d=None));continue
      if q>float(rows[-1]['stop_epoch']):raise ValueError('pre-event support')
      natural=arrive(bg,q);frozen=list(vis)
      def with_candidate(v):
       v=list(v)
       if float(row['stop_epoch'])+LAG*DAY<=q:v.append(report(row))
       v.sort(key=lambda z:(float(z['stop_epoch']),int(z['source_rpt_index'])))
       return v
      slots.append(dict(q=q,alive=True,y=(event-q)/WEEK,a=add(vector(cell,natural,q,cache,cycle)),b=add(vector(cell,with_candidate(natural),q,cache,cycle)),c=add(vector(cell,frozen,q,cache,cycle)),d=add(vector(cell,with_candidate(frozen),q,cache,cycle))))
     draft.append(dict(cell_id=cid,population=population,fold=fi,source_rpt_index=idx,request_epoch=request,input_pending_count=len(pending),input_next_pending_arrival_days=min(rem) if rem else None,input_staleness_weeks=stale,input_stale_above_original_training_max=stale>MAXSTALE,input_arrived_RPT_count=len(vis),label_source_event_epoch=event,label_candidate_stop_epoch=float(row['stop_epoch']),label_request_before_event=request<event,current=current,slots=slots))
    if matrix:
     if rec['model_prediction_rows']+len(matrix)>g['model_row_cap']:raise ValueError('prediction row cap')
     arr=np.asarray(matrix,float);out_of_support_predictions+=int(np.sum(arr[:,6]>MAXSTALE));mu=model.predict(arr);pred=np.exp(mu);rec['model_prediction_rows']+=len(matrix)
     if not np.isfinite(pred).all():raise ValueError('nonfinite no clipping')
     for d in draft:
      caseid=len(cases);gain_a=gain_b=0.;n=0
      for k,s in enumerate(d['slots'],1):
       if s['alive']:
        y=s['y'];a=float(pred[s['a']]);b=float(pred[s['b']]);c=float(pred[s['c']]);dd=float(pred[s['d']]);ga=abs(a-y)-abs(b-y);gb=abs(c-y)-abs(dd-y);n+=1
       else:y=0.;a=b=c=dd=None;ga=gb=0.
       gain_a+=ga/8.;gain_b+=gb/8.
       points.append(dict(case_id=caseid,population=population,cell_id=cid,source_rpt_index=d['source_rpt_index'],slot=k,query_epoch=s['q'],pre_reference_event=s['alive'],true_RUL=y,natural_no_candidate=a,natural_candidate=b,suppress_pending_no_candidate=c,suppress_pending_candidate=dd,gain_pending_arrives=ga,gain_suppress_pending=gb))
      row={k:v for k,v in d.items() if k not in ['current','slots']};row.update(case_id=caseid,input_point_proxy_RUL=float(pred[d['current']]),label_pre_event_slots=n,label_gain_pending_arrives=float(gain_a),label_gain_suppress_pending=float(gain_b),label_difference_suppressed_minus_natural=float(gain_b-gain_a));cases.append(row)
    rec['source_train_cells_read']+=1;rec['cases_completed']=len(cases);prog(out,rec)
  fitcases=[z for z in cases if z['population']=='kernel_fit'];heldcases=[z for z in cases if z['population']=='kernel_held']
  if len(fitcases)!=99 or len(heldcases)!=85 or sum(z['input_pending_count']>0 for z in fitcases)!=88 or sum(z['input_pending_count']>0 for z in heldcases)!=80 or not mutation_tested:raise ValueError('metadata support drift')
  results=[];per=[]
  for pop in ['kernel_fit','kernel_held']:
   x,y=result_summary(cases,pop);results.append(x);per.extend(y)
  csvout(out/'cases.csv',cases);csvout(out/'counterfactual_points.csv',points);csvout(out/'per_cell.csv',per);csvout(out/'excluded_cases.csv',skips)
  writej(out/'summary.json',dict(populations=results,model_prediction_rows_outside_original_staleness_range=out_of_support_predictions,model_prediction_rows_total=rec['model_prediction_rows'],C3_payload_reads=0,C4_payload_reads=0,new_fits=0,pending_candidate_mutation_request_input='PASS',limits=['Hypothetical fixed 14-day delay; not real arrival data.','Suppression is a counterfactual information comparison, not equal-resource policy.','Post-event time reward zero; not a complete event-detection objective.','40 versus 60 head-training cells; operating groups may overlap.','Fixed positive proxy only; no hurdle distribution or physical intervention proof.']))
  rec.update(status='SUCCESS',finished_utc=stamp(),elapsed_seconds=time.time()-started,GO_sha256=sha(go_path),source_files=source_files,input_sha256=g['input_sha256'],eligible_cases=len(cases),counterfactual_slots=len(points),excluded_cases=len(skips),unarrived_signal_mutation='PASS',model_prediction_rows_outside_original_staleness_range=out_of_support_predictions)
  writej(out/'receipt.json',rec);prog(out,rec)
  print(json.dumps(dict(status='SUCCESS',new_fits=0,model_rows=rec['model_prediction_rows'],elapsed_seconds=rec['elapsed_seconds'],populations=results),ensure_ascii=False))
 except BaseException as ex:
  rec.update(status='FAILED',error=repr(ex),traceback=traceback.format_exc(),finished_utc=stamp(),elapsed_seconds=time.time()-started)
  if out.is_dir() and not (out/'failure_receipt.json').exists():writej(out/'failure_receipt.json',rec)
  print(json.dumps(rec,ensure_ascii=False));raise
 finally:
  for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--go',required=True);main(pathlib.Path(a.parse_args().go))
