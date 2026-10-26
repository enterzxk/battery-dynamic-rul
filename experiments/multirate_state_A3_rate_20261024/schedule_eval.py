#!/usr/bin/env python3
"""A3 R3 schedule-value evaluation (saved-prediction panels only; 0 fits).

Science question
----------------
Beyond point prediction, can the mechanism model's state + uncertainty support
"next inspection interval" decisions?  At every as-of query point t of the C3
development panel the operator picks the next inspection interval h from the
menu {1, 4, 12, 32} weeks.  Risk = arriving at the check and finding the
capacity already below the EOL threshold 0.20 Ah (surprise failure); cost =
violation rate traded against inspection burden (mean interval).

Data (saved prediction CSVs ONLY -- 0 fits, 0 payload, 0 checkpoints, 0 prep)
----------------------------------------------------------------------------
* A3 panel: multirate_state_A3_rate_20261024/c3_eval_a3_20261024_run2/
  predictions_c3_a3.csv (per-horizon h{1,4,12,32}_{mean_ah,sd_ah,
  target_capacity_ah} columns).  Truth for horizon h = the panel's
  h{tag}_target_capacity_ah; a (cell, t, h) whose horizon target is absent is
  UNKNOWN and excluded from that horizon's violation accounting (but the
  policy decision and its interval still count, and the unknown count is
  reported).
* A2 panel: multirate_state_A2_fullrefit_20261023/c3_eval_run2/
  predictions_c3_a2.csv (same schema; A2_time = model_key "time").  Its
  horizon truths are cross-checked against the A3 panel (fail-closed refusal
  on any disagreement).
* Trees: single-point forecasts without a horizon column.  For each menu h a
  tree row at the same (cell, arm, round(query_epoch, 5)) whose forecast gap
  is within +-0.5 weeks of h (nearest h) serves as that horizon's prediction;
  unmatched (cell, t, h) slots are MISSING and shrink the policy menu at that
  point (reported verbatim).  F0_hgb = q4_strong_baselines run2 (model hgb,
  default panel F0); F2_hgb = nextcap18 run (panel F2, model hgb).

Policies (independent decision at every query point)
----------------------------------------------------
* Fixed interval: always h, for each h in the menu (4 baselines).
* Risk-guided (model): the LARGEST h with P(Q(t+h) < EOL) <= alpha,
  P = Phi((EOL - mean_h) / sd_h) (normal approximation); if no h qualifies
  choose h = 1 (most conservative; if the h=1 prediction is missing, the
  smallest available h; if no prediction at all, the point is undecided).
  Model columns: A3_full, A2_time, F0_hgb, F2_hgb; alpha in {0.02, 0.05, 0.10}.

Metrics: violation rate and mean chosen interval, pooled + cell-macro, per
query arm (raw / sparse2 / delay7d) and overall; per-cell cost scatter rows;
paired cell bootstrap (default 5000 resamples, seed 20261024) of the A3 risk
policies against the fixed policies and the tree risk policies, on the common
decided-and-known points.

GO discipline
-------------
Default (no arguments) = synthetic self-check on tiny fabricated CSVs (no real
file is read; nothing written outside the system temp dir except the appended
SELF_CHECK_LOG.txt).  Real evaluation requires --run GO.json: an APPROVED GO
pinning saved_prediction_read=true, its own code hash (verified against this
file at binding time), the four input CSVs (path + sha256), a fresh out_dir
and the exact policy parameters (EOL threshold, menu, alphas, gap tolerance,
bootstrap n/seed); request_id must be absent from the consumed-GO registry
and is registered there after full success (a3_train.register_consumed_go,
append-once, duplicate-refusing).
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import os
import shutil
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_A2_DIR = os.path.join(os.path.dirname(HERE), "multirate_state_A2_20261022")
if not os.path.isdir(_A2_DIR):
    raise ImportError("A2 code directory not found at %s" % _A2_DIR)
if _A2_DIR not in sys.path:
    sys.path.insert(0, _A2_DIR)

from a2_targets import hash_file  # noqa: E402  (reused, unchanged)
from a3_train import (  # noqa: E402  (reused, unchanged; registry discipline)
    DEFAULT_CONSUMED_REGISTRY, load_consumed_request_ids,
    register_consumed_go,
)

VERSION = "sched-eval-20261024-r1"
EOL_DEFAULT = 0.20
MENU_DEFAULT = (1.0, 4.0, 12.0, 32.0)
ALPHAS_DEFAULT = (0.02, 0.05, 0.10)
GAP_TOL_DEFAULT = 0.5
BOOTSTRAP_N_DEFAULT = 5000
BOOTSTRAP_SEED_DEFAULT = 20261024
REQUIRED_INPUTS = ("a3", "a2", "tree_f0", "tree_f2")
H_TAGS = {1.0: "h1", 4.0: "h4", 12.0: "h12", 32.0: "h32"}
REQUIRED_CODE = ("schedule_eval.py",)
TREE_MEAN_KEYS = ("pred_mean_ah", "predicted_mean_ah", "predicted_capacity_ah")
TREE_SD_KEYS = ("pred_sd_ah", "predicted_sigma_ah", "sigma_oof_ah", "sigma_ah")
TREE_GAP_KEYS = ("gap_weeks", "forecast_h_weeks", "next_h_weeks", "h_weeks")
TRUTH_TOL = 1e-7
_UNSET = object()


class ScheduleError(RuntimeError):
    """Refusable evaluation error (no output is written)."""


# --------------------------------------------------------------------- small
def _f(value):
    """float or None (empty / unparseable -> None)."""
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


def _phi(z):
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _point_key(cell_id, arm, query_epoch):
    return (str(cell_id), str(arm), round(float(query_epoch), 5))


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value):
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _is_sha(value):
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(c in "0123456789abcdef" for c in text)


def print_header(mode):
    print("=" * 78)
    print("A3 R3 schedule-value evaluation -- %s" % _utc_now())
    print("version %s | python %s | numpy %s"
          % (VERSION, sys.version.split()[0], np.__version__))
    print("mode: %s" % mode)
    print("scope: saved prediction panels only; 0 fits, 0 payload, 0 "
          "checkpoints, 0 prep re-reads")
    print("=" * 78)


# ------------------------------------------------------------- GO validation
def _scope_text(go):
    return " ".join(str(go.get(k, "")) for k in
                    ("scope", "task", "purpose", "allowed_scope", "title")) \
        .upper()


def validate_go_document(go, expect=None, registry_path=None):
    """Pure GO checks (no filesystem access).  Returns (problems, norm)."""
    problems = []
    if not isinstance(go, dict):
        return ["GO must be a JSON object"], None
    if str(go.get("status", "")) != "APPROVED":
        problems.append("GO status is %r, not APPROVED"
                        % str(go.get("status", "")))
    if go.get("allow_fit") is not False:
        problems.append("GO must set allow_fit=false explicitly")
    if go.get("saved_prediction_read") is not True:
        problems.append("GO must set saved_prediction_read=true (panel-only "
                        "evaluation of saved prediction CSVs)")
    if "SCHEDULE-EVAL" not in _scope_text(go):
        problems.append("GO scope does not name SCHEDULE-EVAL")
    request_id = go.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        problems.append("GO has no request_id")
    registry = go.get("registry")
    if registry is not None and registry_path is not None and \
            os.path.abspath(str(registry)) != \
            os.path.abspath(str(registry_path)):
        problems.append("GO registry must be the canonical consumed-GO "
                        "registry %s, got %r"
                        % (registry_path, registry))
    code = go.get("code_sha256") or {}
    code_norm = {}
    if not isinstance(code, dict) or not code:
        problems.append("GO must bind code_sha256 for %s"
                        % ", ".join(REQUIRED_CODE))
    else:
        for name, digest in code.items():
            base = os.path.basename(str(name))
            if not _is_sha(digest):
                problems.append("code_sha256[%s] is not a 64-hex digest" % base)
                continue
            code_norm[base] = str(digest).strip().lower()
        for name in REQUIRED_CODE:
            if name not in code_norm:
                problems.append("GO code_sha256 does not pin %s" % name)
    inputs = go.get("inputs")
    if not isinstance(inputs, dict) or sorted(inputs) != sorted(REQUIRED_INPUTS):
        problems.append("GO inputs must be an object with exactly the keys "
                        "%r, got %r" % (sorted(REQUIRED_INPUTS),
                                        sorted(inputs) if isinstance(inputs,
                                                                      dict)
                                        else inputs))
        inputs = {}
    else:
        for name, spec in inputs.items():
            if not isinstance(spec, dict):
                problems.append("input %s must be an object" % name)
                continue
            path = spec.get("path")
            if not isinstance(path, str) or not os.path.isabs(path):
                problems.append("input %s path must be an absolute path"
                                % name)
            if not _is_sha(spec.get("sha256")):
                problems.append("input %s has no 64-hex sha256" % name)
    out_dir = go.get("out_dir")
    if not isinstance(out_dir, str) or not os.path.isabs(out_dir):
        problems.append("GO out_dir must be an absolute path")
    # -- pinned policy parameters must match the command line exactly
    try:
        eol = float(go.get("eol_threshold_ah"))
        if not eol > 0.0:
            raise ValueError
    except (TypeError, ValueError):
        problems.append("GO eol_threshold_ah must be a positive number, got "
                        "%r" % (go.get("eol_threshold_ah"),))
        eol = None
    menu = go.get("menu_weeks")
    menu_ok = isinstance(menu, list) and bool(menu) and \
        all(_f(m) in H_TAGS for m in menu)
    if not menu_ok:
        problems.append("GO menu_weeks must be a non-empty list drawn from "
                        "%r, got %r" % (sorted(H_TAGS), menu))
    alphas = go.get("alpha_list")
    alphas_ok = isinstance(alphas, list) and bool(alphas) and \
        all(isinstance(a, (int, float)) and 0.0 < float(a) < 1.0
            for a in alphas)
    if not alphas_ok:
        problems.append("GO alpha_list must be a non-empty list of "
                        "probabilities in (0, 1), got %r" % (alphas,))
    try:
        tol = float(go.get("tree_gap_tolerance_weeks"))
        if not tol > 0.0:
            raise ValueError
    except (TypeError, ValueError):
        problems.append("GO tree_gap_tolerance_weeks must be positive, got %r"
                        % (go.get("tree_gap_tolerance_weeks"),))
        tol = None
    try:
        boot_n = int(go.get("bootstrap_n"))
        if boot_n < 100:
            raise ValueError
    except (TypeError, ValueError):
        problems.append("GO bootstrap_n must be an integer >= 100, got %r"
                        % (go.get("bootstrap_n"),))
        boot_n = None
    try:
        boot_seed = int(go.get("bootstrap_seed"))
    except (TypeError, ValueError):
        problems.append("GO bootstrap_seed must be an integer, got %r"
                        % (go.get("bootstrap_seed"),))
        boot_seed = None
    if expect:
        if eol is not None and "eol_threshold_ah" in expect and \
                float(expect["eol_threshold_ah"]) != eol:
            problems.append("GO eol_threshold_ah=%r but command line asks for "
                            "%r" % (eol, expect["eol_threshold_ah"]))
        if menu_ok and "menu_weeks" in expect and \
                sorted(map(float, menu)) != \
                sorted(map(float, expect["menu_weeks"])):
            problems.append("GO menu_weeks=%r but command line asks for %r"
                            % (menu, list(expect["menu_weeks"])))
        if alphas_ok and "alpha_list" in expect and \
                sorted(map(float, alphas)) != \
                sorted(map(float, expect["alpha_list"])):
            problems.append("GO alpha_list=%r but command line asks for %r"
                            % (alphas, list(expect["alpha_list"])))
        if tol is not None and "tree_gap_tolerance_weeks" in expect and \
                float(expect["tree_gap_tolerance_weeks"]) != tol:
            problems.append("GO tree_gap_tolerance_weeks=%r but command line "
                            "asks for %r"
                            % (tol, expect["tree_gap_tolerance_weeks"]))
        if boot_n is not None and "bootstrap_n" in expect and \
                int(expect["bootstrap_n"]) != boot_n:
            problems.append("GO bootstrap_n=%r but command line asks for %r"
                            % (boot_n, expect["bootstrap_n"]))
        if boot_seed is not None and "bootstrap_seed" in expect and \
                int(expect["bootstrap_seed"]) != boot_seed:
            problems.append("GO bootstrap_seed=%r but command line asks for "
                            "%r" % (boot_seed, expect["bootstrap_seed"]))
    norm = {
        "request_id": request_id,
        "code_sha256": code_norm,
        "inputs": inputs if isinstance(inputs, dict) else {},
        "out_dir": os.path.abspath(os.path.expanduser(out_dir))
        if isinstance(out_dir, str) and out_dir else None,
        "eol_threshold_ah": eol,
        "menu_weeks": sorted(map(float, menu)) if menu_ok else None,
        "alpha_list": sorted(map(float, alphas)) if alphas_ok else None,
        "tree_gap_tolerance_weeks": tol,
        "bootstrap_n": boot_n,
        "bootstrap_seed": boot_seed,
    }
    return problems, norm


def validate_go_bindings(norm, registry_path):
    """Filesystem checks: code pin, input hashes, fresh out_dir, request_id
    freshness.  Nothing is written.  Returns (binding, problems)."""
    problems = []
    binding = dict(norm)
    for name, digest in sorted(norm.get("code_sha256", {}).items()):
        path = os.path.join(HERE, name)
        if not os.path.isfile(path):
            problems.append("pinned code file not found: %s" % name)
            continue
        got = hash_file(path)
        if got != digest:
            problems.append("code sha256 mismatch for %s: go=%s actual=%s"
                            % (name, digest[:16], got[:16]))
    inputs = {}
    for name, spec in sorted(norm["inputs"].items()):
        path = spec.get("path")
        if not isinstance(path, str) or not os.path.isfile(path):
            problems.append("input %s file not found: %r" % (name, path))
            continue
        got = hash_file(path)
        if str(spec.get("sha256", "")).strip().lower() != got:
            problems.append("input %s sha256 mismatch: go=%s actual=%s"
                            % (name, str(spec.get("sha256"))[:16], got[:16]))
            continue
        inputs[name] = {"path": path, "sha256": got}
    binding["inputs"] = inputs
    out_dir = norm.get("out_dir")
    if out_dir and os.path.exists(out_dir):
        problems.append("GO out_dir already exists (must be fresh): %s"
                        % out_dir)
    request_id = norm.get("request_id")
    if request_id:
        try:
            consumed = load_consumed_request_ids(registry_path)
        except Exception as exc:  # noqa: BLE001 - fail closed
            problems.append("consumed-GO registry %s unreadable: %s"
                            % (registry_path, exc))
            consumed = None
        if consumed is not None and str(request_id) in consumed:
            problems.append("request_id %r already appears in the consumed-GO "
                            "registry %s" % (str(request_id), registry_path))
    if problems:
        return None, problems
    binding["registry_path"] = os.path.abspath(registry_path)
    return binding, []


# ------------------------------------------------------------------- loaders
def _h_columns(menu):
    cols = []
    for h in sorted(menu):
        tag = H_TAGS[_f(h)]
        cols += [(h, tag + "_mean_ah"), (h, tag + "_sd_ah"),
                 (h, tag + "_target_capacity_ah")]
    return cols


def load_state_panel(path, label, menu):
    """Load an A3/A2-style panel CSV: per-point horizon truth + model preds.

    Returns (points, meta).  points: {point_key: {"cell", "arm",
    "truth": {h: capacity or None}, "preds": {model_key: {h: (mean, sd)}}}}.
    Horizon truth is read once per point; any disagreement across the model
    rows of the same point is a refusal.  Duplicate (point, model) rows are
    refused.
    """
    need = {"cell_id", "arm", "model_key", "query_epoch"} | \
        {c for _, c in _h_columns(menu)}
    points = {}
    seen_pairs = set()
    n_rows = 0
    with open(path, "r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = need - set(reader.fieldnames or [])
        if missing:
            raise ScheduleError("%s CSV is missing columns %r"
                                % (label, sorted(missing)))
        for row in reader:
            n_rows += 1
            key = _point_key(row["cell_id"], row["arm"], row["query_epoch"])
            model_key = str(row["model_key"]).strip()
            pair = (key, model_key)
            if pair in seen_pairs:
                raise ScheduleError("%s CSV has duplicate rows for point %r "
                                    "model %r" % (label, key, model_key))
            seen_pairs.add(pair)
            point = points.setdefault(key, {
                "cell": key[0], "arm": key[1], "truth": {}, "preds": {}})
            for h, col in _h_columns(menu):
                value = _f(row.get(col))
                if col.endswith("_target_capacity_ah"):
                    prev = point["truth"].get(h, _UNSET)
                    if prev is _UNSET:
                        point["truth"][h] = value
                    elif (prev is None) != (value is None) or (
                            prev is not None and value is not None and
                            abs(prev - value) > TRUTH_TOL):
                        raise ScheduleError(
                            "%s CSV horizon truth disagrees across model rows"
                            " at %r h=%g" % (label, key, h))
                elif col.endswith("_mean_ah"):
                    sd = _f(row.get(col[: -len("_mean_ah")] + "_sd_ah"))
                    if value is not None and sd is not None and sd > 0:
                        point["preds"].setdefault(model_key, {})[h] = \
                            (value, sd)
    meta = {"path": path, "label": label, "n_rows": n_rows,
            "n_points": len(points),
            "n_models": len({m for p in points.values()
                             for m in p["preds"]})}
    return points, meta


def load_tree_predictions(path, label, panel_filter=None, model_filter=None):
    """Load a tree predictions CSV (single-point forecasts; no h column).

    Returns {point_key: {"gap": weeks, "mean": ah, "sd": ah}}; duplicate
    point keys are refused (fail-closed).
    """
    out = {}
    n_rows = 0
    with open(path, "r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = set(reader.fieldnames or [])
        if not {"model", "cell_id", "arm", "query_epoch"} <= fields:
            raise ScheduleError("%s CSV lacks model/cell_id/arm/query_epoch"
                                % label)
        gap_key = next((k for k in TREE_GAP_KEYS if k in fields), None)
        mean_key = next((k for k in TREE_MEAN_KEYS if k in fields), None)
        sd_key = next((k for k in TREE_SD_KEYS if k in fields), None)
        if gap_key is None or mean_key is None or sd_key is None:
            raise ScheduleError("%s CSV lacks gap/mean/sd columns (gap=%r "
                                "mean=%r sd=%r)"
                                % (label, gap_key, mean_key, sd_key))
        for row in reader:
            n_rows += 1
            if model_filter is not None and str(row["model"]) != model_filter:
                continue
            row_panel = str(row.get("panel") or "F0")
            if panel_filter is not None and row_panel != panel_filter:
                continue
            mean = _f(row.get(mean_key))
            sd = _f(row.get(sd_key))
            gap = _f(row.get(gap_key))
            if mean is None or sd is None or sd <= 0 or gap is None:
                continue
            key = _point_key(row["cell_id"], row["arm"], row["query_epoch"])
            if key in out:
                raise ScheduleError("%s CSV has duplicate point %r (model=%s "
                                    "panel=%s)" % (label, key, model_filter,
                                                   panel_filter))
            out[key] = {"gap": gap, "mean": mean, "sd": sd}
    return out, {"path": path, "label": label, "n_rows": n_rows,
                 "n_points": len(out)}


def build_records(a3_points, a2_points, tree_f0, tree_f2, menu, tol):
    """Merge panels into evaluation records; cross-check truths; match trees.

    Returns (records, report).  records: {point_key: {"cell", "arm",
    "truth": {h: capacity or None}, "preds": {model_column: {h: (mean, sd)}}}}
    with model columns A3_full / A2_time / F0_hgb / F2_hgb.  A tree row fills
    the nearest menu h within +-tol weeks of its forecast gap (at most one h
    per unique-gap row).
    """
    common = sorted(set(a3_points) & set(a2_points))
    mismatches = 0
    for key in common:
        for h in menu:
            t_a = a3_points[key]["truth"].get(_f(h))
            t_b = a2_points[key]["truth"].get(_f(h))
            if (t_a is None) != (t_b is None) or (
                    t_a is not None and t_b is not None and
                    abs(t_a - t_b) > TRUTH_TOL):
                mismatches += 1
                if mismatches <= 3:
                    print("  truth mismatch %r h=%g: a3=%r a2=%r"
                          % (key, h, t_a, t_b))
    if mismatches:
        raise ScheduleError(
            "A2 horizon truth disagrees with A3 on %d of %d common "
            "point-horizons -- refusing (the panels must share the frozen "
            "truth)" % (mismatches, len(common) * len(menu)))
    records = {}
    for key in sorted(a3_points):
        point = a3_points[key]
        preds = {}
        if "full" in point["preds"]:
            preds["A3_full"] = point["preds"]["full"]
        a2 = a2_points.get(key)
        if a2 is not None and "time" in a2["preds"]:
            preds["A2_time"] = a2["preds"]["time"]
        for name, tree in (("F0_hgb", tree_f0), ("F2_hgb", tree_f2)):
            hit = tree.get(key)
            if hit is None:
                continue
            best, best_gap = None, None
            for h in menu:
                h = _f(h)
                gap = abs(hit["gap"] - h)
                if gap <= tol and (best is None or gap < best_gap):
                    best, best_gap = h, gap
            if best is not None:
                preds[name] = {best: (hit["mean"], hit["sd"])}
        records[key] = {"cell": point["cell"], "arm": point["arm"],
                        "truth": dict(point["truth"]), "preds": preds}
    report = {
        "n_points_a3": len(a3_points),
        "n_points_a2": len(a2_points),
        "n_points_common_truth": len(common),
        "truth_mismatch_count": mismatches,
        "n_records": len(records),
    }
    return records, report


# ------------------------------------------------------------------ policies
def risk_choose(preds, alpha, eol, menu):
    """Risk-guided choice: the largest h with P(Q(t+h)<EOL) <= alpha, else
    the h=1 prediction, else the smallest available h; None if no prediction.
    Predictions with sd <= 0 are unusable and excluded."""
    if not preds:
        return None
    feasible = []
    for h in sorted(menu):
        h = _f(h)
        hit = preds.get(h)
        if hit is None:
            continue
        mean, sd = hit
        if sd > 0 and _phi((eol - mean) / sd) <= alpha:
            feasible.append(h)
    if feasible:
        return max(feasible)
    if _f(1.0) in preds:
        return _f(1.0)
    return min(preds)


def fixed_choose(_point, h):
    return _f(h)


def make_risk_policy(model_column, alpha, eol, menu):
    def decide(point):
        return risk_choose(point["preds"].get(model_column, {}), alpha, eol,
                           menu)

    def menu_size(point):
        return len(point["preds"].get(model_column, {}))

    return decide, menu_size


# ----------------------------------------------------------------- evaluation
def evaluate_arm(points, decide, eol, menu, menu_size_fn=None):
    """Evaluate one policy on one arm's points.

    A point is DECIDED when the policy returns an h; its violation is KNOWN
    when the truth at the chosen h exists (else UNKNOWN: excluded from
    violation rates but still counted in the interval accounting, with the
    unknown count reported).
    """
    out = {"decided": 0, "undecided": 0, "unknown": 0, "known": 0,
           "violations": 0, "interval_sum": 0.0, "menu_slots": 0,
           "menu_slots_available": 0, "rows": []}
    for key in sorted(points):
        point = points[key]
        if menu_size_fn is not None:
            out["menu_slots"] += len(menu)
            out["menu_slots_available"] += min(int(menu_size_fn(point)),
                                               len(menu))
        chosen = decide(point)
        if chosen is None:
            out["undecided"] += 1
            out["rows"].append({"key": key, "chosen": None,
                                "violation": None})
            continue
        out["decided"] += 1
        out["interval_sum"] += float(chosen)
        truth = point["truth"].get(_f(chosen))
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


def aggregate(evaluated):
    """Pooled + cell-macro rates over the evaluated rows.

    cell-macro = mean over cells (with >= 1 counted point) of the per-cell
    rate; pooled = total numerator / total denominator.
    """
    by_cell_known = {}
    by_cell_all = {}
    for row in evaluated["rows"]:
        cell = row["key"][0]
        if row.get("chosen") is not None:
            by_cell_all.setdefault(cell, []).append(float(row["chosen"]))
        if row.get("violation") is not None:
            by_cell_known.setdefault(cell, []).append(bool(row["violation"]))
    pooled_viol = (evaluated["violations"], evaluated["known"])
    cell_rates_v = {c: (sum(1 for v in vs if v), len(vs))
                    for c, vs in by_cell_known.items()}
    macro_viol = (
        float(np.mean([v / n for v, n in cell_rates_v.values()]))
        if cell_rates_v else float("nan"))
    pooled_int = (evaluated["interval_sum"], evaluated["decided"])
    cell_int = {c: (sum(vs), len(vs)) for c, vs in by_cell_all.items()}
    macro_int = (float(np.mean([s / n for s, n in cell_int.values()]))
                 if cell_int else float("nan"))
    return {
        "n_decided": evaluated["decided"],
        "n_undecided": evaluated["undecided"],
        "n_unknown_truth": evaluated["unknown"],
        "n_known": evaluated["known"],
        "n_violations": evaluated["violations"],
        "violation_rate_pooled": (pooled_viol[0] / pooled_viol[1]
                                  if pooled_viol[1] else float("nan")),
        "violation_rate_cell_macro": macro_viol,
        "n_cells_macro_violation": len(cell_rates_v),
        "mean_interval_pooled": (pooled_int[0] / pooled_int[1]
                                 if pooled_int[1] else float("nan")),
        "mean_interval_cell_macro": macro_int,
        "n_cells_macro_interval": len(cell_int),
        "menu_slots_available_fraction":
            (evaluated["menu_slots_available"] / evaluated["menu_slots"]
             if evaluated["menu_slots"] else float("nan")),
    }


# ------------------------------------------------------------------ bootstrap
def paired_bootstrap(common_rows, n_boot, seed):
    """Cell-level paired bootstrap on common decided+known rows.

    common_rows: dicts {cell, viol_a, viol_b, interval_a, interval_b} (truth
    known and both policies decided).  Returns point estimates and 2.5/97.5
    percentile CIs for the macro and pooled differences A - B, plus the
    common-set sizes.
    """
    cells = sorted({r["cell"] for r in common_rows})
    if not cells:
        return {"delta_violation_cell_macro":
                {"delta": float("nan"), "ci_low": float("nan"),
                 "ci_high": float("nan")},
                "delta_violation_pooled":
                {"delta": float("nan"), "ci_low": float("nan"),
                 "ci_high": float("nan")},
                "delta_interval_cell_macro":
                {"delta": float("nan"), "ci_low": float("nan"),
                 "ci_high": float("nan")},
                "delta_interval_pooled":
                {"delta": float("nan"), "ci_low": float("nan"),
                 "ci_high": float("nan")},
                "n_common_points": 0, "n_cells": 0}
    by_cell = {c: {"va": 0, "na": 0, "vb": 0, "nb": 0,
                   "ia": 0.0, "da": 0, "ib": 0.0, "db": 0} for c in cells}
    for r in common_rows:
        c = by_cell[r["cell"]]
        c["va"] += int(bool(r["viol_a"])); c["na"] += 1
        c["vb"] += int(bool(r["viol_b"])); c["nb"] += 1
        c["ia"] += float(r["interval_a"]); c["da"] += 1
        c["ib"] += float(r["interval_b"]); c["db"] += 1
    cells_ok = [c for c in cells if by_cell[c]["na"] > 0]
    va = np.array([by_cell[c]["va"] for c in cells_ok], dtype=np.float64)
    na = np.array([by_cell[c]["na"] for c in cells_ok], dtype=np.float64)
    vb = np.array([by_cell[c]["vb"] for c in cells_ok], dtype=np.float64)
    nb = np.array([by_cell[c]["nb"] for c in cells_ok], dtype=np.float64)
    ia = np.array([by_cell[c]["ia"] for c in cells_ok], dtype=np.float64)
    da = np.array([by_cell[c]["da"] for c in cells_ok], dtype=np.float64)
    ib = np.array([by_cell[c]["ib"] for c in cells_ok], dtype=np.float64)
    db = np.array([by_cell[c]["db"] for c in cells_ok], dtype=np.float64)
    rng = np.random.default_rng(int(seed))
    idx = rng.integers(0, len(cells_ok), (int(n_boot), len(cells_ok)))
    ra, rb = va[idx], vb[idx]
    na_b, nb_b = na[idx], nb[idx]
    ia_b, ib_b = ia[idx], ib[idx]
    da_b, db_b = da[idx], db[idx]
    with np.errstate(invalid="ignore"):
        macro_va = np.where(na_b > 0, ra / np.maximum(na_b, 1), np.nan)
        macro_vb = np.where(nb_b > 0, rb / np.maximum(nb_b, 1), np.nan)
        d_viol_macro = np.nanmean(macro_va - macro_vb, axis=1)
        macro_ia = np.where(da_b > 0, ia_b / np.maximum(da_b, 1), np.nan)
        macro_ib = np.where(db_b > 0, ib_b / np.maximum(db_b, 1), np.nan)
        d_int_macro = np.nanmean(macro_ia - macro_ib, axis=1)
    d_viol_pool = ((ra.sum(1) / np.maximum(na_b.sum(1), 1)) -
                   (rb.sum(1) / np.maximum(nb_b.sum(1), 1)))
    d_int_pool = ((ia_b.sum(1) / np.maximum(da_b.sum(1), 1)) -
                  (ib_b.sum(1) / np.maximum(db_b.sum(1), 1)))

    def pack(dist, point):
        lo, hi = np.quantile(dist, [0.025, 0.975])
        return {"delta": float(point), "ci_low": float(lo),
                "ci_high": float(hi)}

    return {
        "delta_violation_cell_macro":
            pack(d_viol_macro, np.mean(va / na) - np.mean(vb / nb)),
        "delta_violation_pooled":
            pack(d_viol_pool, va.sum() / na.sum() - vb.sum() / nb.sum()),
        "delta_interval_cell_macro":
            pack(d_int_macro, np.mean(ia / da) - np.mean(ib / db)),
        "delta_interval_pooled":
            pack(d_int_pool, ia.sum() / da.sum() - ib.sum() / db.sum()),
        "n_common_points": len(common_rows),
        "n_cells": len(cells_ok),
    }


# ------------------------------------------------------------------- pipeline
RISK_MODELS = ("A3_full", "A2_time", "F0_hgb", "F2_hgb")
BOOT_METRICS = ("delta_violation_cell_macro", "delta_violation_pooled",
                "delta_interval_cell_macro", "delta_interval_pooled")


def run_pipeline(binding, args):
    """Load panels, evaluate all policies, bootstrap, write outputs."""
    t0 = time.time()
    menu = sorted(_f(m) for m in args.menu)
    eol = float(args.eol_threshold)
    alphas = sorted(float(a) for a in args.alpha)
    tol = float(args.gap_tolerance)
    inputs = binding["inputs"]
    print("loading saved prediction panels (0 fits, 0 payload, 0 checkpoints,"
          " 0 prep re-reads)")
    a3_points, meta_a3 = load_state_panel(inputs["a3"]["path"], "A3", menu)
    a2_points, meta_a2 = load_state_panel(inputs["a2"]["path"], "A2", menu)
    tree_f0, meta_f0 = load_tree_predictions(inputs["tree_f0"]["path"],
                                             "tree_f0", panel_filter="F0",
                                             model_filter="hgb")
    tree_f2, meta_f2 = load_tree_predictions(inputs["tree_f2"]["path"],
                                             "tree_f2", panel_filter="F2",
                                             model_filter="hgb")
    records, merge_report = build_records(a3_points, a2_points, tree_f0,
                                          tree_f2, menu, tol)
    arms = sorted({p["arm"] for p in records.values()})
    print("records: %d points, arms %s; A2-vs-A3 truth mismatches=%d"
          % (len(records), arms, merge_report["truth_mismatch_count"]))

    # -- tree match quality (honest numbers, on the A3 grid)
    match = {}
    for name, tree in (("F0_hgb", tree_f0), ("F2_hgb", tree_f2)):
        on_grid = [k for k in tree if k in a3_points]
        slots = 0
        filled = 0
        menu_sizes = []
        for k in on_grid:
            hit = tree[k]
            hs = [h for h in menu if abs(hit["gap"] - _f(h)) <= tol]
            slots += len(menu)
            filled += len(hs)
            menu_sizes.append(len(hs))
        gaps = [t["gap"] for k, t in tree.items() if k in a3_points]
        match[name] = {
            "tree_points": len(tree),
            "points_on_a3_grid": len(on_grid),
            "points_with_any_h": sum(1 for m in menu_sizes if m > 0),
            "menu_slots": slots,
            "menu_slots_filled": filled,
            "missing_slot_fraction": (1.0 - filled / slots if slots
                                      else float("nan")),
            "mean_menu_size": float(np.mean(menu_sizes)) if menu_sizes
            else float("nan"),
            "gap_weeks_min": float(min(gaps)) if gaps else float("nan"),
            "gap_weeks_max": float(max(gaps)) if gaps else float("nan"),
        }
        print("tree match %s: %d/%d points on the A3 grid, mean menu size "
              "%.3f, missing slot fraction %.3f, gaps %.2f..%.2f weeks"
              % (name, len(on_grid), len(tree), match[name]["mean_menu_size"],
                 match[name]["missing_slot_fraction"],
                 match[name]["gap_weeks_min"], match[name]["gap_weeks_max"]))

    # -- truth availability per horizon (A3 panel = the truth source)
    truth_avail = {}
    for h in menu:
        known = sum(1 for p in records.values()
                    if p["truth"].get(_f(h)) is not None)
        truth_avail[H_TAGS[_f(h)]] = {
            "n_known": known, "n_points": len(records),
            "fraction": known / len(records) if records else float("nan")}
        print("truth availability %s: %d/%d points (%.1f%%)"
              % (H_TAGS[_f(h)], known, len(records),
                 100.0 * truth_avail[H_TAGS[_f(h)]]["fraction"]))

    # -- policies
    policies = []
    for h in menu:
        policies.append({"family": "fixed", "model": "", "alpha": None,
                         "h": _f(h),
                         "decide": (lambda point, _h=_f(h):
                                    fixed_choose(point, _h)),
                         "menu_size_fn": None})
    for model in RISK_MODELS:
        for alpha in alphas:
            decide, menu_size_fn = make_risk_policy(model, alpha, eol, menu)
            policies.append({"family": "risk", "model": model, "alpha": alpha,
                             "h": None, "decide": decide,
                             "menu_size_fn": menu_size_fn})
    evaluated = {}
    table_rows = []
    per_cell_rows = []
    for arm in arms + ["all"]:
        arm_points = {k: p for k, p in records.items()
                      if arm == "all" or p["arm"] == arm}
        for pol in policies:
            key = (arm, pol["family"], pol["model"], pol["alpha"], pol["h"])
            ev = evaluate_arm(arm_points, pol["decide"], eol, menu,
                              menu_size_fn=pol["menu_size_fn"])
            stats = aggregate(ev)
            evaluated[key] = {"ev": ev, "stats": stats}
            label = ("fixed_h%g" % pol["h"] if pol["family"] == "fixed"
                     else "risk_%s_a%g" % (pol["model"], pol["alpha"]))
            table_rows.append({
                "arm": arm, "policy": label, "family": pol["family"],
                "model": pol["model"],
                "alpha": "" if pol["alpha"] is None else "%.3g" % pol["alpha"],
                "fixed_h": ("%.3g" % pol["h"])
                if pol["family"] == "fixed" else "",
                **stats})
            if arm == "all":
                continue
            per_cell = {}
            for row in ev["rows"]:
                cell = row["key"][0]
                slot = per_cell.setdefault(
                    cell, {"n_decided": 0, "n_known": 0, "n_violations": 0,
                           "interval_sum": 0.0})
                if row.get("chosen") is not None:
                    slot["n_decided"] += 1
                    slot["interval_sum"] += float(row["chosen"])
                if row.get("violation") is not None:
                    slot["n_known"] += 1
                    slot["n_violations"] += int(row["violation"])
            for cell in sorted(per_cell):
                slot = per_cell[cell]
                per_cell_rows.append({
                    "arm": arm, "policy": label, "cell_id": cell,
                    "n_decided": slot["n_decided"],
                    "n_known": slot["n_known"],
                    "n_violations": slot["n_violations"],
                    "violation_rate": (slot["n_violations"] / slot["n_known"]
                                       if slot["n_known"] else ""),
                    "mean_interval_weeks": (slot["interval_sum"] /
                                            slot["n_decided"]
                                            if slot["n_decided"] else "")})

    # -- paired bootstrap: A3 risk policies vs fixed + tree risk policies
    boot_rows = []
    candidates = [("risk", "A3_full", a, None) for a in alphas]
    references = ([("fixed", "", None, h) for h in menu] +
                  [("risk", m, a, None) for m in ("F0_hgb", "F2_hgb")
                   for a in alphas])
    for arm in arms:
        for c_family, c_model, c_alpha, _c_h in candidates:
            c_rows = evaluated[(arm, c_family, c_model, c_alpha,
                                _c_h)]["ev"]["rows"]
            c_by_key = {r["key"]: r for r in c_rows}
            cand_label = "risk_%s_a%g" % (c_model, c_alpha)
            for r_family, r_model, r_alpha, r_h in references:
                r_rows = evaluated[(arm, r_family, r_model, r_alpha,
                                    r_h)]["ev"]["rows"]
                r_by_key = {r["key"]: r for r in r_rows}
                ref_label = ("fixed_h%g" % r_h if r_family == "fixed"
                             else "risk_%s_a%g" % (r_model, r_alpha))
                common = []
                for key, cr in c_by_key.items():
                    rr = r_by_key.get(key)
                    if rr is None or cr.get("chosen") is None or \
                            rr.get("chosen") is None or \
                            cr.get("violation") is None or \
                            rr.get("violation") is None:
                        continue
                    common.append({"cell": key[0],
                                   "viol_a": cr["violation"],
                                   "viol_b": rr["violation"],
                                   "interval_a": float(cr["chosen"]),
                                   "interval_b": float(rr["chosen"])})
                boot = paired_bootstrap(common, args.bootstrap_n,
                                        args.bootstrap_seed)
                for metric in BOOT_METRICS:
                    pack = boot[metric]
                    boot_rows.append({
                        "arm": arm, "candidate": cand_label,
                        "reference": ref_label, "metric": metric,
                        "delta": pack["delta"], "ci_low": pack["ci_low"],
                        "ci_high": pack["ci_high"],
                        "n_common_points": boot["n_common_points"],
                        "n_cells": boot["n_cells"]})

    # -- write outputs (only after everything computed)
    out_dir = binding["out_dir"]
    os.makedirs(out_dir, exist_ok=False)

    def _write_csv(name, rows):
        path = os.path.join(out_dir, name)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        return path

    table_path = _write_csv("policy_table.csv", table_rows)
    percell_path = _write_csv("per_cell_schedule.csv", per_cell_rows)
    boot_path = _write_csv("paired_bootstrap.csv", boot_rows)
    summary = {
        "schema": "A3_SCHEDULE_EVAL_V1",
        "status": "SCHEDULE_EVAL_COMPLETE",
        "created_utc": _utc_now(),
        "version": VERSION,
        "entry_point": "schedule_eval.py",
        "policy": {"eol_threshold_ah": eol, "menu_weeks": menu,
                   "alpha_list": alphas,
                   "tree_gap_tolerance_weeks": tol,
                   "bootstrap_n": int(args.bootstrap_n),
                   "bootstrap_seed": int(args.bootstrap_seed)},
        "inputs": {k: dict(v) for k, v in sorted(inputs.items())},
        "panels": {"a3": meta_a3, "a2": meta_a2,
                   "tree_f0": meta_f0, "tree_f2": meta_f2},
        "merge": merge_report,
        "tree_match_quality": match,
        "truth_availability": truth_avail,
        "policy_table": table_rows,
        "paired_bootstrap": boot_rows,
        "outputs": {"policy_table_csv": table_path,
                    "per_cell_schedule_csv": percell_path,
                    "paired_bootstrap_csv": boot_path,
                    "summary_json": os.path.join(out_dir,
                                                 "schedule_summary.json")},
        "elapsed_seconds": time.time() - t0,
        "reads": {"fits": 0, "optimizer_steps": 0, "payload_reads": 0,
                  "checkpoint_reads": 0, "prep_rereads": 0},
    }
    summary_path = os.path.join(out_dir, "schedule_summary.json")
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(_json_safe(summary), fh, indent=2, ensure_ascii=False)
    receipt = {
        "schema": "A3_SCHEDULE_EVAL_RECEIPT_V1",
        "status": "SCHEDULE_EVAL_COMPLETE",
        "created_utc": _utc_now(),
        "request_id": binding.get("request_id"),
        "out_dir": out_dir,
        "inputs_sha256": {k: v["sha256"] for k, v in sorted(inputs.items())},
        "policy": summary["policy"],
        "elapsed_seconds": summary["elapsed_seconds"],
        "reads": summary["reads"],
    }
    receipt_path = os.path.join(out_dir, "receipt.json")
    with open(receipt_path, "w", encoding="utf-8") as fh:
        json.dump(_json_safe(receipt), fh, indent=2, ensure_ascii=False)
    return summary, receipt


def run_go(go_path, args, registry_path):
    expect = {"eol_threshold_ah": args.eol_threshold,
              "menu_weeks": list(args.menu), "alpha_list": list(args.alpha),
              "tree_gap_tolerance_weeks": args.gap_tolerance,
              "bootstrap_n": args.bootstrap_n,
              "bootstrap_seed": args.bootstrap_seed}
    try:
        with open(go_path, "r", encoding="utf-8") as fh:
            go = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        print("REFUSED -- GO is not readable JSON: %s" % exc)
        return 3
    problems, norm = validate_go_document(go, expect,
                                          registry_path=registry_path)
    if problems:
        print("REFUSED -- GO validation failed (%d problem(s)):"
              % len(problems))
        for p in problems:
            print("  - %s" % p)
        print("NO FILE WRITTEN. NO DATA READ. NO GO CONSUMED.")
        return 3
    binding, problems = validate_go_bindings(norm, registry_path)
    if problems:
        print("REFUSED -- GO binding validation failed (%d problem(s)):"
              % len(problems))
        for p in problems:
            print("  - %s" % p)
        print("NO FILE WRITTEN. NO GO CONSUMED.")
        return 3
    go_sha = hash_file(go_path)
    print("GO ACCEPTED (schedule-eval, panel-only): %s" % go_path)
    try:
        summary, receipt = run_pipeline(binding, args)
    except Exception as exc:  # noqa: BLE001
        print("SCHEDULE EVAL FAILED: %s: %s" % (type(exc).__name__, exc))
        traceback.print_exc(file=sys.stdout)
        print("NO GO CONSUMED (request_id not registered).")
        return 2
    finished = _utc_now()
    line = register_consumed_go(registry_path, norm["request_id"], go_sha,
                                finished)
    registration = {"request_id": str(norm["request_id"]),
                    "go_sha256": go_sha, "finished_utc": finished,
                    "registry": os.path.abspath(registry_path), "line": line}
    receipt["registration"] = registration
    with open(os.path.join(binding["out_dir"], "receipt.json"), "w",
              encoding="utf-8") as fh:
        json.dump(_json_safe(receipt), fh, indent=2, ensure_ascii=False)
    print("SCHEDULE EVAL COMPLETE: points=%d policy_rows=%d bootstrap_rows=%d"
          % (summary["merge"]["n_records"], len(summary["policy_table"]),
             len(summary["paired_bootstrap"])))
    print("  outputs in %s" % binding["out_dir"])
    print("  registered consumed GO: request_id=%s"
          % registration["request_id"])
    print("NO FIT. NO PAYLOAD READ. NO CHECKPOINT READ. NO PREP RE-READ.")
    return 0


# ------------------------------------------------------------------ self-check
FORBIDDEN_MARKERS = (
    "/data/", "/reports/", "/automation/", "prep_inputs", "prep_v2",
    "consumed_gos.jsonl", "run1_fits", "c3_eval_a3_20261024_run2",
    "c3_eval_run2", "predictions_c3", "/checkpoints/",
)
FORBIDDEN_SUFFIXES = (".npz", ".pt", ".pth", ".ckpt")


def _is_forbidden_path(path, tmp_prefix):
    p = str(path)
    if p.startswith(tmp_prefix):
        return False
    for marker in FORBIDDEN_MARKERS:
        if marker in p:
            return True
    for suffix in FORBIDDEN_SUFFIXES:
        if p.lower().endswith(suffix):
            return True
    return False


class _OpenAudit(object):
    """Record every builtins.open target while the self-check runs."""

    def __init__(self):
        self.paths = []
        self._orig = None

    def __enter__(self):
        import builtins
        self._orig = builtins.open
        auditor = self

        def wrapped(file, *args, **kwargs):
            try:
                auditor.paths.append(os.path.abspath(os.fspath(file)))
            except Exception:  # noqa: BLE001 - record, never block
                auditor.paths.append(repr(file))
            return auditor._orig(file, *args, **kwargs)

        builtins.open = wrapped
        return self

    def __exit__(self, *exc):
        import builtins
        builtins.open = self._orig
        return False


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _write_csv_tmp(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _synthetic_panels(root):
    """Tiny synthetic panels in the real schemas; returns input paths.

    3 cells x 2 arms (raw, delay7d) x 2 points = 12 points.  Truths: h1/h4
    always known, h12 known off SC_C, h32 known on exactly one point;
    capacities straddle the 0.20 EOL.  Means per point parity are designed so
    the risk policy choices are known by hand (healthy -> h4 at a=0.05,
    degrading -> fallback h1).  Trees: every 3rd point missing, gaps 1.08
    (matches h1) or 3.43 (outside +-0.5 of every menu h).
    """
    arms = ("raw", "delay7d")
    cells = ("SC_A", "SC_B", "SC_C")
    points = []
    for ci, cell in enumerate(cells):
        for arm in arms:
            for pi_half in range(2):
                points.append((cell, arm, 1_650_000_000.0 +
                               1000.0 * (ci * 4 + 2 * arms.index(arm) +
                                         pi_half)))
    mean_table = {
        0: {1.0: 0.26, 4.0: 0.24, 12.0: 0.215, 32.0: 0.19},   # healthy
        1: {1.0: 0.24, 4.0: 0.205, 12.0: 0.185, 32.0: 0.16},  # degrading
    }
    sd = 0.02
    h_cols = []
    for h, tag in sorted(H_TAGS.items()):
        h_cols += [tag + "_mean_ah", tag + "_sd_ah",
                   tag + "_target_capacity_ah"]
    state_fields = (["cell_id", "arm", "model_key", "query_epoch",
                     "gap_weeks", "target_available"] + h_cols)
    state_rows = []
    for pi, (cell, arm, qepoch) in enumerate(points):
        means = mean_table[pi % 2]
        parity = (pi // 2) % 2
        truth = {1.0: 0.27 - 0.02 * parity - 0.01 * ci_of(cell),
                 4.0: 0.23 - 0.02 * parity,
                 12.0: (0.21 - 0.03 * parity if cell != "SC_C" else None),
                 32.0: (0.19 if (cell == "SC_A" and pi % 4 == 0) else None)}
        for model in ("full", "noRateUpdate", "time", "noEll"):
            row = {"cell_id": cell, "arm": arm, "model_key": model,
                   "query_epoch": "%.5f" % qepoch, "gap_weeks": "1.1",
                   "target_available": "1"}
            for h, tag in sorted(H_TAGS.items()):
                row[tag + "_mean_ah"] = "%.6f" % means[h]
                row[tag + "_sd_ah"] = "%.6f" % sd
                tv = truth[h]
                row[tag + "_target_capacity_ah"] = ("" if tv is None
                                                    else "%.6f" % tv)
            state_rows.append(row)
    a3_path = _write_csv_tmp(os.path.join(root, "synth_a3.csv"),
                             state_fields, state_rows)
    a2_rows = [dict(r) for r in state_rows
               if r["model_key"] in ("full", "noRPTupdate", "time")]
    a2_path = _write_csv_tmp(os.path.join(root, "synth_a2.csv"),
                             state_fields, a2_rows)
    t1_fields = ["model", "cell_id", "group_id", "arm", "query_epoch",
                 "forecast_h_weeks", "target_next_capacity_ah",
                 "predicted_mean_ah", "predicted_sigma_ah"]
    t2_fields = ["model", "panel", "cell_id", "arm", "query_epoch",
                 "forecast_h_weeks", "target_capacity_ah",
                 "predicted_capacity_ah", "sigma_oof_ah"]
    t1_rows, t2_rows = [], []
    for pi, (cell, arm, qepoch) in enumerate(points):
        if pi % 3 == 2:
            continue  # trees miss every third point (menu shrinkage)
        gap = 3.43 if pi % 5 == 0 else 1.08  # 3.43 matches no menu h
        mean = 0.24 if pi % 2 == 0 else 0.19
        t1_rows.append({"model": "hgb", "cell_id": cell, "group_id": "g",
                        "arm": arm, "query_epoch": "%.5f" % qepoch,
                        "forecast_h_weeks": "%.3f" % gap,
                        "target_next_capacity_ah": "0.22",
                        "predicted_mean_ah": "%.6f" % mean,
                        "predicted_sigma_ah": "0.020000"})
        t2_rows.append({"model": "hgb", "panel": "F2", "cell_id": cell,
                        "arm": arm, "query_epoch": "%.5f" % qepoch,
                        "forecast_h_weeks": "%.3f" % gap,
                        "target_capacity_ah": "0.22",
                        "predicted_capacity_ah": "%.6f" % (mean + 0.005),
                        "sigma_oof_ah": "0.030000"})
        t2_rows.append({"model": "catboost", "panel": "F1", "cell_id": cell,
                        "arm": arm, "query_epoch": "%.5f" % qepoch,
                        "forecast_h_weeks": "%.3f" % gap,
                        "target_capacity_ah": "0.22",
                        "predicted_capacity_ah": "0.200000",
                        "sigma_oof_ah": "0.030000"})
    t1_path = _write_csv_tmp(os.path.join(root, "synth_tree_f0.csv"),
                             t1_fields, t1_rows)
    t2_path = _write_csv_tmp(os.path.join(root, "synth_tree_f2.csv"),
                             t2_fields, t2_rows)
    return ({"a3": a3_path, "a2": a2_path, "tree_f0": t1_path,
             "tree_f2": t2_path}, points)


def ci_of(cell):
    return {"SC_A": 0, "SC_B": 1, "SC_C": 2}[cell]


def _load_synth_records(root, menu=(1.0, 4.0, 12.0, 32.0), tol=0.5):
    paths, _points = _synthetic_panels(root)
    a3, _ = load_state_panel(paths["a3"], "A3", menu)
    a2, _ = load_state_panel(paths["a2"], "A2", menu)
    t0, _ = load_tree_predictions(paths["tree_f0"], "tree_f0",
                                  panel_filter="F0", model_filter="hgb")
    t2, _ = load_tree_predictions(paths["tree_f2"], "tree_f2",
                                  panel_filter="F2", model_filter="hgb")
    records, report = build_records(a3, a2, t0, t2, menu, tol)
    return paths, records, report


def test_phi_normal_cdf(root):
    _assert(abs(_phi(0.0) - 0.5) < 1e-12, "Phi(0) must be 0.5")
    _assert(abs(_phi(1.959963984540054) - 0.975) < 1e-9, "Phi(1.96)=0.975")
    _assert(abs(_phi(-3.0) - 0.0013498980316300946) < 1e-9,
            "Phi(-3) matches the known value")
    _assert(_phi(-2.0) < _phi(-1.0) < _phi(0.0), "Phi is monotone")
    return "Phi(0)=0.5, Phi(1.96)=0.975, Phi(-3)=0.0013499 exact to 1e-9"


def test_risk_policy_choice(root):
    eol, menu = 0.20, [1.0, 4.0, 12.0, 32.0]
    sd = 0.02
    # P1=Phi(-3)=0.0013, P4=Phi(-2)=0.0228, P12=Phi(-0.75)=0.2266, P32=Phi(.5)
    preds = {1.0: (0.26, sd), 4.0: (0.24, sd), 12.0: (0.215, sd),
             32.0: (0.19, sd)}
    _assert(risk_choose(preds, 0.02, eol, menu) == 1.0,
            "alpha=0.02 must pick h=1 (P4=0.0228>0.02)")
    _assert(risk_choose(preds, 0.05, eol, menu) == 4.0,
            "alpha=0.05 must pick the largest feasible h=4")
    _assert(risk_choose(preds, 0.10, eol, menu) == 4.0,
            "alpha=0.10 must pick h=4 (P12=0.2266>0.10)")
    bad = {1.0: (0.10, sd), 4.0: (0.10, sd)}
    _assert(risk_choose(bad, 0.02, eol, menu) == 1.0,
            "no feasible h must fall back to h=1")
    shrunk = {4.0: (0.10, sd), 12.0: (0.10, sd)}
    _assert(risk_choose(shrunk, 0.02, eol, menu) == 4.0,
            "fallback must be the smallest AVAILABLE h when h=1 is missing")
    _assert(risk_choose({}, 0.05, eol, menu) is None,
            "empty menu must be undecided")
    guarded = {1.0: (0.30, 0.0), 4.0: (0.26, sd)}
    _assert(risk_choose(guarded, 0.05, eol, menu) == 4.0,
            "sd<=0 predictions must be excluded from the risk menu")
    return ("max-feasible choice, alpha thresholds (0.02/0.05/0.10), h=1 "
            "fallback, smallest-available fallback, empty menu, sd guard")


def test_tree_gap_matching(root):
    menu = [1.0, 4.0, 12.0, 32.0]
    paths, _points = _synthetic_panels(root)
    a3, _ = load_state_panel(paths["a3"], "A3", menu)
    tree, meta = load_tree_predictions(paths["tree_f0"], "tree_f0",
                                       panel_filter="F0", model_filter="hgb")
    _assert(meta["n_points"] > 0, "tree loader must find rows")
    records, _report = build_records(a3, a3, tree, {}, menu, 0.5)
    n_matched = sum(1 for p in records.values() if "F0_hgb" in p["preds"])
    _assert(n_matched < len(records),
            "tree must miss some synthetic points (every 3rd removed)")
    for point in records.values():
        preds = point["preds"].get("F0_hgb", {})
        _assert(len(preds) <= 1,
                "a unique-gap tree row can fill at most one menu slot")
        for mean, sd in preds.values():
            _assert(sd > 0 and mean > 0, "tree prediction must be usable")
    far = [k for k, p in records.items() if "F0_hgb" in p["preds"] and
           4.0 in p["preds"]["F0_hgb"]]
    _assert(not far, "gap 3.43 is outside +-0.5 of h=4 and must not match")
    # duplicate tree points must be refused (fail-closed)
    path = os.path.join(root, "dup_tree.csv")
    fields = ["model", "cell_id", "group_id", "arm", "query_epoch",
              "forecast_h_weeks", "target_next_capacity_ah",
              "predicted_mean_ah", "predicted_sigma_ah"]
    rows = [{"model": "hgb", "cell_id": "SC_A", "group_id": "g",
             "arm": "raw", "query_epoch": "1650000000.00000",
             "forecast_h_weeks": "1.08", "target_next_capacity_ah": "0.2",
             "predicted_mean_ah": "0.25", "predicted_sigma_ah": "0.02"}]
    _write_csv_tmp(path, fields, rows + [dict(rows[0])])
    refused = False
    try:
        load_tree_predictions(path, "dup", panel_filter="F0",
                              model_filter="hgb")
    except ScheduleError:
        refused = True
    _assert(refused, "duplicate tree point must be refused")
    return ("nearest-h within +-0.5 w, 3.43w gap correctly unmatched, menu "
            "shrinkage recorded, duplicate points fail closed")


def test_missing_unknown_accounting(root):
    menu = [1.0, 4.0, 12.0, 32.0]
    eol = 0.20
    paths, _points = _synthetic_panels(root)
    points, _meta = load_state_panel(paths["a3"], "A3", menu)
    n_h32_known = sum(1 for p in points.values()
                      if p["truth"].get(32.0) is not None)
    _assert(n_h32_known == 1,
            "h32 truth known for exactly 1 synthetic point, got %d"
            % n_h32_known)
    records, _report = build_records(points, points, {}, {}, menu, 0.5)
    ev = evaluate_arm(records, lambda p: 32.0, eol, menu)  # always h=32
    _assert(ev["decided"] == len(records), "fixed h=32 decides everywhere")
    _assert(ev["unknown"] == len(records) - n_h32_known,
            "points without h32 truth must be counted unknown")
    _assert(ev["known"] == n_h32_known, "known must match truth availability")
    _assert(abs(ev["interval_sum"] - 32.0 * ev["decided"]) < 1e-9,
            "interval accounting must include unknown-truth points")
    stats = aggregate(ev)
    _assert(abs(stats["mean_interval_pooled"] - 32.0) < 1e-9,
            "pooled mean interval = 32 for the fixed h=32 policy")
    _assert(stats["n_unknown_truth"] == ev["unknown"], "unknown bookkeeping")
    return ("unknown=%d / known=%d accounting exact; intervals include "
            "unknown-truth points; pooled mean interval = 32"
            % (ev["unknown"], ev["known"]))


def test_macro_pooled_consistency(root):
    rows = [
        {"key": ("A", "raw", 1.0), "chosen": 4.0, "violation": True},
        {"key": ("A", "raw", 2.0), "chosen": 4.0, "violation": False},
        {"key": ("B", "raw", 3.0), "chosen": 4.0, "violation": False},
    ]
    ev = {"decided": 3, "undecided": 0, "unknown": 0, "known": 3,
          "violations": 1, "interval_sum": 12.0, "menu_slots": 12,
          "menu_slots_available": 12, "rows": rows}
    stats = aggregate(ev)
    _assert(abs(stats["violation_rate_cell_macro"] - 0.25) < 1e-12,
            "macro violation must be the mean of per-cell rates")
    _assert(abs(stats["violation_rate_pooled"] - 1.0 / 3.0) < 1e-12,
            "pooled violation must be violations / known")
    _assert(abs(stats["mean_interval_cell_macro"] - 4.0) < 1e-12,
            "macro interval must be the mean of per-cell means")
    _assert(abs(stats["mean_interval_pooled"] - 4.0) < 1e-12,
            "pooled interval must be the interval sum / decided")
    rows2 = rows + [
        {"key": ("A", "raw", 4.0), "chosen": 4.0, "violation": True},
        {"key": ("A", "raw", 5.0), "chosen": 4.0, "violation": True},
    ]
    ev2 = dict(ev, rows=rows2, known=5, violations=3, interval_sum=20.0)
    stats2 = aggregate(ev2)
    _assert(abs(stats2["violation_rate_cell_macro"] - 0.375) < 1e-12,
            "macro violation = (3/4 + 0/1)/2 = 0.375")
    _assert(abs(stats2["violation_rate_pooled"] - 0.6) < 1e-12,
            "pooled violation = 3/5")
    return ("hand example exact: macro 0.25 vs pooled 1/3; unequal cells "
            "macro 0.375 vs pooled 0.6; intervals 4.0 both")


def test_truth_cross_check(root):
    menu = [1.0, 4.0, 12.0, 32.0]
    paths, _points = _synthetic_panels(root)
    a3, _ = load_state_panel(paths["a3"], "A3", menu)
    a2, _ = load_state_panel(paths["a2"], "A2", menu)
    _recs, report = build_records(a3, a2, {}, {}, menu, 0.5)
    _assert(report["truth_mismatch_count"] == 0,
            "identical synthetic panels must agree")
    key = sorted(a2)[0]
    a2[key]["truth"][1.0] = a2[key]["truth"][1.0] + 0.01
    refused = False
    try:
        build_records(a3, a2, {}, {}, menu, 0.5)
    except ScheduleError:
        refused = True
    _assert(refused, "A2/A3 truth disagreement must be refused")
    return ("A2-vs-A3 horizon truth cross-check passes on equal panels and "
            "refuses on a 0.01 Ah disagreement")


def test_bootstrap_reproducible(root):
    # hand example (2 cells): exact point estimates
    rows = [{"cell": "A", "viol_a": True, "viol_b": False, "interval_a": 4.0,
             "interval_b": 1.0},
            {"cell": "A", "viol_a": False, "viol_b": False,
             "interval_a": 4.0, "interval_b": 1.0},
            {"cell": "B", "viol_a": False, "viol_b": True,
             "interval_a": 12.0, "interval_b": 1.0}]
    b1 = paired_bootstrap(rows, 2000, 20261024)
    b2 = paired_bootstrap(rows, 2000, 20261024)
    _assert(b1 == b2, "same seed must reproduce the bootstrap exactly")
    # cells A: viol_a=1/2, viol_b=0/2; cells B: viol_a=0/1, viol_b=1/1
    # delta macro = ((0.5 + 0)/2) - ((0 + 1)/2) = -0.25
    _assert(abs(b1["delta_violation_cell_macro"]["delta"] - (-0.25)) < 1e-12,
            "paired macro violation delta must be -0.25 on the hand example")
    _assert(abs(b1["delta_interval_cell_macro"]["delta"] - 7.0) < 1e-12,
            "paired interval macro delta must be +7.0 ((4+12)/2 - 1)")
    # richer 12-cell set: same-seed reproduction + CI sanity (the CI quantiles
    # of a discrete per-cell lattice can legitimately be seed-independent, so
    # seed independence is asserted only for the point estimate)
    big = []
    for i in range(12):
        big.append({"cell": "C%02d" % i,
                    "viol_a": i % 3 == 0, "viol_b": i % 4 == 1,
                    "interval_a": 4.0 if i % 2 else 12.0, "interval_b": 1.0})
    c1 = paired_bootstrap(big, 2000, 20261024)
    c2 = paired_bootstrap(big, 2000, 7)
    _assert(c1 == paired_bootstrap(big, 2000, 20261024),
            "same seed must reproduce the 12-cell bootstrap exactly")
    _assert(c1["delta_violation_cell_macro"]["delta"] ==
            c2["delta_violation_cell_macro"]["delta"],
            "the point estimate must not depend on the seed")
    for metric in ("delta_violation_cell_macro", "delta_violation_pooled",
                   "delta_interval_cell_macro", "delta_interval_pooled"):
        pack = c1[metric]
        _assert(pack["ci_low"] <= pack["ci_high"],
                "CI must be ordered (%s)" % metric)
    return ("same-seed bit reproduction (2-cell and 12-cell sets), "
            "seed-free point estimates, hand deltas -0.25 (violation) / "
            "+7.0 (interval), CI ordering verified")


def _make_go(root, inputs, mutations=None, request_id="SYNTH_SCHEDULE_EVAL_T1"):
    go = {
        "status": "APPROVED", "allow_fit": False,
        "saved_prediction_read": True,
        "scope": "A3 SCHEDULE-EVAL: R3 scheduling value from saved C3 "
                 "prediction panels; 0 fits; menu {1,4,12,32} weeks; EOL "
                 "0.20 Ah; risk alphas {0.02, 0.05, 0.10}",
        "request_id": request_id,
        "issued_utc": "2026-10-24T00:00:00Z",
        "code_sha256": {"schedule_eval.py":
                        hash_file(os.path.join(HERE, "schedule_eval.py"))},
        "inputs": {name: {"path": path, "sha256": hash_file(path)}
                   for name, path in inputs.items()},
        "out_dir": os.path.join(root, "out_schedule_synth"),
        "eol_threshold_ah": 0.20,
        "menu_weeks": [1, 4, 12, 32],
        "alpha_list": [0.02, 0.05, 0.10],
        "tree_gap_tolerance_weeks": 0.5,
        "bootstrap_n": 2000,
        "bootstrap_seed": 20261024,
    }
    for key, value in (mutations or {}).items():
        if value is _DELETE:
            go.pop(key, None)
        else:
            go[key] = value
    path = os.path.join(root, "GO_synth.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(go, fh, indent=2)
    return path


_DELETE = object()
_EXPECT = {"eol_threshold_ah": 0.20, "menu_weeks": [1.0, 4.0, 12.0, 32.0],
           "alpha_list": [0.02, 0.05, 0.10],
           "tree_gap_tolerance_weeks": 0.5, "bootstrap_n": 2000,
           "bootstrap_seed": 20261024}


def test_go_mutations(root):
    paths, _points = _synthetic_panels(root)
    registry = os.path.join(root, "registry_tmp.jsonl")
    go_path = _make_go(root, paths)
    with open(go_path, "r", encoding="utf-8") as fh:
        good = json.load(fh)
    problems, norm = validate_go_document(good, _EXPECT,
                                          registry_path=registry)
    _assert(not problems, "well-formed synthetic GO refused: %r" % problems)
    _assert(norm["menu_weeks"] == [1.0, 4.0, 12.0, 32.0] and
            norm["alpha_list"] == [0.02, 0.05, 0.10], "norm policy fields")
    binding, bproblems = validate_go_bindings(norm, registry)
    _assert(binding is not None and not bproblems,
            "binding must succeed on the synthetic GO: %r" % bproblems)
    _assert(sorted(binding["inputs"]) == ["a2", "a3", "tree_f0", "tree_f2"],
            "all four inputs bound")

    def mut(fn):
        g = copy.deepcopy(good)
        fn(g)
        return g

    cases = [
        ("status", lambda g: g.__setitem__("status", "PROPOSED")),
        ("allow_fit_true", lambda g: g.__setitem__("allow_fit", True)),
        ("allow_fit_missing", lambda g: g.pop("allow_fit")),
        ("saved_read_false", lambda g:
            g.__setitem__("saved_prediction_read", False)),
        ("saved_read_missing", lambda g: g.pop("saved_prediction_read")),
        ("scope_missing", lambda g:
            g.__setitem__("scope", "A3 inference something")),
        ("input_missing", lambda g: g["inputs"].pop("a2")),
        ("input_extra", lambda g: g["inputs"].__setitem__(
            "extra", {"path": "/tmp/x.csv", "sha256": "0" * 64})),
        ("input_path_relative", lambda g: g["inputs"]["a3"].__setitem__(
            "path", "relative.csv")),
        ("code_pin_missing", lambda g: g["code_sha256"].pop(
            "schedule_eval.py")),
        ("alpha_mismatch", lambda g:
            g.__setitem__("alpha_list", [0.02, 0.05])),
        ("threshold_mismatch", lambda g:
            g.__setitem__("eol_threshold_ah", 0.25)),
        ("menu_mismatch", lambda g: g.__setitem__("menu_weeks", [1, 4, 12])),
        ("menu_unknown_h", lambda g: g.__setitem__("menu_weeks", [2, 8])),
        ("tol_mismatch", lambda g:
            g.__setitem__("tree_gap_tolerance_weeks", 1.0)),
        ("bootstrap_n_mismatch", lambda g: g.__setitem__("bootstrap_n", 100)),
        ("bootstrap_seed_mismatch", lambda g:
            g.__setitem__("bootstrap_seed", 1)),
    ]
    refused = 0
    for label, fn in cases:
        problems, _norm = validate_go_document(mut(fn), _EXPECT,
                                               registry_path=registry)
        _assert(problems, "GO mutation %r was not refused" % label)
        refused += 1
    # binding-level refusals (need the filesystem / the registry)
    register_consumed_go(registry, good["request_id"], "0" * 64, "t")
    _b, problems = validate_go_bindings(norm, registry)
    _assert(problems and any("already appears in the consumed-GO registry"
                             in p for p in problems), problems)
    stale = os.path.join(root, "out_stale")
    os.makedirs(stale, exist_ok=True)
    _b, problems = validate_go_bindings(
        validate_go_document(mut(lambda g: g.__setitem__("out_dir", stale)),
                             _EXPECT, registry_path=registry)[1], registry)
    _assert(problems and any("already exists" in p for p in problems),
            problems)
    _b, problems = validate_go_bindings(
        validate_go_document(mut(lambda g: g["inputs"]["a3"].__setitem__(
            "path", "/nonexistent/nope.csv")), _EXPECT,
            registry_path=registry)[1], registry)
    _assert(problems and any("file not found" in p for p in problems),
            problems)
    _b, problems = validate_go_bindings(
        validate_go_document(mut(lambda g: g["inputs"]["a3"].__setitem__(
            "sha256", "0" * 64)), _EXPECT, registry_path=registry)[1], registry)
    _assert(problems and any("sha256 mismatch" in p for p in problems),
            problems)
    _b, problems = validate_go_bindings(
        validate_go_document(mut(lambda g: g["code_sha256"].__setitem__(
            "schedule_eval.py", "0" * 64)), _EXPECT,
            registry_path=registry)[1], registry)
    _assert(problems and any("code sha256 mismatch" in p for p in problems),
            problems)
    return ("%d document mutations + 5 binding refusals rejected (status, "
            "flags, saved-read flag, scope, request_id reuse, input "
            "sha/missing/extra/relative, code pin missing/bad, stale "
            "out_dir, missing file, alpha/threshold/menu/tolerance/"
            "bootstrap pins)" % refused)


def test_end_to_end_synthetic(root):
    paths, _points = _synthetic_panels(root)
    registry = os.path.join(root, "registry_tmp.jsonl")
    go_path = _make_go(root, paths, request_id="SYNTH_SCHEDULE_EVAL_T2")
    args = argparse.Namespace(
        eol_threshold=0.20, menu=[1.0, 4.0, 12.0, 32.0],
        alpha=[0.02, 0.05, 0.10], gap_tolerance=0.5, bootstrap_n=2000,
        bootstrap_seed=20261024)
    with open(go_path, "r", encoding="utf-8") as fh:
        good = json.load(fh)
    norm = validate_go_document(good, _EXPECT, registry_path=registry)[1]
    binding, problems = validate_go_bindings(norm, registry)
    _assert(binding is not None, "binding must succeed: %r" % problems)
    summary, receipt = run_pipeline(binding, args)
    _assert(summary["status"] == "SCHEDULE_EVAL_COMPLETE", "status")
    _assert(summary["merge"]["truth_mismatch_count"] == 0, "truths agree")
    tq = summary["tree_match_quality"]["F0_hgb"]
    _assert(tq["points_on_a3_grid"] < summary["merge"]["n_records"],
            "trees miss synthetic points")
    _assert(tq["missing_slot_fraction"] > 0.5,
            "tree menu coverage must be tiny (single-gap forecasts)")
    labels = {r["policy"] for r in summary["policy_table"]}
    _assert({"fixed_h1", "fixed_h4", "fixed_h12", "fixed_h32",
             "risk_A3_full_a0.05", "risk_F0_hgb_a0.05",
             "risk_F2_hgb_a0.05", "risk_A2_time_a0.05"} <= labels,
            "all policy families in the table: %r" % sorted(labels))
    boot = {(r["candidate"], r["reference"])
            for r in summary["paired_bootstrap"]}
    _assert(("risk_A3_full_a0.05", "fixed_h4") in boot and
            ("risk_A3_full_a0.05", "risk_F0_hgb_a0.05") in boot,
            "A3-vs-fixed and A3-vs-tree bootstrap pairs present")
    _assert(all(r["n_common_points"] >= 0 for r in
                summary["paired_bootstrap"]), "common counts sane")
    _assert(receipt["reads"]["fits"] == 0 and
            receipt["reads"]["payload_reads"] == 0, "receipt counters")
    _assert(os.path.isfile(os.path.join(binding["out_dir"],
                                        "per_cell_schedule.csv")),
            "per-cell cost scatter written")
    _assert(os.path.isfile(os.path.join(binding["out_dir"], "receipt.json")),
            "receipt written")
    return ("synthetic end-to-end: %d points, %d table rows, %d bootstrap "
            "rows, tree missing-slot fraction %.2f, outputs + receipt written"
            % (summary["merge"]["n_records"], len(summary["policy_table"]),
               len(summary["paired_bootstrap"]), tq["missing_slot_fraction"]))


def test_registry_append_duplicate(root):
    path = os.path.join(root, "registry_append_tmp.jsonl")
    line = register_consumed_go(path, "SYN_SCHED_RID", "ab" * 32, "utc")
    with open(path, "r", encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    _assert(len(lines) == 1 and line == lines[0], "append-once")
    rec = json.loads(lines[0])
    _assert(set(rec) == {"request_id", "go_sha256", "finished_utc"},
            "exact registry fields")
    refused = False
    try:
        register_consumed_go(path, "SYN_SCHED_RID", "ab" * 32, "again")
    except RuntimeError:
        refused = True
    _assert(refused, "duplicate registration refused")
    bad = os.path.join(root, "bad_tmp.jsonl")
    with open(bad, "w", encoding="utf-8") as fh:
        fh.write("not-json\n")
    failed = False
    try:
        load_consumed_request_ids(bad)
    except Exception:  # noqa: BLE001 - expected
        failed = True
    _assert(failed, "malformed registry line fails closed")
    return ("append-once verified, duplicate refused, malformed line fails "
            "closed (a3_train helpers, temp path only)")


def test_no_payload_inputs(root):
    paths, _points = _synthetic_panels(root)
    for name, path in paths.items():
        _assert(os.path.abspath(path).startswith(
            os.path.abspath(root)), "%s must live under the temp root" % name)
        _assert(not path.lower().endswith((".npz", ".pt")),
                "synthetic inputs are CSV only")
    return ("synthetic panels are temp-dir CSVs only; the global open() "
            "audit in run_self_check asserts 0 forbidden paths overall")


FIXTURES = (
    ("phi_normal_cdf", test_phi_normal_cdf),
    ("risk_policy_choice", test_risk_policy_choice),
    ("tree_gap_matching", test_tree_gap_matching),
    ("missing_unknown_accounting", test_missing_unknown_accounting),
    ("macro_pooled_consistency", test_macro_pooled_consistency),
    ("truth_cross_check", test_truth_cross_check),
    ("bootstrap_reproducible", test_bootstrap_reproducible),
    ("go_mutations", test_go_mutations),
    ("end_to_end_synthetic", test_end_to_end_synthetic),
    ("registry_append_duplicate", test_registry_append_duplicate),
    ("no_payload_inputs", test_no_payload_inputs),
)


def run_self_check(append_log=None):
    lines = []

    def emit(text=""):
        print(text)
        lines.append(text)

    emit("=" * 78)
    emit("A3 SCHEDULE-EVAL SELF-CHECK -- %s" % _utc_now())
    emit("mode: SYNTHETIC ONLY -- 0 real fits, 0 payload reads, 0 checkpoint "
         "reads, 0 prep re-reads, 0 GO created or consumed")
    emit("python %s | numpy %s | version %s"
         % (sys.version.split()[0], np.__version__, VERSION))
    emit("code_sha256: %s"
         % json.dumps({"schedule_eval.py":
                       hash_file(os.path.join(HERE, "schedule_eval.py"))},
                      sort_keys=True))
    emit("-" * 78)
    passed = failed = 0
    audit = _OpenAudit()
    tmp_root = tempfile.mkdtemp(prefix="sched_selfcheck_")
    try:
        with audit:
            for name, fn in FIXTURES:
                try:
                    detail = fn(tmp_root)
                    emit("[PASS] %-26s %s" % (name, detail))
                    passed += 1
                except Exception as exc:  # noqa: BLE001 - fail loud
                    failed += 1
                    emit("[FAIL] %-26s %s: %s"
                         % (name, type(exc).__name__, exc))
                    for ln in traceback.format_exc().rstrip().splitlines():
                        emit("       " + ln)
        forbidden = [p for p in audit.paths
                     if _is_forbidden_path(p, tempfile.gettempdir())]
        if forbidden:
            failed += 1
            emit("[FAIL] %-26s opened %d forbidden path(s): %r"
                 % ("no_payload_open_audit", len(forbidden), forbidden[:3]))
        else:
            passed += 1
            emit("[PASS] %-26s %d paths opened, 0 forbidden (all under the "
                 "temp dir)" % ("no_payload_open_audit", len(audit.paths)))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    emit("-" * 78)
    emit("SUMMARY: %d passed, %d failed, %d total"
         % (passed, failed, passed + failed))
    emit("REAL PAYLOAD READS: 0. CHECKPOINT READS: 0. FITS: 0. PREP "
         "RE-READS: 0.")
    emit("NO GO CREATED. NO GO CONSUMED. NO RECEIPT OUTSIDE THE TEMP FIXTURE.")
    emit("RESULT: %s" % ("OK (%d passed / %d failed)" % (passed, failed)
                         if failed == 0 else "FAILED (%d failed)" % failed))
    if append_log:
        block = ("\n===== schedule_eval self-check %s =====\n" % _utc_now()) \
            + "\n".join(lines) + "\n"
        with open(append_log, "a", encoding="utf-8") as fh:
            fh.write(block)
        print("APPENDED %d lines to %s (append-only, no truncation)"
              % (len(lines) + 2, append_log))
    return 0 if failed == 0 else 1


# ------------------------------------------------------------------------ CLI
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="A3 R3 schedule-value evaluation over saved prediction "
                    "panels: synthetic self-check by default; real evaluation "
                    "only under an APPROVED, unconsumed SCHEDULE-EVAL GO.")
    p.add_argument("--self-check", action="store_true",
                   help="run all synthetic fixtures (default behaviour)")
    p.add_argument("--run", metavar="GO.json", default=None,
                   help="guarded evaluation path; requires the GO")
    p.add_argument("--alpha", type=float, nargs="+",
                   default=list(ALPHAS_DEFAULT),
                   help="risk alphas (pinned by the GO)")
    p.add_argument("--eol-threshold", type=float, default=EOL_DEFAULT,
                   help="EOL threshold in Ah (pinned by the GO)")
    p.add_argument("--menu", type=float, nargs="+",
                   default=list(MENU_DEFAULT),
                   help="inspection-interval menu in weeks (pinned by the GO)")
    p.add_argument("--gap-tolerance", type=float, default=GAP_TOL_DEFAULT,
                   help="tree gap-to-horizon matching tolerance in weeks")
    p.add_argument("--bootstrap-n", type=int, default=BOOTSTRAP_N_DEFAULT)
    p.add_argument("--bootstrap-seed", type=int,
                   default=BOOTSTRAP_SEED_DEFAULT)
    p.add_argument("--append-log", default=None,
                   help="append self-check output to this log (append-only)")
    p.add_argument("--registry", default=DEFAULT_CONSUMED_REGISTRY,
                   help="consumed-GO registry (self-check fixtures always use "
                        "temp paths)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.run and args.self_check:
        print("REFUSED -- choose either --self-check or --run, not both")
        return 2
    if args.run:
        print_header("RUN (GO-gated, panel-only)")
        return run_go(args.run, args, args.registry)
    print_header("SELF-CHECK (synthetic only)")
    return run_self_check(append_log=args.append_log)


if __name__ == "__main__":
    sys.exit(main())
