#!/usr/bin/env python3
"""GO-gated zero-fit off-RPT-clock development evaluation for saved factorial models."""
from __future__ import annotations
import argparse, collections, datetime, hashlib, json, math, pathlib, sys, time, traceback
import numpy as np

ROOT=pathlib.Path('/home/yndx/zxk/rul')
HERE=ROOT/'experiments/multisource_factorial_20261021'
SIGNALS=ROOT/'reports/multisource_20261021_signals'
DATA_MAN=ROOT/'reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json'
COHORT=ROOT/'reports/isu_ilcc_capacity_probe_20261020_root/cohort.json'
V18=ROOT/'experiments/dart_rul_v18'
OLD=ROOT/'experiments/isu_irregular_rul_seed42_v1'
sys.path[:0]=[str(HERE),str(SIGNALS),str(OLD),str(V18)]
import features as factorial
import cycle_asof_features as cycle_asof
from data_protocol import _arm_records, _feature_view, _history_key, ARMS, DAY, WEEK
from evaluate import PointZero, metric_row, summarize, write_csv
from hgb_models import HurdleRUL

PANELS=('F0','F1','F2','F3')
KINDS=('hgb','catboost')
GRID_STEP=3.5*DAY
MAX_EXAMPLES=50000
MAX_CELLS=63
TAU=np.asarray([0.,1.,4.,12.,32.])

def sha(path):
 h=hashlib.sha256()
 with pathlib.Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
 return h.hexdigest()

def readj(path): return json.loads(pathlib.Path(path).read_text(encoding='utf-8'))

def writej(path,obj):
 with pathlib.Path(path).open('x',encoding='utf-8') as f:
  json.dump(obj,f,ensure_ascii=False,separators=(',',':'),allow_nan=False)

def write_jsonl(path,rows):
 with pathlib.Path(path).open('x',encoding='utf-8') as f:
  for row in rows: f.write(json.dumps(row,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')

def source_hashes():
 paths=[HERE/'off_rpt_grid_zerofit.py',HERE/'protocol.json',HERE/'features.py',
        V18/'data_protocol.py',V18/'hgb_models.py',V18/'evaluate.py',
        OLD/'train_eval.py',OLD/'baselines.py',OLD/'data_adapter.py',
        SIGNALS/'cycle_asof_features.py']
 return {str(p.relative_to(ROOT)):sha(p) for p in paths}

def inventory(path,expected_sha,expected_status):
 if sha(path)!=expected_sha: raise ValueError('feature manifest SHA mismatch: '+str(path))
 m=readj(path);items=m.get('inventory')
 if m.get('status')!=expected_status or not isinstance(items,list):
  raise ValueError('feature manifest is not complete')
 by={}
 for it in items:
  cid=str(it['cell_id']);role=str(it['role'])
  if cid.endswith('C4') or cid in by or role not in ('train','development'):
   raise ValueError('invalid, duplicate, or locked feature inventory entry')
  by[cid]=it
 if len(by)!=188 or collections.Counter(v['role'] for v in by.values())!={'train':125,'development':63}:
  raise ValueError('feature manifest must cover 188 train/development cells')
 return by

def build_grid_examples(cell):
 rows=sorted(cell['records'],key=lambda r:(float(r['stop_epoch']),int(r['source_rpt_index'])))
 if len(rows)<2: raise ValueError('C3 cell has fewer than two valid RPTs')
 anchor_i=1;anchor=float(rows[anchor_i]['stop_epoch']);end=float(rows[-1]['stop_epoch'])
 event=next((r for r in rows if float(r['capacityAh'])<=0.20),None)
 event_epoch=None if event is None else float(event['stop_epoch'])
 arms={arm:_arm_records(rows,anchor_i,arm) for arm in ARMS}
 stop_epochs=np.asarray([float(r['stop_epoch']) for r in rows],float)
 out=[];q=anchor+WEEK
 while q<=end+1e-6:
  if np.min(np.abs(stop_epochs-q))>1.0:
   visible={arm:[dict(r) for r in arms[arm] if float(r['arrival_epoch'])<=q] for arm in ARMS}
   if all(len(visible[a])>=3 for a in ARMS):
    for arm in ARMS:
     rs=visible[arm];latest=max(float(r['arrival_epoch']) for r in rs)
     known=any(float(r['capacityAh'])<=0.20 for r in rs)
     target=None if event_epoch is None else max(0.,(event_epoch-q)/WEEK)
     out.append({'cell_id':str(cell['cell_id']),'group_id':str(cell['group_id']),'role':str(cell['role']),
      'nominal_capacity_ah':float(cell['nominal_capacity_ah']),'arm':arm,'query_epoch':float(q),
      'origin_age_weeks':float(rs[-1]['calendar_age_weeks'])+(q-float(rs[-1]['stop_epoch']))/WEEK,
      'anchor_age_weeks':float(rows[anchor_i]['calendar_age_weeks']),'warmup_epoch':anchor,
      'last_arrival_epoch':latest,'delta_weeks':(q-latest)/WEEK,
      'elapsed_from_warmup_weeks':(q-anchor)/WEEK,'known_event':known,
      'y_event':0 if event_epoch is None else int(event_epoch<=q),
      'target_rul_weeks':target,'event_time_epoch':event_epoch,'visible_records':rs,
      'x_query':_feature_view(cell,rs,q),'history_key':_history_key(rs)})
  q+=GRID_STEP
 return out

def load_c3_cells():
 manifest=readj(DATA_MAN);roles=readj(COHORT)['roles'];files=manifest.get('files',{})
 if manifest.get('status')!='PASS': raise ValueError('DataV2 manifest is not PASS')
 ids=sorted(cid for cid,r in roles.items() if r=='development')
 if len(ids)!=63 or any(not cid.endswith('C3') for cid in ids): raise ValueError('frozen development roles malformed')
 from data_adapter import load_reviewed_cell
 cells=[]
 for cid in ids:
  info=files.get(cid)
  if not info or info.get('role')!='development': raise ValueError('C3 missing from source manifest: '+cid)
  path=ROOT/info['path']
  if sha(path)!=info['sha256']: raise ValueError('C3 DataV2 source SHA mismatch: '+cid)
  cell=load_reviewed_cell(path,'development')
  if cell['cell_id']!=cid: raise ValueError('C3 identity mismatch')
  cells.append(cell)
 return cells

def shift_distribution(dist,gap):
 p=float(dist.zero_mass);v=np.asarray(dist.positive.values,float);w=np.asarray(dist.positive.weights,float)
 shifted=np.maximum(0.,v-float(gap));keep=shifted>0
 pnew=p+(1-p)*float(w[~keep].sum())
 if pnew>=1 or not keep.any(): return PointZero()
 ww=w[keep];ww=ww/ww.sum()
 return HurdleRUL(pnew,shifted[keep],ww)

def no_new_report_pairs(examples,meta,pred):
 grouped=collections.defaultdict(list)
 for i,e in enumerate(examples): grouped[(e['cell_id'],e['arm'],e['history_key'])].append((i,e))
 cycle_count={m['i']:m['cycle_count'] for m in meta};out=[]
 # The two cross-panel updates retain the original contrasts. Four self-panel
 # transports identify time-transport/recomputation effects at the same RPT pair.
 pair_specs=(('F0','F2','F0_time_only_to_F2_updated'),
             ('F1','F3','F1_time_only_to_F3_updated'),
             ('F0','F0','F0_self_transport'),
             ('F1','F1','F1_self_transport'),
             ('F2','F2','F2_self_transport'),
             ('F3','F3','F3_self_transport'))
 for key,seq in sorted(grouped.items()):
  seq=sorted(seq,key=lambda t:t[1]['query_epoch'])
  for (ia,a),(ib,b) in zip(seq,seq[1:]):
   if cycle_count[ib]<=cycle_count[ia] or a['known_event'] or b['known_event']: continue
   gap=(b['query_epoch']-a['query_epoch'])/WEEK
   if gap<=0: continue
   for kind in KINDS:
    for transport_panel,updated_panel,pair_name in pair_specs:
     dt=shift_distribution(pred[kind+'_'+transport_panel,ia],gap)
     db=pred[kind+'_'+transport_panel,ib]
     du=pred[kind+'_'+updated_panel,ib]
     tr=metric_row(b,dt,42,'time_shifted_'+transport_panel,0.)
     br=metric_row(b,db,42,'recomputed_'+transport_panel,0.)
     ur=metric_row(b,du,42,'source_updated_'+updated_panel,0.)
     row={'cell_id':key[0],'role':b['role'],'arm':key[1],'history_key':key[2],
      'query_a':float(a['query_epoch']),'query_b':float(b['query_epoch']),'gap_weeks':gap,
      'cycle_count_a':cycle_count[ia],'cycle_count_b':cycle_count[ib],
      'factor_pair':pair_name,'transport_panel':transport_panel,'updated_panel':updated_panel,
      'model':kind,
      'target_rul_weeks_at_b':'' if b['target_rul_weeks'] is None else float(b['target_rul_weeks']),
      'y_event_at_b':int(b['y_event']),
      'time_shifted_p_event':float(dt.cdf(0.)),
      'source_updated_p_event':float(du.cdf(0.)),
      'time_shifted_mean_weeks':dt.mean(),'recomputed_base_mean_weeks':db.mean(),
      'source_updated_mean_weeks':du.mean(),
      'time_shifted_cdf_transport_vs_source_update':float(np.max(np.abs(np.asarray(dt.cdf(TAU))-np.asarray(du.cdf(TAU))))),
      'source_arrival':'cycle arrival unobserved; assumed available at source completion'}
     for metric in ('event_brier','mean_abs_error','Brier4','Brier12'):
      row['time_shifted_'+metric]=tr.get(metric,'')
      row['recomputed_transport_'+metric]=br.get(metric,'')
      row['source_updated_'+metric]=ur.get(metric,'')
     out.append(row)
 return out

def _cell_boot_summary(groups,model,pair,arm,metric,negative_note):
 out=[]
 for (m,p,a),vals in sorted(groups.items()):
  x=np.asarray([v for _,v,_ in vals],float)
  if not len(x): continue
  boot=np.mean(np.random.RandomState(42).choice(x,(2000,len(x)),replace=True),axis=1)
  out.append({'model':m,'factor_pair':p,'arm':a,'outcome_metric':metric,'n_cells':len(x),
   'n_pairs':sum(n for _,_,n in vals),'mean_cell_paired_delta_source_minus_time_shift':float(x.mean()),
   'bootstrap95_low':float(np.quantile(boot,.025)),'bootstrap95_high':float(np.quantile(boot,.975)),
   'negative_favors_source_update':negative_note})
 return out

def summarize_pairs(rows):
 metrics=('mean_abs_error','event_brier','Brier4','Brier12')
 # Direct paired source-update minus elapsed-time transport effects, averaged
 # first within physical cell and only then bootstrapped over cells.
 cell_values=collections.defaultdict(list)
 pair_index={}
 for r in rows:
  ident=(r['model'],r['arm'],r['cell_id'],r['history_key'],r['query_a'],r['query_b'])
  pair_index.setdefault(ident,{})[r['factor_pair']]=r
 for ident,pairs in pair_index.items():
  model,arm,cid,*_=ident
  for pair_name,r in pairs.items():
   for metric in metrics:
    x=r.get('source_updated_'+metric,'');y=r.get('time_shifted_'+metric,'')
    if x not in ('',None) and y not in ('',None) and math.isfinite(float(x)) and math.isfinite(float(y)):
     cell_values[(model,pair_name,arm,cid,metric)].append((float(x)-float(y)))
 direct=collections.defaultdict(list)
 for (model,pair,arm,cid,metric),vals in cell_values.items():
  if vals: direct[(model,pair,arm,metric)].append((cid,float(np.mean(vals)),len(vals)))
 out=[]
 for (model,pair,arm,metric),vals in sorted(direct.items()):
  out.extend(_cell_boot_summary({(model,pair,arm):vals},model,pair,arm,metric,True))
 # Matched difference-in-differences on identical physical-cell/RPT query pairs.
 did_specs=(('F3_self_transport','F1_self_transport','DID_F3_minus_F1_selfupdate'),
            ('F2_self_transport','F0_self_transport','DID_F2_minus_F0_selfupdate'))
 # Build metric-specific DID summaries (kept separate to avoid mixing units).
 did_groups=collections.defaultdict(lambda:collections.defaultdict(list))
 for left,right,label in did_specs:
  for ident,pairs in pair_index.items():
   model,arm,cid,*_=ident
   if left not in pairs or right not in pairs: continue
   l,r=pairs[left],pairs[right]
   for metric in metrics:
    lx,ly=l.get('source_updated_'+metric,''),l.get('time_shifted_'+metric,'')
    rx,ry=r.get('source_updated_'+metric,''),r.get('time_shifted_'+metric,'')
    if any(v in ('',None) for v in (lx,ly,rx,ry)): continue
    vals=[float(lx),float(ly),float(rx),float(ry)]
    if all(math.isfinite(v) for v in vals):
     did=(vals[0]-vals[1])-(vals[2]-vals[3])
     did_groups[(model,label,arm,metric)][cid].append(did)
 for (model,label,arm,metric),cells_map in sorted(did_groups.items()):
  cells=[(cid,float(np.mean(v)),len(v)) for cid,v in sorted(cells_map.items())]
  out.extend(_cell_boot_summary({(model,label,arm):cells},model,label,arm,'DID_'+metric,True))
 return out

def run(go_path):
 g=readj(go_path);start=time.time()
 rec={'schema':'OFF_RPT_GRID_ZERO_FIT_RECEIPT_V1','status':'PREFLIGHT','request_id':g.get('request_id'),
  'model_fits':0,'optimizer_steps':0,'inference_rows':0,'C4_payload_reads':0,
  'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'c3_source_files':[]}
 try:
  if g.get('status')!='APPROVED' or g.get('allow_inference') is not True or g.get('allow_fits') is not False:
   raise ValueError('fresh zero-fit GO not approved')
  coord=readj(ROOT/'automation/state/coordinator.json')
  if g.get('owner_thread_id')!=coord.get('owner') or coord.get('thread_id')!=g.get('owner_thread_id') or coord.get('state')!='ACTIVE' or coord.get('actual_cwd')!='/home/yndx/zxk/rul' or coord.get('takeover_verified') is not True:
   raise ValueError('coordinator ownership gate failed')
  now=datetime.datetime.now(datetime.timezone.utc)
  hb=datetime.datetime.fromisoformat(coord['heartbeat_utc'].replace('Z','+00:00'))
  issued=datetime.datetime.fromisoformat(g['issued_utc'].replace('Z','+00:00'))
  if (now-hb).total_seconds()>1800 or (now-issued).total_seconds()>86400: raise ValueError('stale GO/coordinator heartbeat')
  if g.get('source_sha256')!=source_hashes(): raise ValueError('source SHA map mismatch')
  if g.get('data_manifest_sha256')!=sha(DATA_MAN) or g.get('cohort_sha256')!=sha(COHORT): raise ValueError('DataV2/cohort SHA mismatch')
  receipt_path=ROOT/g['formal_receipt_path']
  if sha(receipt_path)!=g.get('formal_receipt_sha256'): raise ValueError('formal run receipt SHA mismatch')
  fr=readj(receipt_path)
  if fr.get('status')!='SUCCESS' or fr.get('CPU_fits_started')!=80 or fr.get('CPU_fits_completed')!=80 or fr.get('C4_payload_reads')!=0:
   raise ValueError('formal run is not complete 80-fit C4-free success')
  if fr.get('data',{}).get('train_queries')!=6870 or fr.get('data',{}).get('development_queries')!=3765:
   raise ValueError('formal frozen query counts differ from exact GO binding')
  formal_out=(ROOT/g['formal_output']).resolve()
  if formal_out!=pathlib.Path(fr['output']).resolve(): raise ValueError('formal output path binding mismatch')
  artifact_hashes=g.get('formal_artifact_sha256')
  expected_artifacts={f'{kind}_{panel}_{suffix}.joblib' for kind in KINDS for panel in PANELS for suffix in ('event','positive','distribution')}
  if not isinstance(artifact_hashes,dict) or set(artifact_hashes)!=expected_artifacts:
   raise ValueError('GO must bind SHA256 for all 24 saved formal model artifacts')
  for fname,expected in artifact_hashes.items():
   if sha(formal_out/fname)!=expected: raise ValueError('formal model artifact SHA mismatch: '+fname)
  rptinv=inventory(ROOT/g['rpt_feature_manifest'],g['rpt_feature_manifest_sha256'],'ALL188_FEATURE_CACHE_COMPLETE')
  cycinv=inventory(ROOT/g['cycling_feature_manifest'],g['cycling_feature_manifest_sha256'],'SUCCESS')
  if set(rptinv)!=set(cycinv): raise ValueError('RPT/Cycling cell inventory mismatch')
  out=(ROOT/g['output']).resolve()
  if HERE.resolve() not in out.parents: raise ValueError('output must be new directory under factorial experiment')
  claim=HERE/(str(g['request_id'])+'.offgrid.claim.json')
  writej(claim,{'GO_sha256':sha(go_path),'claimed_utc':now.isoformat()})
  out.mkdir(parents=False,exist_ok=False)
  cells=load_c3_cells();c3={c['cell_id'] for c in cells}
  if c3!={cid for cid,x in rptinv.items() if x['role']=='development'} or c3!={cid for cid,x in cycinv.items() if x['role']=='development'}:
   raise ValueError('C3 source and feature inventories differ')
  examples=[]
  for c in cells: examples.extend(build_grid_examples(c))
  nc=len({e['cell_id'] for e in examples});n=len(examples)
  if not n or n>MAX_EXAMPLES or nc>MAX_CELLS: raise ValueError('off-grid empty grid or row/cell cap exceeded')
  queries=collections.defaultdict(set)
  for e in examples: queries[(e['cell_id'],e['query_epoch'])].add(e['arm'])
  if any(v!=set(ARMS) for v in queries.values()) or len(queries)*len(ARMS)!=n:
   raise ValueError('off-grid arms do not share exact query rows')
  import joblib
  models={}
  for kind in KINDS:
   for panel in PANELS:
    name=kind+'_'+panel
    clf=joblib.load(formal_out/(name+'_event.joblib'))
    reg=joblib.load(formal_out/(name+'_positive.joblib'))
    d=joblib.load(formal_out/(name+'_distribution.joblib'))
    res=np.asarray(d['residuals'],float);rw=np.asarray(d['weights'],float)
    if res.ndim!=1 or rw.shape!=res.shape or not len(res) or not np.all(np.isfinite(res)) or not np.all(np.isfinite(rw)) or np.any(rw<0) or abs(float(rw.sum())-1)>1e-8:
     raise ValueError('invalid saved residual distribution '+name)
    models[name]=(clf,reg,res,rw)
  mats={p:[] for p in PANELS};meta=[];bycell=collections.defaultdict(list)
  for i,e in enumerate(examples): bycell[e['cell_id']].append((i,e))
  for cid,items in sorted(bycell.items()):
   ri=rptinv[cid];ci=cycinv[cid];rp=ROOT/ri['path'];cp=ROOT/ci['path']
   if sha(rp)!=ri['sha256'] or sha(cp)!=ci['sha256']: raise ValueError('C3 feature SHA mismatch '+cid)
   rpt=readj(rp);cycle=cycle_asof.build_cycle_index(cp)
   if rpt.get('cell_id')!=cid or rpt.get('role')!='development' or cycle.cell_id!=cid or cycle.role!='development':
    raise ValueError('C3 derived feature identity mismatch '+cid)
   cache={cid:{int(r['source_rpt_index']):r for r in rpt['records']}}
   rec['c3_source_files'].append({'cell_id':cid,'rpt_path':ri['path'],'rpt_sha256':ri['sha256'],
    'cycling_path':ci['path'],'cycling_sha256':ci['sha256'],'rpt_records':len(rpt['records']),
    'cycle_source_records':cycle.source_cycle_count,'cycle_records_used':len(cycle.rows),
    'cycle_clock_excluded_count':cycle.excluded_clock_count,
    'cycle_clock_excluded_source_indices':cycle.excluded_clock_cycle_indices})
   for ix,e in items:
    v=factorial.feature_sets(e,cache,cycle)
    for p in PANELS: mats[p].append(np.asarray(v[p],dtype=np.float32))
    meta.append({'i':ix,'cell_id':cid,'arm':e['arm'],'query_epoch':e['query_epoch'],
     'history_key':e['history_key'],'cycle_count':cycle.features_at(e['query_epoch'])['cycle_source_asof_count']})
   del cache,rpt,cycle
  pred={};rows=[]
  dims={'F0':74,'F1':686,'F2':98,'F3':710}
  for kind in KINDS:
   for panel in PANELS:
    name=kind+'_'+panel;clf,reg,res,rw=models[name];X=np.asarray(mats[panel],float)
    if X.ndim!=2 or X.shape[1]!=dims[panel] or np.isinf(X).any(): raise ValueError('feature matrix invalid '+name)
    where=np.flatnonzero(np.asarray(clf.classes_)==1)
    if len(where)!=1: raise ValueError('event classifier missing class 1 '+name)
    prob=clf.predict_proba(X)[:,where[0]];mu=reg.predict(X)
    for i,e in enumerate(examples):
     raw=HurdleRUL(float(prob[i]),np.exp(float(mu[i])+res),rw)
     dist=PointZero() if e['known_event'] else raw
     r=metric_row(e,dist,42,name,0.);r['unclosed_p_event']=float(prob[i]);r['unclosed_mean_weeks']=raw.mean()
     rows.append(r);pred[name,i]=raw
  rec['data']={'development_source_cells':len(cells),'query_cells':nc,'off_grid_query_times':len(queries),
   'examples_all_arms':n,'prediction_rows_expected':n*len(PANELS)*len(KINDS),'grid_step_seconds':GRID_STEP,
   'start':'second valid source RPT stop + 7 days','end':'last valid source RPT stop',
   'excluded_within_actual_RPT_stop_seconds':1.0,'all_arms_share_query_grid':True}
  write_csv(out/'predictions.csv',rows)
  summary,cellmetrics,reliability=summarize(rows)
  write_csv(out/'arm_summary.csv',summary);write_csv(out/'cell_metrics.csv',cellmetrics);write_csv(out/'reliability_bins.csv',reliability)
  pair=no_new_report_pairs(examples,meta,pred);write_csv(out/'no_new_report_pairs.csv',pair)
  write_csv(out/'no_new_report_summary.csv',summarize_pairs(pair))
  write_jsonl(out/'grid_rows.jsonl',[{'cell_id':e['cell_id'],'role':e['role'],'arm':e['arm'],
   'query_epoch':e['query_epoch'],'history_key':e['history_key'],
   'visible_rpt_source_indices':[int(r['source_rpt_index']) for r in e['visible_records']],
   'visible_rpt_arrival_epochs':[float(r['arrival_epoch']) for r in e['visible_records']],
   'known_event':e['known_event'],'y_event':e['y_event'],'target_rul_weeks':e['target_rul_weeks']} for e in examples])
  rec.update(status='SUCCESS',output=str(out),model_fits=0,optimizer_steps=0,inference_rows=len(rows),
   all_eight_saved_formal_models_reused=True,C4_payload_reads=0)
 except BaseException as ex:
  rec.update(status='FAILED',error=repr(ex),traceback=traceback.format_exc())
 finally:
  rec['elapsed_seconds']=time.time()-start;rec['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
  receipt=HERE/(str(g.get('request_id','missing'))+'_offgrid_receipt.json')
  try: writej(receipt,rec)
  except Exception: pass
 print(json.dumps(rec,ensure_ascii=False,indent=2,allow_nan=True))
 return rec

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--go',required=True);a=ap.parse_args()
 r=run(a.go);sys.exit(0 if r.get('status')=='SUCCESS' else 2)

