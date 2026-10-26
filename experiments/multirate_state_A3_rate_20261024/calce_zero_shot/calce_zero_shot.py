#!/usr/bin/env python3
"""CALCE CS2_35 zero-shot capacity-conditioned inference (A4) -- synthetic
self-check only by default; real evaluation is GO-gated.

ESTIMAND (frozen; declared here, in every GO, and in metrics.json)
    Given the prefix of capacity observations that have ARRIVED by calendar
    time q, predict the capacity of the NEXT observation that arrives
    (next-arrived-observation capacity).  This is exactly the ISU
    "nextcapacity" / A3 next-jump RPT target semantics.  NO RUL or event-time
    prediction is performed or reported.  The CALCE endpoint_labels.json
    freeze RUL_labels_allowed=false remains in force and is respected: the
    first observed 0.88 Ah crossing (2010-12-16T07:23:52) is evaluation
    CONTEXT (pre/post-event bucketing) only, never a label.  The A4 GO
    explicitly overrides endpoint_labels.models_fit_or_infer_allowed=false
    to "capacity-conditioned inference only, zero fits": the override and its
    reason are recorded in every GO under "estimand".

WHAT RUNS (all zero-shot; 0 fits, 0 gradient steps, 0 C4)
  * A3 full-arm checkpoints trained on ISU ILCC (seeds 42/43/44), loaded
    with a3_infer._load_arm_model_a3 discipline (sha-pinned, float32
    checkpoint -> float64 filter) and applied through a3_infer.AsOfWalkerA3
    UNCHANGED.  The 24-dim per-observation control is built from the CALCE
    records cache through an explicit ISU->CALCE mapping (CONTROL_MAPPING;
    energy/Wh dims 17-20 do not exist in the cache -> mask=0).  The mu_net
    consumes ISU-standardized CALCE controls: out-of-support inputs (1.1 Ah
    LCO scale vs 0.25 Ah ISU cells) are expected and REPORTED, not corrected.
  * Cross-dataset naive references: hold_last (last visible capacity) and
    past_slope (linear extrapolation from the last two visible observations
    to the observed next-observation stop time; the frozen ISU
    trajectory_strong_baselines run_baselines.py semantic).
  * F0_hgb (ISU-trained HistGradientBoostingRegressor) is NOT RUN: the
    strong-baselines run persisted no model artifact (only CSVs), so the tree
    cannot be loaded zero-shot, and re-fitting it here would break the 0-fit
    claim.  Its unavailability is reported, per the A4 delegation.

PANEL (frozen design; documented in README_CALCE_ZH_ZH.md)
  * capacity observations = capacity_series.csv rows with
    status==VALID_SAMPLED_CC_DISCHARGE and empty duplicate_of (854 unique);
    source = arrival = discharge_end_datetime parsed as timezone-naive UTC
    (source timezone unknown -- disclosed everywhere).
  * anchor = first valid observation (2010-08-16T17:22:57, 1.138460076 Ah);
    q_ref = anchor capacity (ISU construction).
  * arms raw / sparse2 / delay7d via a2_infer._b2_arm_records UNCHANGED with
    anchor_index=0: sparse2 keeps (index-0)%2==0, delay7d shifts arrival by
    +7 days (simulated policy; CALCE has no measured reporting delay).
  * queries at every observation stop with: q >= anchor_stop + 1 week,
    >= 3 visible arrivals, dedupe by (arm, anchor index), target = next
    observation in the FULL record (strictly after q), targetless queries
    dropped.  DELIBERATE DEVIATION from the ISU grid: the ISU
    "visible_threshold" skip is REMOVED so that post-event queries exist
    (post-crossing observations; pre/post-event buckets are reported).  The
    ISU models were only ever queried pre-threshold on ISU, so post-event
    queries are extra out-of-support territory and are labelled per row.
  * walker sequences per arm reuse a2_prep.cell_sequence UNCHANGED: cycle
    events (24-dim control) for ALL observations (dense control stream, ISU
    structure), RPT events restricted to the arm's retained observations.
    For CALCE both streams come from the same discharge record -- a disclosed
    semantic difference vs ISU's separate RPT tests.

GO DISCIPLINE
  Real evaluation requires --run-eval --go GO.json: an APPROVED GO with
  allow_fit exactly false pinning the exact code import closure, the CALCE
  assets (4 files + 25 records gz, each path+sha256), the three ISU
  checkpoints, the A2 PREP manifest (control-semantics reference), a fresh
  output_dir and receipt_path, and a fresh request_id.  Every payload read is
  audited and must be a GO-pinned asset.  After full success the request_id
  is registered in the consumed-GO registry (append-only).  Refusals write
  nothing.  Default mode --self-check: synthetic tmpdir data only, 0 real
  payload reads, 0 real checkpoints, 0 fits, 0 GO created or consumed.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import resource
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SELF_PATH = os.path.abspath(__file__)
SELF_NAME = os.path.basename(SELF_PATH)
A3_DIR = os.path.dirname(HERE)
A2_DIR = os.path.join(os.path.dirname(A3_DIR), "multirate_state_A2_20261022")
for _p in (A3_DIR, A2_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
import torch

import a2_prep
import a2_infer
import a3_infer
import a3_model
import a3_train
from a2_infer import (DELAY7D_SECONDS, MIN_VISIBLE_RECORDS, ReadStats,
                      _b2_arm_records, _rpt_records_for_arm,
                      build_queries as isu_build_queries)
from a2_infer import InferenceError
from a2_prep import CONTROL_DIM, CONTROL_FIELDS
from a3_infer import (AsOfWalkerA3, FILTER_DTYPE, _load_arm_model_a3,
                      reference_asof_state_a3)
from a3_model import ARM_CONFIGS, WEEK_SECONDS
from a3_train import (DEFAULT_CONSUMED_REGISTRY, load_consumed_request_ids,
                      register_consumed_go)

# --------------------------------------------------------------- constants
CELL_ID = "CS2_35"
CALCE_DATA_ROOT = ("/home/yndx/zxk/rul/data/processed/"
                   "CALCE_CS2_35_DataV1_v3")
CALCE_SERIES_NAME = "capacity_series.csv"
CALCE_MEAS_NAME = "discharge_measurements.jsonl"
CALCE_ENDPOINT_NAME = "endpoint_labels.json"
CALCE_MANIFEST_NAME = "manifest.json"
NOMINAL_AH = 1.1
EVENT_THRESHOLD_AH = 0.88
QUERY_ARMS = ("raw", "sparse2", "delay7d")
CURRENT_EPS_A = 1e-3           # |I| <= 1 mA treated as rest (excluded from legs)
ENERGY_DIMS = (17, 18, 19, 20)  # Wh dims absent from the records cache
NAIVE_FAMILIES = ("hold_last", "past_slope")
OWNER_THREAD_ID = "01a15c3a-1a06-7d61-8517-27b70b246183"
TZ_DISCLOSURE = ("source Date_Time has no timezone; parsed as timezone-naive "
                 "and treated as UTC (offset 0) -- disclosed, never corrected")
ESTIMAND_DECLARATION = {
    "quantity": "next_observed_capacity_given_arrived_prefix",
    "definition": ("predict the capacity of the next observation that "
                   "arrives after calendar time q, given only the prefix of "
                   "already-arrived capacity observations (ISU nextcapacity "
                   "/ A3 next-jump semantics)"),
    "rul_labels_used": False,
    "endpoint_role": ("evaluation_context_only: first observed crossing of "
                      "0.88 Ah is used solely for pre/post-event bucketing, "
                      "never as a label"),
    "go_override": ("endpoint_labels.models_fit_or_infer_allowed=false is "
                    "overridden by this GO to capacity-conditioned inference "
                    "only, zero fits; RUL labels stay frozen disallowed"),
}
CHECKPOINT_KEYS = ("a3_full_seed42", "a3_full_seed43", "a3_full_seed44")

# ------------------------------------------------------- ISU->CALCE mapping
# CONTROL_MAPPING[i] documents how CALCE dim i maps to a2_prep.CONTROL_FIELDS:
#   ("leg", stat)        -> statistic over the fragment's charge/discharge leg
#   ("const", ...)       -> structural constant (masked)
#   ("series"/"derived") -> validated series value / derived sum
# Legs: charge = samples with current_A > +CURRENT_EPS_A, discharge =
# current_A < -CURRENT_EPS_A (rest excluded); samples ordered by source_row;
# t = time_s (file-level Test_Time, valid within one fragment).
# Q stats use the DEVICE coulomb counters made leg-local
# (counter - counter[first leg sample]); ISU Q_sample_stats are per-sample
# cumulative capacity within a leg -- same construction.
CONTROL_MAPPING = (
    ("dur_charge_weeks",           "leg", "dur",        "charge"),
    ("dur_discharge_weeks",        "leg", "dur",        "discharge"),
    ("gap_charge_discharge_weeks", "leg", "gap",        "charge->discharge"),
    ("q_last_charge_ah",           "leg", "q_last",     "charge"),
    ("q_last_discharge_ah",        "leg", "q_last",     "discharge"),
    ("q_mean_charge_ah",           "leg", "q_mean",     "charge"),
    ("q_mean_discharge_ah",        "leg", "q_mean",     "discharge"),
    ("q_span_charge_ah",           "leg", "q_span",     "charge"),
    ("q_span_discharge_ah",        "leg", "q_span",     "discharge"),
    ("v_mean_charge_v",            "leg", "v_mean",     "charge"),
    ("v_mean_discharge_v",         "leg", "v_mean",     "discharge"),
    ("v_last_charge_v",            "leg", "v_last",     "charge"),
    ("v_last_discharge_v",         "leg", "v_last",     "discharge"),
    ("i_mean_abs_charge_a",        "leg", "i_mean_abs", "charge"),
    ("i_mean_abs_discharge_a",     "leg", "i_mean_abs", "discharge"),
    ("i_max_abs_charge_a",         "leg", "i_max_abs",  "charge"),
    ("i_max_abs_discharge_a",      "leg", "i_max_abs",  "discharge"),
    ("e_last_charge_wh",           "const", "no_wh_column", None),
    ("e_last_discharge_wh",        "const", "no_wh_column", None),
    ("e_mean_charge_wh",           "const", "no_wh_column", None),
    ("e_mean_discharge_wh",        "const", "no_wh_column", None),
    ("capacity_charge_ah",         "leg", "leg_capacity", "charge"),
    ("capacity_discharge_ah",      "series", "validated_capacity", None),
    ("throughput_ah",              "derived", "charge_plus_discharge", None),
)
assert len(CONTROL_MAPPING) == CONTROL_DIM == 24
assert tuple(m[0] for m in CONTROL_MAPPING) == tuple(n for n, _ in CONTROL_FIELDS)

# ------------------------------------------------------------- read audit
class ReadAudit(object):
    """Every payload byte read goes through here; a successful GO run must
    have its full read set inside the GO-pinned asset set."""

    def __init__(self):
        self.paths = []

    def read_bytes(self, path):
        self.paths.append(os.path.realpath(path))
        with open(path, "rb") as f:
            return f.read()

    def read_json_gz_lines(self, path):
        blob = self.read_bytes(path)
        out = []
        with gzip.open(io.BytesIO(blob), "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out


AUDIT = ReadAudit()

# ------------------------------------------------------------- small utils
def _sha256_bytes(blob):
    return hashlib.sha256(blob).hexdigest()


def _sha256_path(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc(epoch):
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_naive(text):
    """ISO-8601 WITHOUT timezone -> epoch seconds, UTC-naive (disclosed)."""
    d = datetime.fromisoformat(str(text).strip().replace("Z", ""))
    if d.tzinfo is not None:
        raise ValueError("unexpected timezone-aware timestamp %r" % text)
    return (d - datetime(1970, 1, 1)).total_seconds()


def _finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) \
        and math.isfinite(float(x))


def _json_safe(obj):
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_json_safe(obj), f, indent=2, ensure_ascii=False,
                  allow_nan=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def peak_rss_gb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024.0 \
        / (1024.0 ** 3)


def code_closure():
    """Real import closure: hashes of SELF + every module loaded from the
    A3/A2 trees.  The GO must pin exactly this set (a3_targets.py and
    a3_fastdata.py do not exist in this tree; A3 reuses a2_targets.py /
    a2_fastdata.py by import)."""
    out = {}
    seen = set()
    for name, mod in sorted(sys.modules.items()):
        f = getattr(mod, "__file__", None)
        if not f:
            continue
        real = os.path.realpath(f)
        if not os.path.isabs(real) or not os.path.isfile(real):
            continue  # synthetic/namespace modules with relative __file__
        if real in seen:
            continue
        seen.add(real)
        if real.startswith(os.path.realpath(A3_DIR) + os.sep) or \
                real.startswith(os.path.realpath(A2_DIR) + os.sep):
            out[os.path.basename(f)] = _sha256_path(f)
    out[SELF_NAME] = _sha256_path(SELF_PATH)
    return out


def _is_sha(value):
    return isinstance(value, str) and len(value) == 64 and \
        all(c in "0123456789abcdef" for c in value.lower())


# --------------------------------------------------------- CALCE ingestion
def load_observations(audit, data_root=CALCE_DATA_ROOT):
    """capacity_series.csv -> validated observation list (frozen rule)."""
    blob = audit.read_bytes(os.path.join(data_root, CALCE_SERIES_NAME))
    reader = csv.DictReader(io.StringIO(blob.decode("utf-8")))
    required = {"source_file", "source_cycle", "source_occurrence", "step",
                "discharge_end_datetime", "capacity_Ah", "status",
                "duplicate_of"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise ValueError("capacity_series.csv missing columns %r" % missing)
    obs = []
    n_status_excluded = 0
    n_dup_excluded = 0
    for row in reader:
        if row["status"] != "VALID_SAMPLED_CC_DISCHARGE":
            n_status_excluded += 1
            continue
        if str(row["duplicate_of"]).strip():
            n_dup_excluded += 1
            continue
        cap = float(row["capacity_Ah"])
        if not math.isfinite(cap) or cap <= 0.0:
            raise ValueError("invalid capacity on a VALID row: %r" % row)
        stop = parse_iso_naive(row["discharge_end_datetime"])
        obs.append({
            "source_file": row["source_file"],
            "file_base": os.path.basename(row["source_file"]),
            "cycle": int(row["source_cycle"]),
            "occurrence": int(row["source_occurrence"]),
            "step": int(row["step"]),
            "stop_epoch": stop,
            "stop_iso": str(row["discharge_end_datetime"]),
            "capacity_ah": cap,
        })
    obs.sort(key=lambda r: (r["stop_epoch"], r["file_base"], r["cycle"],
                            r["occurrence"]))
    for a, b in zip(obs, obs[1:]):
        if b["stop_epoch"] <= a["stop_epoch"]:
            raise ValueError("observation discharge_end_datetime repeats: "
                             "%s vs %s" % (a["stop_iso"], b["stop_iso"]))
    for i, r in enumerate(obs):
        r["source_rpt_index"] = i
    counts = {"rows_total": n_status_excluded + n_dup_excluded + len(obs),
              "valid_unique": len(obs),
              "excluded_status": n_status_excluded,
              "excluded_duplicate_alias": n_dup_excluded}
    return obs, counts


def load_endpoint(audit, obs, data_root=CALCE_DATA_ROOT):
    blob = audit.read_bytes(os.path.join(data_root, CALCE_ENDPOINT_NAME))
    doc = json.loads(blob.decode("utf-8"))
    if doc.get("RUL_labels_allowed") is not False:
        raise ValueError("endpoint freeze violated: RUL_labels_allowed!=false")
    thr = float(doc["threshold_Ah"])
    cross = doc["first_observed_valid_crossing"]
    event_epoch = parse_iso_naive(cross["discharge_end_datetime"])
    below = [r for r in obs if r["capacity_ah"] <= thr + 1e-12]
    if not below:
        raise ValueError("no observed crossing of %.2f Ah in valid series" % thr)
    first = below[0]
    if abs(first["stop_epoch"] - event_epoch) > 1e-6 or \
            abs(first["capacity_ah"] - float(cross["capacity_Ah"])) > 1e-9:
        raise ValueError("endpoint crossing mismatch vs capacity series")
    return {"threshold_ah": thr,
            "event_epoch": event_epoch,
            "event_iso": cross["discharge_end_datetime"],
            "event_capacity_ah": float(cross["capacity_Ah"]),
            "n_below_threshold": len(below),
            "n_post_event_observations":
                len(obs) - 1 - first["source_rpt_index"],
            "rul_labels_allowed": doc.get("RUL_labels_allowed"),
            "true_first_eol_registered": doc.get("true_first_EOL_event"),
            "independent_confirmation_ready":
                doc.get("independent_confirmation_ready")}


def load_measurements_index(audit, data_root=CALCE_DATA_ROOT):
    """discharge_measurements.jsonl -> {(file_base, cycle, occurrence): rec}."""
    blob = audit.read_bytes(os.path.join(data_root, CALCE_MEAS_NAME))
    index = {}
    with io.StringIO(blob.decode("utf-8")) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            key = (os.path.basename(rec["source_file"]),
                   int(rec["source_cycle"]), int(rec["source_occurrence"]))
            if key in index:
                raise ValueError("duplicate measurement key %r" % (key,))
            index[key] = rec
    return index


def fragment_samples(file_base, lo_row, hi_row, records_cache, audit,
                     data_root=CALCE_DATA_ROOT):
    """records.jsonl.gz samples with lo_row <= source_row <= hi_row."""
    if file_base not in records_cache:
        path = os.path.join(data_root, file_base + ".records.jsonl.gz")
        records_cache[file_base] = audit.read_json_gz_lines(path)
    recs = records_cache[file_base]
    out = []
    for r in recs:
        sr = int(r["source_row"])
        if int(lo_row) - 1 <= sr <= int(hi_row):
            out.append(r)
    out.sort(key=lambda r: int(r["source_row"]))
    return out


# ------------------------------------------------- 24-dim control builder
def _leg_stats(samples, leg_idx, counter_key, t_key="time_s"):
    """Statistics over one leg (given as a list of sample indices); None when
    the leg is empty.  The leg-local Q series is anchored at the counter of
    the sample IMMEDIATELY BEFORE the leg (same fragment, so no cross-record
    information) when it exists -- this reproduces the repair protocol's
    baseline->end counter construction, and degenerates to first-sample
    anchoring when the leg starts the fragment."""
    if not leg_idx:
        return None
    lo = leg_idx[0]
    hi = leg_idx[-1]
    t = [float(samples[i][t_key]) for i in leg_idx]
    v = [float(samples[i]["voltage_V"]) for i in leg_idx]
    i_abs = [abs(float(samples[i]["current_A"])) for i in leg_idx]
    c0 = float(samples[lo - 1][counter_key]) if lo > 0 \
        else float(samples[lo][counter_key])
    q = [float(samples[i][counter_key]) - c0 for i in leg_idx]
    return {"dur": (t[-1] - t[0]) / WEEK_SECONDS,
            "q_last": q[-1],
            "q_mean": sum(q) / len(q),
            "q_span": max(q) - min(q),
            "v_mean": sum(v) / len(v),
            "v_last": v[-1],
            "i_mean_abs": sum(i_abs) / len(i_abs),
            "i_max_abs": max(i_abs),
            "leg_capacity": q[-1],  # anchored leg total (== q_last)
            "t_first": t[0], "t_last": t[-1], "n": len(leg_idx)}


def _put(values, masks, idx, value, admissible):
    if value is not None and math.isfinite(float(value)) and admissible:
        values[idx] = float(value)
        masks[idx] = 1.0
    else:
        values[idx] = 0.0
        masks[idx] = 0.0


def fragment_control(samples, validated_capacity_ah):
    """records fragment + validated capacity -> (values[24], masks[24]).

    a2_prep.CONTROL_MISSING_RULE discipline: a field is present (mask=1) iff
    its raw statistic exists, is finite and admissible (durations/gaps/spans
    >= 0, capacities/throughput >= 0); otherwise value=0.0, mask=0.0.
    Energy/Wh dims (17-20) have no cached column -> always mask=0.
    """
    charge_idx = [i for i, s in enumerate(samples)
                  if float(s["current_A"]) > CURRENT_EPS_A]
    disch_idx = [i for i, s in enumerate(samples)
                 if float(s["current_A"]) < -CURRENT_EPS_A]
    ch = _leg_stats(samples, charge_idx, "charge_counter_Ah")
    di = _leg_stats(samples, disch_idx, "discharge_counter_Ah")
    values = [0.0] * CONTROL_DIM
    masks = [0.0] * CONTROL_DIM
    _put(values, masks, 0, ch["dur"] if ch else None,
         ch is not None and ch["dur"] >= 0.0)
    _put(values, masks, 1, di["dur"] if di else None,
         di is not None and di["dur"] >= 0.0)
    gap = ((di["t_first"] - ch["t_last"]) / WEEK_SECONDS) if (ch and di) \
        else None
    _put(values, masks, 2, gap, gap is not None and gap >= 0.0)
    for base, leg in ((3, ch), (4, di)):
        _put(values, masks, base, leg["q_last"] if leg else None,
             leg is not None and leg["q_last"] >= 0.0)
    for base, leg in ((5, ch), (6, di)):
        _put(values, masks, base, leg["q_mean"] if leg else None,
             leg is not None and leg["q_mean"] >= 0.0)
    for base, leg in ((7, ch), (8, di)):
        _put(values, masks, base, leg["q_span"] if leg else None,
             leg is not None and leg["q_span"] >= 0.0)
    for base, leg in ((9, ch), (10, di)):
        _put(values, masks, base, leg["v_mean"] if leg else None,
             leg is not None)
    for base, leg in ((11, ch), (12, di)):
        _put(values, masks, base, leg["v_last"] if leg else None,
             leg is not None)
    for base, leg in ((13, ch), (14, di)):
        _put(values, masks, base, leg["i_mean_abs"] if leg else None,
             leg is not None)
    for base, leg in ((15, ch), (16, di)):
        _put(values, masks, base, leg["i_max_abs"] if leg else None,
             leg is not None)
    for idx in ENERGY_DIMS:  # 17-20: no Wh column in the records cache
        values[idx] = 0.0
        masks[idx] = 0.0
    _put(values, masks, 21, ch["leg_capacity"] if ch else None,
         ch is not None and ch["leg_capacity"] >= 0.0)
    _put(values, masks, 22, float(validated_capacity_ah),
         float(validated_capacity_ah) >= 0.0)
    thr = None
    if ch is not None and di is not None and ch["leg_capacity"] >= 0.0 \
            and di["leg_capacity"] >= 0.0:
        thr = ch["leg_capacity"] + di["leg_capacity"]
    _put(values, masks, 23, thr, thr is not None and thr >= 0.0)
    for v, m in zip(values, masks):
        if not math.isfinite(v) or m not in (0.0, 1.0):
            raise ValueError("control builder emitted non-finite value/bad mask")
        if m == 0.0 and v != 0.0:
            raise ValueError("masked field with non-zero value")
    return values, masks


def build_controls(obs, meas_index, audit, data_root=CALCE_DATA_ROOT):
    """24-dim controls for every observation (records cache, one pass)."""
    records_cache = {}
    controls = {}
    cross_max = 0.0
    n_masked_dim = [0] * CONTROL_DIM
    for r in obs:
        key = (r["file_base"], r["cycle"], r["occurrence"])
        meas = meas_index.get(key)
        if meas is None:
            raise ValueError("no discharge_measurements row for %r" % (key,))
        if meas.get("status") != "VALID_SAMPLED_CC_DISCHARGE":
            raise ValueError("measurement status mismatch for %r" % (key,))
        samples = fragment_samples(r["file_base"], meas["first_source_row"],
                                   meas["last_source_row"], records_cache,
                                   audit, data_root)
        if not samples:
            raise ValueError("empty records fragment for %r" % (key,))
        values, masks = fragment_control(samples, r["capacity_ah"])
        controls[key] = (values, masks)
        for i in range(CONTROL_DIM):
            n_masked_dim[i] += int(masks[i] == 0.0)
        if masks[4] == 1.0:
            cross_max = max(cross_max, abs(values[4] - r["capacity_ah"]))
    stats = {"n_fragments": len(controls),
             "current_eps_a": CURRENT_EPS_A,
             "mask_rate_per_dim": [round(n_masked_dim[i] / float(len(obs)), 6)
                                   for i in range(CONTROL_DIM)],
             "energy_dims_always_masked": list(ENERGY_DIMS),
             "mapping": [{"index": i, "name": CONTROL_MAPPING[i][0],
                          "kind": CONTROL_MAPPING[i][1],
                          "stat": CONTROL_MAPPING[i][2],
                          "leg": CONTROL_MAPPING[i][3]}
                         for i in range(CONTROL_DIM)],
             "max_abs_discharge_q_last_minus_capacity_ah": cross_max}
    return controls, stats


# ------------------------------------------------------- panel construction
def arm_policy(rows, arm):
    """a2_infer._b2_arm_records UNCHANGED, anchor_index=0 (the CALCE anchor
    is the FIRST valid observation; ISU used the second)."""
    return _b2_arm_records(rows, 0, arm)


def base_rpt_records(rows):
    """All observations as a2_targets-style RPT records (valid, arrival=stop;
    per-arm arrival is applied by a2_infer._rpt_records_for_arm)."""
    return [{"valid": True,
             "source_epoch": float(r["stop_epoch"]),
             "available_epoch": float(r["stop_epoch"]),
             "capacity_ah": float(r["capacityAh"]),
             "source_rpt_index": int(r["source_rpt_index"])}
            for r in rows]


def calce_build_queries(rows, arm, policy_rows, warmup_from_index=0,
                        min_visible=MIN_VISIBLE_RECORDS,
                        threshold_skip_ah=None):
    """CALCE adaptation of a2_infer.build_queries (frozen deltas):
      * warmup anchored at rows[warmup_from_index].stop + 1 week (A4 design:
        q >= anchor + 1 week; ISU anchored at rows[1]);
      * the ISU visible_threshold skip is REMOVED (threshold_skip_ah=None)
        so post-event queries exist; pass a threshold to restore ISU
        behaviour exactly (self-check proves equivalence);
      * queries with no next full observation are DROPPED (no target);
      * each query carries query_source_index (its own observation row).
    Everything else (min-visible gating, anchor = visible[-1] by arrival,
    dedupe by (arm, anchor index), target = next FULL observation) is the
    ISU rule.
    """
    skipped = {"warmup": 0, "visible_lt_min": 0, "duplicate_anchor": 0,
               "visible_threshold": 0, "no_next_target": 0}
    queries = []
    seen = set()
    if len(rows) < 4:
        return queries, skipped
    warmup_epoch = float(rows[warmup_from_index]["stop_epoch"]) + WEEK_SECONDS
    for qrow in rows:
        q = float(qrow["stop_epoch"])
        if q < warmup_epoch:
            skipped["warmup"] += 1
            continue
        visible = [r for r in policy_rows
                   if float(r["arrival_epoch"]) <= q + 1e-9]
        if len(visible) < int(min_visible):
            skipped["visible_lt_min"] += 1
            continue
        anchor = visible[-1]
        aidx = int(anchor["source_rpt_index"])
        key = (arm, aidx)
        if key in seen:
            skipped["duplicate_anchor"] += 1
            continue
        seen.add(key)
        caps = [float(r["capacityAh"]) for r in visible]
        if threshold_skip_ah is not None and \
                any(cap <= float(threshold_skip_ah) for cap in caps):
            skipped["visible_threshold"] += 1
            continue
        next_rows = [r for r in rows if float(r["stop_epoch"]) > q + 1e-9]
        if not next_rows:
            skipped["no_next_target"] += 1
            continue
        next_row = next_rows[0]
        queries.append({
            "arm": arm,
            "query_epoch": q,
            "query_source_index": int(qrow["source_rpt_index"]),
            "anchor_stop_epoch": float(anchor["stop_epoch"]),
            "anchor_arrival_epoch": float(anchor["arrival_epoch"]),
            "anchor_index": aidx,
            "visible_records": len(visible),
            "visible_source_indices": ";".join(
                str(int(r["source_rpt_index"])) for r in visible),
            "visible_capacity_min_ah": min(caps),
            "visible_caps": caps,
            "visible_stops": [float(r["stop_epoch"]) for r in visible],
            "target_source_rpt_index": int(next_row["source_rpt_index"]),
            "target_stop_epoch": float(next_row["stop_epoch"]),
            "target_capacity_ah": float(next_row["capacityAh"]),
        })
    return queries, skipped


def build_arm_sequence(cell_id, obs, controls, rpts_arm):
    """a2_prep.cell_sequence UNCHANGED on CALCE-mapped records: cycle events
    (24-dim control) for ALL observations, RPT events = the arm's retained
    observations (ISU structure: dense controls, arm-filtered capacities)."""
    cycle_recs = []
    for r in obs:
        values, masks = controls[(r["file_base"], r["cycle"], r["occurrence"])]
        cycle_recs.append({
            "source_epoch": float(r["stop_epoch"]),
            "available_epoch": float(r["stop_epoch"]),
            "control": [float(v) for v in values],
            "control_mask": [float(m) for m in masks],
        })
    return a2_prep.cell_sequence(cell_id, cycle_recs, rpts_arm,
                                 cutoff_epoch=None)


def build_panel(obs, controls):
    """Per-arm policy + sequence + query grid (single cell)."""
    rows = [{"source_rpt_index": r["source_rpt_index"],
             "stop_epoch": r["stop_epoch"],
             "capacityAh": r["capacity_ah"],
             "arrival_epoch": r["stop_epoch"]} for r in obs]
    all_rpts = base_rpt_records(rows)
    panel = {}
    skips_total = {}
    qref_by_arm = {}
    for arm in QUERY_ARMS:
        policy = arm_policy(rows, arm)
        rpts_arm = _rpt_records_for_arm(all_rpts, policy)
        seq = build_arm_sequence(CELL_ID, obs, controls, rpts_arm)
        if seq.get("anchor") is None:
            raise ValueError("arm %s produced no anchored sequence" % arm)
        qref_by_arm[arm] = float(seq["q_ref_ah"])
        queries, skips = calce_build_queries(rows, arm, policy)
        panel[arm] = {"seq": seq, "policy": policy, "rpts_arm": rpts_arm,
                      "queries": queries}
        skips_total[arm] = skips
    if len(set(qref_by_arm.values())) != 1:
        raise ValueError("q_ref differs across arms: %r" % qref_by_arm)
    return panel, skips_total, qref_by_arm["raw"]


# ------------------------------------------------------------ naive models
def naive_hold_last(query):
    return float(query["visible_caps"][-1])


def naive_past_slope(query):
    """ISU run_baselines.py semantic: extrapolate the last two VISIBLE
    capacities to the observed next-observation stop time."""
    caps = query["visible_caps"]
    stops = query["visible_stops"]
    base = float(caps[-1])
    slope0 = 0.0
    if len(caps) > 1:
        dt = (float(stops[-1]) - float(stops[-2])) / WEEK_SECONDS
        if dt > 0.0:
            slope0 = (base - float(caps[-2])) / dt
    return base + slope0 * ((float(query["target_stop_epoch"])
                             - float(stops[-1])) / WEEK_SECONDS)


# ---------------------------------------------------------------- metrics
Z90 = 1.6448536269514722


def score_pairs(pairs):
    """pairs: (target_ah, pred_mu_ah, pred_sd_ah_or_None)."""
    n = len(pairs)
    if n == 0:
        return {"n": 0}
    err = np.array([y - mu for y, mu, _ in pairs], dtype=np.float64)
    out = {"n": int(n),
           "mae_ah": float(np.mean(np.abs(err))),
           "rmse_ah": float(np.sqrt(np.mean(err ** 2))),
           "bias_ah": float(np.mean(err)),
           "over_20mah": float(np.mean(np.abs(err) > 0.020)),
           "over_50mah": float(np.mean(np.abs(err) > 0.050))}
    sds = [s for _, _, s in pairs]
    if all(s is not None and s > 0.0 for s in sds):
        nll = [0.5 * ((y - mu) ** 2 / (s * s) + 2.0 * math.log(s)
                      + math.log(2.0 * math.pi))
               for (y, mu, s) in pairs]
        out["gaussian_nll"] = float(np.mean(nll))
        out["cov90"] = float(np.mean(
            [abs(y - mu) <= Z90 * s for (y, mu, s) in pairs]))
    return out


# ------------------------------------------------------------ GO validation
def _check_abs_fresh(path, label, problems):
    if not isinstance(path, str) or not path:
        problems.append("%s missing" % label)
        return None
    if not os.path.isabs(path):
        problems.append("%s must be absolute: %r" % (label, path))
        return None
    if os.path.exists(path):
        problems.append("%s must be fresh (exists): %s" % (label, path))
        return None
    return os.path.realpath(path)


def _pin_check(go, name, problems, audit):
    spec = go.get(name)
    ok = isinstance(spec, dict) and isinstance(spec.get("path"), str) \
        and _is_sha(spec.get("sha256"))
    if not ok:
        problems.append("%s must be {path, sha256}" % name)
        return None
    path = spec["path"]
    if not os.path.isabs(path) or not os.path.isfile(path):
        problems.append("%s path missing: %s" % (name, path))
        return None
    digest = _sha256_path(path)
    if digest != spec["sha256"]:
        problems.append("%s sha256 mismatch: go=%s actual=%s"
                        % (name, spec["sha256"], digest))
        return None
    audit.read_bytes(path)
    return path


def validate_calce_go(go, registry_path=DEFAULT_CONSUMED_REGISTRY,
                      load_models=False, stats=None):
    """Validate one CALCE zero-shot GO.  Returns (binding, problems); never
    writes, never consumes.  Checkpoint loading happens here so a broken
    checkpoint is a cheap refusal before any output path is touched."""
    problems = []
    audit = ReadAudit()
    stats = stats or ReadStats()
    if not isinstance(go, dict):
        return None, ["GO is not an object"]
    if go.get("status") != "APPROVED":
        problems.append("status must be APPROVED")
    if go.get("allow_inference") is not True:
        problems.append("allow_inference must be true")
    if go.get("allow_fit") is not False:
        problems.append("allow_fit must be exactly false (zero-shot GO)")
    if go.get("allow_train") is not False:
        problems.append("allow_train must be false")
    if go.get("allow_C4") is not False:
        problems.append("allow_C4 must be false")
    scope = go.get("scope")
    if not isinstance(scope, str) or "CALCE-ZEROSHOT" not in scope:
        problems.append("scope must contain CALCE-ZEROSHOT")
    estimand = go.get("estimand")
    if not isinstance(estimand, dict):
        problems.append("estimand declaration missing")
    else:
        if estimand.get("quantity") != ESTIMAND_DECLARATION["quantity"]:
            problems.append("estimand.quantity mismatch")
        if estimand.get("rul_labels_used") is not False:
            problems.append("estimand.rul_labels_used must be false")
        if "evaluation_context_only" not in str(estimand.get("endpoint_role")):
            problems.append("estimand.endpoint_role must mark the EOL event "
                            "evaluation_context_only")
    if go.get("owner_thread_id") != OWNER_THREAD_ID:
        problems.append("owner_thread_id mismatch")
    if go.get("device") != "cpu":
        problems.append("device must be cpu")
    if go.get("no_grad") is not True:
        problems.append("no_grad must be true")
    rss = go.get("max_rss_gb")
    if not _finite(rss) or float(rss) <= 0.0:
        problems.append("max_rss_gb must be a positive number")
    rt = go.get("max_runtime_seconds")
    if not isinstance(rt, int) or not (60 <= rt <= 21600):
        problems.append("max_runtime_seconds must be int in [60, 21600]")
    request_id = go.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        problems.append("request_id missing")
    else:
        try:
            consumed = load_consumed_request_ids(registry_path)
        except FileNotFoundError:
            consumed = set()
        except Exception as exc:  # noqa: BLE001
            consumed = None
            problems.append("registry unreadable: %s" % exc)
        if consumed is not None and request_id in consumed:
            problems.append("request_id %r already consumed" % request_id)
    if "registry" in go and go.get("registry") != registry_path:
        problems.append("registry must equal the canonical registry path")

    closure = code_closure()
    codes = go.get("code_sha256")
    if not isinstance(codes, dict):
        problems.append("code_sha256 must be an object")
    else:
        want = closure
        if set(codes) != set(want):
            extra = sorted(set(codes) - set(want))
            lack = sorted(set(want) - set(codes))
            problems.append("code_sha256 set mismatch (extra=%r missing=%r)"
                            % (extra, lack))
        for name, sha in sorted(codes.items()):
            if name in want and want[name] != sha:
                problems.append("code_sha256[%s] mismatch" % name)

    assets = {}
    for name in ("capacity_series", "discharge_measurements",
                 "endpoint_labels", "calce_manifest", "prep_reference"):
        path = _pin_check(go, name, problems, audit)
        if path:
            assets[name] = path
    gz = go.get("records_gz")
    if not isinstance(gz, dict) or len(gz) != 25:
        problems.append("records_gz must pin exactly 25 files")
    else:
        for base in sorted(gz):
            spec = gz[base]
            ok = isinstance(spec, dict) and isinstance(spec.get("path"), str) \
                and _is_sha(spec.get("sha256"))
            if not ok or not os.path.isfile(spec.get("path", "")) or \
                    os.path.basename(os.path.abspath(spec["path"])) != base:
                problems.append("records_gz[%s] bad pin" % base)
                continue
            digest = _sha256_path(spec["path"])
            if digest != spec["sha256"]:
                problems.append("records_gz[%s] sha256 mismatch" % base)
                continue
            audit.read_bytes(spec["path"])
            assets.setdefault("records_gz", []).append(base)

    models = {}
    ck = go.get("checkpoints")
    if not isinstance(ck, dict) or sorted(ck) != sorted(CHECKPOINT_KEYS):
        problems.append("checkpoints must pin exactly %r"
                        % (list(CHECKPOINT_KEYS),))
    else:
        for key in CHECKPOINT_KEYS:
            spec = ck.get(key)
            if not isinstance(spec, dict) or not _is_sha(spec.get("sha256")):
                problems.append("checkpoint %s must be {path, sha256}" % key)
                continue
            if not os.path.isfile(spec.get("path", "")):
                problems.append("checkpoint %s path missing" % key)
                continue
            if load_models:
                try:
                    model, info = _load_arm_model_a3("full", spec, stats)
                except InferenceError as exc:
                    problems.append(str(exc))
                    continue
                models[key] = model

    out_dir = _check_abs_fresh(go.get("output_dir"), "output_dir", problems)
    receipt = _check_abs_fresh(go.get("receipt_path"), "receipt_path",
                               problems)
    if out_dir and receipt and \
            os.path.realpath(out_dir) == os.path.realpath(receipt):
        problems.append("output_dir and receipt_path must differ")
    if problems:
        return None, problems
    binding = dict(go)
    binding["assets"] = assets
    binding["models"] = models
    binding["code_sha256_verified"] = closure
    binding["read_audit"] = audit
    binding["rss_limit_gb"] = float(rss)
    binding["deadline_seconds"] = int(rt)
    return binding, []


# ---------------------------------------------------------------- run eval
CSV_FIELDS = (
    "query_id", "cell_id", "arm", "model_family", "family_class",
    "query_epoch", "query_utc", "event_bucket",
    "query_source_index",
    "anchor_index", "anchor_stop_epoch", "anchor_arrival_epoch",
    "visible_records", "visible_source_indices", "visible_capacity_min_ah",
    "target_source_rpt_index", "target_stop_epoch", "target_capacity_ah",
    "pred_mu_ah", "pred_sd_ah", "abs_error_ah", "gaussian_nll", "covered_90",
    "q_ref_ah", "state_D", "state_ell", "state_R",
    "state_capacity_var_total_ah2",
    "n_cycles_used", "n_rpt_used", "n_late_arrival_excluded",
) + tuple("control_%02d" % i for i in range(CONTROL_DIM)) \
  + tuple("control_mask_%02d" % i for i in range(CONTROL_DIM))


def _blank(v):
    return "" if v is None else v


def _gauss_nll(y, mu, sd):
    return 0.5 * ((y - mu) ** 2 / (sd * sd) + 2.0 * math.log(sd)
                  + math.log(2.0 * math.pi))


def run_eval(go_path, threads=0, verbose=False,
             registry_path=DEFAULT_CONSUMED_REGISTRY):
    """GO-gated zero-shot evaluation on the REAL CALCE payload."""
    started = time.monotonic()
    wall = _utc_now()
    with open(go_path, "rb") as f:
        go_blob = f.read()
    go_sha = _sha256_bytes(go_blob)
    try:
        go = json.loads(go_blob.decode("utf-8"))
    except ValueError as exc:
        print("GO unreadable: %s" % exc)
        return 2
    binding, problems = validate_calce_go(go, registry_path=registry_path,
                                          load_models=True)
    if problems:
        print("GO REFUSED (%d problems):" % len(problems))
        for p in problems:
            print("  - %s" % p)
        return 2
    out_dir = binding["output_dir"]
    receipt_path = binding["receipt_path"]
    os.makedirs(out_dir, exist_ok=False)
    if threads > 0:
        torch.set_num_threads(int(threads))
    deadline = started + float(binding["deadline_seconds"])
    rss_limit = binding["rss_limit_gb"]
    audit = binding["read_audit"]
    models = binding["models"]
    request_id = go["request_id"]

    def rss_check():
        if peak_rss_gb() > rss_limit:
            raise RuntimeError("RSS cap %.2f GB exceeded" % rss_limit)

    def time_check():
        if time.monotonic() > deadline:
            raise RuntimeError("runtime deadline reached")

    print("[calce-zero-shot] GO %s accepted (sha %s)"
          % (request_id, go_sha[:12]))
    # ALL payload reads go to the GO-pinned asset paths (never module
    # defaults) -- the post-run read-set assertion enforces this.
    assets = binding["assets"]
    data_root = os.path.dirname(assets["capacity_series"])
    obs, obs_counts = load_observations(audit, data_root=data_root)
    endpoint = load_endpoint(audit, obs, data_root=data_root)
    meas_index = load_measurements_index(audit, data_root=data_root)
    controls, ctrl_stats = build_controls(obs, meas_index, audit,
                                          data_root=data_root)
    panel, skips, qref = build_panel(obs, controls)
    event_epoch = endpoint["event_epoch"]

    n_rows = 0
    all_rows = []
    bucket_counts = {"pre_event": 0, "post_event": 0}
    with torch.no_grad():
        if torch.is_grad_enabled():
            raise RuntimeError("grad enabled despite no_grad GO field")
        for arm in QUERY_ARMS:
            entry = panel[arm]
            seq = entry["seq"]
            queries = entry["queries"]
            lag = DELAY7D_SECONDS if arm == "delay7d" else 0.0
            walkers = {}
            for key, model in models.items():
                walkers[key] = AsOfWalkerA3(model, seq, lag,
                                            ARM_CONFIGS["full"])
            for query in queries:
                time_check()
                if (n_rows % 25) == 0:
                    rss_check()
                q = float(query["query_epoch"])
                bucket = "pre_event" if q < event_epoch - 1e-9 \
                    else "post_event"
                bucket_counts[bucket] += 1
                qsi = int(query["query_source_index"])
                qobs = obs[qsi]
                values, masks = controls[(qobs["file_base"], qobs["cycle"],
                                          qobs["occurrence"])]
                naive = {"hold_last": naive_hold_last(query),
                         "past_slope": naive_past_slope(query)}
                states = {}
                preds = {}
                sds = {}
                for key, walker in walkers.items():
                    state = walker.state_at(q)
                    model = models[key]
                    mu, _latent, total_var, _H = model.capacity_moments(
                        state["m"], state["P"],
                        torch.tensor([qref], dtype=FILTER_DTYPE))
                    states[key] = state
                    preds[key] = float(mu[0])
                    sds[key] = float(math.sqrt(max(float(total_var[0]), 1e-30)))
                y = float(query["target_capacity_ah"])
                for family in list(models) + list(NAIVE_FAMILIES):
                    if family in preds:
                        mu = preds[family]
                        sd = sds[family]
                        family_class = "a3_zero_shot"
                        state = states[family]
                        extra = {
                            "state_D": float(state["m"][0, 0]),
                            "state_ell": float(state["m"][0, 1]),
                            "state_R": float(state["m"][0, 2]),
                            "state_capacity_var_total_ah2": sd * sd,
                            "n_cycles_used": int(state["n_cycles_used"]),
                            "n_rpt_used": int(state["n_rpt_used"]),
                            "n_late_arrival_excluded":
                                int(state["n_late_arrival_excluded"]),
                        }
                    else:
                        mu = naive[family]
                        sd = None
                        family_class = "naive_reference"
                        extra = {"state_D": None, "state_ell": None,
                                 "state_R": None,
                                 "state_capacity_var_total_ah2": None,
                                 "n_cycles_used": None, "n_rpt_used": None,
                                 "n_late_arrival_excluded": None}
                    row = {
                        "query_id": "CS2_35|%s|%d|%s"
                                    % (arm, query["anchor_index"], family),
                        "cell_id": CELL_ID,
                        "arm": arm,
                        "model_family": family,
                        "family_class": family_class,
                        "query_epoch": q,
                        "query_utc": _utc(q),
                        "event_bucket": bucket,
                        "query_source_index": qsi,
                        "anchor_index": query["anchor_index"],
                        "anchor_stop_epoch": query["anchor_stop_epoch"],
                        "anchor_arrival_epoch": query["anchor_arrival_epoch"],
                        "visible_records": query["visible_records"],
                        "visible_source_indices":
                            query["visible_source_indices"],
                        "visible_capacity_min_ah":
                            query["visible_capacity_min_ah"],
                        "target_source_rpt_index":
                            query["target_source_rpt_index"],
                        "target_stop_epoch": query["target_stop_epoch"],
                        "target_capacity_ah": y,
                        "pred_mu_ah": mu,
                        "pred_sd_ah": _blank(sd),
                        "abs_error_ah": abs(y - mu),
                        "gaussian_nll": _blank(
                            _gauss_nll(y, mu, sd) if sd is not None else None),
                        "covered_90": _blank(
                            int(abs(y - mu) <= Z90 * sd)
                            if sd is not None else None),
                        "q_ref_ah": qref,
                    }
                    row.update(extra)
                    for i in range(CONTROL_DIM):
                        row["control_%02d" % i] = values[i]
                        row["control_mask_%02d" % i] = masks[i]
                    all_rows.append(row)
                    n_rows += 1

    csv_path = os.path.join(out_dir, "predictions_calce.csv")
    tmp_csv = csv_path + ".tmp"
    with open(tmp_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS,
                                extrasaction="ignore")
        writer.writeheader()
        for row in all_rows:
            writer.writerow({k: _blank(v) for k, v in row.items()})
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_csv, csv_path)
    csv_sha = _sha256_path(csv_path)
    # read-set discipline: every audited payload read must be a GO-pinned asset
    pinned = set()
    for name in ("capacity_series", "discharge_measurements",
                 "endpoint_labels", "calce_manifest", "prep_reference"):
        pinned.add(os.path.realpath(go[name]["path"]))
    for base in go["records_gz"]:
        pinned.add(os.path.realpath(go["records_gz"][base]["path"]))
    unpinned = [p for p in audit.paths if p not in pinned]
    if unpinned:
        raise RuntimeError("payload reads outside the GO-pinned asset set: %r"
                           % unpinned[:3])

    # ------------------------------------------------------- metrics ------
    families = list(models) + list(NAIVE_FAMILIES)

    def pairs_for(rows_subset, family):
        return [(r["target_capacity_ah"], r["pred_mu_ah"],
                 r["pred_sd_ah"] if r["pred_sd_ah"] != "" else None)
                for r in rows_subset if r["model_family"] == family]

    metrics = {
        "estimand": ESTIMAND_DECLARATION,
        "cell_id": CELL_ID,
        "zero_shot": {
            "fits": 0, "gradient_steps": 0, "C4_records_touched": 0,
            "rul_labels_used": False,
            "checkpoints_from": "ISU ILCC multirate_state_A3_rate_20261024",
            "note": ("all predictors applied zero-shot; F0_hgb not loadable "
                     "(no persisted model artifact in the strong-baselines "
                     "run) and NOT re-fit per the 0-fit claim"),
        },
        "timezone_disclosure": TZ_DISCLOSURE,
        "event": endpoint,
        "panel": {
            "n_observations": len(obs),
            "observation_counts": obs_counts,
            "queries_by_arm": {arm: len(panel[arm]["queries"])
                               for arm in QUERY_ARMS},
            "skips_by_arm": skips,
            "event_bucket_query_counts": bucket_counts,
            "q_ref_ah": qref,
            "anchor_iso": obs[0]["stop_iso"],
        },
        "controls": ctrl_stats,
        "predictors": {},
        "by_arm": {},
        "by_arm_bucket": {},
    }
    metrics["predictors"] = {f: score_pairs(pairs_for(all_rows, f))
                             for f in families}
    for arm in QUERY_ARMS:
        arm_rows = [r for r in all_rows if r["arm"] == arm]
        metrics["by_arm"][arm] = {f: score_pairs(pairs_for(arm_rows, f))
                                  for f in families}
        metrics["by_arm_bucket"][arm] = {}
        for bucket in ("pre_event", "post_event"):
            sub = [r for r in arm_rows if r["event_bucket"] == bucket]
            metrics["by_arm_bucket"][arm][bucket] = {
                f: score_pairs(pairs_for(sub, f)) for f in families}
    metrics_path = os.path.join(out_dir, "metrics.json")
    atomic_write_json(metrics_path, metrics)

    # ------------------------------------------------------- receipt ------
    finished = _utc_now()
    receipt = {
        "status": "COMPLETE_ZERO_SHOT_NO_FITS",
        "tool": SELF_NAME,
        "request_id": request_id,
        "go_path": os.path.abspath(go_path),
        "go_sha256": go_sha,
        "started_utc": wall,
        "finished_utc": finished,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "peak_rss_gb": round(peak_rss_gb(), 3),
        "rss_limit_gb": rss_limit,
        "zero_fits": 0,
        "zero_gradient_steps": 0,
        "zero_C4": 0,
        "rul_labels_used": False,
        "estimand": ESTIMAND_DECLARATION,
        "timezone_disclosure": TZ_DISCLOSURE,
        "endpoint_freeze_respected": {
            "RUL_labels_allowed": endpoint["rul_labels_allowed"],
            "endpoint_role": "evaluation_context_only",
        },
        "n_prediction_rows": n_rows,
        "n_payload_reads_audited": len(audit.paths),
        "code_sha256": binding["code_sha256_verified"],
        "checkpoints": {key: {"path": go["checkpoints"][key]["path"],
                              "sha256": go["checkpoints"][key]["sha256"]}
                        for key in CHECKPOINT_KEYS},
        "f0_hgb_status": "NOT_RUN_no_persisted_model_artifact_zero_shot",
        "output_files": {
            "predictions_calce.csv": {"path": csv_path, "sha256": csv_sha},
            "metrics.json": {"path": metrics_path,
                             "sha256": _sha256_path(metrics_path)},
        },
        "registration": {
            "registry": registry_path,
            "request_id": request_id,
            "go_sha256": go_sha,
            "finished_utc": finished,
        },
    }
    receipt_parent = os.path.dirname(receipt_path)
    if receipt_parent:
        os.makedirs(receipt_parent, exist_ok=True)
    atomic_write_json(receipt_path, receipt)
    out_copy = os.path.join(out_dir, "receipt.json")
    atomic_write_json(out_copy, receipt)
    register_consumed_go(registry_path, request_id, go_sha, finished)
    print("[calce-zero-shot] COMPLETE: %d rows, arm queries %r"
          % (n_rows, {a: len(panel[a]["queries"]) for a in QUERY_ARMS}))
    print("[calce-zero-shot] out_dir=%s" % out_dir)
    return 0


# ------------------------------------------------------------- self-check
class FixtureLog(object):
    def __init__(self):
        self.results = []

    def record(self, name, ok, detail=""):
        self.results.append((name, bool(ok), detail))
        print("RESULT %-38s %s %s" % (name, "PASS" if ok else "FAIL",
                                      detail if not ok else ""))


def _make_synth_obs(n=12, start_epoch=None, cap0=1.10, decay=0.025):
    start_epoch = start_epoch if start_epoch is not None \
        else parse_iso_naive("2020-01-01T00:00:00")
    obs = []
    for i in range(n):
        cap = cap0 - decay * i
        stop = start_epoch + i * 86400.0 + 3600.0
        obs.append({"source_file": "SYN/syn_%02d.xlsx" % (i % 2),
                    "file_base": "syn_%02d.xlsx" % (i % 2),
                    "cycle": i + 1, "occurrence": 0, "step": 7,
                    "stop_epoch": stop,
                    "stop_iso": datetime.fromtimestamp(stop, tz=timezone.utc)
                    .strftime("%Y-%m-%dT%H:%M:%S"),
                    "capacity_ah": cap})
    obs.sort(key=lambda r: r["stop_epoch"])
    for i, r in enumerate(obs):
        r["source_rpt_index"] = i
    return obs


def _make_synth_samples(cap_ah, t0, row_offset=2):
    """One synthetic fragment: rest + charge(+0.5A, 600 samples) + rest +
    discharge(current sized so the leg counter span == cap_ah, 600 samples).
    Counters rise only in their leg.  row_offset keeps fragments of one file
    row-disjoint (like the real per-file record cache)."""
    samples = []
    row = int(row_offset)
    t = t0
    cc = 0.0
    dc = 0.0
    i_dis = cap_ah / (600 * 10.0 / 3600.0)  # A, so discharge span == cap_ah
    for _ in range(10):  # rest
        samples.append({"data_point": row, "time_s": t,
                        "step_time_s": 10.0, "step": 3, "cycle": 1,
                        "current_A": 0.0, "voltage_V": 3.5,
                        "charge_counter_Ah": cc, "discharge_counter_Ah": dc,
                        "source_row": row})
        row += 1
        t += 10.0
    for k in range(600):  # charge
        cc += 0.5 * 10.0 / 3600.0
        samples.append({"data_point": row, "time_s": t, "step_time_s": 10.0,
                        "step": 4, "cycle": 1, "current_A": 0.5,
                        "voltage_V": 3.6 + 0.0001 * k,
                        "charge_counter_Ah": cc, "discharge_counter_Ah": dc,
                        "source_row": row})
        row += 1
        t += 10.0
    for _ in range(50):  # rest
        samples.append({"data_point": row, "time_s": t, "step_time_s": 10.0,
                        "step": 5, "cycle": 1, "current_A": 0.0,
                        "voltage_V": 4.1, "charge_counter_Ah": cc,
                        "discharge_counter_Ah": dc, "source_row": row})
        row += 1
        t += 10.0
    for k in range(600):  # discharge
        dc += i_dis * 10.0 / 3600.0
        samples.append({"data_point": row, "time_s": t, "step_time_s": 10.0,
                        "step": 7, "cycle": 1, "current_A": -i_dis,
                        "voltage_V": 3.9 - 0.0001 * k,
                        "charge_counter_Ah": cc, "discharge_counter_Ah": dc,
                        "source_row": row})
        row += 1
        t += 10.0
    return samples, {"charge_Ah": 0.5 * 600 * 10.0 / 3600.0,
                     "discharge_Ah": cap_ah,
                     "i_discharge_a": i_dis,
                     "first_row": int(row_offset), "last_row": row - 1,
                     "t0": t0, "t_end": t - 10.0}


def _write_synth_fixture(root):
    """Synthetic CALCE-shaped asset tree + 3 checkpoints + registry."""
    data = os.path.join(root, "data")
    os.makedirs(data)
    obs = _make_synth_obs()
    thr = 0.88
    below = [r for r in obs if r["capacity_ah"] <= thr]
    crossing = below[0]
    rows_csv = []
    for i, r in enumerate(obs):
        rows_csv.append({
            "source_file": r["source_file"],
            "source_cycle": r["cycle"], "source_occurrence": 0, "step": 7,
            "discharge_end_datetime": r["stop_iso"],
            "capacity_Ah": repr(r["capacity_ah"]),
            "status": "VALID_SAMPLED_CC_DISCHARGE", "duplicate_of": ""})
    # one UNCERTAIN + one VALID-but-alias row that must both be excluded
    rows_csv.insert(3, dict(rows_csv[2], status="UNCERTAIN"))
    rows_csv.append(dict(rows_csv[5], duplicate_of="SYN/syn_00.xlsx"))
    fields = ["source_file", "source_cycle", "source_occurrence", "step",
              "discharge_end_datetime", "capacity_Ah", "status",
              "duplicate_of"]
    with open(os.path.join(data, CALCE_SERIES_NAME), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows_csv)
    endpoint = {"nominal_Ah": 1.1, "threshold_Ah": thr,
                "first_observed_valid_crossing": {
                    "source_file": crossing["source_file"],
                    "source_cycle": crossing["cycle"],
                    "discharge_end_datetime": crossing["stop_iso"],
                    "capacity_Ah": crossing["capacity_ah"]},
                "RUL_labels_allowed": False,
                "true_first_EOL_event": None,
                "independent_confirmation_ready": False,
                "models_fit_or_infer_allowed": False}
    with open(os.path.join(data, CALCE_ENDPOINT_NAME), "w",
              encoding="utf-8") as f:
        json.dump(endpoint, f)
    gz_names = []
    meas_lines = []
    file_records = {}
    for i, r in enumerate(obs):
        samples, stats = _make_synth_samples(r["capacity_ah"],
                                             r["stop_epoch"] - 13000.0,
                                             row_offset=2 + i * 2000)
        fb = r["file_base"]
        if fb not in file_records:
            file_records[fb] = []
        for s in samples:
            s2 = dict(s)
            s2["cycle"] = r["cycle"]
            file_records[fb].append(s2)
        meas_lines.append({
            "source_file": r["source_file"],
            "source_cycle": r["cycle"], "source_occurrence": 0,
            "status": "VALID_SAMPLED_CC_DISCHARGE",
            "first_source_row": stats["first_row"],
            "last_source_row": stats["last_row"],
            "capacity_Ah": r["capacity_ah"]})
    with open(os.path.join(data, CALCE_MEAS_NAME), "w",
              encoding="utf-8") as f:
        for rec in meas_lines:
            f.write(json.dumps(rec) + "\n")
    for fb, recs in file_records.items():
        recs.sort(key=lambda s: s["source_row"])
        name = fb + ".records.jsonl.gz"
        with gzip.open(os.path.join(data, name), "wt",
                       encoding="utf-8") as f:
            for s in recs:
                f.write(json.dumps(s) + "\n")
        gz_names.append(name)
    # pad to 25 files (empty caches) so the fixture GO pins exactly 25
    for j in range(len(gz_names), 25):
        name = "syn_pad_%02d.xlsx.records.jsonl.gz" % j
        with gzip.open(os.path.join(data, name), "wt",
                       encoding="utf-8") as f:
            f.write("")
        gz_names.append(name)
    with open(os.path.join(data, CALCE_MANIFEST_NAME), "w",
              encoding="utf-8") as f:
        json.dump({"asset_root": data, "note": "synthetic fixture"}, f)
    # checkpoints: 3 small A3 state dicts (synthetic init, seeds 1/2/3)
    ck = {}
    for i, key in enumerate(CHECKPOINT_KEYS):
        m = a3_model.build_arm_model("full", seed=i + 1)
        path = os.path.join(root, "model_state_dict_%s.pt" % key)
        torch.save(m.state_dict(), path)
        ck[key] = path
    return {"data": data, "obs": obs, "gz_names": gz_names,
            "checkpoints": ck, "endpoint": endpoint,
            "crossing": crossing}


def _synth_go(root, fx, out_dir, registry, request_id, data_key="data"):
    data = fx[data_key] if data_key else fx["data"]
    pins = {}
    for name, fname in (("capacity_series", CALCE_SERIES_NAME),
                        ("discharge_measurements", CALCE_MEAS_NAME),
                        ("endpoint_labels", CALCE_ENDPOINT_NAME),
                        ("calce_manifest", CALCE_MANIFEST_NAME)):
        p = os.path.join(data, fname)
        pins[name] = {"path": os.path.realpath(p), "sha256": _sha256_path(p)}
    with open(os.path.join(root, "prep_ref.json"), "w", encoding="utf-8") as f:
        json.dump({"control": {"dim": 24}}, f)
    pins["prep_reference"] = {"path": os.path.realpath(
        os.path.join(root, "prep_ref.json")),
        "sha256": _sha256_path(os.path.join(root, "prep_ref.json"))}
    pins["records_gz"] = {}
    for name in fx["gz_names"]:
        p = os.path.join(data, name)
        pins["records_gz"][name] = {"path": os.path.realpath(p),
                                    "sha256": _sha256_path(p)}
    pins["checkpoints"] = {}
    for key, path in fx["checkpoints"].items():
        pins["checkpoints"][key] = {"path": os.path.realpath(path),
                                    "sha256": _sha256_path(path)}
    go = {
        "status": "APPROVED",
        "allow_inference": True,
        "allow_fit": False,
        "allow_train": False,
        "allow_C4": False,
        "scope": "CALCE-ZEROSHOT capacity-conditioned zero-shot inference "
                 "(synthetic fixture)",
        "estimand": dict(ESTIMAND_DECLARATION),
        "owner_thread_id": OWNER_THREAD_ID,
        "device": "cpu",
        "no_grad": True,
        "max_rss_gb": 2.0,
        "max_runtime_seconds": 600,
        "request_id": request_id,
        "code_sha256": code_closure(),
        "capacity_series": pins["capacity_series"],
        "discharge_measurements": pins["discharge_measurements"],
        "endpoint_labels": pins["endpoint_labels"],
        "calce_manifest": pins["calce_manifest"],
        "prep_reference": pins["prep_reference"],
        "records_gz": pins["records_gz"],
        "checkpoints": pins["checkpoints"],
        "output_dir": out_dir,
        "receipt_path": os.path.join(root, "receipts", request_id
                                     + "_receipt.json"),
        "registry": registry,
    }
    return go


def self_check(append_log=None):
    """Synthetic-only self-check (16+ fixtures).  Reads NO real payload,
    loads NO real checkpoint, creates/consumes NO real GO."""
    log = FixtureLog()
    started = time.monotonic()
    real_root = os.path.realpath(CALCE_DATA_ROOT)

    with tempfile.TemporaryDirectory(prefix="calce_zs_") as root:
        fx = _write_synth_fixture(root)
        obs = fx["obs"]

        # F01 mapping completeness ---------------------------------------
        samples, stats = _make_synth_samples(1.0, 1000.0)
        values, masks = fragment_control(samples, 1.0)
        ok = len(values) == 24 and len(masks) == 24
        ok = ok and all(m in (0.0, 1.0) for m in masks)
        ok = ok and all(masks[i] == 0.0 and values[i] == 0.0
                        for i in ENERGY_DIMS)
        ok = ok and all(masks[i] == 1.0 for i in range(24)
                        if i not in ENERGY_DIMS)
        ok = ok and abs(values[3] - stats["charge_Ah"]) < 1e-9
        ok = ok and abs(values[4] - stats["discharge_Ah"]) < 1e-9
        ok = ok and abs(values[13] - 0.5) < 1e-9
        ok = ok and abs(values[14] - stats["i_discharge_a"]) < 1e-9
        ok = ok and abs(values[15] - 0.5) < 1e-9
        ok = ok and abs(values[16] - stats["i_discharge_a"]) < 1e-9
        ok = ok and abs(values[21] - stats["charge_Ah"]) < 1e-9
        ok = ok and abs(values[22] - 1.0) < 1e-9
        ok = ok and abs(values[23] - (stats["charge_Ah"]
                                      + stats["discharge_Ah"])) < 1e-9
        ok = ok and 0.0 < values[0] < 0.01 and 0.0 < values[1] < 0.01 \
            and 0.0 < values[2] < 0.001  # weeks-scaled durations and gap
        log.record("F01_mapping_completeness", ok)

        # F02 crosscheck discharge counter span == validated capacity ----
        v2, m2 = fragment_control(samples, stats["discharge_Ah"])
        ok = abs(v2[4] - v2[22]) < 1e-9
        v3s, m3s = fragment_control(samples[:60], 1.0)  # rest+charge only
        ok = ok and m3s[0] == 1.0          # charge leg present
        ok = ok and m3s[1] == 0.0          # no discharge leg -> masked
        ok = ok and m3s[4] == 0.0 and m3s[2] == 0.0 and m3s[23] == 0.0
        ok = ok and m3s[3] == 1.0 and m3s[21] == 1.0 and m3s[22] == 1.0
        log.record("F02_leg_absence_masks", ok)

        # F03 observation selection rule ---------------------------------
        audit = ReadAudit()
        got, counts = load_observations(audit, data_root=fx["data"])
        ok = len(got) == 12 and counts["valid_unique"] == 12
        ok = ok and counts["excluded_status"] == 1
        ok = ok and counts["excluded_duplicate_alias"] == 1
        ok = ok and got[0]["source_rpt_index"] == 0
        ok = ok and all(b["stop_epoch"] > a["stop_epoch"]
                        for a, b in zip(got, got[1:]))
        log.record("F03_observation_rule", ok)

        # F14 timezone discipline ----------------------------------------
        e = parse_iso_naive("2010-08-16T17:22:57")
        ok = abs(e - 1281979377.0) < 1e-6  # naive-UTC epoch (independently
        # verified: date -u -d @1281979377 == 2010-08-16T17:22:57Z)
        ok = ok and len(TZ_DISCLOSURE) > 20
        ok = ok and parse_iso_naive("1970-01-01T00:00:00") == 0.0
        log.record("F14_timezone_naive_utc", ok)

        # F15 event bucket ------------------------------------------------
        ev = fx["crossing"]["stop_epoch"]
        ok = ("pre_event" if got[0]["stop_epoch"] < ev else "post_event") \
            == "pre_event"
        ok = ok and ("post_event"
                     if got[-1]["stop_epoch"] >= ev else "pre_event") \
            == "post_event"
        log.record("F15_event_bucket_rule", ok)

        # endpoint loader on synthetic -----------------------------------
        ep = load_endpoint(audit, got, data_root=fx["data"])
        ok = ep["threshold_ah"] == 0.88
        ok = ok and abs(ep["event_epoch"] - ev) < 1e-9
        ok = ok and ep["rul_labels_allowed"] is False
        log.record("F04b_endpoint_loader_integrity", ok)

        # controls for all synthetic observations ------------------------
        meas_index = load_measurements_index(audit, data_root=fx["data"])
        controls, cstats = build_controls(got, meas_index, audit,
                                          data_root=fx["data"])
        ok = len(controls) == 12
        ok = ok and all(cstats["mask_rate_per_dim"][i] == 0.0
                        for i in range(24) if i not in ENERGY_DIMS)
        ok = ok and all(cstats["mask_rate_per_dim"][i] == 1.0
                        for i in ENERGY_DIMS)
        ok = ok and cstats["max_abs_discharge_q_last_minus_capacity_ah"] < 1e-9
        log.record("F05b_controls_all_obs", ok)

        # F06 arm policies ------------------------------------------------
        rows = [{"source_rpt_index": r["source_rpt_index"],
                 "stop_epoch": r["stop_epoch"],
                 "capacityAh": r["capacity_ah"],
                 "arrival_epoch": r["stop_epoch"]} for r in got]
        pol_raw = arm_policy(rows, "raw")
        pol_s2 = arm_policy(rows, "sparse2")
        pol_d7 = arm_policy(rows, "delay7d")
        ok = [int(r["source_rpt_index"]) for r in pol_raw] == list(range(12))
        ok = ok and [int(r["source_rpt_index"]) for r in pol_s2] == \
            [i for i in range(12) if i % 2 == 0]
        ok = ok and 0 in [int(r["source_rpt_index"]) for r in pol_s2]
        ok = ok and all(abs(r["arrival_epoch"] - r["stop_epoch"]
                            - DELAY7D_SECONDS) < 1e-9 for r in pol_d7)
        ok = ok and all(r["arrival_epoch"] == r["stop_epoch"] for r in pol_s2)
        log.record("F06_arm_policies_sparse2_delay7d", ok)

        # F07 sequences (a2_prep.cell_sequence compat) --------------------
        all_rpts = base_rpt_records(rows)
        rpts_s2 = _rpt_records_for_arm(all_rpts, pol_s2)
        seq_s2 = build_arm_sequence(CELL_ID, got, controls, rpts_s2)
        ok = seq_s2["anchor"] is not None
        ok = ok and abs(seq_s2["q_ref_ah"] - got[0]["capacity_ah"]) < 1e-12
        ok = ok and abs(seq_s2["anchor"]["source_epoch"]
                        - got[0]["stop_epoch"]) < 1e-9
        kinds = [e["kind"] for e in seq_s2["events"]]
        ok = ok and kinds.count("cycle") == 12  # dense controls
        ok = ok and kinds.count("rpt") == 5     # even indices except anchor 0
        ok = ok and all(e["kind"] != "rpt" or e["index"] != 0
                        for e in seq_s2["events"])  # anchor not re-applied
        log.record("F07_sequence_anchor_qref_structure", ok)

        # F08 walker == reference re-filter -------------------------------
        # a3_infer discipline: float32 checkpoint state -> float64 filter
        model = a3_model.build_arm_model("full", seed=7).double().eval()
        cfg = ARM_CONFIGS["full"]
        rpts_raw = _rpt_records_for_arm(all_rpts, pol_raw)
        seq_raw = build_arm_sequence(CELL_ID, got, controls, rpts_raw)
        ok = True
        for lag in (0.0, DELAY7D_SECONDS):
            walker = AsOfWalkerA3(model, seq_raw, lag, cfg)
            for e_i in (9, 10, 11):  # q - lag must stay at/after the anchor
                q = got[e_i]["stop_epoch"]
                a = walker.state_at(q)
                b = reference_asof_state_a3(model, seq_raw, q, cfg, lag)
                ok = ok and torch.allclose(a["m"], b["m"], atol=1e-12) \
                    and torch.allclose(a["P"], b["P"], atol=1e-12)
        log.record("F08_walker_matches_reference", ok)

        # F09 query grid + no leakage -------------------------------------
        panel, skips, qref = build_panel(got, controls)
        ok = True
        for arm in QUERY_ARMS:
            entry = panel[arm]
            lag = DELAY7D_SECONDS if arm == "delay7d" else 0.0
            warmup = got[0]["stop_epoch"] + WEEK_SECONDS
            seen_anchor = set()
            for query in entry["queries"]:
                q = query["query_epoch"]
                ok = ok and q >= warmup - 1e-9
                ok = ok and query["target_stop_epoch"] > q + 1e-9
                ok = ok and query["target_source_rpt_index"] == \
                    query["query_source_index"] + 1  # next FULL observation
                vis = [r for r in entry["policy"]
                       if float(r["arrival_epoch"]) <= q + 1e-9]
                ok = ok and query["visible_records"] == len(vis) >= 3
                ok = ok and int(vis[-1]["source_rpt_index"]) \
                    == query["anchor_index"]
                ok = ok and (arm, query["anchor_index"]) not in seen_anchor
                seen_anchor.add((arm, query["anchor_index"]))
        # walker-level leakage probe: n_rpt_used counts exactly the retained
        # RPT events at/before the arm cutoff; delay7d ghosts are excluded
        for arm in QUERY_ARMS:
            entry = panel[arm]
            lag = DELAY7D_SECONDS if arm == "delay7d" else 0.0
            walker = AsOfWalkerA3(model, entry["seq"], lag,
                                  ARM_CONFIGS["full"])
            for e_i in (9, 10, 11):  # q - lag must stay at/after the anchor
                q = got[e_i]["stop_epoch"]
                st = walker.state_at(q)
                n_used = sum(1 for e in entry["seq"]["events"]
                             if e["kind"] == "rpt"
                             and float(e["source_epoch"]) <= q - lag + 1e-9)
                n_late = sum(1 for e in entry["seq"]["events"]
                             if e["kind"] == "rpt"
                             and q - lag + 1e-9 < float(e["source_epoch"])
                             <= q + 1e-9)
                ok = ok and st["n_rpt_used"] == n_used
                ok = ok and st["n_late_arrival_excluded"] == n_late
        log.record("F09_query_grid_no_leakage", ok)

        # F10 equivalence with the ISU build_queries ----------------------
        # (a) with the ISU threshold skip restored, calce_build_queries
        #     reproduces a2_infer.build_queries exactly on the common keys;
        # (b) without the threshold (the CALCE design), the only remaining
        #     delta vs ISU is the dropped targetless final query row.
        pol1 = arm_policy(rows, "raw")
        cell = {"rows": rows}
        keys = ("query_epoch", "anchor_index", "visible_records",
                "visible_source_indices")
        mine_a, _ska = calce_build_queries(rows, "raw", pol1,
                                           warmup_from_index=1,
                                           threshold_skip_ah=0.89)
        isu_a, isu_ska, _why = isu_build_queries(cell, "raw", pol1,
                                                 threshold_ah=0.89)
        ok = len(mine_a) == len(isu_a) == 1
        ok = ok and isu_ska["visible_threshold"] == 3 \
            and _ska["visible_threshold"] == 3
        ok = ok and all(
            all(m[k] == u[k] for k in keys) and
            m["target_source_rpt_index"] == u["next_source_rpt_index"]
            for m, u in zip(mine_a, isu_a))
        mine_b, _skb = calce_build_queries(rows, "raw", pol1,
                                           warmup_from_index=1,
                                           threshold_skip_ah=None)
        isu_b, _skb, _why2 = isu_build_queries(cell, "raw", pol1,
                                               threshold_ah=0.2)
        ok = ok and len(mine_b) == 3 and len(isu_b) == 4
        ok = ok and isu_b[-1]["next_source_rpt_index"] is None
        ok = ok and all(
            all(m[k] == u[k] for k in keys) and
            m["target_source_rpt_index"] == u["next_source_rpt_index"]
            for m, u in zip(mine_b, isu_b))
        log.record("F10_isu_equivalence_with_threshold_warmup1", ok)

        # F11 baselines ----------------------------------------------------
        q = {"visible_caps": [1.0, 0.98, 0.96],
             "visible_stops": [0.0, 7 * 86400.0, 14 * 86400.0],
             "target_stop_epoch": 21 * 86400.0}
        hold = naive_hold_last(q)
        slope = naive_past_slope(q)
        ok = abs(hold - 0.96) < 1e-12
        ok = ok and abs(slope - (0.96 + (-0.02) * 1.0)) < 1e-12
        q2 = {"visible_caps": [1.0], "visible_stops": [0.0],
              "target_stop_epoch": 7 * 86400.0}
        ok = ok and naive_hold_last(q2) == 1.0
        ok = ok and abs(naive_past_slope(q2) - 1.0) < 1e-12  # no pair -> flat
        q3 = {"visible_caps": [1.0, 1.0], "visible_stops": [0.0, 0.0],
              "target_stop_epoch": 7 * 86400.0}  # dt=0 -> slope 0
        ok = ok and abs(naive_past_slope(q3) - 1.0) < 1e-12
        log.record("F11_naive_baselines_handcheck", ok)

        # F12 metrics -------------------------------------------------------
        m = score_pairs([(1.0, 0.9, 0.1), (0.8, 0.9, 0.1)])
        want_nll = 0.5 * (1.0 + 2.0 * math.log(0.1) + math.log(2 * math.pi))
        ok = m["n"] == 2 and abs(m["mae_ah"] - 0.1) < 1e-12
        ok = ok and abs(m["rmse_ah"] - math.sqrt(0.01)) < 1e-12
        ok = ok and abs(m["gaussian_nll"] - want_nll) < 1e-12
        ok = ok and m["cov90"] == 1.0
        m2 = score_pairs([(1.0, 0.9, None)])
        ok = ok and "gaussian_nll" not in m2 and \
            abs(m2["mae_ah"] - 0.1) < 1e-12
        log.record("F12_metrics_closed_form", ok)

        # F13 GO gate: positive path + >=12 refusals ----------------------
        registry = os.path.join(root, "consumed_gos.jsonl")
        out_dir = os.path.join(root, "eval_out")
        go = _synth_go(root, fx, out_dir, registry,
                       "CALCE_ZS_SELFTEST_RUN1")
        binding, probs = validate_calce_go(go, registry_path=registry,
                                           load_models=True)
        ok = not probs and binding is not None and len(binding["models"]) == 3
        if binding:
            for r in binding["read_audit"].paths:
                ok = ok and r.startswith(os.path.realpath(root))

        os.makedirs(os.path.join(root, "stale_out"))
        with open(registry, "w", encoding="utf-8") as f:
            f.write(json.dumps({"request_id": "ALREADY_CONSUMED_X",
                                "go_sha256": "0" * 64,
                                "finished_utc": _utc_now()}) + "\n")

        def refused(name, mutate=None, out_name=None, request_id=None):
            g2 = json.loads(json.dumps(go))
            if mutate is not None:
                mutate(g2)
            if out_name is not None:
                g2["output_dir"] = out_name
            else:
                g2["output_dir"] = os.path.join(root, "refused_" + name)
            g2["receipt_path"] = os.path.join(root, "receipts",
                                              name + "_r.json")
            if request_id is not None:
                g2["request_id"] = request_id
            b, p = validate_calce_go(g2, registry_path=registry,
                                     load_models=True)
            good = b is None and len(p) > 0
            if out_name is None:
                good = good and not os.path.exists(g2["output_dir"])
            return good

        mutations = [
            ("status", lambda g: g.update(status="SUBMITTED"), None, None),
            ("allow_fit_true", lambda g: g.update(allow_fit=True), None, None),
            ("allow_train_true", lambda g: g.update(allow_train=True),
             None, None),
            ("allow_c4_true", lambda g: g.update(allow_C4=True), None, None),
            ("allow_inference_false", lambda g: g.update(allow_inference=False),
             None, None),
            ("scope_no_calce", lambda g: g.update(scope="generic scope"),
             None, None),
            ("estimand_missing", lambda g: g.pop("estimand"), None, None),
            ("estimand_rul_true", lambda g: g["estimand"]
                .update(rul_labels_used=True), None, None),
            ("estimand_quantity", lambda g: g["estimand"]
                .update(quantity="rul_prediction"), None, None),
            ("owner", lambda g: g.update(owner_thread_id="deadbeef"),
             None, None),
            ("device_gpu", lambda g: g.update(device="cuda"), None, None),
            ("no_grad_false", lambda g: g.update(no_grad=False), None, None),
            ("runtime_range", lambda g: g.update(max_runtime_seconds=10),
             None, None),
            ("rss_bad", lambda g: g.update(max_rss_gb=0), None, None),
            ("consumed_request", None, None, "ALREADY_CONSUMED_X"),
            ("code_hash_wrong", lambda g: g["code_sha256"]
                .update({SELF_NAME: "0" * 64}), None, None),
            ("code_hash_missing", lambda g: g["code_sha256"]
                .pop("a2_prep.py"), None, None),
            ("ckpt_missing", lambda g: g["checkpoints"]
                .pop("a3_full_seed43"), None, None),
            ("ckpt_extra", lambda g: g["checkpoints"]
                .update({"a3_full_seed99": g["checkpoints"]
                         ["a3_full_seed42"]}), None, None),
            ("ckpt_sha_wrong", lambda g: g["checkpoints"]["a3_full_seed42"]
                .update(sha256="1" * 64), None, None),
            ("series_sha_wrong", lambda g: g["capacity_series"]
                .update(sha256="2" * 64), None, None),
            ("endpoint_missing", lambda g: g.pop("endpoint_labels"),
             None, None),
            ("gz_count_24", lambda g: g["records_gz"]
                .pop(sorted(g["records_gz"])[0]), None, None),
            ("gz_sha_wrong", lambda g: g["records_gz"]
                [sorted(g["records_gz"])[0]].update(sha256="3" * 64),
             None, None),
            ("out_dir_stale", None, os.path.join(root, "stale_out"), None),
        ]
        n_refused = 0
        for name, mut, out_name, req in mutations:
            n_refused += int(refused(name, mut, out_name, req))
        ok = ok and n_refused == len(mutations) and n_refused >= 12
        log.record("F13_go_gate_refusals_%d_of_%d"
                   % (n_refused, len(mutations)), ok)

        # F17 end-to-end synthetic run + double-consumption refusal -------
        out2 = os.path.join(root, "eval_out")  # already validated fresh
        rc = None
        try:
            go_path = os.path.join(root, "GO_fixture.json")
            with open(go_path, "w", encoding="utf-8") as f:
                json.dump(go, f)
            rc = run_eval(go_path, threads=1, registry_path=registry)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            rc = -1
        ok = rc == 0 and os.path.isfile(os.path.join(out2,
                                                     "predictions_calce.csv"))
        ok = ok and os.path.isfile(os.path.join(out2, "metrics.json"))
        ok = ok and os.path.isfile(os.path.join(root, "receipts",
                                                "CALCE_ZS_SELFTEST_RUN1"
                                                "_receipt.json"))
        if ok:
            with open(registry, encoding="utf-8") as f:
                lines = [json.loads(l) for l in f if l.strip()]
            ok = any(l["request_id"] == "CALCE_ZS_SELFTEST_RUN1"
                     for l in lines)
            with open(os.path.join(out2, "metrics.json"),
                      encoding="utf-8") as f:
                mm = json.load(f)
            ok = ok and mm["estimand"]["quantity"] == \
                ESTIMAND_DECLARATION["quantity"]
            ok = ok and mm["zero_shot"]["fits"] == 0
            ok = ok and mm["panel"]["n_observations"] == 12
            q_by_arm = mm["panel"]["queries_by_arm"]
            ok = ok and all(q_by_arm[a] > 0 for a in QUERY_ARMS)
            fams = set(mm["predictors"])
            ok = ok and set(NAIVE_FAMILIES) <= fams and len(fams) == 5
            # double consumption refused
            rc2 = run_eval(go_path, threads=1, registry_path=registry)
            ok = ok and rc2 == 2
        log.record("F17_end_to_end_synthetic_run", ok)

        # F16 no-payload discipline ---------------------------------------
        ok = all(p.startswith(os.path.realpath(root)) for p in AUDIT.paths)
        ok = ok and not any(p.startswith(real_root) for p in AUDIT.paths)
        ok = ok and not any(p.endswith(".pt") and not
                            p.startswith(os.path.realpath(root))
                            for p in AUDIT.paths)
        log.record("F16_no_payload_no_real_checkpoint", ok)

    elapsed = time.monotonic() - started
    n_pass = sum(1 for _, ok, _ in log.results if ok)
    head = ("[%s] calce_zero_shot.py self-check: %d/%d fixtures PASS "
            "(elapsed %.1fs, torch %s, fixture seed model = synthetic)"
            % (_utc_now(), n_pass, len(log.results), elapsed,
               torch.__version__))
    print(head)
    if append_log:
        parent = os.path.dirname(os.path.abspath(append_log))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(append_log, "a", encoding="utf-8") as f:
            f.write(head + "\n")
            for name, ok, _ in log.results:
                f.write("RESULT %-38s %s\n" % (name, "PASS" if ok else "FAIL"))
    return 0 if n_pass == len(log.results) else 1


# ------------------------------------------------------------------ main
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="CALCE CS2_35 zero-shot capacity-conditioned inference "
                    "(default: synthetic self-check)")
    parser.add_argument("--self-check", action="store_true",
                        default=False, help="run the synthetic self-check")
    parser.add_argument("--append-log", default=None,
                        help="append RESULT lines to this file")
    parser.add_argument("--run-eval", action="store_true", default=False,
                        help="run the GO-gated real evaluation")
    parser.add_argument("--go", default=None, help="GO json path")
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument("--verbose", action="store_true", default=False)
    args = parser.parse_args(argv)
    if args.run_eval:
        if not args.go:
            print("--run-eval requires --go GO.json")
            return 2
        try:
            return run_eval(args.go, threads=args.threads,
                            verbose=args.verbose)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return 3
    if args.go:
        print("--go requires --run-eval (default mode is --self-check)")
        return 2
    return self_check(append_log=args.append_log)


if __name__ == "__main__":
    sys.exit(main())
