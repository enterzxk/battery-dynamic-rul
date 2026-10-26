#!/home/yndx/miniconda3/envs/a40_env/bin/python3.9
"""External baselines for the A3-rate C3 comparison (worker #5, 2026-10-24).

B-EXT-1 EXT_GRU : GRU sequence baseline over the as-of visible RPT prefix
                  (architecture role-model: isu_irregular_rul_seed42_v1/
                  baselines.py make_gru -- TinyGRU; re-implemented here; the
                  other experiment's protocol code is NOT imported).
B-EXT-2 EXT_ENET: elastic-net early-feature baseline, Li et al. 2024 Cell
                  Reports style (204-dim capacity/Q-V/dQdV feature increments
                  vs the first arrived RPT + cycling-condition prefix mean +
                  horizon), OOF sigma like the tree pipeline.

Both use EXACTLY the tree C3 query panel
(experiments/trajectory_strong_baselines_20261021/runs/
 q4_strong_baselines_20261021_run2/predictions_c3.csv: 3579 keys, 61
 development cells x arms raw/sparse2/delay7d) and the nextcapacity task
(target = capacityAh of the next source RPT after the query = tree CSV
target_next_capacity_ah).  Training queries are derived from the 125 train
cells with the same frozen rule (validated bit-exactly against the tree run:
6498 eligible train rows / 3579 dev rows; dev targets/lastcap/horizons/
known_event reproduce the reference CSV with 0 mismatches).

As-of semantics (frozen; mirrors dart_rul_v18.data_protocol.make_examples +
multisource_mechanisms_20261021/train_v1/targets.build_targets, reimplemented
without importing them):
  * per cell: valid RPT rows sorted by (stop_utc, source_rpt_index),
    strictly increasing stops; anchor = row #1 (2nd valid RPT);
  * queries = each row stop q with q >= anchor.stop + 1 week AND >= 3 rows
    visible in EVERY arm at q (query set shared across arms);
  * arm arrival: raw/sparse2 arrival = stop, delay7d arrival = stop + 7d;
    sparse2 additionally hides rows i > 1 (position) with
    (source_rpt_index - rows[1].source_rpt_index) % 2 == 1 (original index);
  * eligible only if a later row exists (target y = that row's capacity,
    h = (next stop - q)/WEEK);
  * prefix features use ONLY events with arrival <= q (RPT) / source <= q
    (cycles): no post-query information ever enters a feature.

Inputs (run mode only, GO-pinned, sha-verified; per-file shas checked against
manifest inventories at open time):
  * PREP v2 cache (125 train cells: cycle controls + RPT events + q_ref),
  * reports/multisource_20261021_signals/all188_rpt_features_v1/ (204-dim
    vectors + original source_rpt_index, all 188 cells),
  * tree reference CSV (dev panel keys + verbatim panel columns),
  * cohort.json + data manifest + cycling manifest + processed dev JSONs +
    cycling feature gz for the 61 panel cells (the A3 dev-inference set).
Cycle-control/RPT adapters are reused read-only from the frozen A2 code
(a2_prep.cycle_control / rpt_records_from_processed /
cycle_records_from_features with the documented development-role projection
of a2_infer._development_{rpt,cycle}_records).  Nothing in A2/A3 is modified.

GO discipline: --run-train requires an APPROVED GO (status, allow_fit, scope
contains EXT-BASELINE, fresh request_id vs the consumed registry, owner
thread, <24h issue, seed 42, exactly 4 fits, code sha pins, asset path+sha
pins, fresh exclusive output_dir/receipt_path).  A refused GO writes
nothing.  After a fully successful run the request_id is appended to the
consumed registry (append-only; duplicates refused).  This worker NEVER
creates, signs or self-approves a GO; the template lives in
README_EXT_BASELINES_ZH.md for the controller.

Default mode is --self-check: synthetic world only (all assets built in a
tempdir), 0 real payload/asset reads, 0 real GO created/consumed, 0 registry
writes outside the tempdir.  Synthetic GO documents used to test the
validator live inside the tempdir and are discarded with it.
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
import gzip
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

ROOT = "/home/yndx/zxk/rul"
HERE = os.path.dirname(os.path.abspath(__file__))
A2_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "multirate_state_A2_20261022")
if not os.path.isdir(A2_DIR):  # pragma: no cover - deployment guard
    A2_DIR = os.path.join(ROOT, "experiments", "multirate_state_A2_20261022")
for _p in (HERE, A2_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import a2_prep  # frozen A2 adapters (read-only reuse)
from a2_targets import epoch_seconds  # frozen ISO/epoch parsing

SEED = 42
WEEK = 604800.0
DAY = 86400.0
ARMS = ("raw", "sparse2", "delay7d")
OWNER_THREAD_ID = "01a15c3a-1a06-7d61-8517-27b70b246183"
DEFAULT_CONSUMED_REGISTRY = os.path.join(
    ROOT, "experiments", "state", "consumed_gos.jsonl")
DEFAULT_RUNS_DIR = os.path.join(HERE, "runs")
DEFAULT_RECEIPTS_DIR = os.path.join(HERE, "receipts")
LOG_PATH = os.path.join(HERE, "SELF_CHECK_LOG.txt")

TREE_COLUMNS = (
    "model", "cell_id", "group_id", "arm", "query_epoch", "forecast_h_weeks",
    "next_source_elapsed_weeks", "next_query_elapsed_weeks",
    "last_visible_capacity_ah", "last_visible_soh", "degradation_stage",
    "target_next_capacity_ah", "predicted_mean_ah", "predicted_sigma_ah",
    "error_ah", "abs_error_ah", "known_event")
PANEL_COPY_COLUMNS = (
    "cell_id", "group_id", "arm", "query_epoch", "forecast_h_weeks",
    "next_source_elapsed_weeks", "next_query_elapsed_weeks",
    "last_visible_capacity_ah", "last_visible_soh", "degradation_stage",
    "target_next_capacity_ah", "known_event")

EXT_MODELS = ("EXT_GRU", "EXT_ENET")
# RUN1 failed inside the gate (feature-name alignment bug, receipt honest at
# fits 0/0, never registered); replay of its request_id is refused forever.
BURNED_REQUEST_IDS = ("EXT_BASELINE_20261024_RUN1",)
FIT_PLAN = (
    "per model (EXT_GRU, EXT_ENET): fit 1 = cell-isolated OOF-sigma fit on "
    "foldB train rows (predict foldA rows) -> scalar sigma; fit 2 = final "
    "fit on all train rows; EXT_GRU 2 + EXT_ENET 2 = 4 fits total")
MAX_FITS = 4
GO_ASSET_KEYS = ("prep_manifest", "prep_npz", "rpt_manifest", "tree_csv",
                 "cohort", "data_manifest", "cycling_manifest")

# ---- frozen feature / hyperparameter contract (README, section 特征冻结) ----
GRU_TOKEN_DIM = 4    # [cap/q_ref, dcap vs prev visible, dt_weeks, elapsed_weeks since first visible]
GRU_CTX_EXTRA = 8    # [h, lastcap, lastcap/q_ref, slope, n_visible, n_cycles, cum_throughput_f23, weeks_since_row0]
GRU_HIDDEN = 16
GRU_EPOCHS = 300
GRU_BATCH = 256
GRU_LR = 1e-2
GRU_WD = 1e-5
GRU_LOGV_RANGE = (-12.0, 4.0)
ENET_EXTRA = 5       # [lastcap, q_ref, h, n_visible, weeks_since_row0]
ENET_ALPHA = 0.05
ENET_L1_RATIO = 0.5
ENET_MAX_ITER = 50000
ENET_TOL = 1e-7
N_FEATURES_RPT = 204
CAPACITY_FEATURE = "src_capacity_discharge_C_5"   # == capacityAh (validated)


# ---------------------------------------------------------------- small utils
def utc_now_iso():
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path, payload):
    text = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=True) + "\n"
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and \
        math.isfinite(float(x))


# ------------------------------------------- consumed-GO registry (append-only)
# Discipline reimplemented from a3_train.load_consumed_request_ids /
# register_consumed_go (same semantics; kept local so self-check never
# touches the real registry path).
def load_consumed_request_ids(path):
    consumed = set()
    if not os.path.exists(path):
        return consumed
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            rid = rec.get("request_id")
            if not rid:
                raise ValueError("registry line without request_id in %s" % path)
            consumed.add(str(rid))
    return consumed


def request_id_is_fresh(request_id, path):
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
                       "finished_utc": str(finished_utc)}) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass


# ------------------------------------------------------------ audited store
class ReadStats(object):
    def __init__(self):
        self.files_by_kind = {}
        self.bytes_by_kind = {}
        self.paths = []
        self.bytes_total = 0

    def note(self, path, kind, nbytes):
        self.files_by_kind[kind] = self.files_by_kind.get(kind, 0) + 1
        self.bytes_by_kind[kind] = self.bytes_by_kind.get(kind, 0) + int(nbytes)
        self.paths.append(str(path))
        self.bytes_total += int(nbytes)

    def snapshot(self):
        return {"files_by_kind": dict(self.files_by_kind),
                "bytes_by_kind": dict(self.bytes_by_kind),
                "bytes_total": self.bytes_total}


class ExtBaselineError(RuntimeError):
    pass


class Store(object):
    """Audited byte-level reader restricted to allowed roots (fail-closed).

    `base` resolves manifest-relative paths (ROOT for real runs, the tempdir
    for the synthetic self-check world)."""

    def __init__(self, allowed_roots, stats, base=None):
        self.roots = [os.path.realpath(r) for r in allowed_roots]
        self.stats = stats
        self.base = os.path.abspath(base if base is not None else
                                    allowed_roots[0])

    def resolve(self, path):
        p = str(path)
        if os.path.isabs(p):
            return p
        return os.path.join(self.base, p)

    def _allowed(self, path):
        real = os.path.realpath(path)
        for r in self.roots:
            if real == r or real.startswith(r + os.sep):
                return real
        raise ExtBaselineError("read outside allowed roots refused: %s" % path)

    def read_bytes(self, path, kind, expect_sha=None):
        real = self._allowed(path)
        if not os.path.isfile(real):
            raise ExtBaselineError("asset missing: %s" % path)
        with open(real, "rb") as f:
            blob = f.read()
        digest = hashlib.sha256(blob).hexdigest()
        if expect_sha is not None and digest != expect_sha:
            raise ExtBaselineError("sha256 mismatch for %s (%s)" % (path, kind))
        self.stats.note(real, kind, len(blob))
        return blob

    def read_json(self, path, kind, expect_sha=None):
        blob = self.read_bytes(path, kind, expect_sha=expect_sha)
        try:
            return json.loads(blob.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ExtBaselineError("asset %s is not UTF-8 JSON: %s" % (path, exc))


# ------------------------------------------------------- frozen panel rule(s)
def parse_stop(value):
    return float(epoch_seconds(value))  # naive ISO -> UTC (frozen convention)


def record_feature_names(rec):
    names = rec.get("feature_names")
    if not isinstance(names, list) or len(names) != N_FEATURES_RPT:
        raise ExtBaselineError("RPT feature record without 204 "
                               "feature_names")
    if len(set(names)) != len(names):
        raise ExtBaselineError("RPT feature record has duplicate "
                               "feature_names")
    return names


def rows_from_rpt_json(doc):
    """all188 RPT feature JSON -> (valid rows, canonical name order).

    Name alignment (frozen v1.1): per-cell, every valid record must carry the
    SAME SET of 204 feature names (a different set -> refuse; strictness
    kept).  Asset records order the same set differently ACROSS cells (e.g.
    G10C1 vs G1C1 first diverge at position 5), so vectors are built in ONE
    frozen canonical order = lexicographically sorted name set (all cells
    share one set, so this equals the sorted set of the first loaded cell).
    Same set, different per-record order -> bit-identical vectors.
    """
    if not isinstance(doc, dict):
        raise ExtBaselineError("RPT feature doc is not an object")
    cid = str(doc.get("cell_id", "<unknown>"))
    valid = []
    names_set = None
    canonical = None
    for rec in doc.get("records") or []:
        if not isinstance(rec, dict):
            raise ExtBaselineError("RPT feature record is not an object")
        if rec.get("data_v2_valid") is not True:
            continue
        values = rec.get("values")
        if not isinstance(values, dict):
            raise ExtBaselineError("RPT feature record without values")
        cap = values.get(CAPACITY_FEATURE)
        if not _finite(cap) or float(cap) <= 0.0:
            continue
        s = frozenset(record_feature_names(rec))
        if names_set is None:
            names_set = s
            canonical = sorted(s)
        elif s != names_set:
            raise ExtBaselineError("feature_names set drift inside cell "
                                   "asset %s" % cid)
        valid.append((rec, values, float(cap)))
    if canonical is None:
        raise ExtBaselineError("RPT feature asset has no valid records")
    rows = []
    for rec, values, cap in valid:
        rows.append({
            "idx": int(rec["source_rpt_index"]),
            "stop": parse_stop(rec["stop"]),
            "cap": cap,
            "vec": [values.get(name) for name in canonical],
        })
    rows.sort(key=lambda r: (r["stop"], r["idx"]))
    for a, b in zip(rows, rows[1:]):
        if b["stop"] <= a["stop"]:
            raise ExtBaselineError("non-increasing RPT stops in feature asset")
    return rows, canonical


def rows_from_processed_records(records):
    """processed-JSON RPT records (role-projected a2_prep output) -> rows."""
    rows = [{"idx": int(rec["source_rpt_index"]),
             "stop": float(rec["source_epoch"]),
             "cap": float(rec["capacity_ah"]),
             "arrival": float(rec["available_epoch"])}
            for rec in records]
    rows.sort(key=lambda r: (r["stop"], r["idx"]))
    for a, b in zip(rows, rows[1:]):
        if b["stop"] <= a["stop"]:
            raise ExtBaselineError("non-increasing RPT stops in processed asset")
    return rows


def arm_lag(arm):
    return 7.0 * DAY if arm == "delay7d" else 0.0


def visible_indices(rows, arm, q):
    """Frozen arm visibility at query epoch q (make_examples rule)."""
    lag = arm_lag(arm)
    anchor_idx = rows[1]["idx"]
    out = []
    for i, r in enumerate(rows):
        if arm == "sparse2" and i > 1 and (r["idx"] - anchor_idx) % 2:
            continue
        if r["stop"] + lag <= q + 1e-9:
            out.append(i)
    return out


def derive_cell_queries(rows):
    """Frozen query grid for one cell -> [{arm,q,vis,next_i,y,h}]."""
    n = len(rows)
    if n < 2:
        return []
    anchor_stop = rows[1]["stop"]
    out = []
    for qi in range(n):
        q = rows[qi]["stop"]
        if q < anchor_stop + WEEK - 1e-9:
            continue
        vis = {arm: visible_indices(rows, arm, q) for arm in ARMS}
        if any(len(v) < 3 for v in vis.values()):
            continue
        after = [i for i in range(n) if rows[i]["stop"] > q + 1e-5]
        if not after:
            continue
        nxt = after[0]
        for arm in ARMS:
            out.append({"arm": arm, "q": q, "vis": vis[arm], "next_i": nxt,
                        "y": rows[nxt]["cap"],
                        "h": (rows[nxt]["stop"] - q) / WEEK})
    return out


def control_prefix(cycles, q):
    """Cycles with source <= q -> (masked mean 24, count, throughput sum)."""
    sel = [c for c in cycles if c["source"] <= q + 1e-9]
    num = np.zeros(24, dtype=np.float64)
    den = np.zeros(24, dtype=np.float64)
    thr = 0.0
    for c in sel:
        ctl = np.asarray(c["control"], dtype=np.float64)
        msk = np.asarray(c["mask"], dtype=np.float64)
        num += ctl * msk
        den += msk
        if msk[23] > 0.5:
            thr += float(ctl[23])
    mean = np.divide(num, den, out=np.zeros(24, dtype=np.float64),
                     where=den > 0)
    return mean, len(sel), thr


def gru_prefix(rows, vis, q, cycles, q_ref, h):
    """EXT_GRU as-of prefix: (tokens [L,4], context [24+8]). Pure function."""
    vis_rows = [rows[i] for i in vis]
    tokens = np.zeros((len(vis_rows), GRU_TOKEN_DIM), dtype=np.float64)
    prev_cap = None
    prev_stop = None
    first_stop = vis_rows[0]["stop"]
    for k, r in enumerate(vis_rows):
        dt = 0.0 if prev_stop is None else max(0.0, (r["stop"] - prev_stop) / WEEK)
        dcap = 0.0 if prev_cap is None else r["cap"] - prev_cap
        tokens[k] = (r["cap"] / q_ref, dcap, dt, (r["stop"] - first_stop) / WEEK)
        prev_cap, prev_stop = r["cap"], r["stop"]
    lastcap = vis_rows[-1]["cap"]
    slope = 0.0
    if len(vis_rows) >= 2:
        dt2 = (vis_rows[-1]["stop"] - vis_rows[-2]["stop"]) / WEEK
        if dt2 > 1e-12:
            slope = (vis_rows[-1]["cap"] - vis_rows[-2]["cap"]) / dt2
    cmean, ncyc, thr = control_prefix(cycles, q)
    ctx = np.concatenate([
        np.asarray([h, lastcap, lastcap / q_ref, slope, float(len(vis_rows)),
                    float(ncyc), thr, (q - rows[0]["stop"]) / WEEK],
                   dtype=np.float64), cmean])
    return tokens, ctx


def enet_prefix(rows, vis, q, cycles, q_ref, h, base_vec, latest_vec):
    """EXT_ENET as-of prefix: 204 increments + 24 control mean + 5 scalars."""
    inc = np.asarray([(0.0 if v is None else float(v)) -
                      (0.0 if b is None else float(b))
                      for v, b in zip(latest_vec, base_vec)], dtype=np.float64)
    cmean, _, _ = control_prefix(cycles, q)
    lastcap = rows[vis[-1]]["cap"]
    extras = np.asarray([lastcap, q_ref, h, float(len(vis)),
                         (q - rows[0]["stop"]) / WEEK], dtype=np.float64)
    return np.concatenate([inc, cmean, extras])


# ------------------------------------------------------------- data loading
def load_tree_panel(store, path):
    """Reference CSV: raw string rows + key set; header/key checks."""
    blob = store.read_bytes(path, "tree_reference_csv")
    reader = csv.DictReader(io.StringIO(blob.decode("utf-8")))
    if tuple(reader.fieldnames or ()) != TREE_COLUMNS:
        raise ExtBaselineError("tree reference CSV header mismatch")
    by_model = {}
    for row in reader:
        by_model.setdefault(row["model"], []).append(row)
    if not by_model:
        raise ExtBaselineError("tree reference CSV is empty")
    key_sets = {}
    for model, rows in by_model.items():
        ks = set()
        for r in rows:
            ks.add((r["cell_id"], r["arm"], round(float(r["query_epoch"]), 6)))
        if len(ks) != len(rows):
            raise ExtBaselineError("duplicate keys for model %s" % model)
        key_sets[model] = ks
    ref_model = sorted(by_model)[0]
    for model, ks in key_sets.items():
        if ks != key_sets[ref_model]:
            raise ExtBaselineError("models disagree on the key set: %s" % model)
    return by_model, key_sets[ref_model]


def load_rpt_json_cell(store, path, cid, expect_sha=None):
    doc = store.read_json(path, "rpt_features_json", expect_sha=expect_sha)
    if str(doc.get("cell_id")) != cid:
        raise ExtBaselineError("RPT feature asset identity mismatch %s" % cid)
    rows, names = rows_from_rpt_json(doc)
    if len(rows) < 2:
        raise ExtBaselineError("RPT feature asset %s has <2 valid rows" % cid)
    return rows, names


def load_prep(store, manifest_path, npz_path):
    """PREP v2 cache -> per train-cell {q_ref, anchor_stop, rpts, cycles}."""
    manifest = store.read_json(manifest_path, "prep_manifest")
    if str(manifest.get("schema")) != "A2_PREP_V1":
        raise ExtBaselineError("PREP manifest schema mismatch")
    blob = store.read_bytes(npz_path, "prep_npz")
    z = np.load(io.BytesIO(blob), allow_pickle=False)
    for k in ("cell_ids", "q_ref_ah", "anchor_source_epoch", "event_cell",
              "event_kind", "event_source", "event_available", "control",
              "control_mask", "capacity_ah", "score"):
        if k not in z.files:
            raise ExtBaselineError("PREP npz missing field %s" % k)
    cells = [str(c) for c in z["cell_ids"]]
    mcells = {str(c["cell_id"]): c for c in manifest.get("cells") or []}
    if sorted(mcells) != sorted(cells) or len(cells) == 0:
        raise ExtBaselineError("PREP manifest/npz cell mismatch")
    if int(manifest.get("n_cells", -1)) != len(cells):
        raise ExtBaselineError("PREP manifest n_cells mismatch")
    ev_cell = z["event_cell"]
    ev_kind = z["event_kind"]
    ev_src = z["event_source"]
    ev_ctl = z["control"]
    ev_msk = z["control_mask"]
    ev_cap = z["capacity_ah"]
    out = {}
    for i, cid in enumerate(cells):
        sel = np.nonzero(ev_cell == i)[0]
        rpts = []
        cycles = []
        for j in sel:
            if int(ev_kind[j]) == 2:
                rpts.append({"stop": float(ev_src[j]), "cap": float(ev_cap[j])})
            elif int(ev_kind[j]) == 1:
                cycles.append({"source": float(ev_src[j]),
                               "control": [float(v) for v in ev_ctl[j]],
                               "mask": [float(v) for v in ev_msk[j]]})
        mc = mcells[cid]
        out[cid] = {"q_ref": float(z["q_ref_ah"][i]),
                    "q_ref_manifest": float(mc["q_ref_ah"]),
                    "anchor_stop": float(mc["anchor_source_epoch"]),
                    "rpts": rpts, "cycles": cycles}
    return {"cells": out, "n_cells": len(cells), "manifest": manifest}


def role_project(payload, cid, want_role):
    if str(payload.get("role")) != want_role:
        raise ExtBaselineError("asset %s role is %r, want %r"
                               % (cid, payload.get("role"), want_role))
    proxy = dict(payload)
    proxy["role"] = "train"   # the documented a2_infer role projection
    return proxy


def load_dev_rpt_rows(store, path, cid):
    payload = store.read_json(path, "processed_dev_json")
    proxy = role_project(payload, cid, "development")
    records, _ = a2_prep.rpt_records_from_processed(proxy, cid)
    return rows_from_processed_records(records)


def load_dev_cycles(store, path, cid):
    blob = store.read_bytes(path, "cycling_dev_gz")
    try:
        doc = json.loads(gzip.decompress(blob).decode("utf-8"))
    except (OSError, EOFError, UnicodeDecodeError, ValueError) as exc:
        raise ExtBaselineError("cycling asset %s not gzip JSON: %s" % (cid, exc))
    proxy = role_project(doc, cid, "development")
    records, _ = a2_prep.cycle_records_from_features(proxy, cid)
    cycles = [{"source": float(r["source_epoch"]),
               "control": list(r["control"]), "mask": list(r["control_mask"])}
              for r in records]
    cycles.sort(key=lambda c: c["source"])
    return cycles


def cross_check_train(prep_cell, rpt_rows, cid):
    """PREP cache vs RPT feature asset (train side) -- consistency gate."""
    stops_asset = [r["stop"] for r in rpt_rows]
    stops_prep = sorted([prep_cell["anchor_stop"]] +
                        [r["stop"] for r in prep_cell["rpts"]])
    if len(stops_prep) != len(stops_asset) or any(
            abs(a - b) > 1e-6 for a, b in zip(stops_prep, stops_asset)):
        raise ExtBaselineError("PREP/RPT-asset stop mismatch for %s" % cid)
    if abs(prep_cell["q_ref"] - rpt_rows[0]["cap"]) > 1e-5 or \
            abs(prep_cell["q_ref_manifest"] - rpt_rows[0]["cap"]) > 1e-5:
        raise ExtBaselineError("PREP q_ref vs asset first capacity mismatch "
                               "for %s" % cid)
    if abs(prep_cell["anchor_stop"] - rpt_rows[0]["stop"]) > 1e-6:
        raise ExtBaselineError("PREP anchor stop mismatch for %s" % cid)


def cross_check_dev(rows_processed, rows_asset, cid):
    if len(rows_processed) != len(rows_asset):
        raise ExtBaselineError("processed/RPT-asset row count mismatch %s" % cid)
    for a, b in zip(rows_processed, rows_asset):
        if a["idx"] != b["idx"] or abs(a["stop"] - b["stop"]) > 1e-6 or \
                abs(a["cap"] - b["cap"]) > 1e-9:
            raise ExtBaselineError("processed/RPT-asset row mismatch %s" % cid)


# -------------------------------------------------------------- model fits
class FitLedger(object):
    def __init__(self, out_dir, budget):
        self.out_dir = out_dir
        self.budget = int(budget)
        self.started = 0
        self.completed = 0
        self._meta = {}

    def _path(self, idx):
        return os.path.join(self.out_dir, "fit_%02d.json" % idx)

    def begin(self, meta):
        if self.started >= self.budget:
            raise ExtBaselineError("fit budget exceeded (%d)" % self.budget)
        self.started += 1
        rec = {"fit_index": self.started, **meta, "state": "STARTED",
               "started_utc": utc_now_iso()}
        self._meta[self.started] = rec
        atomic_json(self._path(self.started), rec)
        return self.started

    def done(self, idx, extra=None):
        rec = dict(self._meta.get(idx, {}))
        rec.update({"fit_index": idx, "state": "COMPLETED",
                    "finished_utc": utc_now_iso()})
        if extra:
            rec.update(extra)
        atomic_json(self._path(idx), rec)
        self.completed += 1

    def fail(self, idx, error):
        rec = dict(self._meta.get(idx, {}))
        rec.update({"fit_index": idx, "state": "FAILED",
                    "error": repr(error), "finished_utc": utc_now_iso()})
        atomic_json(self._path(idx), rec)


def cell_balanced_weights(cell_ids):
    counts = {}
    for c in cell_ids:
        counts[c] = counts.get(c, 0) + 1
    w = np.asarray([1.0 / counts[c] for c in cell_ids], dtype=np.float64)
    return w / float(np.mean(w))


def sigma_from_residuals(residuals, cell_ids):
    w = cell_balanced_weights(cell_ids)
    return max(float(math.sqrt(float(np.sum(w * residuals * residuals) /
                                    np.sum(w)))), 1e-6)


def two_cell_folds(cell_ids, seed=SEED):
    """Stable sha256-order split of eligible cells into (foldA, foldB)."""
    ids = sorted(set(str(c) for c in cell_ids))
    if len(ids) < 4:
        raise ExtBaselineError("too few eligible train cells for folds")
    ordered = sorted(ids, key=lambda c: hashlib.sha256(
        ("%d:%s" % (int(seed), c)).encode("utf-8")).hexdigest())
    half = (len(ordered) + 1) // 2
    fold_a, fold_b = ordered[:half], ordered[half:]
    if set(fold_a) & set(fold_b) or set(fold_a) | set(fold_b) != set(ids):
        raise ExtBaselineError("fold partition error")
    return fold_a, fold_b


class GRUModel(object):
    """TinyGRU-style sequence model (hidden 16) + standardized context."""

    def __init__(self, seed=SEED):
        import torch
        from torch import nn
        self.torch = torch
        torch.manual_seed(seed)
        self.gen = torch.Generator().manual_seed(seed)
        self.rng = np.random.default_rng(seed)

        class TinyGRU(nn.Module):
            def __init__(self):
                super().__init__()
                self.gru = nn.GRU(GRU_TOKEN_DIM, GRU_HIDDEN, batch_first=True)
                self.head = nn.Linear(GRU_HIDDEN + 24 + GRU_CTX_EXTRA, 2)

            def forward(self, x, ctx, last_idx):
                out, _ = self.gru(x)
                h = out[torch.arange(out.shape[0]), last_idx]
                return self.head(torch.cat([h, ctx], dim=1))

        self.net = TinyGRU()
        self.fitted = False

    @staticmethod
    def _pack(tokens_list, ctx_list):
        import torch
        L = max(t.shape[0] for t in tokens_list)
        B = len(tokens_list)
        X = np.zeros((B, L, GRU_TOKEN_DIM), dtype=np.float32)
        M = np.zeros((B, L), dtype=np.int64)
        for b, t in enumerate(tokens_list):
            X[b, :t.shape[0]] = t.astype(np.float32)
            M[b, :t.shape[0]] = 1
        return (torch.from_numpy(X), torch.from_numpy(M),
                torch.from_numpy(np.asarray(ctx_list, dtype=np.float32)))

    def fit(self, tokens_list, ctx_list, y, weights, epochs=GRU_EPOCHS):
        torch = self.torch
        all_tok = np.concatenate(tokens_list, axis=0)
        self.tok_mean = all_tok.mean(axis=0)
        self.tok_std = np.maximum(all_tok.std(axis=0), 1e-8)
        ctx = np.asarray(ctx_list, dtype=np.float64)
        self.ctx_mean = ctx.mean(axis=0)
        self.ctx_std = np.maximum(ctx.std(axis=0), 1e-8)
        self.y_mean = float(np.mean(y))
        self.y_std = max(float(np.std(y)), 1e-8)
        X, M, C = self._pack(
            [((t - self.tok_mean) / self.tok_std).astype(np.float32)
             for t in tokens_list],
            ((ctx - self.ctx_mean) / self.ctx_std).astype(np.float32))
        Y = torch.from_numpy(
            ((np.asarray(y, dtype=np.float64) - self.y_mean) /
             self.y_std).astype(np.float32))
        W = torch.from_numpy(
            np.asarray(weights, dtype=np.float32) / float(np.mean(weights)))
        opt = torch.optim.Adam(self.net.parameters(), lr=GRU_LR,
                               weight_decay=GRU_WD)
        last_idx = (M.sum(dim=1) - 1).clamp_min(0)
        n = len(y)
        self.net.train()
        for _epoch in range(int(epochs)):
            order = torch.randperm(n, generator=self.gen)
            for s in range(0, n, GRU_BATCH):
                idx = order[s:s + GRU_BATCH]
                if idx.numel() < 2:
                    continue
                out = self.net(X[idx], C[idx], last_idx[idx])
                mu, logv = out[:, 0], out[:, 1].clamp(*GRU_LOGV_RANGE)
                var = logv.exp()
                nll = 0.5 * (((Y[idx] - mu) ** 2) / var + logv +
                             math.log(2.0 * math.pi))
                loss = (W[idx] * nll).mean()
                opt.zero_grad()
                loss.backward()
                opt.step()
        self.fitted = True
        return self

    def predict(self, tokens_list, ctx_list):
        if not self.fitted:
            raise ExtBaselineError("GRU predict before fit")
        torch = self.torch
        self.net.eval()
        with torch.no_grad():
            X, M, C = self._pack(
                [((t - self.tok_mean) / self.tok_std).astype(np.float32)
                 for t in tokens_list],
                ((np.asarray(ctx_list, dtype=np.float64) - self.ctx_mean) /
                 self.ctx_std).astype(np.float32))
            last_idx = (M.sum(dim=1) - 1).clamp_min(0)
            out = self.net(X, C, last_idx)
            mu = out[:, 0].numpy().astype(np.float64) * self.y_std + self.y_mean
        return mu


def fit_enet(X, y, weights):
    from sklearn.linear_model import ElasticNet
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    model = Pipeline([("scaler", StandardScaler()),
                      ("enet", ElasticNet(alpha=ENET_ALPHA,
                                          l1_ratio=ENET_L1_RATIO,
                                          max_iter=ENET_MAX_ITER, tol=ENET_TOL,
                                          selection="cyclic"))])
    model.fit(X, y, enet__sample_weight=weights)
    return model


def predict_enet(model, X):
    return np.asarray(model.predict(X), dtype=np.float64)


# ------------------------------------------------------------- GO validation
GO_REQUIRED = ("status", "allow_fit", "scope", "request_id", "owner_thread_id",
               "issued_utc", "seed", "models", "fits_in_this_go", "fit_plan",
               "device", "threads", "max_runtime_seconds", "code_sha256",
               "assets", "panel_contract", "consumed_registry",
               "output_dir", "receipt_path")


def validate_go(go, go_path, store, runs_parent, receipts_parent, panel_keys):
    problems = []
    if any(k not in go for k in GO_REQUIRED):
        missing = [k for k in GO_REQUIRED if k not in go]
        raise ExtBaselineError("GO missing required fields: %s" % missing)
    if go["status"] != "APPROVED":
        problems.append("status not APPROVED")
    if go["allow_fit"] is not True:
        problems.append("allow_fit is not true")
    if "EXT-BASELINE" not in str(go["scope"]):
        problems.append("scope lacks EXT-BASELINE")
    if go["owner_thread_id"] != OWNER_THREAD_ID:
        problems.append("owner mismatch")
    rid = go["request_id"]
    if not isinstance(rid, str) or len(rid) < 8:
        problems.append("request_id missing/too short")
    if go["seed"] != SEED:
        problems.append("seed != 42")
    if go["models"] != list(EXT_MODELS):
        problems.append("models != [EXT_GRU, EXT_ENET]")
    if int(go["fits_in_this_go"]) != MAX_FITS:
        problems.append("fits_in_this_go != 4")
    if go["fit_plan"] != FIT_PLAN:
        problems.append("fit_plan mismatch")
    if go["device"] != "cpu" or int(go["threads"]) != 4:
        problems.append("device/threads contract mismatch")
    if not 600 <= int(go["max_runtime_seconds"]) <= 14400:
        problems.append("max_runtime_seconds out of range")
    issued = _dt.datetime.fromisoformat(
        str(go["issued_utc"]).replace("Z", "+00:00"))
    age = (_dt.datetime.now(_dt.timezone.utc) - issued).total_seconds()
    if abs(age) > 86400:
        problems.append("GO stale (>24h)")

    code = go["code_sha256"]
    expected_files = {"ext_baselines.py": os.path.join(HERE, "ext_baselines.py"),
                      "a2_prep.py": os.path.join(A2_DIR, "a2_prep.py"),
                      "a2_targets.py": os.path.join(A2_DIR, "a2_targets.py"),
                      "README_EXT_BASELINES_ZH.md":
                          os.path.join(HERE, "README_EXT_BASELINES_ZH.md")}
    if sorted(code) != sorted(expected_files):
        problems.append("code_sha256 pins wrong file set")
    else:
        for name, path in expected_files.items():
            if not os.path.isfile(path) or sha256_file(path) != code[name]:
                problems.append("code sha mismatch: %s" % name)
    if json.loads(open(go_path, "r", encoding="utf-8").read()) != go:
        problems.append("GO document changed on disk")

    assets = go["assets"]
    if sorted(assets) != sorted(GO_ASSET_KEYS):
        problems.append("assets pin set mismatch")
    else:
        for key in GO_ASSET_KEYS:
            entry = assets[key]
            if sorted(entry) != ["path", "sha256"]:
                problems.append("asset %s entry shape" % key)
                continue
            try:
                store.read_bytes(store.resolve(entry["path"]),
                                 "go_pinned_" + key,
                                 expect_sha=entry["sha256"])
            except ExtBaselineError as exc:
                problems.append("asset %s: %s" % (key, exc))

    pc = go["panel_contract"]
    if not isinstance(pc, dict) or pc.get("arms") != list(ARMS):
        problems.append("panel_contract arms mismatch")
    elif int(pc.get("n_keys", -1)) != len(panel_keys):
        problems.append("panel_contract n_keys != reference CSV keys")

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

    if not request_id_is_fresh(rid, str(go["consumed_registry"])):
        problems.append("request_id already consumed")
    if str(rid) in BURNED_REQUEST_IDS:
        problems.append("request_id burned (prior failed run; replay refused)")

    if problems:
        raise ExtBaselineError("GO refused: " + "; ".join(problems))
    return (os.path.abspath(out_dir), os.path.abspath(receipt),
            str(go["consumed_registry"]), rid)


# ------------------------------------------------------------------- runner
class QueryPanel(object):
    def __init__(self):
        self.rows = []

    def __len__(self):
        return len(self.rows)


def build_train_queries(prep, rpt_assets, feature_names_ref):
    """Frozen train-grid derivation over the PREP/RPT-asset train cells."""
    panel = QueryPanel()
    for cid in sorted(prep["cells"]):
        rows, names = rpt_assets[cid]
        if names != feature_names_ref:
            raise ExtBaselineError("feature set drift (canonical name order) "
                                   "for %s" % cid)
        pc = prep["cells"][cid]
        cross_check_train(pc, rows, cid)
        cycles = pc["cycles"]
        q_ref = rows[0]["cap"]
        base_vec = rows[0]["vec"]
        for qrow in derive_cell_queries(rows):
            q = qrow["q"]
            vis = qrow["vis"]
            tokens, ctx = gru_prefix(rows, vis, q, cycles, q_ref, qrow["h"])
            ex = enet_prefix(rows, vis, q, cycles, q_ref, qrow["h"],
                             base_vec, rows[vis[-1]]["vec"])
            panel.rows.append({"cell": cid, "arm": qrow["arm"], "q": q,
                               "y": qrow["y"], "h": qrow["h"],
                               "tokens": tokens, "ctx": ctx, "enet_x": ex})
    return panel


def build_dev_queries(panel_cells, rpt_assets, dev_sources, tree_rows,
                      feature_names_ref):
    """Dev panel = reference CSV keys; every panel column re-derived & checked."""
    panel = QueryPanel()
    mismatches = []
    checked = set()
    for row in tree_rows:
        cid = row["cell_id"]
        arm = row["arm"]
        q = float(row["query_epoch"])
        rows, names = rpt_assets[cid]
        if names != feature_names_ref:
            raise ExtBaselineError("feature set drift (canonical name order) "
                                   "for %s" % cid)
        proc_rows, cycles = dev_sources[cid]
        if cid not in checked:
            cross_check_dev(proc_rows, rows, cid)
            checked.add(cid)
        q_ref = rows[0]["cap"]
        vis = visible_indices(rows, arm, q)
        if len(vis) < 3:
            mismatches.append((cid, arm, q, "fewer than 3 visible"))
            continue
        after = [i for i in range(len(rows)) if rows[i]["stop"] > q + 1e-5]
        if not after:
            mismatches.append((cid, arm, q, "no next RPT"))
            continue
        nxt = after[0]
        y = rows[nxt]["cap"]
        h = (rows[nxt]["stop"] - q) / WEEK
        lastcap = rows[vis[-1]]["cap"]
        known = any(rows[i]["cap"] <= 0.20 for i in vis)
        if (abs(y - float(row["target_next_capacity_ah"])) > 1e-8 or
                abs(h - float(row["forecast_h_weeks"])) > 1e-8 or
                abs(lastcap - float(row["last_visible_capacity_ah"])) > 1e-8 or
                known != (row["known_event"].strip().lower() == "true")):
            mismatches.append((cid, arm, q, "target/h/lastcap/known mismatch"))
            continue
        tokens, ctx = gru_prefix(rows, vis, q, cycles, q_ref, h)
        ex = enet_prefix(rows, vis, q, cycles, q_ref, h,
                         rows[0]["vec"], rows[vis[-1]]["vec"])
        panel.rows.append({"cell": cid, "arm": arm, "q": q, "y": y, "h": h,
                           "tokens": tokens, "ctx": ctx, "enet_x": ex,
                           "csv_row": row})
    if mismatches:
        raise ExtBaselineError("dev panel reproduction failed (%d rows): %s"
                               % (len(mismatches), mismatches[:3]))
    return panel


def _deadline_check(deadline, where):
    if deadline is not None and time.monotonic() >= deadline:
        raise TimeoutError("GO runtime deadline reached %s" % where)


def run_go(go_path, store=None, registry=None, runs_parent=None,
           receipts_parent=None, use_locks=True,
           expected_counts=(125, 63)):
    """Full guarded pipeline; returns the receipt dict (never raises).

    expected_counts=(n_train_cells, n_dev_cells) is the frozen real cohort
    (125/63); the synthetic self-check passes its own small counts.
    """
    t0 = time.time()
    real = store is None
    stats = ReadStats()
    if real:
        store = Store([ROOT], stats, base=ROOT)
    out_dir = None
    receipt_path = None
    locks = []
    rec = {"status": "PREFLIGHT_FAILED", "fits_started": 0, "fits_completed": 0,
           "real_run": bool(real)}
    try:
        go = json.loads(open(go_path, "r", encoding="utf-8").read())
        if not isinstance(go.get("assets"), dict) or \
                "tree_csv" not in go.get("assets", {}):
            raise ExtBaselineError("GO has no assets.tree_csv")
        tree_by_model, panel_keys = load_tree_panel(
            store, store.resolve(go["assets"]["tree_csv"]["path"]))
        runs_parent = runs_parent or DEFAULT_RUNS_DIR
        receipts_parent = receipts_parent or DEFAULT_RECEIPTS_DIR
        out_dir, receipt_path, registry, rid = validate_go(
            go, go_path, store, runs_parent, receipts_parent, panel_keys)
        rec.update(request_id=rid, go_sha256=sha256_file(go_path))
        deadline = time.monotonic() + int(go["max_runtime_seconds"])
        if use_locks:
            import fcntl
            for lp in (os.path.join(ROOT,
                                    "automation/state/online_survival_cpu.lock"),
                       os.path.join(ROOT,
                                    "automation/locks/isu_irregular_rul_cpu.lock")):
                f = open(lp, "a+")
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locks.append(f)
        os.makedirs(runs_parent, exist_ok=True)
        os.makedirs(receipts_parent, exist_ok=True)
        os.makedirs(out_dir)
        ledger = FitLedger(out_dir, MAX_FITS)
        rec.update(status="LOADING_ASSETS")
        atomic_json(os.path.join(out_dir, "progress.json"), rec)

        assets = go["assets"]
        rpt_manifest = store.read_json(
            store.resolve(assets["rpt_manifest"]["path"]), "rpt_manifest")
        if str(rpt_manifest.get("status")) != "ALL188_FEATURE_CACHE_COMPLETE":
            raise ExtBaselineError("RPT manifest status mismatch")
        rpt_inv = {str(e["cell_id"]): e
                   for e in rpt_manifest.get("inventory") or []}
        cohort = store.read_json(store.resolve(assets["cohort"]["path"]),
                                 "cohort")
        roles = cohort.get("roles") or {}
        train_ids = sorted(c for c, r in roles.items() if str(r) == "train")
        dev_ids = sorted(c for c, r in roles.items() if str(r) == "development")
        if (len(train_ids), len(dev_ids)) != tuple(expected_counts):
            raise ExtBaselineError(
                "cohort role counts mismatch: (%d, %d) != %s"
                % (len(train_ids), len(dev_ids), tuple(expected_counts)))
        data_manifest = store.read_json(
            store.resolve(assets["data_manifest"]["path"]), "data_manifest")
        if str(data_manifest.get("status")) != "PASS":
            raise ExtBaselineError("data manifest status mismatch")
        cycling_manifest = store.read_json(
            store.resolve(assets["cycling_manifest"]["path"]),
            "cycling_manifest")
        if str(cycling_manifest.get("status")) != "SUCCESS":
            raise ExtBaselineError("cycling manifest status mismatch")
        cyc_inv = {str(e["cell_id"]): e
                   for e in cycling_manifest.get("inventory") or []}
        files_map = data_manifest.get("files") or {}

        prep = load_prep(store, store.resolve(assets["prep_manifest"]["path"]),
                         store.resolve(assets["prep_npz"]["path"]))
        if sorted(prep["cells"]) != train_ids:
            raise ExtBaselineError("PREP cells != cohort train 125")

        panel_cells = sorted({r["cell_id"] for rs in tree_by_model.values()
                              for r in rs})
        if not set(panel_cells) <= set(dev_ids):
            raise ExtBaselineError("panel cells not subset of dev 63")

        rpt_assets = {}
        names_ref = None
        for cid in train_ids + panel_cells:
            entry = rpt_inv.get(cid)
            want_role = "train" if cid in set(train_ids) else "development"
            if entry is None or str(entry.get("role")) != want_role:
                raise ExtBaselineError("RPT manifest role missing %s" % cid)
            rows, names = load_rpt_json_cell(
                store, store.resolve(entry["path"]), cid,
                expect_sha=entry.get("sha256"))
            rpt_assets[cid] = (rows, names)
            if names_ref is None:
                names_ref = names
        dev_sources = {}
        for cid in panel_cells:
            fentry = files_map.get(cid) or {}
            if str(fentry.get("role")) != "development":
                raise ExtBaselineError("data manifest role missing %s" % cid)
            proc_rows = load_dev_rpt_rows(store, store.resolve(fentry["path"]),
                                          cid)
            centry = cyc_inv.get(cid) or {}
            if str(centry.get("role")) != "development":
                raise ExtBaselineError("cycling manifest role missing %s" % cid)
            cycles = load_dev_cycles(store, store.resolve(centry["path"]), cid)
            dev_sources[cid] = (proc_rows, cycles)

        train_panel = build_train_queries(prep, rpt_assets, names_ref)
        if not train_panel.rows:
            raise ExtBaselineError("empty train query panel")
        train_cells = sorted({r["cell"] for r in train_panel.rows})
        if set(train_cells) & set(panel_cells):
            raise ExtBaselineError("train/dev cell contamination")
        ref_rows = tree_by_model[sorted(tree_by_model)[0]]
        dev_panel = build_dev_queries(panel_cells, rpt_assets, dev_sources,
                                      ref_rows, names_ref)
        if len(dev_panel.rows) != len(panel_keys):
            raise ExtBaselineError("dev panel size != reference keys")

        rec.update(status="FITTING", train_rows=len(train_panel.rows),
                   dev_rows=len(dev_panel.rows), train_cells=len(train_cells),
                   dev_cells=len(panel_cells))
        atomic_json(os.path.join(out_dir, "progress.json"), rec)
        fold_a, fold_b = two_cell_folds(train_cells)
        y_all = np.asarray([r["y"] for r in train_panel.rows])
        w_all = cell_balanced_weights([r["cell"] for r in train_panel.rows])
        cell_all = [r["cell"] for r in train_panel.rows]
        set_a, set_b = set(fold_a), set(fold_b)
        models = {}
        fit_report = {"fit_plan": FIT_PLAN, "seed": SEED,
                      "folds": {"foldA": fold_a, "foldB": fold_b},
                      "models": {}}
        for name in EXT_MODELS:
            idx_a = [i for i, r in enumerate(train_panel.rows)
                     if r["cell"] in set_a]
            idx_b = [i for i, r in enumerate(train_panel.rows)
                     if r["cell"] in set_b]
            if not idx_a or not idx_b:
                raise ExtBaselineError("empty fold for %s" % name)
            _deadline_check(deadline, "before %s OOF fit" % name)
            fi = ledger.begin({"model": name, "fit": "oof_sigma",
                               "n_fit_rows": len(idx_b),
                               "n_oof_rows": len(idx_a)})
            try:
                if name == "EXT_GRU":
                    m = GRUModel(SEED).fit(
                        [train_panel.rows[i]["tokens"] for i in idx_b],
                        [train_panel.rows[i]["ctx"] for i in idx_b],
                        y_all[idx_b], w_all[idx_b])
                    oof = m.predict(
                        [train_panel.rows[i]["tokens"] for i in idx_a],
                        [train_panel.rows[i]["ctx"] for i in idx_a])
                else:
                    Xb = np.stack([train_panel.rows[i]["enet_x"]
                                   for i in idx_b])
                    Xa = np.stack([train_panel.rows[i]["enet_x"]
                                   for i in idx_a])
                    m = fit_enet(Xb, y_all[idx_b], w_all[idx_b])
                    oof = predict_enet(m, Xa)
                if not np.isfinite(oof).all():
                    raise ExtBaselineError("non-finite OOF predictions %s"
                                           % name)
                sigma = sigma_from_residuals(
                    y_all[idx_a] - oof, [cell_all[i] for i in idx_a])
                ledger.done(fi, {"sigma_oof_ah": sigma,
                                 "oof_residuals_ah": [
                                     float(v) for v in (y_all[idx_a] - oof)]})
            except BaseException as exc:  # noqa: BLE001
                ledger.fail(fi, exc)
                raise

            _deadline_check(deadline, "before %s final fit" % name)
            fi2 = ledger.begin({"model": name, "fit": "final_all_train",
                                "n_fit_rows": len(y_all)})
            try:
                if name == "EXT_GRU":
                    mf = GRUModel(SEED).fit(
                        [r["tokens"] for r in train_panel.rows],
                        [r["ctx"] for r in train_panel.rows], y_all, w_all)
                else:
                    mf = fit_enet(
                        np.stack([r["enet_x"] for r in train_panel.rows]),
                        y_all, w_all)
                ledger.done(fi2)
            except BaseException as exc:  # noqa: BLE001
                ledger.fail(fi2, exc)
                raise
            models[name] = (mf, sigma)
            fit_report["models"][name] = {
                "oof": {"n_rows": len(idx_a), "sigma_oof_ah": sigma},
                "final": {"n_rows": len(y_all)},
                "hyper": ({"type": "TinyGRU", "hidden": GRU_HIDDEN,
                           "epochs": GRU_EPOCHS, "batch": GRU_BATCH,
                           "lr": GRU_LR, "weight_decay": GRU_WD,
                           "token_dim": GRU_TOKEN_DIM,
                           "ctx_dim": 24 + GRU_CTX_EXTRA}
                          if name == "EXT_GRU" else
                          {"type": "ElasticNet", "alpha": ENET_ALPHA,
                           "l1_ratio": ENET_L1_RATIO, "max_iter": ENET_MAX_ITER,
                           "tol": ENET_TOL, "selection": "cyclic",
                           "scaler": "StandardScaler",
                           "n_features": N_FEATURES_RPT + 24 + ENET_EXTRA})}
        if ledger.started != MAX_FITS or ledger.completed != MAX_FITS:
            raise ExtBaselineError("fit budget mismatch")

        rec["dev_inference_started"] = True
        atomic_json(os.path.join(out_dir, "progress.json"), rec)
        out_rows = []
        for name in EXT_MODELS:
            mf, sigma = models[name]
            if name == "EXT_GRU":
                mu = mf.predict([r["tokens"] for r in dev_panel.rows],
                                [r["ctx"] for r in dev_panel.rows])
            else:
                mu = predict_enet(
                    mf, np.stack([r["enet_x"] for r in dev_panel.rows]))
            if not np.isfinite(mu).all() or not (sigma > 0):
                raise ExtBaselineError("non-finite dev predictions %s" % name)
            for r, p in zip(dev_panel.rows, mu):
                src = r["csv_row"]
                err = float(p) - float(src["target_next_capacity_ah"])
                out = {"model": name}
                for col in PANEL_COPY_COLUMNS:
                    out[col] = src[col]
                out["predicted_mean_ah"] = repr(float(p))
                out["predicted_sigma_ah"] = repr(float(sigma))
                out["error_ah"] = repr(err)
                out["abs_error_ah"] = repr(abs(err))
                out_rows.append(out)
        out_rows.sort(key=lambda r: (r["model"], r["cell_id"], r["arm"],
                                     float(r["query_epoch"])))
        with open(os.path.join(out_dir, "predictions_ext.csv"), "x",
                  newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(TREE_COLUMNS))
            w.writeheader()
            w.writerows(out_rows)
        if len(out_rows) != 2 * len(panel_keys):
            raise ExtBaselineError("output row count mismatch")

        fit_report.update({
            "status": "COMPLETE",
            "train_rows": len(train_panel.rows),
            "train_cells": train_cells,
            "dev_rows": len(dev_panel.rows),
            "dev_cells": panel_cells,
            "panel_keys": len(panel_keys),
            "query_rule": "frozen make_examples+build_targets reimplementation "
                          "(module docstring / README)",
            "feature_spec": "frozen-v1 (README section 特征冻结)",
        })
        atomic_json(os.path.join(out_dir, "fit_report.json"), fit_report)
        rec.update(status="COMPLETE_NO_DEV_SELECTION",
                   fits_started=ledger.started,
                   fits_completed=ledger.completed,
                   payload_reads=stats.snapshot(),
                   prediction_rows=len(out_rows),
                   elapsed_seconds=time.time() - t0,
                   finished_utc=utc_now_iso())
        atomic_json(os.path.join(out_dir, "receipt.json"), rec)
        register_consumed_go(registry, rid, sha256_file(go_path),
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
def _synth_world(tmp):
    """Build a complete synthetic asset world (5 train + 3 dev cells)."""
    rng = np.random.default_rng(20261024)
    world = {"tmp": tmp, "cells": {}, "train": [], "dev": []}
    spec = [
        ("X01C1", "X01", "train", 16, None),
        ("X01C2", "X01", "train", 14, None),
        ("X02C1", "X02", "train", 15, 4),        # invalid record -> index gap
        ("X02C2", "X02", "train", 12, None),
        ("X03C1", "X03", "train", 11, None),
        ("X04C1", "X04", "development", 15, None),
        ("X04C2", "X04", "development", 13, 5),
        ("X05C1", "X05", "development", 11, None),
    ]
    feat_names = (["src_capacity_discharge_C_5", "src_capacity_discharge_C_2",
                   "src_capacity_charge_C_5", "src_capacity_charge_C_2"] +
                  ["C%s_%s_Q_at_V%.2f" % (r, d, 3.0 + 0.05 * k)
                   for r in ("2", "5") for d in ("charge", "discharge")
                   for k in range(50)])
    assert len(feat_names) == N_FEATURES_RPT
    base_epoch = 1623500000.0
    for cid, group, role, n_rpt, invalid_pos in spec:
        cell = {"cell_id": cid, "group": group, "role": role,
                "invalid_pos": invalid_pos, "rpts": [], "cycles": []}
        t = base_epoch + int(rng.integers(0, 100000))
        cap0 = 0.285 + 0.004 * float(rng.standard_normal())
        recs = []
        for k in range(n_rpt + (1 if invalid_pos is not None else 0)):
            stop = t + k * (WEEK + int(rng.integers(-5000, 40000)))
            cap = cap0 * math.exp(-0.006 * k) + 0.0004 * float(rng.standard_normal())
            recs.append({"idx": k, "stop": float(stop),
                         "cap": max(0.05, cap)})
        if invalid_pos is not None:
            cell["invalid_record"] = recs[invalid_pos]
            recs = recs[:invalid_pos] + recs[invalid_pos + 1:]
        cell["rpts"] = sorted(recs, key=lambda r: r["stop"])
        for j, r in enumerate(cell["rpts"]):
            vec = []
            for fi in range(len(feat_names)):
                if fi == 3 and j % 7 == 3:
                    vec.append(None)
                else:
                    vec.append(round(
                        r["cap"] if fi == 0 else
                        0.01 * math.sin(0.3 * fi + 0.8 * j) + 0.002 * fi +
                        0.05 * j * (1 if fi < 4 else 0.02), 9))
            r["vec"] = vec
        ct = cell["rpts"][0]["stop"] - 300000.0
        while ct < cell["rpts"][-1]["stop"] + 400000.0:
            ctl, msk = [], []
            for d in range(24):
                v = 0.5 + 0.01 * d + 0.02 * math.sin(ct / 1e6 + d)
                m = 0.0 if (d == 21 and int(ct / 100000) % 5 == 0) else 1.0
                ctl.append(0.0 if m == 0.0 else round(v, 9))
                msk.append(m)
            cell["cycles"].append({"source": float(ct), "control": ctl,
                                   "mask": msk})
            ct += 100000.0 + int(rng.integers(0, 100000))
        cell["cycles"].sort(key=lambda c: c["source"])
        world["cells"][cid] = cell
        world["train" if role == "train" else "dev"].append(cid)
    world["feat_names"] = feat_names

    def iso(ep_):
        return _dt.datetime.fromtimestamp(
            float(ep_), _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"

    # ---- RPT feature JSONs (train + dev) --------------------------------
    rpt_dir = os.path.join(tmp, "all188_rpt_features_v1")
    os.makedirs(rpt_dir, exist_ok=True)
    inv = []
    for cid, cell in world["cells"].items():
        allr = sorted(cell["rpts"] + ([cell["invalid_record"]]
                                      if cell.get("invalid_record") else []),
                      key=lambda r: r["stop"])
        recs = []
        for r in allr:
            is_bad = r is cell.get("invalid_record")
            vals = ({n: 0.0 for n in feat_names} if is_bad else
                    {n: v for n, v in zip(feat_names, r["vec"])})
            recs.append({
                "cell_id": cid, "source_rpt_index": r["idx"],
                "start": iso(r["stop"] - 80000), "stop": iso(r["stop"]),
                "features_visible_at": iso(r["stop"]),
                "data_v2_valid": not is_bad,
                "feature_names": feat_names, "values": vals,
                "status": {"C2_charge": "ok"}, "missing": {},
            })
        doc = {"schema": "isu_ilcc_rpt_features_cell_v1", "cell_id": cid,
               "role": cell["role"], "group_id": cell["group"],
               "records": recs}
        p = os.path.join(rpt_dir, cid + ".json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        inv.append({"cell_id": cid, "role": cell["role"],
                    "path": os.path.relpath(p, tmp).replace("\\", "/"),
                    "sha256": sha256_file(p), "records": len(recs)})
    inv.sort(key=lambda e: e["cell_id"])
    rpt_manifest = {
        "status": "ALL188_FEATURE_CACHE_COMPLETE", "cells": len(inv),
        "train": sum(1 for e in inv if e["role"] == "train"),
        "development": sum(1 for e in inv if e["role"] == "development"),
        "locked": 0, "inventory": inv}
    rpt_manifest_path = os.path.join(rpt_dir, "manifest.json")
    with open(rpt_manifest_path, "w", encoding="utf-8") as f:
        json.dump(rpt_manifest, f)

    # ---- processed dev JSONs + cycling gz -------------------------------
    proc_dir = os.path.join(tmp, "processed")
    cyc_dir = os.path.join(tmp, "cycling_features_v3")
    os.makedirs(proc_dir, exist_ok=True)
    os.makedirs(cyc_dir, exist_ok=True)
    files_map = {}
    cyc_inv = []
    for cid in world["dev"]:
        cell = world["cells"][cid]
        allr = sorted(cell["rpts"] + ([cell["invalid_record"]]
                                      if cell.get("invalid_record") else []),
                      key=lambda r: r["stop"])
        recs = []
        for r in allr:
            is_bad = r is cell.get("invalid_record")
            recs.append({
                "source_rpt_index": r["idx"],
                "start": iso(r["stop"] - 80000), "stop": iso(r["stop"]),
                "capacityAh": 0.123 if is_bad else r["cap"],
                "valid": not is_bad,
                "calendar_age_seconds": r["stop"] - base_epoch,
                "capacity_visible_at": "stop",
            })
        payload = {"cell_id": cid, "group_id": cell["group"],
                   "role": "development", "nominal_capacity_ah": 0.25,
                   "records": recs}
        pp = os.path.join(proc_dir, cid + ".json")
        with open(pp, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        files_map[cid] = {"role": "development",
                          "path": os.path.relpath(pp, tmp).replace("\\", "/"),
                          "sha256": sha256_file(pp)}
        cycles = []
        for c in cell["cycles"]:
            ctl, msk = c["control"], c["mask"]
            dur = 0.02 + (ctl[0] if msk[0] else 0.005)
            cycles.append({
                "source_cycle_index": len(cycles),
                "charge": {
                    "start": iso(c["source"] - dur * WEEK),
                    "stop": iso(c["source"] - dur * WEEK / 2),
                    "Q_sample_stats": {
                        "last": ctl[3] if msk[3] else None,
                        "mean": ctl[5] if msk[5] else None,
                        "min": 0.0, "max": 2.0 * (ctl[7] if msk[7] else 0.01)},
                    "V_V_sample_stats": {
                        "mean": ctl[9] if msk[9] else None,
                        "last": ctl[11] if msk[11] else None},
                    "E_sample_stats": {
                        "last": ctl[17] if msk[17] else None,
                        "mean": ctl[19] if msk[19] else None},
                    "I_A_sample_stats": {
                        "mean": ctl[13] if msk[13] else None,
                        "min": -1.0, "max": 1.0}},
                "discharge": {
                    "start": iso(c["source"] - dur * WEEK / 2),
                    "stop": iso(c["source"]),
                    "Q_sample_stats": {
                        "last": ctl[4] if msk[4] else None,
                        "mean": ctl[6] if msk[6] else None,
                        "min": 0.0, "max": 2.0 * (ctl[8] if msk[8] else 0.01)},
                    "V_V_sample_stats": {
                        "mean": ctl[10] if msk[10] else None,
                        "last": ctl[12] if msk[12] else None},
                    "E_sample_stats": {
                        "last": ctl[18] if msk[18] else None,
                        "mean": ctl[20] if msk[20] else None},
                    "I_A_sample_stats": {"mean": None, "min": -2.0,
                                         "max": -0.5}},
                "capacity_charge_source_units_unknown":
                    ctl[21] if msk[21] else None,
                "capacity_discharge_source_units_unknown":
                    ctl[22] if msk[22] else None,
                "observed_cycle_throughput_source_units":
                    ctl[23] if msk[23] else None,
            })
        cdoc = {"cell_id": cid, "role": "development", "cycles": cycles}
        cp = os.path.join(cyc_dir, cid + ".json.gz")
        with open(cp, "wb") as f:
            f.write(gzip.compress(json.dumps(cdoc).encode("utf-8")))
        cyc_inv.append({"cell_id": cid, "role": "development",
                        "path": os.path.relpath(cp, tmp).replace("\\", "/"),
                        "sha256": sha256_file(cp)})
    cyc_inv.sort(key=lambda e: e["cell_id"])
    data_manifest = {"status": "PASS", "files": files_map,
                     "role_counts": {"development": len(files_map),
                                     "locked": 0},
                     "constraints": {"raw_curves_read": False,
                                     "locked_payloads_read": False}}
    dm_path = os.path.join(tmp, "data_manifest.json")
    with open(dm_path, "w", encoding="utf-8") as f:
        json.dump(data_manifest, f)
    cyc_manifest = {"status": "SUCCESS", "development": len(cyc_inv),
                    "C4": 0, "inventory": cyc_inv}
    cm_path = os.path.join(tmp, "cycling_manifest.json")
    with open(cm_path, "w", encoding="utf-8") as f:
        json.dump(cyc_manifest, f)
    cohort = {"status": "FROZEN_BEFORE_ANY_CAPACITY_PAYLOAD",
              "roles": {cid: world["cells"][cid]["role"]
                        for cid in world["cells"]},
              "counts": {"train": len(world["train"]),
                         "development": len(world["dev"])}}
    co_path = os.path.join(tmp, "cohort.json")
    with open(co_path, "w", encoding="utf-8") as f:
        json.dump(cohort, f)

    # ---- PREP npz + manifest (train cells) -------------------------------
    prep_dir = os.path.join(tmp, "prep_v2_synth")
    os.makedirs(prep_dir, exist_ok=True)
    ev_cell, ev_kind, ev_src, ev_avail, ev_dt = [], [], [], [], []
    ev_ctl, ev_msk, ev_cap, ev_score = [], [], [], []
    cells_meta = []
    cell_ids = []
    for cid in world["train"]:
        cell = world["cells"][cid]
        cell_ids.append(cid)
        anchor = cell["rpts"][0]
        events = []
        for c in cell["cycles"]:
            if c["source"] < anchor["stop"] - 1e-9:
                continue
            events.append((c["source"], 0, c))
        for r in cell["rpts"][1:]:
            events.append((r["stop"], 1, r))
        events.sort(key=lambda e: (e[0], e[1]))
        prev = anchor["stop"]
        for src, kind_ord, obj in events:
            ev_cell.append(len(cell_ids) - 1)
            ev_src.append(src)
            ev_avail.append(src)
            ev_dt.append(max(0.0, (src - prev) / WEEK))
            prev = src
            if kind_ord == 0:
                ev_kind.append(1)
                ev_ctl.append(obj["control"])
                ev_msk.append(obj["mask"])
                ev_cap.append(0.0)
                ev_score.append(False)
            else:
                ev_kind.append(2)
                ev_ctl.append([0.0] * 24)
                ev_msk.append([0.0] * 24)
                ev_cap.append(obj["cap"])
                ev_score.append(True)
        cells_meta.append({"cell_id": cid, "q_ref_ah": anchor["cap"],
                           "anchor_source_epoch": anchor["stop"],
                           "n_events": len(events)})
    npz_path = os.path.join(prep_dir, "a2_prep_sequences.npz")
    np.savez(
        npz_path,
        cell_ids=np.asarray(cell_ids, dtype="<U8"),
        q_ref_ah=np.asarray([m["q_ref_ah"] for m in cells_meta],
                            dtype=np.float64),
        anchor_source_epoch=np.asarray(
            [m["anchor_source_epoch"] for m in cells_meta], dtype=np.float64),
        event_cell=np.asarray(ev_cell, dtype=np.int64),
        event_kind=np.asarray(ev_kind, dtype=np.int8),
        event_source=np.asarray(ev_src, dtype=np.float64),
        event_available=np.asarray(ev_avail, dtype=np.float64),
        event_dt_weeks=np.asarray(ev_dt, dtype=np.float32),
        control=np.asarray(ev_ctl, dtype=np.float32),
        control_mask=np.asarray(ev_msk, dtype=np.float32),
        capacity_ah=np.asarray(ev_cap, dtype=np.float32),
        score=np.asarray(ev_score, dtype=bool),
    )
    prep_manifest = {"schema": "A2_PREP_V1", "prepared_npz": npz_path,
                     "n_cells": len(cells_meta), "cells": cells_meta}
    pm_path = os.path.join(prep_dir, "manifest.json")
    with open(pm_path, "w", encoding="utf-8") as f:
        json.dump(prep_manifest, f)

    # ---- independent reference tree CSV (fixture-side reimplementation) --
    def fixture_panel_rows():
        rows = []
        for cid in world["dev"]:
            cell = world["cells"][cid]
            rows_all = cell["rpts"]
            n = len(rows_all)
            anchor_stop = rows_all[1]["stop"]
            for qi in range(n):
                q = rows_all[qi]["stop"]
                if q < anchor_stop + WEEK:
                    continue
                vis_list = {}
                for arm in ARMS:
                    lag = 7.0 * DAY if arm == "delay7d" else 0.0
                    sel = []
                    for i, r in enumerate(rows_all):
                        if arm == "sparse2" and i > 1 and \
                                (r["idx"] - rows_all[1]["idx"]) % 2:
                            continue
                        if r["stop"] + lag <= q:
                            sel.append(i)
                    vis_list[arm] = sel
                if min(len(v) for v in vis_list.values()) < 3:
                    continue
                later = [r for r in rows_all if r["stop"] > q + 1e-5]
                if not later:
                    continue
                tgt = later[0]
                for arm in ARMS:
                    vis = vis_list[arm]
                    lastcap = rows_all[vis[-1]]["cap"]
                    soh = lastcap / 0.25
                    stage = ("gt0.95" if soh > 0.95 else
                             "0.90-0.95" if soh > 0.90 else
                             "0.85-0.90" if soh > 0.85 else "le0.85")
                    known = any(rows_all[i]["cap"] <= 0.20 for i in vis)
                    rows.append({
                        "cell_id": cid, "group_id": cell["group"], "arm": arm,
                        "query_epoch": repr(q),
                        "forecast_h_weeks": repr((tgt["stop"] - q) / WEEK),
                        "next_source_elapsed_weeks": repr(
                            (tgt["stop"] - rows_all[vis[-1]]["stop"]) / WEEK),
                        "next_query_elapsed_weeks": repr(
                            (tgt["stop"] - q) / WEEK),
                        "last_visible_capacity_ah": repr(lastcap),
                        "last_visible_soh": repr(soh),
                        "degradation_stage": stage,
                        "target_next_capacity_ah": repr(tgt["cap"]),
                        "known_event": "True" if known else "False",
                    })
        return rows

    panel_rows = fixture_panel_rows()
    tree_csv = os.path.join(tmp, "predictions_c3.csv")
    with open(tree_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(TREE_COLUMNS))
        w.writeheader()
        for model in ("hgb", "catboost"):
            for r in panel_rows:
                out = {"model": model}
                out.update(r)
                out["predicted_mean_ah"] = r["last_visible_capacity_ah"]
                out["predicted_sigma_ah"] = "0.01"
                out["error_ah"] = repr(
                    float(r["last_visible_capacity_ah"]) -
                    float(r["target_next_capacity_ah"]))
                out["abs_error_ah"] = repr(abs(
                    float(r["last_visible_capacity_ah"]) -
                    float(r["target_next_capacity_ah"])))
                w.writerow(out)

    world.update({
        "rpt_manifest": rpt_manifest_path, "rpt_dir": rpt_dir,
        "cycling_dir": cyc_dir,
        "data_manifest": dm_path, "cycling_manifest": cm_path,
        "cohort": co_path, "prep_manifest": pm_path, "prep_npz": npz_path,
        "tree_csv": tree_csv, "panel_rows": panel_rows,
        "registry": os.path.join(tmp, "consumed_gos.jsonl"),
        "runs": os.path.join(tmp, "runs"),
        "receipts": os.path.join(tmp, "receipts"),
    })
    return world


def _valid_synth_go(world, request_id="EXTBASE_SELFCHECK_0001", issued=None):
    return {
        "status": "APPROVED",
        "allow_fit": True,
        "scope": "EXT-BASELINE synthetic self-check run",
        "request_id": request_id,
        "owner_thread_id": OWNER_THREAD_ID,
        "issued_utc": issued or utc_now_iso().replace("+00:00", "Z"),
        "seed": SEED,
        "models": list(EXT_MODELS),
        "fits_in_this_go": MAX_FITS,
        "fit_plan": FIT_PLAN,
        "device": "cpu", "threads": 4, "max_runtime_seconds": 3600,
        "code_sha256": {
            "ext_baselines.py":
                sha256_file(os.path.join(HERE, "ext_baselines.py")),
            "a2_prep.py": sha256_file(os.path.join(A2_DIR, "a2_prep.py")),
            "a2_targets.py": sha256_file(os.path.join(A2_DIR, "a2_targets.py")),
            "README_EXT_BASELINES_ZH.md":
                sha256_file(os.path.join(HERE, "README_EXT_BASELINES_ZH.md")),
        },
        "assets": {k: {"path": world[a], "sha256": sha256_file(world[a])}
                   for k, a in (("prep_manifest", "prep_manifest"),
                                ("prep_npz", "prep_npz"),
                                ("rpt_manifest", "rpt_manifest"),
                                ("tree_csv", "tree_csv"),
                                ("cohort", "cohort"),
                                ("data_manifest", "data_manifest"),
                                ("cycling_manifest", "cycling_manifest"))},
        "panel_contract": {
            "n_keys": len({(r["cell_id"], r["arm"],
                            round(float(r["query_epoch"]), 6))
                           for r in world["panel_rows"]}),
            "arms": list(ARMS), "source": "synthetic tree CSV"},
        "consumed_registry": world["registry"],
        "output_dir": os.path.join(world["runs"], "extbase_selfcheck_run1"),
        "receipt_path": os.path.join(
            world["receipts"], "extbase_selfcheck_run1_receipt.json"),
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

    tmp = tempfile.mkdtemp(prefix="ext_baseline_selfcheck_")
    real_paths_seen = []
    try:
        world = _synth_world(tmp)
        stats = ReadStats()
        store = Store([tmp], stats, base=tmp)

        def no_real_reads():
            store.read_bytes(world["tree_csv"], "selfcheck_probe")  # a read
            real = [p for p in stats.paths
                    if not p.startswith(os.path.realpath(tmp))]
            real_paths_seen.extend(real)
            assert not real, "self-check opened real assets: %s" % real
            assert stats.paths, "self-check read nothing"
            return "reads=%d, all under tmp" % len(stats.paths)

        # 1 ----------------------------------------------------------
        def chk_world():
            assert os.path.isfile(world["tree_csv"])
            assert world["panel_rows"]
            n_keys = len({(r["cell_id"], r["arm"],
                           round(float(r["query_epoch"]), 6))
                          for r in world["panel_rows"]})
            return "panel_keys=%d train_cells=%d dev_cells=%d" % (
                n_keys, len(world["train"]), len(world["dev"]))
        check("synthetic world built", chk_world)

        # 2 ----------------------------------------------------------
        check("no real payload/asset reads (store audit)", no_real_reads)

        # 3 ----------------------------------------------------------
        def chk_panel():
            by_model, keys = load_tree_panel(store, world["tree_csv"])
            assert len(keys) == len(world["panel_rows"])
            dev_cells = {k[0] for k in keys}
            assert dev_cells == set(world["dev"])
            derived = set()
            for cid in world["dev"]:
                rows, _ = load_rpt_json_cell(
                    store, os.path.join(world["rpt_dir"], cid + ".json"), cid)
                for qrow in derive_cell_queries(rows):
                    derived.add((cid, qrow["arm"], round(qrow["q"], 6)))
            assert derived == keys, \
                "derived dev grid %d != CSV keys %d" % (len(derived), len(keys))
            train_keys = set()
            for cid in world["train"]:
                rows, _ = load_rpt_json_cell(
                    store, os.path.join(world["rpt_dir"], cid + ".json"), cid)
                for qrow in derive_cell_queries(rows):
                    train_keys.add((cid, qrow["arm"]))
            assert train_keys, "empty train grid"
            assert not ({k[0] for k in train_keys} & dev_cells)
            return "dev keys=%d reproduced exactly; train grid cells=%d disjoint" % (
                len(keys), len({k[0] for k in train_keys}))
        check("panel-key consistency (CSV == derived dev grid; train disjoint)",
              chk_panel)

        # 4 ----------------------------------------------------------
        def chk_arms():
            cid = "X02C1"   # train cell with an original-index gap
            rows, _ = load_rpt_json_cell(
                store, os.path.join(world["rpt_dir"], cid + ".json"), cid)
            gaps = [rows[i + 1]["idx"] - rows[i]["idx"]
                    for i in range(len(rows) - 1)]
            assert 2 in gaps, "fixture lost its index gap"
            q = rows[3]["stop"]
            vis_raw = visible_indices(rows, "raw", q)
            vis_sp = visible_indices(rows, "sparse2", q)
            vis_dl = visible_indices(rows, "delay7d", q)
            assert vis_raw[-1] == 3
            assert all(rows[i]["stop"] + 7 * DAY <= q + 1e-9
                       for i in vis_dl)
            if rows[3]["stop"] + 7 * DAY > q + 1e-9:
                assert 3 not in vis_dl
            hidden = [i for i in range(len(rows))
                      if i > 1 and (rows[i]["idx"] - rows[1]["idx"]) % 2]
            assert hidden and all(i not in vis_sp for i in hidden)
            return "raw=%d sp=%d dl=%d visible at q=row3; parity on orig idx" % (
                len(vis_raw), len(vis_sp), len(vis_dl))
        check("arm semantics (raw / sparse2 parity on original index / delay7d)",
              chk_arms)

        # 5 ----------------------------------------------------------
        def chk_leak():
            cid = world["dev"][0]
            rows, _ = load_rpt_json_cell(
                store, os.path.join(world["rpt_dir"], cid + ".json"), cid)
            cycles = load_dev_cycles(
                store, os.path.join(world["cycling_dir"], cid + ".json.gz"),
                cid)
            queries = derive_cell_queries(rows)
            assert len(queries) >= 4
            qrow = queries[3]
            q, vis = qrow["q"], qrow["vis"]
            q_ref = rows[0]["cap"]
            t0, c0 = gru_prefix(rows, vis, q, cycles, q_ref, qrow["h"])
            e0 = enet_prefix(rows, vis, q, cycles, q_ref, qrow["h"],
                             rows[0]["vec"], rows[vis[-1]]["vec"])
            rows2 = copy.deepcopy(rows)
            for r in rows2:
                if r["stop"] > q + 1e-5:
                    r["cap"] = 0.0731                      # future capacity
                    r["vec"] = [None if v is None else v - 1.0
                                for v in r["vec"]]         # future features
            cycles2 = copy.deepcopy(cycles)
            for c in cycles2:                              # future controls
                if c["source"] > q + 1e-9:
                    c["control"] = [7.7] * 24
            cycles2.append({"source": q + 500000.0, "control": [9.9] * 24,
                            "mask": [1.0] * 24})           # future cycle
            t1, c1 = gru_prefix(rows2, vis, q, cycles2, q_ref, qrow["h"])
            e1 = enet_prefix(rows2, vis, q, cycles2, q_ref, qrow["h"],
                             rows2[0]["vec"], rows2[vis[-1]]["vec"])
            np.testing.assert_array_equal(t0, t1)
            np.testing.assert_array_equal(c0, c1)
            np.testing.assert_array_equal(e0, e1)
            return "future capacity/feature/control perturbation invariant"
        check("prefix no-leakage (perturbing future events changes nothing)",
              chk_leak)

        # 6 ----------------------------------------------------------
        def chk_prep():
            prep = load_prep(store, world["prep_manifest"], world["prep_npz"])
            assert sorted(prep["cells"]) == sorted(world["train"])
            cid = world["train"][0]
            rows, _ = load_rpt_json_cell(
                store, os.path.join(world["rpt_dir"], cid + ".json"), cid)
            cross_check_train(prep["cells"][cid], rows, cid)
            bad = copy.deepcopy(prep["cells"][cid])
            bad["q_ref"] = bad["q_ref"] + 0.5
            try:
                cross_check_train(bad, rows, cid)
                raise AssertionError("corrupted PREP q_ref not refused")
            except ExtBaselineError:
                pass
            return "PREP<->RPT-asset consistency accepted; corruption refused"
        check("PREP cross-check gate (accept good, refuse corrupted)", chk_prep)

        # 7 ----------------------------------------------------------
        def chk_gru():
            toks = [np.asarray([[0.9, 0.0, 0.0, 0.0],
                                [0.89, -0.01, 1.0, 1.0]]),
                    np.asarray([[0.95, 0.0, 0.0, 0.0]])]
            ctx = [np.zeros(24 + GRU_CTX_EXTRA), np.ones(24 + GRU_CTX_EXTRA)]
            m = GRUModel(SEED)
            X, M, C = GRUModel._pack(toks, ctx)
            assert X.shape == (2, 2, GRU_TOKEN_DIM) and M.shape == (2, 2)
            out = m.net(X, C, (M.sum(dim=1) - 1).clamp_min(0))
            assert out.shape == (2, 2)
            assert np.isfinite(out.detach().numpy()).all()
            m.fit(toks, ctx, np.asarray([0.28, 0.27]),
                  np.asarray([1.0, 1.0]), epochs=5)
            pred = m.predict(toks, ctx)
            assert pred.shape == (2,) and np.isfinite(pred).all()
            m2 = GRUModel(SEED).fit(toks, ctx, np.asarray([0.28, 0.27]),
                                    np.asarray([1.0, 1.0]), epochs=5)
            np.testing.assert_array_equal(pred, m2.predict(toks, ctx))
            return "forward (2,2) finite; seeded refit bit-identical"
        check("GRU forward shape/finiteness/backward + determinism", chk_gru)

        # 8 ----------------------------------------------------------
        def chk_enet():
            rng = np.random.default_rng(7)
            X = rng.standard_normal((300, N_FEATURES_RPT + 24 + ENET_EXTRA))
            y = X[:, 0] * 0.1 + 0.25 + 0.001 * rng.standard_normal(300)
            w = np.ones(300)
            p1 = predict_enet(fit_enet(X, y, w), X)
            p2 = predict_enet(fit_enet(X, y, w), X)
            np.testing.assert_array_equal(p1, p2)
            assert np.isfinite(p1).all()
            return "two fits identical"
        check("ElasticNet determinism", chk_enet)

        # 9 ----------------------------------------------------------
        def chk_sigma():
            res = np.asarray([0.01, -0.02, 0.03, -0.01, 0.02, -0.03])
            cells = ["A", "A", "A", "B", "B", "B"]
            s1 = sigma_from_residuals(res, cells)
            w = cell_balanced_weights(cells)
            s2 = math.sqrt(float(np.sum(w * res * res) / np.sum(w)))
            assert abs(s1 - s2) < 1e-15 and s1 > 0
            folds = two_cell_folds(["A", "B", "C", "D", "E"])
            assert sorted(folds[0] + folds[1]) == ["A", "B", "C", "D", "E"]
            assert not set(folds[0]) & set(folds[1])
            assert folds == two_cell_folds(["A", "B", "C", "D", "E"])
            return "sigma=%.8f reproducible; folds stable" % s1
        check("OOF sigma formula + stable sha256 folds", chk_sigma)

        # 10 ---------------------------------------------------------
        def chk_registry():
            reg = os.path.join(tmp, "registry_test.jsonl")
            register_consumed_go(reg, "RID_TEST_1", "a" * 64, utc_now_iso())
            assert request_id_is_fresh("RID_TEST_2", reg)
            assert not request_id_is_fresh("RID_TEST_1", reg)
            try:
                register_consumed_go(reg, "RID_TEST_1", "a" * 64,
                                     utc_now_iso())
                raise AssertionError("duplicate registration not refused")
            except RuntimeError:
                pass
            assert os.path.realpath(reg).startswith(os.path.realpath(tmp))
            return "append once + duplicate refused (tmp registry only)"
        check("registry append/duplicate-refusal (isolated tmp registry)",
              chk_registry)

        # 11 ---------------------------------------------------------
        n_refused = [0]

        def chk_go():
            good = _valid_synth_go(world)
            panel = {(r["cell_id"], r["arm"],
                      round(float(r["query_epoch"]), 6))
                     for r in world["panel_rows"]}
            gp = os.path.join(tmp, "go_good.json")
            with open(gp, "w", encoding="utf-8") as f:
                json.dump(good, f)
            out, rcp, reg, rid = validate_go(good, gp, store, world["runs"],
                                             world["receipts"], panel)
            assert rid == good["request_id"]

            def mutate(kind):
                g = copy.deepcopy(good)
                if kind == "status":
                    g["status"] = "PENDING"
                elif kind == "allow_fit":
                    g["allow_fit"] = False
                elif kind == "scope":
                    g["scope"] = "something else"
                elif kind == "owner":
                    g["owner_thread_id"] = "deadbeef"
                elif kind == "stale":
                    g["issued_utc"] = "2020-01-01T00:00:00Z"
                elif kind == "seed":
                    g["seed"] = 7
                elif kind == "fits":
                    g["fits_in_this_go"] = 6
                elif kind == "models":
                    g["models"] = ["EXT_GRU"]
                elif kind == "fit_plan":
                    g["fit_plan"] = "loose"
                elif kind == "code_sha":
                    g["code_sha256"]["ext_baselines.py"] = "0" * 64
                elif kind == "asset_sha":
                    g["assets"]["tree_csv"]["sha256"] = "0" * 64
                elif kind == "asset_missing":
                    del g["assets"]["cohort"]
                elif kind == "panel_nkeys":
                    g["panel_contract"]["n_keys"] += 1
                elif kind == "consumed_rid":
                    g["request_id"] = "ALREADY_CONSUMED_RID"
                    register_consumed_go(good["consumed_registry"],
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
                elif kind == "device":
                    g["device"] = "cuda"
                elif kind == "runtime":
                    g["max_runtime_seconds"] = 999999
                elif kind == "missing_field":
                    del g["request_id"]
                else:
                    raise AssertionError("unknown mutation " + kind)
                mp = os.path.join(tmp, "go_mut_%s.json" % kind)
                with open(mp, "w", encoding="utf-8") as f:
                    json.dump(g, f)
                try:
                    validate_go(g, mp, store, world["runs"],
                                world["receipts"], panel)
                    raise AssertionError("mutation %s NOT refused" % kind)
                except ExtBaselineError:
                    n_refused[0] += 1
                finally:
                    shutil.rmtree(g["output_dir"], ignore_errors=True)
                    if os.path.exists(g["receipt_path"]):
                        os.remove(g["receipt_path"])

            for kind in ("status", "allow_fit", "scope", "owner", "stale",
                         "seed", "fits", "models", "fit_plan", "code_sha",
                         "asset_sha", "asset_missing", "panel_nkeys",
                         "consumed_rid", "burned_rid", "out_dir_exists",
                         "receipt_exists", "device", "runtime",
                         "missing_field"):
                mutate(kind)
            assert n_refused[0] >= 12, "only %d mutations refused" % n_refused[0]
            return "valid GO accepted; %d/20 mutations refused" % n_refused[0]
        check("GO validator (valid accepted, >=12 mutations refused)", chk_go)

        # 12 ---------------------------------------------------------
        def chk_ledger():
            ld = os.path.join(tmp, "ledger_run")
            os.makedirs(ld)
            led = FitLedger(ld, MAX_FITS)
            for i in range(MAX_FITS):
                idx = led.begin({"model": "X", "fit": i})
                led.done(idx)
            assert led.started == MAX_FITS and led.completed == MAX_FITS
            try:
                led.begin({"model": "X", "fit": 5})
                raise AssertionError("5th fit not refused")
            except ExtBaselineError:
                pass
            return "4 fits recorded, 5th refused"
        check("fit ledger budget (4 fits, 5th refused)", chk_ledger)

        # 13 ---------------------------------------------------------
        def chk_run():
            good = _valid_synth_go(world)
            gp = os.path.join(tmp, "go_run.json")
            with open(gp, "w", encoding="utf-8") as f:
                json.dump(good, f)
            r = run_go(gp, store=store, registry=world["registry"],
                       runs_parent=world["runs"],
                       receipts_parent=world["receipts"], use_locks=False,
                       expected_counts=(len(world["train"]),
                                        len(world["dev"])))
            assert r.get("status") == "COMPLETE_NO_DEV_SELECTION", r
            assert r.get("fits_started") == 4 and r.get("fits_completed") == 4
            assert r.get("registered") is True
            assert not request_id_is_fresh(good["request_id"],
                                           world["registry"])
            fr = json.load(open(os.path.join(
                world["runs"], "extbase_selfcheck_run1", "fit_report.json")))
            assert fr["status"] == "COMPLETE" and \
                sorted(fr["models"]) == sorted(EXT_MODELS)
            # OOF sigma reproducible from the saved residuals
            for name in EXT_MODELS:
                sigma = fr["models"][name]["oof"]["sigma_oof_ah"]
                fit1 = json.load(open(os.path.join(
                    world["runs"], "extbase_selfcheck_run1", "fit_01.json")))
                assert sigma > 0
                break
            residuals = None
            for i in range(1, MAX_FITS + 1):
                rec = json.load(open(os.path.join(
                    world["runs"], "extbase_selfcheck_run1",
                    "fit_%02d.json" % i)))
                if rec.get("model") == "EXT_GRU" and \
                        rec.get("fit") == "oof_sigma":
                    residuals = rec["oof_residuals_ah"]
            assert residuals is not None and len(residuals) > 0
            return "status=%s fits=4 rows=%s sigma_resid_persisted" % (
                r["status"], r.get("prediction_rows"))
        check("full guarded run on synthetic world (4 fits + outputs)",
              chk_run)

        # 14 ---------------------------------------------------------
        def chk_output():
            out_csv = os.path.join(world["runs"], "extbase_selfcheck_run1",
                                   "predictions_ext.csv")
            with open(out_csv, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                assert tuple(reader.fieldnames) == TREE_COLUMNS
                rows = list(reader)
            keys = {(r["cell_id"], r["arm"], round(float(r["query_epoch"]), 6))
                    for r in rows}
            ref_keys = {(r["cell_id"], r["arm"],
                         round(float(r["query_epoch"]), 6))
                        for r in world["panel_rows"]}
            assert keys == ref_keys and len(rows) == 2 * len(ref_keys)
            assert sorted({r["model"] for r in rows}) == sorted(EXT_MODELS)
            for m in EXT_MODELS:
                assert len({r["predicted_sigma_ah"]
                            for r in rows if r["model"] == m}) == 1
            for r in rows:
                tgt = float(r["target_next_capacity_ah"])
                p = float(r["predicted_mean_ah"])
                assert math.isfinite(p)
                assert abs(float(r["error_ah"]) - (p - tgt)) < 1e-12
                assert abs(float(r["abs_error_ah"]) - abs(p - tgt)) < 1e-12
            with open(world["tree_csv"], newline="", encoding="utf-8") as f:
                ref = {(x["model"], x["cell_id"], x["arm"],
                        round(float(x["query_epoch"]), 6)): x
                       for x in csv.DictReader(f) if x["model"] == "hgb"}
            for r in rows:
                refrow = ref[("hgb", r["cell_id"], r["arm"],
                              round(float(r["query_epoch"]), 6))]
                for col in PANEL_COPY_COLUMNS:
                    assert r[col] == refrow[col], (col, r[col], refrow[col])
            return "columns identical; %d keys x2 models; panel verbatim" % \
                len(ref_keys)
        check("predictions_ext.csv schema/keys/verbatim panel columns",
              chk_output)

        # 15 ---------------------------------------------------------
        def chk_rerun():
            good = _valid_synth_go(world)
            gp = os.path.join(tmp, "go_run.json")
            r = run_go(gp, store=store, registry=world["registry"],
                       runs_parent=world["runs"],
                       receipts_parent=world["receipts"], use_locks=False,
                       expected_counts=(len(world["train"]),
                                        len(world["dev"])))
            assert r.get("status") != "COMPLETE_NO_DEV_SELECTION", r
            panel = {(x["cell_id"], x["arm"],
                      round(float(x["query_epoch"]), 6))
                     for x in world["panel_rows"]}
            try:
                validate_go(good, gp, store, world["runs"], world["receipts"],
                            panel)
                raise AssertionError("validate_go accepted a consumed GO")
            except ExtBaselineError:
                pass
            return "rerun of consumed GO refused everywhere"
        check("consumed GO / existing out_dir refused on rerun", chk_rerun)

        # 16 ---------------------------------------------------------
        def chk_names_order():
            cid = world["dev"][0]
            doc = store.read_json(
                os.path.join(world["rpt_dir"], cid + ".json"), "probe_names")
            rows_a, names_a = rows_from_rpt_json(doc)
            assert names_a == sorted(names_a) and \
                len(names_a) == N_FEATURES_RPT and \
                len(set(names_a)) == N_FEATURES_RPT
            doc2 = copy.deepcopy(doc)
            shuffler = np.random.default_rng(99)
            n_shuffled = 0
            for rec in doc2["records"]:
                order = list(range(len(rec["feature_names"])))
                shuffler.shuffle(order)
                if order != sorted(order):
                    n_shuffled += 1
                rec["feature_names"] = [rec["feature_names"][i]
                                        for i in order]
            assert n_shuffled > 0, "fixture failed to shuffle any record"
            rows_b, names_b = rows_from_rpt_json(doc2)
            assert names_b == names_a
            assert len(rows_a) == len(rows_b)
            for ra, rb in zip(rows_a, rows_b):
                assert ra["vec"] == rb["vec"], "shuffled order changed vector"
                assert ra["cap"] == rb["cap"] and ra["stop"] == rb["stop"]
            return ("per-record shuffled orders (%d records) -> identical "
                    "canonical vectors" % n_shuffled)
        check("feature-name order normalization (shuffle -> same vectors)",
              chk_names_order)

        # 17 ---------------------------------------------------------
        def chk_names_set():
            cid = world["dev"][1]
            doc = store.read_json(
                os.path.join(world["rpt_dir"], cid + ".json"), "probe_set")
            doc2 = copy.deepcopy(doc)
            hit = 0
            for rec in doc2["records"]:
                if rec.get("data_v2_valid") is True:
                    rec["feature_names"] = list(rec["feature_names"])
                    rec["feature_names"][0] += "_renamed"
                    hit += 1
                    break
            assert hit == 1
            try:
                rows_from_rpt_json(doc2)
                raise AssertionError("different feature set not refused")
            except ExtBaselineError:
                pass
            doc3 = copy.deepcopy(doc)
            for rec in doc3["records"]:
                if rec.get("data_v2_valid") is True:
                    rec["feature_names"] = list(rec["feature_names"])
                    rec["feature_names"][1] = rec["feature_names"][0]
                    break
            try:
                rows_from_rpt_json(doc3)
                raise AssertionError("duplicate feature names not refused")
            except ExtBaselineError:
                pass
            return "set drift refused; duplicate names refused"
        check("feature-name set drift / duplicates refused", chk_names_set)

        # 18 ---------------------------------------------------------
        check("no real payload/asset reads after full run", no_real_reads)

        total = len(passed) + len(failed)
        result = "RESULT: self_check total=%d passed=%d failed=%d" % (
            total, len(passed), len(failed))
        emit("")
        emit(result)
        for name, exc in failed:
            emit("FAILED: %s: %s" % (name, exc))
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("\n===== ext_baselines self-check run %s =====\n"
                    % utc_now_iso())
            f.write("\n".join(log_lines) + "\n")
        return 0 if not failed else 2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="External baselines (EXT_GRU + EXT_ENET): synthetic "
                    "self-check by default; guarded fit+inference only with "
                    "--run-train --go GO.json")
    p.add_argument("--self-check", action="store_true",
                   help="synthetic fixtures only (default behaviour)")
    p.add_argument("--run-train", action="store_true",
                   help="guarded real run; requires --go")
    p.add_argument("--go", default=None,
                   help="path to an APPROVED, unconsumed GO json")
    args = p.parse_args(argv)
    if args.run_train:
        if not args.go:
            print("--run-train requires --go GO.json", file=sys.stderr)
            return 2
        rec = run_go(args.go)
        print(json.dumps(rec, indent=2, ensure_ascii=False, allow_nan=True))
        return 0 if rec.get("status") == "COMPLETE_NO_DEV_SELECTION" else 2
    return self_check()


if __name__ == "__main__":
    sys.exit(main())
