#!/home/yndx/miniconda3/envs/a40_env/bin/python
"""Zero-fit conditional next-jump capacity scoring for B2 (raw exact-source queries).

For raw-arm queries whose query epoch equals the last arrived source stop, the next
source RPT transition is the same target as a next-source-capacity baseline. Scores the
observed (gap, C_next) under the joint marked-renewal density (Jacobian to Ah units) and
compares with saved strong next-capacity tree predictions on exact matching keys.
GO-gated; no fits; no C4; no raw archive.
"""
from __future__ import annotations
import argparse,csv,datetime,hashlib,json,math,pathlib,sys,time
import numpy as np
ROOT=pathlib.Path('/home/yndx/zxk/rul');HERE=ROOT/'experiments/trajectory_b2_joint_marked_renewal_20261021/candidate_v2'
OWNER='01a15c3a-1a06-7d61-8517-27b70b246183';WEEK=604800.0
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def atomicj(p,x):
 t=pathlib.Path(str(p)+'.tmp');t.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=True),encoding='utf-8');__import__('os').replace(t,p)
def run(go_path):
 t0=time.time();out=None;receipt=None
 r={'status':'PREFLIGHT_FAILED','fit_count':0,'raw_payload_reads':0,'C4_reads':0}
 try:
  go=json.loads(pathlib.Path(go_path).read_text(encoding='utf-8'))
  req=('status','allow_inference','allow_fit','request_id','owner_thread_id','issued_utc','max_runtime_seconds',
       'cohort_sha256','manifest_sha256','rpt_manifest_sha256','source_sha256','checkpoints','comparator_predictions',
       'comparator_sha256','output_path','receipt_path','data_scope','device')
  if any(k not in go for k in req):raise ValueError('GO missing required field')
  if go['status']!='APPROVED_C3_INFERENCE' or go['allow_inference'] is not True or go['allow_fit'] is not False:raise ValueError('GO not inference-only')
  if go['owner_thread_id']!=OWNER or go['data_scope']!='C3_source63_development_only_no_C4_no_raw':raise ValueError('owner/scope mismatch')
  issued=datetime.datetime.fromisoformat(go['issued_utc'].replace('Z','+00:00'))
  if abs((datetime.datetime.now(datetime.timezone.utc)-issued).total_seconds())>86400:raise ValueError('stale GO')
  COHORT=ROOT/'reports/isu_ilcc_capacity_probe_20261020_root/cohort.json'
  MANIFEST=ROOT/'reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json'
  RPTM=ROOT/'reports/multisource_20261021_signals/all188_rpt_features_v1/manifest.json'
  if sha(COHORT)!=go['cohort_sha256'] or sha(MANIFEST)!=go['manifest_sha256'] or sha(RPTM)!=go['rpt_manifest_sha256']:raise ValueError('manifest hash mismatch')
  sources={n:sha(HERE/n) for n in ('eval_nextjump.py','model.py','target_builder.py')}
  if sources!=go['source_sha256']:raise ValueError('source hash mismatch')
  if sha(go['comparator_predictions'])!=go['comparator_sha256']:raise ValueError('comparator hash mismatch')
  ck={}
  for v,spec in go['checkpoints'].items():
   p=HERE/spec['path'];g=sha(p)
   if g!=spec['sha256']:raise ValueError('checkpoint hash mismatch '+v)
   ck[v]=str(p)
  out=pathlib.Path(go['output_path']);receipt=pathlib.Path(go['receipt_path'])
  if out.exists() or receipt.exists():raise ValueError('output/receipt not fresh')
  import torch
  torch.set_num_threads(4);torch.cuda.set_device(0);dev=torch.device('cuda:0')
  from model import JointMarkedMixtureNet,conditional_delta_capacity_mixture,conditional_anchor_transition_capacity_log_prob
  import target_builder as TB
  import importlib.util
  sys.path[:0]=[str(ROOT/'experiments/isu_irregular_rul_seed42_v1'),str(ROOT/'experiments/dart_rul_v18')]
  from data_adapter import load_reviewed_cell
  co=json.loads(COHORT.read_text());ma=json.loads(MANIFEST.read_text())
  dev_ids=sorted(c for c,role in co['roles'].items() if role=='development')
  rpt=json.loads(RPTM.read_text())
  inv={str(a['cell_id']):a for a in rpt['inventory']}
  models={v:JointMarkedMixtureNet(TB.FIXED_DIM) for v in ck}
  for v,m in models.items():
   m.load_state_dict(torch.load(ck[v],map_location='cpu',weights_only=False));m.to(dev).eval()
  rows=[]
  for cid in dev_ids:
   if cid.endswith('C4'):raise ValueError('C4 in dev cohort')
   p=ROOT/'data/processed/ISU_ILCC_DataV2_v1'/(cid+'.json')
   if sha(p)!=ma['files'][cid]['sha256']:raise ValueError('C3 hash mismatch '+cid)
   cell=load_reviewed_cell(p,'development')
   recs=sorted(cell['records'],key=lambda x:(float(x['stop_epoch']),int(x['source_rpt_index'])))
   if len(recs)<4:continue
   a=inv[cid];rp=ROOT/a['path'] if not pathlib.Path(a['path']).is_absolute() else pathlib.Path(a['path'])
   cache=TB._rpt_index(str(rp),cid)
   pol=TB.data_protocol._arm_records(recs,1,'raw');seen=set()
   for i,q in enumerate(recs[:-1]):
    qe=float(q['stop_epoch'])
    if qe<float(recs[1]['stop_epoch'])+WEEK:continue
    vis=[x for x in pol if float(x['arrival_epoch'])<=qe]
    if len(vis)<3:continue
    anchor=vis[-1];aidx=int(anchor['source_rpt_index'])
    if (aidx,) in seen:continue
    seen.add((aidx,))
    if abs(float(anchor['stop_epoch'])-qe)>1e-6:continue      # exact-source query only
    if any(float(x['capacityAh'])<=0.20 for x in vis):continue
    nxt=next((x for x in recs if int(x['source_rpt_index'])>aidx),None)
    if nxt is None:continue
    gap=(float(nxt['stop_epoch'])-float(anchor['stop_epoch']))/604800.0
    cprev=float(anchor['capacityAh']);cnext=float(nxt['capacityAh'])
    if gap<=0 or cprev<=0 or cnext<=0:continue
    fixed=TB._f0_and_rpt_anchor(cell,vis,float(anchor['stop_epoch']),qe,cache)
    for v,m in models.items():
     with torch.no_grad():
      params=m(torch.as_tensor(fixed,dtype=torch.float32,device=dev).reshape(1,-1),
               torch.as_tensor(TB._dynamic_from_prefix(vis,float(anchor['stop_epoch'])),dtype=torch.float32,device=dev).reshape(1,-1))[0]
      nll=float(conditional_anchor_transition_capacity_log_prob(params,gap,cprev,cnext,v))
      w,mu,sd=conditional_delta_capacity_mixture(params,gap,v)
     wl=w.detach().cpu().numpy();ml=mu.detach().cpu().numpy();sl=sd.detach().cpu().numpy()
     m1=float((wl*np.exp(ml+0.5*sl*sl)).sum());m2=float((wl*np.exp(2*ml+2*sl*sl)).sum())
     pm=cprev*m1;ps=cprev*math.sqrt(max(m2-m1*m1,0.0))
     rows.append({'cell_id':cid,'arm':'raw','query_epoch':int(round(qe)),'variant':v,'gap_weeks':gap,
                  'capacity_prev_ah':cprev,'capacity_next_ah':cnext,'nll_per_ah':nll,
                  'pred_mean_ah':pm,'pred_sd_ah':ps})
  if not rows:raise ValueError('no raw exact-source next-jump rows')
  comp=list(csv.DictReader(open(go['comparator_predictions'])))
  cmap={}
  for c in comp:
   try:cmap[(c['cell_id'],c['arm'],int(round(float(c['query_epoch']))))]=c
   except Exception:pass
  matched=[]
  for x in rows:
   c=cmap.get((x['cell_id'],x['arm'],x['query_epoch']))
   if c is None:continue
   if abs(float(c.get('target_capacity_ah','nan'))-x['capacity_next_ah'])>1e-6:continue
   matched.append({**x,'comparator_pred':float(c['predicted_capacity_ah']),'comparator_sigma':float(c['sigma_oof_ah']),'comparator_panel':c.get('panel','')})
  if not matched:raise ValueError('no exact matched comparator rows')
  # metrics
  res={'status':'SUCCESS','rows':len(rows),'matched':len(matched),'fit_count':0,'C4_reads':0,'source_sha256':sources}
  for v in models:
   sub=[x for x in matched if x['variant']==v]
   if not sub:continue
   by={}
   for x in sub:by.setdefault(x['cell_id'],[]).append(x)
   res[v]={'cells':len(by),'queries':len(sub),
           'cell_nll_per_ah':float(np.mean([np.mean([z['nll_per_ah'] for z in c]) for c in by.values()])),
           'cell_RMSE_mean_ah':float(np.sqrt(np.mean([np.mean([(z['pred_mean_ah']-z['capacity_next_ah'])**2 for z in c]) for c in by.values()]))),
           'cell_MAE_mean_ah':float(np.mean([np.mean([abs(z['pred_mean_ah']-z['capacity_next_ah']) for z in c]) for c in by.values()]))}
  # comparator on the same keys (one row per key)
  by={}
  for x in matched:
   k=(x['cell_id'],x['query_epoch'])
   by.setdefault(x['cell_id'],{}).setdefault(k,x)
  comps=[]
  for cid,d in by.items():
   for k,x in d.items():
    sig=x['comparator_sigma'];mu=x['comparator_pred'];y=x['capacity_next_ah']
    nll=0.5*math.log(2*math.pi*sig*sig)+(mu-y)**2/(2*sig*sig)
    comps.append({'cell_id':cid,'nll_per_ah':nll,'err':mu-y})
  byc={}
  for x in comps:byc.setdefault(x['cell_id'],[]).append(x)
  res['comparator_tree']={'cells':len(byc),'queries':len(comps),
      'cell_nll_per_ah':float(np.mean([np.mean([z['nll_per_ah'] for z in c]) for c in byc.values()])),
      'cell_RMSE_mean_ah':float(np.sqrt(np.mean([np.mean([z['err']**2 for z in c]) for c in byc.values()]))),
      'cell_MAE_mean_ah':float(np.mean([np.mean([abs(z['err']) for z in c]) for c in byc.values()]))}
  out.mkdir(parents=True,exist_ok=False)
  with (out/'nextjump_scores.csv').open('w',newline='',encoding='utf-8') as f:
   w=csv.DictWriter(f,fieldnames=list(matched[0].keys()));w.writeheader();w.writerows(matched)
  atomicj(out/'summary.json',res);r.update(status='SUCCESS',summary=res,elapsed_seconds=time.time()-t0)
 except BaseException as e:
  r.update(status='FAILED',error=repr(e),traceback=__import__('traceback').format_exc())
 finally:
  if out and out.exists():atomicj(out/'receipt.json',r)
  if receipt:
   receipt.parent.mkdir(parents=True,exist_ok=True)
   with receipt.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,ensure_ascii=False,allow_nan=True)
 print(json.dumps({k:v for k,v in r.items() if k!='summary'},indent=2)[:1200]);return r
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--go',required=True);args=ap.parse_args();z=run(args.go);sys.exit(0 if z['status']=='SUCCESS' else 2)
