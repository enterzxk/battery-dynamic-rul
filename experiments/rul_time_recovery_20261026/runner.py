#!/usr/bin/env python3
"""Frozen cache-only, cell-isolated RUL baseline experiment; six fits maximum."""
import os
os.environ['OMP_NUM_THREADS'] = '4'
os.environ['MKL_NUM_THREADS'] = '4'
os.environ['OPENBLAS_NUM_THREADS'] = '4'
import argparse, collections, csv, datetime, fcntl, hashlib, json, math
import pathlib, signal, sys, time, traceback
import numpy as np
import joblib
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = pathlib.Path('/home/yndx/zxk/rul')
HERE = ROOT / 'experiments/rul_time_recovery_20261026'
CACHE = ROOT / 'experiments/multisource_factorial_20261021/run2_clocksafe'
sys.path.insert(0, str(ROOT / 'experiments/dart_rul_v18'))
from evaluate import metric_row, summarize, write_csv, PointZero
from hgb_models import EmpiricalRUL

def sha(p):
    h = hashlib.sha256()
    with pathlib.Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()

def readj(p):
    return json.loads(pathlib.Path(p).read_text())

def createj(p, obj):
    with pathlib.Path(p).open('x') as f:
        json.dump(obj, f, indent=2, allow_nan=False)

def utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def weights(cells):
    counts = collections.Counter(cells)
    return np.array([1. / counts[c] for c in cells])

def key(r):
    return str(r['cell_id']), str(r['arm']), float(r['query_epoch'])

def jsonlines(p):
    return [json.loads(l) for l in p.open()]

def saveprogress(out, rec):
    p = out / 'progress.json.tmp'
    p.write_text(json.dumps(rec, indent=2))
    os.replace(p, out / 'progress.json')

def point_report(rows, baseline, out):
    """Keep strata/cells and use paired physical-cell bootstrap, including harms."""
    cells_out, summary = [], []
    for model in sorted({r['model'] for r in rows}):
        for arm in ['raw', 'sparse2', 'delay7d']:
            for stratum in ['all', 'unconfirmed', 'known_event', 'hidden_event', 'early_gt12w', 'near_le4w']:
                def selected(r):
                    t = r['target_rul_weeks']
                    if t in ['', None]: return False
                    return (stratum == 'all' or
                            stratum == 'unconfirmed' and not r['known_event'] or
                            stratum == 'known_event' and r['known_event'] or
                            stratum == 'hidden_event' and r['y_event'] == 1 and not r['known_event'] or
                            stratum == 'early_gt12w' and t > 12 or
                            stratum == 'near_le4w' and 0 < t <= 4)
                ss = [r for r in rows if r['model'] == model and r['arm'] == arm and selected(r)]
                cc = []
                for cid in sorted({r['cell_id'] for r in ss}):
                    rs = [r for r in ss if r['cell_id'] == cid]
                    y = np.array([r['target_rul_weeks'] for r in rs])
                    p = np.array([r['point_weeks'] for r in rs])
                    b = np.array([baseline[key(r)]['median_weeks'] for r in rs])
                    bm = np.array([baseline[key(r)]['mean_weeks'] for r in rs])
                    c = dict(model=model, arm=arm, stratum=stratum, cell_id=cid, n=len(rs),
                             mae=float(np.mean(abs(p-y))), mse=float(np.mean((p-y)**2)),
                             baseline_median_mae=float(np.mean(abs(b-y))),
                             baseline_mean_mae=float(np.mean(abs(bm-y))),
                             overestimate_gt4w=float(np.mean(p-y > 4)))
                    c['delta_vs_baseline_median'] = c['mae']-c['baseline_median_mae']
                    cc.append(c); cells_out.append(c)
                if not cc: continue
                delta = np.array([c['delta_vs_baseline_median'] for c in cc])
                rng = np.random.default_rng(42)
                boot = delta[rng.integers(0,len(cc),(5000,len(cc)))].mean(1)
                lo, hi = np.quantile(boot,[.025,.975])
                s = dict(model=model, arm=arm, stratum=stratum, n_cells=len(cc), n_queries=len(ss),
                         mae_weeks=float(np.mean([c['mae'] for c in cc])),
                         rmse_weeks=float(np.sqrt(np.mean([c['mse'] for c in cc]))),
                         baseline_median_mae=float(np.mean([c['baseline_median_mae'] for c in cc])),
                         baseline_mean_mae=float(np.mean([c['baseline_mean_mae'] for c in cc])),
                         delta_mae=float(delta.mean()), ci_low=float(lo), ci_high=float(hi),
                         improved_cell_fraction=float(np.mean(delta < 0)),
                         worst_cell_delta=float(delta.max()))
                summary.append(s)
    write_csv(out/'paired_per_cell.csv', cells_out)
    write_csv(out/'point_summary.csv', summary)
    return summary

def main(go_path):
    start = time.time(); g = readj(go_path); locks = []; out = None
    rec = dict(request_id=g['request_id'], status='PREFLIGHT', started_utc=utc(),
               fits_started=0, fits_completed=0, C4_payload_reads=0,
               development_fit_rows=0, max_fits=6, predictions=0)
    try:
        assert g['allow_fit'] is True and g['max_fits'] == 6
        assert g['owner_thread_id'] == '01a17810-6ae6-7cf2-9729-5bfcaa8df5f4'
        coord = readj(ROOT/'automation/state/coordinator.json')
        assert coord['owner'] == coord['thread_id'] == g['owner_thread_id']
        assert coord['state'] == 'ACTIVE' and coord['takeover_verified'] is True
        assert coord['actual_cwd'] == str(ROOT)
        hb = datetime.datetime.fromisoformat(coord['heartbeat_utc'].replace('Z','+00:00'))
        assert (datetime.datetime.now(datetime.timezone.utc)-hb).total_seconds() < 1800
        for rel, digest in g['input_sha256'].items():
            assert sha(ROOT/rel) == digest, 'Hash mismatch: '+rel
        assert g['input_sha256'][str(pathlib.Path(__file__).relative_to(ROOT))] == sha(__file__)
        for name in ['automation/state/online_survival_cpu.lock','automation/locks/isu_irregular_rul_cpu.lock']:
            f = (ROOT/name).open('a+'); fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB); locks.append(f)
        registry = ROOT/'experiments/state/consumed_gos.jsonl'
        with registry.open('a+') as f:
            fcntl.flock(f,fcntl.LOCK_EX); f.seek(0)
            assert all(json.loads(l).get('request_id') != g['request_id'] for l in f if l.strip())
            createj(HERE/(g['request_id']+'.claim.json'),dict(pid=os.getpid(),go_sha256=sha(go_path),claimed_utc=utc()))
            f.write(json.dumps(dict(request_id=g['request_id'],go_sha256=sha(go_path),claimed_utc=utc(),status='CLAIMED'))+'\n')
            f.flush(); os.fsync(f.fileno())
        out = ROOT/g['output']; assert out.parent == HERE
        out.mkdir(exist_ok=False)
        signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('1800s budget')))
        signal.alarm(1800)
        tr = jsonlines(CACHE/'train_targets.jsonl'); dr = jsonlines(CACHE/'development_targets.jsonl')
        tm = jsonlines(CACHE/'train_rows.jsonl'); dm = jsonlines(CACHE/'development_rows.jsonl')
        assert len(tr) == len(tm) == 6870 and len(dr) == len(dm) == 3765
        assert all(key(a)==key(b) for a,b in zip(tr,tm))
        assert all(key(a)==key(b) for a,b in zip(dr,dm))
        assert len({key(r) for r in tr}) == len(tr) and len({key(r) for r in dr}) == len(dr)
        tc = {r['cell_id'] for r in tr}; dc = {r['cell_id'] for r in dr}
        assert tc.isdisjoint(dc)
        assert all(r['role']=='train' and r['cell_id'].endswith(('C1','C2')) for r in tm)
        assert all(r['role']=='development' and r['cell_id'].endswith('C3') for r in dm)
        train = np.load(CACHE/'train_features.npz',allow_pickle=False)['F3']
        dev = np.load(CACHE/'development_features.npz',allow_pickle=False)['F3']
        assert train.shape == (6870,710) and dev.shape == (3765,710)
        assert not np.isinf(train).any() and not np.isinf(dev).any()
        ix = np.array([i for i,r in enumerate(tr) if r['target_rul_weeks'] is not None])
        X = train[ix]; y = np.array([tr[i]['target_rul_weeks'] for i in ix],float)
        cells = np.array([tr[i]['cell_id'] for i in ix]); assert np.isfinite(y).all() and (y>=0).all()
        ids = sorted(set(cells)); np.random.RandomState(42).shuffle(ids)
        folds = [set(ids[::2]),set(ids[1::2])]
        rec.update(status='RUNNING',train_query_cells=len(tc),development_query_cells=len(dc),
                   excluded_no_event_train_rows=len(tr)-len(ix),
                   missing_event_dev_rows=sum(r['target_rul_weeks'] is None for r in dr),
                   train_role_only=True,cell_overlap=0,OOF_fold_cells=[sorted(s) for s in folds])
        fitted = {}
        for loss in ['squared_error','absolute_error']:
            residual = np.empty(len(y)); assigned = np.zeros(len(y),bool)
            for fold_i, held in list(enumerate(folds))+[(2,set())]:
                fit = np.array([c not in held for c in cells]); val = ~fit
                assert not set(cells[fit]) & set(cells[val])
                model = HistGradientBoostingRegressor(loss=loss,max_iter=150,max_leaf_nodes=15,
                          l2_regularization=1.,random_state=42,early_stopping=False)
                rec['fits_started'] += 1; assert rec['fits_started'] <= 6
                rec['current_fit'] = loss+'_fold'+str(fold_i); saveprogress(out,rec)
                print('FIT_START',rec['current_fit'],int(fit.sum()),flush=True)
                model.fit(X[fit],y[fit],sample_weight=weights(cells[fit]))
                rec['fits_completed'] += 1
                joblib.dump(model,out/(loss+'_fold'+str(fold_i)+'.joblib'))
                if fold_i < 2:
                    residual[val] = y[val]-model.predict(X[val]); assigned[val]=True
                else:
                    assert assigned.all()
                    fitted[loss] = (model,residual,weights(cells))
                    np.savez_compressed(out/(loss+'_oof_residuals.npz'),residual=residual,cells=cells,weights=weights(cells))
                saveprogress(out,rec); print('FIT_DONE',rec['current_fit'],flush=True)
        assert rec['fits_completed']==6
        rec['all_fits_before_development_scoring']=True
        baseline = {}
        for r in csv.DictReader((CACHE/'predictions.csv').open()):
            if r['model'] != 'hgb_F3': continue
            k=key(r); assert k not in baseline
            for name in ['mean_weeks','median_weeks']: r[name]=float(r[name])
            baseline[k]=r
        assert set(baseline)=={key(r) for r in dr}
        for r in dr:
            b=baseline[key(r)]; yb=None if b['target_rul_weeks']=='' else float(b['target_rul_weeks'])
            assert yb==r['target_rul_weeks'], 'Target mismatch'
        predictions=[]
        for loss,(model,residual,w) in fitted.items():
            point=model.predict(dev)
            for i,r in enumerate(dr):
                # Additive OOF empirical error; mapping to nonnegative RUL preserves all tail mass at zero.
                dist = PointZero() if r['known_event'] else EmpiricalRUL(np.maximum(0.,point[i]+residual),w)
                e=dict(r,last_arrival_epoch=max(dm[i]['visible_rpt_arrival_epochs']),
                       delta_weeks=(r['query_epoch']-max(dm[i]['visible_rpt_arrival_epochs']))/604800.,
                       history_key=dm[i]['history_key'])
                z=metric_row(e,dist,42,'direct_'+loss,0.)
                z['point_raw_unconstrained_weeks']=float(point[i])
                z['point_weeks']=0. if r['known_event'] else float(max(0.,point[i]))
                predictions.append(z)
        rec['predictions']=len(predictions)
        write_csv(out/'predictions.csv',predictions)
        sums,cm,rel=summarize(predictions)
        write_csv(out/'distribution_summary.csv',sums); write_csv(out/'distribution_per_cell.csv',cm)
        summary=point_report(predictions,baseline,out)
        rec.update(status='SUCCESS',completed_utc=utc(),wall_seconds=time.time()-start,
                   primary=[s for s in summary if s['arm']=='raw' and s['stratum']=='unconfirmed'],
                   evidence_scope='Adaptive-development baseline study; no novelty or independent-confirmation claim')
        createj(out/'receipt.json',rec); saveprogress(out,rec)
        print('SUCCESS',json.dumps(rec['primary']),flush=True)
    except BaseException as e:
        rec.update(status='FAILED_STOP',error=repr(e),traceback=traceback.format_exc(),completed_utc=utc())
        if out is not None and out.exists():
            createj(out/'failure_receipt.json',rec); saveprogress(out,rec)
        else:
            createj(HERE/(g['request_id']+'_PREFLIGHT_FAILURE.json'),rec)
        raise
    finally:
        for f in reversed(locks): f.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--go',required=True)
    main(pathlib.Path(parser.parse_args().go))
