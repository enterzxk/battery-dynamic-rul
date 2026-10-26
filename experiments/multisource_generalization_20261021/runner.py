"""Condition-isolated retraining from frozen train-only factorial feature caches."""
import os
for key in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS']:
 os.environ[key]='4'
import pathlib,json,hashlib,datetime,fcntl,signal,sys,time,traceback,collections
import numpy as np
R=pathlib.Path('/home/yndx/zxk/rul');D=R/'experiments/multisource_generalization_20261021'
F=R/'experiments/multisource_factorial_20261021';O=R/'experiments/isu_irregular_rul_seed42_v1';V=R/'experiments/dart_rul_v18'
sys.path[:0]=[str(F),str(O),str(V)]
import runner as formal
from data_adapter import load_reviewed_cell
from data_protocol import make_examples
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def sources():
 x=formal.source_hashes();x[str(pathlib.Path(__file__).relative_to(R))]=sha(__file__)
 x['experiments/multisource_generalization_20261021/condition_group_split.json']=sha(D/'condition_group_split.json')
 return x
def run(go_path):
 started=time.time();out=None;locks=[];rec={'status':'PREFLIGHT','CPU_fits_started':0,'CPU_fits_completed':0,'C3_payload_reads':0,'C4_payload_reads':0,'seed':42}
 g=json.loads(pathlib.Path(go_path).read_text());receipt=D/(g['request_id']+'_receipt.json')
 try:
  assert g['status']=='APPROVED' and g['allow_fit'] is True and g['fit_budget']==32
  assert g['source_sha256']==sources()
  state=json.loads((R/'automation/state/coordinator.json').read_text());assert state['owner']==g['owner_thread_id'] and state['state']=='ACTIVE'
  now=datetime.datetime.now(datetime.timezone.utc);hb=datetime.datetime.fromisoformat(state['heartbeat_utc']);issued=datetime.datetime.fromisoformat(g['issued_utc'])
  assert 0<=(now-hb).total_seconds()<1800 and 0<=(now-issued).total_seconds()<86400
  for rel,want in g['input_sha256'].items():assert sha(R/rel)==want,'input hash '+rel
  upstream=R/g['factorial_output'];fr=json.loads((R/g['factorial_receipt']).read_text())
  assert fr['status']=='SUCCESS' and fr['CPU_fits_completed']==80 and fr['C4_payload_reads']==0
  split=json.loads((D/'condition_group_split.json').read_text());fitids=set(split['fit_cell_ids']);valids=set(split['validation_cell_ids']);assert len(fitids)==101 and len(valids)==24 and not fitids&valids
  roles=json.loads((R/'reports/isu_ilcc_capacity_probe_20261020_root/cohort.json').read_text())['roles'];manifest=json.loads((R/'reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json').read_text())
  assert fitids|valids=={c for c,v in roles.items() if v=='train'}
  for rel in ['automation/state/online_survival_cpu.lock','automation/locks/isu_irregular_rul_cpu.lock']:
   f=(R/rel).open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  out=(R/g['output']).resolve();assert D in out.parents;out.mkdir(exist_ok=False)
  formal.writej(D/(g['request_id']+'.claim.json'),{'GO_sha256':sha(go_path)})
  signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('GO runtime')));signal.alarm(g['max_runtime_seconds'])
  cells=[]
  for cid in sorted(fitids|valids):
   p=R/'data/processed/ISU_ILCC_DataV2_v1'/(cid+'.json');assert roles[cid]=='train' and not cid.endswith(('C3','C4')) and sha(p)==manifest['files'][cid]['sha256']
   cells.append(load_reviewed_cell(p,'train'))
  examples=make_examples(cells);metadata=[json.loads(x) for x in (upstream/'train_rows.jsonl').read_text().splitlines()]
  key=lambda e:(e['cell_id'],e['arm'],float(e['query_epoch']))
  cachekeys={key(e):i for i,e in enumerate(metadata)};assert len(cachekeys)==len(metadata)
  train=[e for e in examples if e['cell_id'] in fitids];dev=[dict(e,role='development') for e in examples if e['cell_id'] in valids]
  assert train and dev and {e['group_id'] for e in train}.isdisjoint({e['group_id'] for e in dev})
  ti=[cachekeys[key(e)] for e in train];di=[cachekeys[key(e)] for e in dev]
  primary=('F0','F1','F2','F3');full=np.load(upstream/'train_features.npz',allow_pickle=False)
  xt={p:np.asarray(full[p][ti]) for p in primary};xd={p:np.asarray(full[p][di]) for p in primary};full.close()
  tm=[metadata[i] for i in ti];dm=[metadata[i] for i in di]
  rec.update(status='FITTING',train_source_cells=101,validation_source_cells=24,train_query_cells=len({e['cell_id'] for e in train}),validation_query_cells=len({e['cell_id'] for e in dev}),train_queries=len(train),validation_queries=len(dev),held_condition_groups=split['held_condition_groups'],source_role='all payloads original C1/C2 train; validation role assigned only for internal G-isolated scoring')
  formal.PANELS=primary;formal.FIT_BUDGET=32
  rows,summary,cell=formal.fit_and_score(g,train,dev,xt,xd,tm,dm,out,rec)
  formal.write_csv(out/'paired_panel_deltas.csv',formal.paired_panel_deltas(cell))
  rec.update(status='SUCCESS',prediction_rows=len(rows),scope='internal condition-combination holdout after C3 development; not independent final or within-cell regime-change confirmation')
 except BaseException as ex:rec.update(status='FAILED',error=repr(ex),traceback=traceback.format_exc())
 finally:
  signal.alarm(0);rec['elapsed_seconds']=time.time()-started
  formal.writej(receipt,rec)
  for f in locks:f.close()
 print(json.dumps(rec,indent=2));return rec
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--go',required=True);a=p.parse_args();r=run(a.go);sys.exit(0 if r['status']=='SUCCESS' else 2)
