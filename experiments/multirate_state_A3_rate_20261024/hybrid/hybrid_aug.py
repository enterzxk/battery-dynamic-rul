#!/home/yndx/miniconda3/envs/a40_env/bin/python3.9
"""HYBRID: does the A3 per-query mechanistic state make the strongest tree
significantly better?  (F2 98-dim cache + 9 mechanistic state features -> HGB)

Science question
----------------
A3_full (mechanistic multirate filter) and the strongest tree (HGB on the F2
98-dim frozen cache + h) are point-accuracy tied on the dev panel.  This
experiment tests the INFORMATION INCREMENT of the mechanistic state: feed the
A3 per-query filtered posterior (state_D/ell/R + covariance diagonal), the
walker's next-RPT forecast (mean, sd) and its implied degradation slope back
into the tree as extra features.  Two models, frozen design:

  A  baseline_F2_hgb   HGB on [F2 cache 98 | h]            (99 input cols)
                       -- pipeline replication gate: cell-macro MAE must be
                       within the GO tolerance of the pinned original F2_hgb
                       predictions CSV (nextcap18-9e7d9cb1c67f)
  B  hybrid_F2_A3state HGB on [F2 cache 98 | h | 9 state]  (108 input cols)
     state features (frozen order): state_D, state_ell, state_R, state_P00,
     state_P11, state_P22, pred_mean_ah,
     (pred_mean_ah - visible_capacity_min_ah) / gap_weeks  (implied slope),
     pred_sd_ah

Mechanistic features come from the frozen A3 walker (AsOfWalkerA3 + the exact
state-recording semantics of a3_infer._row_for_query; forecast via
a3_infer._advance_horizon under the held-recent-control policy -- the exact
computation behind the C3 CSV's state_*/pred_* columns):

  * train side: 125 PREP cells x 3 arms, the a3_calibrate.build_cell_arm
    derivation (verified 6498 queries == tree run2 receipt keys); the walker
    pass is a state-column extension of a3_calibrate.train_walker_pass.
  * dev side: the walker runs on the FULL tree dev panel (the 3579
    nextcap18 F2_hgb keys, re-derived and verified identical through
    ext_baselines.derive_cell_queries over the 61 dev RPT assets).  The saved
    C3 CSV covers only a sparser sub-grid (2343 scored keys, 2326 of them on
    the F2 panel), so it is used as an integrity cross-check on the common
    keys + as the A3_full / ENS3 reference predictions, NOT as the sole dev
    feature source.  Dev cells are loaded with a2_infer.load_cell /
    _build_dev_specs exactly as the C3 GO did (cohort + data/cycling/RPT
    manifests are pinned assets).
  * join key: (cell_id, arm, round(query_epoch,5), round(h,6)); cache rows
    joined by (cell_id, arm, round(query_epoch,6)).  Missing joins are
    counted and refuse the run (fail-closed).

sigma: tree-pipeline OOF discipline -- two cell-isolated folds over the
eligible train cells with V18 hgb_models._two_cell_folds semantics
(np.random.RandomState(42).shuffle(sorted ids); even/odd split), sigma =
sqrt(mean over cells of mean squared OOF residual).  NOTE: the tree OOF fold
rule is the RandomState even/odd split, NOT the sha256("42:"+cell) order
(that is the ext/a2 convention) -- "consistent with the tree pipeline" is
implemented as the tree rule verbatim.

Evaluation: the 3579-key dev panel, MAE / RMSE(=sqrt mean-cell MSE) / NLL /
cov90 / over20mAh / over50mAh pooled + cell-macro, per arm + overall;
5000-resample cell paired bootstrap (rng seed 20261024) for B vs A,
B vs F2 original, B vs A3_full and B vs ENS3 (equal-weight 3-seed Gaussian
mixture, moment-matched -- compare_ens3.py semantics).

GO discipline
-------------
Default (no arguments) = synthetic self-check (15 checks, >=12 refused GO
mutations); 0 real asset reads, 0 real GO files, 0 registry writes outside a
tempdir, 0 fits on real data.  --run-train --go GO.json requires an APPROVED
GO with allow_fit TRUE, allow_C4 false, scope containing HYBRID,
fits_in_this_go == 6 (A: 2 OOF folds + 1 final; B: same), seed 42, cpu / 4
threads, code pins = the exact import closure (CODE_PINS; a3_targets.py does
NOT exist in the A3 tree -- A3 reuses a2_targets.py), checkpoint + asset
path/sha pins, fresh request_id, fresh out_dir/receipt under
hybrid/runs|receipts.  This worker never creates or signs a GO; the
request_id is registered only after a fully successful run.
"""
from __future__ import annotations

import os
if os.environ.get("HYBRID_NO_THREADSET") != "1":
    for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ.setdefault(_v, "4")

import argparse
import copy
import csv
import datetime as _dt
import io
import json
import math
import shutil
import sys
import tempfile
import time
import traceback

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
_A3_DIR = os.path.dirname(HERE)
_EXT_DIR = os.path.join(_A3_DIR, "ext_baselines")
_A2_DIR = os.path.join(os.path.dirname(_A3_DIR), "multirate_state_A2_20261022")
if not (os.path.isdir(_EXT_DIR) and os.path.isdir(_A2_DIR)):
    _A3_DIR = os.path.join("/home/yndx/zxk/rul", "experiments",
                           "multirate_state_A3_rate_20261024")
    _EXT_DIR = os.path.join(_A3_DIR, "ext_baselines")
    _A2_DIR = os.path.join(os.path.dirname(_A3_DIR),
                           "multirate_state_A2_20261022")
for _p in (HERE, _EXT_DIR, _A3_DIR, _A2_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ext_baselines as ext          # Store / registry / panel rule / weights
import a3_calibrate as cal           # frozen train-panel derivation (reuse)
import a3_infer                      # walker + forecast + control policy
import a2_infer                      # ReadStats for load_cell
from a2_infer import (               # dev cell loading + query-grid code
    DELAY7D_SECONDS, _b2_arm_records, _build_dev_specs, _rpt_records_for_arm,
    build_queries, load_cell)
from a3_model import build_arm_model

SEED = 42
OWNER_THREAD_ID = ext.OWNER_THREAD_ID
ARMS = ext.ARMS
WEEK = ext.WEEK
THREADS = 4
DEVICE = "cpu"
MODEL_KEY = "full"
BASE_NAME = "baseline_F2_hgb"
HYB_NAME = "hybrid_F2_A3state"
PANEL_COL_BASE = "F2"
PANEL_COL_HYB = "HYB"
FITS_PER_MODEL = 3                   # 2 OOF folds + 1 all-rows final
FITS_IN_GO = FITS_PER_MODEL * 2      # = 6
MIN_RUNTIME = 600
MAX_RUNTIME = 21600
STALE_SECONDS = 86400.0
F2_CACHE_DIM = 98                    # frozen cache panel; X = cache | h (+9)
HYB_STATE_FEATURES = ("state_D", "state_ell", "state_R", "state_P00",
                      "state_P11", "state_P22", "pred_mean_ah",
                      "implied_slope_ah_per_week", "pred_sd_ah")
FROZEN_HGB_CONFIG = {"max_iter": 150, "max_leaf_nodes": 15,
                     "l2_regularization": 1, "random_state": 42,
                     "early_stopping": False}
SIGMA_SOURCE = ("tree-pipeline OOF sigma: sqrt(mean over cells of mean "
                "squared OOF residual) over two cell-isolated folds "
                "(V18 hgb_models._two_cell_folds semantics, seed 42)")
BOOTSTRAP_DRAWS = 5000
BOOTSTRAP_SEED = 20261024
Z90 = 1.6448536269514722
LOG_2PI = math.log(2.0 * math.pi)
ROOT = "/home/yndx/zxk/rul"
CACHE = os.path.join(ROOT, "experiments/multisource_factorial_20261021/"
                           "run2_clocksafe")
F2_REF_CSV = os.path.join(ROOT, "experiments/trajectory_multisource_nextcap_"
                                "20261021/runs/nextcap18-9e7d9cb1c67f/"
                                "predictions_c3.csv")
C3_S42 = os.path.join(_A3_DIR, "c3_eval_a3_20261024_run2",
                      "predictions_c3_a3.csv")
C3_S43 = os.path.join(_A3_DIR, "c3_eval_seed43_20261024",
                      "predictions_c3_a3.csv")
C3_S44 = os.path.join(_A3_DIR, "c3_eval_seed44_20261024",
                      "predictions_c3_a3.csv")
CKPT_FULL = os.path.join(_A3_DIR, "run1_fits", "model_state_dict_full.pt")
RPT_MANIFEST = os.path.join(ROOT, "reports/multisource_20261021_signals/"
                                  "all188_rpt_features_v1/manifest.json")
COHORT = os.path.join(ROOT, "reports/isu_ilcc_capacity_probe_20261020_root/"
                            "cohort.json")
DATA_MANIFEST = os.path.join(ROOT, "reports/isu_ilcc_datav2_full_20261020_"
                                   "root/data_manifest.json")
CYCLING_MANIFEST = os.path.join(ROOT, "reports/multisource_20261021_signals/"
                                      "cycling_all188_feature_manifest.json")
PRODUCTION_ASSET_PATHS = {
    "prep_manifest": os.path.join(ROOT, "experiments/multirate_state_A2_"
                                        "20261022/prep_v2_20261022/"
                                        "manifest.json"),
    "prep_npz": os.path.join(ROOT, "experiments/multirate_state_A2_20261022/"
                                   "prep_v2_20261022/"
                                   "a2_prep_sequences.npz"),
    "rpt_manifest": RPT_MANIFEST,
    "cohort": COHORT,
    "data_manifest": DATA_MANIFEST,
    "cycling_manifest": CYCLING_MANIFEST,
    "checkpoint": CKPT_FULL,
    "f2_train_features_npz": os.path.join(CACHE, "train_features.npz"),
    "f2_development_features_npz": os.path.join(CACHE,
                                                "development_features.npz"),
    "f2_train_rows": os.path.join(CACHE, "train_rows.jsonl"),
    "f2_development_rows": os.path.join(CACHE, "development_rows.jsonl"),
    "f2_feature_schema": os.path.join(CACHE, "feature_schema.json"),
    "f2_reference_csv": F2_REF_CSV,
    "c3_seed42_csv": C3_S42,
    "c3_seed43_csv": C3_S43,
    "c3_seed44_csv": C3_S44,
}
ASSET_KEYS = tuple(sorted(PRODUCTION_ASSET_PATHS))
CODE_PINS = ("hybrid_aug.py", "a3_calibrate.py", "ext_baselines.py",
             "a3_infer.py", "a3_model.py", "a3_train.py", "a2_infer.py",
             "a2_prep.py", "a2_targets.py", "a2_fastdata.py", "a2_model.py",
             "a2_train.py", "a2_fixtures.py")
CODE_PIN_DIRS = {"hybrid_aug.py": HERE, "a3_calibrate.py": _EXT_DIR,
                 "ext_baselines.py": _EXT_DIR}
LOG_PATH = os.path.join(HERE, "SELF_CHECK_LOG.txt")
BURNED_REQUEST_IDS = ()               # first run; burned ids appended here
GO_REQUIRED = ("status", "allow_fit", "allow_C4", "scope", "request_id",
               "owner_thread_id", "issued_utc", "seed", "device", "threads",
               "max_runtime_seconds", "code_sha256", "checkpoint", "assets",
               "panel_contract", "model_config", "fits_in_this_go",
               "replication_gate", "consumed_registry", "out_dir",
               "receipt_path")
C3_NEED_COLUMNS = ("cell_id", "arm", "model_key", "model_arm", "query_epoch",
                   "gap_weeks", "target_available", "target_capacity_ah",
                   "pred_mean_ah", "pred_var_ah2", "pred_sd_ah",
                   "state_D", "state_ell", "state_R", "state_P00",
                   "state_P11", "state_P22", "qref_ah",
                   "visible_capacity_min_ah")
F2_REF_HEADER = ["model", "panel", "cell_id", "arm", "query_epoch",
                 "forecast_h_weeks", "target_capacity_ah",
                 "predicted_capacity_ah", "sigma_oof_ah", "error_ah",
                 "abs_error_ah"]
METRIC_NAMES = ("MAE_Ah", "RMSE_Ah", "NLL_per_Ah", "coverage90",
                "over_20mAh", "over_50mAh")
# dev-side directory layout required by a2_infer._build_dev_specs
DEV_PROCESSED_REL = "data/processed/ISU_ILCC_DataV2_v1"
DEV_CYCLING_ROOT_REL = "reports/multisource_20261021_signals"
DEV_RPT_ROOT_REL = DEV_CYCLING_ROOT_REL + "/all188_rpt_features_v1"


class HybridError(RuntimeError):
    pass


# ------------------------------------------------------------------ helpers
def utc_now_iso():
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def atomic_json(path, payload):
    text = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=True) \
        + "\n"
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def panel_key(cell_id, arm, query_epoch, h_weeks):
    """The compare scripts' key: (cell, arm, round(q,5), round(h,6))."""
    return (str(cell_id), str(arm), round(float(query_epoch), 5),
            round(float(h_weeks), 6))


def cache_key(cell_id, arm, query_epoch):
    return (str(cell_id), str(arm), round(float(query_epoch), 6))


def _f(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        got = float(text)
    except ValueError:
        return None
    return got if math.isfinite(got) else None


def new_hgb():
    from sklearn.ensemble import HistGradientBoostingRegressor
    return HistGradientBoostingRegressor(**FROZEN_HGB_CONFIG)


def cell_weights(cell_ids):
    """tree_frac._weights semantics: 1 / per-cell row count (not rescaled)."""
    counts = {}
    for c in cell_ids:
        counts[str(c)] = counts.get(str(c), 0) + 1
    return np.asarray([1.0 / counts[str(c)] for c in cell_ids],
                      dtype=np.float64)


def two_cell_folds_v18(cell_ids, seed=SEED):
    """V18 hgb_models._two_cell_folds semantics, copied verbatim:
    RandomState(seed).shuffle(sorted unique ids) -> even/odd split."""
    ids = sorted({str(c) for c in cell_ids})
    if len(ids) < 2:
        raise HybridError("cell-isolated OOF requires at least two cells")
    rng = np.random.RandomState(seed)
    rng.shuffle(ids)
    folds = [set(ids[::2]), set(ids[1::2])]
    if any(not fold for fold in folds):
        raise HybridError("empty cell-isolated OOF fold")
    return folds


def sigma_from_oof(residuals, cell_ids):
    """F2 tree sigma: sqrt(mean over cells of mean squared OOF residual)."""
    by = {}
    for c, e in zip(cell_ids, residuals):
        by.setdefault(str(c), []).append(float(e) * float(e))
    if not by:
        raise HybridError("no cells for OOF sigma")
    return max(math.sqrt(float(np.mean([np.mean(v) for v in by.values()]))),
               1e-6)


# ------------------------------------------------- mechanistic feature rows
def walker_feature_rows(model, seq, queries, lag, vis_mins):
    """AsOfWalkerA3 + a3_infer state-recording semantics -> per-query rows.

    `queries`: monotone list of {key, q, h, y}; `vis_mins`: the parallel
    arm-visible capacity minima (the C3 column visible_capacity_min_ah).
    The state block mirrors a3_infer._row_for_query (state_D..state_P22 =
    m[0,0..2], P diag); the forecast is a3_infer._advance_horizon over the
    query gap under the held-recent-control policy -- the exact C3
    pred_mean_ah / pred_sd_ah computation."""
    cfg = a3_infer.MODEL_ARMS[MODEL_KEY]
    q_ref = float(seq["q_ref_ah"])
    q_ref_t = torch.tensor([q_ref], dtype=a3_infer.FILTER_DTYPE)
    walker = a3_infer.AsOfWalkerA3(model, seq, lag, cfg)
    rows = []
    with torch.no_grad():
        for query, vis_min in zip(queries, vis_mins):
            q = float(query["q"])
            h = float(query["h"])
            if not (math.isfinite(h) and h > 0.0):
                raise HybridError("non-positive gap at %r" % (query["key"],))
            state = walker.state_at(q)
            ctl_np, msk_np, _policy, _held = a3_infer._control_for_output(
                state, cfg)
            ctl = torch.as_tensor(ctl_np.reshape(1, -1),
                                  dtype=state["m"].dtype,
                                  device=state["m"].device)
            msk = torch.as_tensor(msk_np.reshape(1, -1),
                                  dtype=state["m"].dtype,
                                  device=state["m"].device)
            pred = a3_infer._advance_horizon(model, state["m"], state["P"],
                                             h, ctl, msk, q_ref_t, cfg)
            mu = float(pred["mean_ah"])
            sd = float(pred["sd_ah"])
            vals = (float(state["m"][0, 0]), float(state["m"][0, 1]),
                    float(state["m"][0, 2]), float(state["P"][0, 0, 0]),
                    float(state["P"][0, 1, 1]), float(state["P"][0, 2, 2]),
                    mu, (mu - float(vis_min)) / h, sd)
            if not all(math.isfinite(v) for v in vals) or sd <= 0.0:
                raise HybridError("non-finite/non-positive mechanistic "
                                  "feature row at %r" % (query["key"],))
            rows.append({
                "key": query["key"], "cell_id": query["key"][0],
                "arm": query["key"][1], "q": q, "h": h,
                "y": float(query["y"]), "qref_ah": q_ref,
                "visible_capacity_min_ah": float(vis_min),
                "pred_mean_ah": mu, "pred_sd_ah": sd,
                "pred_var_ah2": float(pred["var_ah2"]),
                "state_D": vals[0], "state_ell": vals[1], "state_R": vals[2],
                "state_P00": vals[3], "state_P11": vals[4],
                "state_P22": vals[5], "implied_slope_ah_per_week": vals[7],
            })
    return rows


def hyb_matrix_rows(rows):
    """9-column mechanistic block in the frozen feature order."""
    return np.asarray([[r["state_D"], r["state_ell"], r["state_R"],
                        r["state_P00"], r["state_P11"], r["state_P22"],
                        r["pred_mean_ah"], r["implied_slope_ah_per_week"],
                        r["pred_sd_ah"]] for r in rows], dtype=np.float64)


# ------------------------------------------------------------- F2 cache/ref
def load_f2_cache(store, paths):
    """{split: {by_key, mat, n}} for the frozen 98-dim F2 cache."""
    schema = store.read_json(paths["f2_feature_schema"], "f2_feature_schema")
    dims = (schema or {}).get("dimensions") or {}
    if int(dims.get("F2", -1)) != F2_CACHE_DIM:
        raise HybridError("feature_schema F2 dim != %d" % F2_CACHE_DIM)
    out = {}
    for split, npz_key, rows_key in (
            ("train", "f2_train_features_npz", "f2_train_rows"),
            ("development", "f2_development_features_npz",
             "f2_development_rows")):
        blob = store.read_bytes(paths[npz_key], npz_key)
        z = np.load(io.BytesIO(blob), allow_pickle=False)
        if "F2" not in z.files:
            raise HybridError("cache npz missing F2: %s" % split)
        mat = np.asarray(z["F2"], dtype=np.float64)
        meta = []
        for line in store.read_bytes(paths[rows_key],
                                     rows_key).decode("utf-8").splitlines():
            if line.strip():
                meta.append(json.loads(line))
        if mat.shape != (len(meta), F2_CACHE_DIM):
            raise HybridError("cache shape error %s: %r vs (%d, %d)"
                              % (split, mat.shape, len(meta), F2_CACHE_DIM))
        # tree_frac gate verbatim: inf refused, NaN allowed (HGB handles
        # missing values natively -- the frozen cache really carries a few)
        if np.isinf(mat).any():
            raise HybridError("non-finite (inf) values in cache %s" % split)
        n_nan = int(np.isnan(mat).sum())
        by_key = {}
        for i, m in enumerate(meta):
            k = cache_key(m["cell_id"], m["arm"], m["query_epoch"])
            if k in by_key:
                raise HybridError("duplicate cache key %s %r" % (split, k))
            by_key[k] = i
        out[split] = {"by_key": by_key, "mat": mat, "n": len(meta),
                      "n_nan": n_nan, "n_nan_rows":
                          int(np.isnan(mat).any(1).sum())}
    return out


def load_f2_reference(store, path):
    """Original F2_hgb dev panel: ordered keys + per-key records."""
    blob = store.read_bytes(path, "f2_reference_csv")
    reader = csv.DictReader(io.StringIO(blob.decode("utf-8")))
    if list(reader.fieldnames or ()) != F2_REF_HEADER:
        raise HybridError("F2 reference CSV header mismatch")
    keys = []
    recs = {}
    for row in reader:
        if row["model"] != "hgb" or row["panel"] != "F2":
            continue
        k = panel_key(row["cell_id"], row["arm"], row["query_epoch"],
                      row["forecast_h_weeks"])
        if k in recs:
            raise HybridError("duplicate F2 reference key %r" % (k,))
        recs[k] = {"y": float(row["target_capacity_ah"]),
                   "mu": float(row["predicted_capacity_ah"]),
                   "sd": float(row["sigma_oof_ah"]),
                   "q": float(row["query_epoch"]),
                   "h": float(row["forecast_h_weeks"])}
        keys.append(k)
    if not recs:
        raise HybridError("F2 reference CSV has no hgb/F2 rows")
    return keys, recs


def parse_c3_full(store, path):
    """C3 A3 CSV -> {key: rec} for model_key=full, scored rows only."""
    blob = store.read_bytes(path, "c3_predictions_csv")
    reader = csv.DictReader(io.StringIO(blob.decode("utf-8")))
    missing = [c for c in C3_NEED_COLUMNS
               if c not in (reader.fieldnames or [])]
    if missing:
        raise HybridError("C3 CSV missing columns %s" % missing)
    out = {}
    for row in reader:
        if str(row["model_key"]).strip() != MODEL_KEY:
            continue
        if str(row.get("target_available", "")).strip() != "1":
            continue
        q, h = _f(row["query_epoch"]), _f(row["gap_weeks"])
        y, mu = _f(row["target_capacity_ah"]), _f(row["pred_mean_ah"])
        sd, var = _f(row["pred_sd_ah"]), _f(row["pred_var_ah2"])
        if None in (q, h, y, mu, sd, var):
            continue
        k = panel_key(row["cell_id"], row["arm"], q, h)
        if k in out:
            raise HybridError("duplicate C3 key %r" % (k,))
        if abs(math.sqrt(var) - sd) > 1e-9 * max(1.0, sd):
            raise HybridError("C3 sd/var inconsistent at %r" % (k,))
        out[k] = {"y": y, "mu": mu, "sd": sd, "q": q, "h": h,
                  "qref_ah": _f(row["qref_ah"]),
                  "visible_capacity_min_ah":
                      _f(row["visible_capacity_min_ah"]),
                  "state_D": _f(row["state_D"]),
                  "state_ell": _f(row["state_ell"]),
                  "state_R": _f(row["state_R"]),
                  "state_P00": _f(row["state_P00"]),
                  "state_P11": _f(row["state_P11"]),
                  "state_P22": _f(row["state_P22"])}
    if not out:
        raise HybridError("C3 CSV has no scored full rows")
    return out


def ens3_moment(c3_dicts):
    """Equal-weight 3-component Gaussian mixture, moment-matched."""
    keys = None
    for d in c3_dicts:
        keys = set(d) if keys is None else (keys & set(d))
    out = {}
    for k in keys:
        comps = [(d[k]["mu"], d[k]["sd"] ** 2) for d in c3_dicts]
        mu = sum(m for m, _ in comps) / len(comps)
        var = sum(v + m * m for m, v in comps) / len(comps) - mu * mu
        out[k] = {"mu": mu, "sd": math.sqrt(max(var, 1e-12)),
                  "y": c3_dicts[0][k]["y"]}
    return out


def cross_check_c3(walker_rows, c3_recs, tol_state=1e-9, tol_pred=1e-6):
    """Dev-walker rows vs the C3 CSV on common keys (integrity gate)."""
    checked = 0
    worst = {"state": 0.0, "pred_mean": 0.0, "pred_sd": 0.0}
    for r in walker_rows:
        ref = c3_recs.get(r["key"])
        if ref is None:
            continue
        if abs(ref["y"] - r["y"]) > 1e-9:
            raise HybridError("C3/panel target mismatch at %r" % (r["key"],))
        ds = max(abs(ref[c] - r[c]) for c in
                 ("state_D", "state_ell", "state_R", "state_P00",
                  "state_P11", "state_P22"))
        dm = abs(ref["mu"] - r["pred_mean_ah"])
        dd = abs(ref["sd"] - r["pred_sd_ah"])
        worst["state"] = max(worst["state"], ds)
        worst["pred_mean"] = max(worst["pred_mean"], dm)
        worst["pred_sd"] = max(worst["pred_sd"], dd)
        if ds > tol_state or dm > tol_pred or dd > tol_pred:
            raise HybridError("C3 cross-check failed at %r "
                              "(dstate=%.3e dmean=%.3e dsd=%.3e)"
                              % (r["key"], ds, dm, dd))
        checked += 1
    return {"n_common": checked, "max_abs_diff": worst}


# -------------------------------------------------------------- join + fit
def join_cache(rows, cache_split, split):
    """Join panel rows to cache indices by (cell, arm, round(q,6))."""
    idxs = []
    missing = []
    for r in rows:
        k3 = cache_key(r["cell_id"], r["arm"], r["q"])
        idx = cache_split["by_key"].get(k3)
        if idx is None:
            missing.append(k3)
        idxs.append(idx)
    if missing:
        raise HybridError("%s join: %d rows without a cache row, e.g. %r"
                          % (split, len(missing), sorted(missing)[:3]))
    return np.asarray(idxs, dtype=np.int64), {"n_rows": len(rows),
                                              "n_matched": len(rows),
                                              "n_missing": 0}


def fit_model(name, X, y, w, cell_ids, ledger, deadline):
    """2 cell-isolated OOF folds (sigma) + 1 all-rows final fit.  3 fits."""
    folds = two_cell_folds_v18(cell_ids)
    union = folds[0] | folds[1]
    if union != set(str(c) for c in cell_ids) or (folds[0] & folds[1]):
        raise HybridError("invalid OOF cell partition for %s" % name)
    ordered = sorted(folds, key=lambda s: sorted(s)[0])
    oof = np.full(len(y), np.nan)
    for fi, held in enumerate(ordered):
        fit_idx = np.asarray([i for i, c in enumerate(cell_ids)
                              if str(c) not in held], dtype=np.int64)
        test_idx = np.asarray([i for i, c in enumerate(cell_ids)
                               if str(c) in held], dtype=np.int64)
        if time.monotonic() >= deadline:
            raise TimeoutError("GO runtime deadline reached before fit")
        m = ledger.run({"model": name, "fold": fi,
                        "held_cells": sorted(held),
                        "n_fit": int(len(fit_idx)),
                        "n_pred": int(len(test_idx))},
                       lambda ii=fit_idx: _fit_hgb(X[ii], y[ii], w[ii]))
        oof[test_idx] = m.predict(X[test_idx])
    if not np.isfinite(oof).all():
        raise HybridError("OOF incomplete for %s" % name)
    sigma = sigma_from_oof(y - oof, cell_ids)
    if time.monotonic() >= deadline:
        raise TimeoutError("GO runtime deadline reached before final fit")
    final = ledger.run({"model": name, "fold": "all", "n_fit": int(len(y)),
                        "n_pred": 0}, lambda: _fit_hgb(X, y, w))
    return final, sigma, oof, [sorted(f) for f in ordered]


def _fit_hgb(X, y, w):
    m = new_hgb()
    m.fit(X, y, sample_weight=w)
    return m


# --------------------------------------------------------------- metrics
def metric_row_set(mu, sd, y):
    e = np.asarray(mu, dtype=np.float64) - np.asarray(y, dtype=np.float64)
    s = np.asarray(sd, dtype=np.float64)
    v = s ** 2
    if not (np.isfinite(v) & (v > 0)).all():
        raise HybridError("non-positive sigma in metric block")
    return np.column_stack([np.abs(e), e ** 2,
                            0.5 * (e ** 2 / v + np.log(2 * np.pi * v)),
                            np.abs(e) <= Z90 * s, e > 0.02, e > 0.05])


def per_cell_metric_matrix(keys, z):
    """keys -> (cells, per-cell mean metric matrix V)."""
    cells = sorted({k[0] for k in keys})
    cmap = {c: i for i, c in enumerate(cells)}
    ci = np.asarray([cmap[k[0]] for k in keys], dtype=np.int64)
    count = np.bincount(ci, minlength=len(cells))
    V = np.stack([np.bincount(ci, weights=z[:, j], minlength=len(cells))
                  / count for j in range(z.shape[1])], axis=1)
    return cells, V


def _metric_blocks(z):
    return {"MAE_Ah": float(z[:, 0].mean()),
            "RMSE_Ah": float(math.sqrt(float(z[:, 1].mean()))),
            "NLL_per_Ah": float(z[:, 2].mean()),
            "coverage90": float(z[:, 3].mean()),
            "over_20mAh": float(z[:, 4].mean()),
            "over_50mAh": float(z[:, 5].mean())}


def evaluate_model(name, keys, mu, sd, y):
    """Per-arm + overall metric blocks (cell-macro + pooled)."""
    z = metric_row_set(mu, sd, y)
    cells, V = per_cell_metric_matrix(keys, z)
    out = {"all": {**_metric_blocks(V), "n": int(len(keys)),
                   "n_cells": len(cells),
                   "MAE_Ah_pooled": float(z[:, 0].mean()),
                   "RMSE_Ah_pooled": float(math.sqrt(float(z[:, 1].mean())))}}
    for arm in sorted({k[1] for k in keys}):
        sel = [i for i, k in enumerate(keys) if k[1] == arm]
        za = z[sel]
        _c, Va = per_cell_metric_matrix([keys[i] for i in sel], za)
        out[arm] = {**_metric_blocks(Va), "n": int(len(sel)),
                    "n_cells": len(_c),
                    "MAE_Ah_pooled": float(za[:, 0].mean()),
                    "RMSE_Ah_pooled": float(math.sqrt(float(za[:, 1]
                                                            .mean())))}
    return out


def paired_bootstrap(keys, model_vals, draws=BOOTSTRAP_DRAWS,
                     seed=BOOTSTRAP_SEED):
    """5000 cell resamples, candidate vs reference, per arm + overall.

    model_vals: {name: (mu, sd)} aligned with keys, plus "_y" (targets).
    Mirrors compare_a3_vs_all.py (metric deltas of cell-macro values; RMSE
    delta of sqrt(mean cell MSE))."""
    rng = np.random.default_rng(seed)
    y_all = np.asarray(model_vals["_y"], dtype=np.float64)
    names = [n for n in sorted(model_vals) if not str(n).startswith("_")]
    idx_of = {k: i for i, k in enumerate(keys)}
    out = []
    scopes = [("all", list(keys))] + [
        (arm, [k for k in keys if k[1] == arm])
        for arm in sorted({k[1] for k in keys})]
    for scope, skeys in scopes:
        if not skeys:
            continue
        sel = np.asarray([idx_of[k] for k in skeys])
        cmats = {}
        for name in names:
            mu, sd = model_vals[name]
            z = metric_row_set(np.asarray(mu)[sel], np.asarray(sd)[sel],
                               y_all[sel])
            cells, V = per_cell_metric_matrix(skeys, z)
            cmats[name] = (cells, V)
        ref_cells = cmats[names[0]][0]
        bs = rng.integers(0, len(ref_cells), (draws, len(ref_cells)))
        for cand in names:
            for ref in names:
                if cand == ref:
                    continue
                cl_c, Vc = cmats[cand]
                cl_r, Vr = cmats[ref]
                if cl_c != cl_r:
                    raise HybridError("cell set drift in bootstrap %s/%s"
                                      % (cand, ref))
                for j, metric in enumerate(METRIC_NAMES):
                    if j == 1:
                        p = float(math.sqrt(float(Vc[:, j].mean())) -
                                  math.sqrt(float(Vr[:, j].mean())))
                        dist = (np.sqrt(Vc[bs, j].mean(1)) -
                                np.sqrt(Vr[bs, j].mean(1)))
                    else:
                        p = float((Vc[:, j] - Vr[:, j]).mean())
                        dist = (Vc[:, j] - Vr[:, j])[bs].mean(1)
                    lo, hi = np.quantile(dist, [.025, .975])
                    out.append({
                        "scope": scope, "candidate": cand, "reference": ref,
                        "metric": metric, "delta": p,
                        "ci_low": float(lo), "ci_high": float(hi),
                        "cells": len(ref_cells),
                        "improved_cell_fraction":
                            float((Vc[:, j] < Vr[:, j]).mean()),
                        "draws": draws})
    return out


# ---------------------------------------------------------------- GO gate
def validate_go(go, go_path, store, expected_asset_paths, runs_parent,
                receipts_parent):
    problems = []
    missing = [k for k in GO_REQUIRED if k not in go]
    if missing:
        raise HybridError("GO missing required fields: %s" % missing)
    if go["status"] != "APPROVED":
        problems.append("status not APPROVED")
    if go["allow_fit"] is not True:
        problems.append("allow_fit is not true")
    if go.get("allow_C4") is not False:
        problems.append("allow_C4 must be false (C4 is sealed)")
    if "HYBRID" not in str(go["scope"]).upper():
        problems.append("scope lacks HYBRID")
    if go["owner_thread_id"] != OWNER_THREAD_ID:
        problems.append("owner mismatch")
    rid = go["request_id"]
    if not isinstance(rid, str) or len(rid) < 8:
        problems.append("request_id missing/too short")
    if str(rid) in BURNED_REQUEST_IDS:
        problems.append("request_id burned")
    if go["seed"] != SEED:
        problems.append("seed != 42")
    if go["device"] != DEVICE or int(go["threads"]) != THREADS:
        problems.append("device/threads contract mismatch (cpu/4)")
    if not MIN_RUNTIME <= int(go["max_runtime_seconds"]) <= MAX_RUNTIME:
        problems.append("max_runtime_seconds out of range")
    try:
        issued = _dt.datetime.fromisoformat(
            str(go["issued_utc"]).replace("Z", "+00:00"))
        age = (_dt.datetime.now(_dt.timezone.utc) - issued).total_seconds()
        if abs(age) > STALE_SECONDS:
            problems.append("GO stale (>24h)")
    except ValueError:
        problems.append("issued_utc is not an ISO timestamp")
    if int(go["fits_in_this_go"]) != FITS_IN_GO:
        problems.append("fits_in_this_go != %d" % FITS_IN_GO)
    if go["model_config"] != {"hgb": FROZEN_HGB_CONFIG}:
        problems.append("model_config != frozen HGB config")
    rg = go["replication_gate"]
    if not isinstance(rg, dict) or \
            not 0.0 < float(rg.get("f2_mae_cell_macro_rel_tol", 0)) <= 0.05:
        problems.append("replication_gate tolerance must be in (0, 0.05]")

    code = go["code_sha256"]
    pin_paths = {}
    for name in CODE_PINS:
        d = CODE_PIN_DIRS.get(name)
        if d is None:
            d = _A3_DIR if name.startswith("a3_") else _A2_DIR
        pin_paths[name] = os.path.join(d, name)
    if sorted(code) != sorted(pin_paths):
        problems.append("code_sha256 pins wrong file set (expected %s)"
                        % sorted(pin_paths))
    else:
        for name, path in pin_paths.items():
            if not os.path.isfile(path) or ext.sha256_file(path) != code[name]:
                problems.append("code sha mismatch: %s" % name)
    if json.loads(open(go_path, "r", encoding="utf-8").read()) != go:
        problems.append("GO document changed on disk")

    ckpt = go["checkpoint"]
    if sorted(ckpt) != ["path", "sha256"]:
        problems.append("checkpoint entry shape")
    else:
        if os.path.realpath(str(ckpt["path"])) != \
                os.path.realpath(expected_asset_paths["checkpoint"]):
            problems.append("checkpoint path is not the frozen full-model "
                            "checkpoint")
        else:
            try:
                store.read_bytes(store.resolve(ckpt["path"]), "go_checkpoint",
                                 expect_sha=ckpt["sha256"])
            except ext.ExtBaselineError as exc:
                problems.append("checkpoint: %s" % exc)

    assets = go["assets"]
    if sorted(assets) != sorted(ASSET_KEYS):
        problems.append("assets pin set mismatch (expected %s)"
                        % sorted(ASSET_KEYS))
    else:
        for key in ASSET_KEYS:
            entry = assets[key]
            if sorted(entry) != ["path", "sha256"]:
                problems.append("asset %s entry shape" % key)
                continue
            want = expected_asset_paths[key]
            if os.path.realpath(str(entry["path"])) != os.path.realpath(want):
                problems.append("asset %s path is not the frozen %s"
                                % (key, want))
                continue
            try:
                store.read_bytes(store.resolve(entry["path"]),
                                 "go_pinned_" + key,
                                 expect_sha=entry["sha256"])
            except ext.ExtBaselineError as exc:
                problems.append("asset %s: %s" % (key, exc))

    pc = go["panel_contract"]
    if not isinstance(pc, dict) or pc.get("arms") != list(ARMS):
        problems.append("panel_contract arms mismatch")
    elif not isinstance(pc.get("n_train_queries"), int) or \
            pc["n_train_queries"] <= 0:
        problems.append("panel_contract n_train_queries invalid")
    elif not isinstance(pc.get("n_dev_keys"), int) or \
            pc["n_dev_keys"] <= 0:
        problems.append("panel_contract n_dev_keys invalid")

    out_dir = go["out_dir"]
    receipt = go["receipt_path"]
    if os.path.realpath(os.path.dirname(os.path.abspath(out_dir))) != \
            os.path.realpath(runs_parent):
        problems.append("out_dir not fresh under hybrid/runs/")
    if os.path.exists(out_dir):
        problems.append("out_dir already exists")
    if os.path.realpath(os.path.dirname(os.path.abspath(receipt))) != \
            os.path.realpath(receipts_parent):
        problems.append("receipt_path not under hybrid/receipts/")
    if os.path.exists(receipt):
        problems.append("receipt_path already exists")
    if not ext.request_id_is_fresh(str(rid), str(go["consumed_registry"])):
        problems.append("request_id already consumed")
    if problems:
        raise HybridError("GO refused: " + "; ".join(problems))
    return (os.path.abspath(out_dir), os.path.abspath(receipt),
            str(go["consumed_registry"]), str(rid))


def load_checkpoint_model(store, ckpt_spec):
    blob = store.read_bytes(store.resolve(ckpt_spec["path"]), "checkpoint",
                            expect_sha=ckpt_spec["sha256"])
    try:
        obj = torch.load(io.BytesIO(blob), map_location="cpu",
                         weights_only=True)
    except TypeError:  # older torch
        obj = torch.load(io.BytesIO(blob), map_location="cpu")
    if isinstance(obj, dict) and "state_dict" in obj:
        obj = obj["state_dict"]
    model = build_arm_model(MODEL_KEY, seed=SEED)
    model.load_state_dict(obj, strict=True)
    model.eval()
    for name, param in model.named_parameters():
        if not torch.all(torch.isfinite(param)):
            raise HybridError("checkpoint has non-finite parameter %s"
                              % name)
    return model.double().eval()


# --------------------------------------------------------------- fit ledger
class FitLedger(object):
    """Fit recorder with a hard GO budget and per-fit json."""

    def __init__(self, out_dir, budget, deadline):
        self.out_dir = out_dir
        self.budget = int(budget)
        self.deadline = deadline
        self.started = 0
        self.completed = 0
        self.records = []

    def run(self, meta, fit_fn):
        if self.started >= self.budget:
            raise HybridError("fit budget exceeded (%d)" % self.budget)
        if time.monotonic() >= self.deadline:
            raise TimeoutError("GO runtime deadline reached before fit")
        self.started += 1
        rec = {"fit_index": self.started, **meta, "state": "STARTED",
               "started_utc": utc_now_iso()}
        atomic_json(os.path.join(self.out_dir, "fit_%02d.json"
                                 % self.started), rec)
        t0 = time.time()
        try:
            model = fit_fn()
        except BaseException:
            rec.update({"state": "FAILED",
                        "finished_utc": utc_now_iso()})
            atomic_json(os.path.join(self.out_dir, "fit_%02d.json"
                                     % self.started), rec)
            raise
        rec.update({"state": "COMPLETED", "seconds": time.time() - t0,
                    "finished_utc": utc_now_iso()})
        atomic_json(os.path.join(self.out_dir, "fit_%02d.json"
                                 % self.started), rec)
        self.completed += 1
        self.records.append(rec)
        return model


# ------------------------------------------------------- train/dev builders
def build_train_rows(model, store, paths, expected_cells, deadline,
                     log_every=25):
    """ext-rule train queries + walker mechanistic rows (0 fits, 0 steps)."""
    rpt_doc = store.read_json(paths["rpt_manifest"], "rpt_manifest")
    if str(rpt_doc.get("status")) != "ALL188_FEATURE_CACHE_COMPLETE":
        raise HybridError("RPT manifest status mismatch")
    inv = {str(e["cell_id"]): e for e in rpt_doc.get("inventory") or []}
    prep = ext.load_prep(store, paths["prep_manifest"], paths["prep_npz"])
    if len(prep["cells"]) != int(expected_cells):
        raise HybridError("PREP cell count %d != expected %d"
                          % (len(prep["cells"]), expected_cells))
    train_ids = sorted(prep["cells"])
    if int(rpt_doc.get("train", -1)) != len(train_ids):
        raise HybridError("RPT manifest train count mismatch")
    if int(rpt_doc.get("locked", 0)) != 0:
        raise HybridError("RPT manifest reports locked cells")
    names_ref = None
    rpt_assets = {}
    for cid in train_ids:
        entry = inv.get(cid)
        if entry is None or str(entry.get("role")) != "train":
            raise HybridError("RPT manifest role missing %s" % cid)
        rows, names = ext.load_rpt_json_cell(
            store, store.resolve(entry["path"]), cid,
            expect_sha=entry.get("sha256"))
        rpt_assets[cid] = (rows, names)
        if names_ref is None:
            names_ref = names
    all_rows = []
    n_cells = 0
    with torch.no_grad():
        for cid in train_ids:
            if time.monotonic() >= deadline:
                raise TimeoutError("runtime deadline in train walker")
            rows, names = rpt_assets[cid]
            if names != names_ref:
                raise HybridError("feature set drift for %s" % cid)
            pc = prep["cells"][cid]
            ext.cross_check_train(pc, rows, cid)
            for arm in ARMS:
                seq, queries = cal.build_cell_arm(cid, pc, rows, names_ref,
                                                  arm)
                lag = DELAY7D_SECONDS if arm == "delay7d" else 0.0
                qd = [{"key": panel_key(cid, arm, q["q"], q["gap"]),
                       "q": q["q"], "h": q["gap"], "y": q["y"]}
                      for q in queries]
                vis = [min(rows[i]["cap"] for i in
                           ext.visible_indices(rows, arm, q["q"]))
                       for q in queries]
                all_rows.extend(walker_feature_rows(model, seq, qd, lag,
                                                    vis))
            n_cells += 1
            if log_every and n_cells % log_every == 0:
                print("  [hybrid-train] cells %d/%d rows %d"
                      % (n_cells, len(train_ids), len(all_rows)))
    if not all_rows:
        raise HybridError("train walker produced no rows")
    return all_rows, len(train_ids)


def a2_prep_cell_sequence(cid, cycles, rpts_arm):
    import a2_prep
    try:
        seq = a2_prep.cell_sequence(cid, cycles, rpts_arm, cutoff_epoch=None)
    except Exception as exc:  # noqa: BLE001 - a2_prep.PrepError passthrough
        raise HybridError("cell %s sequence refused: %s" % (cid, exc))
    if seq.get("anchor") is None:
        raise HybridError("cell %s has no anchor" % cid)
    return seq


def build_dev_specs(store, paths, expected_dev_cells):
    """a2_infer._build_dev_specs over the pinned manifests (dev only)."""
    docs = {name: store.read_json(paths[name], name)
            for name in ("cohort", "data_manifest", "cycling_manifest",
                         "rpt_manifest")}
    cohort_path = store.resolve(paths["cohort"])
    data_root = os.path.realpath(os.path.dirname(os.path.dirname(
        os.path.dirname(cohort_path))))
    specs, _roots = _build_dev_specs(docs["cohort"], docs["data_manifest"],
                                     docs["cycling_manifest"],
                                     docs["rpt_manifest"], data_root,
                                     int(expected_dev_cells))
    return {s["cell_id"]: s for s in specs}


def build_dev_rows(model, store, paths, panel_keys, panel_recs, deadline,
                   expected_dev_specs, log_every=10):
    """Walker mechanistic rows on the FULL tree dev panel keys."""
    spec_map = build_dev_specs(store, paths, expected_dev_specs)
    panel_cells = sorted({k[0] for k in panel_keys})
    if not set(panel_cells) <= set(spec_map):
        raise HybridError("panel cells not covered by dev specs: %s"
                          % sorted(set(panel_cells) - set(spec_map))[:3])
    by_cell_arm = {}
    for k in panel_keys:
        by_cell_arm.setdefault((k[0], k[1]), []).append(k)
    stats = a2_infer.ReadStats()
    all_rows = []
    done = 0
    with torch.no_grad():
        for cid in panel_cells:
            if time.monotonic() >= deadline:
                raise TimeoutError("runtime deadline in dev walker")
            cell = load_cell(spec_map[cid], stats)
            if cell.get("skip_reason"):
                raise HybridError("panel cell %s skipped: %s"
                                  % (cid, cell["skip_reason"]))
            for arm in ARMS:
                keys = sorted(by_cell_arm.get((cid, arm), []))
                if not keys:
                    continue
                policy = _b2_arm_records(cell["rows"], 1, arm)
                rpts_arm = _rpt_records_for_arm(cell["rpts"], policy)
                seq = a2_prep_cell_sequence(cid, cell["cycles"], rpts_arm)
                queries = []
                vis = []
                for k in keys:
                    rec = panel_recs[k]
                    visible = [r for r in policy
                               if float(r["arrival_epoch"])
                               <= rec["q"] + 1e-9]
                    if len(visible) < 3:
                        raise HybridError("panel key with <3 arm-visible "
                                          "records: %r" % (k,))
                    queries.append({"key": k, "q": rec["q"], "h": rec["h"],
                                    "y": rec["y"]})
                    vis.append(min(float(r["capacityAh"])
                                   for r in visible))
                lag = DELAY7D_SECONDS if arm == "delay7d" else 0.0
                all_rows.extend(walker_feature_rows(model, seq, queries,
                                                    lag, vis))
            done += 1
            if log_every and done % log_every == 0:
                print("  [hybrid-dev] cells %d/%d rows %d"
                      % (done, len(panel_cells), len(all_rows)))
    if len(all_rows) != len(panel_keys):
        raise HybridError("dev walker rows %d != panel keys %d"
                          % (len(all_rows), len(panel_keys)))
    return all_rows, {"processed_cells": int(stats.processed_cells),
                      "cycling_cells": int(stats.cycling_cells)}


# ----------------------------------------------------------------- runner
def run_go(go_path, store=None, runs_parent=None, receipts_parent=None,
           use_locks=True, expected_asset_paths=None):
    t0 = time.time()
    real = store is None
    stats = ext.ReadStats()
    if real:
        store = ext.Store([ROOT], stats, base=ROOT)
    if expected_asset_paths is None:
        expected_asset_paths = PRODUCTION_ASSET_PATHS
    runs_parent = runs_parent or os.path.join(HERE, "runs")
    receipts_parent = receipts_parent or os.path.join(HERE, "receipts")
    out_dir = None
    receipt_path = None
    locks = []
    rec = {"status": "PREFLIGHT_FAILED", "fits_started": 0, "fit_count": 0,
           "C4_payload_reads": 0, "fits": []}
    try:
        go = json.loads(open(go_path, "r", encoding="utf-8").read())
        out_dir, receipt_path, registry, rid = validate_go(
            go, go_path, store, expected_asset_paths, runs_parent,
            receipts_parent)
        rec.update(request_id=rid, go_sha256=ext.sha256_file(go_path))
        deadline = time.monotonic() + int(go["max_runtime_seconds"])
        if use_locks:
            import fcntl
            for lp in (os.path.join(ROOT, "automation/state/"
                                    "online_survival_cpu.lock"),
                       os.path.join(ROOT, "automation/locks/"
                                    "isu_irregular_rul_cpu.lock")):
                f = open(lp, "a+")
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locks.append(f)
        os.makedirs(runs_parent, exist_ok=True)
        os.makedirs(receipts_parent, exist_ok=True)
        os.makedirs(out_dir)
        torch.set_num_threads(THREADS)
        rec.update(status="LOADING_ASSETS")
        atomic_json(os.path.join(out_dir, "progress.json"), rec)

        paths = {k: go["assets"][k]["path"] for k in ASSET_KEYS}
        pc = go["panel_contract"]
        cache = load_f2_cache(store, paths)
        panel_keys, panel_recs = load_f2_reference(
            store, go["assets"]["f2_reference_csv"]["path"])
        if len(panel_keys) != int(pc["n_dev_keys"]):
            raise HybridError("F2 reference panel %d != GO contract %d"
                              % (len(panel_keys), pc["n_dev_keys"]))
        c3_s42 = parse_c3_full(store, go["assets"]["c3_seed42_csv"]["path"])
        c3_s43 = parse_c3_full(store, go["assets"]["c3_seed43_csv"]["path"])
        c3_s44 = parse_c3_full(store, go["assets"]["c3_seed44_csv"]["path"])
        model = load_checkpoint_model(store, go["checkpoint"])

        # ---- stage 1: train panel + walker states ------------------------
        rec.update(status="TRAIN_WALKER")
        atomic_json(os.path.join(out_dir, "progress.json"), rec)
        n_train_expected = int(pc["n_train_queries"])
        expected_train_cells = int(pc.get("n_train_cells", 125))
        train_rows, n_train_cells = build_train_rows(
            model, store, paths, expected_train_cells, deadline=deadline)
        if len(train_rows) != n_train_expected:
            raise HybridError("derived train queries %d != GO contract %d"
                              % (len(train_rows), n_train_expected))
        if n_train_cells != expected_train_cells:
            raise HybridError("train cells %d != expected %d"
                              % (n_train_cells, expected_train_cells))
        tidx, train_join = join_cache(train_rows, cache["train"], "train")

        # ---- stage 2: dev panel walker + C3 cross-check ------------------
        rec.update(status="DEV_WALKER")
        atomic_json(os.path.join(out_dir, "progress.json"), rec)
        expected_dev_specs = int(pc.get("n_dev_specs", 63))
        dev_rows, dev_reads = build_dev_rows(
            model, store, paths, panel_keys, panel_recs, deadline,
            expected_dev_specs)
        didx, dev_join = join_cache(dev_rows, cache["development"],
                                    "development")
        cross = cross_check_c3(dev_rows, c3_s42)
        c3_only = len(set(c3_s42) - {r["key"] for r in dev_rows})

        # ---- stage 3: 6 fits (A then B) ----------------------------------
        rec.update(status="FITTING")
        atomic_json(os.path.join(out_dir, "progress.json"), rec)
        ledger = FitLedger(out_dir, FITS_IN_GO, deadline)
        tr_cells = [r["cell_id"] for r in train_rows]
        y_tr = np.asarray([r["y"] for r in train_rows], dtype=np.float64)
        h_tr = np.asarray([r["h"] for r in train_rows], dtype=np.float64)
        w_tr = cell_weights(tr_cells)
        X_A_tr = np.column_stack((cache["train"]["mat"][tidx], h_tr))
        X_B_tr = np.column_stack((X_A_tr, hyb_matrix_rows(train_rows)))
        # inf refused everywhere; NaN allowed in the cache block only (HGB
        # native missing-value handling, original F2 pipeline semantics);
        # the mechanistic block must be fully finite (walker guarantee)
        if np.isinf(X_A_tr).any() or np.isinf(X_B_tr).any() or \
                not np.isfinite(X_B_tr[:, F2_CACHE_DIM + 1:]).all():
            raise HybridError("invalid training matrix (inf / non-finite "
                              "mechanistic block)")
        m_A, sig_A, _oof_A, folds = fit_model(BASE_NAME, X_A_tr, y_tr, w_tr,
                                              tr_cells, ledger, deadline)
        m_B, sig_B, _oof_B, folds_B = fit_model(HYB_NAME, X_B_tr, y_tr,
                                                w_tr, tr_cells, ledger,
                                                deadline)
        if folds != folds_B:
            raise HybridError("fold drift between A and B")

        # ---- stage 4: dev predictions + metrics + bootstrap --------------
        rec.update(status="DEV_PREDICT")
        atomic_json(os.path.join(out_dir, "progress.json"), rec)
        h_dev = np.asarray([r["h"] for r in dev_rows], dtype=np.float64)
        y_dev = np.asarray([r["y"] for r in dev_rows], dtype=np.float64)
        dkeys = [r["key"] for r in dev_rows]
        X_A_dev = np.column_stack((cache["development"]["mat"][didx],
                                   h_dev))
        X_B_dev = np.column_stack((X_A_dev, hyb_matrix_rows(dev_rows)))
        if np.isinf(X_A_dev).any() or np.isinf(X_B_dev).any() or \
                not np.isfinite(X_B_dev[:, F2_CACHE_DIM + 1:]).all():
            raise HybridError("invalid dev matrix (inf / non-finite "
                              "mechanistic block)")
        mu_A = np.asarray(m_A.predict(X_A_dev), dtype=np.float64)
        mu_B = np.asarray(m_B.predict(X_B_dev), dtype=np.float64)
        idx_of = {k: i for i, k in enumerate(dkeys)}
        mu_F2 = np.full(len(dkeys), np.nan)
        sd_F2 = np.full(len(dkeys), np.nan)
        for k, r in panel_recs.items():
            mu_F2[idx_of[k]] = r["mu"]
            sd_F2[idx_of[k]] = r["sd"]
        if not (np.isfinite(mu_F2) & np.isfinite(sd_F2)).all():
            raise HybridError("F2 reference did not cover the panel")

        metrics = {
            BASE_NAME: evaluate_model(BASE_NAME, dkeys, mu_A,
                                      np.full(len(dkeys), sig_A), y_dev),
            HYB_NAME: evaluate_model(HYB_NAME, dkeys, mu_B,
                                     np.full(len(dkeys), sig_B), y_dev)}
        f2_keys = sorted(panel_recs)
        metrics["F2_hgb_original"] = evaluate_model(
            "F2_hgb_original", f2_keys,
            np.asarray([panel_recs[k]["mu"] for k in f2_keys]),
            np.asarray([panel_recs[k]["sd"] for k in f2_keys]),
            np.asarray([panel_recs[k]["y"] for k in f2_keys]))

        # replication gate: A vs F2 original (cell-macro MAE)
        tol = float(go["replication_gate"]["f2_mae_cell_macro_rel_tol"])
        mA = metrics[BASE_NAME]["all"]["MAE_Ah"]
        mF = metrics["F2_hgb_original"]["all"]["MAE_Ah"]
        rel = abs(mA - mF) / mF
        gate = {"baseline_mae_cell_macro": mA,
                "f2_original_mae_cell_macro": mF,
                "abs_diff": abs(mA - mF), "rel_diff": rel,
                "tolerance": tol, "pass": bool(rel <= tol)}
        if not gate["pass"]:
            raise HybridError("pipeline replication gate FAILED: baseline "
                              "MAE %.6g vs F2 original %.6g (rel %.4f > "
                              "%.4f)" % (mA, mF, rel, tol))

        # bootstrap 1: full panel, B vs A and B vs F2 original (+ A vs F2)
        boot_full = paired_bootstrap(dkeys, {
            BASE_NAME: (mu_A, np.full(len(dkeys), sig_A)),
            HYB_NAME: (mu_B, np.full(len(dkeys), sig_B)),
            "F2_hgb_original": (mu_F2, sd_F2), "_y": y_dev})

        # bootstrap 2: A3-common panel, B vs A3_full and B vs ENS3
        ens3 = ens3_moment((c3_s42, c3_s43, c3_s44))
        common3 = sorted(set(c3_s42) & set(dkeys) & set(ens3))
        sel3 = np.asarray([idx_of[k] for k in common3])
        boot_a3 = paired_bootstrap(common3, {
            HYB_NAME: (mu_B[sel3], np.full(len(sel3), sig_B)),
            BASE_NAME: (mu_A[sel3], np.full(len(sel3), sig_A)),
            "A3_full": (np.asarray([c3_s42[k]["mu"] for k in common3]),
                        np.asarray([c3_s42[k]["sd"] for k in common3])),
            "ENS3": (np.asarray([ens3[k]["mu"] for k in common3]),
                     np.asarray([ens3[k]["sd"] for k in common3])),
            "_y": np.asarray([c3_s42[k]["y"] for k in common3])})

        # ---- outputs ------------------------------------------------------
        rec.update(status="WRITING")
        atomic_json(os.path.join(out_dir, "progress.json"), rec)
        for name, panel_col, mu, sig in (
                (BASE_NAME, PANEL_COL_BASE, mu_A, sig_A),
                (HYB_NAME, PANEL_COL_HYB, mu_B, sig_B)):
            sub = os.path.join(out_dir, name)
            os.makedirs(sub)
            with open(os.path.join(sub, "predictions_c3.csv"), "x",
                      newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(F2_REF_HEADER))
                w.writeheader()
                for r, p in zip(dev_rows, mu):
                    w.writerow({"model": "hgb", "panel": panel_col,
                                "cell_id": r["cell_id"], "arm": r["arm"],
                                "query_epoch": repr(r["q"]),
                                "forecast_h_weeks": repr(r["h"]),
                                "target_capacity_ah": repr(r["y"]),
                                "predicted_capacity_ah": float(p),
                                "sigma_oof_ah": sig,
                                "error_ah": float(p - r["y"]),
                                "abs_error_ah": abs(float(p - r["y"]))})
        fit_report = {
            "entry_point": "hybrid_aug.py",
            "seed": SEED, "device": DEVICE, "threads": THREADS,
            "fits_in_this_go": FITS_IN_GO,
            "fits": ledger.records,
            "hyperparams": {"hgb": FROZEN_HGB_CONFIG},
            "sigma_source": SIGMA_SOURCE,
            "models": {
                BASE_NAME: {"panel_col": PANEL_COL_BASE,
                            "n_features": int(X_A_tr.shape[1]),
                            "feature_layout": "F2 cache %d + h" % F2_CACHE_DIM,
                            "sigma_oof_ah": sig_A,
                            "n_train_rows": int(len(y_tr)),
                            "n_train_cells": int(len(set(tr_cells)))},
                HYB_NAME: {"panel_col": PANEL_COL_HYB,
                           "n_features": int(X_B_tr.shape[1]),
                           "feature_layout": "F2 cache %d + h + 9 "
                                             "mechanistic" % F2_CACHE_DIM,
                           "state_features": list(HYB_STATE_FEATURES),
                           "sigma_oof_ah": sig_B,
                           "n_train_rows": int(len(y_tr)),
                           "n_train_cells": int(len(set(tr_cells)))}},
            "oof_folds": folds,
            "input_sha256": {k: go["assets"][k]["sha256"]
                             for k in ASSET_KEYS},
            "checkpoint": {k: go["checkpoint"][k] for k in ("path",
                                                            "sha256")},
        }
        atomic_json(os.path.join(out_dir, "fit_report.json"), fit_report)
        summary = {
            "schema": "HYBRID_F2_A3STATE_V1",
            "panel": {"n_keys": len(dkeys),
                      "n_cells": len({k[0] for k in dkeys}),
                      "by_arm": {arm: sum(1 for k in dkeys if k[1] == arm)
                                 for arm in ARMS}},
            "join": {"train": train_join, "development": dev_join,
                     "c3_overlap": cross["n_common"],
                     "c3_only_keys_not_in_panel": c3_only,
                     "c3_crosscheck_max_abs_diff": cross["max_abs_diff"],
                     "f2_cache": {s: {"n_rows": cache[s]["n"],
                                      "n_nan": cache[s]["n_nan"],
                                      "n_nan_rows": cache[s]["n_nan_rows"]}
                                  for s in ("train", "development")}},
            "metrics": metrics,
            "replication_gate": gate,
            "paired_bootstrap_full_panel": boot_full,
            "paired_bootstrap_a3_common_panel": {
                "n_keys": len(common3), "rows": boot_a3},
            "dev_walker_reads": dev_reads,
            "fits": ledger.completed,
            "optimizer_steps_a3": 0,
            "payload_reads": stats.snapshot(),
        }
        atomic_json(os.path.join(out_dir, "compare_summary.json"), summary)
        rec.update(status="COMPLETE_6_FITS", fits=ledger.completed,
                   fits_started=ledger.started,
                   baseline_mae=mA,
                   hybrid_mae=metrics[HYB_NAME]["all"]["MAE_Ah"],
                   gate_pass=True, payload_reads=stats.snapshot(),
                   elapsed_seconds=time.time() - t0,
                   finished_utc=utc_now_iso())
        atomic_json(os.path.join(out_dir, "receipt.json"), rec)
        ext.register_consumed_go(registry, rid, ext.sha256_file(go_path),
                                 utc_now_iso())
        rec["registered"] = True
        atomic_json(os.path.join(out_dir, "receipt.json"), rec)
    except BaseException as exc:  # noqa: BLE001 - receipt discipline
        rec.update(status="FAILED", error=repr(exc),
                   traceback=traceback.format_exc(),
                   elapsed_seconds=time.time() - t0,
                   finished_utc=utc_now_iso())
        if out_dir is not None and os.path.isdir(out_dir):
            atomic_json(os.path.join(out_dir, "receipt.json"), rec)
    finally:
        for f in reversed(locks):
            try:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_UN)
                f.close()
            except Exception:  # noqa: BLE001
                pass
        if receipt_path is not None:
            os.makedirs(os.path.dirname(receipt_path), exist_ok=True)
            if os.path.exists(receipt_path):
                receipt_path = receipt_path + "_" + str(time.time_ns()) + \
                    ".failure.json"
            with open(receipt_path, "x", encoding="utf-8") as f:
                json.dump(rec, f, indent=2, ensure_ascii=False,
                          allow_nan=True)
    return rec


# ============================================================== self-check
def _rename_dev_cells(world):
    """Rename synthetic dev cells to real *C3 ids and rebuild the dev-side
    manifests in the production directory layout (what a2_infer
    ._build_dev_specs demands).  Pure fixture surgery inside the tempdir."""
    # e.g. X04C1 -> X040C3, X04C2 -> X041C3, X05C1 -> X050C3 (endswith C3,
    # unique; _build_dev_specs refuses non-C3 dev ids by contract)
    rename = {cid: cid[:-2] + str(i) + "C3"
              for i, cid in enumerate(sorted(world["dev"]))}
    import gzip as _gz
    tmp = world["tmp"]
    cells = {}
    for cid, cell in world["cells"].items():
        if cid in rename:
            cell = dict(cell)
            cell["cell_id"] = rename[cid]
        cells[cell["cell_id"]] = cell
    world["cells"] = cells
    world["dev"] = [rename[c] for c in world["dev"]]

    def _write(path, payload):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    rpt_root = os.path.join(tmp, DEV_RPT_ROOT_REL)
    os.makedirs(rpt_root, exist_ok=True)
    inv = []
    for cid, cell in sorted(world["cells"].items()):
        old = _orig_id(rename, cid) if cid in rename.values() else cid
        src = os.path.join(world["rpt_dir"], old + ".json")
        doc = json.load(open(src, "r", encoding="utf-8"))
        doc["cell_id"] = cid
        dst = os.path.join(rpt_root, cid + ".json")
        _write(dst, doc)
        inv.append({"cell_id": cid, "role": cell["role"],
                    "path": "%s/%s.json" % (DEV_RPT_ROOT_REL, cid),
                    "sha256": ext.sha256_file(dst),
                    "records": len(doc["records"])})
    inv.sort(key=lambda e: e["cell_id"])
    rpt_manifest = {
        "status": "ALL188_FEATURE_CACHE_COMPLETE", "cells": len(inv),
        "train": sum(1 for e in inv if e["role"] == "train"),
        "development": sum(1 for e in inv if e["role"] == "development"),
        "locked": 0, "inventory": inv}
    rpt_manifest_path = os.path.join(rpt_root, "manifest.json")
    _write(rpt_manifest_path, rpt_manifest)

    proc_root = os.path.join(tmp, DEV_PROCESSED_REL)
    files_map = {}
    for old, new in sorted(rename.items()):
        src = os.path.join(os.path.dirname(world["data_manifest"]),
                           "processed", old + ".json")
        payload = json.load(open(src, "r", encoding="utf-8"))
        payload["cell_id"] = new
        dst = os.path.join(proc_root, new + ".json")
        _write(dst, payload)
        files_map[new] = {"role": "development",
                          "path": "%s/%s.json" % (DEV_PROCESSED_REL, new),
                          "sha256": ext.sha256_file(dst)}
    # the data-manifest set check requires the train cells too (paths of
    # train entries are never opened by _build_dev_specs)
    for cid in world["train"]:
        files_map[cid] = {"role": "train",
                          "path": "%s/%s.json" % (DEV_PROCESSED_REL, cid),
                          "sha256": "0" * 64}
    data_manifest = {"status": "PASS", "files": files_map,
                     "role_counts": {"development": len(rename),
                                     "train": len(world["train"]),
                                     "locked": 0},
                     "constraints": {"raw_curves_read": False,
                                     "locked_payloads_read": False}}
    dm_path = os.path.join(tmp, "reports/isu_ilcc_datav2_full_20261020_root",
                           "data_manifest.json")
    _write(dm_path, data_manifest)

    cyc_root = os.path.join(tmp, DEV_CYCLING_ROOT_REL, "cycling_features_v3")
    os.makedirs(cyc_root, exist_ok=True)
    cyc_inv = []
    for old, new in sorted(rename.items()):
        src = os.path.join(os.path.dirname(world["cycling_manifest"]),
                           "cycling_features_v3", old + ".json.gz")
        doc = json.loads(_gz.decompress(open(src, "rb").read())
                         .decode("utf-8"))
        doc["cell_id"] = new
        dst = os.path.join(cyc_root, new + ".json.gz")
        with open(dst, "wb") as f:
            f.write(_gz.compress(json.dumps(doc).encode("utf-8")))
        cyc_inv.append({"cell_id": new, "role": "development",
                        "path": "%s/cycling_features_v3/%s.json.gz"
                                % (DEV_CYCLING_ROOT_REL, new),
                        "sha256": ext.sha256_file(dst),
                        "cycles": len(doc["cycles"])})
    cyc_inv.sort(key=lambda e: e["cell_id"])
    cm_path = os.path.join(tmp, DEV_CYCLING_ROOT_REL,
                           "cycling_all188_feature_manifest.json")
    _write(cm_path, {"status": "SUCCESS",
                     "development": len(cyc_inv), "C4": 0,
                     "inventory": cyc_inv})

    cohort = {"status": "FROZEN_BEFORE_ANY_CAPACITY_PAYLOAD",
              "roles": {cid: cell["role"]
                        for cid, cell in sorted(world["cells"].items())},
              "counts": {"train": len(world["train"]),
                         "development": len(world["dev"])}}
    co_path = os.path.join(tmp, "reports/isu_ilcc_capacity_probe_"
                               "20261020_root", "cohort.json")
    _write(co_path, cohort)
    world.update({"rpt_manifest": rpt_manifest_path, "data_manifest": dm_path,
                  "cycling_manifest": cm_path, "cohort": co_path})
    return world


def _orig_id(rename, new):
    for old, n in rename.items():
        if n == new:
            return old
    raise KeyError(new)


def _synth_hybrid_world(tmp):
    """ext._synth_world + real-layout dev tree + F2 cache + F2 ref CSV
    (original = an aligned HGB final fit, so the replication gate is exact)
    + 3-seed C3 sub-grid CSVs + checkpoint."""
    world = _rename_dev_cells(ext._synth_world(tmp))
    rng = np.random.default_rng(20261024)
    torch.manual_seed(3)
    ckpt_model = build_arm_model("full", seed=3)
    ckpt_path = os.path.join(tmp, "model_state_dict_full.pt")
    torch.save(ckpt_model.state_dict(), ckpt_path)
    world["checkpoint"] = ckpt_path
    model = ckpt_model.double().eval()

    # ---- grids via the frozen ext rule over train + dev cells -----------
    def grid(cells):
        rows_out = []
        for cid in cells:
            cell = world["cells"][cid]
            rows = [{"idx": r["idx"], "stop": r["stop"], "cap": r["cap"]}
                    for r in cell["rpts"]]
            for q in ext.derive_cell_queries(rows):
                rows_out.append({"cell_id": cid, "arm": q["arm"],
                                 "q": q["q"], "h": q["h"], "y": q["y"]})
        return rows_out

    train_grid = grid(world["train"])
    dev_grid = grid(world["dev"])
    # dev panel order = run_go's build_dev_rows order (cell, arm, q)
    dev_grid_sorted = []
    by_cell = {}
    for r in dev_grid:
        by_cell.setdefault((r["cell_id"], r["arm"]), []).append(r)
    for cid in sorted({r["cell_id"] for r in dev_grid}):
        for arm in ARMS:
            dev_grid_sorted.extend(sorted(
                by_cell.get((cid, arm), []), key=lambda r: r["q"]))
    world["train_grid"] = train_grid
    world["dev_grid"] = dev_grid_sorted
    grid_by_key = {panel_key(r["cell_id"], r["arm"], r["q"], r["h"]): r
                   for r in dev_grid_sorted}

    # ---- F2 cache (98-dim; col 0 carries the target signal) -------------
    cache = os.path.join(tmp, "run2_clocksafe_synth")
    os.makedirs(cache, exist_ok=True)
    for split, g in (("train", train_grid), ("development", dev_grid)):
        meta, feats = [], []
        for r in g:
            meta.append({"cell_id": r["cell_id"], "arm": r["arm"],
                         "query_epoch": r["q"], "idx": len(meta)})
            v = rng.standard_normal(F2_CACHE_DIM) * 0.01
            v[0] = r["y"] + 0.002 * rng.standard_normal()
            feats.append(v)
        # the frozen real cache carries a few NaNs (12 train / 6 dev) which
        # HGB handles natively; mirror that here
        for pos in ((2, 5), (9, 40)) if split == "train" else ((1, 3),):
            feats[pos[0]][pos[1]] = float("nan")
        with open(os.path.join(cache, split + "_rows.jsonl"), "w",
                  encoding="utf-8") as f:
            for m in meta:
                f.write(json.dumps(m) + "\n")
        np.savez(os.path.join(cache, split + "_features.npz"),
                 F2=np.asarray(feats, float))
    with open(os.path.join(cache, "feature_schema.json"), "w",
              encoding="utf-8") as f:
        json.dump({"synthetic": True, "dimensions": {"F2": F2_CACHE_DIM}},
                  f)
    world["cache"] = cache

    # ---- F2 original reference CSV = aligned HGB final-fit predictions --
    # replicate build_train_rows row order exactly (cell, arm, q) so the
    # synthetic "original" final fit is bit-identical to model A's final
    # fit and the replication gate closes at rel_diff ~ 0.
    def _cache_keys(split):
        out = {}
        with open(os.path.join(cache, split + "_rows.jsonl"),
                  encoding="utf-8") as f:
            for i, line in enumerate(l for l in f if l.strip()):
                m = json.loads(line)
                out[cache_key(m["cell_id"], m["arm"],
                              m["query_epoch"])] = i
        return out

    ordered_train = []
    for cid in sorted(world["train"]):
        rows = [{"idx": r["idx"], "stop": r["stop"], "cap": r["cap"]}
                for r in world["cells"][cid]["rpts"]]
        for arm in ARMS:
            qs = sorted((q for q in ext.derive_cell_queries(rows)
                         if q["arm"] == arm), key=lambda q: q["q"])
            ordered_train.extend(
                {"cell_id": cid, "arm": arm, "q": q["q"], "h": q["h"],
                 "y": q["y"]} for q in qs)
    tby = _cache_keys("train")
    tr_mat = np.load(os.path.join(cache, "train_features.npz"))["F2"]
    Xo = np.column_stack((
        tr_mat[[tby[cache_key(r["cell_id"], r["arm"], r["q"])]
                for r in ordered_train]].astype(float),
        [r["h"] for r in ordered_train]))
    yo = np.asarray([r["y"] for r in ordered_train])
    wo = cell_weights([r["cell_id"] for r in ordered_train])
    orig_model = _fit_hgb(Xo, yo, wo)
    dby = _cache_keys("development")
    dv_mat = np.load(os.path.join(cache, "development_features.npz"))["F2"]
    Xd = np.column_stack((
        dv_mat[[dby[cache_key(r["cell_id"], r["arm"], r["q"])]
                for r in dev_grid_sorted]].astype(float),
        [r["h"] for r in dev_grid_sorted]))
    mu_orig = orig_model.predict(Xd)
    f2_ref = os.path.join(tmp, "f2_original_predictions_c3.csv")
    with open(f2_ref, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(F2_REF_HEADER))
        w.writeheader()
        for r, p in zip(dev_grid_sorted, mu_orig):
            w.writerow({"model": "hgb", "panel": "F2",
                        "cell_id": r["cell_id"], "arm": r["arm"],
                        "query_epoch": repr(r["q"]),
                        "forecast_h_weeks": repr(r["h"]),
                        "target_capacity_ah": repr(r["y"]),
                        "predicted_capacity_ah": repr(float(p)),
                        "sigma_oof_ah": "0.011",
                        "error_ah": repr(float(p) - r["y"]),
                        "abs_error_ah": repr(abs(float(p) - r["y"]))})
    world["f2_ref"] = f2_ref

    # ---- dev specs + C3 sub-grid rows (walker; a2 build_queries rule) ---
    stats = a2_infer.ReadStats()
    store = ext.Store([tmp], ext.ReadStats(), base=tmp)
    man_paths = {k: world[k] for k in ("cohort", "data_manifest",
                                       "cycling_manifest", "rpt_manifest")}
    spec_map = build_dev_specs(store, man_paths, len(world["dev"]))
    c3_paths = {}
    for tag, sd_model in (("42", model),
                          ("43", build_arm_model("full", seed=4)
                           .double().eval()),
                          ("44", build_arm_model("full", seed=5)
                           .double().eval())):
        path = os.path.join(tmp, "c3_seed%s.csv" % tag)
        rows = []
        for cid in world["dev"]:
            cell = load_cell(spec_map[cid], stats)
            for arm in ARMS:
                policy = _b2_arm_records(cell["rows"], 1, arm)
                queries, _sk, why = build_queries(cell, arm, policy)
                assert why is None, why
                qd = [{"key": panel_key(cid, arm, q["query_epoch"],
                                        q["gap_weeks"]),
                       "q": q["query_epoch"], "h": q["gap_weeks"],
                       "y": q["target_capacity_ah"]}
                      for q in queries
                      if q["gap_weeks"] is not None and panel_key(
                          cid, arm, q["query_epoch"], q["gap_weeks"])
                      in grid_by_key]
                if not qd:
                    continue
                vis = [min(float(r["capacityAh"]) for r in policy
                           if float(r["arrival_epoch"]) <= qq["q"] + 1e-9)
                       for qq in qd]
                rpts_arm = _rpt_records_for_arm(cell["rpts"], policy)
                seq = a2_prep_cell_sequence(cid, cell["cycles"], rpts_arm)
                lag = DELAY7D_SECONDS if arm == "delay7d" else 0.0
                rows.extend(walker_feature_rows(sd_model, seq, qd, lag,
                                                vis))
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(C3_NEED_COLUMNS),
                               extrasaction="ignore")
            w.writeheader()
            for r in rows:
                rec = dict(r)
                rec.update({"model_key": "full", "model_arm": "A3_full",
                            "target_available": "1",
                            "target_capacity_ah": repr(r["y"]),
                            "query_epoch": repr(r["q"]),
                            "gap_weeks": repr(r["h"]),
                            "pred_var_ah2": r["pred_sd_ah"] ** 2})
                w.writerow(rec)
                decoy = dict(rec)
                decoy.update({"model_key": "time", "model_arm": "A3_time",
                              "pred_mean_ah": "0.1"})
                w.writerow(decoy)
        c3_paths[tag] = path
    world.update({"c3_42": c3_paths["42"], "c3_43": c3_paths["43"],
                  "c3_44": c3_paths["44"]})
    world["runs"] = os.path.join(tmp, "runs")
    world["receipts"] = os.path.join(tmp, "receipts")
    return world


def _asset_paths(world):
    return {"prep_manifest": world["prep_manifest"],
            "prep_npz": world["prep_npz"],
            "rpt_manifest": world["rpt_manifest"],
            "cohort": world["cohort"],
            "data_manifest": world["data_manifest"],
            "cycling_manifest": world["cycling_manifest"],
            "checkpoint": world["checkpoint"],
            "f2_train_features_npz": os.path.join(
                world["cache"], "train_features.npz"),
            "f2_development_features_npz": os.path.join(
                world["cache"], "development_features.npz"),
            "f2_train_rows": os.path.join(world["cache"],
                                          "train_rows.jsonl"),
            "f2_development_rows": os.path.join(
                world["cache"], "development_rows.jsonl"),
            "f2_feature_schema": os.path.join(world["cache"],
                                              "feature_schema.json"),
            "f2_reference_csv": world["f2_ref"],
            "c3_seed42_csv": world["c3_42"],
            "c3_seed43_csv": world["c3_43"],
            "c3_seed44_csv": world["c3_44"]}


def _valid_hybrid_go(world, request_id="HYBRID_SELFCHECK_0001"):
    paths = _asset_paths(world)
    code = {}
    for name in CODE_PINS:
        d = CODE_PIN_DIRS.get(name)
        if d is None:
            d = _A3_DIR if name.startswith("a3_") else _A2_DIR
        code[name] = ext.sha256_file(os.path.join(d, name))
    n_train = len(world["train_grid"])
    n_dev = len({panel_key(r["cell_id"], r["arm"], r["q"], r["h"])
                 for r in world["dev_grid"]})
    return {
        "status": "APPROVED", "allow_fit": True, "allow_C4": False,
        "scope": "HYBRID TRAIN/FIT: F2 cache + A3 state features, 6 HGB "
                 "fits, 0 C4",
        "request_id": request_id,
        "owner_thread_id": OWNER_THREAD_ID,
        "issued_utc": utc_now_iso().replace("+00:00", "Z"),
        "seed": SEED, "device": DEVICE, "threads": THREADS,
        "max_runtime_seconds": 3600,
        "code_sha256": code,
        "checkpoint": {"path": world["checkpoint"],
                       "sha256": ext.sha256_file(world["checkpoint"])},
        "assets": {k: {"path": p, "sha256": ext.sha256_file(p)}
                   for k, p in paths.items()},
        "panel_contract": {"n_train_queries": n_train, "n_dev_keys": n_dev,
                           "arms": list(ARMS),
                           "n_train_cells": len(world["train"]),
                           "n_dev_specs": len(world["dev"])},
        "model_config": {"hgb": FROZEN_HGB_CONFIG},
        "fits_in_this_go": FITS_IN_GO,
        "replication_gate": {"f2_mae_cell_macro_rel_tol": 0.05},
        "consumed_registry": world["registry"],
        "out_dir": os.path.join(world["runs"], "hybrid_selfcheck_run1"),
        "receipt_path": os.path.join(world["receipts"],
                                     "hybrid_selfcheck_run1.json"),
    }


class _CountingLedger(object):
    def __init__(self):
        self.started = 0

    def run(self, meta, fit_fn):
        self.started += 1
        return fit_fn()


def self_check():
    log_lines = []
    passed = []
    failed = []

    def emit(line):
        print(line)
        log_lines.append(line)

    def check(name, fn):
        emit("[CHECK] %s" % name)
        try:
            detail = fn() or ""
            passed.append(name)
            emit("  -> PASS %s" % detail)
        except Exception as exc:  # noqa: BLE001
            failed.append((name, exc))
            tb = traceback.format_exc().strip().splitlines()
            emit("  -> FAIL %s: %s" % (name, exc))
            for line in tb[-6:]:
                emit("      %s" % line)

    tmp = tempfile.mkdtemp(prefix="hybrid_aug_selfcheck_")
    try:
        world = _synth_hybrid_world(tmp)
        stats = ext.ReadStats()
        store = ext.Store([tmp], stats, base=tmp)
        paths = _asset_paths(world)

        def no_real_reads():
            store.read_bytes(world["f2_ref"], "selfcheck_probe")
            real = [p for p in stats.paths
                    if not p.startswith(os.path.realpath(tmp))]
            assert not real, "self-check opened real assets: %s" % real
            assert stats.paths, "self-check read nothing"
            return "reads=%d, all under tmp" % len(stats.paths)

        # 1 --------------------------------------------------------------
        def chk_world():
            assert len(world["train_grid"]) > 0 and \
                len(world["dev_grid"]) > 0
            assert len(world["train"]) >= 4 and len(world["dev"]) >= 2
            got = set(parse_c3_full(store, world["c3_42"]))
            panel = {panel_key(r["cell_id"], r["arm"], r["q"], r["h"])
                     for r in world["dev_grid"]}
            assert got <= panel and len(got) >= 10, (len(got), len(panel))
            assert len(panel) > len(got), "C3 sub-grid must be sparser"
            return ("train_grid=%d dev_grid=%d c3_sub=%d (proper subset of "
                    "the tree panel, mirrors the real 2326/3579 gap)"
                    % (len(world["train_grid"]), len(world["dev_grid"]),
                       len(got)))
        check("synthetic hybrid world built (train/dev/cache/C3 x3/ckpt)",
              chk_world)

        # 2 --------------------------------------------------------------
        check("no real payload/asset reads (store audit)", no_real_reads)

        # 3 --------------------------------------------------------------
        def chk_recorder():
            """walker_feature_rows == a3_infer._row_for_query semantics."""
            spec_map = build_dev_specs(store, paths, len(world["dev"]))
            cid = world["dev"][0]
            cell = load_cell(spec_map[cid], a2_infer.ReadStats())
            model = build_arm_model("full", seed=3).double().eval()
            n = 0
            worst = [0.0]
            for arm in ARMS:
                policy = _b2_arm_records(cell["rows"], 1, arm)
                queries, _sk, why = build_queries(cell, arm, policy)
                assert why is None
                keep = [q for q in queries if q["gap_weeks"] is not None]
                qd = [{"key": panel_key(cid, arm, q["query_epoch"],
                                        q["gap_weeks"]),
                       "q": q["query_epoch"], "h": q["gap_weeks"],
                       "y": q["target_capacity_ah"]} for q in keep]
                vis = [q["visible_capacity_min_ah"] for q in keep]
                rpts_arm = _rpt_records_for_arm(cell["rpts"], policy)
                seq = a2_prep_cell_sequence(cid, cell["cycles"], rpts_arm)
                lag = DELAY7D_SECONDS if arm == "delay7d" else 0.0
                mine = walker_feature_rows(model, seq, qd, lag, vis)
                for q, r in zip(keep, mine):
                    walker = a3_infer.AsOfWalkerA3(
                        model, seq, lag, a3_infer.MODEL_ARMS["full"])
                    row = a3_infer._row_for_query(
                        cell, arm, q, "full", model,
                        walker.state_at(q["query_epoch"]),
                        float(seq["q_ref_ah"]), seq)
                    # fresh-walker vs monotone-walker states agree to float
                    # association noise only (a3_infer's own walker==ref
                    # gate uses the same 1e-12)
                    for col in ("state_D", "state_ell", "state_R",
                                "state_P00", "state_P11", "state_P22",
                                "pred_mean_ah", "pred_sd_ah",
                                "pred_var_ah2", "qref_ah",
                                "visible_capacity_min_ah"):
                        d = abs(float(row[col]) - float(r[col]))
                        assert d <= 1e-12, (col, row[col], r[col], d)
                        worst[0] = max(worst[0], d)
                    assert row["gap_weeks"] == r["h"]
                    n += 1
            assert n >= 12
            return ("state/pred columns == a3_infer._row_for_query on %d "
                    "queries x %d arms (fresh vs monotone walker, "
                    "max|diff|=%.1e <= 1e-12)" % (n, len(ARMS), worst[0]))
        check("walker state recorder == a3_infer._row_for_query (reuse "
              "proof)", chk_recorder)

        # 4 --------------------------------------------------------------
        def chk_join():
            cache = load_f2_cache(store, paths)
            tidx, tj = join_cache(
                [{"cell_id": r["cell_id"], "arm": r["arm"], "q": r["q"]}
                 for r in world["train_grid"]], cache["train"], "train")
            assert tj["n_missing"] == 0 and len(tidx) == \
                len(world["train_grid"])
            panel_keys, panel_recs = load_f2_reference(store, world["f2_ref"])
            assert len(panel_keys) == len(world["dev_grid"])
            for k in panel_keys:
                assert k in panel_recs
            try:
                join_cache([{"cell_id": "ZZZC9", "arm": "raw",
                             "q": 1.0}], cache["train"], "train")
                raise AssertionError("missing cache row not refused")
            except HybridError as exc:
                assert "1 rows without a cache row" in str(exc)
            return ("train join %d/%d matched, dev ref %d keys, "
                    "missing-row refusal counted"
                    % (tj["n_matched"], tj["n_rows"], len(panel_keys)))
        check("join correctness + key-mismatch counting (cache/ref panels)",
              chk_join)

        # 5 --------------------------------------------------------------
        def chk_leak():
            model = build_arm_model("full", seed=3).double().eval()
            cid = world["train"][0]
            prep = ext.load_prep(store, world["prep_manifest"],
                                 world["prep_npz"])["cells"][cid]
            rows = [{"idx": r["idx"], "stop": r["stop"], "cap": r["cap"]}
                    for r in world["cells"][cid]["rpts"]]
            arm = "raw"
            seq, queries = cal.build_cell_arm(cid, prep, rows, None, arm)
            q = queries[len(queries) // 2]["q"]
            gap = queries[len(queries) // 2]["gap"]
            y = queries[len(queries) // 2]["y"]
            vis = min(rows[i]["cap"] for i in
                      ext.visible_indices(rows, arm, q))
            qd = [{"key": ("k", "raw", round(q, 5), round(gap, 6)),
                   "q": q, "h": gap, "y": y}]
            a = walker_feature_rows(model, seq, qd, 0.0, [vis])
            seq2 = copy.deepcopy(seq)
            for e in seq2["events"]:
                if float(e["source_epoch"]) > q + 1e-9:
                    if e["kind"] == "rpt":
                        e["capacity_ah"] = 0.05
                    else:
                        e["control"] = [9.9] * 24
                        e["control_mask"] = [1.0] * 24
            b = walker_feature_rows(model, seq2, qd, 0.0, [vis])
            for col in ("state_D", "state_ell", "state_R", "state_P00",
                        "state_P11", "state_P22", "pred_mean_ah",
                        "pred_sd_ah"):
                assert a[0][col] == b[0][col], col
            return ("post-query capacity/control perturbation leaves all 8 "
                    "state features bit-identical")
        check("no leakage (future events cannot touch the state features)",
              chk_leak)

        # 6 --------------------------------------------------------------
        def chk_finiteness():
            model = build_arm_model("full", seed=3).double().eval()
            cid = world["train"][0]
            prep = ext.load_prep(store, world["prep_manifest"],
                                 world["prep_npz"])["cells"][cid]
            rows = [{"idx": r["idx"], "stop": r["stop"], "cap": r["cap"]}
                    for r in world["cells"][cid]["rpts"]]
            seq, queries = cal.build_cell_arm(cid, prep, rows, None, "raw")
            q = queries[len(queries) // 2]["q"]
            gap = queries[len(queries) // 2]["gap"]
            y = queries[len(queries) // 2]["y"]
            qd = [{"key": ("k", "raw", round(q, 5), round(gap, 6)),
                   "q": q, "h": gap, "y": y}]
            row = walker_feature_rows(model, seq, qd, 0.0, [0.28])
            assert all(math.isfinite(v) for v in row[0].values()
                       if isinstance(v, float))
            try:  # NaN visible capacity poisons the implied slope -> refuse
                walker_feature_rows(model, seq, qd, 0.0, [float("nan")])
                raise AssertionError("non-finite feature not refused")
            except HybridError:
                pass
            try:  # non-positive gap refused
                walker_feature_rows(model, seq, [dict(qd[0], h=0.0)],
                                    0.0, [0.28])
                raise AssertionError("non-positive gap not refused")
            except HybridError:
                pass
            return "finite-state assertion + NaN-feature and gap<=0 refused"
        check("state-column finiteness guard", chk_finiteness)

        # 7 --------------------------------------------------------------
        def chk_folds_sigma():
            ids = ["c%02d" % i for i in range(9)]
            f1, f2 = two_cell_folds_v18(ids, 42)
            assert f1 | f2 == set(ids) and not (f1 & f2)
            assert len(f1) == 5 and len(f2) == 4
            assert f1 == two_cell_folds_v18(ids, 42)[0], \
                "folds must be deterministic"
            ref = sorted(ids)                     # V18 semantics verbatim
            np.random.RandomState(42).shuffle(ref)
            assert f1 == set(ref[::2]) and f2 == set(ref[1::2])
            got = sigma_from_oof([0.1, 0.3, 0.2], ["c1", "c1", "c2"])
            want = math.sqrt((0.05 + 0.04) / 2)
            assert math.isclose(got, want, rel_tol=1e-15)
            return ("folds == RandomState(42) even/odd split (5/4, "
                    "deterministic); sigma hand case exact %.10f" % got)
        check("OOF folds (V18 tree rule) + sigma formula hand case",
              chk_folds_sigma)

        # 8 --------------------------------------------------------------
        def chk_ens3():
            a = {("c", "raw", 1.0, 2.0): {"mu": 0.30, "sd": 0.01,
                                          "y": 0.29}}
            b = {("c", "raw", 1.0, 2.0): {"mu": 0.32, "sd": 0.02,
                                          "y": 0.29}}
            c = {("c", "raw", 1.0, 2.0): {"mu": 0.34, "sd": 0.01,
                                          "y": 0.29},
                 ("c", "raw", 9.0, 2.0): {"mu": 0.1, "sd": 0.01, "y": 0.1}}
            ens = ens3_moment((a, b, c))
            assert len(ens) == 1
            mu = (0.30 + 0.32 + 0.34) / 3
            var = (0.0001 + 0.09 + 0.0004 + 0.1024 + 0.0001 + 0.1156) \
                / 3 - mu * mu
            e = ens[("c", "raw", 1.0, 2.0)]
            assert math.isclose(e["mu"], mu, rel_tol=1e-12), (e["mu"], mu)
            assert math.isclose(e["sd"], math.sqrt(var), rel_tol=1e-12),                 (e["sd"], math.sqrt(var))
            assert e["y"] == 0.29
            return ("equal-weight mixture moment match exact; key "
                    "intersection honoured")
        check("ENS3 moment-matched mixture (compare_ens3 semantics)",
              chk_ens3)

        # 9 --------------------------------------------------------------
        def chk_cross():
            recs = parse_c3_full(store, world["c3_42"])
            spec_map = build_dev_specs(store, paths, len(world["dev"]))
            cid = world["dev"][0]
            cell = load_cell(spec_map[cid], a2_infer.ReadStats())
            model = build_arm_model("full", seed=3).double().eval()
            arm = "raw"
            policy = _b2_arm_records(cell["rows"], 1, arm)
            qd = [{"key": k, "q": v["q"], "h": v["h"], "y": v["y"]}
                  for k, v in sorted(recs.items())
                  if k[0] == cid and k[1] == arm]
            assert qd, "no C3 rows for the first dev cell/raw arm"
            vis = [min(float(r["capacityAh"]) for r in policy
                       if float(r["arrival_epoch"]) <= q["q"] + 1e-9)
                   for q in qd]
            rpts_arm = _rpt_records_for_arm(cell["rpts"], policy)
            seq = a2_prep_cell_sequence(cid, cell["cycles"], rpts_arm)
            rows = walker_feature_rows(model, seq, qd, 0.0, vis)
            cross = cross_check_c3(rows, recs)
            assert cross["n_common"] == len(rows) and len(rows) >= 3
            assert cross["max_abs_diff"]["state"] == 0.0
            assert cross["max_abs_diff"]["pred_mean"] < 1e-12
            bad = {k: dict(v) for k, v in recs.items()}
            k0 = qd[0]["key"]
            bad[k0] = dict(bad[k0], state_D=bad[k0]["state_D"] + 1e-3)
            try:
                cross_check_c3(rows, bad)
                raise AssertionError("corrupted C3 row not refused")
            except HybridError:
                pass
            return ("recompute == C3 CSV on %d keys (dstate=0 bit-exact, "
                    "dmean<1e-12); corruption refused" % cross["n_common"])
        check("C3 cross-check gate (dev walker vs saved C3, bit-exact)",
              chk_cross)

        # 10 -------------------------------------------------------------
        def chk_determinism():
            rng = np.random.default_rng(7)
            X = rng.standard_normal((200, 6))
            y = X[:, 0] * 0.5 + 0.01 * rng.standard_normal(200)
            cells = ["c%d" % (i % 5) for i in range(200)]
            w = cell_weights(cells)
            la, lb = _CountingLedger(), _CountingLedger()
            dl = time.monotonic() + 600
            ma, sa, oa, fa = fit_model("det", X, y, w, cells, la, dl)
            mb, sb, ob, fb = fit_model("det", X, y, w, cells, lb, dl)
            assert fa == fb and sa == sb
            assert np.array_equal(oa, ob)
            assert np.array_equal(ma.predict(X), mb.predict(X))
            assert la.started == 3 and lb.started == 3
            return ("two independent OOF+final pipelines identical (sigma "
                    "%.8g, OOF and predictions bitwise; 3 fits each)" % sa)
        check("pipeline replication/determinism gate (synthetic side)",
              chk_determinism)

        # 11 -------------------------------------------------------------
        n_refused = [0]

        def chk_go():
            good = _valid_hybrid_go(world)
            gp = os.path.join(tmp, "go_good.json")
            with open(gp, "w", encoding="utf-8") as f:
                json.dump(good, f)
            paths_map = _asset_paths(world)
            _out, _rcp, _reg, rid = validate_go(good, gp, store, paths_map,
                                                world["runs"],
                                                world["receipts"])
            assert rid == good["request_id"]

            def mutate(kind):
                g = copy.deepcopy(good)
                if kind == "status":
                    g["status"] = "PENDING"
                elif kind == "allow_fit_false":
                    g["allow_fit"] = False
                elif kind == "allow_c4":
                    g["allow_C4"] = True
                elif kind == "scope":
                    g["scope"] = "EXT-BASELINE fit GO"
                elif kind == "owner":
                    g["owner_thread_id"] = "deadbeef"
                elif kind == "stale":
                    g["issued_utc"] = "2020-01-01T00:00:00Z"
                elif kind == "seed":
                    g["seed"] = 7
                elif kind == "device":
                    g["device"] = "cuda"
                elif kind == "threads":
                    g["threads"] = 8
                elif kind == "runtime_low":
                    g["max_runtime_seconds"] = 10
                elif kind == "runtime_high":
                    g["max_runtime_seconds"] = 10 ** 7
                elif kind == "fits":
                    g["fits_in_this_go"] = 4
                elif kind == "model_config":
                    g["model_config"] = {"hgb": {"max_iter": 50}}
                elif kind == "gate_tol":
                    g["replication_gate"] = {
                        "f2_mae_cell_macro_rel_tol": 0.5}
                elif kind == "code_sha":
                    g["code_sha256"]["hybrid_aug.py"] = "0" * 64
                elif kind == "code_set":
                    g["code_sha256"]["bogus.py"] = "1" * 64
                elif kind == "ckpt_sha":
                    g["checkpoint"]["sha256"] = "0" * 64
                elif kind == "ckpt_path":
                    g["checkpoint"]["path"] = os.path.join(tmp, "other.pt")
                elif kind == "asset_sha":
                    g["assets"]["f2_train_features_npz"]["sha256"] = \
                        "0" * 64
                elif kind == "asset_path":
                    g["assets"]["c3_seed42_csv"]["path"] = os.path.join(
                        tmp, "elsewhere.csv")
                elif kind == "asset_missing":
                    del g["assets"]["cohort"]
                elif kind == "arms_wrong":
                    g["panel_contract"]["arms"] = ["raw"]
                elif kind == "issued_bad":
                    g["issued_utc"] = "not-a-timestamp"
                elif kind == "consumed_rid":
                    g["request_id"] = "ALREADY_CONSUMED_RID"
                    ext.register_consumed_go(good["consumed_registry"],
                                             "ALREADY_CONSUMED_RID",
                                             "b" * 64, utc_now_iso())
                elif kind == "out_dir_exists":
                    os.makedirs(g["out_dir"], exist_ok=True)
                elif kind == "receipt_exists":
                    os.makedirs(os.path.dirname(g["receipt_path"]),
                                exist_ok=True)
                    with open(g["receipt_path"], "w") as f:
                        f.write("x")
                elif kind == "missing_field":
                    del g["request_id"]
                else:
                    raise AssertionError("unknown mutation " + kind)
                mp = os.path.join(tmp, "go_mut_%s.json" % kind)
                with open(mp, "w", encoding="utf-8") as f:
                    json.dump(g, f)
                try:
                    validate_go(g, mp, store, paths_map, world["runs"],
                                world["receipts"])
                    raise AssertionError("mutation %s NOT refused" % kind)
                except (HybridError, ext.ExtBaselineError):
                    n_refused[0] += 1
                finally:
                    shutil.rmtree(g["out_dir"], ignore_errors=True)
                    if os.path.exists(g["receipt_path"]):
                        os.remove(g["receipt_path"])

            for kind in ("status", "allow_fit_false", "allow_c4", "scope",
                         "owner", "stale", "seed", "device", "threads",
                         "runtime_low", "runtime_high", "fits",
                         "model_config", "gate_tol", "code_sha", "code_set",
                         "ckpt_sha", "ckpt_path", "asset_sha", "asset_path",
                         "asset_missing", "arms_wrong", "issued_bad",
                         "consumed_rid", "out_dir_exists", "receipt_exists",
                         "missing_field"):
                mutate(kind)
            assert n_refused[0] >= 12, "only %d refused" % n_refused[0]
            return "valid GO accepted; %d/27 mutations refused" \
                % n_refused[0]
        check("GO validator (allow_fit/C4/scope/fits/gate; >=12 mutations)",
              chk_go)

        # 12 -------------------------------------------------------------
        def chk_registry():
            reg = os.path.join(tmp, "registry_test.jsonl")
            ext.register_consumed_go(reg, "RID_TEST_1", "a" * 64,
                                     utc_now_iso())
            assert ext.request_id_is_fresh("RID_TEST_2", reg)
            assert not ext.request_id_is_fresh("RID_TEST_1", reg)
            try:
                ext.register_consumed_go(reg, "RID_TEST_1", "a" * 64,
                                         utc_now_iso())
                raise AssertionError("duplicate not refused")
            except RuntimeError:
                pass
            return "append once + duplicate refused (tmp registry only)"
        check("registry append/duplicate-refusal (isolated tmp)",
              chk_registry)

        # 13 -------------------------------------------------------------
        def chk_bootstrap():
            keys = [("c%d" % i, "raw", float(j), 1.0)
                    for i in range(6) for j in range(4)]
            mu1 = np.full(len(keys), 0.282)
            mu2 = np.full(len(keys), 0.28)
            sd = np.full(len(keys), 0.01)
            y = np.full(len(keys), 0.28)
            rows = paired_bootstrap(keys, {"A": (mu1, sd), "B": (mu2, sd),
                                           "_y": y})
            hits = [r for r in rows if r["scope"] == "all"
                    and r["metric"] == "MAE_Ah" and r["candidate"] == "B"
                    and r["reference"] == "A"]
            assert hits, rows[:2]
            r = hits[0]
            assert math.isclose(r["delta"], -0.002, rel_tol=1e-9)
            assert r["ci_low"] <= r["delta"] <= r["ci_high"]
            assert r["cells"] == 6 and r["draws"] == BOOTSTRAP_DRAWS
            again = paired_bootstrap(keys, {"A": (mu1, sd), "B": (mu2, sd),
                                            "_y": y})
            assert again == rows, "bootstrap must be seed-deterministic"
            return ("hand delta -0.002 exact (all-scope MAE); 95%% CI "
                    "brackets; seed-deterministic; %d rows" % len(rows))
        check("paired cell bootstrap semantics + determinism", chk_bootstrap)

        # 14 -------------------------------------------------------------
        def chk_run():
            good = _valid_hybrid_go(world,
                                    request_id="HYBRID_SELFCHECK_0002")
            gp = os.path.join(tmp, "go_run.json")
            with open(gp, "w", encoding="utf-8") as f:
                json.dump(good, f)
            r = run_go(gp, store=store, runs_parent=world["runs"],
                       receipts_parent=world["receipts"], use_locks=False,
                       expected_asset_paths=_asset_paths(world))
            assert r.get("status") == "COMPLETE_6_FITS", r.get("error")
            assert r.get("fits") == FITS_IN_GO and r.get("registered")
            assert r.get("gate_pass") is True
            out_dir = good["out_dir"]
            for name, col in ((BASE_NAME, PANEL_COL_BASE),
                              (HYB_NAME, PANEL_COL_HYB)):
                p = os.path.join(out_dir, name, "predictions_c3.csv")
                with open(p, newline="") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    hdr = list(reader.fieldnames or ())
                assert hdr == F2_REF_HEADER, hdr
                assert len(rows) == len(world["dev_grid"])
                assert {x["panel"] for x in rows} == {col}
                assert {x["model"] for x in rows} == {"hgb"}
            s = json.load(open(os.path.join(out_dir,
                                            "compare_summary.json")))
            assert s["join"]["train"]["n_missing"] == 0
            assert s["join"]["development"]["n_missing"] == 0
            assert s["join"]["c3_overlap"] >= 10
            # full-grid walker vs C3 sub-grid walk agree to float batching
            # noise only (the run gate itself refuses beyond 1e-9)
            assert s["join"]["c3_crosscheck_max_abs_diff"]["state"] < 1e-12
            assert s["join"]["c3_crosscheck_max_abs_diff"]["pred_mean"] \
                < 1e-9
            assert s["replication_gate"]["pass"] is True
            assert s["replication_gate"]["rel_diff"] <= 1e-9
            full = s["paired_bootstrap_full_panel"]
            assert any(x["candidate"] == HYB_NAME and
                       x["reference"] == BASE_NAME for x in full)
            assert any(x["reference"] == "F2_hgb_original" for x in full)
            a3p = s["paired_bootstrap_a3_common_panel"]["rows"]
            assert any(x["reference"] == "A3_full" for x in a3p)
            assert any(x["reference"] == "ENS3" for x in a3p)
            assert not ext.request_id_is_fresh(good["request_id"],
                                               world["registry"])
            fr = json.load(open(os.path.join(out_dir, "fit_report.json")))
            assert len(fr["fits"]) == FITS_IN_GO
            return ("status=%s fits=%d train_join=%d dev_join=%d "
                    "c3_overlap=%d gate_rel_diff=%.2e bootstrap rows=%d/%d"
                    % (r["status"], r["fits"], s["join"]["train"]["n_rows"],
                       s["join"]["development"]["n_rows"],
                       s["join"]["c3_overlap"],
                       s["replication_gate"]["rel_diff"], len(full),
                       len(a3p)))
        check("full guarded run on synthetic world (6 fits, outputs, "
              "registration)", chk_run)

        # 15 -------------------------------------------------------------
        check("no real payload/asset reads after full run", no_real_reads)

        total = len(passed) + len(failed)
        result = "RESULT: self_check total=%d passed=%d failed=%d" % (
            total, len(passed), len(failed))
        emit("")
        emit(result)
        for name, exc in failed:
            emit("FAILED: %s: %s" % (name, exc))
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("\n===== hybrid_aug self-check run %s =====\n"
                    % utc_now_iso())
            f.write("\n".join(log_lines) + "\n")
        return 0 if not failed else 2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="HYBRID: HGB on F2 cache + A3 mechanistic state "
                    "features. Synthetic self-check by default; guarded "
                    "6-fit run with --run-train --go GO.json")
    p.add_argument("--self-check", action="store_true",
                   help="synthetic fixtures only (default behaviour)")
    p.add_argument("--run-train", action="store_true",
                   help="guarded real run (6 HGB fits); requires --go")
    p.add_argument("--go", default=None,
                   help="path to an APPROVED, unconsumed GO json")
    args = p.parse_args(argv)
    if args.run_train:
        if not args.go:
            print("--run-train requires --go GO.json", file=sys.stderr)
            return 2
        rec = run_go(args.go)
        print(json.dumps(rec, indent=2, ensure_ascii=False, allow_nan=True))
        return 0 if rec.get("status") == "COMPLETE_6_FITS" else 2
    return self_check()


if __name__ == "__main__":
    sys.exit(main())
