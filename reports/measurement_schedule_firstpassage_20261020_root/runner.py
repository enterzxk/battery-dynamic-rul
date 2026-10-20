from pathlib import Path
import csv,json,hashlib,datetime,fcntl,signal,time,io,decimal
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
def dump(name,x):
 with (O/name).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
def summarize(cycles,q,anchor,spacing,threshold):
 dense=next((t for t,v in zip(cycles,q) if v<=threshold),None)
 inspected=[(t,v) for t,v in zip(cycles,q) if t>=anchor and (t-anchor)%spacing==0]
 sparse=next((t for t,v in inspected if v<=threshold),None)
 prior_above=[t for t,v in inspected if sparse is not None and t<sparse and v>threshold]
 left=max(prior_above) if prior_above else None
 false_survival=[t for t,v in inspected if dense is not None and t>=dense and v>threshold]
 interval_valid=None if sparse is None or left is None or dense is None else left<dense<=sparse
 delay=None if sparse is None or dense is None else sparse-dense
 undetected_long=(sparse is None and dense is not None and cycles[-1]>=dense+spacing)
 mechanism=interval_valid is False or (delay is not None and delay>spacing) or undetected_long
 return dict(dense_reference_event=dense,sparse_first_detected=sparse,last_inspected_above_before_detection=left,naive_interval_contains_dense_first_passage=interval_valid,detection_delay_cycles=delay,false_survival_inspection_cycles=false_survival,undetected_despite_spacing_of_followup=undetected_long,mechanism_positive=mechanism,sparse_inspections=len(inspected),last_recorded_cycle=cycles[-1])
def main():
 start=time.monotonic();p=json.loads((O/'protocol.json').read_text());g=json.loads((O/'ROOT_GO.json').read_text())
 assert g['status']=='GO_ONE_TRAIN_ONLY_COARSENING_DIAGNOSTIC_ZERO_FIT'
 for n in ['runner.py','protocol.json']:assert sha((O/n).read_bytes())==g[n+'_sha256']
 review=Path(g['review_path']);assert sha(review.read_bytes())==g['review_sha256'] and json.loads(review.read_text())['status']=='PASS'
 with (R/'automation/state/online_survival_cpu.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  c=json.loads((R/'automation/state/coordinator.json').read_text());assert c['owner']==c['thread_id']==p['owner'] and c['takeover_verified'] and not c['new_fits_allowed'] and c['pending_experiment'] is None
  with (O/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
  def alarm(a,b):raise TimeoutError('Frozen30second bound exceeded')
  signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,30)
  try:
   cofile=Path(p['cohort_path']);assert sha(cofile.read_bytes())==p['cohort_sha256'];co=json.loads(cofile.read_text())
   assert {x['cell_id'] for x in p['sources']}=={k for k,v in co['roles'].items() if v=='fit'} and len(p['sources'])==42
   # One exact semantic counterexample: recovery can put first passage before L.
   probe=summarize([0,1,2,3,4],[1.,.79,.82,.81,.79],0,2,.8)
   assert probe['dense_reference_event']==1 and probe['sparse_first_detected']==4 and probe['last_inspected_above_before_detection']==2 and probe['naive_interval_contains_dense_first_passage'] is False
   rows=[];bytes_read=0;raw_rows=0
   for source in p['sources']:
    assert source['role']=='fit' and co['roles'][source['cell_id']]=='fit' and source['gap_count']==0
    f=Path(source['path']);assert f.parent in [Path(m['path']).parent for m in p['manifests']] and f.name==source['cell_id']+'_cycles.csv'
    b=f.read_bytes();bytes_read+=len(b);assert len(b)==source['bytes'] and bytes_read<=p['budget']['max_main_source_bytes'] and sha(b)==source['sha256']
    records=list(csv.DictReader(io.StringIO(b.decode())));raw_rows+=len(records)
    assert all(r['valid'].lower()=='true' for r in records)
    cycles=[int(r['actual_cycle']) for r in records];q=[float(r['capacity_Ah']) for r in records]
    assert all(qi>0 and qi<float('inf') for qi in q) and len(set(cycles))==len(cycles) and all(y-x==1 for x,y in zip(cycles,cycles[1:]))
    threshold=float(decimal.Decimal(str(source['nominal_Ah']))*decimal.Decimal('0.8'))
    assert threshold==.88 and p['anchor_cycle'] in cycles
    result=summarize(cycles,q,p['anchor_cycle'],p['spacing_actual_cycles'],threshold)
    assert result['dense_reference_event']==source['reference_event']>p['anchor_cycle']
    result.update(cell_id=source['cell_id'],role='fit',source_sha256=source['sha256'],dense_rows=len(cycles),first_recorded_cycle=cycles[0])
    rows.append(result)
   n=len(rows);pos=sum(x['mechanism_positive'] for x in rows);det=[x['detection_delay_cycles'] for x in rows if x['detection_delay_cycles'] is not None];det.sort()
   summary=dict(status='COMPLETE_ONE_TRAIN_ONLY_COARSENING_DIAGNOSTIC',cells=n,source_bytes=bytes_read,source_rows=raw_rows,spacing_cycles=20,invalid_naive_intervals=sum(x['naive_interval_contains_dense_first_passage'] is False for x in rows),undetected_dense_events=sum(x['sparse_first_detected'] is None for x in rows),undetected_with_full_spacing_followup=sum(x['undetected_despite_spacing_of_followup'] for x in rows),cells_with_false_survival_inspections=sum(bool(x['false_survival_inspection_cycles']) for x in rows),false_survival_inspections=sum(len(x['false_survival_inspection_cycles']) for x in rows),cells_delay_gt_spacing=sum(x['detection_delay_cycles'] is not None and x['detection_delay_cycles']>20 for x in rows),detected_cells=len(det),detection_delay_median=(det[(len(det)-1)//2]+det[len(det)//2])/2 if det else None,detection_delay_max=max(det) if det else None,mechanism_positive_cells=pos,screen_pass=pos>=3,decision='MECHANISM_PRESENT_REQUIRES_SEPARATE_PROTOCOL_NO_MODEL_AUTHORIZATION' if pos>=3 else 'NO_GO_COMPLEX_OBSERVATION_MECHANISM_EXPANSION_FROM_THIS_SCREEN',new_fits=0,new_model_inference=0,cal_dev_test_reads=0,raw_archive_reads=0,checkpoint_loads=0,elapsed_seconds=time.monotonic()-start)
   dump('per_cell.json',rows);dump('summary.json',summary);dump('semantic_validation.json',dict(status='PASS_ONE_RECOVERY_COUNTEREXAMPLE',probe=probe))
   dump('completion.json',dict(status='COMPLETE',protocol_sha256=sha((O/'protocol.json').read_bytes()),runner_sha256=sha(Path(__file__).read_bytes()),GO_sha256=sha((O/'ROOT_GO.json').read_bytes()),summary_sha256=sha((O/'summary.json').read_bytes()),per_cell_sha256=sha((O/'per_cell.json').read_bytes()),reads={'train_csv_files':n,'train_bytes':bytes_read,'cal_dev_test':0,'raw_archives':0,'models':0,'fits':0}))
   print(json.dumps(summary))
  except BaseException as e:
   dump('failure.json',dict(status='FAILED_STOP_NO_RETRY',type=type(e).__name__,error=str(e)));raise
  finally:signal.setitimer(signal.ITIMER_REAL,0)
if __name__=='__main__':main()
