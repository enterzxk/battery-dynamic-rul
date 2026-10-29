#!/usr/bin/env python3
"""P4 -- direct-RUL-supervised test of whether the *full causal history* adds
information over the current F3 snapshot (710-d), under identical structure.

This file is the ONLY deliverable of the P4 implementation step.  It never
trains on real data unless a fresh exact-hash training GO is supplied with
--go.  Default action (no arguments) is --self-check on synthetic data with
zero payload reads.

Protocol (locked, see P4_HISTORY_PLAN_ZH.md)
-------------------------------------------
Observations  : cached, audited query snapshots.  For every (cell, arm) the
                prefix of snapshots with query_epoch <= query_epoch, strictly
                increasing in time, same cell and same arm.  Left padding plus
                an explicit missing-value mask; padding is never read by the
                recurrent core (packed sequence over the real steps only).
Forbidden     : true RUL, event age, number of future queries, final sequence
                length, any C4 / raw payload.
Models        : GRU_current   -- single token (current F3 only)
                GRU_history   -- same class/params/seed, causal F3 sequence
                HGB_history_summary -- current F3 + *pre-registered* fixed
                                 history summary, 150 iters / 15 leaves / L2=1,
                                 2 cell-isolated OOF folds + full fit (3 fits)
GRU structure : value+mask standardisation -> Linear(2*710 -> 32) -> GRU(32 ->
                64, 1 layer) -> Linear(64 -> 2) = (log mean, log sigma raw);
                sigma = softplus(raw) + 1e-3  (log-normal predictive law)
Training      : target_rul_weeks > 0 rows of C1/C2 only; cell-balanced
                weights; Adam 1e-3; batch 32; seed 42; no hyper-parameter
                search.  Internal selection = the audit's validation_cells
                (24 held training cells), metric = held-cell cell-macro
                positive log-RUL NLL, never C3.  After the step count is
                chosen, the model is refit from the same initial seed on all
                training cells; preprocessing is fitted on the fitting cells
                only (fit cells during selection, all training cells for the
                refit).
Event mass    : the existing F3 same-key hurdle probability is reused
                (unclosed_p_event) so that the positive-lifetime model is the
                only thing that changes.
Evaluation    : all 3,765 C3 development keys, raw/unconfirmed cell-macro
                median-RUL MAE primary, plus all/mean/median, RMSE, severe
                over-estimation, IS80, coverage, Brier(4/12), early/near/hidden
                buckets, per-cell harm, and same-key paired cell bootstrap
                (5,000 draws) against F3 mean, F3 median, P1 direct squared
                regression and P3 linear calibration.

GO contract (--print-go-contract prints the machine-readable form)
------------------------------------------------------------------
status                == "APPROVED"
allow_fit             is True
owner_thread_id       == 01a17810-6ae6-7cf2-9729-5bfcaa8df5f4
data_scope            == "C1_C2_train_C3_dev_no_C4"
C4_allowed            is False (when present)
code_sha256           dict with (at least) the keys in GO_REQUIRED_HASH_KEYS,
                      every digest matching the file on disk
budget.grus           max_selection_steps_per_model <= 400
                      max_refit_steps_per_model     <= 400
                      max_neural_fits               <= 4
budget.hgb            max_fits <= 3 (max_iterations 150, max_leaf_nodes 15)
budget.max_runtime_seconds <= 1800
output                fresh directory under the P4 experiment directory
receipt               fresh .json path inside that output directory

Any deviation -> exit code 3, zero writes, the GO is not consumed.
Exit codes    : 0 success / 3 GO (or claim) rejection / 4 data-contract or
                implementation failure after a valid GO was claimed.
"""

import os
os.environ.setdefault('OMP_NUM_THREADS', '4')
os.environ.setdefault('MKL_NUM_THREADS', '4')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '4')

import argparse
import collections
import csv
import datetime
import fcntl
import hashlib
import json
import math
import pathlib
import signal
import statistics
import sys
import time
import traceback

import numpy as np

# --------------------------------------------------------------------------- #
# Frozen constants
# --------------------------------------------------------------------------- #
ROOT = pathlib.Path(os.environ.get('RUL_ROOT', '/home/yndx/zxk/rul'))
HERE = ROOT / 'experiments/rul_time_recovery_20261026'
CACHE = ROOT / 'experiments/multisource_factorial_20261021/run2_clocksafe'
AUDIT = HERE / 'p4_input_audit_run1'

OWNER_THREAD_ID = '01a17810-6ae6-7cf2-9729-5bfcaa8df5f4'
DATA_SCOPE = 'C1_C2_train_C3_dev_no_C4'

SEED = 42
N_FEAT = 710
PROJ = 32
HIDDEN = 64
SIGMA_FLOOR = 1e-3
BATCH = 32
LR = 1e-3
SEL_STEPS_CAP = 400
REFIT_STEPS_CAP = 400
NEURAL_FITS_CAP = 4
EVAL_EVERY = 20
TRAIN_BOOT = 5000
RUNTIME_CAP = 1800

HGB_MAX_ITER = 150
HGB_LEAVES = 15
HGB_L2 = 1.0
HGB_FITS_CAP = 3

# Fixed *before* any training: the scalar columns on which the history summary
# reports shape statistics.  These are the same eight context columns the P3
# calibration already used, so the summary is not fitted to C3 in any way.
SUMMARY_BASIS_COLS = (0, 1, 3, 4, 6, 8, 686, 687)
SUMMARY_K = 3
N_SUMMARY = N_FEAT + 7 * len(SUMMARY_BASIS_COLS) + 3   # 710 + 56 + 3 = 769

ARMS = ('raw', 'sparse2', 'delay7d')
STRATA = ('all', 'unconfirmed', 'known_event', 'hidden_event',
          'early_gt12w', 'near_le4w')

EDGES = np.asarray([0, .25, .5, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96,
                    128], float)

GO_REQUIRED_HASH_KEYS = (
    'experiments/rul_time_recovery_20261026/p4_history.py',
    'experiments/rul_time_recovery_20261026/P4_HISTORY_PLAN_ZH.md',
    'experiments/rul_time_recovery_20261026/p4_input_audit_run1/INPUT_AUDIT.json',
    'experiments/rul_time_recovery_20261026/p4_input_audit_run1/internal_training_split.json',
    'experiments/rul_time_recovery_20261026/p4_input_audit_run1/train_prefix_index.npz',
    'experiments/rul_time_recovery_20261026/p4_input_audit_run1/development_prefix_index.npz',
    'experiments/multisource_factorial_20261021/run2_clocksafe/train_features.npz',
    'experiments/multisource_factorial_20261021/run2_clocksafe/train_rows.jsonl',
    'experiments/multisource_factorial_20261021/run2_clocksafe/train_targets.jsonl',
    'experiments/multisource_factorial_20261021/run2_clocksafe/feature_schema.json',
)

# Files consumed by the evaluation stage.  They must be pinned too when the GO
# carries them; the gate rejects a mismatch and the evaluator cross-checks every
# key/target anyway.
GO_OPTIONAL_HASH_KEYS = (
    'experiments/multisource_factorial_20261021/run2_clocksafe/development_features.npz',
    'experiments/multisource_factorial_20261021/run2_clocksafe/development_rows.jsonl',
    'experiments/multisource_factorial_20261021/run2_clocksafe/development_targets.jsonl',
    'experiments/rul_time_recovery_20261026/p1_run1/predictions.csv',
    'experiments/rul_time_recovery_20261026/p3_calibration_run1/predictions.csv',
    'experiments/rul_time_recovery_20261026/p3_peer_run1/predictions.csv',
    'experiments/multisource_factorial_20261021/run2_clocksafe/predictions.csv',
)

_PAYLOAD_READS = 0          # incremented by every real-data loader
GO_REJECT_CODES = []        # filled by the self-check
_SYNTHETIC = False          # True while --self-check runs


def payload_read():
    global _PAYLOAD_READS
    _PAYLOAD_READS += 1


# --------------------------------------------------------------------------- #
# Small utilities (create-only writers, hashing, time)
# --------------------------------------------------------------------------- #
def sha(p):
    h = hashlib.sha256()
    with pathlib.Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def readj(p):
    return json.loads(pathlib.Path(p).read_text())


def jsonlines(p):
    with pathlib.Path(p).open() as f:
        return [json.loads(line) for line in f if line.strip()]


def createj(p, obj):
    with pathlib.Path(p).open('x') as f:
        json.dump(obj, f, indent=2, allow_nan=False)


def write_csv(p, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with pathlib.Path(p).open('x', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def key(r):
    return str(r['cell_id']), str(r['arm']), float(r['query_epoch'])


def weights_cell_equal(cells):
    counts = collections.Counter(cells)
    return np.asarray([1.0 / counts[c] for c in cells], float)


def finite(x):
    return isinstance(x, (int, float)) and math.isfinite(float(x))


# --------------------------------------------------------------------------- #
# Predictive laws
# --------------------------------------------------------------------------- #
class PointZero:
    """Degenerate law at RUL=0 (known event time reached)."""

    def cdf(self, t):
        a = np.asarray(t, float)
        z = (a >= 0).astype(float)
        return float(z) if z.ndim == 0 else z

    def mean(self):
        return 0.0

    def quantile(self, p):
        return 0.0


class EmpiricalRUL:
    """Weighted empirical law on non-negative RUL; identical semantics to the
    project's dart_rul_v18.hgb_models.EmpiricalRUL."""

    def __init__(self, values, w=None):
        values = np.asarray(values, float)
        if values.ndim != 1 or len(values) == 0:
            raise ValueError('bad empirical support')
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError('non-finite or negative empirical support')
        order = np.argsort(values, kind='mergesort')
        self.values = values[order]
        ww = np.ones(len(values)) if w is None else np.asarray(w, float)[order]
        if ww.shape != values.shape or not np.isfinite(ww).all() or ww.sum() <= 0:
            raise ValueError('bad empirical weights')
        self.weights = ww / ww.sum()
        self.cumulative = np.cumsum(self.weights)
        self.cumulative[-1] = 1.0

    def cdf(self, x):
        a = np.asarray(x, float)
        idx = np.searchsorted(self.values, a, side='right') - 1
        idx = np.clip(idx, 0, len(self.values) - 1)
        out = np.where(a < self.values[0], 0.0, self.cumulative[idx])
        out = np.where(a < 0.0, 0.0, out)
        return float(out) if np.ndim(out) == 0 else out

    def mean(self):
        return float(np.dot(self.values, self.weights))

    def quantile(self, p):
        p = float(p)
        if not 0.0 <= p <= 1.0:
            raise ValueError('quantile outside [0,1]')
        i = min(len(self.values) - 1,
                int(np.searchsorted(self.cumulative, p, side='left')))
        return float(self.values[i])


class LogNormalRUL:
    """Log-normal law on positive RUL in weeks: log RUL ~ N(mu, sigma)."""

    _ND = statistics.NormalDist()

    def __init__(self, mu, sigma):
        self.mu = float(mu)
        self.sigma = float(sigma)
        if not finite(self.mu) or not finite(self.sigma) or self.sigma <= 0:
            raise ValueError('bad log-normal parameters')

    @staticmethod
    def _phi(z):
        return np.asarray([0.5 * (1.0 + math.erf(v / math.sqrt(2.0)))
                           for v in np.asarray(z, float).ravel()]).reshape(
                               np.asarray(z, float).shape)

    def cdf(self, x):
        a = np.asarray(x, float)
        flat = a.ravel()
        out = np.zeros(flat.shape)
        pos = flat > 0
        if pos.any():
            out[pos] = LogNormalRUL._phi((np.log(flat[pos]) - self.mu) / self.sigma)
        return float(out[0]) if a.ndim == 0 else out.reshape(a.shape)

    def mean(self):
        return float(math.exp(self.mu + 0.5 * self.sigma ** 2))

    def quantile(self, p):
        p = float(p)
        if not 0.0 <= p <= 1.0:
            raise ValueError('quantile outside [0,1]')
        return float(math.exp(self.mu + self.sigma * self._ND.inv_cdf(p)))


class HurdleMix:
    """p0 at zero plus a positive component, matching HurdleRUL semantics."""

    def __init__(self, zero_mass, positive):
        self.p0 = float(zero_mass)
        if not 0.0 <= self.p0 <= 1.0:
            raise ValueError('bad zero atom')
        self.positive = positive

    def cdf(self, x):
        a = np.asarray(x, float)
        out = self.p0 + (1.0 - self.p0) * self.positive.cdf(a)
        out = np.where(a < 0.0, 0.0, out)
        return float(out) if a.ndim == 0 else out

    def mean(self):
        return float((1.0 - self.p0) * self.positive.mean())

    def quantile(self, p):
        p = float(p)
        if p <= self.p0 or self.p0 >= 1.0:
            return 0.0
        return self.positive.quantile((p - self.p0) / (1.0 - self.p0))


# --------------------------------------------------------------------------- #
# Per-row metrics (same definitions/columns as dart_rul_v18.evaluate.metric_row)
# --------------------------------------------------------------------------- #
def metric_row(e, dist, model, wall_ms=0.0):
    vals = np.asarray(dist.cdf(EDGES), float)
    p = float(vals[0])
    mu = float(dist.mean())
    med = float(dist.quantile(.5))
    lo = float(dist.quantile(.1))
    hi = float(dist.quantile(.9))
    if not np.all(np.isfinite(vals)) or not all(math.isfinite(v) for v in (mu, med, lo, hi)):
        raise FloatingPointError('non-finite distribution')
    if vals.min() < -1e-10 or vals.max() > 1 + 1e-10 or np.any(np.diff(vals) < -1e-10):
        raise ValueError('invalid CDF')
    if lo < 0 or hi < lo or mu < 0:
        raise ValueError('invalid quantiles/mean')
    y = int(e['y_event'])
    target = e['target_rul_weeks']
    known = target is not None
    probs = np.r_[p, np.diff(vals), 1 - vals[-1]]
    if abs(probs.sum() - 1) > 1e-9:
        raise ValueError('mass normalisation failure')
    logscore = ''
    if known:
        if target == 0:
            mass = p
        elif target <= EDGES[-1]:
            mass = probs[1 + min(len(EDGES) - 1,
                                 int(np.searchsorted(EDGES, target, side='left')) - 1)]
        else:
            mass = probs[-1]
        logscore = -math.log(mass) if mass > 0 else float('inf')
    f4 = float(dist.cdf(4.))
    f12 = float(dist.cdf(12.))
    return {
        'seed': SEED, 'model': model, 'cell_id': e['cell_id'], 'arm': e['arm'],
        'query_epoch': e['query_epoch'],
        'arrival_anchor_epoch': e['last_arrival_epoch'],
        'delta_weeks': e['delta_weeks'], 'history_key': e['history_key'],
        'known_event': bool(e['known_event']), 'y_event': y,
        'target_rul_weeks': '' if target is None else target,
        'p_event': p, 'F4': f4, 'F12': f12,
        'Splus4': '' if p >= 1 else (1 - f4) / (1 - p),
        'Splus12': '' if p >= 1 else (1 - f12) / (1 - p),
        'mean_weeks': mu, 'median_weeks': med, 'q10': lo, 'q90': hi,
        'event_brier': (p - y) ** 2,
        'event_logloss': ((-math.log(p) if p > 0 else float('inf')) if y
                          else (-math.log1p(-p) if p < 1 else float('inf'))),
        'mean_abs_error': abs(mu - target) if known else '',
        'median_abs_error': abs(med - target) if known else '',
        'severe_gt4w': float(mu - target > 4) if known else '',
        'IS80': hi - lo + 10 * (max(lo - target, 0) + max(target - hi, 0)) if known else '',
        'coverage80': float(lo <= target <= hi) if known else '',
        'Brier4': (f4 - float(target <= 4)) ** 2 if known else '',
        'Brier12': (f12 - float(target <= 12)) ** 2 if known else '',
        'bin_logscore': logscore, 'predict_wall_ms': wall_ms,
    }


def stratum_selected(r, stratum):
    t = r['target_rul_weeks']
    if t in ('', None):
        return False
    if stratum == 'all':
        return True
    if stratum == 'unconfirmed':
        return not r['known_event']
    if stratum == 'known_event':
        return bool(r['known_event'])
    if stratum == 'hidden_event':
        return r['y_event'] == 1 and not r['known_event']
    if stratum == 'early_gt12w':
        return t > 12
    if stratum == 'near_le4w':
        return 0 < t <= 4
    raise ValueError('unknown stratum ' + stratum)


METRIC_COLS = ('event_brier', 'event_logloss', 'mean_abs_error',
               'median_abs_error', 'severe_gt4w', 'IS80', 'coverage80',
               'Brier4', 'Brier12', 'bin_logscore')


def summarize(rows):
    """Cell-macro distribution summary; mirrors dart_rul_v18.evaluate.summarize."""
    groups = collections.defaultdict(list)
    for r in rows:
        groups[(r['seed'], r['model'], r['arm'])].append(r)
    summary, cells, reliability = [], [], []
    for k, rs in sorted(groups.items()):
        for stratum, select in [
                ('all', lambda r: True),
                ('unconfirmed', lambda r: not r['known_event']),
                ('known_event', lambda r: bool(r['known_event'])),
                ('hidden_event', lambda r: r['y_event'] == 1 and not r['known_event'])]:
            ss = [r for r in rs if select(r)]
            by = collections.defaultdict(list)
            for r in ss:
                by[r['cell_id']].append(r)
            entries = []
            for cid, cr in sorted(by.items()):
                ce = {'seed': k[0], 'model': k[1], 'arm': k[2], 'stratum': stratum,
                      'cell_id': cid, 'n_queries': len(cr)}
                for m in METRIC_COLS:
                    v = [float(r[m]) for r in cr if r[m] != '']
                    ce[m] = statistics.mean(v) if v else ''
                cells.append(ce)
                entries.append(ce)
            s = {'seed': k[0], 'model': k[1], 'arm': k[2], 'stratum': stratum,
                 'n_rows': len(ss), 'n_cells': len(by)}
            for m in METRIC_COLS:
                v = [float(x[m]) for x in entries if x[m] != '']
                s[m] = statistics.mean(v) if v else ''
                s[m + '_infinite_cells'] = sum(not math.isfinite(x) for x in v)
            bins = [[] for _ in range(10)]
            for cid, cr in by.items():
                for r in cr:
                    bins[min(9, int(r['p_event'] * 10))].append(
                        (r['p_event'], r['y_event'], 1.0 / len(cr)))
            ece, tot = 0.0, float(len(by))
            for i, b in enumerate(bins):
                w = sum(x[2] for x in b)
                pred = sum(x[0] * x[2] for x in b) / w if w else ''
                obs = sum(x[1] * x[2] for x in b) / w if w else ''
                reliability.append({'seed': k[0], 'model': k[1], 'arm': k[2],
                                    'stratum': stratum, 'bin': i,
                                    'row_count': len(b), 'cell_weight': w,
                                    'mean_predicted': pred,
                                    'observed_fraction': obs})
                if w:
                    ece += w / tot * abs(pred - obs)
            s['ECE10'] = ece if tot else ''
            summary.append(s)
    return summary, cells, reliability


def point_table(rows, arms=ARMS, strata=STRATA):
    """Cell-macro point metrics (median-RUL MAE is the primary one)."""
    out = []
    groups = collections.defaultdict(list)
    for r in rows:
        groups[(r['model'], r['arm'])].append(r)
    for (model, arm), rs in sorted(groups.items()):
        for stratum in strata:
            ss = [r for r in rs if stratum_selected(r, stratum)]
            if not ss:
                continue
            by = collections.defaultdict(list)
            for r in ss:
                by[r['cell_id']].append(r)
            med_mae, mean_mae, rmse, severe, is80, cov, b4, b12 = ([] for _ in range(8))
            for cid, cr in by.items():
                y = np.asarray([float(r['target_rul_weeks']) for r in cr])
                md = np.asarray([float(r['median_weeks']) for r in cr])
                mn = np.asarray([float(r['mean_weeks']) for r in cr])
                med_mae.append(float(np.mean(np.abs(md - y))))
                mean_mae.append(float(np.mean(np.abs(mn - y))))
                rmse.append(float(np.sqrt(np.mean((md - y) ** 2))))
                severe.append(float(np.mean([float(r['severe_gt4w']) for r in cr])))
                is80.append(float(np.mean([float(r['IS80']) for r in cr])))
                cov.append(float(np.mean([float(r['coverage80']) for r in cr])))
                b4.append(float(np.mean([float(r['Brier4']) for r in cr])))
                b12.append(float(np.mean([float(r['Brier12']) for r in cr])))
            out.append({
                'model': model, 'arm': arm, 'stratum': stratum,
                'n_cells': len(by), 'n_queries': len(ss),
                'median_rul_mae_weeks': float(np.mean(med_mae)),
                'mean_rul_mae_weeks': float(np.mean(mean_mae)),
                'rmse_weeks': float(np.mean(rmse)),
                'severe_overestimate_gt4w': float(np.mean(severe)),
                'IS80_weeks': float(np.mean(is80)),
                'coverage80': float(np.mean(cov)),
                'Brier4': float(np.mean(b4)), 'Brier12': float(np.mean(b12))})
    return out


def paired_bootstrap(rows_a, rows_b, arm, stratum, B=TRAIN_BOOT, seed=SEED):
    """Same-key paired physical-cell bootstrap of cell-macro median-RUL MAE."""
    a = {key(r): r for r in rows_a if r['arm'] == arm and stratum_selected(r, stratum)}
    b = {key(r): r for r in rows_b if r['arm'] == arm and stratum_selected(r, stratum)}
    if set(a) != set(b):
        raise AssertionError('paired bootstrap key mismatch')
    if not a:
        raise AssertionError('empty paired population')
    cells = sorted({k[0] for k in a})
    delta = np.empty(len(cells))
    for i, cid in enumerate(cells):
        ks = [k for k in a if k[0] == cid]
        ya = np.asarray([float(a[k]['target_rul_weeks']) for k in ks])
        ma = np.asarray([float(a[k]['median_weeks']) for k in ks])
        mb = np.asarray([float(b[k]['median_weeks']) for k in ks])
        delta[i] = (float(np.mean(np.abs(ma - ya))) -
                    float(np.mean(np.abs(mb - ya))))
    rng = np.random.default_rng(seed)
    boot = delta[rng.integers(0, len(cells), (B, len(cells)))].mean(1)
    lo, hi = np.quantile(boot, [.025, .975])
    return {'n_cells': len(cells), 'n_queries': len(a),
            'delta_mae_weeks': float(delta.mean()),
            'ci_low': float(lo), 'ci_high': float(hi),
            'boot_mean': float(boot.mean()),
            'p_delta_ge_0': float(np.mean(boot >= 0)),
            'improved_cell_fraction': float(np.mean(delta < 0)),
            'worst_cell_delta': float(delta.max()),
            'best_cell_delta': float(delta.min()), 'draws': int(B)}


# --------------------------------------------------------------------------- #
# Data loading (real payload; guarded by _PAYLOAD_READS)
# --------------------------------------------------------------------------- #
def load_split(split, expect_rows, expect_cells):
    payload_read()
    rows = jsonlines(CACHE / (split + '_rows.jsonl'))
    tgts = jsonlines(CACHE / (split + '_targets.jsonl'))
    X = np.load(CACHE / (split + '_features.npz'), allow_pickle=False)['F3']
    pfx = np.load(AUDIT / (split + '_prefix_index.npz'), allow_pickle=False)
    pointer = pfx['pointer'].astype(np.int64)
    index = pfx['index'].astype(np.int64)
    length = pfx['length'].astype(np.int64)
    if not (len(rows) == len(tgts) == len(X) == len(length) == len(pointer) - 1):
        raise AssertionError('row/feature/prefix length mismatch for ' + split)
    if X.shape[1] != N_FEAT:
        raise AssertionError('F3 must be %d-wide' % N_FEAT)
    if np.isinf(X).any():
        raise AssertionError('inf in F3')
    ks = [key(r) for r in rows]
    if len(set(ks)) != len(ks):
        raise AssertionError('duplicate (cell,arm,query) in ' + split)
    for r, t in zip(rows, tgts):
        if key(r) != key(t):
            raise AssertionError('row/target key mismatch in ' + split)
    if len(rows) != expect_rows or len({r['cell_id'] for r in rows}) != expect_cells:
        raise AssertionError('unexpected %s population: %d rows / %d cells'
                            % (split, len(rows), len({r['cell_id'] for r in rows})))
    if not all(r['role'] == split for r in rows):
        raise AssertionError('role mismatch')
    suf = ('C1', 'C2') if split == 'train' else ('C3',)
    if not all(str(r['cell_id']).endswith(suf) for r in rows):
        raise AssertionError('cohort suffix check failed for ' + split)
    ep = np.asarray([float(r['query_epoch']) for r in rows])
    for r in rows:
        arr = r['visible_rpt_arrival_epochs']
        if len(arr) < 3 or max(arr) > float(r['query_epoch']) + 1e-6:
            raise AssertionError('arrival visibility violated')
    cells = np.asarray([r['cell_id'] for r in rows])
    arms = np.asarray([r['arm'] for r in rows])
    # prefix contract: same cell/arm, strictly increasing, never beyond query
    verify_prefix(ep, cells, arms, pointer, index, length)
    return dict(rows=rows, targets=tgts, X=X.astype(np.float64), ep=ep,
                cells=cells, arms=arms, pointer=pointer, index=index,
                length=length)


def positive_ids(tgts):
    return np.asarray([i for i, t in enumerate(tgts)
                       if t['target_rul_weeks'] is not None
                       and t['target_rul_weeks'] > 0], np.int64)


def load_internal_split():
    payload_read()
    s = readj(AUDIT / 'internal_training_split.json')
    for f in ('seed', 'fit_cells', 'validation_cells', 'positive_train_indices',
              'fit_query_indices', 'validation_query_indices'):
        if f not in s:
            raise AssertionError('internal split missing ' + f)
    if s['seed'] != SEED:
        raise AssertionError('internal split seed must be 42')
    return s


def load_internal_audit():
    payload_read()
    a = readj(AUDIT / 'INPUT_AUDIT.json')
    if a.get('status') != 'PASS':
        raise AssertionError('input audit is not PASS')
    if a.get('C4_reads') != 0 or a.get('new_fits') != 0:
        raise AssertionError('input audit consumed budget or C4')
    if a['splits']['train']['rows'] != 6870 or a['splits']['development']['rows'] != 3765:
        raise AssertionError('input audit population mismatch')
    if a.get('cell_overlap') != 0:
        raise AssertionError('cell overlap in audit')
    return a


# --------------------------------------------------------------------------- #
# GO gate: read-only, zero writes, exit 3 on any deviation
# --------------------------------------------------------------------------- #
class GoRejected(Exception):
    def __init__(self, code, detail):
        super().__init__('%s: %s' % (code, detail))
        self.code = code
        self.detail = detail


def _need(cond, code, detail):
    if not cond:
        raise GoRejected(code, detail)


def _hex64(s):
    return (isinstance(s, str) and len(s) == 64
            and all(c in '0123456789abcdef' for c in s))


def _int_at(d, path):
    cur = d
    for part in path.split('.'):
        _need(isinstance(cur, dict) and part in cur, 'budget',
              'budget missing ' + path)
        cur = cur[part]
    _need(isinstance(cur, int) and not isinstance(cur, bool) and cur >= 0,
          'budget', 'budget %s must be a non-negative int' % path)
    return cur


def go_contract():
    return {
        'required_fields': {
            'request_id': 'non-empty string, unique in experiments/state/consumed_gos.jsonl',
            'status': 'APPROVED',
            'allow_fit': True,
            'owner_thread_id': OWNER_THREAD_ID,
            'data_scope': DATA_SCOPE,
            'C4_allowed': False,
            'code_sha256': 'dict path -> sha256; must contain >= the keys in required_hash_keys',
            'budget.grus.max_selection_steps_per_model': '<= %d' % SEL_STEPS_CAP,
            'budget.grus.max_refit_steps_per_model': '<= %d' % REFIT_STEPS_CAP,
            'budget.grus.max_neural_fits': '<= %d' % NEURAL_FITS_CAP,
            'budget.hgb.max_fits': '<= %d' % HGB_FITS_CAP,
            'budget.hgb.max_iterations': HGB_MAX_ITER,
            'budget.hgb.max_leaf_nodes': HGB_LEAVES,
            'budget.max_runtime_seconds': '<= %d' % RUNTIME_CAP,
            'output': 'fresh directory under %s' % HERE.relative_to(ROOT),
            'receipt': 'fresh .json path inside that output directory',
        },
        'required_hash_keys': list(GO_REQUIRED_HASH_KEYS),
        'optional_hash_keys_verified_when_present': list(GO_OPTIONAL_HASH_KEYS),
        'protocol_constants': {
            'seed': SEED, 'gru_input_features': N_FEAT, 'gru_projection': PROJ,
            'gru_hidden': HIDDEN, 'gru_layers': 1, 'batch': BATCH,
            'adam_lr': LR, 'eval_every': EVAL_EVERY,
            'selection_cells': 24, 'cell_macro_metric':
            'held-cell positive-log-RUL NLL',
            'hgb_max_iter': HGB_MAX_ITER, 'hgb_leaves': HGB_LEAVES,
            'hgb_l2': HGB_L2, 'hgb_fits': HGB_FITS_CAP,
            'bootstrap_draws': TRAIN_BOOT,
        },
        'rejection': 'any deviation -> exit code 3, zero writes, GO not consumed',
    }


def gate_go(g, *, sha_of, output_exists, receipt_exists):
    """Validate a training GO.  Pure function of its arguments: never writes."""
    _need(isinstance(g, dict), 'go_shape', 'GO must be a JSON object')
    rid = g.get('request_id')
    _need(isinstance(rid, str) and 8 <= len(rid) <= 120
          and all(c.isalnum() or c in '_-' for c in rid),
          'request_id', 'missing or malformed request_id')
    _need(g.get('status') == 'APPROVED', 'status',
          'status must be APPROVED, got %r' % (g.get('status'),))
    _need(g.get('allow_fit') is True, 'allow_fit', 'allow_fit must be true')
    _need(g.get('owner_thread_id') == OWNER_THREAD_ID, 'owner_thread_id',
          'owner_thread_id mismatch')
    _need(g.get('data_scope') == DATA_SCOPE, 'data_scope',
          'data_scope must be %r, got %r' % (DATA_SCOPE, g.get('data_scope')))
    if 'C4_allowed' in g:
        _need(g['C4_allowed'] is False, 'c4', 'C4_allowed must be false')

    pins = g.get('code_sha256')
    _need(isinstance(pins, dict) and pins, 'code_sha256', 'code_sha256 must be a dict')
    for rel in GO_REQUIRED_HASH_KEYS:
        _need(rel in pins, 'code_sha256_missing', 'code_sha256 lacks ' + rel)
    for rel, digest in pins.items():
        _need(isinstance(rel, str) and not os.path.isabs(rel) and '..' not in rel,
              'code_sha256_path', 'unsafe path in code_sha256: %r' % (rel,))
        _need(_hex64(digest), 'code_sha256_format',
              'code_sha256[%s] is not a sha256 hex digest' % rel)
        _need(sha_of(rel) == digest, 'code_sha256_mismatch',
              'sha256 mismatch for ' + rel)

    steps_sel = _int_at(g, 'budget.grus.max_selection_steps_per_model')
    steps_ref = _int_at(g, 'budget.grus.max_refit_steps_per_model')
    n_fits = _int_at(g, 'budget.grus.max_neural_fits')
    _need(steps_sel <= SEL_STEPS_CAP, 'budget_selection_steps',
          'selection-step budget %d exceeds protocol cap %d' % (steps_sel, SEL_STEPS_CAP))
    _need(steps_ref <= REFIT_STEPS_CAP, 'budget_refit_steps',
          'refit-step budget %d exceeds protocol cap %d' % (steps_ref, REFIT_STEPS_CAP))
    _need(n_fits <= NEURAL_FITS_CAP, 'budget_neural_fits',
          'neural fit budget %d exceeds protocol cap %d' % (n_fits, NEURAL_FITS_CAP))
    hgb_fits = _int_at(g, 'budget.hgb.max_fits')
    _need(hgb_fits <= HGB_FITS_CAP, 'budget_hgb_fits',
          'hgb fit budget %d exceeds protocol cap %d' % (hgb_fits, HGB_FITS_CAP))
    if 'max_iterations' in g['budget']['hgb']:
        _need(_int_at(g, 'budget.hgb.max_iterations') <= HGB_MAX_ITER,
              'budget_hgb_iterations', 'hgb iterations exceed 150')
    if 'max_leaf_nodes' in g['budget']['hgb']:
        _need(_int_at(g, 'budget.hgb.max_leaf_nodes') <= HGB_LEAVES,
              'budget_hgb_leaves', 'hgb leaves exceed 15')
    runtime = _int_at(g, 'budget.max_runtime_seconds')
    _need(0 < runtime <= RUNTIME_CAP, 'budget_runtime',
          'max_runtime_seconds must be in (0, %d]' % RUNTIME_CAP)

    out_rel = g.get('output')
    _need(isinstance(out_rel, str) and out_rel and not os.path.isabs(out_rel),
          'output_path', 'output must be a relative path')
    out = ROOT / pathlib.Path(out_rel)
    _need(out.parent == HERE, 'output_parent',
          'output must live directly under ' + str(HERE.relative_to(ROOT)))
    _need(out.name.startswith('p4'), 'output_namespace',
          'output directory must start with "p4" to protect other stages')
    _need(not output_exists(out), 'output_not_fresh',
          'output directory already exists: ' + out_rel)

    rec_rel = g.get('receipt')
    _need(isinstance(rec_rel, str) and rec_rel.endswith('.json'),
          'receipt_path', 'receipt must be a .json path')
    rec = ROOT / pathlib.Path(rec_rel)
    _need(rec.parent == out, 'receipt_parent', 'receipt must sit inside output')
    _need(not receipt_exists(rec), 'receipt_not_fresh',
          'receipt already exists: ' + rec_rel)

    return {'request_id': rid, 'out': out, 'receipt': rec,
            'steps_sel_cap': steps_sel, 'steps_refit_cap': steps_ref,
            'neural_fits_cap': n_fits, 'hgb_fits_cap': hgb_fits,
            'runtime_cap': runtime, 'pins': dict(pins)}


# --------------------------------------------------------------------------- #
# Sequence batching (left padding + mask; padding never read)
# --------------------------------------------------------------------------- #
def token_stats(X, row_ids, pointer, index):
    """Per-feature mean/std over every observed prefix token of the given rows."""
    nf = X.shape[1]
    s = np.zeros(nf)
    ss = np.zeros(nf)
    n = np.zeros(nf)
    for r in row_ids:
        idx = index[int(pointer[r]):int(pointer[r + 1])]
        v = X[idx]
        ok = np.isfinite(v)
        vv = np.where(ok, v, 0.0)
        s += vv.sum(0)
        ss += (vv * vv).sum(0)
        n += ok.sum(0)
    mean = np.where(n > 0, s / np.maximum(n, 1), 0.0)
    var = np.where(n > 0, ss / np.maximum(n, 1) - mean ** 2, 1.0)
    std = np.sqrt(np.maximum(var, 1e-12))
    std = np.where(n > 0, np.maximum(std, 1e-6), 1.0)
    return mean.astype(np.float32), std.astype(np.float32)


def build_sequences(X, pointer, index, row_ids, mean, std, current_only):
    """Left-padded (n, T, 2*N_FEAT) float32: standardised value + observed mask.

    The real steps of a row occupy positions T-L..T-1 (left padding); the mask
    is exactly the finiteness mask of the F3 snapshot, so padded positions and
    missing values are both explicit zeros.
    """
    lens = np.asarray([int(pointer[r + 1] - pointer[r]) for r in row_ids], np.int64)
    T = 1 if current_only else int(lens.max())
    if current_only:
        lens = np.ones_like(lens)
    n = len(row_ids)
    nf = X.shape[1]
    val = np.zeros((n, T, nf), np.float32)
    msk = np.zeros((n, T, nf), np.float32)
    for j, r in enumerate(row_ids):
        if current_only:
            idx = np.asarray([r], np.int64)
        else:
            idx = index[int(pointer[r]):int(pointer[r + 1])]
        v = X[idx]
        ok = np.isfinite(v)
        z = (np.where(ok, v, 0.0).astype(np.float32) - mean) / std
        z = np.clip(z, -5.0, 5.0)
        L = len(idx)
        val[j, T - L:, :] = z
        msk[j, T - L:, :] = ok.astype(np.float32)
    return np.concatenate([val, msk], axis=2), lens


# --------------------------------------------------------------------------- #
# GRU model / training
# --------------------------------------------------------------------------- #
def _torch():
    import torch
    return torch


class GRURULFactory:
    """Same class, same parameter count and same seed for both variants."""

    @staticmethod
    def build(n_feat=N_FEAT, proj=PROJ, hidden=HIDDEN):
        torch = _torch()
        nn = torch.nn

        class GRURUL(nn.Module):
            def __init__(self):
                super().__init__()
                self.proj = nn.Linear(2 * n_feat, proj)
                self.gru = nn.GRU(proj, hidden, num_layers=1, batch_first=True)
                self.head = nn.Linear(hidden, 2)
                self.sigma_floor = SIGMA_FLOOR

            def forward(self, x, lens):
                # x: (B, T, 2F) left padded.  Move the real steps to the front
                # so pack_padded_sequence never sees a padded timestep.
                B, T = x.shape[0], x.shape[1]
                if T == 1:
                    seq = x
                else:
                    shift = (T - lens.to(x.device)).view(B, 1)
                    ar = torch.arange(T, device=x.device).view(1, T)
                    gather = ((ar + shift) % T).unsqueeze(-1).expand(-1, -1, x.shape[2])
                    seq = x.gather(1, gather)
                seq = self.proj(seq)
                packed = torch.nn.utils.rnn.pack_padded_sequence(
                    seq, lens.cpu(), batch_first=True, enforce_sorted=False)
                _, h = self.gru(packed)
                z = self.head(h[-1])
                mu = z[:, 0]
                sigma = torch.nn.functional.softplus(z[:, 1]) + self.sigma_floor
                return mu, sigma

        return GRURUL()


def nll_gaussian(y, mu, sigma):
    torch = _torch()
    return (0.5 * math.log(2.0 * math.pi) + torch.log(sigma)
            + 0.5 * ((y - mu) / sigma) ** 2)


def _init_rng(seed):
    torch = _torch()
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


class SeqDataset:
    def __init__(self, X, pointer, index, mean, std, current_only):
        self.X, self.pointer, self.index = X, pointer, index
        self.mean, self.std = mean, std
        self.current_only = current_only

    def tensor_for(self, row_ids):
        torch = _torch()
        arr, lens = build_sequences(self.X, self.pointer, self.index, row_ids,
                                    self.mean, self.std, self.current_only)
        return torch.from_numpy(arr), torch.from_numpy(lens)


def cell_macro_nll(model, ds, row_ids, y_log, cells):
    """Cell-macro Gaussian NLL of log RUL (validation / selection metric)."""
    torch = _torch()
    model.eval()
    out = np.empty(len(row_ids))
    with torch.no_grad():
        for a in range(0, len(row_ids), 128):
            sl = slice(a, min(a + 128, len(row_ids)))
            x, l = ds.tensor_for(row_ids[sl])
            dev = next(model.parameters()).device
            x, l = x.to(dev), l.to(dev)
            mu, sigma = model(x, l)
            out[sl] = nll_gaussian(torch.from_numpy(y_log[sl]).to(device=mu.device, dtype=mu.dtype), mu,
                                   sigma).cpu().numpy()
    model.train()
    per_cell = collections.defaultdict(list)
    for v, c in zip(out, cells):
        per_cell[c].append(float(v))
    return float(np.mean([np.mean(v) for v in per_cell.values()]))


def train_gru(variant, split, fit_ids, val_ids, all_ids, y_log, cells, device,
              sel_steps_cap, refit_steps_cap, on_fit=None, log=print):
    """Selection run on fit cells, then a refit from the same seed on all cells."""
    torch = _torch()
    current_only = (variant == 'current')
    rec = {'variant': variant, 'device': str(device), 'curve': [],
           'selected_steps': None, 'best_val_nll': None,
           'selection_fit_on': len(fit_ids), 'refit_fit_on': len(all_ids)}

    mean_f, std_f = token_stats(split['X'], fit_ids, split['pointer'], split['index'])
    ds_fit = SeqDataset(split['X'], split['pointer'], split['index'], mean_f, std_f,
                        current_only)
    _init_rng(SEED)
    model = GRURULFactory.build().to(device)
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    if on_fit:
        on_fit('neural_start', 'gru_%s_selection' % variant)
    rng = np.random.default_rng(SEED)
    w = weights_cell_equal(cells[fit_ids])
    w = w / w.mean()
    y_fit = y_log[fit_ids]
    model.train()
    best = (float('inf'), 0)
    for step in range(1, sel_steps_cap + 1):
        pick = rng.integers(0, len(fit_ids), BATCH)
        rows = fit_ids[pick]
        x, l = ds_fit.tensor_for(rows)
        x, l = x.to(device), l.to(device)
        mu, sigma = model(x, l)
        yt = torch.from_numpy(y_fit[pick]).to(device)
        wt = torch.from_numpy(w[pick]).to(device)
        loss = (nll_gaussian(yt, mu, sigma) * wt).mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
        if step % EVAL_EVERY == 0 or step == sel_steps_cap:
            nll = cell_macro_nll(model, ds_fit, val_ids, y_log[val_ids],
                                 cells[val_ids])
            rec['curve'].append({'step': step, 'val_cell_macro_nll': nll})
            log('SELECT %s step %d val_nll %.6f' % (variant, step, nll))
            if nll < best[0] - 1e-9:
                best = (nll, step)
    rec['best_val_nll'] = best[0]
    rec['selected_steps'] = int(best[1]) if best[1] > 0 else int(sel_steps_cap)
    if on_fit:
        on_fit('neural_complete', 'gru_%s_selection' % variant)

    steps = min(rec['selected_steps'], refit_steps_cap)
    rec['refit_steps'] = int(steps)
    mean_a, std_a = token_stats(split['X'], all_ids, split['pointer'], split['index'])
    ds_all = SeqDataset(split['X'], split['pointer'], split['index'], mean_a, std_a,
                        current_only)
    _init_rng(SEED)                     # same initial seed for the refit
    model = GRURULFactory.build().to(device)
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    if on_fit:
        on_fit('neural_start', 'gru_%s_refit' % variant)
    rng = np.random.default_rng(SEED)
    w_all = weights_cell_equal(cells[all_ids])
    w_all = w_all / w_all.mean()
    y_all = y_log[all_ids]
    model.train()
    for step in range(steps):
        pick = rng.integers(0, len(all_ids), BATCH)
        rows = all_ids[pick]
        x, l = ds_all.tensor_for(rows)
        x, l = x.to(device), l.to(device)
        mu, sigma = model(x, l)
        yt = torch.from_numpy(y_all[pick]).to(device)
        wt = torch.from_numpy(w_all[pick]).to(device)
        loss = (nll_gaussian(yt, mu, sigma) * wt).mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
    if on_fit:
        on_fit('neural_complete', 'gru_%s_refit' % variant)
    model.eval()
    rec['scalers'] = {'selection_mean_l2': float(np.linalg.norm(mean_f)),
                      'refit_mean_l2': float(np.linalg.norm(mean_a))}
    return model, ds_all, rec


def predict_gru(model, ds, row_ids, device):
    torch = _torch()
    mu = np.empty(len(row_ids))
    sigma = np.empty(len(row_ids))
    model.eval()
    with torch.no_grad():
        for a in range(0, len(row_ids), 128):
            sl = slice(a, min(a + 128, len(row_ids)))
            x, l = ds.tensor_for(row_ids[sl])
            m, s = model(x.to(device), l.to(device))
            mu[sl] = m.cpu().numpy()
            sigma[sl] = s.cpu().numpy()
    return mu, sigma


# --------------------------------------------------------------------------- #
# Fixed, pre-registered history summary for the tree model
# --------------------------------------------------------------------------- #
def history_features(X, ep, pointer, index, row_ids):
    """Pre-registered causal history summary (fixed before any training).

    Block A (710): prefix mean of every F3 feature (NaN-ignoring).
    Block B (7 per basis column): prefix std, first value, last-minus-first,
        OLS slope per week, prefix min, prefix max, mean of the last K tokens.
    Block C (3): current history length, weeks since the first snapshot,
        weeks since the previous snapshot.
    Nothing here depends on the target, on future snapshots, on the number of
    future queries or on the final length of the sequence.
    """
    basis = list(SUMMARY_BASIS_COLS)
    out = np.full((len(row_ids), N_SUMMARY), np.nan, np.float64)
    for j, r in enumerate(row_ids):
        a, b = int(pointer[r]), int(pointer[r + 1])
        idx = index[a:b]
        V = X[idx]
        ok = np.isfinite(V)
        cnt = ok.sum(0)
        mean = np.where(cnt > 0, np.nansum(V, 0) / np.maximum(cnt, 1), np.nan)
        out[j, :N_FEAT] = mean
        base = N_FEAT
        B = V[:, basis]
        Bok = np.isfinite(B)
        t = (ep[idx] - ep[r]) / 604800.0
        L = len(idx)
        for c in range(len(basis)):
            col = B[:, c]
            o = Bok[:, c]
            v = col[o]
            tt = t[o]
            if len(v) >= 2:
                dt = tt - tt.mean()
                den = float(np.dot(dt, dt))
                slope = float(np.dot(dt, v - v.mean()) / den) if den > 0 else np.nan
            else:
                slope = np.nan
            first = float(v[0]) if len(v) else np.nan
            last = float(v[-1]) if len(v) else np.nan
            k = min(SUMMARY_K, len(v))
            lastk = float(np.mean(v[-k:])) if k else np.nan
            stats = [float(np.std(v)) if len(v) > 1 else 0.0,
                     first,
                     (last - first) if len(v) else np.nan,
                     slope,
                     float(np.min(v)) if len(v) else np.nan,
                     float(np.max(v)) if len(v) else np.nan,
                     lastk]
            out[j, base + 7 * c:base + 7 * c + 7] = stats
        base = N_FEAT + 7 * len(basis)
        gap_prev = ((ep[r] - ep[idx[-2]]) / 604800.0) if L >= 2 else 0.0
        out[j, base:base + 3] = [float(L), (ep[r] - ep[idx[0]]) / 604800.0, gap_prev]
    return out.astype(np.float32)


def hgb_fit_predict(Xtr, ytr, wtr, Xva, seed=SEED, max_iter=HGB_MAX_ITER,
                    leaves=HGB_LEAVES, l2=HGB_L2):
    from sklearn.ensemble import HistGradientBoostingRegressor
    m = HistGradientBoostingRegressor(max_iter=max_iter, max_leaf_nodes=leaves,
                                      l2_regularization=l2, random_state=seed,
                                      early_stopping=False)
    m.fit(Xtr, ytr, sample_weight=wtr)
    return m, m.predict(Xva)


# --------------------------------------------------------------------------- #
# Output helpers
# --------------------------------------------------------------------------- #
def saveprogress(out, rec):
    p = out / 'progress.json.tmp'
    p.write_text(json.dumps(rec, indent=2, default=str))
    os.replace(p, out / 'progress.json')


def parse_baseline(path, model_name, expect_keys):
    payload_read()
    rows = []
    for r in csv.DictReader(pathlib.Path(path).open()):
        if r['model'] != model_name:
            continue
        k = key(r)
        if r['target_rul_weeks'] == '':
            tgt = None
        else:
            tgt = float(r['target_rul_weeks'])
        rows.append({
            'model': model_name, 'cell_id': k[0], 'arm': k[1],
            'query_epoch': k[2], 'target_rul_weeks': tgt,
            'known_event': r['known_event'] == 'True', 'y_event': int(r['y_event']),
            'median_weeks': float(r['median_weeks']),
            'mean_weeks': float(r['mean_weeks']),
            'severe_gt4w': '' if r['severe_gt4w'] == '' else float(r['severe_gt4w']),
            'IS80': '' if r['IS80'] == '' else float(r['IS80']),
            'coverage80': '' if r['coverage80'] == '' else float(r['coverage80']),
            'Brier4': '' if r['Brier4'] == '' else float(r['Brier4']),
            'Brier12': '' if r['Brier12'] == '' else float(r['Brier12']),
            'p_event': float(r['p_event']), 'seed': SEED,
            'mean_abs_error': '' if r['mean_abs_error'] == '' else float(r['mean_abs_error']),
            'median_abs_error': '' if r['median_abs_error'] == '' else float(r['median_abs_error']),
        })
    got = {key(r) for r in rows}
    if got != expect_keys:
        raise AssertionError('%s keys do not match the development keys (%d vs %d)'
                            % (model_name, len(got), len(expect_keys)))
    return rows


def with_point(rows, source):
    """Copy baseline rows with median_weeks replaced by another point estimate."""
    out = []
    for r in rows:
        r2 = dict(r)
        r2['median_weeks'] = float(r[source])
        out.append(r2)
    return out


# --------------------------------------------------------------------------- #
# Main training / evaluation driver
# --------------------------------------------------------------------------- #
def run(go_path):
    start = time.time()
    out = None
    rec = {'request_id': None, 'status': 'PREFLIGHT', 'started_utc': utc(),
           'C4_reads': 0, 'development_fit_rows': 0, 'neural_fits': 0,
           'optimizer_steps': 0, 'hgb_fits': 0, 'predictions': 0,
           'data_scope': DATA_SCOPE, 'script_sha256': sha(pathlib.Path(__file__))}
    locks = []

    # ---- gate: read-only, zero writes ------------------------------------- #
    try:
        g = readj(go_path)
    except Exception as exc:                                  # noqa: BLE001
        raise GoRejected('go_unreadable', 'cannot read GO: %r' % (exc,))
    gate = gate_go(g, sha_of=lambda rel: sha(ROOT / rel),
                   output_exists=lambda p: p.exists(),
                   receipt_exists=lambda p: p.exists())
    out = gate['out']
    rec['request_id'] = gate['request_id']
    rec['go_sha256'] = sha(go_path)
    rec['pinned_inputs'] = gate['pins']

    try:
        coord = readj(ROOT / 'automation/state/coordinator.json')
    except Exception as exc:                                  # noqa: BLE001
        raise GoRejected('coordinator_unreadable', repr(exc))
    if not (coord.get('owner') == coord.get('thread_id') == OWNER_THREAD_ID):
        raise GoRejected('coordinator_owner', 'coordinator owner/thread mismatch')
    if coord.get('state') != 'ACTIVE' or coord.get('takeover_verified') is not True:
        raise GoRejected('coordinator_state', 'coordinator is not ACTIVE/verified')
    if coord.get('actual_cwd') != str(ROOT):
        raise GoRejected('coordinator_cwd',
                         'coordinator cwd %r != %r' % (coord.get('actual_cwd'), str(ROOT)))

    registry = ROOT / 'experiments/state/consumed_gos.jsonl'
    if registry.exists():
        for line in registry.read_text().splitlines():
            if not line.strip():
                continue
            if json.loads(line).get('request_id') == gate['request_id']:
                raise GoRejected('already_consumed',
                                 'request_id already claimed: ' + gate['request_id'])
    claim = HERE / (gate['request_id'] + '.claim.json')
    if claim.exists():
        raise GoRejected('claim_exists', 'claim file exists: ' + claim.name)

    # ---- claim (first write), then the fresh output directory ------------- #
    for name in ['automation/state/online_survival_cpu.lock',
                 'automation/locks/isu_irregular_rul_cpu.lock',
                 'automation/locks/rul_gpu.lock']:
        f = (ROOT / name).open('a+')
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locks.append(f)
    try:
        with registry.open('a+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            if any(json.loads(l).get('request_id') == gate['request_id']
                   for l in f if l.strip()):
                raise GoRejected('already_consumed', 'request_id claimed under lock')
            createj(claim, {'pid': os.getpid(), 'go_sha256': sha(go_path),
                            'claimed_utc': utc()})
            f.write(json.dumps({'request_id': gate['request_id'],
                                'go_sha256': sha(go_path),
                                'claimed_utc': utc(),
                                'status': 'CLAIMED'}) + '\n')
            f.flush()
            os.fsync(f.fileno())
        out.mkdir(exist_ok=False)
    except GoRejected:
        for f in reversed(locks):
            f.close()
        raise

    rec.update(status='RUNNING', output=str(out.relative_to(ROOT)))
    signal.signal(signal.SIGALRM,
                  lambda *_: (_ for _ in ()).throw(TimeoutError('runtime budget')))
    signal.alarm(int(gate['runtime_cap']))

    try:
        # ---- data ---------------------------------------------------------- #
        audit = load_internal_audit()
        splitinfo = load_internal_split()
        train = load_split('train', 6870, 124)
        dev = load_split('development', 3765, 62)
        if not set(train['cells']).isdisjoint(set(dev['cells'])):
            raise AssertionError('train/development cell overlap')
        pos_tr = positive_ids(train['targets'])
        pos_dv = positive_ids(dev['targets'])
        if len(pos_tr) != 4713 or len(pos_dv) != 2697:
            raise AssertionError('unexpected positive populations')
        if len({train['cells'][i] for i in pos_tr}) != 120:
            raise AssertionError('expected 120 positive train cells')
        if len({dev['cells'][i] for i in pos_dv}) != 60:
            raise AssertionError('expected 60 positive development cells')
        fit_cells = set(splitinfo['fit_cells'])
        val_cells = set(splitinfo['validation_cells'])
        if len(fit_cells) != 96 or len(val_cells) != 24 or not fit_cells.isdisjoint(val_cells):
            raise AssertionError('internal split shape mismatch')
        if set(np.asarray(splitinfo['positive_train_indices']).tolist()) != set(pos_tr.tolist()):
            raise AssertionError('audit positive indices differ from the payload')
        fit_ids = np.asarray([i for i in pos_tr if train['cells'][i] in fit_cells], np.int64)
        val_ids = np.asarray([i for i in pos_tr if train['cells'][i] in val_cells], np.int64)
        if len(fit_ids) + len(val_ids) != len(pos_tr) or not len(val_ids):
            raise AssertionError('internal fit/validation partition failed')
        y_log = np.full(len(train['rows']), np.nan)
        y_log[pos_tr] = np.log(np.asarray([train['targets'][i]['target_rul_weeks']
                                           for i in pos_tr], float))
        rec.update(train_rows=len(train['rows']), development_rows=len(dev['rows']),
                   positive_train_rows=int(len(pos_tr)),
                   internal_fit_cells=len(fit_cells),
                   internal_validation_cells=len(val_cells),
                   audit_status=audit['status'])

        # ---- device / GPU preflight ---------------------------------------- #
        torch = _torch()
        torch.set_num_threads(4)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        gpu_txt = 'n/a'
        if device.type == 'cuda':
            import subprocess
            r = subprocess.run(['nvidia-smi',
                                '--query-gpu=index,name,memory.used,memory.total,utilization.gpu',
                                '--format=csv,noheader'], capture_output=True, text=True)
            gpu_txt = r.stdout.strip()
            free = []
            for line in gpu_txt.splitlines():
                parts = [p.strip() for p in line.split(',')]
                free.append(int(parts[3].split()[0]) - int(parts[2].split()[0]))
            if max(free) < 4096:
                raise RuntimeError('less than 4 GiB free on every GPU: %s' % gpu_txt)
        rec.update(device=str(device), gpu=gpu_txt)
        saveprogress(out, rec)

        # ---- GRU current / history ----------------------------------------- #
        cells_tr = train['cells']
        fits = []

        def on_fit(phase, name):
            if phase == 'neural_start':
                rec['neural_fits'] += 1
                if rec['neural_fits'] > gate['neural_fits_cap']:
                    raise AssertionError('neural fit budget exceeded')
                rec['current_fit'] = name
                saveprogress(out, rec)

        gru_models = {}
        gru_rec = {}
        for variant in ('current', 'history'):
            model, ds_all, mrec = train_gru(
                variant, train, fit_ids, val_ids, pos_tr, y_log, cells_tr,
                device, gate['steps_sel_cap'], gate['steps_refit_cap'],
                on_fit=on_fit)
            rec['optimizer_steps'] += mrec['selected_steps'] + mrec['refit_steps']
            mrec['optimizer_steps'] = mrec['selected_steps'] + mrec['refit_steps']
            fits.append(mrec)
            gru_models[variant] = (model, ds_all)
            gru_rec[variant] = mrec
            with (out / ('gru_%s.pt' % variant)).open('xb') as fh:
                torch.save(model.state_dict(), fh)
            saveprogress(out, rec)
        rec['gru_selection'] = fits
        if rec['neural_fits'] != 4:
            raise AssertionError('expected exactly 4 neural fits, got %d'
                                % rec['neural_fits'])

        # ---- HGB history summary ------------------------------------------- #
        hist_tr = history_features(train['X'], train['ep'], train['pointer'],
                                   train['index'], pos_tr)
        Xh = np.concatenate([train['X'][pos_tr], hist_tr], axis=1)
        if Xh.shape[1] != N_FEAT + N_SUMMARY:
            raise AssertionError('history feature width mismatch')
        ytr = y_log[pos_tr]
        wtr = weights_cell_equal(cells_tr[pos_tr])
        pcells = cells_tr[pos_tr]
        ids = sorted(set(pcells.tolist()))
        np.random.RandomState(SEED).shuffle(ids)
        folds = [set(ids[::2]), set(ids[1::2])]
        residual = np.empty(len(pos_tr))
        assigned = np.zeros(len(pos_tr), bool)
        for fi, held in enumerate(folds):
            sel = np.asarray([c not in held for c in pcells])
            va = ~sel
            if not sel.any() or not va.any():
                raise AssertionError('empty HGB cell fold')
            if rec['hgb_fits'] + 1 > gate['hgb_fits_cap']:
                raise AssertionError('hgb fit budget exceeded')
            rec['hgb_fits'] += 1
            rec['current_fit'] = 'hgb_history_summary_fold%d' % fi
            saveprogress(out, rec)
            print('FIT_START hgb_history_summary_fold%d' % fi, flush=True)
            m, mu_va = hgb_fit_predict(Xh[sel], ytr[sel], wtr[sel], Xh[va],
                                       max_iter=HGB_MAX_ITER, leaves=HGB_LEAVES,
                                       l2=HGB_L2)
            residual[va] = ytr[va] - mu_va
            assigned[va] = True
        if not assigned.all():
            raise AssertionError('OOF residual not assigned for every row')
        rec['hgb_fits'] += 1
        if rec['hgb_fits'] > gate['hgb_fits_cap']:
            raise AssertionError('hgb fit budget exceeded')
        rec['current_fit'] = 'hgb_history_summary_full'
        saveprogress(out, rec)
        print('FIT_START hgb_history_summary_full', flush=True)
        full, _ = hgb_fit_predict(Xh, ytr, wtr, Xh, max_iter=HGB_MAX_ITER,
                                  leaves=HGB_LEAVES, l2=HGB_L2)
        import joblib
        buf = pathlib.Path(out / 'hgb_history_summary.joblib')
        with buf.open('xb') as fh:
            joblib.dump({'model': full, 'n_current': N_FEAT,
                         'n_summary': N_SUMMARY,
                         'summary_basis_cols': list(SUMMARY_BASIS_COLS),
                         'summary_k': SUMMARY_K,
                         'residuals': residual,
                         'residual_weights': weights_cell_equal(pcells)},
                        fh)
        hist_dv = history_features(dev['X'], dev['ep'], dev['pointer'],
                                   dev['index'], np.arange(len(dev['rows'])))
        Xd = np.concatenate([dev['X'], hist_dv], axis=1)
        mu_dv = full.predict(Xd)
        if not np.isfinite(mu_dv).all():
            raise AssertionError('non-finite HGB prediction')
        rec['hgb_oof_residual_std'] = float(np.std(residual))
        rec['all_fits_and_step_selection_complete'] = True
        saveprogress(out, rec)

        # Development inference starts only now: every fit and every step
        # selection is complete, so no C3 input can influence what was fitted.
        gru_pred = {}
        for variant in ('current', 'history'):
            model, ds_all = gru_models[variant]
            mu, sigma = predict_gru(model, ds_all, np.arange(len(dev['rows'])),
                                    device)
            if not (np.isfinite(mu).all() and np.isfinite(sigma).all()
                    and (sigma > 0).all()):
                raise AssertionError('non-finite GRU prediction')
            gru_pred[variant] = (mu, sigma)

        # ---- distances and metric rows ------------------------------------- #
        base_f3 = {key(r): r for r in parse_baseline(
            CACHE / 'predictions.csv', 'hgb_F3', {key(r) for r in dev['rows']})}
        if len(base_f3) != 3765:
            raise AssertionError('F3 baseline must cover all 3765 development keys')
        wres = weights_cell_equal(pcells)
        resid_sorted_order = np.argsort(residual, kind='mergesort')
        residuals_sorted = residual[resid_sorted_order]
        w_sorted = wres[resid_sorted_order]
        preds = []
        dev_rows = dev['rows']
        for i, r in enumerate(dev_rows):
            tgt = dev['targets'][i]
            e = dict(tgt,
                     last_arrival_epoch=max(r['visible_rpt_arrival_epochs']),
                     delta_weeks=(float(r['query_epoch'])
                                  - max(r['visible_rpt_arrival_epochs'])) / 604800.0,
                     history_key=r['history_key'])
            p0 = float(base_f3[key(e)]['p_event'])
            dists = {}
            for variant, name in (('current', 'GRU_current'),
                                  ('history', 'GRU_history')):
                mu, sigma = gru_pred[variant]
                dists[name] = (PointZero() if tgt['known_event']
                               else HurdleMix(p0, LogNormalRUL(mu[i], sigma[i])))
            if tgt['known_event']:
                dists['HGB_history_summary'] = PointZero()
            else:
                positives = np.exp(mu_dv[i] + residuals_sorted)
                dists['HGB_history_summary'] = HurdleMix(
                    p0, EmpiricalRUL(positives, w_sorted))
            for name, dist in dists.items():
                preds.append(metric_row(e, dist, name))
        if len(preds) != 3 * 3765:
            raise AssertionError('expected 3 x 3765 predictions')
        pk = [(r['model'],) + key(r) for r in preds]
        if len(set(pk)) != len(pk):
            raise AssertionError('duplicate (model,cell,arm,query) prediction')
        dev_keys = {key(t) for t in dev['targets']}
        for name in ('GRU_current', 'GRU_history', 'HGB_history_summary'):
            got = {key(r) for r in preds if r['model'] == name}
            if got != dev_keys:
                raise AssertionError('%s does not cover exactly the 3,765 '
                                     'development keys' % name)
        for r in preds:
            b = base_f3[key(r)]
            bt = None if b['target_rul_weeks'] in ('', None) else float(b['target_rul_weeks'])
            rt = None if r['target_rul_weeks'] == '' else float(r['target_rul_weeks'])
            if bt != rt:
                raise AssertionError('target mismatch against the F3 baseline')
        rec.update(predictions=len(preds), all_fits_before_development_scoring=True)
        write_csv(out / 'predictions.csv', preds)
        summary, dist_cells, reliability = summarize(preds)
        write_csv(out / 'distribution_summary.csv', summary)
        write_csv(out / 'distribution_per_cell.csv', dist_cells)
        write_csv(out / 'reliability.csv', reliability)
        point = point_table(preds)
        write_csv(out / 'point_summary.csv', point)

        # ---- baselines, same keys ------------------------------------------ #
        b_f3 = parse_baseline(CACHE / 'predictions.csv', 'hgb_F3', set(base_f3))
        b_f3_mean = with_point(b_f3, 'mean_weeks')
        b_p1 = parse_baseline(HERE / 'p1_run1/predictions.csv',
                             'direct_squared_error', set(base_f3))
        b_p3 = parse_baseline(HERE / 'p3_calibration_run1/predictions.csv',
                              'ridge_context', set(base_f3))
        b_peer = parse_baseline(HERE / 'p3_peer_run1/predictions.csv',
                                'group_EOL_prior', set(base_f3))
        for rows_b, nm in ((b_f3, 'F3_median'), (b_f3_mean, 'F3_mean'),
                           (b_p1, 'P1_direct_squared'), (b_p3, 'P3_ridge_context'),
                           (b_peer, 'P3peer_group_EOL_prior')):
            for r in rows_b:
                r['model'] = nm
        base_rows = b_f3 + b_f3_mean + b_p1 + b_p3 + b_peer
        write_csv(out / 'baseline_point_summary.csv', point_table(base_rows))

        # ---- paired cell bootstrap ----------------------------------------- #
        model_rows = collections.defaultdict(list)
        for r in preds:
            model_rows[r['model']].append(r)
        base_by_name = {'F3_median': b_f3, 'F3_mean': b_f3_mean,
                        'P1_direct_squared': b_p1,
                        'P3_ridge_context': b_p3,
                        'P3peer_group_EOL_prior': b_peer}
        pairs = []
        for nm in ('GRU_current', 'GRU_history', 'HGB_history_summary'):
            for bn, brows in base_by_name.items():
                pairs.append((nm, model_rows[nm], bn, brows))
        pairs.append(('GRU_history', model_rows['GRU_history'],
                      'GRU_current', model_rows['GRU_current']))
        pairs.append(('GRU_history', model_rows['GRU_history'],
                      'HGB_history_summary', model_rows['HGB_history_summary']))
        pairs.append(('GRU_current', model_rows['GRU_current'],
                      'HGB_history_summary', model_rows['HGB_history_summary']))
        boot_rows = []
        skipped = []
        for arm in ARMS:
            for stratum in STRATA:
                for na, ra, nb, rb in pairs:
                    if not any(r['arm'] == arm and stratum_selected(r, stratum)
                               for r in ra):
                        skipped.append({'model': na, 'baseline': nb, 'arm': arm,
                                        'stratum': stratum,
                                        'reason': 'empty_stratum'})
                        continue
                    res = paired_bootstrap(ra, rb, arm, stratum)
                    row = {'model': na, 'baseline': nb, 'arm': arm,
                           'stratum': stratum}
                    row.update(res)
                    boot_rows.append(row)
        write_csv(out / 'paired_bootstrap.csv', boot_rows)
        write_csv(out / 'paired_bootstrap_skipped.csv', skipped)

        primary = {}
        for r in boot_rows:
            if r['arm'] == 'raw' and r['stratum'] == 'unconfirmed':
                primary['%s_vs_%s' % (r['model'], r['baseline'])] = {
                    k: r[k] for k in ('delta_mae_weeks', 'ci_low', 'ci_high',
                                      'p_delta_ge_0', 'improved_cell_fraction',
                                      'worst_cell_delta', 'n_cells', 'n_queries')}
        prim_point = [p for p in point if p['arm'] == 'raw'
                      and p['stratum'] == 'unconfirmed']
        rec.update(status='SUCCESS', finished_utc=utc(),
                   wall_seconds=time.time() - start,
                   primary_point=prim_point, primary_bootstrap=primary,
                   novelty_claim=False,
                   evidence_scope='Adaptive C3 development comparison; same-key '
                                  'paired cell bootstrap; no novelty claim')
        createj(gate['receipt'], rec)
        saveprogress(out, rec)
        print('SUCCESS ' + json.dumps(prim_point, default=float), flush=True)
        return rec
    except GoRejected:
        raise
    except BaseException as exc:                              # noqa: BLE001
        rec.update(status='FAILED_STOP', error=repr(exc),
                   traceback=traceback.format_exc(),
                   finished_utc=utc(), wall_seconds=time.time() - start)
        try:
            createj(out / 'failure_receipt.json', rec)
            saveprogress(out, rec)
        except Exception:                                     # noqa: BLE001
            pass
        raise
    finally:
        signal.alarm(0)
        for f in reversed(locks):
            f.close()


# --------------------------------------------------------------------------- #
# Prefix contract (shared by the real loader and the self-check)
# --------------------------------------------------------------------------- #
def verify_prefix(ep, cells, arms, pointer, index, length):
    """Hard causality contract for a prefix index: for every row, the prefix is
    a strictly time-increasing run of snapshots of the same cell and the same
    arm, ending at the row itself, containing no snapshot newer than the query.
    Raises AssertionError, never repairs."""
    n = len(ep)
    if not (len(length) == n and len(pointer) == n + 1):
        raise AssertionError('prefix index shape mismatch')
    if np.any(np.diff(pointer) != length):
        raise AssertionError('pointer/length disagreement')
    if np.any(length < 1):
        raise AssertionError('empty prefix')
    if np.any(index < 0) or np.any(index >= n):
        raise AssertionError('prefix index out of range')
    flat_ep = ep[index]
    row_of = np.repeat(np.arange(n), length)
    if np.any(cells[index] != cells[row_of]) or np.any(arms[index] != arms[row_of]):
        raise AssertionError('prefix crosses cell or arm')
    if np.any(index[pointer[:-1] + length - 1] != np.arange(n)):
        raise AssertionError('prefix must end at its own query')
    maxep = np.maximum.reduceat(flat_ep, pointer[:-1])
    if np.any(maxep > ep + 1e-6):
        raise AssertionError('prefix contains a future snapshot')
    d = np.diff(flat_ep)
    if len(d):
        keep = np.ones(len(d), bool)
        starts = pointer[:-1][1:]
        keep[np.clip(starts - 1, 0, len(d) - 1)] = False
        if np.any(d[keep] <= 0):
            raise AssertionError('prefix epochs not strictly increasing')
    return True


# --------------------------------------------------------------------------- #
# Self-check (synthetic data only; zero payload reads)
# --------------------------------------------------------------------------- #
def _synth(seed=SEED):
    """4 cells x 1 arm x 6 queries, 12 features, causal prefix index."""
    rng = np.random.default_rng(seed)
    n_feat = 12
    cells, arms, ep, X, y, truth = [], [], [], [], [], []
    ptr, idx, ln = [], [], []
    clock = 1.60e9
    for ci in range(4):
        cid = 'S%dC1' % (ci + 1)
        for q in range(1, 7):
            k = len(cells)
            cells.append(cid)
            arms.append('raw')
            ep.append(clock + q * 604800.0 + ci * 1e5)
            v = rng.normal(size=n_feat) + ci
            if q == 2 and ci == 1:
                v[3] = np.nan
            if q == 4 and ci == 2:
                v[5:8] = np.nan
            X.append(v)
            truth.append(np.log(7.0 - q))
            y.append(7.0 - q)
    X = np.asarray(X, float)
    ep = np.asarray(ep, float)
    cells = np.asarray(cells)
    arms = np.asarray(arms)
    start = 0
    for ci in range(4):
        rows = list(range(ci * 6, ci * 6 + 6))
        for j, r in enumerate(rows):
            ptr.append(start)
            seg = rows[:j + 1]
            idx.extend(seg)
            ln.append(len(seg))
            start += len(seg)
    ptr.append(start)
    return dict(X=X, ep=ep, cells=cells, arms=arms, y=np.asarray(y),
                logy=np.asarray(truth), pointer=np.asarray(ptr, np.int64),
                index=np.asarray(idx, np.int64), length=np.asarray(ln, np.int64),
                n_feat=n_feat)


def _fake_go():
    return {
        'request_id': 'RUL_TIME_P4_HISTORY_GRU_20261027_RUN1',
        'status': 'APPROVED', 'allow_fit': True,
        'owner_thread_id': OWNER_THREAD_ID, 'data_scope': DATA_SCOPE,
        'C4_allowed': False,
        'code_sha256': {k: 'a' * 64 for k in GO_REQUIRED_HASH_KEYS},
        'budget': {'grus': {'max_selection_steps_per_model': 400,
                            'max_refit_steps_per_model': 400,
                            'max_neural_fits': 4},
                   'hgb': {'max_fits': 3, 'max_iterations': 150,
                           'max_leaf_nodes': 15, 'max_l2': 1.0},
                   'max_runtime_seconds': 1800},
        'output': 'experiments/rul_time_recovery_20261026/p4_history_run1',
        'receipt': 'experiments/rul_time_recovery_20261026/p4_history_run1/receipt.json',
    }


def _right_pad_forward(model, X, pointer, index, row_ids, mean, std):
    """Reference path: right-padding, packed directly (no roll)."""
    torch = _torch()
    lens = np.asarray([int(pointer[r + 1] - pointer[r]) for r in row_ids], np.int64)
    T = int(lens.max())
    arr = np.zeros((len(row_ids), T, 2 * X.shape[1]), np.float32)
    for j, r in enumerate(row_ids):
        v = X[index[int(pointer[r]):int(pointer[r + 1])]]
        ok = np.isfinite(v)
        z = np.clip((np.where(ok, v, 0.0).astype(np.float32) - mean) / std, -5, 5)
        arr[j, :len(v), :X.shape[1]] = z
        arr[j, :len(v), X.shape[1]:] = ok.astype(np.float32)
    x = torch.from_numpy(arr)
    seq = model.proj(x)
    packed = torch.nn.utils.rnn.pack_padded_sequence(
        seq, torch.from_numpy(lens), batch_first=True, enforce_sorted=False)
    _, h = model.gru(packed)
    z = model.head(h[-1])
    sigma = torch.nn.functional.softplus(z[:, 1]) + model.sigma_floor
    return z[:, 0].detach().numpy(), sigma.detach().numpy()


def selfcheck(log_path):
    global _SYNTHETIC
    _SYNTHETIC = True
    t0 = time.time()
    torch = _torch()
    torch.set_num_threads(2)
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    results = []

    def check(name, fn):
        fn()
        results.append(name)
        print('PASS %-34s' % name, flush=True)

    s = _synth()
    X, ep, ptr, idx = s['X'], s['ep'], s['pointer'], s['index']
    n_feat = s['n_feat']
    zero_writes = []

    # 1. prefix contract accepts the synthetic index and rejects violations
    def t_prefix():
        verify_prefix(ep, s['cells'], s['arms'], ptr, idx, s['length'])
        bad = idx.copy()
        # future leak: row 3 (cell 1, 4th query) gets cell 1's 6th snapshot in
        # the middle of its prefix while still ending at itself
        bad[ptr[3] + 2] = 5
        try:
            verify_prefix(ep, s['cells'], s['arms'], ptr, bad, s['length'])
        except AssertionError:
            pass
        else:
            raise AssertionError('future snapshot was accepted')
        # cross-cell prefix
        bad2 = idx.copy()
        bad2[ptr[-2]] = 6
        try:
            verify_prefix(ep, s['cells'], s['arms'], ptr, bad2, s['length'])
        except AssertionError:
            pass
        else:
            raise AssertionError('cross-cell prefix was accepted')
        # non-increasing
        bad3 = idx.copy()
        bad3[ptr[10] + 2] = bad3[ptr[10] + 1]
        try:
            verify_prefix(ep, s['cells'], s['arms'], ptr, bad3, s['length'])
        except AssertionError:
            pass
        else:
            raise AssertionError('non-increasing prefix was accepted')
    check('prefix_causality_contract', t_prefix)

    # 2. mask / padding correctness
    mean, std = token_stats(X, np.arange(len(ep)), ptr, idx)

    def t_mask():
        rows = np.asarray([0, 3, 7, 14])
        arr, lens = build_sequences(X, ptr, idx, rows, mean, std, False)
        T = arr.shape[1]
        if arr.shape[2] != 2 * n_feat:
            raise AssertionError('bad channel width')
        for j, r in enumerate(rows):
            L = int(ptr[r + 1] - ptr[r])
            if lens[j] != L:
                raise AssertionError('bad length')
            pad = T - L
            if pad and not np.all(arr[j, :pad] == 0.0):
                raise AssertionError('left padding is not zero')
            seg = X[idx[int(ptr[r]):int(ptr[r + 1])]]
            ok = np.isfinite(seg)
            if not np.array_equal(arr[j, pad:, n_feat:] > 0.5, ok):
                raise AssertionError('mask does not equal finiteness')
            got = arr[j, pad:, :n_feat]
            exp = np.clip((np.where(ok, seg, 0.0) - mean) / std, -5, 5)
            if not np.allclose(got, exp.astype(np.float32), atol=1e-6):
                raise AssertionError('standardisation mismatch')
        cur, clens = build_sequences(X, ptr, idx, rows, mean, std, True)
        if cur.shape[1] != 1 or not np.all(clens == 1):
            raise AssertionError('current-only view is not a single token')
    check('mask_and_left_padding', t_mask)

    # 3. forward + backward one step, both variants, identical parameter count
    model_c = GRURULFactory.build(n_feat=n_feat)
    model_h = GRURULFactory.build(n_feat=n_feat)

    def t_param_parity():
        pc = sum(p.numel() for p in model_c.parameters())
        ph = sum(p.numel() for p in model_h.parameters())
        if pc != ph or pc == 0:
            raise AssertionError('parameter counts differ: %d vs %d' % (pc, ph))
    check('gru_parameter_parity', t_param_parity)

    def t_backward(variant, model):
        rows = np.asarray([5, 11, 17, 23])
        arr, lens = build_sequences(X, ptr, idx, rows, mean, std,
                                    variant == 'current')
        x = torch.from_numpy(arr)
        yt = torch.from_numpy(s['logy'][rows])
        opt = torch.optim.Adam(model.parameters(), lr=LR)
        before = [p.detach().clone() for p in model.parameters()]
        mu, sigma = model(x, torch.from_numpy(lens))
        if mu.shape != (len(rows),) or not torch.isfinite(mu).all():
            raise AssertionError('bad forward output')
        loss = nll_gaussian(yt, mu, sigma).mean()
        if not torch.isfinite(loss):
            raise AssertionError('non-finite loss')
        opt.zero_grad()
        loss.backward()
        for p in model.parameters():
            if p.grad is None or not torch.isfinite(p.grad).all():
                raise AssertionError('missing or non-finite gradient')
        opt.step()
        changed = any(not torch.equal(b, p.detach()) for b, p in zip(before,
                                                                    model.parameters()))
        if not changed:
            raise AssertionError('parameters did not update')
    check('gru_current_forward_backward', lambda: t_backward('current', model_c))
    check('gru_history_forward_backward', lambda: t_backward('history', model_h))

    # 4. right padding == left padding, and extra empty slots are never read
    def t_pad_equivalence():
        rows = np.asarray([2, 8, 13, 20])
        arr, lens = build_sequences(X, ptr, idx, rows, mean, std, False)
        mu_l, sg_l = model_h(torch.from_numpy(arr), torch.from_numpy(lens))
        mu_l, sg_l = mu_l.detach().numpy(), sg_l.detach().numpy()
        mu_r, sg_r = _right_pad_forward(model_h, X, ptr, idx, rows, mean, std)
        if not (np.allclose(mu_l, mu_r, atol=1e-5)
                and np.allclose(sg_l, sg_r, atol=1e-5)):
            raise AssertionError('left/right padding differ')
        wide = np.concatenate([np.zeros((len(rows), 4, arr.shape[2]),
                                             np.float32), arr], axis=1)
        mu_w, sg_w = model_h(torch.from_numpy(wide), torch.from_numpy(lens))
        if not (np.allclose(mu_l, mu_w.detach().numpy(), atol=1e-6)
                and np.allclose(sg_l, sg_w.detach().numpy(), atol=1e-6)):
            raise AssertionError('extra padding slots change the prediction')
    check('padding_never_read', t_pad_equivalence)

    # 5. future snapshots cannot change a query prediction
    def t_future_invariance():
        rows = np.asarray([4, 10])           # query 5 of cells 1 and 2
        arr0, l0 = build_sequences(X, ptr, idx, rows, mean, std, False)
        mu0, _ = model_h(torch.from_numpy(arr0), torch.from_numpy(l0))
        mu0 = mu0.detach().numpy()
        X2 = X.copy()
        keep = set(idx[ptr[rows[0]]:ptr[rows[0] + 1]].tolist())
        keep |= set(idx[ptr[rows[1]]:ptr[rows[1] + 1]].tolist())
        future = [i for i in range(len(ep)) if i not in keep]
        X2[future] += 1e6                    # corrupt every snapshot not in the prefix
        arr1, l1 = build_sequences(X2, ptr, idx, rows, mean, std, False)
        mu1, _ = model_h(torch.from_numpy(arr1), torch.from_numpy(l1))
        if not np.array_equal(mu0, mu1.detach().numpy()):
            raise AssertionError('future snapshots change the query prediction')
        arrc0, lc0 = build_sequences(X, ptr, idx, rows, mean, std, True)
        arrc1, lc1 = build_sequences(X2, ptr, idx, rows, mean, std, True)
        if not np.array_equal(arrc0, arrc1):
            raise AssertionError('current-only view reads the history')
    check('future_snapshot_invariance', t_future_invariance)

    # 6. HGB on a small sample (2 cell folds + full = 3 fits)
    def t_hgb():
        pos = np.arange(len(ep))
        feats = np.concatenate([X, np.zeros((len(X), 5), np.float32)], axis=1)
        y = s['logy']
        w = weights_cell_equal(s['cells'])
        pcells = s['cells']
        ids = sorted(set(pcells.tolist()))
        np.random.RandomState(SEED).shuffle(ids)
        folds = [set(ids[::2]), set(ids[1::2])]
        residual = np.empty(len(pos))
        for held in folds:
            sel = np.asarray([c not in held for c in pcells])
            va = ~sel
            m, mu = hgb_fit_predict(feats[sel], y[sel], w[sel], feats[va],
                                    max_iter=5, leaves=4)
            residual[va] = y[va] - mu
        full, mu_full = hgb_fit_predict(feats, y, w, feats, max_iter=5, leaves=4)
        if not (np.isfinite(residual).all() and np.isfinite(mu_full).all()):
            raise AssertionError('non-finite HGB output')
        if full.n_features_in_ != feats.shape[1]:
            raise AssertionError('HGB feature count mismatch')
    check('hgb_small_sample_3_fits', t_hgb)

    # 7. metric / summary / bootstrap pipeline on synthetic rows
    def t_eval_pipeline():
        rows = []
        for i in range(len(ep)):
            e = {'cell_id': s['cells'][i], 'arm': 'raw', 'query_epoch': float(ep[i]),
                 'last_arrival_epoch': float(ep[i]), 'delta_weeks': 0.0,
                 'history_key': '[]', 'known_event': False, 'y_event': 0,
                 'target_rul_weeks': float(s['y'][i])}
            for name, mu in (('synth_a', 0.05), ('synth_b', -0.15)):
                d = HurdleMix(0.1, LogNormalRUL(float(s['logy'][i]) + mu, 0.35))
                rows.append(metric_row(e, d, name))
        for r in rows:
            for c in ('target_rul_weeks', 'median_abs_error', 'IS80', 'coverage80',
                      'Brier4', 'Brier12', 'severe_gt4w'):
                if r[c] == '':
                    raise AssertionError('unexpected empty metric ' + c)
        summ, cells_out, rel = summarize(rows)
        if not summ or not cells_out or not rel:
            raise AssertionError('empty distribution summary')
        pt = point_table(rows)
        if not pt:
            raise AssertionError('empty point table')
        boot = paired_bootstrap(rows, rows, 'raw', 'all', B=200)
        if abs(boot['delta_mae_weeks']) > 1e-12 or boot['n_cells'] != 4:
            raise AssertionError('bootstrap identity failure')
        a = [r for r in rows if r['model'] == 'synth_a']
        b = [r for r in rows if r['model'] == 'synth_b']
        boot2 = paired_bootstrap(a, b, 'raw', 'all', B=200)
        if not (boot2['ci_low'] <= boot2['delta_mae_weeks'] <= boot2['ci_high']):
            raise AssertionError('bootstrap interval does not cover its mean')
        try:
            paired_bootstrap(a, b[:-1], 'raw', 'all', B=50)
        except AssertionError:
            pass
        else:
            raise AssertionError('unpaired populations were accepted')
    check('eval_metric_bootstrap_pipeline', t_eval_pipeline)

    # 8. metric parity against the project's own evaluate.metric_row
    def t_parity():
        sys.path.insert(0, str(ROOT / 'experiments/dart_rul_v18'))
        try:
            import evaluate as ev
        except Exception:
            print('SKIP metric parity (project evaluate.py not importable)')
            return
        rng = np.random.default_rng(7)
        for t in (0.0, 3.0, 25.0, 80.0):
            e = {'cell_id': 'X', 'arm': 'raw', 'query_epoch': 1.0,
                 'last_arrival_epoch': 1.0, 'delta_weeks': 0.0,
                 'history_key': '[]', 'known_event': False, 'y_event': 1,
                 'target_rul_weeks': t}
            d1 = HurdleMix(0.02, LogNormalRUL(3.0, 0.5))
            mine = metric_row(e, d1, 'm')
            theirs = ev.metric_row(e, d1, SEED, 'm', 0.0)
            for c in ('p_event', 'F4', 'F12', 'mean_weeks', 'median_weeks',
                      'q10', 'q90', 'median_abs_error', 'IS80', 'Brier4',
                      'Brier12', 'coverage80'):
                if isinstance(mine[c], float) and not math.isclose(
                        mine[c], float(theirs[c]), rel_tol=1e-12, abs_tol=1e-12):
                    raise AssertionError('metric parity break on ' + c)
    check('metric_parity_with_project', t_parity)

    # 9. GO gate: one valid GO and >= 10 rejections, all with zero writes
    import copy

    def t_go():
        good = _fake_go()
        sha_of = lambda rel: 'a' * 64
        gate_go(good, sha_of=sha_of, output_exists=lambda p: False,
                receipt_exists=lambda p: False)

        def mutate(fn, code):
            g = copy.deepcopy(good)
            fn(g)
            try:
                gate_go(g, sha_of=sha_of, output_exists=lambda p: False,
                        receipt_exists=lambda p: False)
            except GoRejected as exc:
                if exc.code != code:
                    raise AssertionError('expected %s, got %s (%s)'
                                         % (code, exc.code, exc.detail))
                zero_writes.append(code)
                return
            raise AssertionError('mutation accepted: ' + code)

        mutate(lambda g: g.update(status='PENDING'), 'status')
        mutate(lambda g: g.update(allow_fit=False), 'allow_fit')
        mutate(lambda g: g.update(owner_thread_id='deadbeef'), 'owner_thread_id')
        mutate(lambda g: g.update(data_scope='C1_C2_train_C3_dev_C4'), 'data_scope')
        mutate(lambda g: g.update(C4_allowed=True), 'c4')
        mutate(lambda g: g['code_sha256'].pop(GO_REQUIRED_HASH_KEYS[0]),
               'code_sha256_missing')
        mutate(lambda g: g['code_sha256'].update(
            {GO_REQUIRED_HASH_KEYS[0]: 'b' * 64}), 'code_sha256_mismatch')
        mutate(lambda g: g['code_sha256'].update(
            {GO_REQUIRED_HASH_KEYS[1]: 'zz'}), 'code_sha256_format')
        mutate(lambda g: g['code_sha256'].update({'../etc/passwd': 'a' * 64}),
               'code_sha256_path')
        mutate(lambda g: g['budget']['grus'].update(
            {'max_selection_steps_per_model': 401}), 'budget_selection_steps')
        mutate(lambda g: g['budget']['grus'].update(
            {'max_refit_steps_per_model': 801}), 'budget_refit_steps')
        mutate(lambda g: g['budget']['grus'].update({'max_neural_fits': 5}),
               'budget_neural_fits')
        mutate(lambda g: g['budget']['hgb'].update({'max_fits': 4}),
               'budget_hgb_fits')
        mutate(lambda g: g['budget'].update({'max_runtime_seconds': 3600}),
               'budget_runtime')
        mutate(lambda g: g['budget'].pop('hgb'), 'budget')
        mutate(lambda g: g.pop('request_id'), 'request_id')
        mutate(lambda g: g.update(
            output='experiments/rul_time_recovery_20261026/p3_calibration_run1'),
               'output_namespace')
        mutate(lambda g: g.update(output='/tmp/p4_run1'), 'output_path')
        mutate(lambda g: g.update(
            output='experiments/rul_time_recovery_20261026/deep/p4b'),
               'output_parent')
        mutate(lambda g: g.update(receipt='experiments/p4_run1/receipt.json'),
               'receipt_parent')
        # freshness failures need a path predicate
        for code, make_pred in (('output_not_fresh', 'out'),
                                ('receipt_not_fresh', 'rec')):
            g = copy.deepcopy(good)
            pred = (lambda p: True) if code == 'output_not_fresh' else (lambda p: False)
            pred2 = (lambda p: True) if code == 'receipt_not_fresh' else (lambda p: False)
            try:
                gate_go(g, sha_of=sha_of, output_exists=pred, receipt_exists=pred2)
            except GoRejected as exc:
                if exc.code != code:
                    raise AssertionError('expected %s, got %s' % (code, exc.code))
                zero_writes.append(code)
            else:
                raise AssertionError('freshness mutation accepted: ' + code)
        if len(zero_writes) < 10:
            raise AssertionError('fewer than 10 GO rejections exercised')
        GO_REJECT_CODES.extend(zero_writes)
    check('go_gate_rejections', t_go)

    # 10. GO contract is printable and names every required hash key
    def t_contract():
        c = go_contract()
        if set(c['required_hash_keys']) != set(GO_REQUIRED_HASH_KEYS):
            raise AssertionError('contract hash-key list drift')
        json.dumps(c)
    check('go_contract_serialisable', t_contract)

    if _PAYLOAD_READS != 0:
        raise AssertionError('self-check read %d payload files' % _PAYLOAD_READS)

    summary = {'status': 'PASS', 'utc': utc(), 'checks': len(results),
               'names': results, 'go_rejections': len(GO_REJECT_CODES),
               'go_rejection_codes': GO_REJECT_CODES,
               'payload_reads': _PAYLOAD_READS,
               'synthetic_cells': 4, 'synthetic_queries': int(len(ep)),
               'synthetic_features': int(n_feat),
               'wall_seconds': round(time.time() - t0, 3),
               'script_sha256': sha(pathlib.Path(__file__)),
               'python': sys.version.split()[0],
               'numpy': np.__version__,
               'torch': torch.__version__}
    print('SELF-CHECK PASS ' + json.dumps(summary, default=str), flush=True)
    if log_path:
        p = pathlib.Path(log_path)
        with p.open('a') as f:
            f.write(json.dumps(summary, default=str) + '\n')
        print('SELF_CHECK_LOG ' + str(p), flush=True)
    return summary


# --------------------------------------------------------------------------- #
# Read-only data-contract check (no fit, no optimizer step, no write)
# --------------------------------------------------------------------------- #
def check_data():
    """Validate the real payload against this file's contracts only.

    Reads the audited C1/C2/C3 cache, recomputes nothing of the audit, performs
    no forward/backward pass, increments no fit or optimizer-step counter and
    writes no file.
    """
    t0 = time.time()
    audit = load_internal_audit()
    splitinfo = load_internal_split()
    train = load_split('train', 6870, 124)
    dev = load_split('development', 3765, 62)
    if not set(train['cells']).isdisjoint(set(dev['cells'])):
        raise AssertionError('train/development cell overlap')
    pos_tr = positive_ids(train['targets'])
    pos_dv = positive_ids(dev['targets'])
    if len(pos_tr) != 4713 or len(pos_dv) != 2697:
        raise AssertionError('unexpected positive populations')
    fit_cells = set(splitinfo['fit_cells'])
    val_cells = set(splitinfo['validation_cells'])
    if len(fit_cells) != 96 or len(val_cells) != 24 or not fit_cells.isdisjoint(val_cells):
        raise AssertionError('internal split shape mismatch')
    fit_ids = np.asarray([i for i in pos_tr if train['cells'][i] in fit_cells], np.int64)
    val_ids = np.asarray([i for i in pos_tr if train['cells'][i] in val_cells], np.int64)
    if len(fit_ids) + len(val_ids) != len(pos_tr):
        raise AssertionError('internal fit/validation partition failed')
    mean, std = token_stats(train['X'], fit_ids, train['pointer'], train['index'])
    if not (np.isfinite(mean).all() and np.isfinite(std).all() and (std > 0).all()):
        raise AssertionError('bad standardisation statistics')
    arr, _ = build_sequences(train['X'], train['pointer'], train['index'],
                             pos_tr[:4], mean, std, False)
    cur, _ = build_sequences(train['X'], train['pointer'], train['index'],
                             pos_tr[:4], mean, std, True)
    token_stats(dev['X'], pos_dv[:64], dev['pointer'], dev['index'])
    hist = history_features(train['X'], train['ep'], train['pointer'],
                            train['index'], pos_tr[:8])
    if hist.shape != (8, N_SUMMARY) or not np.isfinite(hist[:, :N_FEAT]).any():
        raise AssertionError('history summary shape/number check failed')
    dev_hist = history_features(dev['X'], dev['ep'], dev['pointer'],
                                dev['index'], np.arange(16))
    # every evaluation input must cover exactly the development keys with the
    # same per-key targets; this is the same assertion the evaluation stage makes
    dev_keys = {key(t) for t in dev['targets']}
    dev_targets = {key(t): (None if t['target_rul_weeks'] is None
                            else float(t['target_rul_weeks']))
                   for t in dev['targets']}
    baseline_rows = {}
    for path, name in ((CACHE / 'predictions.csv', 'hgb_F3'),
                       (HERE / 'p1_run1/predictions.csv', 'direct_squared_error'),
                       (HERE / 'p3_calibration_run1/predictions.csv', 'ridge_context'),
                       (HERE / 'p3_peer_run1/predictions.csv', 'group_EOL_prior')):
        rows_b = parse_baseline(path, name, dev_keys)
        if {key(r): r['target_rul_weeks'] for r in rows_b} != dev_targets:
            raise AssertionError('per-key target mismatch in ' + str(path))
        if not all(math.isfinite(r['median_weeks']) and math.isfinite(r['mean_weeks'])
                   for r in rows_b):
            raise AssertionError('non-finite point estimate in ' + str(path))
        if name == 'hgb_F3' and not all(0.0 <= r['p_event'] <= 1.0 for r in rows_b):
            raise AssertionError('F3 hurdle probability out of range')
        baseline_rows[name] = {'rows': len(rows_b),
                               'sha256': sha(path)}
    out = {'status': 'PASS', 'utc': utc(),
           'baselines_same_keys_and_targets': True,
           'baselines': baseline_rows,
           'audit_status': audit['status'], 'audit_cell_overlap': audit['cell_overlap'],
           'train_rows': len(train['rows']), 'train_cells': int(len(set(train['cells']))),
           'development_rows': len(dev['rows']),
           'development_cells': int(len(set(dev['cells']))),
           'positive_train_rows': int(len(pos_tr)),
           'positive_development_rows': int(len(pos_dv)),
           'internal_fit_cells': len(fit_cells),
           'internal_validation_cells': len(val_cells),
           'fit_queries': int(len(fit_ids)), 'validation_queries': int(len(val_ids)),
           'max_history_length': int(train['length'].max()),
           'sequence_tensor_shape': [int(v) for v in arr.shape],
           'current_tensor_shape': [int(v) for v in cur.shape],
           'history_summary_shape': [int(v) for v in hist.shape],
           'dev_history_summary_shape': [int(v) for v in dev_hist.shape],
           'history_feature_width': int(N_FEAT + N_SUMMARY),
           'standardisation_finite': True,
           'prefix_contract': 'verified for every row of both splits',
           'fits': 0, 'optimizer_steps': 0, 'writes': 0, 'C4_reads': 0,
           'development_fit_rows': 0, 'forward_backward': 'not performed',
           'wall_seconds': round(time.time() - t0, 3),
           'script_sha256': sha(pathlib.Path(__file__))}
    print('DATA-CONTRACT PASS ' + json.dumps(out, default=str), flush=True)
    return 0


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(
        description='P4 direct-RUL-supervised history test (code + self-check).')
    ap.add_argument('--go', help='APPROVED training GO (exact-hash, fresh output)')
    ap.add_argument('--self-check', action='store_true',
                    help='synthetic self-check (default when --go is absent)')
    ap.add_argument('--print-go-contract', action='store_true',
                    help='print the GO field contract as JSON and exit')
    ap.add_argument('--check-data', action='store_true',
                    help='read-only payload contract check (no fit, no writes)')
    ap.add_argument('--log', default=str(HERE / 'P4_SELF_CHECK_LOG.jsonl'),
                    help='append-only self-check log')
    a = ap.parse_args(argv)
    if a.print_go_contract:
        print(json.dumps(go_contract(), indent=2))
        return 0
    if a.check_data:
        try:
            return check_data()
        except GoRejected:
            raise
        except Exception as exc:                              # noqa: BLE001
            print(json.dumps({'status': 'DATA_CONTRACT_FAILED',
                              'error': repr(exc),
                              'traceback': traceback.format_exc()},
                             ensure_ascii=False), file=sys.stderr)
            return 4
    if a.go:
        try:
            run(pathlib.Path(a.go))
        except GoRejected as exc:
            print(json.dumps({'status': 'GO_REJECTED', 'code': exc.code,
                              'detail': exc.detail, 'writes': 0,
                              'go_consumed': False}, ensure_ascii=False),
                  file=sys.stderr)
            return 3
        return 0
    try:
        selfcheck(a.log)
    except Exception as exc:                                  # noqa: BLE001
        print(json.dumps({'status': 'SELF_CHECK_FAILED', 'error': repr(exc),
                          'traceback': traceback.format_exc()},
                         ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
