#!/home/yndx/miniconda3/envs/a40_env/bin/python3.9
"""Tree subset-retrain entry point: R2 stage B (A3-vs-trees data efficiency).

Retrains the two strong tree baselines F0_hgb and F2_hgb on the frozen A3
fraction pools (f25 = 31 cells, f50 = 62 cells) and emits predictions on the
FROZEN C3 query panels of the original pipelines, so the existing compare
scripts (compare_a3_vs_all.py / compare_frac.py) can join them by the same
keys (cell_id, arm, round(query_epoch,5), round(forecast_h_weeks,6)).

GO-gated like run_baselines.py / run_extension.py; the default behaviour (no
arguments, or --self-check) is a synthetic self-check with ZERO real fits,
ZERO payload reads (data/, reports/), ZERO C4 access and ZERO GO consumed.

Safety design (mirrors the house guards; no new guard type is introduced)
--------------------------------------------------------------------------
* Self-check mode runs synthetic fixtures only: no payload (data/, reports/),
  no real feature cache npz (only temp stand-ins), no real consumed-GO
  registry (temp registries only), no GO created or consumed, no file written
  outside the system temp dir except the APPENDED SELF_CHECK_LOG.txt (unless
  --no-log-append).
* --run-train refuses to do anything unless it is given an APPROVED, fresh,
  unconsumed GO that pins: the sha256 of tree_frac.py itself; the two frozen
  fraction pools (label f25/f50 -> cells_file path + sha256); every input
  table (cohort, data manifest, the 5 nextcap cache files) path + sha256;
  the two frozen panel reference predictions_c3.csv path + sha256; the
  frozen HGB model_config; the feature dims; seed 42; threads 4 / cpu;
  fits_in_this_go == FITS_IN_GO (12 HGB fits = 2 pools x 2 models x
  [2 OOF folds + 1 final]); a fresh out_dir inside this experiment directory;
  and a request_id absent from /home/yndx/zxk/rul/experiments/state/
  consumed_gos.jsonl.  After a fully successful run it APPENDS the
  request_id to that registry (append-once, duplicate-refusing; same 3-field
  line format as a3_train.register_consumed_go).
* Subset semantics (frozen): for each pool P in {f25, f50} the training cell
  set is  P ∩ {cohort roles == "train"}  (the pipelines' original C1/C2 125
  train cells; the pool lists are subsets, the intersection is taken anyway
  and its size is recorded honestly).  Everything else is reused verbatim
  from the two frozen pipelines:
  - F0_hgb (trajectory_strong_baselines_20261021/run_baselines.py):
    features = V18 74-dim causal x_query + next_query_elapsed_weeks (75),
    per-cell inverse-count sample weights, OOF sigma = cell-balanced
    weighted RMS of the two cell-isolated seed-42 fold residuals
    (hgb_models._two_cell_folds), HGB(max_iter=150, max_leaf_nodes=15,
    l2_regularization=1, random_state=42, early_stopping=False), C3
    predictions on the full development rows, CSV columns exactly the 17
    columns of q4_strong_baselines_20261021_run2/predictions_c3.csv with
    model="hgb" (the compare scripts map the missing panel column to F0).
  - F2_hgb (trajectory_multisource_nextcap_20261021/run_extension.py):
    features = frozen cache F2 matrix (98) + h (99), per-cell inverse-count
    weights, OOF sigma = unweighted mean over cells of the per-cell mean
    squared OOF residual, same HGB config, C3 predictions on the full
    development cache rows, CSV columns exactly the 11 columns of
    nextcap18-9e7d9cb1c67f/predictions_c3.csv with model="hgb", panel="F2".
  - The C3 query panel is NOT redesigned: predictions are generated on the
    dev rows rebuilt by the pipelines' own deterministic dev path, then
    resolved against the pinned reference predictions_c3.csv under
    panel_key_policy:
      * "exact" (RUN1 default): predicted keys must equal the reference
        keys; any deviation refuses;
      * "subset": predicted keys must be a subset of the reference keys;
      * "reference_filter" (RUN2): rows whose compare key is outside the
        reference are DROPPED and counted (n_predicted_full / n_kept /
        n_dropped, with arm/cell distributions); every kept key must match
        the reference target within 1e-7 Ah (drift refuses); reference keys
        without a prediction are ALLOWED and recorded (n_missing_reference,
        warning only).  The CSV is written from the kept rows.
    Targets of matched keys must always equal the reference targets within
    1e-7 Ah.
  - RUN1 root cause (fixed): the dev-side loader loaded train+development
    cells when unrestricted, so the F0 prediction panel contained 6498
    train-cohort rows on top of the 3579 development rows (F2 was
    unaffected because its dev side is cache-meta driven).  The loader now
    loads development-role cells only for the panel side and requires an
    explicit restrict_to set for train cells; the reference panel IS the
    full development grid, not a post-hoc filtered product.
  - TREE_FRAC_F25_F50_20261024_RUN1 is burned (BURNED_REQUEST_IDS): it
    failed at the panel assertion after 3 real fits, wrote no predictions
    and was never registered, but is treated as consumed by convention.
* Payload discipline: --run-train only opens payload JSONs for cells with
  cohort role "train" (restricted to the pool intersection) or
  "development"; every payload is sha-verified against data_manifest.json
  and role-checked by data_adapter.normalize_cell (allowed roles
  train/development only), so C4 cells cannot be opened even by accident.
  The F2 feature matrices come from the frozen nextcap cache npz exactly as
  in run_extension.py.  Self-check opens none of these.

REUSE vs ADAPTATION NOTE: the fit/OOF/sigma mechanics below are line-level
adaptations of run_baselines.py (rows_for, fit, pred, prediction-row
emitter) and run_extension.py (split_rows, X, sw, recorded_fit, prediction
emitter) with exactly one delta: the training row set is restricted to the
pool intersection.  The dev-side code paths are the same computations as the
original runs.  make_examples/build_targets are per-cell independent, so
building targets from pool cells only yields exactly the original targets of
those cells.  The consumed-GO registry helpers reimplement a3_train's
semantics locally (same 3 fields, sort_keys, fsync, duplicate-refusing,
fail-closed on malformed lines) so that --run-train does not import the
torch stack; the self-check asserts the format equivalence.  The open-audit
harness is a3_fixtures (imported unchanged).
"""
from __future__ import annotations

import argparse
import csv
import datetime
import fcntl
import hashlib
import json
import math
import os
import signal
import sys
import time
import traceback
from pathlib import Path

import numpy as np

# ------------------------------------------------------------------ constants
ROOT = Path("/home/yndx/zxk/rul")
HERE = ROOT / "experiments/multirate_state_A3_rate_20261024"
SELF_CHECK_LOG_NAME = "SELF_CHECK_LOG.txt"
DEFAULT_CONSUMED_REGISTRY = str(ROOT / "experiments/state/consumed_gos.jsonl")
STATE = ROOT / "automation/state/coordinator.json"
LOCK_PATHS = (
    ROOT / "automation/state/online_survival_cpu.lock",
    ROOT / "automation/locks/isu_irregular_rul_cpu.lock",
)
COHORT = ROOT / "reports/isu_ilcc_capacity_probe_20261020_root/cohort.json"
MANIFEST = ROOT / "reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json"
DATA = ROOT / "data/processed/ISU_ILCC_DataV2_v1"
V18 = ROOT / "experiments/dart_rul_v18"
MECH = ROOT / "experiments/multisource_mechanisms_20261021"
OLD = ROOT / "experiments/isu_irregular_rul_seed42_v1"
CACHE = ROOT / "experiments/multisource_factorial_20261021/run2_clocksafe"
F0_RUN = ROOT / ("experiments/trajectory_strong_baselines_20261021/"
                 "runs/q4_strong_baselines_20261021_run2")
F2_RUN = ROOT / ("experiments/trajectory_multisource_nextcap_20261021/"
                 "runs/nextcap18-9e7d9cb1c67f")
PANEL_REF_F0 = F0_RUN / "predictions_c3.csv"
PANEL_REF_F2 = F2_RUN / "predictions_c3.csv"
POOL_LABELS = ("f25", "f50")
PANELS = ("F0", "F2")
MODELS = ("hgb",)
# Fit accounting (RUN2 fix): every (pool x model) arm costs exactly 3 HGB
# fits -- two cell-isolated OOF folds (hgb_models._two_cell_folds, seed 42)
# feeding the OOF sigma, plus one all-rows final fit -- so a full
# 2-pool x 2-model GO is 12 HGB fits, not 4.  Derived from the structure
# below so the gate, the receipts and the fixture suite can never drift
# apart again.  The gate's strict go["fits_in_this_go"] == FITS_IN_GO is
# unchanged.
OOF_FOLDS_PER_POOL_MODEL = 2
FINAL_FITS_PER_POOL_MODEL = 1
FITS_PER_POOL_MODEL = OOF_FOLDS_PER_POOL_MODEL + FINAL_FITS_PER_POOL_MODEL
FITS_IN_GO = FITS_PER_POOL_MODEL * len(POOL_LABELS) * len(PANELS)  # = 12
SEED = 42
THREADS = 4
DEVICE = "cpu"
MIN_RUNTIME_SECONDS = 60
MAX_RUNTIME_SECONDS = 21600
STALE_SECONDS = 86400.0
TARGET_TOL = 1e-7
EXPECTED_FEATURE_DIMS = {"F0": 74, "F2": 98}
FROZEN_HGB_CONFIG = {"max_iter": 150, "max_leaf_nodes": 15,
                     "l2_regularization": 1, "random_state": 42,
                     "early_stopping": False}
# Exact headers of the two frozen reference predictions_c3.csv (copied from
# the files; run-train re-verifies against the pinned reference CSV itself).
F0_HEADER = ["model", "cell_id", "group_id", "arm", "query_epoch",
             "forecast_h_weeks", "next_source_elapsed_weeks",
             "next_query_elapsed_weeks", "last_visible_capacity_ah",
             "last_visible_soh", "degradation_stage",
             "target_next_capacity_ah", "predicted_mean_ah",
             "predicted_sigma_ah", "error_ah", "abs_error_ah", "known_event"]
F2_HEADER = ["model", "panel", "cell_id", "arm", "query_epoch",
             "forecast_h_weeks", "target_capacity_ah", "predicted_capacity_ah",
             "sigma_oof_ah", "error_ah", "abs_error_ah"]
# Production pin map: input slot -> frozen absolute path (the gate refuses a
# GO that pins any other path for the same slot; the self-check passes a temp
# stand-in map so the gate code path is identical without touching real data).
PRODUCTION_INPUT_PATHS = {
    "cohort_json": str(COHORT),
    "data_manifest_json": str(MANIFEST),
    "cache_train_features_npz": str(CACHE / "train_features.npz"),
    "cache_development_features_npz": str(CACHE / "development_features.npz"),
    "cache_train_rows_jsonl": str(CACHE / "train_rows.jsonl"),
    "cache_development_rows_jsonl": str(CACHE / "development_rows.jsonl"),
    "cache_feature_schema_json": str(CACHE / "feature_schema.json"),
}
PRODUCTION_PANEL_PATHS = {"F0": str(PANEL_REF_F0), "F2": str(PANEL_REF_F2)}
REQUIRED_INPUT_SLOTS = tuple(sorted(PRODUCTION_INPUT_PATHS))
WEEK = 604800.0
SIGMA_SOURCE = ("pipeline OOF sigma recomputed on the fraction-pool train "
                "rows: F0 cell-balanced weighted RMS of two cell-isolated "
                "seed-42 fold residuals; F2 unweighted mean of per-cell mean "
                "squared OOF residuals")
CODE_FILE = "tree_frac.py"
# Request ids treated as burned even though they never reached the consumed-GO
# registry (by convention a failed run's request_id must never be
# re-presented):
# - RUN1 failed at the panel assertion after 3 real fits (train-cohort rows
#   leaked into the F0 dev panel; loader fixed), wrote no predictions;
# - RUN2 executed ALL 12 HGB fits and wrote all four prediction CSVs, but
#   FAILED at the (then stale) fits_in_this_go=4 budget check and was never
#   registered -- its outputs carry FAILED/unconsumed status, so RUN3 is the
#   clean path and RUN2 must not be re-presented.
BURNED_REQUEST_IDS = ("TREE_FRAC_F25_F50_20261024_RUN1",
                      "TREE_FRAC_F25_F50_20261024_RUN2")
PANEL_KEY_POLICIES = ("exact", "subset", "reference_filter")


# ------------------------------------------------------------------ utilities
def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1048576), b""):
            h.update(b)
    return h.hexdigest()


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def atomic_json(p, x):
    p = Path(p)
    t = p.with_suffix(p.suffix + ".tmp")
    t.write_text(json.dumps(x, indent=2, ensure_ascii=False, allow_nan=True),
                 encoding="utf-8")
    os.replace(str(t), str(p))


def csv_write(path, rows, fieldnames):
    """csv.DictWriter with an explicit header, as in both pipelines."""
    with open(path, "x", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(fieldnames))
        w.writeheader()
        w.writerows(rows)


def panel_key(cell_id, arm, query_epoch, h_weeks):
    """The compare scripts' query key (compare_a3_vs_all.py / compare_frac.py)."""
    return (str(cell_id), str(arm), round(float(query_epoch), 5),
            round(float(h_weeks), 6))


# ------------------------------------------------- consumed-GO registry (local
# reimplementation with a3_train.register_consumed_go's exact semantics)
def load_consumed_request_ids(path):
    consumed = set()
    if not os.path.exists(path):
        return consumed
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)  # malformed line -> raises (fail-closed)
            rid = rec.get("request_id")
            if not rid:
                raise ValueError("consumed-GO registry line without "
                                 "request_id in %s" % path)
            consumed.add(str(rid))
    return consumed


def request_id_is_fresh(request_id, path=DEFAULT_CONSUMED_REGISTRY):
    return str(request_id) not in load_consumed_request_ids(path)


def register_consumed_go(path, request_id, go_sha256, finished_utc):
    rid = str(request_id)
    if rid in load_consumed_request_ids(path):
        raise RuntimeError("request_id %r already registered in %s -- GO "
                           "double consumption refused" % (rid, path))
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    line = json.dumps({"request_id": rid, "go_sha256": str(go_sha256),
                       "finished_utc": str(finished_utc)},
                      ensure_ascii=True, sort_keys=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())
    return line


# ------------------------------------------------------------- pool utilities
def load_pool_file(path, expected_sha256):
    """Load a frozen fraction-pool cell list; fail-closed on any deviation."""
    if not os.path.exists(path):
        raise ValueError("pool cells_file missing: %s" % path)
    got = sha_file(path)
    if str(expected_sha256).lower() != got.lower():
        raise ValueError("pool cells_file sha256 mismatch: %s" % path)
    with open(path, "r", encoding="utf-8") as f:
        cells = json.load(f)
    if not isinstance(cells, list) or len(cells) < 2:
        raise ValueError("pool cells_file must be a JSON list of >= 2 ids")
    ids = [str(c) for c in cells]
    if any(not c for c in ids):
        raise ValueError("pool cells_file contains an empty id")
    if len(set(ids)) != len(ids):
        raise ValueError("pool cells_file contains duplicate cell ids")
    return sorted(ids)


def pool_train_intersection(pool_ids, cohort_roles):
    """Frozen subset semantics: pool ∩ {roles == 'train'}; sizes recorded."""
    train = {str(c) for c, r in cohort_roles.items() if r == "train"}
    inter = sorted(set(str(c) for c in pool_ids) & train)
    return inter, {"n_pool": len(pool_ids), "n_train_cohort": len(train),
                   "n_intersection": len(inter),
                   "outside_train_cohort": sorted(set(str(c) for c in pool_ids)
                                                  - train)}


# ---------------------------------------------------------------- GO validation
REQUIRED_GO_FIELDS = (
    "status", "allow_fit", "scope", "request_id", "owner_thread_id",
    "issued_utc", "code_sha256", "seed", "fits_in_this_go", "threads",
    "device", "max_runtime_seconds", "pools", "inputs", "panel_references",
    "model_config", "feature_dims", "out_dir",
)


def validate_go_tree(go_path, registry_path=DEFAULT_CONSUMED_REGISTRY,
                     expected_input_paths=None, expected_panel_paths=None,
                     expected_out_root=None, now=None, code_sha=None):
    """Flat, self-contained GO gate for the tree subset retrain.

    Returns (problems, go); never consumes, never writes.  expected_* maps
    default to the frozen production paths/root (self-check passes temp
    stand-ins so the identical gate code is exercised without real data).
    """
    problems = []
    if expected_input_paths is None:
        expected_input_paths = PRODUCTION_INPUT_PATHS
    if expected_panel_paths is None:
        expected_panel_paths = PRODUCTION_PANEL_PATHS
    if expected_out_root is None:
        expected_out_root = str(HERE)
    if code_sha is None:
        code_sha = sha_file(os.path.abspath(__file__))
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    try:
        with open(go_path, "r", encoding="utf-8") as f:
            go = json.load(f)
    except Exception as exc:  # noqa: BLE001 - fail closed
        return ["GO file unreadable as JSON: %s" % exc], None
    if not isinstance(go, dict):
        return ["GO must be a JSON object"], None
    for k in REQUIRED_GO_FIELDS:
        if k not in go:
            problems.append("GO missing required field %r" % k)
    if problems:
        return problems, go
    # -- approval
    if go["status"] != "APPROVED":
        problems.append("GO status must be APPROVED; got %r" % go["status"])
    if go["allow_fit"] is not True:
        problems.append("GO allow_fit must be true")
    if "allow_C4" in go and go["allow_C4"]:
        problems.append("GO allow_C4 must not be true (C4 is locked)")
    # -- scope: TREE-FRAC and TRAIN/FIT
    scope = go.get("scope")
    if not isinstance(scope, str) or not scope:
        problems.append("GO scope must be a non-empty string")
    else:
        up = scope.upper()
        if "TREE-FRAC" not in up:
            problems.append("GO scope does not name TREE-FRAC")
        if "TRAIN" not in up or "FIT" not in up:
            problems.append("GO scope does not name TRAIN/FIT")
    # -- request_id freshness (and burned-run convention)
    rid = go["request_id"]
    if not isinstance(rid, str) or len(rid) < 8:
        problems.append("GO request_id must be a string of >= 8 chars")
    else:
        if rid in BURNED_REQUEST_IDS:
            problems.append("request_id %r is burned (failed run treated as "
                            "consumed); use a fresh request_id" % rid)
        try:
            if not request_id_is_fresh(rid, registry_path):
                problems.append("request_id %r already appears in the "
                                "consumed-GO registry %s"
                                % (rid, registry_path))
        except Exception as exc:  # noqa: BLE001 - fail closed
            problems.append("consumed-GO registry %s unreadable: %s"
                            % (registry_path, exc))
    # -- owner
    if not isinstance(go["owner_thread_id"], str) or \
            not go["owner_thread_id"].strip():
        problems.append("GO owner_thread_id must be a non-empty string")
    # -- freshness of issue
    try:
        issued = datetime.datetime.fromisoformat(
            str(go["issued_utc"]).replace("Z", "+00:00"))
        if issued.tzinfo is None:
            issued = issued.replace(tzinfo=datetime.timezone.utc)
        age = (now - issued).total_seconds()
        if abs(age) > STALE_SECONDS:
            problems.append("GO stale (issued_utc %s, age %.0f s)"
                            % (go["issued_utc"], age))
    except ValueError:
        problems.append("GO issued_utc is not an ISO timestamp: %r"
                        % go["issued_utc"])
    # -- pinned code: this file itself
    code = go["code_sha256"]
    if not isinstance(code, dict) or CODE_FILE not in code:
        problems.append("GO code_sha256 must pin %s" % CODE_FILE)
    elif str(code[CODE_FILE]).lower() != code_sha.lower():
        problems.append("GO code_sha256[%s] mismatch: go=%s actual=%s"
                        % (CODE_FILE, str(code[CODE_FILE])[:16],
                           code_sha[:16]))
    # -- run contract
    if go["seed"] != SEED:
        problems.append("GO seed must be %d (frozen pipeline seed); got %r"
                        % (SEED, go["seed"]))
    try:
        if int(go["fits_in_this_go"]) != FITS_IN_GO:
            problems.append("GO fits_in_this_go must be %d; got %r"
                            % (FITS_IN_GO, go["fits_in_this_go"]))
    except (TypeError, ValueError):
        problems.append("GO fits_in_this_go must be the integer %d"
                        % FITS_IN_GO)
    if go["threads"] != THREADS or go["device"] != DEVICE:
        problems.append("GO threads/device must be %d/%s; got %r/%r"
                        % (THREADS, DEVICE, go["threads"], go["device"]))
    try:
        rt = int(go["max_runtime_seconds"])
        if not MIN_RUNTIME_SECONDS <= rt <= MAX_RUNTIME_SECONDS:
            problems.append("GO max_runtime_seconds must be within [%d, %d]; "
                            "got %d" % (MIN_RUNTIME_SECONDS,
                                        MAX_RUNTIME_SECONDS, rt))
    except (TypeError, ValueError):
        problems.append("GO max_runtime_seconds must be an integer")
    # -- pools: exactly the two frozen fraction labels
    pools = go["pools"]
    if not isinstance(pools, dict) or sorted(pools) != sorted(POOL_LABELS):
        problems.append("GO pools must have exactly the labels %r; got %r"
                        % (sorted(POOL_LABELS),
                           sorted(pools) if isinstance(pools, dict) else pools))
    else:
        for label, spec in sorted(pools.items()):
            if not isinstance(spec, dict) or "cells_file" not in spec or \
                    "cells_sha256" not in spec:
                problems.append("GO pools[%r] must pin cells_file + "
                                "cells_sha256" % label)
                continue
            p = str(spec["cells_file"])
            if not os.path.exists(p):
                problems.append("GO pools[%r].cells_file missing: %s"
                                % (label, p))
                continue
            if str(spec["cells_sha256"]).lower() != sha_file(p).lower():
                problems.append("GO pools[%r].cells_sha256 mismatch" % label)
                continue
            try:
                load_pool_file(p, spec["cells_sha256"])
            except ValueError as exc:
                problems.append("GO pools[%r]: %s" % (label, exc))
    # -- inputs: exact frozen paths + shas
    inputs = go["inputs"]
    if not isinstance(inputs, dict):
        problems.append("GO inputs must be a mapping")
    else:
        for slot in REQUIRED_INPUT_SLOTS:
            spec = inputs.get(slot)
            if not isinstance(spec, dict) or "path" not in spec or \
                    "sha256" not in spec:
                problems.append("GO inputs[%r] must pin path + sha256" % slot)
                continue
            want = expected_input_paths[slot]
            if os.path.realpath(str(spec["path"])) != os.path.realpath(want):
                problems.append("GO inputs[%r].path must be the frozen %s; "
                                "got %r" % (slot, want, spec["path"]))
                continue
            if not os.path.exists(spec["path"]):
                problems.append("GO inputs[%r].path missing: %s"
                                % (slot, spec["path"]))
                continue
            if str(spec["sha256"]).lower() != sha_file(spec["path"]).lower():
                problems.append("GO inputs[%r].sha256 mismatch" % slot)
    # -- panel references: the two frozen predictions_c3.csv
    refs = go["panel_references"]
    if not isinstance(refs, dict) or sorted(refs) != sorted(PANELS):
        problems.append("GO panel_references must have exactly the keys %r"
                        % (sorted(PANELS),))
    else:
        for panel, spec in sorted(refs.items()):
            if not isinstance(spec, dict) or "path" not in spec or \
                    "sha256" not in spec:
                problems.append("GO panel_references[%r] must pin path + "
                                "sha256" % panel)
                continue
            want = expected_panel_paths[panel]
            if os.path.realpath(str(spec["path"])) != os.path.realpath(want):
                problems.append("GO panel_references[%r].path must be the "
                                "frozen %s; got %r"
                                % (panel, want, spec["path"]))
                continue
            if not os.path.exists(spec["path"]):
                problems.append("GO panel_references[%r].path missing: %s"
                                % (panel, spec["path"]))
                continue
            if str(spec["sha256"]).lower() != sha_file(spec["path"]).lower():
                problems.append("GO panel_references[%r].sha256 mismatch"
                                % panel)
    # -- frozen model config
    if go["model_config"] != {"hgb": FROZEN_HGB_CONFIG}:
        problems.append("GO model_config must equal the frozen HGB config "
                        "%r" % ({"hgb": FROZEN_HGB_CONFIG},))
    # -- frozen feature dims
    if go["feature_dims"] != EXPECTED_FEATURE_DIMS:
        problems.append("GO feature_dims must equal %r; got %r"
                        % (EXPECTED_FEATURE_DIMS, go["feature_dims"]))
    # -- panel key policy
    if go.get("panel_key_policy", "exact") not in PANEL_KEY_POLICIES:
        problems.append("GO panel_key_policy must be one of %r; got %r"
                        % (list(PANEL_KEY_POLICIES),
                           go.get("panel_key_policy")))
    # -- fresh out_dir inside the expected root (production: this experiment
    #    directory; self-check: the temp fixture root)
    out_dir = go["out_dir"]
    if not isinstance(out_dir, str) or not out_dir:
        problems.append("GO out_dir must be a non-empty string")
    else:
        rp = os.path.realpath(out_dir)
        if os.path.exists(rp):
            problems.append("GO out_dir already exists (must be fresh): %s"
                            % out_dir)
        if Path(os.path.realpath(expected_out_root)) not in Path(rp).parents:
            problems.append("GO out_dir must live inside %s; got %s"
                            % (expected_out_root, out_dir))
    return problems, go


# ------------------------------------------------------------- shared loaders
def load_cells_restricted(cohort_path, manifest_path, roles=("development",),
                          restrict_to=None):
    """load_split restricted to the requested cohort roles.

    Mirrors isu_irregular_rul_seed42_v1.train_eval.load_split (manifest
    status PASS, manifest files == frozen train/dev IDs, per-payload sha
    verification, normalize_cell role check) but only opens the payloads it
    needs.  Role handling (RUN1 root-cause fix):
    - roles=("development",) -> exactly the development cells (the original
      pipelines' C3 panel side; 63 cells);
    - roles=("train",) -> train cells INTERSECTED with restrict_to (the
      pool intersection); restrict_to=None/empty is refused (fail-closed:
      never silently load all 125 train payloads).
    C4/locked cells are not in these roles and are never opened.
    """
    if not roles or set(roles) - {"train", "development"}:
        raise ValueError("roles must be a non-empty subset of "
                         "{'train','development'}; got %r" % (roles,))
    if "train" in roles and not restrict_to:
        raise ValueError("loading train payloads requires an explicit "
                         "restrict_to set (pool intersection); refused to "
                         "load all train cells")
    sys.path.insert(0, str(OLD))
    from data_adapter import load_reviewed_cell
    cohort = json.loads(Path(cohort_path).read_text())
    manifest = json.loads(Path(manifest_path).read_text())
    roles_c = cohort["roles"]
    files = manifest.get("files", {})
    if manifest.get("status") != "PASS":
        raise RuntimeError("data manifest qualification is not PASS")
    allowed = {c for c, r in roles_c.items()
               if r in ("train", "development")}
    if set(files) != allowed:
        raise RuntimeError("manifest must exactly match frozen train/dev IDs")
    cells = []
    for role in roles:
        for cid in sorted(c for c, r in roles_c.items() if r == role):
            if role == "train":
                if cid not in restrict_to:
                    continue
            p = Path(DATA) / (cid + ".json")
            if not p.is_file() or sha_file(p) != files[cid].get("sha256"):
                raise RuntimeError("record missing/hash mismatch " + cid)
            x = load_reviewed_cell(p, role)
            if x["cell_id"] != cid:
                raise RuntimeError("record ID mismatch")
            cells.append(x)
    return cells


# ------------------------------------------------------- F0 path (verbatim
# mechanics of run_baselines.rows_for / fit / pred, subset delta only)
def rows_for_f0(cells):
    sys.path[:0] = [str(V18), str(MECH / "train_v1")]
    from data_protocol import make_examples
    from targets import build_targets
    nominal = {str(c["cell_id"]): float(c["nominal_capacity_ah"])
               for c in cells}
    out = []
    for r in build_targets(make_examples(cells), cells):
        h = r.get("next_query_elapsed_weeks")
        y = r.get("next_capacity_ah")
        if y is None or h is None or not math.isfinite(float(h)) or \
                float(h) <= 0:
            continue
        x = np.asarray(r["x_query"], float)
        if x.shape != (74,):
            raise ValueError("feature dimension not 74")
        out.append({**r, "features": np.r_[x, float(h)],
                    "target": float(y), "h": float(h),
                    "lastcap": float(r["visible_records"][-1]["capacityAh"]),
                    "nominal": nominal[str(r["cell_id"])],
                    "lastsoh": float(r["visible_records"][-1]["capacityAh"])
                    / nominal[str(r["cell_id"])]})
    return out


def new_hgb():
    from sklearn.ensemble import HistGradientBoostingRegressor
    return HistGradientBoostingRegressor(**FROZEN_HGB_CONFIG)


def _weights(rows, key):
    counts = {}
    for r in rows:
        counts[r[key]] = counts.get(r[key], 0) + 1
    return np.array([1 / counts[r[key]] for r in rows])


def _fit_hgb(rows):
    m = new_hgb()
    m.fit(np.stack([r["features"] for r in rows]),
          [r["target"] for r in rows], sample_weight=_weights(rows, "cell_id"))
    return m


def _pred_hgb(m, rows):
    return np.asarray(m.predict(np.stack([r["features"] for r in rows])),
                      float).reshape(-1)


def _fit_arrays(x, y, w):
    m = new_hgb()
    m.fit(x, y, sample_weight=w)
    return m


def two_cell_folds(rows, seed):
    sys.path.insert(0, str(V18))
    from hgb_models import _two_cell_folds
    return _two_cell_folds(rows, seed)


def _ordered_folds(folds):
    return sorted(folds, key=lambda s: sorted(s)[0])


def oof_fit_f0(tr_rows, seed, record_fit, out_dir, rec, deadline):
    """F0 OOF + final fit; run_baselines fit/OOF mechanics on the subset."""
    train_ids = {r["cell_id"] for r in tr_rows}
    folds = two_cell_folds(tr_rows, seed)
    if len(folds) != 2 or sorted(len(x) for x in folds) != \
            [len(train_ids) // 2, (len(train_ids) + 1) // 2]:
        raise ValueError("V18 seed42 eligible folds not balanced")
    if set.union(*folds) != train_ids or set.intersection(*folds):
        raise ValueError("V18 folds do not partition eligible cells")
    oof = np.full(len(tr_rows), np.nan)
    for fi, held in enumerate(_ordered_folds(folds)):
        fit_idx = [i for i, z in enumerate(tr_rows) if z["cell_id"] not in held]
        test_idx = [i for i, z in enumerate(tr_rows) if z["cell_id"] in held]
        m = record_fit({"model": "hgb", "panel": "F0", "fold": fi,
                        "held_cells": sorted(held), "n_fit": len(fit_idx)},
                       out_dir, rec, deadline,
                       lambda ii=tuple(fit_idx): _fit_hgb([tr_rows[i]
                                                           for i in ii]))
        pr = _pred_hgb(m, [tr_rows[i] for i in test_idx])
        for j, p in zip(test_idx, pr):
            oof[j] = p
    if not np.isfinite(oof).all():
        raise ValueError("OOF incomplete")
    w = _weights(tr_rows, "cell_id")
    res = np.array([r["target"] for r in tr_rows]) - oof
    sig = max(float(np.sqrt(np.sum(w * res * res) / np.sum(w))), 1e-6)
    m = record_fit({"model": "hgb", "panel": "F0", "fold": "all",
                    "n_fit": len(tr_rows)},
                   out_dir, rec, deadline, lambda: _fit_hgb(tr_rows))
    return m, sig, oof, [sorted(x) for x in folds]


def oof_fit_f2(tr_rows, xs, ys, ws, seed, record_fit, out_dir, rec, deadline):
    """F2 OOF + final fit; run_extension fit/OOF mechanics on the subset."""
    train_ids = {r["cell"] for r in tr_rows}
    folds = two_cell_folds(tr_rows, seed)
    if set.union(*folds) != train_ids or set.intersection(*folds):
        raise ValueError("invalid OOF cell partition")
    oof = np.full(len(tr_rows), np.nan)
    for fi, held in enumerate(_ordered_folds(folds)):
        a = np.asarray([i for i, z in enumerate(tr_rows)
                        if z["cell"] not in held])
        b = np.asarray([i for i, z in enumerate(tr_rows)
                        if z["cell"] in held])
        m = record_fit({"model": "hgb", "panel": "F2", "fold": fi,
                        "held_cells": sorted(held), "n_fit": len(a)},
                       out_dir, rec, deadline,
                       lambda aa=a: _fit_arrays(xs[aa], ys[aa], ws[aa]))
        oof[b] = m.predict(xs[b])
    if not np.isfinite(oof).all():
        raise ValueError("OOF incomplete")
    by = {}
    for z, e in zip(tr_rows, ys - oof):
        by.setdefault(z["cell"], []).append(float(e * e))
    sigma = max(math.sqrt(float(np.mean([np.mean(v) for v in by.values()]))),
                1e-6)
    m = record_fit({"model": "hgb", "panel": "F2", "fold": "all",
                    "n_fit": len(ys)},
                   out_dir, rec, deadline, lambda: _fit_arrays(xs, ys, ws))
    return m, sigma, oof, [sorted(x) for x in folds]


# ------------------------------------------------- F2 cache path (verbatim
# mechanics of run_extension.split_rows / X / sw, restricted to pool cells)
def jsonl_rows(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def split_rows_tree(cache_dir, split, cells, expected_dim):
    sys.path[:0] = [str(V18), str(MECH / "train_v1")]
    from data_protocol import make_examples
    from targets import build_targets
    ex = make_examples(cells)
    targets = build_targets(ex, cells)
    tm = {(str(r["cell_id"]), str(r["arm"]),
           round(float(r["query_epoch"]), 6)): r for r in targets}
    meta = jsonl_rows(Path(cache_dir) / (split + "_rows.jsonl"))
    z = np.load(Path(cache_dir) / (split + "_features.npz"),
                allow_pickle=False)
    if "F2" not in z.files:
        raise ValueError("cache npz missing F2 matrix")
    mats = z["F2"]
    if mats.shape != (len(meta), expected_dim) or np.isinf(mats).any():
        raise ValueError("feature cache shape/value error F2")
    rows = []
    for i, m in enumerate(meta):
        k = (str(m["cell_id"]), str(m["arm"]),
             round(float(m["query_epoch"]), 6))
        t = tm.get(k)
        if t is None or t.get("next_capacity_ah") is None:
            continue
        h = float(t["next_query_elapsed_weeks"])
        if math.isfinite(h) and h > 0:
            rows.append({"key": k, "idx": i, "cell": k[0],
                         "cell_id": k[0], "arm": k[1], "q": k[2], "h": h,
                         "y": float(t["next_capacity_ah"])})
    if len({r["key"] for r in rows}) != len(rows):
        raise ValueError("duplicate eligible target keys")
    return rows, mats


def f2_matrix(rows, mats):
    return np.column_stack((mats[[r["idx"] for r in rows]].astype(float),
                            [r["h"] for r in rows]))


def f2_weights(rows):
    return _weights(rows, "cell")


# ------------------------------------------------------- panel reference I/O
def read_panel_reference(path, kind):
    """Frozen C3 query panel keys (+targets) from a saved predictions_c3.csv."""
    header = F0_HEADER if kind == "F0" else F2_HEADER
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if list(reader.fieldnames) != header:
            raise ValueError("panel reference %s header mismatch: %r"
                             % (path, reader.fieldnames))
        keys, targets = set(), {}
        for r in reader:
            if kind == "F0":
                if r["model"] != "hgb":
                    continue
            else:
                if r["model"] != "hgb" or r["panel"] != "F2":
                    continue
            k = panel_key(r["cell_id"], r["arm"], r["query_epoch"],
                          r["forecast_h_weeks"])
            y = float(r["target_next_capacity_ah"] if kind == "F0"
                      else r["target_capacity_ah"])
            if k in keys:
                raise ValueError("duplicate panel reference key %r" % (k,))
            keys.add(k)
            targets[k] = y
    return keys, targets


def assert_panel_consistency(pred_rows, kind, ref_keys, ref_targets, policy,
                             target_tol=TARGET_TOL):
    """Frozen-panel contract: predicted keys ⊆ (or ==) the reference keys and
    identical targets on matched keys (compare-script key definition)."""
    pred_keys = set()
    for r in pred_rows:
        k = panel_key(r["cell_id"], r["arm"], r["query_epoch"],
                      r["forecast_h_weeks"])
        if k in pred_keys:
            raise ValueError("duplicate prediction key %r" % (k,))
        pred_keys.add(k)
    if policy == "exact":
        missing = ref_keys - pred_keys
        if missing:
            raise ValueError("panel key mismatch (exact policy): %d "
                             "reference keys not predicted, e.g. %r"
                             % (len(missing), sorted(missing)[:3]))
    extra = pred_keys - ref_keys
    if extra:
        raise ValueError("panel key mismatch: %d predicted keys outside the "
                         "frozen reference panel, e.g. %r"
                         % (len(extra), sorted(extra)[:3]))
    for r in pred_rows:
        k = panel_key(r["cell_id"], r["arm"], r["query_epoch"],
                      r["forecast_h_weeks"])
        y = float(r["target_next_capacity_ah"] if kind == "F0"
                  else r["target_capacity_ah"])
        if abs(y - ref_targets[k]) > target_tol:
            raise ValueError("target mismatch on frozen panel key %r" % (k,))
    return {"policy": policy, "n_pred_keys": len(pred_keys),
            "n_ref_keys": len(ref_keys), "subset_of_reference": True}


def _count_by(rows_or_keys, field, key_index=None):
    counts = {}
    for item in rows_or_keys:
        k = item[key_index] if key_index is not None else item[field]
        counts[k] = counts.get(k, 0) + 1
    return dict(sorted(counts.items()))


def apply_reference_filter(pred_rows, kind, ref_keys, ref_targets,
                           target_tol=TARGET_TOL):
    """panel_key_policy="reference_filter": keep only the rows whose compare
    key lies in the frozen reference panel; drop (and count) the rest.

    Contract (R2 stage B, RUN2):
    - kept keys: target must equal the reference target within target_tol
      (drift refuses, same assertion family as exact/subset);
    - predicted keys outside the reference are DROPPED, not refused
      (counted, distributions recorded);
    - reference keys with no prediction are ALLOWED (warn, never refuse --
      recorded as n_missing_reference with per-arm/per-cell distributions).
    Returns (kept_rows, stats dict)."""
    target_field = ("target_next_capacity_ah" if kind == "F0"
                    else "target_capacity_ah")
    kept, dropped, seen = [], [], set()
    for r in pred_rows:
        k = panel_key(r["cell_id"], r["arm"], r["query_epoch"],
                      r["forecast_h_weeks"])
        if k in seen:
            raise ValueError("duplicate prediction key %r" % (k,))
        seen.add(k)
        if k in ref_keys:
            if abs(float(r[target_field]) - ref_targets[k]) > target_tol:
                raise ValueError("kept-key target drift on frozen panel key "
                                 "%r: pred=%r ref=%r"
                                 % (k, r[target_field], ref_targets[k]))
            kept.append(r)
        else:
            dropped.append(r)
    kept_keys = {panel_key(r["cell_id"], r["arm"], r["query_epoch"],
                           r["forecast_h_weeks"]) for r in kept}
    missing = ref_keys - kept_keys
    stats = {
        "policy": "reference_filter",
        "n_predicted_full": len(pred_rows),
        "n_reference_keys": len(ref_keys),
        "n_kept": len(kept),
        "n_dropped": len(dropped),
        "n_missing_reference": len(missing),
        "dropped_by_arm": _count_by(dropped, "arm"),
        "dropped_by_cell": _count_by(dropped, "cell_id"),
        "missing_by_arm": _count_by(sorted(missing), None, key_index=1),
        "missing_by_cell": _count_by(sorted(missing), None, key_index=0),
    }
    return kept, stats


def resolve_panel(pred_rows, kind, ref_keys, ref_targets, policy,
                  target_tol=TARGET_TOL):
    """Unified frozen-panel handling; returns (final_rows, stats).

    - exact: predicted keys must equal the reference keys (unchanged
      RUN1 semantics);
    - subset: predicted keys must be a subset of the reference keys
      (unchanged RUN1 semantics);
    - reference_filter: rows outside the reference are dropped and counted
      (see apply_reference_filter); the CSV is written from the kept rows.
    """
    if policy == "reference_filter":
        return apply_reference_filter(pred_rows, kind, ref_keys, ref_targets,
                                      target_tol)
    assert_panel_consistency(pred_rows, kind, ref_keys, ref_targets, policy,
                             target_tol)
    pred_keys = {panel_key(r["cell_id"], r["arm"], r["query_epoch"],
                           r["forecast_h_weeks"]) for r in pred_rows}
    return pred_rows, {
        "policy": policy,
        "n_predicted_full": len(pred_rows),
        "n_reference_keys": len(ref_keys),
        "n_kept": len(pred_rows),
        "n_dropped": 0,
        "n_missing_reference": len(ref_keys - pred_keys),
        "dropped_by_arm": {}, "dropped_by_cell": {},
        "missing_by_arm": _count_by(sorted(ref_keys - pred_keys), None,
                                    key_index=1),
        "missing_by_cell": _count_by(sorted(ref_keys - pred_keys), None,
                                     key_index=0),
    }


# ------------------------------------------------------------- row emitters
def f0_prediction_rows(rows, means, sig):
    """run_baselines prediction-row emitter verbatim (hgb rows only)."""
    out = []
    for r, p in zip(rows, means):
        stage = ("gt0.95" if r["lastsoh"] > .95 else "0.90-0.95"
                 if r["lastsoh"] > .90 else "0.85-0.90"
                 if r["lastsoh"] > .85 else "le0.85")
        out.append({"model": "hgb", "cell_id": r["cell_id"],
                    "group_id": r["group_id"], "arm": r["arm"],
                    "query_epoch": r["query_epoch"],
                    "forecast_h_weeks": r["h"],
                    "next_source_elapsed_weeks": r["next_elapsed_weeks"],
                    "next_query_elapsed_weeks": r["next_query_elapsed_weeks"],
                    "last_visible_capacity_ah": r["lastcap"],
                    "last_visible_soh": r["lastsoh"],
                    "degradation_stage": stage,
                    "target_next_capacity_ah": r["target"],
                    "predicted_mean_ah": float(p),
                    "predicted_sigma_ah": sig,
                    "error_ah": float(p - r["target"]),
                    "abs_error_ah": abs(float(p - r["target"])),
                    "known_event": bool(r["known_event"])})
    return out


def f2_prediction_rows(rows, means, sig):
    """run_extension prediction-row emitter verbatim (hgb/F2 rows only)."""
    out = []
    for z, p in zip(rows, means):
        out.append({"model": "hgb", "panel": "F2", "cell_id": z["cell"],
                    "arm": z["arm"], "query_epoch": z["q"],
                    "forecast_h_weeks": z["h"],
                    "target_capacity_ah": z["y"],
                    "predicted_capacity_ah": float(p),
                    "sigma_oof_ah": sig,
                    "error_ah": float(p - z["y"]),
                    "abs_error_ah": abs(float(p - z["y"]))})
    return out


# ------------------------------------------------------------- fit recording
def make_record_fit(out_dir, rec, deadline):
    def record_fit(meta, _out_dir, _rec, _deadline, fit_fn):
        if time.monotonic() >= deadline:
            raise TimeoutError("GO runtime deadline reached before fit")
        rec["fits_started"] += 1
        idx = rec["fits_started"]
        t0 = time.time()
        m = fit_fn()
        if time.monotonic() >= deadline:
            raise TimeoutError("GO runtime deadline reached during fit")
        rec["fit_count"] += 1
        rec.setdefault("fits", []).append(
            {"fit_index": idx, **meta, "seconds": time.time() - t0,
             "finished_utc": datetime.datetime.now(
                 datetime.timezone.utc).isoformat()})
        atomic_json(Path(out_dir) / "progress.json", rec)
        return m
    return record_fit


def counting_record_fit(meta, _out_dir, rec, _deadline, fit_fn):
    """Self-check stand-in for make_record_fit (counts fits, no deadline)."""
    rec["fits_started"] = rec.get("fits_started", 0) + 1
    m = fit_fn()
    rec["fit_count"] = rec.get("fit_count", 0) + 1
    rec.setdefault("fits", []).append({"fit_index": rec["fit_count"], **meta})
    return m


# ------------------------------------------------------------- per-fit report
def fit_report(out_dir, name, *, pool_label, pool_info, train_cell_ids,
               hyperparams, sigma, sigma_source, input_shas, extra=None):
    rep = {
        "fit_name": name,
        "entry_point": CODE_FILE,
        "pool_label": pool_label,
        "pool_info": pool_info,
        "n_train_cells": len(set(train_cell_ids)),
        "train_cell_ids": sorted(set(train_cell_ids)),
        "model": "hgb",
        "hyperparams": hyperparams,
        "sigma_oof_ah": sigma,
        "sigma_source": sigma_source,
        "input_sha256": input_shas,
        "seed": SEED,
    }
    rep.update(extra or {})
    with open(Path(out_dir) / "fit_report.json", "x", encoding="utf-8") as f:
        json.dump(rep, f, indent=2, ensure_ascii=False, allow_nan=True)
    return rep


# ------------------------------------------------------------------ run-train
def run_train(go_path, registry_path=DEFAULT_CONSUMED_REGISTRY):
    t0 = time.time()
    out_dir = None
    rec = {"status": "PREFLIGHT_FAILED", "fit_count": 0, "fits_started": 0,
           "C4_payload_reads": 0, "payload_reads": 0, "fits": []}
    locks = []
    deadline = None
    timer_armed = False
    try:
        problems, go = validate_go_tree(go_path, registry_path)
        if problems:
            print("REFUSED -- GO validation failed:")
            for p in problems:
                print("  - %s" % p)
            return 3
        with open(go_path, "r", encoding="utf-8") as f:
            if json.load(f) != go:
                print("REFUSED -- GO changed on disk during validation")
                return 3
        # -- coordinator ownership (same check as both original pipelines)
        sys.path.insert(0, str(OLD))
        from train_eval import validate_owner
        validate_owner(STATE, go["owner_thread_id"])
        # -- locks (same two CPU locks as both original pipelines)
        for lp in LOCK_PATHS:
            f = lp.open("a+")
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locks.append(f)
        out_dir = os.path.realpath(str(go["out_dir"]))
        os.makedirs(out_dir, exist_ok=False)
        deadline = time.monotonic() + int(go["max_runtime_seconds"])

        def alarm_handler(signum, frame):
            raise TimeoutError("GO runtime deadline reached")

        signal.signal(signal.SIGALRM, alarm_handler)
        signal.setitimer(signal.ITIMER_REAL, int(go["max_runtime_seconds"]))
        timer_armed = True
        os.environ["OMP_NUM_THREADS"] = str(THREADS)
        os.environ["MKL_NUM_THREADS"] = str(THREADS)
        os.environ["OPENBLAS_NUM_THREADS"] = str(THREADS)
        rec.update(status="FITTING", request_id=go["request_id"],
                   go_sha256=sha_file(go_path), out_dir=out_dir,
                   seed=SEED, threads=THREADS)
        atomic_json(Path(out_dir) / "progress.json", rec)
        # -- pools x cohort intersection (frozen subset semantics)
        cohort = json.loads(COHORT.read_text())
        roles = cohort["roles"]
        pools = {}
        for label in POOL_LABELS:
            spec = go["pools"][label]
            ids = load_pool_file(spec["cells_file"], spec["cells_sha256"])
            inter, info = pool_train_intersection(ids, roles)
            if len(inter) < 2:
                raise ValueError("pool %r intersects the train cohort in %d "
                                 "cells; cell-isolated OOF needs >= 2"
                                 % (label, len(inter)))
            pools[label] = {"cell_ids": inter, "info": info}
        rec["pools"] = {k: v["info"] for k, v in pools.items()}
        atomic_json(Path(out_dir) / "progress.json", rec)
        # -- frozen panel references (query contract; no redesign)
        ref = {}
        for panel in PANELS:
            ref[panel] = read_panel_reference(
                go["panel_references"][panel]["path"], panel)
        rec["panel_reference"] = {
            p: {"path": str(go["panel_references"][p]["path"]),
                "n_keys": len(ref[p][0])} for p in PANELS}
        policy = go.get("panel_key_policy", "exact")
        # -- development side loaded ONCE (development role ONLY -- the
        #    original pipelines' C3 panel side; RUN1 root-cause fix: the
        #    train cohort must never enter the prediction panel)
        dev_cells = load_cells_restricted(COHORT, MANIFEST)
        f0_dv = rows_for_f0(dev_cells)
        f2_dv, f2_dmats = split_rows_tree(CACHE, "development", dev_cells,
                                          int(go["feature_dims"]["F2"]))
        rec["payload_reads"] += len(dev_cells)
        rec["dev_panel"] = {"F0_rows": len(f0_dv), "F2_rows": len(f2_dv)}
        atomic_json(Path(out_dir) / "progress.json", rec)
        record_fit = make_record_fit(out_dir, rec, deadline)
        input_shas = {slot: spec["sha256"]
                      for slot, spec in go["inputs"].items()}
        hyper = dict(FROZEN_HGB_CONFIG)
        for label in POOL_LABELS:
            train_ids = set(pools[label]["cell_ids"])
            cells = load_cells_restricted(COHORT, MANIFEST, roles=("train",),
                                          restrict_to=train_ids)
            rec["payload_reads"] += len(cells)
            # ---------------- F0_hgb on this pool
            tr0 = rows_for_f0(cells)
            if not tr0:
                raise ValueError("pool %r produced no eligible F0 train rows"
                                 % label)
            f0_start = time.time()
            m0, sig0, _oof0, folds0 = oof_fit_f0(
                tr0, SEED, record_fit, out_dir, rec, deadline)
            means0 = _pred_hgb(m0, f0_dv)
            rows0, stats0 = resolve_panel(f0_prediction_rows(f0_dv, means0,
                                                             sig0),
                                          "F0", ref["F0"][0], ref["F0"][1],
                                          policy)
            if stats0["n_missing_reference"]:
                print("WARNING -- F0 %s: %d reference keys have no "
                      "prediction (missing_by_arm=%r); allowed, recorded"
                      % (label, stats0["n_missing_reference"],
                         stats0["missing_by_arm"]))
            sub0 = os.path.join(out_dir, "%s__F0_hgb" % label)
            os.makedirs(sub0, exist_ok=False)
            csv_write(os.path.join(sub0, "predictions_c3.csv"), rows0,
                      F0_HEADER)
            fit_report(sub0, "F0_hgb", pool_label=label,
                       pool_info=pools[label]["info"],
                       train_cell_ids=[r["cell_id"] for r in tr0],
                       hyperparams=hyper, sigma=sig0,
                       sigma_source=SIGMA_SOURCE, input_shas=input_shas,
                       extra={"panel": "F0", "csv": "predictions_c3.csv",
                              "panel_policy": policy,
                              "n_predicted_full": stats0["n_predicted_full"],
                              "n_reference_keys": stats0["n_reference_keys"],
                              "n_kept": stats0["n_kept"],
                              "n_dropped": stats0["n_dropped"],
                              "n_missing_reference":
                              stats0["n_missing_reference"],
                              "panel_consistency": stats0,
                              "n_train_rows": len(tr0), "oof_folds": folds0,
                              "n_dev_rows": len(f0_dv),
                              "fit_seconds": time.time() - f0_start,
                              "csv_header": list(F0_HEADER),
                              "compare_model_key": "F0_hgb",
                              "pool_model": "%s__F0_hgb" % label})
            # ---------------- F2_hgb on this pool
            tr2, tmats = split_rows_tree(CACHE, "train", cells,
                                         int(go["feature_dims"]["F2"]))
            tr2 = [r for r in tr2 if r["cell"] in train_ids]
            if len({r["cell"] for r in tr2}) < 2:
                raise ValueError("pool %r produced < 2 eligible F2 train "
                                 "cells" % label)
            xs2 = f2_matrix(tr2, tmats)
            ys2 = np.asarray([r["y"] for r in tr2])
            ws2 = f2_weights(tr2)
            f2_start = time.time()
            m2, sig2, _oof2, folds2 = oof_fit_f2(
                tr2, xs2, ys2, ws2, SEED, record_fit, out_dir, rec, deadline)
            means2 = m2.predict(f2_matrix(f2_dv, f2_dmats))
            rows2, stats2 = resolve_panel(f2_prediction_rows(f2_dv, means2,
                                                             sig2),
                                          "F2", ref["F2"][0], ref["F2"][1],
                                          policy)
            if stats2["n_missing_reference"]:
                print("WARNING -- F2 %s: %d reference keys have no "
                      "prediction (missing_by_arm=%r); allowed, recorded"
                      % (label, stats2["n_missing_reference"],
                         stats2["missing_by_arm"]))
            sub2 = os.path.join(out_dir, "%s__F2_hgb" % label)
            os.makedirs(sub2, exist_ok=False)
            csv_write(os.path.join(sub2, "predictions_c3.csv"), rows2,
                      F2_HEADER)
            fit_report(sub2, "F2_hgb", pool_label=label,
                       pool_info=pools[label]["info"],
                       train_cell_ids=sorted({r["cell"] for r in tr2}),
                       hyperparams=hyper, sigma=sig2,
                       sigma_source=SIGMA_SOURCE, input_shas=input_shas,
                       extra={"panel": "F2", "csv": "predictions_c3.csv",
                              "panel_policy": policy,
                              "n_predicted_full": stats2["n_predicted_full"],
                              "n_reference_keys": stats2["n_reference_keys"],
                              "n_kept": stats2["n_kept"],
                              "n_dropped": stats2["n_dropped"],
                              "n_missing_reference":
                              stats2["n_missing_reference"],
                              "panel_consistency": stats2,
                              "n_train_rows": len(tr2), "oof_folds": folds2,
                              "n_dev_rows": len(f2_dv),
                              "fit_seconds": time.time() - f2_start,
                              "csv_header": list(F2_HEADER),
                              "compare_model_key": "F2_hgb",
                              "pool_model": "%s__F2_hgb" % label})
        if rec["fit_count"] != FITS_IN_GO or \
                rec["fits_started"] != FITS_IN_GO:
            raise ValueError("fit budget mismatch: %d" % rec["fit_count"])
        rec.update(status="COMPLETE_NO_DEV_SELECTION",
                   elapsed_seconds=time.time() - t0,
                   completed_utc=datetime.datetime.now(
                       datetime.timezone.utc).isoformat())
        atomic_json(Path(out_dir) / "progress.json", rec)
        with open(os.path.join(out_dir, "consumption_record.json"), "x",
                  encoding="utf-8") as f:
            json.dump({"request_id": str(go["request_id"]),
                       "go_sha256": sha_file(go_path),
                       "fits_in_this_go": FITS_IN_GO,
                       "pools": sorted(POOL_LABELS), "panels": sorted(PANELS),
                       "models": sorted(MODELS), "out_dir": out_dir},
                      f, indent=2)
        finished = datetime.datetime.now(datetime.timezone.utc).isoformat()
        register_consumed_go(registry_path, go["request_id"],
                             sha_file(go_path), finished)
        print("TREE-FRAC DONE: %d fits (%s x {F0_hgb, F2_hgb}), elapsed "
              "%.1f s" % (FITS_IN_GO, "/".join(POOL_LABELS), time.time() - t0))
        print("registered consumed GO: request_id=%s finished_utc=%s"
              % (go["request_id"], finished))
        return 0
    except BaseException as exc:  # noqa: BLE001 - house receipt style
        rec.update(status="FAILED", error=repr(exc),
                   traceback=traceback.format_exc(),
                   elapsed_seconds=time.time() - t0)
        print("FAILED -- %r" % exc)
        return 2
    finally:
        if timer_armed:
            signal.setitimer(signal.ITIMER_REAL, 0)
        if out_dir and os.path.exists(out_dir):
            try:
                atomic_json(Path(out_dir) / "progress.json", rec)
            except Exception:  # noqa: BLE001
                pass
        for f in reversed(locks):
            try:
                fcntl.flock(f, fcntl.LOCK_UN)
                f.close()
            except Exception:  # noqa: BLE001
                pass


# ------------------------------------------------------------------ self-check
def _synthetic_f0_cells(n_cells, first_index, role, group, seed):
    """Normalized-shape synthetic cells (data_adapter.normalize_cell output
    shape) for the F0 row builder: weekly RPTs, near-linear fade to an event."""
    rng = np.random.default_rng(seed)
    cells = []
    base = 1_730_000_000.0
    for j in range(n_cells):
        cap0 = 0.250 + 0.002 * float(rng.standard_normal())
        n_rec = 10
        records = []
        for i in range(n_rec):
            stop = base + first_index * 3600.0 + i * WEEK + j * 86400.0
            cap = cap0 - 0.006 * i + 0.0005 * float(rng.standard_normal())
            records.append({"source_rpt_index": i + 1,
                            "start": stop - 3600.0,
                            "stop": stop,
                            "stop_epoch": stop,
                            "capacityAh": float(max(cap, 0.15)),
                            "valid": True,
                            "calendar_age_weeks": (stop - base) / WEEK})
        event = next((r["stop_epoch"] for r in records
                      if r["capacityAh"] <= 0.20), None)
        cells.append({"cell_id": "syn%03dC1" % (first_index + j),
                      "group_id": group, "role": role,
                      "nominal_capacity_ah": 0.25,
                      "baseline_stop": base,
                      "records": records,
                      "source_observed_event_stop_epoch": event,
                      "source_observed_event_age_weeks":
                          None if event is None else (event - base) / WEEK,
                      "event_observed": event is not None})
    return cells


def _synthetic_cache(tmp, train_cells, dev_cells, dim, seed):
    """Temp stand-in for the nextcap cache (npz + rows jsonl), F2 only."""
    rng = np.random.default_rng(seed)
    cache = os.path.join(tmp, "cache")
    os.makedirs(cache, exist_ok=True)
    for split, cells in (("train", train_cells), ("development", dev_cells)):
        meta, feats = [], []
        for c in cells:
            stops = sorted(r["stop_epoch"] for r in c["records"])
            anchor = stops[1]
            for arm in ("raw", "sparse2", "delay7d"):
                for q in stops:
                    if q < anchor + WEEK:
                        continue
                    meta.append({"cell_id": c["cell_id"], "arm": arm,
                                 "query_epoch": q, "idx": len(meta),
                                 "role": c["role"]})
                    feats.append(rng.standard_normal(dim))
        with open(os.path.join(cache, split + "_rows.jsonl"), "w",
                  encoding="utf-8") as f:
            for m in meta:
                f.write(json.dumps(m) + "\n")
        np.savez(os.path.join(cache, split + "_features.npz"),
                 F2=np.asarray(feats, float))
    with open(os.path.join(cache, "feature_schema.json"), "w",
              encoding="utf-8") as f:
        json.dump({"synthetic": True, "dimensions": {"F2": dim}}, f)
    return cache


def _write_csv(path, rows, header):
    csv_write(path, rows, header)


def test_pool_semantics():
    roles = {"a": "train", "b": "train", "c": "train", "d": "development",
             "e": "locked_C4"}
    inter, info = pool_train_intersection(["b", "a", "b", "d", "e"], roles)
    _assert(inter == ["a", "b"],
            "intersection must be pool ∩ train, sorted, deduped")
    _assert(info["n_intersection"] == 2 and info["n_pool"] == 5,
            "sizes must be recorded honestly")
    _assert(set(info["outside_train_cohort"]) == {"d", "e"},
            "cells outside the train cohort must be listed")
    inter2, info2 = pool_train_intersection(["d"], roles)
    _assert(inter2 == [] and info2["n_intersection"] == 0,
            "a pool fully outside the train cohort intersects to empty")
    return ("pool ∩ roles==train sorted+dedup; sizes recorded; outside-train "
            "cells listed; degenerate empty intersection handled")


def test_registry():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "consumed_registry_tmp.jsonl")
        line = register_consumed_go(path, "SYN_TREE_RID_1", "ab" * 32,
                                    "2026-10-24T00:00:00+00:00")
        with open(path, "r", encoding="utf-8") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
        _assert(len(lines) == 1, "append must add exactly one line")
        rec = json.loads(lines[0])
        _assert(set(rec) == {"request_id", "go_sha256", "finished_utc"} and
                rec["request_id"] == "SYN_TREE_RID_1",
                "registry line fields must be exactly "
                "request_id/go_sha256/finished_utc")
        _assert(line == lines[0], "returned line must match the file")
        _assert(request_id_is_fresh("SYN_TREE_RID_2", path),
                "an unseen request_id must be fresh")
        _assert(not request_id_is_fresh("SYN_TREE_RID_1", path),
                "a registered request_id must not be fresh")
        doubled = False
        try:
            register_consumed_go(path, "SYN_TREE_RID_1", "ab" * 32, "again")
        except RuntimeError:
            doubled = True
        _assert(doubled, "duplicate request_id must be refused")
        with open(path, "r", encoding="utf-8") as f:
            _assert(len([ln for ln in f.read().splitlines() if ln.strip()])
                    == 1, "refused duplicate must not append")
        bad = os.path.join(tmp, "bad_registry_tmp.jsonl")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("not-json\n")
        failed = False
        try:
            load_consumed_request_ids(bad)
        except Exception:  # noqa: BLE001 - expected
            failed = True
        _assert(failed, "malformed registry line must fail closed")
        _assert(json.loads(line) == {"request_id": "SYN_TREE_RID_1",
                                     "go_sha256": "ab" * 32,
                                     "finished_utc":
                                     "2026-10-24T00:00:00+00:00"},
                "line must round-trip the 3 documented fields")
    return ("append-once verified (exact 3 fields, sort_keys), duplicate "
            "refused, malformed line fail-closed, fresh-check both ways "
            "(temp registry only)")


def _synthetic_tree_go(tmp, pool_paths, input_paths, panel_paths, code_sha,
                       out_name="out_tree_syn"):
    pools = {label: {"cells_file": path, "cells_sha256": sha_file(path)}
             for label, path in pool_paths.items()}
    inputs = {slot: {"path": path, "sha256": sha_file(path)}
              for slot, path in input_paths.items()}
    refs = {p: {"path": path, "sha256": sha_file(path)}
            for p, path in panel_paths.items()}
    go = {
        "status": "APPROVED", "allow_fit": True, "allow_C4": False,
        "scope": "TREE-FRAC TRAIN/FIT: R2 stage B tree subset retrain "
                 "(F0_hgb + F2_hgb on the frozen f25/f50 fraction pools), "
                 "%d fits in this GO" % FITS_IN_GO,
        "request_id": "SYN_TREE_FRAC_GO_20261024_T1",
        "owner_thread_id": "synthetic-self-check",
        "issued_utc": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
        "issued_by": {"controller": "synthetic self-check fixture"},
        "code_sha256": {CODE_FILE: code_sha},
        "seed": SEED, "fits_in_this_go": FITS_IN_GO,
        "threads": THREADS, "device": DEVICE,
        "max_runtime_seconds": 3600,
        "pools": pools, "inputs": inputs, "panel_references": refs,
        "model_config": {"hgb": FROZEN_HGB_CONFIG},
        "feature_dims": dict(EXPECTED_FEATURE_DIMS),
        "panel_key_policy": "exact",
        "out_dir": os.path.join(tmp, out_name),
        "data_scope": "synthetic gate-test stand-ins only; no real data",
    }
    path = os.path.join(tmp, "GO_synthetic_tree_frac.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(go, f, indent=2)
    return path, go


def test_go_gate(tmp_root, pool_paths, input_paths, panel_paths, code_sha):
    """Builds the accept/mutation fixtures over the temp stand-in maps."""
    import tempfile

    def accepts_wellformed():
        with tempfile.TemporaryDirectory() as tmp:
            registry = os.path.join(tmp, "consumed_registry_tmp.jsonl")
            go_path, _ = _synthetic_tree_go(tmp, pool_paths, input_paths,
                                            panel_paths, code_sha)
            problems, go = validate_go_tree(
                go_path, registry, input_paths, panel_paths,
                expected_out_root=tmp, code_sha=code_sha)
            _assert(not problems,
                    "well-formed tree GO refused: %r" % problems)
            _assert(go["fits_in_this_go"] == FITS_IN_GO and
                    go["seed"] == 42,
                    "accepted GO must expose the frozen contract")
        return ("well-formed synthetic tree GO accepted with 0 problems "
                "(temp registry + temp stand-in inputs only)")

    def refuses_mutations():
        cases = [
            "wrong code sha", "code sha not pinned", "status not APPROVED",
            "allow_fit false", "allow_C4 true", "scope without TREE-FRAC",
            "scope without TRAIN/FIT", "scope not a string",
            "request_id too short", "request_id reused", "owner missing",
            "GO stale", "issued_utc malformed", "seed mismatch",
            "fits_in_this_go stale 4", "threads mismatch", "device mismatch",
            "max_runtime too large", "max_runtime too small",
            "pools missing f50", "pools extra label", "pool sha mismatch",
            "pool file missing", "pool duplicate ids", "pool not a list",
            "input sha mismatch", "input path not frozen",
            "inputs missing slot", "panel sha mismatch",
            "panel path not frozen", "model_config mutated",
            "feature_dims mutated", "panel policy bogus",
            "policy unknown value", "ref_filter missing panel_references",
            "ref_filter missing one panel ref", "burned request_id RUN1",
            "burned request_id RUN2", "out_dir stale", "out_dir outside root",
        ]
        refused = 0
        for label in cases:
            with tempfile.TemporaryDirectory() as tmp:
                registry = os.path.join(tmp, "consumed_registry_tmp.jsonl")
                go_path, go = _synthetic_tree_go(tmp, pool_paths, input_paths,
                                                 panel_paths, code_sha)
                if label == "request_id reused":
                    register_consumed_go(registry, go["request_id"],
                                         "0" * 64, "2026-10-24T00:00:00Z")
                elif label == "wrong code sha":
                    go["code_sha256"] = {CODE_FILE: "0" * 64}
                elif label == "code sha not pinned":
                    go["code_sha256"] = {"other.py": code_sha}
                elif label == "status not APPROVED":
                    go["status"] = "PROPOSED"
                elif label == "allow_fit false":
                    go["allow_fit"] = False
                elif label == "allow_C4 true":
                    go["allow_C4"] = True
                elif label == "scope without TREE-FRAC":
                    go["scope"] = "A3 TRAIN/FIT: subset retrain"
                elif label == "scope without TRAIN/FIT":
                    go["scope"] = "TREE-FRAC: subset retrain only"
                elif label == "scope not a string":
                    go["scope"] = 17
                elif label == "request_id too short":
                    go["request_id"] = "short"
                elif label == "owner missing":
                    go["owner_thread_id"] = ""
                elif label == "GO stale":
                    go["issued_utc"] = "2020-01-01T00:00:00Z"
                elif label == "issued_utc malformed":
                    go["issued_utc"] = "not-a-timestamp"
                elif label == "seed mismatch":
                    go["seed"] = 43
                elif label == "fits_in_this_go stale 4":
                    go["fits_in_this_go"] = 4  # the exact RUN2 bug value
                elif label == "threads mismatch":
                    go["threads"] = 8
                elif label == "device mismatch":
                    go["device"] = "gpu"
                elif label == "max_runtime too large":
                    go["max_runtime_seconds"] = 999999
                elif label == "max_runtime too small":
                    go["max_runtime_seconds"] = 1
                elif label == "pools missing f50":
                    go["pools"].pop("f50")
                elif label == "pools extra label":
                    extra = os.path.join(tmp, "cells_f75.json")
                    with open(extra, "w", encoding="utf-8") as f:
                        json.dump(["x1", "x2"], f)
                    go["pools"]["f75"] = {"cells_file": extra,
                                          "cells_sha256": sha_file(extra)}
                elif label == "pool sha mismatch":
                    go["pools"]["f25"]["cells_sha256"] = "0" * 64
                elif label == "pool file missing":
                    go["pools"]["f25"]["cells_file"] = \
                        os.path.join(tmp, "missing_cells.json")
                elif label == "pool duplicate ids":
                    dup = os.path.join(tmp, "cells_dup.json")
                    with open(dup, "w", encoding="utf-8") as f:
                        json.dump(["c1", "c1", "c2"], f)
                    go["pools"]["f25"] = {"cells_file": dup,
                                          "cells_sha256": sha_file(dup)}
                elif label == "pool not a list":
                    nl = os.path.join(tmp, "cells_notlist.json")
                    with open(nl, "w", encoding="utf-8") as f:
                        json.dump({"cells": ["c1"]}, f)
                    go["pools"]["f25"] = {"cells_file": nl,
                                          "cells_sha256": sha_file(nl)}
                elif label == "input sha mismatch":
                    k0 = sorted(input_paths)[0]
                    go["inputs"][k0]["sha256"] = "0" * 64
                elif label == "input path not frozen":
                    other = os.path.join(tmp, "other_standin.json")
                    with open(other, "w", encoding="utf-8") as f:
                        json.dump({"synthetic": True}, f)
                    k0 = sorted(input_paths)[0]
                    go["inputs"][k0] = {"path": other,
                                        "sha256": sha_file(other)}
                elif label == "inputs missing slot":
                    go["inputs"].pop(sorted(input_paths)[0])
                elif label == "panel sha mismatch":
                    go["panel_references"]["F0"]["sha256"] = "0" * 64
                elif label == "panel path not frozen":
                    other = os.path.join(tmp, "other_panel.csv")
                    with open(other, "w", encoding="utf-8") as f:
                        f.write("x\n1\n")
                    go["panel_references"]["F0"] = {"path": other,
                                                    "sha256": sha_file(other)}
                elif label == "model_config mutated":
                    go["model_config"] = {
                        "hgb": dict(FROZEN_HGB_CONFIG, max_iter=149)}
                elif label == "feature_dims mutated":
                    go["feature_dims"] = {"F0": 74, "F2": 99}
                elif label == "panel policy bogus":
                    go["panel_key_policy"] = "any"
                elif label == "policy unknown value":
                    go["panel_key_policy"] = "fuzzy"
                elif label == "ref_filter missing panel_references":
                    go["panel_key_policy"] = "reference_filter"
                    go.pop("panel_references")
                elif label == "ref_filter missing one panel ref":
                    go["panel_key_policy"] = "reference_filter"
                    go["panel_references"].pop("F2")
                elif label == "burned request_id RUN1":
                    go["request_id"] = BURNED_REQUEST_IDS[0]
                elif label == "burned request_id RUN2":
                    go["request_id"] = BURNED_REQUEST_IDS[-1]
                elif label == "out_dir stale":
                    os.makedirs(go["out_dir"], exist_ok=True)
                elif label == "out_dir outside root":
                    go["out_dir"] = os.path.join(
                        tempfile.gettempdir(),
                        "outside_fixture_root_%d" % time.time_ns())
                with open(go_path, "w", encoding="utf-8") as f:
                    json.dump(go, f, indent=2)
                problems, _ = validate_go_tree(
                    go_path, registry, input_paths, panel_paths,
                    expected_out_root=tmp, code_sha=code_sha)
                _assert(problems,
                        "mutation %r was NOT refused (gate hole)" % label)
                refused += 1
        _assert(refused >= 10,
                "expected >= 10 refused mutations, got %d" % refused)
        return ("%d/%d GO mutations refused: code sha (wrong/unpinned), "
                "status, allow_fit, allow_C4, scope x4, request_id (short/"
                "reused/burned), owner, stale/malformed issued_utc, seed, "
                "fits budget, threads/device, runtime bounds, pools (missing/"
                "extra/sha/missing-file/duplicates/not-a-list), inputs (sha/"
                "frozen-path/missing-slot), panel refs (sha/frozen-path/"
                "missing under reference_filter), model_config, "
                "feature_dims, policy (bogus/unknown/missing-refs), out_dir "
                "(stale/outside)" % (refused, len(cases)))

    return accepts_wellformed, refuses_mutations


def test_f2_smoke(tmp):
    """Synthetic nextcap-cache pipeline: subset fit, panel keys, CSV contract."""
    dim = 5
    tr_cells = _synthetic_f0_cells(5, 100, "train", "G1", seed=11)
    dv_cells = _synthetic_f0_cells(2, 200, "development", "G2", seed=12)
    cache = _synthetic_cache(tmp, tr_cells, dv_cells, dim, seed=13)
    dv_rows, dv_mats = split_rows_tree(cache, "development", dv_cells, dim)
    _assert(len(dv_rows) > 0, "synthetic dev rows must be non-empty")
    # frozen reference panel = same dev rows with stand-in predictions
    rng = np.random.default_rng(7)
    ref_rows = []
    for z in dv_rows:
        mu = z["y"] + 0.001 * float(rng.standard_normal())
        ref_rows.append(f2_prediction_rows([z], [mu], 0.01)[0])
    ref_path = os.path.join(tmp, "ref_F2_predictions_c3.csv")
    _write_csv(ref_path, ref_rows, F2_HEADER)
    ref_keys, ref_targets = read_panel_reference(ref_path, "F2")
    _assert(len(ref_keys) == len(dv_rows),
            "reference panel must cover every dev query")
    # subset fit: 3 of the 5 train cells
    pool = sorted(c["cell_id"] for c in tr_cells)[:3]
    fit_rows, t_mats = split_rows_tree(cache, "train", tr_cells, dim)
    fit_rows = [r for r in fit_rows if r["cell"] in set(pool)]
    _assert({r["cell"] for r in fit_rows} == set(pool),
            "subset rows must be exactly the pool cells with eligible rows")
    xs = f2_matrix(fit_rows, t_mats)
    ys = np.asarray([r["y"] for r in fit_rows])
    ws = f2_weights(fit_rows)
    sub = os.path.join(tmp, "f25__F2_hgb")
    os.makedirs(sub, exist_ok=True)
    rec = {"fit_count": 0, "fits_started": 0, "fits": []}
    t0 = time.time()
    m, sig, _oof, folds = oof_fit_f2(fit_rows, xs, ys, ws, SEED,
                                     counting_record_fit, sub, rec,
                                     time.monotonic() + 600)
    _assert(rec["fit_count"] == 3, "OOF (2 folds) + final = 3 fits recorded")
    means = m.predict(f2_matrix(dv_rows, dv_mats))
    rows = f2_prediction_rows(dv_rows, means, sig)
    cons = assert_panel_consistency(rows, "F2", ref_keys, ref_targets, "exact")
    _assert(cons["n_pred_keys"] == cons["n_ref_keys"] == len(ref_keys),
            "exact policy must reproduce every panel key")
    _assert(np.isfinite(sig) and sig > 0, "sigma must be finite positive")
    _assert(len(folds) == 2, "two cell-isolated folds")
    csv_path = os.path.join(sub, "predictions_c3.csv")
    _write_csv(csv_path, rows, F2_HEADER)
    with open(csv_path, newline="", encoding="utf-8") as f:
        got = list(csv.DictReader(f))
    _assert(list(got[0].keys()) == F2_HEADER,
            "F2 CSV header must equal the frozen 11-column reference header")
    _assert(all(r["model"] == "hgb" and r["panel"] == "F2" for r in got),
            "model/panel columns must be hgb/F2")
    _assert(len(got) == len(rows), "row count must match")
    rep = fit_report(sub, "F2_hgb", pool_label="f25",
                     pool_info={"n_pool": len(pool),
                                "n_intersection": len(pool)},
                     train_cell_ids=pool, hyperparams=FROZEN_HGB_CONFIG,
                     sigma=sig, sigma_source=SIGMA_SOURCE,
                     input_shas={"cache_train_features_npz": "synthetic"},
                     extra={"panel": "F2", "n_train_rows": len(fit_rows),
                            "panel_consistency": cons,
                            "fit_seconds": time.time() - t0})
    for k in ("pool_label", "n_train_cells", "hyperparams", "sigma_oof_ah",
              "sigma_source", "input_sha256", "fit_seconds"):
        _assert(k in rep, "fit_report missing %r" % k)
    return ("synthetic cache (dim %d, %d train cells -> pool %d, %d pool "
            "rows, folds %s): sigma=%.4f, %d panel keys exact-matched, 3 "
            "fits recorded, 11-col header + panel/model columns verified"
            % (dim, len(tr_cells), len(pool), len(fit_rows),
               [len(f) for f in folds], sig, cons["n_pred_keys"]))


def test_f0_smoke(tmp):
    """Synthetic normalized cells through the real F0 row builder."""
    tr_cells = _synthetic_f0_cells(4, 300, "train", "G1", seed=21)
    dv_cells = _synthetic_f0_cells(2, 400, "development", "G2", seed=22)
    dv_rows = rows_for_f0(dv_cells)
    _assert(len(dv_rows) > 0, "synthetic F0 dev rows must be non-empty")
    _assert(all(np.asarray(r["features"]).shape == (75,) for r in dv_rows),
            "F0 features must be 74-dim x_query + h")
    rng = np.random.default_rng(9)
    ref_rows = []
    for z in dv_rows:
        mu = z["target"] + 0.001 * float(rng.standard_normal())
        ref_rows.append(f0_prediction_rows([z], [mu], 0.01)[0])
    ref_path = os.path.join(tmp, "ref_F0_predictions_c3.csv")
    _write_csv(ref_path, ref_rows, F0_HEADER)
    ref_keys, ref_targets = read_panel_reference(ref_path, "F0")
    pool = set(sorted(c["cell_id"] for c in tr_cells)[:2])
    tr_rows = [r for r in rows_for_f0(tr_cells) if r["cell_id"] in pool]
    _assert({r["cell_id"] for r in tr_rows} == pool,
            "subset F0 rows must cover exactly the pool cells")
    sub = os.path.join(tmp, "f25__F0_hgb")
    os.makedirs(sub, exist_ok=True)
    rec = {"fit_count": 0, "fits_started": 0, "fits": []}
    t0 = time.time()
    m, sig, _oof, folds = oof_fit_f0(tr_rows, SEED, counting_record_fit, sub,
                                     rec, time.monotonic() + 600)
    _assert(rec["fit_count"] == 3, "OOF (2 folds) + final = 3 fits recorded")
    means = _pred_hgb(m, dv_rows)
    rows = f0_prediction_rows(dv_rows, means, sig)
    cons = assert_panel_consistency(rows, "F0", ref_keys, ref_targets, "exact")
    _assert(cons["n_pred_keys"] == len(ref_keys),
            "exact policy must reproduce every F0 panel key")
    _assert(np.isfinite(sig) and sig > 0, "sigma must be finite positive")
    stages = {r["degradation_stage"] for r in rows}
    _assert(stages <= {"gt0.95", "0.90-0.95", "0.85-0.90", "le0.85"},
            "degradation_stage labels must come from the frozen set")
    csv_path = os.path.join(sub, "predictions_c3.csv")
    _write_csv(csv_path, rows, F0_HEADER)
    with open(csv_path, newline="", encoding="utf-8") as f:
        got = list(csv.DictReader(f))
    _assert(list(got[0].keys()) == F0_HEADER,
            "F0 CSV header must equal the frozen 17-column reference header")
    _assert(all(r["model"] == "hgb" for r in got),
            "model column must be hgb (panel F0 is the compare default)")
    _assert(all(r["known_event"] in ("True", "False") for r in got),
            "known_event must serialize like the original csv writer")
    rep = fit_report(sub, "F0_hgb", pool_label="f25",
                     pool_info={"n_pool": len(pool),
                                "n_intersection": len(pool)},
                     train_cell_ids=sorted(pool),
                     hyperparams=FROZEN_HGB_CONFIG, sigma=sig,
                     sigma_source=SIGMA_SOURCE,
                     input_shas={"cohort_json": "synthetic"},
                     extra={"panel": "F0", "n_train_rows": len(tr_rows),
                            "panel_consistency": cons,
                            "fit_seconds": time.time() - t0})
    for k in ("pool_label", "n_train_cells", "hyperparams", "sigma_oof_ah",
              "sigma_source", "input_sha256", "fit_seconds"):
        _assert(k in rep, "fit_report missing %r" % k)
    return ("synthetic normalized cells through the real V18 row builder: "
            "%d pool rows (2 cells), folds %s, sigma=%.4f, %d panel keys "
            "exact-matched, 17-col header + stage labels verified"
            % (len(tr_rows), [len(f) for f in folds], sig,
               cons["n_pred_keys"]))


def test_panel_policy_and_headers():
    """Subset policy accepts a partial panel; exact refuses it; header
    constants must equal the frozen reference headers byte-for-byte."""
    import tempfile
    _assert(F2_HEADER == ["model", "panel", "cell_id", "arm", "query_epoch",
                          "forecast_h_weeks", "target_capacity_ah",
                          "predicted_capacity_ah", "sigma_oof_ah", "error_ah",
                          "abs_error_ah"], "F2 header constant drift")
    _assert(F0_HEADER == ["model", "cell_id", "group_id", "arm",
                          "query_epoch", "forecast_h_weeks",
                          "next_source_elapsed_weeks",
                          "next_query_elapsed_weeks",
                          "last_visible_capacity_ah", "last_visible_soh",
                          "degradation_stage", "target_next_capacity_ah",
                          "predicted_mean_ah", "predicted_sigma_ah",
                          "error_ah", "abs_error_ah", "known_event"],
            "F0 header constant drift")
    with tempfile.TemporaryDirectory() as tmp:
        rows = [{"model": "hgb", "panel": "F2", "cell_id": "c1", "arm": "raw",
                 "query_epoch": 1730000000.0, "forecast_h_weeks": 2.0,
                 "target_capacity_ah": 0.24, "predicted_capacity_ah": 0.241,
                 "sigma_oof_ah": 0.01, "error_ah": -0.001,
                 "abs_error_ah": 0.001}]
        p = os.path.join(tmp, "panel.csv")
        _write_csv(p, rows, F2_HEADER)
        keys, targets = read_panel_reference(p, "F2")
        _assert(len(keys) == 1, "one reference key expected")
        bigger_keys = keys | {("zz", "raw", 1.0, 1.0)}
        bigger_targets = dict(targets)
        bigger_targets[("zz", "raw", 1.0, 1.0)] = 0.2
        assert_panel_consistency(rows, "F2", bigger_keys, bigger_targets,
                                 "subset")
        exact_refused = False
        try:
            assert_panel_consistency(rows, "F2", bigger_keys, bigger_targets,
                                     "exact")
        except ValueError:
            exact_refused = True
        _assert(exact_refused, "exact policy must refuse a partial panel")
        outside_refused = False
        try:
            assert_panel_consistency([dict(rows[0], cell_id="zz")], "F2",
                                     keys, targets, "subset")
        except ValueError:
            outside_refused = True
        _assert(outside_refused,
                "predicted keys outside the reference must be refused even "
                "under the subset policy")
        target_refused = False
        try:
            assert_panel_consistency(
                [dict(rows[0], target_capacity_ah=0.9)], "F2", keys, targets,
                "subset")
        except ValueError:
            target_refused = True
        _assert(target_refused, "target drift on a matched key must refuse")
        dup_refused = False
        try:
            assert_panel_consistency([rows[0], rows[0]], "F2", keys, targets,
                                     "subset")
        except ValueError:
            dup_refused = True
        _assert(dup_refused, "duplicate predicted keys must refuse")
    return ("subset policy accepts predicted ⊆ reference; exact refuses it; "
            "out-of-panel keys, target drift and duplicate keys always "
            "refuse; header constants byte-equal the frozen reference "
            "headers")


def test_reference_filter_semantics():
    """reference_filter: keep the reference intersection, drop+count rows
    outside the frozen panel, allow+count missing reference keys (warn, not
    refuse), refuse kept-key target drift and duplicate keys; the gate
    accepts a well-formed reference_filter GO; exact/subset unchanged."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        rows = []
        for i in range(8):
            rows.append({"model": "hgb", "panel": "F2",
                         "cell_id": "c%d" % (i // 4),
                         "arm": ("raw", "delay7d")[i % 2],
                         "query_epoch": 1730000000.0 + 604800.0 * i,
                         "forecast_h_weeks": 1.0 + 0.25 * i,
                         "target_capacity_ah": 0.24 - 0.001 * i,
                         "predicted_capacity_ah": 0.241 - 0.001 * i,
                         "sigma_oof_ah": 0.01, "error_ah": -0.001,
                         "abs_error_ah": 0.001})
        ref_rows = [dict(r) for r in rows[:5]]
        ref_rows.append({"model": "hgb", "panel": "F2", "cell_id": "c9",
                         "arm": "raw", "query_epoch": 1730999999.0,
                         "forecast_h_weeks": 2.5, "target_capacity_ah": 0.2,
                         "predicted_capacity_ah": 0.2, "sigma_oof_ah": 0.01,
                         "error_ah": 0.0, "abs_error_ah": 0.0})
        p = os.path.join(tmp, "ref.csv")
        _write_csv(p, ref_rows, F2_HEADER)
        keys, targets = read_panel_reference(p, "F2")
        _assert(len(keys) == 6, "6 reference keys expected")
        kept, stats = apply_reference_filter(rows, "F2", keys, targets)
        _assert(stats["n_predicted_full"] == 8 and
                stats["n_reference_keys"] == 6,
                "full/reference counts must be recorded")
        _assert(stats["n_kept"] == 5 and len(kept) == 5,
                "the 5 in-reference rows must be kept in order")
        _assert(stats["n_dropped"] == 3 and
                stats["dropped_by_arm"] == {"delay7d": 2, "raw": 1} and
                stats["dropped_by_cell"] == {"c1": 3},
                "dropped rows must be counted with arm/cell distributions")
        _assert(stats["n_missing_reference"] == 1 and
                stats["missing_by_arm"] == {"raw": 1} and
                stats["missing_by_cell"] == {"c9": 1},
                "the reference-only key must be allowed and counted (warn, "
                "not refuse)")
        drift = [dict(r) for r in rows]
        drift[0]["target_capacity_ah"] = 0.9
        refused = False
        try:
            apply_reference_filter(drift, "F2", keys, targets)
        except ValueError as exc:
            refused = "kept-key target drift" in str(exc)
        _assert(refused, "kept-key target drift must refuse")
        dup_refused = False
        try:
            apply_reference_filter([rows[0], rows[0]], "F2", keys, targets)
        except ValueError:
            dup_refused = True
        _assert(dup_refused, "duplicate predicted keys must refuse")
        # exact/subset semantics unchanged (RUN1 contract)
        exact_refused = False
        try:
            resolve_panel(rows, "F2", keys, targets, "exact")
        except ValueError:
            exact_refused = True
        _assert(exact_refused,
                "exact must still refuse predicted keys outside the panel")
        subset_rows, subset_stats = resolve_panel(rows[:5], "F2", keys,
                                                  targets, "subset")
        _assert(len(subset_rows) == 5 and
                subset_stats["n_missing_reference"] == 1 and
                subset_stats["n_dropped"] == 0,
                "subset still requires predicted ⊆ reference (missing "
                "allowed, nothing dropped)")
        # gate accepts a well-formed reference_filter GO
        pool_paths, input_paths, panel_paths = _temp_standins(tmp)
        go_path, go = _synthetic_tree_go(tmp, pool_paths, input_paths,
                                         panel_paths,
                                         sha_file(os.path.abspath(__file__)))
        go["panel_key_policy"] = "reference_filter"
        with open(go_path, "w", encoding="utf-8") as f:
            json.dump(go, f, indent=2)
        problems, _ = validate_go_tree(
            go_path, os.path.join(tmp, "registry_tmp.jsonl"), input_paths,
            panel_paths, expected_out_root=tmp,
            code_sha=sha_file(os.path.abspath(__file__)))
        _assert(not problems,
                "reference_filter GO refused: %r" % problems)
        return ("8 predicted keys vs 6-key reference: kept=5 (order kept), "
                "dropped=3 (arm/cell distributions), missing=1 (allowed, "
                "counted); kept-key target drift and duplicates refuse; "
                "exact still refuses out-of-panel keys, subset still "
                "requires ⊆; reference_filter GO accepted by the gate")


def _tree_is_forbidden(path, tmp_prefix):
    """a3_fixtures rule (data/reports/prep_inputs, prep_v2, real registry,
    .npz outside tmp) plus the tree-specific adds: run1_fits, checkpoints."""
    import a3_fixtures
    if a3_fixtures._is_forbidden_path(path, tmp_prefix):
        return True
    p = str(path)
    if p.startswith(tmp_prefix):
        return False
    if "run1_fits" in p:
        return True
    if p.startswith(str(ROOT) + "/checkpoints"):
        return True
    return False


def _temp_standins(tmp_root):
    """Temp stand-ins for the gate's frozen-path pin map (never real data)."""
    pool_paths = {}
    for label, ids in (("f25", ["s1", "s2", "s3"]),
                       ("f50", ["s1", "s2", "s3", "s4", "s5"])):
        p = os.path.join(tmp_root, "cells_%s.json" % label)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(ids, f)
        pool_paths[label] = p
    input_paths = {}
    for slot in REQUIRED_INPUT_SLOTS:
        p = os.path.join(tmp_root, "standin_%s.json" % slot)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"synthetic": True, "slot": slot}, f)
        input_paths[slot] = p
    panel_paths = {}
    for panel, header in (("F0", F0_HEADER), ("F2", F2_HEADER)):
        p = os.path.join(tmp_root, "standin_panel_%s.csv" % panel)
        row = {k: "" for k in header}
        row["model"] = "hgb"
        row["cell_id"] = "sx"
        row["arm"] = "raw"
        row["query_epoch"] = "1730000000.0"
        row["forecast_h_weeks"] = "2.0"
        if "panel" in row:
            row["panel"] = "F2"
        if "target_capacity_ah" in row:
            row["target_capacity_ah"] = "0.2"
        if "target_next_capacity_ah" in row:
            row["target_next_capacity_ah"] = "0.2"
        _write_csv(p, [row], header)
        panel_paths[panel] = p
    return pool_paths, input_paths, panel_paths


FIXTURES = (
    ("pool_semantics", lambda tmp: test_pool_semantics()),
    ("registry_gate", lambda tmp: test_registry()),
    ("f2_synthetic_cache_smoke", test_f2_smoke),
    ("f0_synthetic_cells_smoke", test_f0_smoke),
    ("panel_policy_and_headers", lambda tmp: test_panel_policy_and_headers()),
    ("reference_filter_semantics",
     lambda tmp: test_reference_filter_semantics()),
)


def run_self_check():
    """Synthetic fixtures only; returns (text_lines, n_fail, code_sha)."""
    import tempfile
    out = []

    def emit(line):
        print(line)
        out.append(line)

    results = []
    code_sha = sha_file(os.path.abspath(__file__))
    try:
        import a3_fixtures  # own-directory harness, reused unchanged
    except Exception as exc:  # noqa: BLE001
        emit("[FAIL] import a3_fixtures: %s: %s" % (type(exc).__name__, exc))
        return out, 1, code_sha
    auditor = a3_fixtures.OpenAuditor()
    auditor.__enter__()
    tmp_root = None
    try:
        tmp_root = tempfile.mkdtemp(prefix="tree_frac_selfcheck_")
        pool_paths, input_paths, panel_paths = _temp_standins(tmp_root)
        accept, refuse = test_go_gate(tmp_root, pool_paths, input_paths,
                                      panel_paths, code_sha)
        fixtures = (("go_gate_accepts_wellformed", lambda tmp: accept()),
                    ("go_gate_refuses_mutations", lambda tmp: refuse())) + \
                   FIXTURES
        for name, fn in fixtures:
            try:
                detail = fn(tmp_root)
                results.append((name, True, str(detail)))
                emit("[PASS] %-48s %s" % (name, detail))
            except Exception as exc:  # noqa: BLE001 - fail loud, keep going
                results.append((name, False,
                                "%s: %s" % (type(exc).__name__, exc)))
                emit("[FAIL] %-48s %s: %s"
                     % (name, type(exc).__name__, exc))
                for ln in traceback.format_exc().rstrip().splitlines():
                    emit("       " + ln)
    finally:
        auditor.__exit__(None, None, None)
        tmp_prefix = tempfile.gettempdir()
        forbidden = [p for p in auditor.paths
                     if _tree_is_forbidden(p, tmp_prefix)]
        emit("[AUDIT] global open() audit: %d paths recorded, %d forbidden"
             % (len(auditor.paths), len(forbidden)))
        for p in forbidden[:5]:
            emit("[AUDIT]   forbidden open: %s" % p)
        if forbidden:
            results.append(("global_no_payload_audit", False,
                            "forbidden opens: %r" % forbidden[:5]))
        else:
            results.append(("global_no_payload_audit", True,
                            "0 opens under real data/reports/automation, "
                            "0 real registry reads, 0 npz outside tmp"))
    n_pass = sum(1 for r in results if r[1])
    n_fail = len(results) - n_pass
    emit("-" * 78)
    emit("NO TRAINING PERFORMED. NO PAYLOAD READ (data/, reports/, C4). "
         "NO REAL FEATURE CACHE READ. NO GO CREATED OR CONSUMED.")
    emit("RESULT: %s (%d passed / %d failed)"
         % ("OK" if n_fail == 0 else "FAILED", n_pass, n_fail))
    return out, n_fail, code_sha


def append_self_check_log(lines, code_sha):
    import sklearn
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    header = [
        "===== tree_frac self-check %s =====" % stamp,
        "=" * 78,
        "TREE SUBSET-RETRAIN (R2 data-efficiency stage B) -- %s" % stamp,
        "mode: SYNTHETIC ONLY -- 0 real fits | 0 payload reads (data/, "
        "reports/, C4) | 0 real feature-cache reads | 0 GO created or "
        "consumed",
        "python %s | numpy %s | sklearn %s | code_sha256 %s"
        % (sys.version.split()[0], np.__version__, sklearn.__version__,
           code_sha),
        "-" * 78,
    ]
    with open(os.path.join(str(HERE), SELF_CHECK_LOG_NAME), "a",
              encoding="utf-8") as f:
        f.write("\n".join(header + list(lines)) + "\n")
        f.flush()
        os.fsync(f.fileno())


# ------------------------------------------------------------------------ CLI
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Tree subset-retrain (R2 stage B): self-check by "
                    "default; F0_hgb/F2_hgb x {f25,f50} = %d HGB fits only "
                    "under an exact, unconsumed TREE-FRAC GO." % FITS_IN_GO)
    p.add_argument("--self-check", action="store_true",
                   help="run all synthetic fixtures (default behaviour)")
    p.add_argument("--run-train", action="store_true",
                   help="guarded training path; requires --go")
    p.add_argument("--go", default=None,
                   help="path to an APPROVED, unconsumed TREE-FRAC GO json")
    p.add_argument("--no-log-append", action="store_true",
                   help="self-check: do not append SELF_CHECK_LOG.txt")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.run_train:
        if not args.go:
            print("REFUSED -- --run-train requires --go")
            return 4
        print("=" * 78)
        print("TREE SUBSET-RETRAIN (R2 stage B) -- GO-gated run-train")
        print("=" * 78)
        return run_train(args.go)
    print("=" * 78)
    print("TREE SUBSET-RETRAIN (R2 stage B) -- SELF-CHECK (synthetic only)")
    print("=" * 78)
    out, n_fail, code_sha = run_self_check()
    if not args.no_log_append:
        append_self_check_log(out, code_sha)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
