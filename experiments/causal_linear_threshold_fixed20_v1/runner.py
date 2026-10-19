from pathlib import Path
import json,csv,hashlib,math,datetime,fcntl,signal,time
R=Path('/home/yndx/zxk/rul');D=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(n,j):
 with (D/n).open('x') as f:json.dump(j,f,indent=2,allow_nan=False);f.write('\n')
def calculate(soh,rate,missing):
 if missing:return None,'missing_rate'
 if not math.isfinite(soh) or not math.isfinite(rate):return None,'nonfinite_input'
 if soh<=.8:return None,'invalid_preevent_SOH'
 if rate>=0:return None,'nonnegative_rate'
 v=(soh-.8)/(-rate)
 return (v,'finite') if math.isfinite(v) and v>0 else (None,'nonfinite_output')
def calculate_fields(f):
 missing=f['rate20_missing']=='True'
 try:soh=float(f['soh'])
 except (ValueError,TypeError):soh=float('nan')
 if missing:rate=float('nan')
 else:
  try:rate=float(f['rate20_per_cycle'])
  except (ValueError,TypeError):rate=float('nan')
 return calculate(soh,rate,missing)
def metric(rows,col):
 if any(r[col] is None for r in rows):return None
 e=[r[col]-r['true_RUL'] for r in rows]
 return {'MAE':sum(abs(v) for v in e)/len(e),'bias':sum(e)/len(e),'severe_over100':sum(v>100 for v in e)/len(e)}
def main():
 p=json.loads((D/'protocol.json').read_text());g=json.loads((D/'ROOT_GO.json').read_text());meta=json.loads((D/'feature_manifest.json').read_text())
 assert g['runner_sha256']==sha(__file__) and g['protocol_sha256']==sha(D/'protocol.json') and g['feature_manifest_sha256']==sha(D/'feature_manifest.json')
 assert sha(g['review_path'])==g['review_sha256'] and json.loads(Path(g['review_path']).read_text())['status']=='PASS'
 for rel,h in p['source_sha256'].items():assert sha(R/rel)==h
 assert calculate(.9,-.001,False)[0]-100<1e-10 and calculate(.9,0,False)[0] is None
 co=json.loads((R/p['cohort']).read_text());ids={k for k,v in co['roles'].items() if v=='calibration'};assert ids==set(meta['cells']) and len(ids)==10
 with (R/'automation/state/online_survival_cpu.lock').open('a+') as lk:
  fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB);c=json.loads((R/'automation/state/coordinator.json').read_text());assert c['owner']==c['thread_id']==p['owner'] and c['takeover_verified'] and not c['new_fits_allowed']
  with (D/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
  def timeout(a,b):raise TimeoutError('60second budget')
  signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,60)
  try:
   mixture=list(csv.DictReader((R/p['mixture']).open()));dist=list(csv.DictReader((R/p['distributions']).open()));dyn=[r for r in dist if r['arm']=='lossless_dynamic'];early=[r for r in dist if r['arm']=='lossless_early_survival_conditioned']
   def keyed(rs):
    z={}
    for r in rs:
     k=(r['cell_id'],int(r['origin']));assert k[0] in ids and k not in z;z[k]=r
    return z
   m=keyed(mixture);dy=keyed(dyn);ea=keyed(early);assert set(m)==set(dy)==set(ea) and len(m)==4567
   rows=[];opened=[]
   for cid in sorted(ids):
    cc=meta['cells'][cid];assert cc['source_role']=='train' and co['roles'][cid]=='calibration'
    fp=R/cc['features_path'];assert sha(fp)==cc['features_sha256'];opened.append(str(fp))
    ff=list(csv.DictReader(fp.open()));assert len(ff)==cc['prefix_count'];seen=set()
    for f in ff:
     s=int(f['origin_cycle']);k=(cid,s);assert s not in seen and k in m;seen.add(s)
     assert int(f['visible_through_cycle'])==s<cc['event_cycle']
     truth=float(m[k]['true_RUL']);assert truth==float(dy[k]['true_RUL'])==float(ea[k]['true_RUL'])==cc['event_cycle']-s
     assert f['rate20_missing'] in ['True','False']
     pred,status=calculate_fields(f)
     rows.append(dict(cell_id=cid,origin=s,true_RUL=truth,linear_RUL=pred,status=status,early_RUL=float(ea[k]['q50']),dynamic_RUL=float(dy[k]['q50']),mixture_RUL=float(m[k]['q50'])))
    assert seen=={s for c,s in m if c==cid}
   assert len(opened)==10 and len(rows)==4567
   with (D/'predictions.csv').open('x',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
   pc=[]
   from collections import Counter
   for cid in sorted(ids):
    z=[r for r in rows if r['cell_id']==cid];v=[r for r in z if r['status']=='finite'];assert v
    pc.append({'cell_id':cid,'all_origins':len(z),'finite_origins':len(v),'finite_fraction':len(v)/len(z),'status_counts':dict(Counter(r['status'] for r in z)),'full_linear':metric(z,'linear_RUL'),'common_finite_subset':{a:metric(v,col) for a,col in [('linear','linear_RUL'),('early','early_RUL'),('dynamic','dynamic_RUL'),('mixture','mixture_RUL')]},'max_finite_linear_RUL':max(r['linear_RUL'] for r in v)})
   complete=all(r['status']=='finite' for r in rows);cols=['MAE','bias','severe_over100']
   summary={'cells':10,'origins':4567,'finite_origins':sum(r['status']=='finite' for r in rows),'status_counts':dict(Counter(r['status'] for r in rows)),'macro_finite_fraction':sum(r['finite_fraction'] for r in pc)/10,'complete_allorigin_point_predictions':complete,'full_linear_metrics':{k:sum(r['full_linear'][k] for r in pc)/10 for k in cols} if complete else None,'common_finite_subset_metrics':{a:{k:sum(r['common_finite_subset'][a][k] for r in pc)/10 for k in cols} for a in ['linear','early','dynamic','mixture']},'common_subset_cannot_replace_full_metrics':True,'max_finite_RUL':max(r['linear_RUL'] for r in rows if r['linear_RUL'] is not None)}
   dump('per_cell_metrics.json',pc);dump('metrics.json',summary)
   dump('completion.json',{'status':'COMPLETE_ONE_NOFIT_STANDARD_LINEAR_BASELINE','new_fits':0,'new_model_inference':0,'checkpoint_loads':0,'feature_files_read':opened,'feature_rows':4567,'dev_test_reads':0,'runner_sha256':sha(__file__),'protocol_sha256':sha(D/'protocol.json'),'feature_manifest_sha256':sha(D/'feature_manifest.json'),'GO_sha256':sha(D/'ROOT_GO.json'),'predictions_sha256':sha(D/'predictions.csv')})
   signal.setitimer(signal.ITIMER_REAL,0);print(json.dumps(summary))
  except BaseException as e:
   signal.setitimer(signal.ITIMER_REAL,0);dump('failure.json',{'error':repr(e),'GO_consumed':True,'no_retry':True});raise
if __name__=='__main__':main()
