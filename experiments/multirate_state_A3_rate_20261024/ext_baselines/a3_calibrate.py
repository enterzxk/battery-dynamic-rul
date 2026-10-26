#!/home/yndx/miniconda3/envs/a40_env/bin/python3.9
"""A3 variance calibration (P2/V3): training-internal closed-form factor s,
C3 recalibrated re-evaluation and schedule-frontier re-evaluation.

Science question (R3 finding)
-----------------------------
The A3_full risk schedule at nominal alpha=5% actually violates ~19% (4x):
the predicted Gaussian variance is systematically too small (normal
approximation + model misspecification).  Fix = ONE closed-form variance
scaling factor s estimated INSIDE the training panel, never tuned on C3:

    s = sum_i (y_i - mu_i)^2 / sum_i v_i        (classic variance-scaling MLE)

where (mu_i, v_i, y_i) are the A3_full walker's forecast mean, total forecast
variance and the realised next-source-RPT capacity at the SAME nextcapacity
task used by the tree baselines, over the 6498 training-panel as-of queries
(125 train cells x arms raw/sparse2/delay7d, ext_baselines frozen rule).
0 optimiser steps, 0 fits, 0 C3/C4 reads at estimation time.

Data path (real run; everything GO-pinned, sha-verified, Store-audited)
----------------------------------------------------------------------
* Training panel: ext_baselines' verified derivation (PREP v2 npz cycles +
  all188 RPT feature assets; cross-checked; 6498 keys reproduced the tree
  run2 receipt exactly).  Arm sequences are built with the frozen B2 rule
  (a2_infer._b2_arm_records semantics; parity on ORIGINAL source_rpt_index,
  delay7d arrival = stop + 7d) and filtered with a3_infer's own
  AsOfWalkerA3 (the exact segment engine used for C3 inference) in float64,
  no_grad, streaming O(events + queries).  Forecast = a3_infer
  ._advance_horizon over gap weeks with the held-recent-control policy --
  the exact computation behind the C3 CSV's pred_mean_ah / pred_var_ah2.
* C3 re-evaluation (saved predictions + s only): c3_eval_a3_20261024_run2/
  predictions_c3_a3.csv, model_arm == "A3_full" rows.  Calibrated variance
  = s * pred_var_ah2 (and s * h{tag}_var_ah2); means unchanged.  Recomputes
  Gaussian NLL / coverage; integrity gate: with s=1 the recomputation must
  reproduce the CSV's own nll_per_ah / covered_* columns.
* Schedule re-evaluation: risk policies alpha in {0.02, 0.05, 0.10} with
  sd_cal = sqrt(s) * sd (schedule_eval semantics copied verbatim:
  largest menu h with Phi((EOL - mean)/sd) <= alpha, else h=1, else min;
  violation = truth < EOL; pooled + cell-macro rates; arm "all" = pooled
  points).  BEFORE (s=1) is cross-checked cell-exactly against the pinned
  R3 policy_table.csv (run_schedule_eval_20261024) A3_full risk rows --
  any mismatch refuses the run.  AFTER uses the calibrated sd.
* Honest report: if the calibrated alpha=5% cell-macro violation rate of the
  pooled "all" arm is still > 10%, the report says so verbatim
  (TRAIN_CALIBRATION_INSUFFICIENT) and attaches evidence (per-arm s,
  residual-variance scatter bins).

GO discipline
-------------
Default (no arguments) = synthetic self-check: a full synthetic world in a
tempdir (own PREP/RPT/tree CSV/checkpoint/C3 CSV/policy table), 0 real
asset reads, 0 real GO created/consumed, 0 registry writes outside the
tempdir.  --run-calibrate requires an APPROVED GO with allow_fit FALSE
(inference only), scope containing CALIBRATE, a fresh request_id (consumed
registry + burned list), code pins = the exact import closure (see
CODE_PINS; note the A3 tree has NO a3_targets.py -- A3 reuses
a2_targets.py; a2_fastdata.py IS pinned, it is imported by a3_model/
a3_train), checkpoint path+sha, asset path+sha pins (schedule_dir pinned
by a canonical directory digest), a fresh out_dir/receipt_path.  A refused
GO writes nothing; after full success the request_id is registered
(append-once).  This worker never creates, signs or self-approves a GO.
"""
from __future__ import annotations

import os
if os.environ.get("EXT_BASELINE_NO_THREADSET") != "1":
    for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ.setdefault(_v, "4")

import argparse
import copy
import csv
import datetime as _dt
import hashlib
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
_A3_DIR = os.path.dirname(HERE)                    # multirate_state_A3_rate_20261024
_A2_DIR = os.path.join(os.path.dirname(_A3_DIR), "multirate_state_A2_20261022")
if not os.path.isdir(_A3_DIR) or not os.path.isdir(_A2_DIR):
    _A3_DIR = os.path.join("/home/yndx/zxk/rul", "experiments",
                           "multirate_state_A3_rate_20261024")
    _A2_DIR = os.path.join("/home/yndx/zxk/rul", "experiments",
                           "multirate_state_A2_20261022")
for _p in (HERE, _A3_DIR, _A2_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ext_baselines as ext  # frozen panel rule / Store / registry discipline

from a2_infer import DELAY7D_SECONDS, _b2_arm_records  # frozen B2 arm rule
from a2_prep import cell_sequence                       # frozen A2 sequence
import a3_infer                                         # walker + forecast
from a3_model import build_arm_model                    # checkpoint binding

SEED = 42
WEEK = ext.WEEK
ARMS = ext.ARMS
OWNER_THREAD_ID = ext.OWNER_THREAD_ID
MODEL_KEY = "full"
MODEL_LABEL = "A3_full"
EOL_AH = 0.20
MENU_WEEKS = (1.0, 4.0, 12.0, 32.0)
ALPHAS = (0.02, 0.05, 0.10)
Z50 = 0.6744897501960817
Z90 = 1.6448536269514722
Z95 = 1.959963984540054
LOG_2PI = math.log(2.0 * math.pi)
S_DEFINITION = (
    "s = sum((y - pred_mean)^2) / sum(pred_var_total) over ALL training-panel "
    "rows (6498 as-of queries, 125 train cells, arms raw/sparse2/delay7d, "
    "A3_full walker forecast to the next source RPT stop under the "
    "held-recent-control policy); classic variance-scaling MLE under "
    "N(mean, s*var); estimated inside the training panel only, never on C3")
N_VARIANCE_BINS = 10
HONEST_THRESHOLD = 0.10   # calibrated alpha=5% cell-macro violation above this -> flag
BURNED_REQUEST_IDS = tuple(ext.BURNED_REQUEST_IDS)

GO_REQUIRED = ("status", "allow_fit", "scope", "request_id", "owner_thread_id",
               "issued_utc", "seed", "device", "threads",
               "max_runtime_seconds", "code_sha256", "checkpoint", "assets",
               "panel_contract", "s_definition", "eol_threshold_ah",
               "menu_weeks", "alphas", "consumed_registry", "output_dir",
               "receipt_path")
CODE_PINS = ("a3_calibrate.py", "ext_baselines.py", "a3_infer.py",
             "a3_model.py", "a3_train.py", "a2_infer.py", "a2_prep.py",
             "a2_targets.py", "a2_model.py", "a2_fastdata.py", "a2_train.py")
ASSET_KEYS = ("prep_manifest", "prep_npz", "rpt_manifest", "tree_csv",
              "c3_predictions_csv", "schedule_dir")

C3_NEED_COLUMNS = ("cell_id", "group_id", "arm", "model_key", "model_arm",
                   "query_epoch", "target_capacity_ah", "pred_mean_ah",
                   "pred_latent_var_ah2", "pred_var_ah2", "nll_per_ah",
                   "covered_50", "covered_90", "covered_95")
for _h in MENU_WEEKS:
    tag = ("h%g" % _h).replace(".", "p")
    C3_NEED_COLUMNS += (tag + "_mean_ah", tag + "_sd_ah", tag + "_var_ah2",
                        tag + "_target_capacity_ah")


class CalibrateError(RuntimeError):
    pass


# ------------------------------------------------------------------- helpers
def utc_now_iso():
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def atomic_json(path, payload):
    text = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=True) + "\n"
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def dir_digest(store, path):
    """Canonical directory digest: sha256 over sorted {relpath: sha256}."""
    real = store._allowed(store.resolve(path))  # fail-closed root check
    if not os.path.isdir(real):
        raise CalibrateError("schedule_dir is not a directory: %s" % path)
    entries = {}
    for name in sorted(os.listdir(real)):
        full = os.path.join(real, name)
        if os.path.isfile(full) and not name.endswith(".tmp"):
            entries[name] = hashlib.sha256(
                store.read_bytes(full, "schedule_dir_file")).hexdigest()
    return hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True).encode("utf-8")).hexdigest()


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


def gaussian_nll(y, mean, var):
    if var <= 0:
        raise CalibrateError("non-positive variance in Gaussian NLL")
    z = float(y) - float(mean)
    return 0.5 * (z * z / float(var) + math.log(float(var)) + LOG_2PI)


def coverage(y, mean, var, z):
    return int(abs(float(y) - float(mean)) <= z * math.sqrt(float(var)))


def phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# --------------------------------------------------------- training side
def arm_keep_rule(rpt_rows, arm):
    """Frozen arm retention (== a2_infer._b2_arm_records with anchor 1).

    Returns kept records in PREP shape: arrival = stop + lag, sparse2 parity
    on ORIGINAL source_rpt_index."""
    if len(rpt_rows) < 2:
        raise CalibrateError("cell has fewer than two valid RPTs")
    anchor_orig = int(rpt_rows[1]["idx"])
    lag = DELAY7D_SECONDS if arm == "delay7d" else 0.0
    keep = []
    for i, r in enumerate(rpt_rows):
        if arm == "sparse2" and i > 1 and (int(r["idx"]) - anchor_orig) % 2:
            continue
        keep.append({"source_epoch": float(r["stop"]),
                     "available_epoch": float(r["stop"]) + lag,
                     "capacity_ah": float(r["cap"]),
                     "valid": True,
                     "source_rpt_index": int(r["idx"])})
    return keep


def assert_matches_b2_rule(rpt_rows, arm):
    """Cross-contract gate: my keep rule == a2_infer._b2_arm_records."""
    rows_b2shape = [{"source_rpt_index": int(r["idx"]),
                     "stop_epoch": float(r["stop"]),
                     "capacityAh": float(r["cap"])} for r in rpt_rows]
    policy = _b2_arm_records(rows_b2shape, 1, arm)
    b2_keep = sorted(int(r["source_rpt_index"]) for r in policy)
    b2_arrival = {int(r["source_rpt_index"]): float(r["arrival_epoch"])
                  for r in policy}
    mine = arm_keep_rule(rpt_rows, arm)
    my_keep = sorted(int(r["source_rpt_index"]) for r in mine)
    my_arrival = {int(r["source_rpt_index"]): float(r["available_epoch"])
                  for r in mine}
    if b2_keep != my_keep or b2_arrival != my_arrival:
        raise CalibrateError("arm rule diverges from _b2_arm_records (%s)"
                             % arm)


def build_cell_arm(cid, prep_cell, rpt_rows, names_ref, arm):
    """One (cell, arm) A2 sequence + monotone query list (ext derivation)."""
    if names_ref is not None:
        pass  # names checked by caller
    assert_matches_b2_rule(rpt_rows, arm)
    keep = arm_keep_rule(rpt_rows, arm)
    cycles = [{"source_epoch": float(c["source"]),
               "available_epoch": float(c["source"]),
               "control": list(c["control"]),
               "control_mask": list(c["mask"]),
               "source_cycle_index": j}
              for j, c in enumerate(prep_cell["cycles"])]
    seq = cell_sequence(cid, cycles, keep, cutoff_epoch=None)
    if seq.get("anchor") is None:
        raise CalibrateError("cell %s arm %s has no anchor" % (cid, arm))
    if abs(float(seq["q_ref_ah"]) - float(prep_cell["q_ref"])) > 1e-5:
        raise CalibrateError("cell %s sequence q_ref != PREP q_ref" % cid)
    queries = sorted(
        ({"q": qrow["q"], "gap": qrow["h"], "y": qrow["y"],
          "next_stop": rpt_rows[qrow["next_i"]]["stop"]}
         for qrow in ext.derive_cell_queries(rpt_rows)
         if qrow["arm"] == arm),
        key=lambda r: r["q"])
    for a, b in zip(queries, queries[1:]):
        if b["q"] <= a["q"]:
            raise CalibrateError("queries not strictly monotone %s/%s" % (cid, arm))
    return seq, queries


def train_walker_pass(model, train_work, deadline=None, log_every=None):
    """Stream every (cell, arm, q) through the A3 walker + held-control
    forecast.  Returns rows + counters.  0 optimiser steps."""
    cfg = a3_infer.MODEL_ARMS[MODEL_KEY]
    rows = []
    n_cells = 0
    with torch.no_grad():
        for cid in sorted(train_work):
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("calibration runtime deadline reached")
            entry = train_work[cid]
            q_ref_t = torch.tensor([float(entry["q_ref"])],
                                   dtype=a3_infer.FILTER_DTYPE)
            for arm in ARMS:
                seq = entry["arms"][arm]["seq"]
                queries = entry["arms"][arm]["queries"]
                if not queries:
                    continue
                lag = DELAY7D_SECONDS if arm == "delay7d" else 0.0
                walker = a3_infer.AsOfWalkerA3(model, seq, lag, cfg)
                for query in queries:
                    state = walker.state_at(query["q"])
                    ctl_np, msk_np, _policy, _held = \
                        a3_infer._control_for_output(state, cfg)
                    ctl = torch.as_tensor(ctl_np.reshape(1, -1),
                                          dtype=state["m"].dtype,
                                          device=state["m"].device)
                    msk = torch.as_tensor(msk_np.reshape(1, -1),
                                          dtype=state["m"].dtype,
                                          device=state["m"].device)
                    pred = a3_infer._advance_horizon(
                        model, state["m"], state["P"], query["gap"],
                        ctl, msk, q_ref_t, cfg)
                    mu = float(pred["mean_ah"])
                    var = float(pred["var_ah2"])
                    if not (math.isfinite(mu) and math.isfinite(var) and var > 0):
                        raise CalibrateError(
                            "non-finite forecast for %s/%s@%.3f" % (cid, arm,
                                                                    query["q"]))
                    rows.append({
                        "cell_id": cid, "arm": arm,
                        "query_epoch": query["q"],
                        "gap_weeks": query["gap"],
                        "next_source_stop_epoch": query["next_stop"],
                        "target_capacity_ah": query["y"],
                        "pred_mean_ah": mu,
                        "pred_latent_var_ah2": float(pred["latent_var_ah2"]),
                        "pred_var_ah2": var,
                        "residual_ah": query["y"] - mu,
                        "n_cycles_used": int(state["n_cycles_used"]),
                        "n_rpt_used": int(state["n_rpt_used"]),
                        "n_late_arrival_excluded":
                            int(state["n_late_arrival_excluded"])})
            n_cells += 1
            if log_every and n_cells % log_every == 0:
                print("  [cal] cells %d/%d rows %d" % (n_cells, len(train_work),
                                                       len(rows)))
    return rows, {"n_cells": n_cells, "n_rows": len(rows),
                  "optimizer_steps": 0, "fits": 0}


def calibration_factor(rows):
    """Frozen estimator: s = sum r^2 / sum v (pooled over all rows).

    With var' = s*v the POOLED standardised second moment is exactly 1.
    Diagnostic only: the per-point MLE under heteroscedastic v would be
    mean(r^2/v); both are reported (the applied factor is the frozen one)."""
    num = math.fsum(r["residual_ah"] ** 2 for r in rows)
    den = math.fsum(r["pred_var_ah2"] for r in rows)
    if den <= 0:
        raise CalibrateError("sum of predicted variances is not positive")
    s_mle = (math.fsum(r["residual_ah"] ** 2 / r["pred_var_ah2"]
                       for r in rows) / len(rows))
    return num / den, {"sum_sq_residual_ah2": num, "sum_pred_var_ah2": den,
                       "s_mle_per_point_mean_diagnostic": s_mle}


def s_summaries(rows, s):
    """Per-arm and per-cell s summaries + residual-variance scatter bins."""
    by_arm = {}
    for r in rows:
        by_arm.setdefault(r["arm"], []).append(r)
    per_arm = {}
    for arm in ARMS:
        sub = by_arm.get(arm) or []
        num = math.fsum(r["residual_ah"] ** 2 for r in sub)
        den = math.fsum(r["pred_var_ah2"] for r in sub)
        per_arm[arm] = {"n": len(sub), "s_arm": (num / den if den > 0 else None),
                        "mean_abs_residual_ah":
                            (float(np.mean([abs(r["residual_ah"])
                                            for r in sub])) if sub else None)}
    by_cell = {}
    for r in rows:
        by_cell.setdefault(r["cell_id"], []).append(r)
    per_cell = []
    for cid in sorted(by_cell):
        sub = by_cell[cid]
        num = math.fsum(r["residual_ah"] ** 2 for r in sub)
        den = math.fsum(r["pred_var_ah2"] for r in sub)
        per_cell.append({"cell_id": cid, "n": len(sub),
                         "s_cell": (num / den if den > 0 else None)})
    qs = np.quantile(np.asarray([r["pred_var_ah2"] for r in rows],
                                dtype=np.float64),
                     np.linspace(0.0, 1.0, N_VARIANCE_BINS + 1))
    bins = []
    for i in range(N_VARIANCE_BINS):
        lo, hi = float(qs[i]), float(qs[i + 1])
        if i == 0:
            sub = [r for r in rows if r["pred_var_ah2"] <= hi]
        elif i == N_VARIANCE_BINS - 1:
            sub = [r for r in rows if r["pred_var_ah2"] > lo]
        else:
            sub = [r for r in rows if lo < r["pred_var_ah2"] <= hi]
        if not sub:
            continue
        n = len(sub)
        mean_var = math.fsum(r["pred_var_ah2"] for r in sub) / n
        emp_var = math.fsum(r["residual_ah"] ** 2 for r in sub) / n
        bins.append({"bin": i, "var_lo": lo, "var_hi": hi, "n": n,
                     "mean_pred_var_ah2": mean_var,
                     "empirical_residual_var_ah2": emp_var,
                     "ratio_emp_over_model": (emp_var / mean_var
                                              if mean_var > 0 else None)})
    return {"per_arm": per_arm, "per_cell": per_cell, "variance_bins": bins}


# ------------------------------------------------------------ C3 re-eval
def parse_c3_csv(store, path, model_label=MODEL_LABEL):
    blob = store.read_bytes(path, "c3_predictions_csv")
    reader = csv.DictReader(io.StringIO(blob.decode("utf-8")))
    missing = [c for c in C3_NEED_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise CalibrateError("C3 CSV missing columns %s" % missing)
    rows = []
    seen_pairs = set()
    for row in reader:
        if str(row["model_arm"]).strip() != model_label:
            continue
        key = (row["cell_id"], row["arm"], round(float(row["query_epoch"]), 5))
        if key in seen_pairs:
            raise CalibrateError("duplicate A3_full point %r" % (key,))
        seen_pairs.add(key)
        rec = {"cell_id": row["cell_id"], "group_id": row["group_id"],
               "arm": row["arm"], "query_epoch": float(row["query_epoch"]),
               "model_key": str(row["model_key"]).strip()}
        rec["target"] = _f(row.get("target_capacity_ah"))
        rec["mean"] = _f(row.get("pred_mean_ah"))
        rec["var"] = _f(row.get("pred_var_ah2"))
        rec["nll_csv"] = _f(row.get("nll_per_ah"))
        rec["cov50_csv"] = _f(row.get("covered_50"))
        rec["cov90_csv"] = _f(row.get("covered_90"))
        rec["cov95_csv"] = _f(row.get("covered_95"))
        rec["scored"] = all(rec[k] is not None
                            for k in ("target", "mean", "var"))
        for h in MENU_WEEKS:
            tag = ("h%g" % h).replace(".", "p")
            rec[tag + "_mean"] = _f(row.get(tag + "_mean_ah"))
            rec[tag + "_sd"] = _f(row.get(tag + "_sd_ah"))
            rec[tag + "_var"] = _f(row.get(tag + "_var_ah2"))
            rec[tag + "_truth"] = _f(row.get(tag + "_target_capacity_ah"))
        rows.append(rec)
    if not rows:
        raise CalibrateError("C3 CSV has no %s rows" % model_label)
    return rows


def c3_integrity_gate(rows):
    """With s=1 the recomputation must reproduce the CSV's own columns."""
    bad = 0
    for r in rows:
        if not r["scored"]:
            continue
        nll1 = gaussian_nll(r["target"], r["mean"], r["var"])
        if not math.isclose(nll1, r["nll_csv"], rel_tol=1e-9, abs_tol=1e-12):
            bad += 1
            continue
        if coverage(r["target"], r["mean"], r["var"], Z50) != \
                int(r["cov50_csv"]) or \
           coverage(r["target"], r["mean"], r["var"], Z90) != \
                int(r["cov90_csv"]) or \
           coverage(r["target"], r["mean"], r["var"], Z95) != \
                int(r["cov95_csv"]):
            bad += 1
    if bad:
        raise CalibrateError("C3 integrity gate failed on %d rows: "
                             "pred_var_ah2 is not the variance behind "
                             "nll/covered columns" % bad)
    return {"checked_rows": sum(1 for r in rows if r["scored"])}


def _aggregate_nll_cov(rows, s):
    """Aggregate one variant over row dicts with cell/arm; returns scopes."""
    scopes = {}
    scopes["all"] = rows
    for arm in ARMS:
        scopes[arm] = [r for r in rows if r["arm"] == arm]
    out = {}
    for scope, sub in scopes.items():
        scored = [r for r in sub if r["scored"]]
        nll_cells = {}
        cov_cells = {z: {} for z in ("cov50", "cov90", "cov95")}
        nll_sum = 0.0
        cov_hits = {"cov50": 0, "cov90": 0, "cov95": 0}
        for r in scored:
            var = s * r["var"]
            nll = gaussian_nll(r["target"], r["mean"], var)
            nll_sum += nll
            nll_cells.setdefault(r["cell_id"], []).append(nll)
            for z, zz in (("cov50", Z50), ("cov90", Z90), ("cov95", Z95)):
                hit = coverage(r["target"], r["mean"], var, zz)
                cov_hits[z] += hit
                cov_cells[z].setdefault(r["cell_id"], []).append(hit)
        n = len(scored)
        cells = sorted(nll_cells)
        block = {"n": n}
        if n:
            block["nll_pooled"] = nll_sum / n
            block["nll_cell_macro"] = float(np.mean(
                [float(np.mean(nll_cells[c])) for c in cells]))
            for z in ("cov50", "cov90", "cov95"):
                block[z + "_pooled"] = cov_hits[z] / n
                block[z + "_cell_macro"] = float(np.mean(
                    [float(np.mean(cov_cells[z][c])) for c in cells
                     if cov_cells[z].get(c)]))
        out[scope] = block
    return out


# --------------------------------------------------------- schedule side
def schedule_points(rows):
    """A3_full rows -> schedule_eval-shaped points (copied semantics)."""
    points = {}
    for r in rows:
        key = (r["cell_id"], r["arm"], round(float(r["query_epoch"]), 5))
        point = points.setdefault(key, {"cell": key[0], "arm": key[1],
                                        "truth": {}, "preds": {}})
        preds = point["preds"].setdefault(MODEL_LABEL, {})
        for h in MENU_WEEKS:
            tag = ("h%g" % h).replace(".", "p")
            truth = r[tag + "_truth"]
            if h in point["truth"]:
                prev = point["truth"][h]
                if (prev is None) != (truth is None) or (
                        prev is not None and truth is not None and
                        abs(prev - truth) > 1e-7):
                    raise CalibrateError("horizon truth disagrees at %r h=%g"
                                         % (key, h))
            else:
                point["truth"][h] = truth
            mean, sd = r[tag + "_mean"], r[tag + "_sd"]
            if mean is not None and sd is not None and sd > 0:
                preds[h] = (mean, sd)
    return points


def risk_choose(preds, alpha, eol, menu):
    """schedule_eval.risk_choose, copied verbatim in semantics."""
    if not preds:
        return None
    feasible = []
    for h in sorted(menu):
        hit = preds.get(float(h))
        if hit is None:
            continue
        mean, sd = hit
        if sd > 0 and phi((eol - mean) / sd) <= alpha:
            feasible.append(float(h))
    if feasible:
        return max(feasible)
    if 1.0 in preds:
        return 1.0
    return min(preds)


def evaluate_policy(points, decide, eol):
    """schedule_eval.evaluate_arm/aggregate semantics (copied)."""
    out = {"decided": 0, "undecided": 0, "unknown": 0, "known": 0,
           "violations": 0, "interval_sum": 0.0, "rows": []}
    for key in sorted(points):
        point = points[key]
        chosen = decide(point)
        if chosen is None:
            out["undecided"] += 1
            out["rows"].append({"key": key, "chosen": None,
                                "violation": None})
            continue
        out["decided"] += 1
        out["interval_sum"] += float(chosen)
        truth = point["truth"].get(float(chosen))
        if truth is None:
            out["unknown"] += 1
            out["rows"].append({"key": key, "chosen": chosen,
                                "violation": None})
        else:
            violation = bool(truth < eol)
            out["known"] += 1
            out["violations"] += int(violation)
            out["rows"].append({"key": key, "chosen": chosen,
                                "violation": violation})
    return out


def aggregate_policy(evaluated):
    by_cell_known = {}
    by_cell_all = {}
    for row in evaluated["rows"]:
        cell = row["key"][0]
        if row.get("chosen") is not None:
            by_cell_all.setdefault(cell, []).append(float(row["chosen"]))
        if row.get("violation") is not None:
            by_cell_known.setdefault(cell, []).append(bool(row["violation"]))
    cell_rates = {c: (sum(1 for v in vs if v), len(vs))
                  for c, vs in by_cell_known.items()}
    macro_v = (float(np.mean([v / n for v, n in cell_rates.values()]))
               if cell_rates else float("nan"))
    cell_int = {c: (sum(vs), len(vs)) for c, vs in by_cell_all.items()}
    macro_i = (float(np.mean([s / n for s, n in cell_int.values()]))
               if cell_int else float("nan"))
    return {
        "n_decided": evaluated["decided"],
        "n_undecided": evaluated["undecided"],
        "n_unknown_truth": evaluated["unknown"],
        "n_known": evaluated["known"],
        "n_violations": evaluated["violations"],
        "violation_rate_pooled":
            (evaluated["violations"] / evaluated["known"]
             if evaluated["known"] else float("nan")),
        "violation_rate_cell_macro": macro_v,
        "n_cells_macro_violation": len(cell_rates),
        "mean_interval_pooled":
            (evaluated["interval_sum"] / evaluated["decided"]
             if evaluated["decided"] else float("nan")),
        "mean_interval_cell_macro": macro_i,
        "n_cells_macro_interval": len(cell_int),
    }


def policy_table(points, s, eol, menu, alphas):
    """Risk-policy rows for one variance scale s (sd scaled by sqrt(s))."""
    scaled = {}
    for key, point in points.items():
        preds = point["preds"].get(MODEL_LABEL) or {}
        sp = {}
        for h, (mean, sd) in preds.items():
            sd_cal = math.sqrt(float(s)) * float(sd)
            if sd_cal > 0:
                sp[h] = (mean, sd_cal)
        entry = dict(point)
        entry["preds"] = {MODEL_LABEL: sp} if sp else {}
        scaled[key] = entry
    rows = []
    for arm in list(ARMS) + ["all"]:
        arm_points = {k: p for k, p in scaled.items()
                      if arm == "all" or p["arm"] == arm}
        for alpha in alphas:
            decide = lambda pt, a=alpha: risk_choose(
                pt["preds"].get(MODEL_LABEL, {}), a, eol, menu)
            stats = aggregate_policy(evaluate_policy(arm_points, decide, eol))
            rows.append({"arm": arm,
                         "policy": "risk_%s_a%g" % (MODEL_LABEL, alpha),
                         "family": "risk", "model": MODEL_LABEL,
                         "alpha": "%.3g" % alpha, "variant": None,
                         **stats})
    return rows


def cross_check_policy_table(computed, pinned_rows):
    """BEFORE (s=1) must reproduce the pinned R3 policy_table A3_full rows."""
    pinned = {}
    for row in pinned_rows:
        if str(row.get("family")) == "risk" and \
                str(row.get("model")) == MODEL_LABEL:
            pinned[(str(row["arm"]), str(row["alpha"]))] = row
    if not pinned:
        raise CalibrateError("pinned policy_table has no %s risk rows"
                             % MODEL_LABEL)
    exact = ("n_decided", "n_undecided", "n_unknown_truth", "n_known",
             "n_violations")
    close = ("violation_rate_pooled", "violation_rate_cell_macro",
             "mean_interval_pooled", "mean_interval_cell_macro")
    checked = 0
    for row in computed:
        key = (row["arm"], row["alpha"])
        if key not in pinned:
            raise CalibrateError("pinned policy_table lacks (%s, %s)" % key)
        ref = pinned[key]
        for k in exact:
            if int(round(float(ref[k]))) != int(row[k]):
                raise CalibrateError("policy_table mismatch %s %s: "
                                     "pinned=%s computed=%s"
                                     % (key, k, ref[k], row[k]))
        for k in close:
            a, b = float(ref[k]), float(row[k])
            if not (math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12) or
                    (math.isnan(a) and math.isnan(b))):
                raise CalibrateError("policy_table mismatch %s %s: "
                                     "pinned=%r computed=%r" % (key, k, a, b))
        checked += 1
    if checked != len(pinned):
        raise CalibrateError("policy_table row count mismatch: pinned=%d "
                             "computed=%d" % (len(pinned), checked))
    return {"matched_rows": checked}


def honest_flag(after_rows):
    """Training-internal calibration sufficiency check (frozen wording)."""
    row = next((r for r in after_rows
                if r["arm"] == "all" and r["alpha"] == "%.3g" % 0.05), None)
    if row is None:
        raise CalibrateError("honest flag: no calibrated all/alpha=0.05 row")
    rate = float(row["violation_rate_cell_macro"])
    flag = bool(rate > HONEST_THRESHOLD)
    return {
        "flag": "TRAIN_CALIBRATION_INSUFFICIENT" if flag else
                "TRAIN_CALIBRATION_ADEQUATE_AT_THIS_THRESHOLD",
        "calibrated_alpha5_violation_rate_cell_macro_all": rate,
        "threshold": HONEST_THRESHOLD,
        "statement": ("training-internal variance calibration is NOT "
                      "sufficient: calibrated alpha=5%% cell-macro violation "
                      "is still above 10%% (rate=%.4f); a process-noise "
                      "redesign is required" % rate) if flag else
                     ("calibrated alpha=5%% cell-macro violation rate is "
                      "at or below 10%% (rate=%.4f)" % rate),
    }


# ---------------------------------------------------------------- GO gate
def validate_go(go, go_path, store, runs_parent, receipts_parent):
    problems = []
    if any(k not in go for k in GO_REQUIRED):
        missing = [k for k in GO_REQUIRED if k not in go]
        raise CalibrateError("GO missing required fields: %s" % missing)
    if go["status"] != "APPROVED":
        problems.append("status not APPROVED")
    if go["allow_fit"] is not False:
        problems.append("allow_fit must be FALSE for a calibration GO "
                        "(0 fits, inference only)")
    if "CALIBRATE" not in str(go["scope"]):
        problems.append("scope lacks CALIBRATE")
    if go["owner_thread_id"] != OWNER_THREAD_ID:
        problems.append("owner mismatch")
    rid = go["request_id"]
    if not isinstance(rid, str) or len(rid) < 8:
        problems.append("request_id missing/too short")
    if go["seed"] != SEED:
        problems.append("seed != 42")
    if go["device"] != "cpu" or int(go["threads"]) != 4:
        problems.append("device/threads contract mismatch")
    if not 600 <= int(go["max_runtime_seconds"]) <= 14400:
        problems.append("max_runtime_seconds out of range")
    issued = _dt.datetime.fromisoformat(
        str(go["issued_utc"]).replace("Z", "+00:00"))
    age = (_dt.datetime.now(_dt.timezone.utc) - issued).total_seconds()
    if abs(age) > 86400:
        problems.append("GO stale (>24h)")
    if go["s_definition"] != S_DEFINITION:
        problems.append("s_definition is not the frozen string")
    if float(go["eol_threshold_ah"]) != EOL_AH:
        problems.append("eol_threshold mismatch")
    if tuple(float(x) for x in go["menu_weeks"]) != MENU_WEEKS:
        problems.append("menu_weeks mismatch")
    if tuple(float(x) for x in go["alphas"]) != ALPHAS:
        problems.append("alphas mismatch")

    code = go["code_sha256"]
    pin_paths = {name: (os.path.join(HERE, name) if name in
                        ("a3_calibrate.py", "ext_baselines.py")
                        else os.path.join(_A3_DIR, name)
                        if name.startswith("a3_")
                        else os.path.join(_A2_DIR, name))
                 for name in CODE_PINS}
    if sorted(code) != sorted(pin_paths):
        problems.append("code_sha256 pins wrong file set")
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
        try:
            store.read_bytes(ckpt["path"], "go_pinned_checkpoint",
                             expect_sha=ckpt["sha256"])
        except ext.ExtBaselineError as exc:
            problems.append("checkpoint: %s" % exc)

    assets = go["assets"]
    if sorted(assets) != sorted(ASSET_KEYS):
        problems.append("assets pin set mismatch")
    else:
        for key in ASSET_KEYS:
            entry = assets[key]
            if sorted(entry) != ["path", "sha256"]:
                problems.append("asset %s entry shape" % key)
                continue
            try:
                if key == "schedule_dir":
                    digest = dir_digest(store, entry["path"])
                    if digest != entry["sha256"]:
                        problems.append("schedule_dir digest mismatch")
                else:
                    store.read_bytes(store.resolve(entry["path"]),
                                     "go_pinned_" + key,
                                     expect_sha=entry["sha256"])
            except (ext.ExtBaselineError, CalibrateError) as exc:
                problems.append("asset %s: %s" % (key, exc))

    pc = go["panel_contract"]
    if not isinstance(pc, dict) or pc.get("arms") != list(ARMS):
        problems.append("panel_contract arms mismatch")
    elif not isinstance(pc.get("n_train_queries"), int) or \
            pc["n_train_queries"] <= 0:
        problems.append("panel_contract n_train_queries invalid")

    out_dir = go["output_dir"]
    receipt = go["receipt_path"]
    if os.path.realpath(os.path.dirname(os.path.abspath(out_dir))) != \
            os.path.realpath(runs_parent):
        problems.append("output_dir not fresh under runs/")
    if os.path.exists(out_dir):
        problems.append("output_dir already exists")
    if os.path.realpath(os.path.dirname(os.path.abspath(receipt))) != \
            os.path.realpath(receipts_parent):
        problems.append("receipt_path not under receipts/")
    if os.path.exists(receipt):
        problems.append("receipt_path already exists")

    if not ext.request_id_is_fresh(rid, str(go["consumed_registry"])):
        problems.append("request_id already consumed")
    if str(rid) in BURNED_REQUEST_IDS:
        problems.append("request_id burned (replay refused)")

    if problems:
        raise CalibrateError("GO refused: " + "; ".join(problems))
    return (os.path.abspath(out_dir), os.path.abspath(receipt),
            str(go["consumed_registry"]), rid)


# ---------------------------------------------------------------- runner
def run_go(go_path, store=None, runs_parent=None, receipts_parent=None,
           use_locks=True, expected_train_cells=125):
    """Full guarded calibration; returns the receipt dict (never raises)."""
    t0 = time.time()
    real = store is None
    stats = ext.ReadStats()
    if real:
        store = ext.Store(["/home/yndx/zxk/rul"], stats,
                          base="/home/yndx/zxk/rul")
    out_dir = None
    receipt_path = None
    locks = []
    rec = {"status": "PREFLIGHT_FAILED", "fits": 0, "optimizer_steps": 0,
           "real_run": bool(real)}
    try:
        go = json.loads(open(go_path, "r", encoding="utf-8").read())
        runs_parent = runs_parent or os.path.join(HERE, "runs")
        receipts_parent = receipts_parent or os.path.join(HERE, "receipts")
        out_dir, receipt_path, registry, rid = validate_go(
            go, go_path, store, runs_parent, receipts_parent)
        rec.update(request_id=rid, go_sha256=ext.sha256_file(go_path))
        deadline = time.monotonic() + int(go["max_runtime_seconds"])
        if use_locks:
            import fcntl
            for lp in ("/home/yndx/zxk/rul/automation/state/"
                       "online_survival_cpu.lock",
                       "/home/yndx/zxk/rul/automation/locks/"
                       "isu_irregular_rul_cpu.lock"):
                f = open(lp, "a+")
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locks.append(f)
        os.makedirs(runs_parent, exist_ok=True)
        os.makedirs(receipts_parent, exist_ok=True)
        os.makedirs(out_dir)
        rec.update(status="LOADING_ASSETS")
        atomic_json(os.path.join(out_dir, "progress.json"), rec)

        assets = go["assets"]
        rpt_manifest = store.read_json(
            store.resolve(assets["rpt_manifest"]["path"]), "rpt_manifest")
        if str(rpt_manifest.get("status")) != "ALL188_FEATURE_CACHE_COMPLETE":
            raise CalibrateError("RPT manifest status mismatch")
        rpt_inv = {str(e["cell_id"]): e
                   for e in rpt_manifest.get("inventory") or []}
        prep = ext.load_prep(store, store.resolve(
            assets["prep_manifest"]["path"]),
            store.resolve(assets["prep_npz"]["path"]))
        if len(prep["cells"]) != int(expected_train_cells):
            raise CalibrateError("PREP cell count %d != expected %d"
                                 % (len(prep["cells"]), expected_train_cells))
        train_ids = sorted(prep["cells"])
        if int(rpt_manifest.get("train", -1)) != len(train_ids):
            raise CalibrateError("RPT manifest train count mismatch")
        if int(rpt_manifest.get("locked", 0)) != 0:
            raise CalibrateError("RPT manifest reports locked cells")

        # tree CSV: the dev-panel keys are re-derived and asserted equal --
        # run-time proof that the shared frozen query rule is intact.
        _by_model, tree_keys = ext.load_tree_panel(
            store, store.resolve(assets["tree_csv"]["path"]))
        panel_cells = sorted({k[0] for k in tree_keys})
        dev_ids = sorted(c for c, e in rpt_inv.items()
                         if str(e.get("role")) == "development")
        if not set(panel_cells) <= set(dev_ids):
            raise CalibrateError("panel cells not subset of RPT-manifest dev")
        derived_dev = set()
        for cid in panel_cells:
            entry = rpt_inv.get(cid)
            if entry is None or str(entry.get("role")) != "development":
                raise CalibrateError("RPT manifest role missing %s" % cid)
            rows, _names = ext.load_rpt_json_cell(
                store, store.resolve(entry["path"]), cid,
                expect_sha=entry.get("sha256"))
            for q in ext.derive_cell_queries(rows):
                derived_dev.add((cid, q["arm"], round(q["q"], 6)))
        if derived_dev != tree_keys:
            raise CalibrateError("derived dev panel != tree CSV keys "
                                 "(%d vs %d)" % (len(derived_dev),
                                                 len(tree_keys)))

        # checkpoint -> float64 filter model (a3_infer discipline)
        blob = store.read_bytes(store.resolve(go["checkpoint"]["path"]),
                                "checkpoint",
                                expect_sha=go["checkpoint"]["sha256"])
        try:
            obj = torch.load(io.BytesIO(blob), map_location="cpu",
                             weights_only=True)
        except TypeError:  # older torch
            obj = torch.load(io.BytesIO(blob), map_location="cpu")
        if isinstance(obj, dict) and "state_dict" in obj:
            obj = obj["state_dict"]
        model = build_arm_model(MODEL_KEY, seed=SEED)
        try:
            model.load_state_dict(obj, strict=True)
        except Exception as exc:  # noqa: BLE001
            raise CalibrateError("checkpoint does not match A3StateModel: %s"
                                 % exc)
        model.eval()
        for name, param in model.named_parameters():
            if not torch.all(torch.isfinite(param)):
                raise CalibrateError("checkpoint has non-finite parameter %s"
                                     % name)
        model = model.double().eval()
        rec.update(checkpoint={k: go["checkpoint"][k] for k in
                               ("path", "sha256")},
                   model_arm=a3_infer.MODEL_ARMS[MODEL_KEY]["label"])
        atomic_json(os.path.join(out_dir, "progress.json"), rec)

        # ---- stage 1: training-panel walker pass (0 fits) ----------------
        rec.update(status="TRAIN_WALKER")
        atomic_json(os.path.join(out_dir, "progress.json"), rec)
        names_ref = None
        rpt_assets = {}
        for cid in train_ids:
            entry = rpt_inv.get(cid)
            if entry is None or str(entry.get("role")) != "train":
                raise CalibrateError("RPT manifest role missing %s" % cid)
            rows, names = ext.load_rpt_json_cell(
                store, store.resolve(entry["path"]), cid,
                expect_sha=entry.get("sha256"))
            rpt_assets[cid] = (rows, names)
            if names_ref is None:
                names_ref = names
        train_work = {}
        for cid in train_ids:
            rows, names = rpt_assets[cid]
            if names != names_ref:
                raise CalibrateError("feature set drift for %s" % cid)
            pc = prep["cells"][cid]
            ext.cross_check_train(pc, rows, cid)
            entry = {"q_ref": float(pc["q_ref"]), "arms": {}}
            for arm in ARMS:
                seq, queries = build_cell_arm(cid, pc, rows, names_ref, arm)
                entry["arms"][arm] = {"seq": seq, "queries": queries}
            train_work[cid] = entry
        n_train_queries = sum(len(e["arms"][a]["queries"])
                              for e in train_work.values() for a in ARMS)
        if n_train_queries != int(go["panel_contract"]["n_train_queries"]):
            raise CalibrateError("derived train queries %d != GO panel "
                                 "contract %d" % (n_train_queries,
                                                  go["panel_contract"]
                                                  ["n_train_queries"]))
        train_rows, counters = train_walker_pass(model, train_work,
                                                 deadline=deadline,
                                                 log_every=25)
        s, s_parts = calibration_factor(train_rows)
        if not (math.isfinite(s) and s > 0):
            raise CalibrateError("calibration factor s is not finite/positive")
        summaries = s_summaries(train_rows, s)

        # ---- stage 2: C3 saved-prediction re-evaluation ------------------
        rec.update(status="C3_REEVAL", train_rows=len(train_rows),
                   n_train_queries=n_train_queries, s=s,
                   train_walker_counters=counters)
        atomic_json(os.path.join(out_dir, "progress.json"), rec)
        c3_rows = parse_c3_csv(store, store.resolve(
            assets["c3_predictions_csv"]["path"]))
        integrity = c3_integrity_gate(c3_rows)
        c3_before = _aggregate_nll_cov(c3_rows, 1.0)
        c3_after = _aggregate_nll_cov(c3_rows, s)

        # ---- stage 3: schedule frontier re-evaluation --------------------
        rec.update(status="SCHEDULE_REEVAL")
        atomic_json(os.path.join(out_dir, "progress.json"), rec)
        points = schedule_points(c3_rows)
        before_rows = policy_table(points, 1.0, float(go["eol_threshold_ah"]),
                                   tuple(float(x) for x in go["menu_weeks"]),
                                   [float(a) for a in go["alphas"]])
        after_rows = policy_table(points, s, float(go["eol_threshold_ah"]),
                                  tuple(float(x) for x in go["menu_weeks"]),
                                  [float(a) for a in go["alphas"]])
        # BEFORE must reproduce the pinned R3 policy table exactly.
        pinned_blob = None
        pin_table = None
        sched_dir = store.resolve(assets["schedule_dir"]["path"])
        real_dir = store._allowed(sched_dir)
        for name in sorted(os.listdir(real_dir)):
            if name == "policy_table.csv":
                pin_table = os.path.join(real_dir, name)
        if pin_table is None:
            raise CalibrateError("schedule_dir has no policy_table.csv")
        pinned_blob = store.read_bytes(pin_table, "schedule_dir_file")
        pinned_rows = list(csv.DictReader(
            io.StringIO(pinned_blob.decode("utf-8"))))
        cross = cross_check_policy_table(before_rows, pinned_rows)

        flag = honest_flag(after_rows)

        # ---- outputs ------------------------------------------------------
        if not train_rows:
            raise CalibrateError("training walker produced no rows")
        with open(os.path.join(out_dir, "train_walker_predictions.csv"),
                  "x", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(train_rows[0]))
            w.writeheader()
            w.writerows(train_rows)
        metric_fields = ("scope", "variant", "n", "nll_pooled",
                         "nll_cell_macro", "cov50_pooled", "cov50_cell_macro",
                         "cov90_pooled", "cov90_cell_macro", "cov95_pooled",
                         "cov95_cell_macro")
        with open(os.path.join(out_dir, "c3_reeval_metrics.csv"), "x",
                  newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(metric_fields))
            w.writeheader()
            for variant, block in (("before_s1", c3_before),
                                   ("after_calibrated", c3_after)):
                for scope in ("all",) + tuple(ARMS):
                    row = {"scope": scope, "variant": variant}
                    row.update({k: block[scope].get(k, "")
                                for k in metric_fields[2:]})
                    w.writerow(row)
        front_fields = ("variant", "arm", "policy", "family", "model",
                        "alpha", "n_decided", "n_undecided",
                        "n_unknown_truth", "n_known", "n_violations",
                        "violation_rate_pooled", "violation_rate_cell_macro",
                        "n_cells_macro_violation", "mean_interval_pooled",
                        "mean_interval_cell_macro", "n_cells_macro_interval")
        with open(os.path.join(out_dir, "schedule_frontier_calibrated.csv"),
                  "x", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(front_fields))
            w.writeheader()
            for variant, table in (("before_s1", before_rows),
                                   ("after_calibrated", after_rows)):
                for row in table:
                    out = {k: row.get(k, "") for k in front_fields}
                    out["variant"] = variant
                    w.writerow(out)

        report = {
            "status": "COMPLETE",
            "s_definition": S_DEFINITION,
            "s": s,
            "s_parts": s_parts,
            "n_train_queries": n_train_queries,
            "n_train_cells": len(train_work),
            "train_walker_counters": counters,
            "summaries": summaries,
            "c3_integrity": integrity,
            "c3_reeval": {"before_s1": c3_before,
                          "after_calibrated": c3_after},
            "schedule_cross_check": cross,
            "schedule_frontier": {"before_s1": before_rows,
                                  "after_calibrated": after_rows},
            "honest_report": flag,
            "optimizer_steps": 0,
            "fits": 0,
            "payload_reads": stats.snapshot(),
        }
        atomic_json(os.path.join(out_dir, "calibration_report.json"), report)
        rec.update(status="COMPLETE_NO_FITS_NO_DEV_TUNING",
                   fits=0, optimizer_steps=0,
                   s=s, n_train_queries=n_train_queries,
                   honest_flag=flag["flag"],
                   calibrated_alpha5_cell_macro_all=flag[
                       "calibrated_alpha5_violation_rate_cell_macro_all"],
                   payload_reads=stats.snapshot(),
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
                json.dump(rec, f, indent=2, ensure_ascii=False, allow_nan=True)
    return rec


# ============================================================== self-check
def _synth_c3_rows(world):
    """Fabricate A3_full C3 rows with self-consistent NLL/coverage columns."""
    rng = np.random.default_rng(7)
    rows = []
    for cid in world["dev"]:
        for arm in ARMS:
            for k in range(2):
                q = 1625000000.0 + 7.0 * WEEK * (k + 1)
                mean = 0.25 - 0.01 * (k + 1)
                var = 4e-5 + 2e-5 * k
                target = mean + 1.2 * math.sqrt(var) * (1 if k == 0 else -1)
                nll = gaussian_nll(target, mean, var)
                rec = {"cell_id": cid, "group_id": cid[:3], "arm": arm,
                       "model_key": "full", "model_arm": MODEL_LABEL,
                       "query_epoch": q, "target_capacity_ah": repr(target),
                       "pred_mean_ah": repr(mean), "pred_var_ah2": repr(var),
                       "pred_latent_var_ah2": repr(var * 0.5),
                       "nll_per_ah": repr(nll),
                       "covered_50": coverage(target, mean, var, Z50),
                       "covered_90": coverage(target, mean, var, Z90),
                       "covered_95": coverage(target, mean, var, Z95)}
                for h in MENU_WEEKS:
                    tag = ("h%g" % h).replace(".", "p")
                    hmean = mean - 0.002 * h
                    hvar = var * (1.0 + 0.1 * h)
                    htruth = hmean + 1.5 * math.sqrt(hvar) * \
                        (1 if ((k + len(cid) + len(arm)) % 2) else -1)
                    rec[tag + "_mean_ah"] = repr(hmean)
                    rec[tag + "_sd_ah"] = repr(math.sqrt(hvar))
                    rec[tag + "_var_ah2"] = repr(hvar)
                    rec[tag + "_target_capacity_ah"] = repr(htruth)
                    rec[tag + "_target_epoch"] = repr(q + h * WEEK)
                rows.append(rec)
                # decoy model row (must be ignored)
                decoy = dict(rec)
                decoy["model_arm"] = "A3_time"
                decoy["model_key"] = "time"
                decoy["pred_mean_ah"] = "0.1"
                rows.append(decoy)
    return rows


def _c3_csv_columns():
    cols = list(C3_NEED_COLUMNS) + ["target_capacity_ah"]
    seen = set()
    out = []
    for c in cols:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _synth_cal_world(tmp):
    world = ext._synth_world(tmp)
    # checkpoint from an independent seed (architecture identical)
    torch.manual_seed(3)
    ckpt_model = build_arm_model("full", seed=3)
    ckpt_path = os.path.join(tmp, "model_state_dict_full.pt")
    torch.save(ckpt_model.state_dict(), ckpt_path)
    world["checkpoint"] = ckpt_path
    # C3 CSV + pinned policy table
    c3_rows = _synth_c3_rows(world)
    c3_path = os.path.join(tmp, "predictions_c3_a3.csv")
    with open(c3_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_c3_csv_columns(), extrasaction="ignore")
        w.writeheader()
        w.writerows(c3_rows)
    world["c3_csv"] = c3_path
    store = ext.Store([tmp], ext.ReadStats(), base=tmp)
    parsed = parse_c3_csv(store, c3_path)   # exercise the real parser
    points = schedule_points(parsed)
    before = policy_table(points, 1.0, EOL_AH, MENU_WEEKS, list(ALPHAS))
    sched_dir = os.path.join(tmp, "run_schedule_eval_synth")
    os.makedirs(sched_dir, exist_ok=True)
    with open(os.path.join(sched_dir, "policy_table.csv"), "w",
              newline="", encoding="utf-8") as f:
        fields = ("arm", "policy", "family", "model", "alpha", "fixed_h",
                  "n_decided", "n_undecided", "n_unknown_truth", "n_known",
                  "n_violations", "violation_rate_pooled",
                  "violation_rate_cell_macro", "n_cells_macro_violation",
                  "mean_interval_pooled", "mean_interval_cell_macro",
                  "n_cells_macro_interval", "menu_slots_available_fraction")
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in before:
            w.writerow({k: row.get(k, "") for k in fields})
    with open(os.path.join(sched_dir, "schedule_summary.json"), "w") as f:
        json.dump({"status": "SCHEDULE_EVAL_COMPLETE",
                   "policy": {"eol_threshold_ah": EOL_AH,
                              "menu_weeks": list(MENU_WEEKS),
                              "alpha_list": list(ALPHAS)}}, f)
    with open(os.path.join(sched_dir, "per_cell_schedule.csv"), "w") as f:
        f.write("arm,policy,cell_id\n")
    world["schedule_dir"] = sched_dir
    world["c3_rows"] = c3_rows
    world["before_table"] = before
    return world


def _valid_cal_go(world, request_id="EXTCAL_SELFCHECK_0001"):
    stats = ext.ReadStats()
    store = ext.Store([world["tmp"]], stats, base=world["tmp"])

    def pin(key, path):
        return {"path": path, "sha256": ext.sha256_file(path)}

    code = {}
    for name in CODE_PINS:
        if name in ("a3_calibrate.py", "ext_baselines.py"):
            code[name] = ext.sha256_file(os.path.join(HERE, name))
        elif name.startswith("a3_"):
            code[name] = ext.sha256_file(os.path.join(_A3_DIR, name))
        else:
            code[name] = ext.sha256_file(os.path.join(_A2_DIR, name))
    n_train = sum(len(ext.derive_cell_queries(
        ext.load_rpt_json_cell(store, os.path.join(world["rpt_dir"],
                                                   cid + ".json"), cid)[0]))
                  for cid in world["train"])
    return {
        "status": "APPROVED",
        "allow_fit": False,
        "allow_inference": True,
        "scope": "A3 CALIBRATE: training-internal variance factor s + C3 "
                 "recalibrated re-eval + schedule frontier (0 fits)",
        "request_id": request_id,
        "owner_thread_id": OWNER_THREAD_ID,
        "issued_utc": utc_now_iso().replace("+00:00", "Z"),
        "seed": SEED,
        "device": "cpu", "threads": 4, "max_runtime_seconds": 3600,
        "code_sha256": code,
        "checkpoint": pin("checkpoint", world["checkpoint"]),
        "assets": {
            "prep_manifest": pin("prep_manifest", world["prep_manifest"]),
            "prep_npz": pin("prep_npz", world["prep_npz"]),
            "rpt_manifest": pin("rpt_manifest", world["rpt_manifest"]),
            "tree_csv": pin("tree_csv", world["tree_csv"]),
            "c3_predictions_csv": pin("c3_predictions_csv", world["c3_csv"]),
            "schedule_dir": {
                "path": world["schedule_dir"],
                "sha256": dir_digest(store, world["schedule_dir"])},
        },
        "panel_contract": {"n_train_queries": n_train, "arms": list(ARMS),
                           "c3_model_arm": MODEL_LABEL},
        "s_definition": S_DEFINITION,
        "eol_threshold_ah": EOL_AH,
        "menu_weeks": list(MENU_WEEKS),
        "alphas": list(ALPHAS),
        "consumed_registry": world["registry"],
        "output_dir": os.path.join(world["runs"], "extcal_selfcheck_run1"),
        "receipt_path": os.path.join(
            world["receipts"], "extcal_selfcheck_run1_receipt.json"),
    }


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
            emit("  -> FAIL %s: %s" % (name, exc))

    tmp = tempfile.mkdtemp(prefix="a3_calibrate_selfcheck_")
    try:
        world = _synth_cal_world(tmp)
        stats = ext.ReadStats()
        store = ext.Store([tmp], stats, base=tmp)

        def no_real_reads():
            store.read_bytes(world["tree_csv"], "selfcheck_probe")
            real = [p for p in stats.paths
                    if not p.startswith(os.path.realpath(tmp))]
            assert not real, "self-check opened real assets: %s" % real
            assert stats.paths, "self-check read nothing"
            return "reads=%d, all under tmp" % len(stats.paths)

        # 1 ----------------------------------------------------------
        def chk_world():
            assert os.path.isfile(world["checkpoint"])
            assert os.path.isfile(world["c3_csv"])
            assert len(world["c3_rows"]) > 0
            return "world + checkpoint + c3 csv + schedule dir built"
        check("synthetic calibration world built", chk_world)

        # 2 ----------------------------------------------------------
        check("no real payload/asset reads (store audit)", no_real_reads)

        # 3 ----------------------------------------------------------
        def chk_s():
            rows = [
                {"residual_ah": 0.02, "pred_var_ah2": 1e-4},
                {"residual_ah": -0.002, "pred_var_ah2": 4e-4},
            ]
            s, parts = calibration_factor(rows)
            expect = (0.02 ** 2 + 0.002 ** 2) / (1e-4 + 4e-4)
            assert math.isclose(s, expect, rel_tol=1e-15)
            assert math.isclose(s, 0.808, rel_tol=1e-12)
            assert math.isclose(parts["sum_sq_residual_ah2"], 0.000404,
                                rel_tol=1e-15)
            # defining property of the ratio estimator: with var' = s*var
            # the POOLED standardised second moment is exactly 1
            pooled_std = sum(r["residual_ah"] ** 2 for r in rows) /                 sum(s * r["pred_var_ah2"] for r in rows)
            assert math.isclose(pooled_std, 1.0, rel_tol=1e-15)
            try:
                calibration_factor([{"residual_ah": 0.0,
                                     "pred_var_ah2": 0.0}])
                raise AssertionError("zero variance not refused")
            except CalibrateError:
                pass
            return "s=0.808 exact; MLE property; zero-variance refused"
        check("s closed-form correctness (hand case + MLE property)", chk_s)

        # 4 ----------------------------------------------------------
        def chk_walker():
            cfg = a3_infer.MODEL_ARMS[MODEL_KEY]
            model = build_arm_model("full", seed=3).double().eval()
            cid = world["train"][0]
            pc = ext.load_prep(store, world["prep_manifest"],
                               world["prep_npz"])["cells"][cid]
            rows, _names = ext.load_rpt_json_cell(
                store, os.path.join(world["rpt_dir"], cid + ".json"), cid)
            n_cmp = 0
            for arm in ARMS:
                seq, queries = build_cell_arm(cid, pc, rows, None, arm)
                lag = DELAY7D_SECONDS if arm == "delay7d" else 0.0
                walker = a3_infer.AsOfWalkerA3(model, seq, lag, cfg)
                for query in queries[::2]:
                    st_w = walker.state_at(query["q"])
                    st_r = a3_infer.reference_asof_state_a3(
                        model, seq, query["q"], cfg, lag)
                    dm = float((st_w["m"] - st_r["m"]).abs().max())
                    dP = float((st_w["P"] - st_r["P"]).abs().max())
                    assert dm <= 1e-12 and dP <= 1e-12,                         (cid, arm, query, dm, dP)
                    assert int(st_w["n_late_arrival_excluded"]) == \
                        int(st_r["n_late_arrival_excluded"])
                    n_cmp += 1
            assert n_cmp >= 3
            return "walker == per-query re-filter on %d cuts x %d arms " \
               "(bitwise m/P)" % (n_cmp, len(ARMS))
        check("walker == per-query re-filtering (a3_infer reference)", chk_walker)

        # 5 ----------------------------------------------------------
        def chk_leak():
            cfg = a3_infer.MODEL_ARMS[MODEL_KEY]
            model = build_arm_model("full", seed=3).double().eval()
            cid = world["train"][0]
            pc = ext.load_prep(store, world["prep_manifest"],
                               world["prep_npz"])["cells"][cid]
            rows, _names = ext.load_rpt_json_cell(
                store, os.path.join(world["rpt_dir"], cid + ".json"), cid)
            arm = "raw"
            seq, queries = build_cell_arm(cid, pc, rows, None, arm)
            q = queries[len(queries) // 2]["q"]
            st1 = a3_infer.AsOfWalkerA3(model, seq, 0.0, cfg).state_at(q)
            # perturb every event AFTER q (capacities + controls) and retry
            seq2 = copy.deepcopy(seq)
            for e in seq2["events"]:
                if float(e["source_epoch"]) > q + 1e-9:
                    if e["kind"] == "rpt":
                        e["capacity_ah"] = 0.05
                    else:
                        e["control"] = [9.9] * 24
                        e["control_mask"] = [1.0] * 24
            st2 = a3_infer.AsOfWalkerA3(model, seq2, 0.0, cfg).state_at(q)
            assert torch.equal(st1["m"], st2["m"])
            assert torch.equal(st1["P"], st2["P"])
            return "post-query capacity/control perturbation invariant"
        check("no-leakage (future events cannot touch the as-of state)", chk_leak)

        # 6 ----------------------------------------------------------
        def chk_b2():
            cid = "X02C1"   # the index-gap train cell
            rows, _ = ext.load_rpt_json_cell(
                store, os.path.join(world["rpt_dir"], cid + ".json"), cid)
            for arm in ARMS:
                assert_matches_b2_rule(rows, arm)
            keep_raw = {int(r["source_rpt_index"])
                        for r in arm_keep_rule(rows, "raw")}
            keep_sp = {int(r["source_rpt_index"])
                       for r in arm_keep_rule(rows, "sparse2")}
            assert keep_sp < keep_raw and len(keep_sp) >= 3
            return "keep sets + arrivals identical to _b2_arm_records (3 arms)"
        check("arm keep rule == frozen B2 rule (cross-contract)", chk_b2)

        # 7 ----------------------------------------------------------
        n_refused = [0]

        def chk_go():
            good = _valid_cal_go(world)
            gp = os.path.join(tmp, "go_good.json")
            with open(gp, "w", encoding="utf-8") as f:
                json.dump(good, f)
            out, rcp, reg, rid = validate_go(good, gp, store,
                                             world["runs"], world["receipts"])
            assert rid == good["request_id"]

            def mutate(kind):
                g = copy.deepcopy(good)
                if kind == "status":
                    g["status"] = "PENDING"
                elif kind == "allow_fit_true":
                    g["allow_fit"] = True
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
                elif kind == "runtime":
                    g["max_runtime_seconds"] = 999999
                elif kind == "code_sha":
                    g["code_sha256"]["a3_calibrate.py"] = "0" * 64
                elif kind == "code_set":
                    g["code_sha256"]["bogus.py"] = "1" * 64
                elif kind == "ckpt_sha":
                    g["checkpoint"]["sha256"] = "0" * 64
                elif kind == "asset_sha":
                    g["assets"]["prep_npz"]["sha256"] = "0" * 64
                elif kind == "sched_dir_sha":
                    g["assets"]["schedule_dir"]["sha256"] = "0" * 64
                elif kind == "asset_missing":
                    del g["assets"]["tree_csv"]
                elif kind == "panel":
                    g["panel_contract"]["n_train_queries"] += 1
                elif kind == "s_def":
                    g["s_definition"] = "tune on C3 (forbidden)"
                elif kind == "eol":
                    g["eol_threshold_ah"] = 0.25
                elif kind == "alphas":
                    g["alphas"] = [0.05]
                elif kind == "consumed_rid":
                    g["request_id"] = "ALREADY_CONSUMED_RID"
                    ext.register_consumed_go(good["consumed_registry"],
                                             "ALREADY_CONSUMED_RID",
                                             "b" * 64, utc_now_iso())
                elif kind == "burned_rid":
                    g["request_id"] = BURNED_REQUEST_IDS[0]
                elif kind == "out_dir_exists":
                    os.makedirs(g["output_dir"], exist_ok=True)
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
                    validate_go(g, mp, store, world["runs"], world["receipts"])
                    raise AssertionError("mutation %s NOT refused" % kind)
                except (CalibrateError, ext.ExtBaselineError):
                    n_refused[0] += 1
                finally:
                    shutil.rmtree(g["output_dir"], ignore_errors=True)
                    if os.path.exists(g["receipt_path"]):
                        os.remove(g["receipt_path"])

            for kind in ("status", "allow_fit_true", "scope", "owner", "stale",
                         "seed", "device", "runtime", "code_sha", "code_set",
                         "ckpt_sha", "asset_sha", "sched_dir_sha",
                         "asset_missing", "s_def", "eol", "alphas",
                         "consumed_rid", "burned_rid", "out_dir_exists",
                         "receipt_exists", "missing_field"):
                mutate(kind)
            assert n_refused[0] >= 12, "only %d refused" % n_refused[0]
            return "valid GO accepted; %d/22 mutations refused" % n_refused[0]
        check("GO validator (allow_fit=true refused; >=12 mutations)", chk_go)

        # 8 ----------------------------------------------------------
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
            assert os.path.realpath(reg).startswith(os.path.realpath(tmp))
            return "append once + duplicate refused (tmp registry only)"
        check("registry append/duplicate-refusal (isolated tmp)", chk_registry)

        # 9 ----------------------------------------------------------
        def chk_policy():
            eol, menu = EOL_AH, MENU_WEEKS
            preds = {1.0: (0.24, 0.01), 4.0: (0.23, 0.01),
                     12.0: (0.21, 0.01), 32.0: (0.19, 0.01)}
            assert risk_choose(preds, 0.02, eol, menu) == 4.0
            assert risk_choose(preds, 0.2, eol, menu) == 12.0
            assert risk_choose(preds, 0.5, eol, menu) == 12.0  # h32 z=+1 -> .841
            preds2 = {1.0: (0.10, 0.01), 4.0: (0.10, 0.01)}
            assert risk_choose(preds2, 0.05, eol, menu) == 1.0  # none -> h1
            preds3 = {4.0: (0.10, 0.01)}                       # no h1 -> min
            assert risk_choose(preds3, 0.05, eol, menu) == 4.0
            preds4 = {1.0: (0.10, 0.0), 4.0: (0.10, 0.01)}     # sd=0 excluded
            assert risk_choose(preds4, 0.05, eol, menu) == 1.0  # h1 exists
            assert risk_choose({}, 0.05, eol, menu) is None
            # evaluate + aggregate hand case: 1 cell, 2 points
            points = {
                ("C1", "raw", 1.0): {"cell": "C1", "arm": "raw",
                                     "truth": {4.0: 0.19, 1.0: 0.25},
                                     "preds": {"A3_full": preds}},
                ("C1", "raw", 2.0): {"cell": "C1", "arm": "raw",
                                     "truth": {4.0: 0.21},
                                     "preds": {"A3_full": preds}},
            }
            ev = evaluate_policy(points,
                                 lambda p: risk_choose(
                                     p["preds"]["A3_full"], 0.02, eol, menu),
                                 eol)
            st = aggregate_policy(ev)
            assert st["n_decided"] == 2 and st["n_known"] == 2
            assert st["n_violations"] == 1   # pt1 h4 truth .19 <.2; pt2 .21 safe
            assert abs(st["violation_rate_pooled"] - 0.5) < 1e-15
            assert abs(st["mean_interval_pooled"] - 4.0) < 1e-15
            assert abs(st["violation_rate_cell_macro"] - 0.5) < 1e-15
            # policy_table cross-check: faithful + corrupted refusal
            computed = policy_table(points, 1.0, eol, menu, [0.02])
            pinned = [{"family": "risk", "model": MODEL_LABEL,
                       "arm": r["arm"], "alpha": r["alpha"],
                       **{k: r[k] for k in
                          ("n_decided", "n_undecided", "n_unknown_truth",
                           "n_known", "n_violations",
                           "violation_rate_pooled",
                           "violation_rate_cell_macro",
                           "mean_interval_pooled",
                           "mean_interval_cell_macro")}}
                      for r in computed]
            cross_check_policy_table(computed, pinned)
            bad = copy.deepcopy(pinned)
            bad[0]["n_violations"] = int(bad[0]["n_violations"]) + 1
            try:
                cross_check_policy_table(computed, bad)
                raise AssertionError("corrupted table not refused")
            except CalibrateError:
                pass
            return "risk_choose/evaluate/aggregate hand-checked; " \
                   "table cross-check faithful + corruption refused"
        check("schedule policy semantics + policy_table cross-check", chk_policy)

        # 10 ---------------------------------------------------------
        def chk_c3metrics():
            rows = [
                {"cell_id": "C1", "arm": "raw", "scored": True,
                 "target": 0.26, "mean": 0.25, "var": 1e-4,
                 "nll_csv": gaussian_nll(0.26, 0.25, 1e-4),
                 "cov50_csv": coverage(0.26, 0.25, 1e-4, Z50),
                 "cov90_csv": coverage(0.26, 0.25, 1e-4, Z90),
                 "cov95_csv": coverage(0.26, 0.25, 1e-4, Z95)},
                {"cell_id": "C2", "arm": "delay7d", "scored": True,
                 "target": 0.23, "mean": 0.25, "var": 1e-4,
                 "nll_csv": gaussian_nll(0.23, 0.25, 1e-4),
                 "cov50_csv": coverage(0.23, 0.25, 1e-4, Z50),
                 "cov90_csv": coverage(0.23, 0.25, 1e-4, Z90),
                 "cov95_csv": coverage(0.23, 0.25, 1e-4, Z95)},
                {"cell_id": "C2", "arm": "delay7d", "scored": False,
                 "target": None, "mean": 0.25, "var": 1e-4,
                 "nll_csv": None, "cov50_csv": None, "cov90_csv": None,
                 "cov95_csv": None},
            ]
            gate = c3_integrity_gate(rows)
            assert gate["checked_rows"] == 2
            bad = copy.deepcopy(rows)
            bad[0]["nll_csv"] = 0.1
            try:
                c3_integrity_gate(bad)
                raise AssertionError("corrupted nll not refused")
            except CalibrateError:
                pass
            after = _aggregate_nll_cov(rows, 2.0)
            # hand: row1 var 2e-4, z=.1/sqrt(2e-4)=.707 -> nll=.5(.5+ln2e-4+ln2pi)
            nll1 = 0.5 * (0.5 + math.log(2e-4) + LOG_2PI)
            assert abs(after["all"]["nll_pooled"] -
                       (nll1 + gaussian_nll(0.23, 0.25, 2e-4)) / 2) < 1e-15
            assert after["raw"]["n"] == 1 and after["delay7d"]["n"] == 1
            assert after["all"]["cov90_pooled"] == 1.0  # .707 and 1.414 <= 1.645
            return "s=1 reproduces CSV columns; s=2 hand-checked; " \
                   "pooled/cell-macro consistent"
        check("C3 metric recomputation consistency (s=1 gate, s=2 hand)",
              chk_c3metrics)

        # 11 ---------------------------------------------------------
        def chk_flag():
            hot = honest_flag([{"arm": "all", "alpha": "0.05",
                                "violation_rate_cell_macro": 0.12}])
            cool = honest_flag([{"arm": "all", "alpha": "0.05",
                                 "violation_rate_cell_macro": 0.08}])
            assert hot["flag"] == "TRAIN_CALIBRATION_INSUFFICIENT"
            assert "process-noise" in hot["statement"]
            assert cool["flag"] == "TRAIN_CALIBRATION_ADEQUATE_AT_THIS_THRESHOLD"
            return "flag fires at 0.12, silent at 0.08 (threshold 0.10)"
        check("honest-report flag logic", chk_flag)

        # 12 ---------------------------------------------------------
        def chk_run():
            good = _valid_cal_go(world)
            gp = os.path.join(tmp, "go_run.json")
            with open(gp, "w", encoding="utf-8") as f:
                json.dump(good, f)
            r = run_go(gp, store=store, runs_parent=world["runs"],
                       receipts_parent=world["receipts"], use_locks=False,
                       expected_train_cells=len(world["train"]))
            assert r.get("status") == "COMPLETE_NO_FITS_NO_DEV_TUNING", r
            assert r.get("fits") == 0 and r.get("optimizer_steps") == 0
            assert r.get("s", 0) > 0 and math.isfinite(r.get("s", float("nan")))
            assert r.get("registered") is True
            out_dir = good["output_dir"]
            for name in ("calibration_report.json", "train_walker_predictions.csv",
                         "c3_reeval_metrics.csv",
                         "schedule_frontier_calibrated.csv"):
                assert os.path.isfile(os.path.join(out_dir, name)), name
            report = json.load(open(os.path.join(out_dir,
                                                 "calibration_report.json")))
            assert report["schedule_cross_check"]["matched_rows"] >= 3
            fr = list(csv.DictReader(open(os.path.join(
                out_dir, "schedule_frontier_calibrated.csv"))))
            before = [x for x in fr if x["variant"] == "before_s1"]
            after = [x for x in fr if x["variant"] == "after_calibrated"]
            assert before and after and len(before) == len(after)
            assert not ext.request_id_is_fresh(good["request_id"],
                                               world["registry"])
            return "status=%s s=%.6g rows=%d before/after frontier rows=%d" % (
                r["status"], r["s"], r["n_train_queries"], len(after))
        check("full guarded calibration run on synthetic world", chk_run)

        # 13 ---------------------------------------------------------
        check("no real payload/asset reads after full run", no_real_reads)

        total = len(passed) + len(failed)
        result = "RESULT: self_check total=%d passed=%d failed=%d" % (
            total, len(passed), len(failed))
        emit("")
        emit(result)
        for name, exc in failed:
            emit("FAILED: %s: %s" % (name, exc))
        with open(ext.LOG_PATH, "a", encoding="utf-8") as f:
            f.write("\n===== a3_calibrate self-check run %s =====\n"
                    % utc_now_iso())
            f.write("\n".join(log_lines) + "\n")
        return 0 if not failed else 2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="A3 variance calibration: synthetic self-check by "
                    "default; guarded inference-only calibration with "
                    "--run-calibrate --go GO.json (allow_fit must be false)")
    p.add_argument("--self-check", action="store_true",
                   help="synthetic fixtures only (default behaviour)")
    p.add_argument("--run-calibrate", action="store_true",
                   help="guarded real calibration; requires --go")
    p.add_argument("--go", default=None,
                   help="path to an APPROVED, unconsumed GO json")
    args = p.parse_args(argv)
    if args.run_calibrate:
        if not args.go:
            print("--run-calibrate requires --go GO.json", file=sys.stderr)
            return 2
        rec = run_go(args.go)
        print(json.dumps(rec, indent=2, ensure_ascii=False, allow_nan=True))
        return 0 if rec.get("status") == "COMPLETE_NO_FITS_NO_DEV_TUNING" \
            else 2
    return self_check()


if __name__ == "__main__":
    sys.exit(main())
