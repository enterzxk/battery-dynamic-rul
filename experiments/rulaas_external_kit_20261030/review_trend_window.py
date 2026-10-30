#!/usr/bin/env python3
"""Independently reconstruct fixed local fits and reported paired statistics."""
from pathlib import Path
import bisect,collections,csv,datetime,fcntl,hashlib,json,math
import numpy as np
import sklearn
import pandas as pd
R=Path('/home/yndx/zxk/rul');E=R/'experiments/rulaas_external_kit_20261030';O=E/'trend_window01';W=604800.;owner='01a17810-6ae6-7cf2-9729-5bfcaa8df5f4'
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def out(p,x):
    with p.open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
locks=[];checks=0
try:
    for p in [R/'automation/state/coordinator.lock',R/'automation/locks/isu_irregular_rul_cpu.lock']:
        f=p.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
    cp=R/'automation/state/coordinator.json';co=read(cp);assert co['owner']==co['thread_id']==owner and co['state']=='ACTIVE' and co['rulaas_20261029']['stage']=='EXTERNAL_KIT_TREND_WINDOW_COMPLETE'
    assert read(O/'receipt.json')['status']=='SUCCESS' and read(O/'ROOT_DECISION.json')['status']=='NO_GAIN_FIXED_TREND_WINDOW'
    gp=E/'GO_TREND_WINDOW_REVIEW01.json';assert not gp.exists() and not (O/'INDEPENDENT_RECOMPUTE.json').exists()
    paths=['experiments/rulaas_external_kit_20261030/GO_TREND_WINDOW01.json','experiments/rulaas_external_kit_20261030/TRAIN_SPLIT.json',
       'experiments/rulaas_external_kit_20261030/development_audit01/development_candidates.csv',
       'experiments/rulaas_external_kit_20261030/anchor_day100_01/predictions.csv',
       'experiments/rulaas_external_kit_20261030/anchor_day100_01/fit_manifest.json',
       'experiments/rulaas_external_kit_20261030/trend_window01/predictions.csv',
       'experiments/rulaas_external_kit_20261030/trend_window01/summary.csv',
       'experiments/rulaas_external_kit_20261030/trend_window01/paired_contrasts.csv',
       'experiments/rulaas_external_kit_20261030/review_trend_window.py']
    out(gp,dict(status='APPROVED',owner=owner,issued_utc=now(),new_global_fits=0,reconstruction_local_fit_cap=1038,
                allow_C3=False,allow_C4=False,allow_confirmation_groups=False,input_sha256={p:sha(R/p) for p in paths}))
    split=read(E/'TRAIN_SPLIT.json');val=set(split['internal_validation_groups']);locked=set(split['external_confirmation_groups_locked']);assert not val&locked
    hist=collections.defaultdict(list)
    with (E/'development_audit01/development_candidates.csv').open(newline='',encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['source_group'] in val:
                assert row['source_group'] not in locked
                hist[row['cell_id']].append((float(row['timestamp_s']),float(row['cap_aged_est_Ah'])))
    for cid in hist:hist[cid].sort()
    df=pd.read_csv(O/'predictions.csv');assert len(df)==1557 and set(df.model)=={'last2','ols3','ols5'}
    base=pd.read_csv(E/'anchor_day100_01/predictions.csv');base=base[base.model=='slope'].set_index(['cell_id','query_epoch']);assert len(base)==519
    fallback=float(read(E/'anchor_day100_01/fit_manifest.json')['fallback_median_weeks'])
    for r in df.itertuples(index=False):
        if r.model=='last2':
            assert math.isclose(r.median,float(base.loc[(r.cell,r.query_epoch),'median_weeks']),rel_tol=1e-12,abs_tol=1e-10)
            continue
        k=3 if r.model=='ols3' else 5;a=hist[r.cell];times=[x[0] for x in a];j=bisect.bisect_right(times,r.query_epoch)
        assert j>=2 and times[j-1]==r.query_epoch;prefix=a[max(0,j-k):j];assert all(t<=r.query_epoch for t,_ in prefix)
        tt=np.array([(t-r.query_epoch)/W for t,_ in prefix]);cc=np.array([c for _,c in prefix]);X=np.column_stack([np.ones(len(tt)),tt])
        coef,_,rank,_=np.linalg.lstsq(X,cc,rcond=None);assert rank==2;slope=float(coef[1]);pred=(cc[-1]-.8*a[0][1])/(-slope) if slope<0 else fallback
        assert math.isclose(float(r.median),float(pred),rel_tol=1e-8,abs_tol=1e-8),(r.model,r.cell,r.query_epoch,pred,r.median)
        assert int(r.window_used)==len(prefix) and bool(r.fallback)==(slope>=0);checks+=1
    assert checks==1038
    saved=pd.read_csv(O/'summary.csv').set_index('model');orig=pd.read_csv(O/'paired_contrasts.csv').set_index('candidate')
    group_data={};metrics={}
    for m in ['last2','ols3','ols5']:
        d=df[df.model==m].copy();assert len(d)==519 and not d.duplicated(['cell','query_epoch']).any()
        ev=d[d.target.notna()].copy();cen=d[(d.censor.notna())&(d.censor>0)].copy();known=d[d.horizon.notna()].copy()
        ev['error']=(ev['median']-ev.target).abs();per=ev.groupby(['source_group','cell']).error.mean();group_data[m]=per
        decision=known['median']<=4;label=known.horizon==1
        vals=dict(event_cell_macro_MAE_weeks=float(per.mean()),predicted_before_censor_queries=int((cen['median']<cen.censor).sum()),
                  TP=int((decision&label).sum()),FP=int((decision&~label).sum()),TN=int((~decision&~label).sum()),FN=int((~decision&label).sum()))
        for x,v in vals.items():assert math.isclose(float(saved.loc[m,x]),v,rel_tol=1e-12,abs_tol=1e-10),(m,x,v,saved.loc[m,x])
        metrics[m]=vals
    groups=sorted(group_data['last2'].index.get_level_values(0).unique());assert len(groups)==6
    draws=np.random.RandomState(42).randint(0,len(groups),size=(10000,len(groups)))
    contrasts={}
    for m in ['ols3','ols5']:
        delta=group_data[m]-group_data['last2'];assert len(delta)==16 and not delta.isna().any()
        sums=np.array([delta.loc[g].sum() for g in groups]);counts=np.array([len(delta.loc[g]) for g in groups]);bs=sums[draws].sum(axis=1)/counts[draws].sum(axis=1);lo,hi=np.quantile(bs,[.0125,.9875])
        for col,v in [('delta_event_cell_macro_MAE_weeks',delta.mean()),('CI97_5_low',lo),('CI97_5_high',hi)]:assert math.isclose(float(orig.loc[m,col]),float(v),rel_tol=1e-11,abs_tol=1e-10)
        assert int(orig.loc[m,'cells_better'])==int((delta<0).sum()) and int(orig.loc[m,'cells_worse'])==int((delta>0).sum())
        assert not bool(orig.loc[m,'development_gate_pass'])
        contrasts[m]=dict(delta=float(delta.mean()),CI97_5_low=float(lo),CI97_5_high=float(hi),cells_better=int((delta<0).sum()),cells_worse=int((delta>0).sum()))
    result=dict(status='PASS',candidate_predictions_recomputed_from_past_prefix=checks,method='independent numpy.linalg.lstsq',saved_baselines_checked=519,
        paired_statistics_recomputed=True,group_bootstrap_seed=42,group_bootstrap_draws=10000,metrics=metrics,contrasts=contrasts,
        new_global_fits=0,local_fit_reconstruction_checks=checks,C3_payload_reads=0,C4_payload_reads=0,confirmation_groups_opened=0,GO_sha256=sha(gp),finished_utc=now(),
        limit='Development outcomes previously inspected; six event groups; unknown true reporting delay.')
    out(O/'INDEPENDENT_RECOMPUTE.json',result)
    co['heartbeat_utc']=now();co['rulaas_20261029'].update(stage='EXTERNAL_KIT_TREND_WINDOW_NO_GAIN_REVIEW_PASS',trend_window_review=str((O/'INDEPENDENT_RECOMPUTE.json').relative_to(R)))
    cp.write_text(json.dumps(co,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(status='PASS',checks=checks,metrics=metrics,contrasts=contrasts),ensure_ascii=False))
finally:
    for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
