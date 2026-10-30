#!/usr/bin/env python3
"""Fixed 2/3/5-checkup trend comparison on audited KIT development histories."""
from pathlib import Path
import bisect,collections,csv,datetime,fcntl,hashlib,json,math,statistics,time,traceback
import numpy as np

R=Path('/home/yndx/zxk/rul');E=R/'experiments/rulaas_external_kit_20261030';O=E/'trend_window01';W=604800.
owner='01a17810-6ae6-7cf2-9729-5bfcaa8df5f4';gp=E/'GO_TREND_WINDOW01.json'
stamp=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def out(p,x):
    with p.open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def incsv(p):
    with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def csvout(p,rows):
    assert rows
    with p.open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def val(x):return None if x=='' else float(x)
def result_stats(rows):
    event=[r for r in rows if r['target'] is not None];cen=[r for r in rows if r['censor'] is not None];pos=[r for r in cen if r['censor']>0];mature=[r for r in rows if r['horizon'] is not None]
    tp=sum(r['horizon']==1 and r['median']<=4 for r in mature);fp=sum(r['horizon']==0 and r['median']<=4 for r in mature)
    tn=sum(r['horizon']==0 and r['median']>4 for r in mature);fn=sum(r['horizon']==1 and r['median']>4 for r in mature)
    return dict(queries=len(rows),cells=len({r['cell'] for r in rows}),event_queries=len(event),censored_queries=len(cen),
        positive_followup_censored_queries=len(pos),predicted_before_censor_queries=sum(r['median']<r['censor'] for r in pos),
        event_query_MAE_weeks=statistics.mean(abs(r['median']-r['target']) for r in event) if event else None,
        TP=tp,FP=fp,TN=tn,FN=fn,unknown_horizon_queries=len(rows)-len(mature),
        fallback_queries=sum(r['fallback'] for r in rows),
        fewer_than_requested_window_queries=sum(r['window_used']<r['window_requested'] for r in rows))

locks=[];t0=time.time();rec=dict(status='STARTED',local_regression_fits=0,new_model_predictions=0,new_global_model_fits=0,
    C3_payload_reads=0,C4_payload_reads=0,confirmation_groups_opened=0,actual_coordinator_model_recorded='gpt-6.1-terra')
try:
    for p in [R/'automation/state/coordinator.lock',R/'automation/locks/isu_irregular_rul_cpu.lock']:
        f=p.open('a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
    cp=R/'automation/state/coordinator.json';co=read(cp);assert co['owner']==co['thread_id']==owner and co['state']=='ACTIVE'
    assert co['rulaas_20261029']['stage']=='EXTERNAL_KIT_SLOPE_CENSOR_DIAGNOSTIC_REVIEW_PASS' and co['rulaas_20261029']['github_sync_pending'] is False
    assert read(E/'slope_censor_diagnostic01/INDEPENDENT_RECOMPUTE.json')['status']=='PASS'
    assert read(E/'eis_value01/ROOT_DECISION.json')['status']=='NO_GAIN_FIXED_KIT_EIS_INFORMATION'
    assert read(E/'anchor_day100_01/ROOT_DECISION.json')['status']=='NO_GAIN_FIXED_KIT_SLOPE_ANCHOR'
    split=read(E/'TRAIN_SPLIT.json');fit=set(split['fit_groups']);val_groups=set(split['internal_validation_groups']);locked=set(split['external_confirmation_groups_locked'])
    assert len(fit)==45 and len(val_groups)==15 and len(locked)==16 and not fit&val_groups and not(fit|val_groups)&locked
    fallback=read(E/'anchor_day100_01/fit_manifest.json')['fallback_median_weeks'];assert fallback>0 and math.isfinite(fallback)
    assert not gp.exists() and not O.exists()
    paths=['AGENTS.md','experiments/rulaas_external_kit_20261030/TRAIN_SPLIT.json',
        'experiments/rulaas_external_kit_20261030/development_audit01/development_candidates.csv',
        'experiments/rulaas_external_kit_20261030/anchor_day100_01/fit_manifest.json',
        'experiments/rulaas_external_kit_20261030/anchor_day100_01/predictions.csv',
        'experiments/rulaas_external_kit_20261030/slope_censor_diagnostic01/INDEPENDENT_RECOMPUTE.json',
        'experiments/rulaas_external_kit_20261030/TREND_WINDOW_PROTOCOL_ZH.md',
        'experiments/rulaas_external_kit_20261030/trend_window.py']
    go=dict(status='APPROVED',request_id='KIT_TREND_WINDOW_20261030_01',owner=owner,issued_utc=stamp(),actual_model='gpt-6.1-terra',
        allow_global_fits=False,local_linear_fit_cap=1038,new_prediction_cap=1038,seed=42,group_bootstrap_draws=10000,
        familywise_CI=0.975,allow_confirmation_groups=False,allow_C3=False,allow_C4=False,input_sha256={p:sha(R/p) for p in paths})
    out(gp,go);O.mkdir();out(E/'KIT_TREND_WINDOW_20261030_01.claim.json',dict(GO_sha256=sha(gp),claimed_utc=stamp()))
    co['heartbeat_utc']=stamp();co['rulaas_20261029'].update(stage='EXTERNAL_KIT_TREND_WINDOW_ACTIVE',current_GO=str(gp.relative_to(R)),max_new_fits=1038,max_prediction_rows=1038)
    cp.write_text(json.dumps(co,ensure_ascii=False,indent=2)+'\n')
    saved=[r for r in incsv(E/'anchor_day100_01/predictions.csv') if r['model']=='slope']
    baseline={(r['cell_id'],float(r['query_epoch'])):r for r in saved};assert len(baseline)==len(saved)==519
    histories=collections.defaultdict(list)
    with (E/'development_audit01/development_candidates.csv').open(encoding='utf-8',newline='') as f:
        for r in csv.DictReader(f):
            g=r['source_group']
            if g not in val_groups:continue
            assert g not in locked and g not in fit
            histories[r['cell_id']].append(r)
    for cid,rs in histories.items():
        rs.sort(key=lambda r:float(r['timestamp_s']));ts=[float(r['timestamp_s']) for r in rs]
        assert len(ts)==len(set(ts)) and all(a<b for a,b in zip(ts,ts[1:])) and all(r['source_group'] in val_groups for r in rs)
    outputs=[];reconstructed=0
    for (cid,q),ref in sorted(baseline.items()):
        rs=histories[cid];times=[float(r['timestamp_s']) for r in rs];j=bisect.bisect_right(times,q)
        assert j>=2 and times[j-1]==q and ref['source_group']==rs[j-1]['source_group'] and all(t<=q for t in times[:j])
        cap0=float(rs[0]['cap_aged_est_Ah']);cur=float(rs[j-1]['cap_aged_est_Ah']);prev=float(rs[j-2]['cap_aged_est_Ah']);dt=(times[j-1]-times[j-2])/W
        assert float(rs[0]['num_cycles_checkup'])<=1 and dt>0 and cur>.8*cap0 and int(float(rs[j-1]['timestamp_origin']))==1
        s2=(cur-prev)/dt;point2=(cur-.8*cap0)/(-s2) if s2<0 else fallback
        assert math.isclose(point2,float(ref['median_weeks']),rel_tol=1e-10,abs_tol=1e-9) and (s2>=0)==(ref['slope_fallback']=='True')
        reconstructed+=1
        common=dict(cell=cid,source_group=ref['source_group'],query_epoch=q,label_status=ref['label_status'],
                    target=val(ref['target_rul_weeks']),censor=val(ref['censor_lower_weeks']),horizon=val(ref['target_within4']))
        assert (common['target'] is not None and common['censor'] is None) if common['label_status']=='event_observed_later' else (common['target'] is None and common['censor'] is not None)
        outputs.append(dict(model='last2',**common,median=float(ref['median_weeks']),window_requested=2,window_used=2,fallback=s2>=0))
        for k in (3,5):
            ix=max(0,j-k);sub=rs[ix:j];t=[(float(x['timestamp_s'])-q)/W for x in sub];c=[float(x['cap_aged_est_Ah']) for x in sub]
            assert len(sub)>=2 and len(sub)<=k and max(t)<=0 and all(math.isfinite(x) for x in t+c)
            tm=statistics.mean(t);cm=statistics.mean(c);den=sum((x-tm)**2 for x in t);assert den>0
            slope=sum((a-tm)*(b-cm) for a,b in zip(t,c))/den;rec['local_regression_fits']+=1
            pred=(cur-.8*cap0)/(-slope) if slope<0 else fallback
            assert math.isfinite(pred) and pred>0 and rec['local_regression_fits']<=go['local_linear_fit_cap']
            outputs.append(dict(model='ols'+str(k),**common,median=pred,window_requested=k,window_used=len(sub),fallback=slope>=0));rec['new_model_predictions']+=1
            assert rec['new_model_predictions']<=go['new_prediction_cap']
    assert reconstructed==519 and rec['local_regression_fits']==rec['new_model_predictions']==1038 and len(outputs)==1557
    by=collections.defaultdict(list)
    for r in outputs:by[r['model'],r['cell']].append(r)
    models=['last2','ols3','ols5'];cells=sorted({r['cell'] for r in outputs});eventcells=sorted({r['cell'] for r in outputs if r['target'] is not None});eventgroups=sorted({r['source_group'] for r in outputs if r['target'] is not None})
    assert len(cells)==34 and len(eventcells)==16 and len(eventgroups)==6
    cellrows=[];summary=[]
    for m in models:
        rows=[r for r in outputs if r['model']==m];s=result_stats(rows)
        assert (s['queries'],s['event_queries'],s['censored_queries'],s['positive_followup_censored_queries'],s['unknown_horizon_queries'])==(519,105,414,396,18)
        for cid in cells:
            rr=by[m,cid];cellrows.append(dict(model=m,cell_id=cid,source_group=rr[0]['source_group'],**result_stats(rr)))
        evcells=[x for x in cellrows if x['model']==m and x['event_queries']]
        s['event_cell_macro_MAE_weeks']=statistics.mean(x['event_query_MAE_weeks'] for x in evcells)
        positive=[r for r in rows if r['horizon']==1];pc={r['cell'] for r in positive}
        s['pre_event_episode_cells']=len(pc);s['missed_episode_cells']=sum(not any(r['median']<=4 for r in positive if r['cell']==cid) for cid in pc)
        assert s['TP']+s['FN']==16 and s['FP']+s['TN']==485 and len(pc)==16
        summary.append(dict(model=m,**s))
    assert math.isclose(summary[0]['event_cell_macro_MAE_weeks'],2.791665377384949,rel_tol=1e-12) and (summary[0]['TP'],summary[0]['FP'],summary[0]['TN'],summary[0]['FN'])==(16,3,482,0)
    cm={(x['model'],x['cell_id']):x for x in cellrows};rng=np.random.RandomState(42);draws=rng.randint(0,len(eventgroups),size=(10000,len(eventgroups)))
    contrasts=[];paired=[];summ={x['model']:x for x in summary}
    for candidate in ('ols3','ols5'):
        deltas={cid:cm[candidate,cid]['event_query_MAE_weeks']-cm['last2',cid]['event_query_MAE_weeks'] for cid in eventcells}
        group_sum=np.array([sum(deltas[cid] for cid in eventcells if cm['last2',cid]['source_group']==g) for g in eventgroups]);group_n=np.array([sum(cm['last2',cid]['source_group']==g for cid in eventcells) for g in eventgroups]);boot=group_sum[draws].sum(axis=1)/group_n[draws].sum(axis=1)
        low,high=map(float,np.quantile(boot,[.0125,.9875]));delta=statistics.mean(deltas.values());relative=(summ['last2']['event_cell_macro_MAE_weeks']-summ[candidate]['event_cell_macro_MAE_weeks'])/summ['last2']['event_cell_macro_MAE_weeks']
        passed=relative>=.05 and high<0 and summ[candidate]['missed_episode_cells']<=summ['last2']['missed_episode_cells'] and summ[candidate]['FP']<=summ['last2']['FP'] and summ[candidate]['predicted_before_censor_queries']<=summ['last2']['predicted_before_censor_queries']
        contrasts.append(dict(candidate=candidate,reference='last2',delta_event_cell_macro_MAE_weeks=delta,CI97_5_low=low,CI97_5_high=high,relative_improvement=relative,cells_better=sum(x<0 for x in deltas.values()),cells_worse=sum(x>0 for x in deltas.values()),development_gate_pass=passed))
        for cid in eventcells:paired.append(dict(candidate=candidate,cell_id=cid,source_group=cm['last2',cid]['source_group'],candidate_MAE=cm[candidate,cid]['event_query_MAE_weeks'],last2_MAE=cm['last2',cid]['event_query_MAE_weeks'],delta_MAE=deltas[cid]))
    group_rows=[]
    for m in models:
        for g in sorted({r['source_group'] for r in outputs}):
            rr=[r for r in outputs if r['model']==m and r['source_group']==g];group_rows.append(dict(model=m,source_group=g,**result_stats(rr)))
    csvout(O/'predictions.csv',outputs);csvout(O/'summary.csv',summary);csvout(O/'paired_contrasts.csv',contrasts);csvout(O/'paired_per_cell.csv',paired);csvout(O/'per_group.csv',group_rows)
    passed=[x['candidate'] for x in contrasts if x['development_gate_pass']]
    decision=dict(status='TREND_WINDOW_DEVELOPMENT_SCREEN_PASS_NOT_INDEPENDENT' if passed else 'NO_GAIN_FIXED_TREND_WINDOW',passing_candidates=passed,paper_ready=False,
        baseline='last2',criterion='>=5% lower event-cell macro MAE, 97.5% group-bootstrap upper bound <0, no extra missed event cells, false-positive queries or positive-followup censor-bound early counts',
        prior_eis_and_anchor_NO_GAIN_preserved=True,limits=['six event groups','previously used development outcomes','retrospective cutoff',
            'unknown report arrival and simulated immediate visibility','descriptive censor bound, not exact event','no real queue or inspection cost'])
    out(O/'ROOT_DECISION.json',decision)
    rec.update(status='SUCCESS',finished_utc=stamp(),elapsed_seconds=time.time()-t0,GO_sha256=sha(gp),input_sha256=go['input_sha256'],
        saved_baseline_predictions_reconstructed=reconstructed,validation_queries=519,event_cells=16,event_groups=6,
        feature_prefix_timestamp_checks='PASS',bootstrap_seed=42,bootstrap_draws=10000)
    out(O/'receipt.json',rec)
    co['heartbeat_utc']=stamp();co['rulaas_20261029'].update(stage='EXTERNAL_KIT_TREND_WINDOW_COMPLETE',trend_window_decision=str((O/'ROOT_DECISION.json').relative_to(R)),github_sync_pending=True)
    cp.write_text(json.dumps(co,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(status=decision['status'],summary=summary,contrasts=contrasts),ensure_ascii=False))
except BaseException as e:
    rec.update(status='FAILED',error=repr(e),traceback=traceback.format_exc(),finished_utc=stamp())
    if O.exists() and not (O/'failure_receipt.json').exists():out(O/'failure_receipt.json',rec)
    print(json.dumps(rec,ensure_ascii=False));raise
finally:
    for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
