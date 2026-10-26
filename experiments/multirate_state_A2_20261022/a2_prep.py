#!/usr/bin/env python3
"""A2 PREP builder: 125 C1/C2 train cells -> one compact npz for a2_train.py.

This module is the only A2 component that is allowed to touch the two reviewed
data sources.  It never trains, never touches an optimiser, never reads a raw
archive, a C3/C4 cell or a checkpoint, and it never consumes a GO.

===========================================================================
1. INPUT CONTRACT (read-only, two sources only)
===========================================================================
  RPT side  data/processed/ISU_ILCC_DataV2_v1/<cell>.json
      {"cell_id","role","group_id","nominal_capacity_ah","baseline_stop",
       "records":[{"source_rpt_index","start","stop","capacityAh","valid",
                   "calendar_age_seconds","capacity_visible_at",
                   "observed_nominal80_endpoint"}, ...]}
      * source clock  = "stop" (ISO-8601)
      * arrival clock = "stop" when capacity_visible_at == "stop" (the frozen
        data-v2 visibility policy: capacity becomes visible exactly at stop).
        A valid row with capacity_visible_at == None has NO known arrival and is
        dropped and counted (never guessed).  An ISO string is honoured if the
        source ever starts emitting a real latency.
      * only valid == True rows with finite capacityAh > 0 are candidates.

  cycle side reports/multisource_20261021_signals/cycling_features_v{3,4}/<cell>.json.gz (manifest-pinned; basename must equal <cell>.json.gz)
      {"cell_id","role","cycles":[{"source_cycle_index","source_visible_at",
        "charge":{"start","stop","Q_sample_stats","V_V_sample_stats",
                  "t_sample_stats","E_sample_stats","I_A_sample_stats"},
        "discharge":{...},
        "capacity_charge_source_units_unknown",
        "capacity_discharge_source_units_unknown",
        "observed_cycle_throughput_source_units"}, ...]}
      * a cycle is "completed" only when BOTH leg stops parse as ISO timestamps;
        completion = max(charge.stop, discharge.stop) = the only clock available
        (communication arrival of cycling records is unobserved, see the asset's
        own time_basis field).  source == available == completion.
      * every sample_stats object is {n, finite_n, first, last, min, max, mean}
        (or None).  No level-0 arrays, no cumulative counters: each cycle is
        turned into its own control vector, so a later record can never change
        an earlier one.

===========================================================================
2. THE 24-DIM CONTROL TABLE (fixed order, units, source, missing rule)
===========================================================================
  idx  name                          unit    source (per cycle record)
  ---  ----------------------------  ------  -------------------------------
   0   dur_charge_weeks              week    charge.stop - charge.start
   1   dur_discharge_weeks           week    discharge.stop - discharge.start
   2   gap_charge_discharge_weeks    week    discharge.start - charge.stop
   3   q_last_charge_ah              Ah      charge.Q_sample_stats.last
   4   q_last_discharge_ah           Ah      discharge.Q_sample_stats.last
   5   q_mean_charge_ah              Ah      charge.Q_sample_stats.mean
   6   q_mean_discharge_ah           Ah      discharge.Q_sample_stats.mean
   7   q_span_charge_ah              Ah      charge.Q: max - min
   8   q_span_discharge_ah           Ah      discharge.Q: max - min
   9   v_mean_charge_v               V       charge.V_V_sample_stats.mean
  10   v_mean_discharge_v            V       discharge.V_V_sample_stats.mean
  11   v_last_charge_v               V       charge.V_V_sample_stats.last
  12   v_last_discharge_v            V       discharge.V_V_sample_stats.last
  13   i_mean_abs_charge_a           A       charge.I_A_sample_stats (see below)
  14   i_mean_abs_discharge_a        A       discharge.I_A_sample_stats
  15   i_max_abs_charge_a            A       max(|min|,|max|) of charge I
  16   i_max_abs_discharge_a         A       max(|min|,|max|) of discharge I
  17   e_last_charge_wh              Wh      charge.E_sample_stats.last
  18   e_last_discharge_wh           Wh      discharge.E_sample_stats.last
  19   e_mean_charge_wh              Wh      charge.E_sample_stats.mean
  20   e_mean_discharge_wh           Wh      discharge.E_sample_stats.mean
  21   capacity_charge_ah            Ah      capacity_charge_source_units_unknown
  22   capacity_discharge_ah         Ah      capacity_discharge_source_units_unknown
  23   throughput_ah                 Ah      observed_cycle_throughput_source_units

  |I| rule (no sign convention is claimed by the source): if min and max are both
  finite and straddle zero, mean|I| = 0.5*(|min|+|max|) (a bounded estimate);
  otherwise |mean| when mean is finite; otherwise max(|min|,|max|).  This is an
  estimate of the current magnitude, not a coulomb count.

  MISSING RULE: a field is present (mask = 1.0) iff its raw statistic exists and
  is finite, and the derived value is finite and physically admissible (duration
  and gap must be >= 0; capacity/throughput must be >= 0; span must be >= 0).
  Anything else -> value = 0.0 AND mask = 0.0 (explicit joint zero, no imputation,
  no carry-forward, no interpolation).  A legitimate measured zero keeps mask 1.0.
  The mask never disagrees with the value: mask==0 implies value==0.0 exactly.

  Deliberately NOT in the vector: cumulative cycle counts, cumulative throughput,
  hours-since-last-completion, calendar age, temperatures (t_sample_stats unit is
  not declared by the source) and any history-dependent term.  Those would make a
  cycle's control depend on other records, which breaks the as-of contract.

===========================================================================
3. ANCHOR / AS-OF RULE (delegated to a2_targets.build_cell_sequence)
===========================================================================
  * Q_ref = capacity of the valid arrived RPT with the EARLIEST ARRIVAL at/before
    the cutoff (ties: source stop, then record index).  Its source stop is the
    time origin.
  * pre-anchor records (source stop < origin) are excluded and counted, even when
    they arrive later (no negative-time propagation).
  * as-of gating requires source <= query AND arrival <= query; a record with
    source <= query < arrival is excluded and counted.
  * the anchor reading defines Q_ref and is never scored again; every other
    arrived post-anchor RPT is scored (score=True), so the noRPTupdate arm still
    predicts and scores every RPT -- it simply never applies the update.
  * cutoff: default "full_history" (cutoff_epoch = None) because these are
    training cells with no query.  An explicit cutoff is accepted from the GO
    and is then enforced by the same replay contract.

===========================================================================
4. GO CONTRACT (PREP-only; all fields are mandatory unless marked optional)
===========================================================================
  {"status": "APPROVED",                  # or approval_status
   "allow_prep": true,
   "allow_fit": false,                    # must be explicitly false
   "scope": "... A2 ... PREP ...",        # must name A2 and PREP
   "code_sha256": {"a2_prep.py": "<sha>", "a2_model.py": "<sha>",
                   "a2_targets.py": "<sha>", "a2_train.py": "<sha>"},
   "processed_manifest": {"path": ".../processed_manifest.json", "sha256": "<sha>"},
   "cycling_manifest":   {"path": ".../cycling_all188_feature_manifest.json",
                          "sha256": "<sha>"},
   "output_dir": "<absolute fresh directory>",
   "receipt_path": "<absolute path that must not exist yet>",
   # optional, validated when present:
   "expected_cell_count": 125, "n_val_cells": 25, "split_seed": 42,
   "cutoff_policy": "full_history" | "explicit_epoch", "cutoff_epoch": <float|ISO>,
   "max_events": <int>, "expires_utc": "<ISO>",
   "raw_archive_reads_allowed": false, "C3_reads_allowed": false,
   "C4_reads_allowed": false, "max_fits": 0}

  Flat aliases processed_manifest_path/processed_manifest_sha256 and
  cycling_manifest_path/cycling_manifest_sha256 are accepted too.

  Refusal is total: a rejected GO produces no output directory, no npz, no
  manifest, no receipt, and exit code != 0.  The receipt that a successful run
  writes records the run only; it carries "consumes_go": false and never writes
  "consumed_at" -- consumption stays with the controller.

===========================================================================
5. OUTPUT
===========================================================================
  <output_dir>/a2_prep_sequences.npz   exact keys a2_train.load_prepared_sequences
                                       reads: cell_ids[N]<U, q_ref_ah[N] f64,
                                       anchor_source_epoch[N] f64,
                                       event_cell[E] i8, event_kind[E] i8,
                                       event_source[E] f64, event_available[E] f64,
                                       event_dt_weeks[E] f32, control[E,24] f32,
                                       control_mask[E,24] f32, capacity_ah[E] f32,
                                       score[E] bool
  <output_dir>/manifest.json           npz path + sha256 + counts + split + reads
  <receipt_path>                       run receipt (written last, never consuming)

Default behaviour with no arguments is --self-check: the whole build pipeline runs
on fabricated records in a temporary directory (0 payload reads, 0 fits) and every
assertion is printed.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np

from a2_targets import (
    CONTROL_DIM,
    WEEK_SECONDS,
    TrainControlStandardizer,
    build_cell_sequence,
    epoch_seconds,
    hash_file,
    split_cells_by_hash,
)

DEFAULT_ROOT = "/home/yndx/zxk/rul"
SCHEMA = "A2_PREP_V1"
NPZ_NAME = "a2_prep_sequences.npz"
MANIFEST_NAME = "manifest.json"
REQUIRED_CODE = ("a2_prep.py", "a2_model.py", "a2_targets.py", "a2_train.py")

CONTROL_FIELDS = (
    ("dur_charge_weeks", "weeks"),
    ("dur_discharge_weeks", "weeks"),
    ("gap_charge_discharge_weeks", "weeks"),
    ("q_last_charge_ah", "Ah"),
    ("q_last_discharge_ah", "Ah"),
    ("q_mean_charge_ah", "Ah"),
    ("q_mean_discharge_ah", "Ah"),
    ("q_span_charge_ah", "Ah"),
    ("q_span_discharge_ah", "Ah"),
    ("v_mean_charge_v", "V"),
    ("v_mean_discharge_v", "V"),
    ("v_last_charge_v", "V"),
    ("v_last_discharge_v", "V"),
    ("i_mean_abs_charge_a", "A"),
    ("i_mean_abs_discharge_a", "A"),
    ("i_max_abs_charge_a", "A"),
    ("i_max_abs_discharge_a", "A"),
    ("e_last_charge_wh", "Wh"),
    ("e_last_discharge_wh", "Wh"),
    ("e_mean_charge_wh", "Wh"),
    ("e_mean_discharge_wh", "Wh"),
    ("capacity_charge_ah", "Ah"),
    ("capacity_discharge_ah", "Ah"),
    ("throughput_ah", "Ah"),
)
assert len(CONTROL_FIELDS) == CONTROL_DIM == 24
assert len({n for n, _ in CONTROL_FIELDS}) == 24

CONTROL_MISSING_RULE = (
    "field present (mask=1) iff its raw statistic exists and is finite and the "
    "derived value is finite and admissible (durations/gaps/spans >= 0, "
    "capacities/throughput >= 0); otherwise value=0.0 and mask=0.0 exactly "
    "(no imputation, no carry-forward, no interpolation)"
)

NPZ_KEYS = (
    "cell_ids", "q_ref_ah", "anchor_source_epoch", "event_cell", "event_kind",
    "event_source", "event_available", "event_dt_weeks", "control",
    "control_mask", "capacity_ah", "score",
)


class PrepError(RuntimeError):
    """Any refusal or schema violation in the PREP build path."""


# --------------------------------------------------------------- small helpers
def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _finite(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)))


def _finite_or_none(value):
    return float(value) if _finite(value) else None


def _iso_or_none(value):
    if value is None:
        return None
    if _finite(value):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text in ("[]", "null", "None", "nan"):
        return None
    try:
        return float(epoch_seconds(text))
    except (ValueError, TypeError, OverflowError):
        return None


def _json_safe(obj):
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return v if math.isfinite(v) else None
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    return obj


def _sha256_bytes(blob):
    return hashlib.sha256(blob).hexdigest()


class PrepEnv(object):
    """Filesystem facts: where the two sources live and what may be read."""

    def __init__(self, root, processed_root, cycling_root, processed_manifest,
                 cycling_manifest, read_roots=None):
        self.root = os.path.realpath(root)
        self.processed_root = os.path.realpath(processed_root)
        self.cycling_root = os.path.realpath(cycling_root)
        self.processed_manifest = os.path.abspath(processed_manifest)
        self.cycling_manifest = os.path.abspath(cycling_manifest)
        roots = list(read_roots or [])
        roots += [HERE, self.processed_root, self.cycling_root,
                  os.path.dirname(self.processed_manifest),
                  os.path.dirname(self.cycling_manifest)]
        self.read_roots = []
        for r in roots:
            real = os.path.realpath(r)
            if real not in self.read_roots:
                self.read_roots.append(real)
        self.bytes_read = 0
        self.files_read = 0

    def permit_read_roots(self, *paths):
        for p in paths:
            if not p:
                continue
            real = os.path.realpath(p)
            if real not in self.read_roots:
                self.read_roots.append(real)

    def _allowed(self, real):
        for r in self.read_roots:
            if real == r or real.startswith(r + os.sep):
                return True
        return False

    def read_bytes(self, path, what):
        real = os.path.realpath(path)
        if not self._allowed(real):
            raise PrepError("%s is outside the GO-pinned read roots: %s" % (what, path))
        low = real.lower()
        if os.sep + "raw" + os.sep in low or low.endswith((".pt", ".pth", ".ckpt")):
            raise PrepError("%s points at a forbidden payload/checkpoint: %s" % (what, path))
        if not os.path.isfile(real):
            raise PrepError("%s is not a regular file: %s" % (what, path))
        with open(real, "rb") as fh:
            blob = fh.read()
        self.bytes_read += len(blob)
        self.files_read += 1
        return blob

    def read_json(self, path, what):
        blob = self.read_bytes(path, what)
        try:
            return json.loads(blob.decode("utf-8")), _sha256_bytes(blob)
        except (UnicodeDecodeError, ValueError) as exc:
            raise PrepError("%s is not readable JSON: %s" % (what, exc))


def default_env():
    root = os.environ.get("A2_PREP_ROOT", DEFAULT_ROOT)
    return PrepEnv(
        root=root,
        processed_root=os.path.join(root, "data", "processed", "ISU_ILCC_DataV2_v1"),
        cycling_root=os.path.join(root, "reports", "multisource_20261021_signals",
                                  "cycling_features_v3"),
        processed_manifest=os.path.join(
            root, "experiments", "trajectory_b2_joint_marked_renewal_20261021",
            "candidate_v2", "prep_inputs", "processed_manifest.json"),
        cycling_manifest=os.path.join(
            root, "reports", "multisource_20261021_signals",
            "cycling_all188_feature_manifest.json"),
    )


# ------------------------------------------------------------- 24-dim control
def _stat(leg, name, key):
    if not isinstance(leg, dict):
        return None
    stats = leg.get(name)
    if not isinstance(stats, dict):
        return None
    return _finite_or_none(stats.get(key))


def _leg_duration_weeks(leg):
    if not isinstance(leg, dict):
        return None
    start = _iso_or_none(leg.get("start"))
    stop = _iso_or_none(leg.get("stop"))
    if start is None or stop is None:
        return None
    dur = (stop - start) / WEEK_SECONDS
    return dur if dur >= 0.0 else None


def _leg_gap_weeks(first_leg, second_leg):
    if not isinstance(first_leg, dict) or not isinstance(second_leg, dict):
        return None
    a = _iso_or_none(first_leg.get("stop"))
    b = _iso_or_none(second_leg.get("start"))
    if a is None or b is None:
        return None
    gap = (b - a) / WEEK_SECONDS
    return gap if gap >= 0.0 else None


def _span(leg, name):
    if not isinstance(leg, dict):
        return None
    stats = leg.get(name)
    if not isinstance(stats, dict):
        return None
    lo = _finite_or_none(stats.get("min"))
    hi = _finite_or_none(stats.get("max"))
    if lo is None or hi is None:
        return None
    span = hi - lo
    return span if span >= 0.0 else None


def _mean_abs(stats):
    if not isinstance(stats, dict):
        return None
    mean = _finite_or_none(stats.get("mean"))
    lo = _finite_or_none(stats.get("min"))
    hi = _finite_or_none(stats.get("max"))
    if lo is not None and hi is not None and lo < 0.0 < hi:
        return 0.5 * (abs(lo) + abs(hi))
    if mean is not None:
        return abs(mean)
    if lo is not None and hi is not None:
        return max(abs(lo), abs(hi))
    return None


def _max_abs(stats):
    if not isinstance(stats, dict):
        return None
    lo = _finite_or_none(stats.get("min"))
    hi = _finite_or_none(stats.get("max"))
    if lo is None and hi is None:
        return None
    cand = [abs(v) for v in (lo, hi) if v is not None]
    return max(cand)


def _nonneg(value):
    v = _finite_or_none(value)
    return v if (v is not None and v >= 0.0) else None


def cycle_control(row):
    """Turn ONE completed cycle record into its 24 control values and 24 masks.

    Every number comes from this record alone (no cumulative counter, no history,
    no reference to any other cycle), so appending a later record can never change
    an earlier control row.  Missing statistics become value=0.0 with mask=0.0.
    """
    if not isinstance(row, dict):
        raise PrepError("cycle row is not an object")
    charge = row.get("charge")
    discharge = row.get("discharge")
    ci = charge.get("I_A_sample_stats") if isinstance(charge, dict) else None
    di = discharge.get("I_A_sample_stats") if isinstance(discharge, dict) else None
    raw = (
        _leg_duration_weeks(charge),                      # 0
        _leg_duration_weeks(discharge),                   # 1
        _leg_gap_weeks(charge, discharge),                # 2
        _stat(charge, "Q_sample_stats", "last"),          # 3
        _stat(discharge, "Q_sample_stats", "last"),       # 4
        _stat(charge, "Q_sample_stats", "mean"),          # 5
        _stat(discharge, "Q_sample_stats", "mean"),       # 6
        _span(charge, "Q_sample_stats"),                  # 7
        _span(discharge, "Q_sample_stats"),               # 8
        _stat(charge, "V_V_sample_stats", "mean"),        # 9
        _stat(discharge, "V_V_sample_stats", "mean"),     # 10
        _stat(charge, "V_V_sample_stats", "last"),        # 11
        _stat(discharge, "V_V_sample_stats", "last"),     # 12
        _mean_abs(ci),                                    # 13
        _mean_abs(di),                                    # 14
        _max_abs(ci),                                     # 15
        _max_abs(di),                                     # 16
        _stat(charge, "E_sample_stats", "last"),          # 17
        _stat(discharge, "E_sample_stats", "last"),       # 18
        _stat(charge, "E_sample_stats", "mean"),          # 19
        _stat(discharge, "E_sample_stats", "mean"),       # 20
        _nonneg(row.get("capacity_charge_source_units_unknown")),     # 21
        _nonneg(row.get("capacity_discharge_source_units_unknown")),  # 22
        _nonneg(row.get("observed_cycle_throughput_source_units")),   # 23
    )
    values = []
    mask = []
    for v in raw:
        if v is None or not math.isfinite(v):
            values.append(0.0)
            mask.append(0.0)
        else:
            values.append(float(v))
            mask.append(1.0)
    if len(values) != CONTROL_DIM:
        raise PrepError("control vector has %d values, expected %d"
                        % (len(values), CONTROL_DIM))
    return values, mask


def cycle_completion_epoch(row):
    """max(charge.stop, discharge.stop) or None.

    Mirrors reports/multisource_20261021_signals/cycle_asof_features.py
    ::safe_cycle_completion (both leg stops must parse).  Re-implemented here so
    the A2 directory stays self-contained and never imports a reports/ script.
    """
    if not isinstance(row, dict):
        return None
    charge = row.get("charge")
    discharge = row.get("discharge")
    if not isinstance(charge, dict) or not isinstance(discharge, dict):
        return None
    a = _iso_or_none(charge.get("stop"))
    b = _iso_or_none(discharge.get("stop"))
    if a is None or b is None:
        return None
    return max(float(a), float(b))


# ----------------------------------------------------- source record adapters
def rpt_records_from_processed(payload, cell_id):
    """processed cell JSON -> a2_targets rpt records + counters."""
    if not isinstance(payload, dict):
        raise PrepError("processed cell %s is not an object" % cell_id)
    if str(payload.get("cell_id")) != str(cell_id):
        raise PrepError("processed cell identity mismatch: %r != %r"
                        % (payload.get("cell_id"), cell_id))
    if str(payload.get("role")) != "train":
        raise PrepError("processed cell %s has role %r, only train is allowed"
                        % (cell_id, payload.get("role")))
    rows = payload.get("records")
    if not isinstance(rows, list) or not rows:
        raise PrepError("processed cell %s has no records" % cell_id)
    counters = {
        "rpt_rows": len(rows),
        "rpt_invalid_skipped": 0,
        "rpt_bad_capacity_skipped": 0,
        "rpt_missing_stop_skipped": 0,
        "rpt_unknown_availability_skipped": 0,
        "rpt_arrival_from_stop_policy": 0,
        "rpt_arrival_explicit": 0,
    }
    out = []
    for raw in rows:
        if not isinstance(raw, dict):
            raise PrepError("processed cell %s has a non-object record" % cell_id)
        valid = raw.get("valid") is True
        if not valid:
            counters["rpt_invalid_skipped"] += 1
            continue
        cap = _finite_or_none(raw.get("capacityAh"))
        if cap is None or cap <= 0.0:
            counters["rpt_bad_capacity_skipped"] += 1
            continue
        stop = _iso_or_none(raw.get("stop"))
        if stop is None:
            counters["rpt_missing_stop_skipped"] += 1
            continue
        visible = raw.get("capacity_visible_at")
        if isinstance(visible, str) and visible.strip() == "stop":
            arrived = stop
            counters["rpt_arrival_from_stop_policy"] += 1
        elif isinstance(visible, str):
            arrived = _iso_or_none(visible)
            if arrived is None:
                counters["rpt_unknown_availability_skipped"] += 1
                continue
            counters["rpt_arrival_explicit"] += 1
        elif visible is None:
            counters["rpt_unknown_availability_skipped"] += 1
            continue
        else:
            raise PrepError("processed cell %s has an unrecognised "
                            "capacity_visible_at %r" % (cell_id, visible))
        if arrived < stop:
            raise PrepError("processed cell %s has an RPT arrival before its stop"
                            % cell_id)
        out.append({
            "source_epoch": float(stop),
            "available_epoch": float(arrived),
            "capacity_ah": float(cap),
            "valid": True,
            "source_rpt_index": raw.get("source_rpt_index"),
        })
    return out, counters


def cycle_records_from_features(doc, cell_id):
    """cycling feature asset -> a2_targets cycle records + counters."""
    if not isinstance(doc, dict):
        raise PrepError("cycling asset %s is not an object" % cell_id)
    if str(doc.get("cell_id")) != str(cell_id):
        raise PrepError("cycling asset identity mismatch: %r != %r"
                        % (doc.get("cell_id"), cell_id))
    if str(doc.get("role")) != "train":
        raise PrepError("cycling asset %s has role %r, only train is allowed"
                        % (cell_id, doc.get("role")))
    rows = doc.get("cycles")
    if not isinstance(rows, list):
        raise PrepError("cycling asset %s has no cycles list" % cell_id)
    counters = {
        "cycle_rows": len(rows),
        "cycle_no_clock_skipped": 0,
        "cycle_masked_fields": 0,
    }
    out = []
    for row in rows:
        done = cycle_completion_epoch(row)
        if done is None:
            counters["cycle_no_clock_skipped"] += 1
            continue
        values, mask = cycle_control(row)
        counters["cycle_masked_fields"] += int(sum(1 for m in mask if m == 0.0))
        out.append({
            "source_epoch": float(done),
            "available_epoch": float(done),
            "control": values,
            "control_mask": mask,
            "source_cycle_index": row.get("source_cycle_index"),
        })
    return out, counters


# ----------------------------------------------------------- per-cell sequence
def cell_sequence(cell_id, cycle_records, rpt_records, cutoff_epoch=None):
    """a2_targets.build_cell_sequence + control/vector audits."""
    seq = build_cell_sequence(cell_id, cycle_records, rpt_records,
                              cutoff_epoch=cutoff_epoch,
                              assume_cycle_arrival_equal_source=False)
    for event in seq["events"]:
        if event["kind"] != "cycle":
            continue
        ctl = event["control"]
        msk = event["control_mask"]
        if len(ctl) != CONTROL_DIM or len(msk) != CONTROL_DIM:
            raise PrepError("cell %s emitted a control of wrong width" % cell_id)
        for v, m in zip(ctl, msk):
            if not math.isfinite(float(v)) or not math.isfinite(float(m)):
                raise PrepError("cell %s emitted a non-finite control value" % cell_id)
            if m not in (0.0, 1.0):
                raise PrepError("cell %s emitted mask=%r" % (cell_id, m))
            if m == 0.0 and float(v) != 0.0:
                raise PrepError("cell %s emitted value!=0 on a masked field" % cell_id)
    return seq


def _flatten(seq):
    """-> dict of per-cell np arrays (no padding)."""
    n = len(seq["events"])
    kind = np.zeros(n, dtype=np.int8)
    src = np.zeros(n, dtype=np.float64)
    avail = np.zeros(n, dtype=np.float64)
    dt = np.zeros(n, dtype=np.float32)
    ctl = np.zeros((n, CONTROL_DIM), dtype=np.float32)
    msk = np.zeros((n, CONTROL_DIM), dtype=np.float32)
    cap = np.zeros(n, dtype=np.float32)
    score = np.zeros(n, dtype=bool)
    for i, event in enumerate(seq["events"]):
        src[i] = float(event["source_epoch"])
        avail[i] = float(event["available_epoch"])
        dt[i] = float(event["dt_weeks"])
        if event["kind"] == "cycle":
            kind[i] = 1
            ctl[i, :] = np.asarray(event["control"], dtype=np.float32)
            msk[i, :] = np.asarray(event["control_mask"], dtype=np.float32)
        else:
            kind[i] = 2
            cap[i] = float(event["capacity_ah"])
            score[i] = bool(event.get("score", False))
    return {"kind": kind, "source": src, "available": avail, "dt": dt,
            "control": ctl, "control_mask": msk, "capacity_ah": cap,
            "score": score}


# -------------------------------------------------------------------- GO gate
def _go_path_sha(go, name):
    """Accept {"path","sha256"}, {"<name>_path","<name>_sha256"} and nested."""
    node = go.get(name)
    if isinstance(node, dict):
        return node.get("path"), node.get("sha256")
    return go.get(name + "_path"), go.get(name + "_sha256")


def _check_abs(path, label, problems):
    if not path:
        problems.append("%s is missing from the GO" % label)
        return None
    if not isinstance(path, str) or not os.path.isabs(path):
        problems.append("%s must be an absolute path, got %r" % (label, path))
        return None
    return path


def _check_fresh_dir(path, label, problems):
    real = os.path.realpath(path)
    if os.path.exists(real):
        if not os.path.isdir(real):
            problems.append("%s exists and is not a directory: %s" % (label, real))
            return None
        if os.listdir(real):
            problems.append("%s must be a fresh/empty directory: %s" % (label, real))
            return None
    parent = os.path.dirname(real)
    if not os.path.isdir(parent):
        problems.append("%s parent directory does not exist: %s" % (label, parent))
        return None
    return real


def validate_prep_go(go_path, env):
    """Return (problems, go, binding).  Never writes, never consumes."""
    problems = []
    if not go_path:
        return ["no --go supplied; PREP requires an APPROVED PREP-only GO"], None, None
    if not os.path.isfile(go_path):
        return ["GO file not found: %r" % (go_path,)], None, None
    try:
        with open(go_path, "r", encoding="utf-8") as fh:
            go = json.load(fh)
    except (OSError, ValueError) as exc:
        return ["GO is not readable JSON: %s" % exc], None, None
    if not isinstance(go, dict):
        return ["GO must be a JSON object"], None, None

    status = str(go.get("status", go.get("approval_status", ""))).strip().upper()
    if status != "APPROVED":
        problems.append("GO status is %r, not APPROVED" % status)
    if go.get("allow_prep") is not True:
        problems.append("GO must set allow_prep=true")
    if go.get("allow_fit") is not False:
        problems.append("GO must set allow_fit=false explicitly (got %r)"
                        % (go.get("allow_fit"),))
    if go.get("allow_train") is True:
        problems.append("GO must not authorise training (allow_train=true)")
    max_fits = go.get("max_fits")
    if max_fits is not None and int(max_fits) != 0:
        problems.append("GO max_fits must be 0 for PREP, got %r" % (max_fits,))
    for key in ("consumed_at", "consumed", "consumed_utc", "consumed_by"):
        if go.get(key):
            problems.append("GO already consumed (%s)" % key)
    scope = " ".join(str(go.get(k, "")) for k in
                     ("scope", "task", "purpose", "allowed_scope", "title")).upper()
    if "A2" not in scope:
        problems.append("GO scope does not name A2")
    if "PREP" not in scope:
        problems.append("GO scope does not name PREP")
    expires = go.get("expires_utc") or go.get("not_after")
    if expires:
        try:
            if epoch_seconds(expires) < time.time() - 1.0:
                problems.append("GO expired at %s" % expires)
        except (ValueError, TypeError):
            problems.append("GO expires_utc is not a timestamp: %r" % (expires,))

    code = go.get("code_sha256") or go.get("code_hashes")
    if not isinstance(code, dict) or not code:
        problems.append("GO must bind code_sha256 for %s"
                        % ", ".join(REQUIRED_CODE))
    else:
        lowered = {str(k).lower(): v for k, v in code.items()}
        for name in REQUIRED_CODE:
            if name not in lowered and name.lower() not in lowered:
                problems.append("GO code_sha256 does not pin %s" % name)
                continue
            expected = lowered.get(name, lowered.get(name.lower()))
            path = os.path.join(HERE, name)
            if not os.path.isfile(path):
                problems.append("missing code file %s" % path)
                continue
            got = hash_file(path)
            if str(expected).strip().lower() != got.lower():
                problems.append("code_sha256 mismatch for %s: go=%s actual=%s"
                                % (name, expected, got))
        for name in code:
            base = os.path.basename(str(name))
            if base not in REQUIRED_CODE and not os.path.isfile(os.path.join(HERE, base)):
                problems.append("GO pins an unknown code file %r" % (name,))

    pm_path, pm_sha = _go_path_sha(go, "processed_manifest")
    cm_path, cm_sha = _go_path_sha(go, "cycling_manifest")
    pm_real = _check_abs(pm_path, "processed_manifest.path", problems)
    cm_real = _check_abs(cm_path, "cycling_manifest.path", problems)
    for label, path, expected in (("processed_manifest", pm_real, pm_sha),
                                  ("cycling_manifest", cm_real, cm_sha)):
        if not path:
            continue
        if not os.path.isfile(path):
            problems.append("%s not found: %s" % (label, path))
            continue
        if not expected:
            problems.append("GO must pin %s.sha256" % label)
            continue
        got = hash_file(path)
        if str(expected).strip().lower() != got.lower():
            problems.append("%s sha256 mismatch: go=%s actual=%s"
                            % (label, expected, got))

    out_dir = _check_abs(go.get("output_dir"), "output_dir", problems)
    if out_dir:
        out_dir = _check_fresh_dir(out_dir, "output_dir", problems)
    receipt = _check_abs(go.get("receipt_path"), "receipt_path", problems)
    if receipt:
        if os.path.exists(receipt):
            problems.append("receipt_path already exists (refuse to overwrite): %s"
                            % receipt)
        if not os.path.isdir(os.path.dirname(os.path.realpath(receipt))):
            problems.append("receipt_path parent directory does not exist: %s"
                            % receipt)
    for label, path in (("output_dir", out_dir), ("receipt_path", receipt)):
        if not path:
            continue
        real = os.path.realpath(path)
        for root_label, root in (("processed data root", env.processed_root),
                                 ("cycling feature root", env.cycling_root)):
            if real == root or real.startswith(root + os.sep):
                problems.append("%s must not be inside the read-only %s: %s"
                                % (label, root_label, real))

    for flag in ("raw_archive_reads_allowed", "C3_reads_allowed", "C4_reads_allowed"):
        if go.get(flag) is True:
            problems.append("GO sets %s=true; PREP never reads those" % flag)

    expected_cells = go.get("expected_cell_count", 125)
    try:
        expected_cells = int(expected_cells)
    except (TypeError, ValueError):
        problems.append("expected_cell_count must be an integer")
        expected_cells = None
    if expected_cells is not None and expected_cells <= 0:
        problems.append("expected_cell_count must be positive")
    n_val = go.get("n_val_cells", 25)
    try:
        n_val = int(n_val)
    except (TypeError, ValueError):
        problems.append("n_val_cells must be an integer")
        n_val = None
    seed = go.get("split_seed", 42)
    try:
        seed = int(seed)
    except (TypeError, ValueError):
        problems.append("split_seed must be an integer")
        seed = None

    cutoff_policy = str(go.get("cutoff_policy", "full_history")).strip().lower()
    cutoff_epoch = None
    if cutoff_policy == "full_history":
        cutoff_epoch = None
    elif cutoff_policy == "explicit_epoch":
        raw = go.get("cutoff_epoch")
        if raw is None:
            problems.append("cutoff_policy=explicit_epoch requires cutoff_epoch")
        else:
            try:
                cutoff_epoch = float(epoch_seconds(raw))
            except (ValueError, TypeError):
                problems.append("cutoff_epoch is not a timestamp: %r" % (raw,))
    else:
        problems.append("cutoff_policy must be full_history or explicit_epoch, got %r"
                        % (cutoff_policy,))

    if problems:
        return problems, go, None
    binding = {
        "go_path": os.path.abspath(go_path),
        "go_sha256": hash_file(go_path),
        "go_status": status,
        "processed_manifest": os.path.abspath(pm_real),
        "processed_manifest_sha256": str(pm_sha).strip().lower(),
        "cycling_manifest": os.path.abspath(cm_real),
        "cycling_manifest_sha256": str(cm_sha).strip().lower(),
        "output_dir": os.path.realpath(out_dir),
        "receipt_path": os.path.abspath(receipt),
        "expected_cell_count": expected_cells,
        "n_val_cells": n_val,
        "split_seed": seed,
        "cutoff_policy": cutoff_policy,
        "cutoff_epoch": cutoff_epoch,
        "max_events": go.get("max_events"),
    }
    return [], go, binding


# --------------------------------------------------------------- build + write
def _cell_ids_from_assets(processed_doc, cycling_doc, env, binding, out):
    """Validate both manifests and return the ordered (cell, path, sha) triples."""
    if not isinstance(processed_doc, dict):
        raise PrepError("processed manifest is not an object")
    if processed_doc.get("raw_archive_reads_allowed") is not False:
        raise PrepError("processed manifest does not forbid raw archive reads")
    if processed_doc.get("C3_reads_allowed") is not False:
        raise PrepError("processed manifest does not forbid C3 reads")
    if processed_doc.get("C4_reads_allowed") is not False:
        raise PrepError("processed manifest does not forbid C4 reads")
    assets = processed_doc.get("assets")
    if not isinstance(assets, list) or not assets:
        raise PrepError("processed manifest has no assets list")
    if str(processed_doc.get("manifest_type", "")) != "processed_datav2_train_cells_v1":
        raise PrepError("unexpected processed manifest_type %r"
                        % (processed_doc.get("manifest_type"),))
    if not isinstance(cycling_doc, dict):
        raise PrepError("cycling manifest is not an object")
    if str(cycling_doc.get("status", "")).upper() != "SUCCESS":
        raise PrepError("cycling manifest status is %r" % (cycling_doc.get("status"),))
    if int(cycling_doc.get("C4", 0) or 0) != 0:
        raise PrepError("cycling manifest reports C4 cells")
    inventory = cycling_doc.get("inventory")
    if not isinstance(inventory, list) or not inventory:
        raise PrepError("cycling manifest has no inventory list")
    cyc_by_cell = {}
    for entry in inventory:
        cid = str(entry.get("cell_id"))
        if cid in cyc_by_cell:
            raise PrepError("cycling manifest lists %s twice" % cid)
        cyc_by_cell[cid] = entry

    train, seen = [], set()
    for entry in assets:
        cid = str(entry.get("cell_id"))
        role = str(entry.get("role"))
        if role != "train":
            raise PrepError("processed manifest asset %s has role %r" % (cid, role))
        if cid.endswith("C3") or cid.endswith("C4"):
            raise PrepError("asset %s is a C3/C4 cell; PREP must never touch it" % cid)
        if cid in seen:
            raise PrepError("processed manifest lists %s twice" % cid)
        seen.add(cid)
        path = entry.get("path")
        if not isinstance(path, str) or not os.path.isabs(path):
            raise PrepError("asset %s has no absolute path" % cid)
        real = os.path.realpath(path)
        root = env.processed_root
        if not real.startswith(root + os.sep):
            raise PrepError("asset %s lives outside %s: %s" % (cid, root, path))
        if os.path.basename(real) != cid + ".json":
            raise PrepError("asset %s path does not match its cell id: %s" % (cid, path))
        sha = entry.get("sha256")
        if not isinstance(sha, str) or len(sha) != 64:
            raise PrepError("asset %s has no sha256" % cid)
        cyc = cyc_by_cell.get(cid)
        if cyc is None:
            raise PrepError("cycling manifest has no entry for %s" % cid)
        if str(cyc.get("role")) != "train":
            raise PrepError("cycling entry %s has role %r" % (cid, cyc.get("role")))
        cpath = cyc.get("path")
        if not isinstance(cpath, str):
            raise PrepError("cycling entry %s has no path" % cid)
        if not os.path.isabs(cpath):
            cpath = os.path.join(env.root, cpath)
        creal = os.path.realpath(cpath)
        _cdir = os.path.dirname(creal)
        _ok_signal_root = creal.startswith(os.path.dirname(env.cycling_root) + os.sep) and os.path.basename(_cdir).startswith("cycling_features")
        if not creal.startswith(env.cycling_root + os.sep) and not _ok_signal_root:
            raise PrepError("cycling entry %s lives outside %s: %s"
                            % (cid, env.cycling_root, cpath))
        if os.path.basename(creal) != cid + ".json.gz":
            raise PrepError("cycling entry %s path does not match its cell id" % cid)
        csha = cyc.get("sha256")
        if not isinstance(csha, str) or len(csha) != 64:
            raise PrepError("cycling entry %s has no sha256" % cid)
        train.append({"cell_id": cid, "processed_path": real,
                      "processed_sha256": sha.lower(),
                      "cycling_path": creal, "cycling_sha256": csha.lower(),
                      "cycling_cycles": cyc.get("cycles")})

    train.sort(key=lambda x: x["cell_id"])
    expected = binding["expected_cell_count"]
    if len(train) != expected:
        raise PrepError("manifest yields %d train cells, GO expects %d"
                        % (len(train), expected))
    missing = set(train[i]["cell_id"] for i in range(len(train))) - set(cyc_by_cell)
    if missing:
        raise PrepError("cycling manifest misses %d cells" % len(missing))
    out("sources accepted: %d processed cells, %d cycling assets (all role=train)"
        % (len(train), len(train)))
    return train


def build_all(env, binding, out=print):
    """Read the two sources, build every cell, return (arrays, manifest body)."""
    started = time.time()
    processed_doc, pm_sha = env.read_json(binding["processed_manifest"],
                                          "processed manifest")
    if pm_sha != binding["processed_manifest_sha256"]:
        raise PrepError("processed manifest changed after GO validation")
    cycling_doc, cm_sha = env.read_json(binding["cycling_manifest"],
                                        "cycling manifest")
    if cm_sha != binding["cycling_manifest_sha256"]:
        raise PrepError("cycling manifest changed after GO validation")
    cells = _cell_ids_from_assets(processed_doc, cycling_doc, env, binding, out)
    del processed_doc, cycling_doc

    cutoff = binding["cutoff_epoch"]
    per_cell = []
    excluded = []
    agg = {}
    cell_order = []
    flat_parts = []
    total_events = 0
    for index, spec in enumerate(cells):
        cid = spec["cell_id"]
        payload, sha = env.read_json(spec["processed_path"],
                                     "processed cell %s" % cid)
        if sha != spec["processed_sha256"]:
            raise PrepError("processed cell %s sha256 mismatch" % cid)
        rpts, rcount = rpt_records_from_processed(payload, cid)
        del payload
        blob = env.read_bytes(spec["cycling_path"], "cycling asset %s" % cid)
        if _sha256_bytes(blob) != spec["cycling_sha256"]:
            raise PrepError("cycling asset %s sha256 mismatch" % cid)
        try:
            doc = json.loads(gzip.decompress(blob).decode("utf-8"))
        except (OSError, EOFError, ValueError) as exc:
            raise PrepError("cycling asset %s is not readable gzip JSON: %s"
                            % (cid, exc))
        del blob
        cycles, ccount = cycle_records_from_features(doc, cid)
        del doc
        seq = cell_sequence(cid, cycles, rpts, cutoff_epoch=cutoff)
        del cycles, rpts
        counts = {k: int(seq[k]) for k in
                  ("n_cycle_used", "n_cycle_pre_anchor_excluded",
                   "n_cycle_late_excluded", "n_rpt_scored",
                   "n_rpt_pre_anchor_excluded", "n_rpt_late_excluded",
                   "n_rpt_future_excluded", "assumed_cycle_arrival")}
        counts.update(rcount)
        counts.update(ccount)
        for key, value in counts.items():
            agg[key] = agg.get(key, 0) + int(value)
        if seq["anchor"] is None:
            excluded.append({
                "cell_id": cid,
                "reason": "no valid RPT arrived at/before the cutoff (no Q_ref)",
                "counts": counts,
            })
            out("  [skip] %-8s no arrived valid RPT -> excluded" % cid)
            continue
        arrays = _flatten(seq)
        cell_order.append(cid)
        flat_parts.append(arrays)
        total_events += arrays["kind"].shape[0]
        per_cell.append({
            "cell_id": cid,
            "q_ref_ah": float(seq["q_ref_ah"]),
            "anchor_source_epoch": float(seq["anchor"]["source_epoch"]),
            "anchor_available_epoch": float(seq["anchor"]["available_epoch"]),
            "anchor_record_index": int(seq["anchor"]["index"]),
            "n_valid_arrived_at_anchor": int(seq["anchor"]["n_valid_arrived"]),
            "n_events": int(arrays["kind"].shape[0]),
            "n_cycle_events": int((arrays["kind"] == 1).sum()),
            "n_rpt_events": int((arrays["kind"] == 2).sum()),
            "counts": counts,
        })
        if (index + 1) % 25 == 0:
            out("  ... %d/%d cells, %d events" % (index + 1, len(cells), total_events))

    if not cell_order:
        raise PrepError("no cell produced an anchored sequence")
    if len(cell_order) != len(set(cell_order)):
        raise PrepError("duplicate cell in the assembled order")

    cell_ids = np.asarray(cell_order, dtype=str)
    q_ref = np.asarray([c["q_ref_ah"] for c in per_cell], dtype=np.float64)
    anchor = np.asarray([c["anchor_source_epoch"] for c in per_cell],
                        dtype=np.float64)
    event_cell = np.concatenate([
        np.full(part["kind"].shape[0], i, dtype=np.int64)
        for i, part in enumerate(flat_parts)])
    arrays = {
        "cell_ids": cell_ids,
        "q_ref_ah": q_ref,
        "anchor_source_epoch": anchor,
        "event_cell": event_cell,
        "event_kind": np.concatenate([p["kind"] for p in flat_parts]),
        "event_source": np.concatenate([p["source"] for p in flat_parts]),
        "event_available": np.concatenate([p["available"] for p in flat_parts]),
        "event_dt_weeks": np.concatenate([p["dt"] for p in flat_parts]),
        "control": np.concatenate([p["control"] for p in flat_parts], axis=0),
        "control_mask": np.concatenate([p["control_mask"] for p in flat_parts], axis=0),
        "capacity_ah": np.concatenate([p["capacity_ah"] for p in flat_parts]),
        "score": np.concatenate([p["score"] for p in flat_parts]),
    }
    _audit_arrays(arrays)

    ids = [str(c) for c in cell_order]
    train_cells, val_cells = split_cells_by_hash(ids, binding["n_val_cells"],
                                                 seed=binding["split_seed"])
    if not train_cells or not val_cells:
        raise PrepError("hash split produced an empty train or val side")
    if set(train_cells) & set(val_cells) or set(train_cells) | set(val_cells) != set(ids):
        raise PrepError("hash split is not a partition of the prepared cells")

    reads = {
        "processed_json_cells": len(cells),
        "cycling_gz_cells": len(cells),
        "files_read": int(env.files_read),
        "payload_bytes_read": int(env.bytes_read),
        "raw_archive_reads": 0,
        "c3_reads": 0,
        "c4_reads": 0,
        "checkpoint_reads": 0,
        "optimizer_steps": 0,
        "fits": 0,
    }
    body = {
        "schema": SCHEMA,
        "prepared_npz": NPZ_NAME,
        "n_cells": len(cell_order),
        "n_cells_requested": len(cells),
        "n_cells_excluded_unanchored": len(excluded),
        "n_events": int(total_events),
        "n_cycle_events": int((arrays["event_kind"] == 1).sum()),
        "n_rpt_events": int((arrays["event_kind"] == 2).sum()),
        "n_scored_rpt_events": int(arrays["score"].sum()),
        "n_cells_zero_events": int(sum(1 for c in per_cell if c["n_events"] == 0)),
        "counts": dict(sorted(agg.items())),
        "cells": per_cell,
        "excluded_cells": excluded,
        "split": {
            "method": "a2_targets.split_cells_by_hash",
            "seed": binding["split_seed"],
            "n_val": binding["n_val_cells"],
            "train_cells": train_cells,
            "val_cells": val_cells,
        },
        "reads": reads,
        "fits": 0,
        "optimizer_steps": 0,
        "training_runs": 0,
        "anchor_rule": ("earliest ARRIVAL among valid RPTs arrived at/before the "
                        "cutoff; ties by source stop then record index; anchor "
                        "reading defines Q_ref and is not scored"),
        "cutoff_policy": binding["cutoff_policy"],
        "cutoff_epoch": binding["cutoff_epoch"],
        "control": {
            "dim": CONTROL_DIM,
            "fields": [{"index": i, "name": n, "unit": u}
                       for i, (n, u) in enumerate(CONTROL_FIELDS)],
            "missing_rule": CONTROL_MISSING_RULE,
            "history_dependent_terms": 0,
        },
        "go": {"path": binding["go_path"], "sha256": binding["go_sha256"],
               "status_at_read": binding["go_status"],
               "allow_prep": True, "allow_fit": False, "consumes_go": False},
        "sources": {
            "processed_manifest": binding["processed_manifest"],
            "processed_manifest_sha256": binding["processed_manifest_sha256"],
            "cycling_manifest": binding["cycling_manifest"],
            "cycling_manifest_sha256": binding["cycling_manifest_sha256"],
        },
        "code_sha256": {name: hash_file(os.path.join(HERE, name))
                        for name in REQUIRED_CODE if os.path.isfile(
                            os.path.join(HERE, name))},
        "elapsed_seconds_build": round(time.time() - started, 3),
        "created_utc": _utc_now(),
    }
    return arrays, body, per_cell


def _audit_arrays(arrays):
    for key in NPZ_KEYS:
        if key not in arrays:
            raise PrepError("assembled npz is missing %r" % key)
    n_cells = arrays["cell_ids"].shape[0]
    n_events = arrays["event_cell"].shape[0]
    for key in ("q_ref_ah", "anchor_source_epoch"):
        if arrays[key].shape != (n_cells,):
            raise PrepError("%s has shape %r, expected (%d,)"
                            % (key, arrays[key].shape, n_cells))
    for key in ("event_kind", "event_source", "event_available", "event_dt_weeks",
                "capacity_ah", "score"):
        if arrays[key].shape != (n_events,):
            raise PrepError("%s has shape %r, expected (%d,)"
                            % (key, arrays[key].shape, n_events))
    for key in ("control", "control_mask"):
        if arrays[key].shape != (n_events, CONTROL_DIM):
            raise PrepError("%s has shape %r, expected (%d,%d)"
                            % (key, arrays[key].shape, n_events, CONTROL_DIM))
    if not np.all(np.isfinite(arrays["q_ref_ah"])) or np.any(arrays["q_ref_ah"] <= 0):
        raise PrepError("Q_ref must be finite and positive")
    if np.any(np.diff(arrays["event_cell"]) < 0):
        raise PrepError("event_cell is not non-decreasing")
    if not set(np.unique(arrays["event_kind"]).tolist()) <= {1, 2}:
        raise PrepError("event_kind must be 1 (cycle) or 2 (rpt)")
    if np.any(arrays["event_dt_weeks"] < 0):
        raise PrepError("negative dt_weeks")
    if np.any(arrays["event_available"] < arrays["event_source"] - 1e-6):
        raise PrepError("availability precedes source completion")
    is_cycle = arrays["event_kind"] == 1
    is_rpt = arrays["event_kind"] == 2
    if np.any(arrays["capacity_ah"][is_cycle] != 0.0):
        raise PrepError("cycle events must not carry a capacity value")
    if np.any(arrays["score"][is_cycle]):
        raise PrepError("cycle events must not be scored")
    if np.any(arrays["capacity_ah"][is_rpt] <= 0.0):
        raise PrepError("rpt events must carry a positive capacity")
    if not np.all(arrays["score"][is_rpt]):
        raise PrepError("every post-anchor arrived RPT must be scored")
    masked = arrays["control_mask"] == 0.0
    if np.any(arrays["control"][masked] != 0.0):
        raise PrepError("masked control fields must be exactly 0.0")
    if not set(np.unique(arrays["control_mask"]).tolist()) <= {0.0, 1.0}:
        raise PrepError("control_mask must be 0/1")
    if not np.all(np.isfinite(arrays["control"])):
        raise PrepError("non-finite control value")


def _write_atomic(path, payload_bytes):
    if os.path.exists(path):
        raise PrepError("refuse to overwrite %s" % path)
    with open(path, "xb") as fh:
        fh.write(payload_bytes)
        fh.flush()
        os.fsync(fh.fileno())


def write_outputs(env, binding, arrays, body, out=print):
    out_dir = binding["output_dir"]
    if os.path.isdir(out_dir):
        if os.listdir(out_dir):
            raise PrepError("output_dir is no longer fresh: %s" % out_dir)
    else:
        os.makedirs(out_dir)

    npz_path = os.path.join(out_dir, NPZ_NAME)
    if os.path.exists(npz_path):
        raise PrepError("refuse to overwrite %s" % npz_path)
    np.savez_compressed(npz_path, **arrays)
    npz_sha = hash_file(npz_path)
    npz_bytes = os.path.getsize(npz_path)

    man = dict(body)
    man["prepared_npz"] = npz_path
    man["prepared_npz_sha256"] = npz_sha
    man["prepared_npz_bytes"] = int(npz_bytes)
    man["written_utc"] = _utc_now()
    man_path = os.path.join(out_dir, MANIFEST_NAME)
    _write_atomic(man_path, (json.dumps(_json_safe(man), indent=2,
                                        sort_keys=False) + "\n").encode("utf-8"))
    man_sha = hash_file(man_path)

    receipt = {
        "receipt_type": "A2_PREP_RUN_RECEIPT",
        "receipt_schema": 1,
        "status": "SUCCESS",
        "consumes_go": False,
        "go_consumption": "owned by the controller; this receipt never marks a GO consumed",
        "go_path": binding["go_path"],
        "go_sha256": binding["go_sha256"],
        "go_status_at_read": binding["go_status"],
        "allow_prep": True,
        "allow_fit": False,
        "manifest_path": man_path,
        "manifest_sha256": man_sha,
        "prepared_npz": npz_path,
        "prepared_npz_sha256": npz_sha,
        "n_cells": man["n_cells"],
        "n_events": man["n_events"],
        "counts": man["counts"],
        "reads": man["reads"],
        "fits": 0,
        "optimizer_steps": 0,
        "written_utc": _utc_now(),
    }
    _write_atomic(binding["receipt_path"],
                  (json.dumps(_json_safe(receipt), indent=2) + "\n").encode("utf-8"))
    out("wrote %s" % npz_path)
    out("wrote %s" % man_path)
    out("wrote %s" % binding["receipt_path"])
    return man, man_path, man_sha, npz_path, npz_sha


def run_prep(go_path, env=None, out=print):
    env = env or default_env()
    problems, go, binding = validate_prep_go(go_path, env)
    if problems:
        out("REFUSED -- PREP GO validation failed (%d problem(s)):" % len(problems))
        for problem in problems:
            out("  - %s" % problem)
        out("NO FILE WRITTEN. NO RECEIPT. NO DATA READ. NO GO CONSUMED.")
        return 2
    env.permit_read_roots(os.path.dirname(binding["processed_manifest"]),
                          os.path.dirname(binding["cycling_manifest"]))
    out("GO ACCEPTED (PREP-only): %s" % binding["go_path"])
    out("  go_sha256=%s" % binding["go_sha256"])
    out("  output_dir=%s" % binding["output_dir"])
    out("  receipt_path=%s" % binding["receipt_path"])
    try:
        arrays, body, _ = build_all(env, binding, out=out)
        man, man_path, man_sha, npz_path, npz_sha = write_outputs(
            env, binding, arrays, body, out=out)
    except PrepError as exc:
        out("PREP FAILED (schema/refusal): %s" % exc)
        out("NO RECEIPT WRITTEN. NO GO CONSUMED.")
        return 3
    except Exception as exc:  # noqa: BLE001 - report, never swallow silently
        out("PREP FAILED (unexpected): %s" % exc)
        traceback.print_exc(file=sys.stdout)
        out("NO RECEIPT WRITTEN. NO GO CONSUMED.")
        return 3
    out("PREP OK: %d cells, %d events (%d cycles, %d rpt, %d scored)"
        % (man["n_cells"], man["n_events"], man["n_cycle_events"],
           man["n_rpt_events"], man["n_scored_rpt_events"]))
    out("npz_sha256=%s" % npz_sha)
    out("manifest_sha256=%s" % man_sha)
    out("NO TRAINING. NO FIT. NO OPTIMIZER STEP. C3/C4 READS: 0.")
    return 0


# ------------------------------------------------------------------ self-check
def _iso(epoch):
    return datetime.fromtimestamp(float(epoch), timezone.utc).isoformat().replace(
        "+00:00", "Z")


def _stats(values, unit=1.0):
    vals = [float(v) * unit for v in values]
    return {"n": len(vals), "finite_n": len(vals), "first": vals[0],
            "last": vals[-1], "min": min(vals), "max": max(vals),
            "mean": sum(vals) / len(vals)}


def _leg(start, stop, q_last, v_mean, v_last, i_vals, e_last, e_mean):
    return {"start": _iso(start), "stop": _iso(stop),
            "Q_sample_stats": _stats([0.0, q_last / 2.0, q_last]),
            "V_V_sample_stats": {"n": 3, "finite_n": 3, "first": v_mean,
                                 "last": v_last, "min": min(v_mean, v_last),
                                 "max": max(v_mean, v_last), "mean": v_mean},
            "t_sample_stats": None,
            "E_sample_stats": {"n": 3, "finite_n": 3, "first": e_mean,
                               "last": e_last, "min": min(e_mean, e_last),
                               "max": max(e_mean, e_last), "mean": e_mean},
            "I_A_sample_stats": {"n": 3, "finite_n": 3, "first": i_vals[0],
                                 "last": i_vals[-1], "min": min(i_vals),
                                 "max": max(i_vals), "mean": sum(i_vals) / 3.0}}


def _cycle(idx, ch_start, ch_stop, di_start, di_stop, **kw):
    return {
        "source_cycle_index": idx,
        "charge": _leg(ch_start, ch_stop, kw.get("qc", 0.300), kw.get("vc", 4.20),
                       kw.get("vcl", 4.25), kw.get("ic", [-1.0, 0.0, 1.0]),
                       kw.get("ec", 1.20), kw.get("ecm", 0.60)),
        "discharge": _leg(di_start, di_stop, kw.get("qd", 0.280), kw.get("vd", 3.80),
                          kw.get("vdl", 3.70), kw.get("id", [-2.0, 0.0, 2.0]),
                          kw.get("ed", 1.00), kw.get("edm", 0.50)),
        "capacity_charge_source_units_unknown": kw.get("capc", 0.290),
        "capacity_discharge_source_units_unknown": kw.get("capd", 0.280),
        "observed_cycle_throughput_source_units": kw.get("thr", 0.570),
    }


def _rpt(idx, stop, cap, valid=True, visible="stop", start=None):
    start = stop - 3600.0 if start is None else start
    return {"source_rpt_index": idx, "start": _iso(start), "stop": _iso(stop),
            "capacityAh": cap, "valid": valid,
            "calendar_age_seconds": 0.0,
            "capacity_visible_at": visible,
            "observed_nominal80_endpoint": False}


def _cell(cid, records):
    return {"cell_id": cid, "role": "train",
            "group_id": "G" + cid[1:].split("C")[0],
            "nominal_capacity_ah": 0.25, "baseline_stop": records[0]["stop"],
            "records": records, "eol_or_censoring_claim": None}


def _fixture_tree(tmp):
    """Fabricate processed cells + cycling assets + both manifests."""
    day = 86400.0
    base = 1_700_000_000.0
    proc = os.path.join(tmp, "data", "processed", "ISU_ILCC_DataV2_v1")
    cyc = os.path.join(tmp, "reports", "signals", "cycling_features_v3")
    man = os.path.join(tmp, "prep_inputs")
    for path in (proc, cyc, man):
        os.makedirs(path)

    # G10C1: normal cell, one pre-anchor cycle, invalid RPT first.
    c1_rpts = [_rpt(0, base + 1 * day, 0.290, valid=False),
               _rpt(1, base + 10 * day, 0.281),
               _rpt(2, base + 20 * day, 0.276)]
    c1_cycles = [
        _cycle(0, base + 7 * day, base + 7 * day + 7200, base + 8 * day,
               base + 8 * day + 6300),
        _cycle(1, base + 11 * day, base + 11 * day + 7200, base + 11 * day + 3600,
               base + 11 * day + 9900),
        _cycle(2, base + 24 * day, base + 24 * day + 7200, base + 24 * day + 3600,
               base + 24 * day + 9900),
    ]
    # G10C2: earlier source, later arrival -> anchor is the later-source record.
    c2_rpts = [
        {"source_rpt_index": 0, "start": _iso(base + 9 * day),
         "stop": _iso(base + 10 * day), "capacityAh": 0.300, "valid": True,
         "calendar_age_seconds": 0.0,
         "capacity_visible_at": _iso(base + 30 * day)},
        {"source_rpt_index": 1, "start": _iso(base + 14 * day),
         "stop": _iso(base + 15 * day), "capacityAh": 0.272, "valid": True,
         "calendar_age_seconds": 0.0,
         "capacity_visible_at": _iso(base + 16 * day)},
    ]
    c2_cycles = [
        _cycle(0, base + 11 * day, base + 11 * day + 3600,
               base + 11 * day + 7200, base + 11 * day + 10800),
        _cycle(1, base + 21 * day, base + 21 * day + 3600,
               base + 21 * day + 7200, base + 21 * day + 10800),
    ]
    # G10C9: no valid arrived RPT -> cannot be anchored, must be excluded.
    c3_rpts = [_rpt(0, base + 5 * day, 0.0), _rpt(1, base + 6 * day, 0.30, valid=False)]
    c3_cycles = [_cycle(0, base + 4 * day, base + 4 * day + 3600,
                        base + 4 * day + 7200, base + 4 * day + 10800)]
    # G11C1: masked stats, a no-clock cycle, a negative-duration leg.
    c4_rpts = [_rpt(0, base + 10 * day, 0.279), _rpt(1, base + 30 * day, 0.270,
                                                     visible=None)]
    c4_cycles = [
        _cycle(0, base + 12 * day, base + 12 * day + 7200, base + 12 * day + 3600,
               base + 12 * day + 9900),
        {"source_cycle_index": 1, "charge": {"start": _iso(base + 13 * day),
                                             "stop": None},
         "discharge": {"start": _iso(base + 13 * day), "stop": _iso(base + 13 * day)},
         "capacity_charge_source_units_unknown": None,
         "capacity_discharge_source_units_unknown": None,
         "observed_cycle_throughput_source_units": None},
        {"source_cycle_index": 2,
         "charge": {"start": _iso(base + 14 * day + 7200),
                    "stop": _iso(base + 14 * day)},
         "discharge": {"start": _iso(base + 15 * day),
                       "stop": _iso(base + 15 * day + 3600)},
         "capacity_charge_source_units_unknown": None,
         "capacity_discharge_source_units_unknown": None,
         "observed_cycle_throughput_source_units": None},
    ]

    payloads = {"G10C1": (c1_rpts, c1_cycles), "G10C2": (c2_rpts, c2_cycles),
                "G10C9": (c3_rpts, c3_cycles), "G11C1": (c4_rpts, c4_cycles)}

    assets = []
    inventory = []
    for cid, (rpts, cycles) in payloads.items():
        pdoc = _cell(cid, rpts)
        ppath = os.path.join(proc, cid + ".json")
        pbytes = (json.dumps(pdoc) + "\n").encode("utf-8")
        with open(ppath, "wb") as fh:
            fh.write(pbytes)
        cdoc = {"cell_id": cid, "role": "train", "cycle_count": len(cycles),
                "time_basis": "source per-leg start/stop ISO strings",
                "cycles": cycles}
        cpath = os.path.join(cyc, cid + ".json.gz")
        with open(cpath, "wb") as fh:
            fh.write(gzip.compress(json.dumps(cdoc).encode("utf-8")))
        assets.append({"cell_id": cid, "role": "train", "path": ppath,
                       "sha256": _sha256_bytes(pbytes)})
        inventory.append({"cell_id": cid, "role": "train",
                          "path": os.path.relpath(cpath, tmp),
                          "sha256": hash_file(cpath), "cycles": len(cycles),
                          "bytes": os.path.getsize(cpath)})

    pd = {"manifest_type": "processed_datav2_train_cells_v1", "assets": assets,
          "raw_archive_reads_allowed": False, "C3_reads_allowed": False,
          "C4_reads_allowed": False}
    cd = {"status": "SUCCESS", "schema": "MULTISOURCE_CYCLING_FEATURES_ALL188_V1",
          "cells": len(inventory), "train": len(inventory), "development": 0,
          "C4": 0, "inventory": inventory,
          "arrival": "actual communication arrival unobserved"}
    pm_path = os.path.join(man, "processed_manifest.json")
    cm_path = os.path.join(man, "cycling_all188_feature_manifest.json")
    for path, doc in ((pm_path, pd), (cm_path, cd)):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1)
    expected = {
        "G10C1": {"q_ref": 0.281, "anchor": base + 10 * day},
        "G10C2": {"q_ref": 0.272, "anchor": base + 15 * day},
        "G11C1": {"q_ref": 0.279, "anchor": base + 10 * day},
    }
    return {"root": tmp, "processed_root": proc, "cycling_root": cyc,
            "processed_manifest": pm_path, "cycling_manifest": cm_path,
            "expected": expected, "base": base, "day": day,
            "payloads": payloads}


def _env_for(fixture):
    return PrepEnv(root=fixture["root"], processed_root=fixture["processed_root"],
                   cycling_root=fixture["cycling_root"],
                   processed_manifest=fixture["processed_manifest"],
                   cycling_manifest=fixture["cycling_manifest"],
                   read_roots=[fixture["root"]])


def _go_template(env, fixture=None, out_dir=None, receipt=None):
    return {
        "status": "APPROVED",
        "allow_prep": True,
        "allow_fit": False,
        "scope": "A2 PREP data build (compact sequences only; no fit, no C3/C4)",
        "code_sha256": {name: hash_file(os.path.join(HERE, name))
                        for name in REQUIRED_CODE},
        "processed_manifest": {"path": env.processed_manifest,
                               "sha256": hash_file(env.processed_manifest)},
        "cycling_manifest": {"path": env.cycling_manifest,
                             "sha256": hash_file(env.cycling_manifest)},
        "output_dir": out_dir,
        "receipt_path": receipt,
        "expected_cell_count": 4 if fixture else 125,
        "n_val_cells": 1 if fixture else 25,
        "split_seed": 42,
        "cutoff_policy": "full_history",
        "max_fits": 0,
        "raw_archive_reads_allowed": False,
        "C3_reads_allowed": False,
        "C4_reads_allowed": False,
    }


def check_go_gate(tmp, line):
    """Unapproved GOs are refused and leave no output/receipt behind."""
    fixture = _fixture_tree(os.path.join(tmp, "gate"))
    env = _env_for(fixture)
    out_dir = os.path.join(fixture["root"], "out_refused")
    receipt = os.path.join(fixture["root"], "receipt_refused.json")
    good = _go_template(env, fixture, out_dir, receipt)

    from copy import deepcopy
    cases = []
    def add(name, mutate):
        go = deepcopy(good)
        mutate(go)
        cases.append((name, go))
    add("status_not_approved", lambda g: g.update(status="PENDING"))
    add("allow_prep_false", lambda g: g.update(allow_prep=False))
    add("allow_fit_true", lambda g: g.update(allow_fit=True))
    add("allow_fit_missing", lambda g: g.pop("allow_fit"))
    add("no_code_hashes", lambda g: g.pop("code_sha256"))
    add("code_hash_mismatch",
        lambda g: g["code_sha256"].update({"a2_prep.py": "0" * 64}))
    add("missing_code_entry",
        lambda g: g["code_sha256"].pop("a2_targets.py"))
    add("already_consumed", lambda g: g.update(consumed_at="2026-01-01T00:00:00Z"))
    add("scope_not_prep", lambda g: g.update(scope="A2 TRAIN FIT"))
    add("raw_reads_allowed", lambda g: g.update(raw_archive_reads_allowed=True))
    add("c3_reads_allowed", lambda g: g.update(C3_reads_allowed=True))
    add("manifest_sha_wrong",
        lambda g: g["processed_manifest"].update({"sha256": "f" * 64}))
    add("bad_cutoff_policy", lambda g: g.update(cutoff_policy="whatever"))
    add("relative_output", lambda g: g.update(output_dir="relative/out"))
    add("max_fits_nonzero", lambda g: g.update(max_fits=1))

    for name, go in cases:
        go_path = os.path.join(fixture["root"], "go_%s.json" % name)
        with open(go_path, "w", encoding="utf-8") as fh:
            json.dump(go, fh)
        code = run_prep(go_path, env=env, out=lambda *a, **k: None)
        assert code != 0, "GO gate accepted %s" % name
        assert not os.path.exists(out_dir), "%s created the output dir" % name
        assert not os.path.exists(receipt), "%s wrote a receipt" % name

    # A stale (non-fresh) output dir must also be refused.
    dirty = os.path.join(fixture["root"], "out_dirty")
    os.makedirs(dirty)
    with open(os.path.join(dirty, "stale.txt"), "w", encoding="utf-8") as fh:
        fh.write("x")
    go = deepcopy(good)
    go["output_dir"] = dirty
    go_path = os.path.join(fixture["root"], "go_dirty.json")
    with open(go_path, "w", encoding="utf-8") as fh:
        json.dump(go, fh)
    code = run_prep(go_path, env=env, out=lambda *a, **k: None)
    assert code != 0, "GO gate accepted a non-fresh output dir"
    assert not os.path.exists(receipt), "dirty-dir refusal wrote a receipt"

    # A happy GO must still pass the gate (no build yet).
    go_path = os.path.join(fixture["root"], "go_ok.json")
    with open(go_path, "w", encoding="utf-8") as fh:
        json.dump(good, fh)
    problems, _go, binding = validate_prep_go(go_path, env)
    assert problems == [], "valid GO rejected: %r" % (problems,)

    # A C3/C4 asset is a hard refusal, never a silent skip.
    with open(env.processed_manifest, "r", encoding="utf-8") as fh:
        pd = json.load(fh)
    with open(env.cycling_manifest, "r", encoding="utf-8") as fh:
        cd = json.load(fh)
    pd["assets"].append({"cell_id": "G10C3", "role": "train",
                         "path": os.path.join(fixture["processed_root"], "G10C3.json"),
                         "sha256": "0" * 64})
    cd["inventory"].append({"cell_id": "G10C3", "role": "train",
                            "path": os.path.join(fixture["cycling_root"], "G10C3.json.gz"),
                            "sha256": "0" * 64, "cycles": 1})
    try:
        _cell_ids_from_assets(pd, cd, env, binding, lambda *a, **k: None)
    except PrepError as exc:
        assert "C3/C4" in str(exc), "unexpected refusal: %s" % exc
    else:
        raise AssertionError("a C3 asset must be refused")
    line("  gate: %d bad GOs refused, 0 files written; 1 good GO accepted; "
         "C3 asset refused" % len(cases))


def check_control_table(tmp, line):
    day = 86400.0
    base = 1_700_000_000.0
    row = _cycle(0, base, base + 7200, base + 7200 + 3600, base + 7200 + 3600 + 6300)
    values, mask = cycle_control(row)
    assert len(values) == 24 and len(mask) == 24
    assert mask == [1.0] * 24, "complete synthetic cycle must be fully observed"
    expect = [7200.0 / WEEK_SECONDS, 6300.0 / WEEK_SECONDS, 3600.0 / WEEK_SECONDS,
              0.300, 0.280, 0.150, 0.140, 0.300, 0.280,
              4.20, 3.80, 4.25, 3.70,
              1.0, 2.0, 1.0, 2.0,
              1.20, 1.00, 0.60, 0.50,
              0.290, 0.280, 0.570]
    for i, (got, want) in enumerate(zip(values, expect)):
        assert abs(got - want) < 1e-9, "field %d (%s): %r != %r" % (
            i, CONTROL_FIELDS[i][0], got, want)
    assert abs(values[13] - 1.0) < 1e-12, "mixed-sign charge I must be (|min|+|max|)/2"

    partial = _cycle(1, base, base + 7200, base + 3600, base + 7200)
    partial["charge"] = {"start": _iso(base), "stop": _iso(base + 7200)}
    partial["discharge"] = {"start": _iso(base + 3600), "stop": _iso(base + 7200)}
    partial["capacity_charge_source_units_unknown"] = -1.0
    partial["observed_cycle_throughput_source_units"] = None
    values2, mask2 = cycle_control(partial)
    for i, (v, m) in enumerate(zip(values2, mask2)):
        if m == 0.0:
            assert v == 0.0, "masked field %d must be exactly 0" % i
    assert mask2[0] == 1.0 and mask2[1] == 1.0, "durations still observable"
    assert mask2[2] == 0.0 and values2[2] == 0.0, "gap must be missing"
    assert mask2[3] == 0.0 and mask2[21] == 0.0 and mask2[23] == 0.0
    assert mask2[7] == 0.0, "span needs min and max"

    no_clock = {"source_cycle_index": 9,
                "charge": {"start": _iso(base), "stop": "not-a-time"},
                "discharge": {"start": _iso(base), "stop": _iso(base + 60)}}
    assert cycle_completion_epoch(no_clock) is None, "malformed clock must be unknown"
    line("  control: 24 finite fields match the hand-computed table; "
         "mask=0 <-> value=0; malformed clocks unknown")


def check_asof_and_anchor(tmp, line):
    day = 86400.0
    base = 1_700_000_000.0
    rpts = [_rpt(0, base + 10 * day, 0.280),
            _rpt(1, base + 20 * day, 0.274),
            _rpt(2, base + 22 * day, 0.270, visible=_iso(base + 40 * day)),
            _rpt(3, base + 35 * day, 0.260)]
    cycles = [_cycle(i, base + t * day, base + t * day + 3600,
                     base + t * day + 7200, base + t * day + 10800)
              for i, t in enumerate((11, 19, 24, 33))]
    recs, _ = rpt_records_from_processed(_cell("G10C1", rpts), "G10C1")
    crecs = []
    for i, row in enumerate(cycles):
        recs_c, _ = cycle_records_from_features(
            {"cell_id": "G10C1", "role": "train", "cycles": [row]}, "G10C1")
        crecs.extend(recs_c)
    full = cell_sequence("G10C1", crecs, recs, cutoff_epoch=None)
    assert full["q_ref_ah"] == 0.280, "anchor must be the first arrived RPT"
    assert full["n_cycle_pre_anchor_excluded"] == 0
    assert full["n_rpt_scored"] == 3, "without a cutoff every post-anchor RPT scores"
    assert full["assumed_cycle_arrival"] == 0, "cycle arrivals must be explicit"

    cutoff = base + 25 * day
    gated = cell_sequence("G10C1", crecs, recs, cutoff_epoch=cutoff)
    # cycles are visible at their completion, so a cycle can only be excluded by
    # being beyond the cutoff (never by an arrival lag); both are counted.
    assert gated["n_cycle_late_excluded"] == 1, "cycle@33d is beyond the cutoff"
    assert gated["n_cycle_used"] == 3
    assert gated["n_rpt_future_excluded"] == 1, "RPT@35d is beyond the cutoff"
    assert gated["n_rpt_late_excluded"] == 1, "RPT@22d arrives 40d > cutoff"
    assert gated["n_rpt_scored"] == 1, "only RPT@20d is source- and arrival-visible"
    assert all(e["source_epoch"] <= cutoff + 1e-6 for e in gated["events"]),         "no event may be beyond the cutoff"
    assert all(e["available_epoch"] <= cutoff + 1e-6 for e in gated["events"])

    rpts2 = [{"source_rpt_index": 0, "start": _iso(base + 9 * day),
              "stop": _iso(base + 10 * day), "capacityAh": 0.300, "valid": True,
              "calendar_age_seconds": 0.0,
              "capacity_visible_at": _iso(base + 30 * day)},
             _rpt(1, base + 15 * day, 0.272)]
    recs2, _ = rpt_records_from_processed(_cell("G10C2", rpts2), "G10C2")
    seq2 = cell_sequence("G10C2", [], recs2, cutoff_epoch=base + 40 * day)
    assert seq2["q_ref_ah"] == 0.272, "earliest arrival wins, not earliest source"
    assert seq2["n_rpt_pre_anchor_excluded"] == 1, "pre-anchor RPT must be counted"

    mixed = {"cell_id": "G10C9", "role": "train", "records": [
        _rpt(0, base, -0.1), _rpt(1, base + day, 0.30, valid=False),
        _rpt(2, base + 2 * day, 0.28)]}
    kept, kcount = rpt_records_from_processed(mixed, "G10C9")
    assert len(kept) == 1 and kept[0]["capacity_ah"] == 0.28
    assert kcount["rpt_bad_capacity_skipped"] == 1
    assert kcount["rpt_invalid_skipped"] == 1
    seq3 = cell_sequence("G10C9", [], [], cutoff_epoch=None)
    assert seq3["anchor"] is None and seq3["q_ref_ah"] is None
    line("  anchor: earliest arrival, pre-anchor/future/late gating counted "
         "(scored 3->1 under the cutoff); unanchored cell has no Q_ref")


def check_end_to_end(tmp, line):
    fixture = _fixture_tree(os.path.join(tmp, "e2e"))
    env = _env_for(fixture)
    out_dir = os.path.join(fixture["root"], "out")
    receipt = os.path.join(fixture["root"], "receipt.json")
    go = _go_template(env, fixture, out_dir, receipt)
    go_path = os.path.join(fixture["root"], "go.json")
    with open(go_path, "w", encoding="utf-8") as fh:
        json.dump(go, fh)
    code = run_prep(go_path, env=env, out=lambda *a, **k: None)
    assert code == 0, "synthetic PREP run failed with exit %d" % code
    man_path = os.path.join(out_dir, MANIFEST_NAME)
    assert os.path.isfile(man_path), "manifest not written"
    assert os.path.isfile(receipt), "receipt not written"
    with open(man_path, "r", encoding="utf-8") as fh:
        man = json.load(fh)
    with open(receipt, "r", encoding="utf-8") as fh:
        rc = json.load(fh)
    assert rc["consumes_go"] is False and "consumed_at" not in rc
    assert man["fits"] == 0 and man["optimizer_steps"] == 0
    assert man["reads"]["c3_reads"] == 0 and man["reads"]["c4_reads"] == 0
    assert man["reads"]["raw_archive_reads"] == 0
    assert man["n_cells"] == 3 and man["n_cells_requested"] == 4
    assert man["n_cells_excluded_unanchored"] == 1
    assert [c["cell_id"] for c in man["cells"]] == ["G10C1", "G10C2", "G11C1"]
    assert man["prepared_npz_sha256"] == hash_file(man["prepared_npz"])
    assert man["counts"]["rpt_invalid_skipped"] >= 1
    assert man["counts"]["cycle_no_clock_skipped"] >= 1
    assert man["counts"]["rpt_unknown_availability_skipped"] >= 1
    for cid, want in fixture["expected"].items():
        entry = next(c for c in man["cells"] if c["cell_id"] == cid)
        assert abs(entry["q_ref_ah"] - want["q_ref"]) < 1e-12, "%s Q_ref" % cid
        assert abs(entry["anchor_source_epoch"] - want["anchor"]) < 1e-3, \
            "%s anchor epoch" % cid

    z = np.load(man["prepared_npz"], allow_pickle=False)
    assert set(z.files) == set(NPZ_KEYS), "npz keys %r" % (sorted(z.files),)
    assert z["cell_ids"].dtype.kind == "U"
    assert z["q_ref_ah"].dtype == np.float64
    assert z["anchor_source_epoch"].dtype == np.float64
    assert z["event_kind"].dtype == np.int8
    assert z["event_source"].dtype == np.float64
    assert z["event_available"].dtype == np.float64
    assert z["event_dt_weeks"].dtype == np.float32
    assert z["control"].dtype == np.float32 and z["control"].shape[1] == 24
    assert z["control_mask"].dtype == np.float32 and z["control_mask"].shape[1] == 24
    assert z["capacity_ah"].dtype == np.float32
    assert z["score"].dtype == bool
    assert z["event_cell"].shape[0] == man["n_events"]
    assert z["control"].shape[0] == man["n_events"]
    _audit_arrays({k: z[k] for k in z.files})

    # first-event dt of each cell is measured from that cell's anchor stop.
    counts = np.bincount(z["event_cell"], minlength=z["cell_ids"].shape[0])
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    for i, start in enumerate(starts):
        if int(counts[i]) == 0:
            continue
        first = int(start)
        want = (z["event_source"][first] - z["anchor_source_epoch"][i]) / WEEK_SECONDS
        assert abs(float(z["event_dt_weeks"][first]) - want) < 1e-5, \
            "cell %d first dt" % i
        assert z["event_source"][first] >= z["anchor_source_epoch"][i] - 1e-6

    # the real loader must accept it unchanged.
    from a2_train import load_prepared_sequences
    train_seqs, val_seqs, man2 = load_prepared_sequences(man_path)
    assert len(train_seqs) + len(val_seqs) == man["n_cells"]
    assert set(s["cell_id"] for s in train_seqs) & set(
        s["cell_id"] for s in val_seqs) == set()
    by_id = {c["cell_id"]: c for c in man["cells"]}
    for seq in train_seqs + val_seqs:
        assert abs(seq["q_ref_ah"] - by_id[seq["cell_id"]]["q_ref_ah"]) < 1e-12
        assert abs(seq["anchor"]["source_epoch"]
                   - by_id[seq["cell_id"]]["anchor_source_epoch"]) < 1e-3
        for event in seq["events"]:
            if event["kind"] == "cycle":
                assert len(event["control"]) == 24
                assert len(event["control_mask"]) == 24
            else:
                assert event["score"] is True
    std = TrainControlStandardizer().fit(train_seqs)
    assert std.control_dim == 24
    from a2_targets import A2SequenceBatch
    batch = A2SequenceBatch.from_sequences(train_seqs)
    assert tuple(batch.control.shape[1:]) == (int(batch.kind.shape[1]), CONTROL_DIM)
    assert tuple(batch.control_mask.shape) == tuple(batch.control.shape)
    for row, length in enumerate(batch.lengths):
        assert int(length) > 0
        assert set(batch.kind[row, :int(length)].tolist()) <= {1, 2}
        assert bool(batch.kind[row, int(length):].eq(0).all())
    import torch
    assert batch.score.dtype == torch.bool
    assert tuple(batch.kind.shape) == (len(train_seqs), max(batch.lengths))
    assert tuple(batch.q_ref.shape) == (len(train_seqs),)
    assert float(batch.q_ref.min()) > 0
    line("  e2e: 3 anchored cells / %d events, npz+manifest+receipt, "
         "a2_train loader round-trip OK, standardizer fits %d/24 dims"
         % (man["n_events"], 24 - std.n_constant_skipped))


def check_no_future_leakage(tmp, line):
    day = 86400.0
    base = 1_700_000_000.0
    rpts = [_rpt(0, base + 10 * day, 0.281), _rpt(1, base + 20 * day, 0.276)]
    rows = [_cycle(0, base + 11 * day, base + 11 * day + 3600,
                   base + 11 * day + 7200, base + 11 * day + 10800),
            _cycle(1, base + 21 * day, base + 21 * day + 3600,
                   base + 21 * day + 7200, base + 21 * day + 10800)]
    doc = {"cell_id": "G10C1", "role": "train", "cycles": rows}
    recs, _ = rpt_records_from_processed(_cell("G10C1", rpts), "G10C1")
    crecs, _ = cycle_records_from_features(doc, "G10C1")
    first = cell_sequence("G10C1", crecs, recs)
    mutated_rows = [dict(rows[0]), dict(rows[1])]
    mutated_rows[1] = _cycle(1, base + 21 * day, base + 21 * day + 3600,
                             base + 21 * day + 7200,
                             base + 21 * day + 10800,
                             qc=9.9, qd=9.9, vc=9.9, vd=9.9, ec=9.9, ed=9.9,
                             capc=9.9, capd=9.9, thr=19.8)
    doc2 = {"cell_id": "G10C1", "role": "train", "cycles": mutated_rows}
    crecs2, _ = cycle_records_from_features(doc2, "G10C1")
    second = cell_sequence("G10C1", crecs2, recs)
    assert len(first["events"]) == len(second["events"])
    for a, b in zip(first["events"], second["events"]):
        if a["kind"] == "cycle" and a["source_epoch"] < base + 21 * day:
            assert a["control"] == b["control"], "a later cycle changed an earlier one"
        if a["source_epoch"] >= base + 21 * day:
            assert b["control"] != a["control"], "mutation fixture did not apply"

    # cutoff-gated prefix must be identical when a future record is appended.
    q = base + 15 * day
    gated = cell_sequence("G10C1", crecs, recs, cutoff_epoch=q)
    extra = list(crecs) + [{"source_epoch": base + 16 * day,
                            "available_epoch": base + 16 * day,
                            "control": [123.0] * 24,
                            "control_mask": [1.0] * 24}]
    gated2 = cell_sequence("G10C1", extra, recs, cutoff_epoch=q)
    assert [e["source_epoch"] for e in gated["events"]] == \
           [e["source_epoch"] for e in gated2["events"]], "cutoff leaked future events"
    line("  leakage: control is per-cycle only; cutoff prefix unchanged by a "
         "future cycle")


class _OpenAudit(object):
    """Record every path touched through builtins.open while it is active."""

    def __init__(self):
        self.paths = []
        self._orig = None

    def __enter__(self):
        import builtins
        self._orig = builtins.open
        audit = self

        def patched(file, *args, **kwargs):
            try:
                if isinstance(file, (str, bytes, os.PathLike)):
                    audit.paths.append(os.path.abspath(os.fspath(file)))
            except (TypeError, ValueError):
                pass
            return audit._orig(file, *args, **kwargs)

        builtins.open = patched
        return self

    def __exit__(self, *exc_info):
        import builtins
        if self._orig is not None:
            builtins.open = self._orig
        return False

    def under(self, prefixes):
        return [x for x in self.paths
                if any(x == q or x.startswith(q + os.sep) for q in prefixes)]


def run_self_check(tmp_root=None, append_log=None):
    lines = []
    def emit(text=""):
        print(text)
        lines.append(text)
    def line(text):
        emit(text)

    emit("=" * 78)
    emit("A2 PREP self-check -- %s" % _utc_now())
    emit("mode: SYNTHETIC ONLY -- 0 payload reads, 0 fits, 0 optimizer steps")
    emit("python %s | numpy %s" % (sys.version.split()[0], np.__version__))
    emit("code_sha256: %s" % json.dumps(
        {name: hash_file(os.path.join(HERE, name)) for name in REQUIRED_CODE
         if os.path.isfile(os.path.join(HERE, name))}, sort_keys=True))
    emit("-" * 78)

    checks = [("go_gate", check_go_gate),
              ("control_table", check_control_table),
              ("anchor_asof", check_asof_and_anchor),
              ("end_to_end", check_end_to_end),
              ("no_future_leakage", check_no_future_leakage)]
    passed = failed = 0
    own_tmp = tmp_root is None
    root = tmp_root or tempfile.mkdtemp(prefix="a2_prep_selfcheck_")
    real_root = os.environ.get("A2_PREP_ROOT", DEFAULT_ROOT)
    forbidden = [os.path.join(real_root, "data"),
                 os.path.join(real_root, "reports"),
                 os.path.join(real_root, "automation"),
                 os.path.join(real_root, "experiments",
                              "trajectory_b2_joint_marked_renewal_20261021")]
    audit = _OpenAudit()
    try:
        with audit:
            for name, fn in checks:
                try:
                    fn(root, line)
                    emit("[PASS] %-18s %s" % (name, ""))
                    passed += 1
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    emit("[FAIL] %-18s %s" % (name, exc))
                    traceback.print_exc(file=sys.stdout)
            bad = audit.under(forbidden)
            if bad:
                failed += 1
                emit("[FAIL] %-18s opened %d forbidden payload path(s): %r"
                     % ("no_payload_read", len(bad), bad[:3]))
            else:
                passed += 1
                emit("[PASS] %-18s %d paths opened, 0 under data/, reports/, "
                     "automation/ or prep_inputs/ (only this directory and %s)"
                     % ("no_payload_read", len(audit.paths), os.path.basename(root)))
    finally:
        if own_tmp:
            import shutil
            shutil.rmtree(root, ignore_errors=True)
    emit("-" * 78)
    emit("SUMMARY: %d passed, %d failed, %d total" % (passed, failed, passed + failed))
    emit("NO PAYLOAD READ. NO TRAINING. NO FIT. NO OPTIMIZER STEP. NO GO CREATED.")
    emit("NO GO CONSUMED. NO RECEIPT WRITTEN BY THE SELF-CHECK.")
    emit("RESULT: %s" % ("OK" if failed == 0 else "FAILED"))
    if append_log:
        block = ("\n===== a2_prep self-check %s =====\n" % _utc_now()) + \
                "\n".join(lines) + "\n"
        with open(append_log, "a", encoding="utf-8") as fh:
            fh.write(block)
        print("APPENDED %d lines to %s (append-only, no truncation)"
              % (len(lines) + 2, append_log))
    return 0 if failed == 0 else 1


# ------------------------------------------------------------------------ main
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="A2 PREP builder: synthetic self-check by default; a real "
                    "build only under an APPROVED PREP-only GO.")
    parser.add_argument("--self-check", action="store_true",
                        help="run the synthetic build fixtures (default behaviour)")
    parser.add_argument("--go", default=None,
                        help="path to an APPROVED PREP-only GO json")
    parser.add_argument("--append-log", default=None,
                        help="append the self-check output to this log (append-only)")
    parser.add_argument("--go-template", action="store_true",
                        help="print a GO skeleton with the current code/manifest "
                             "hashes and exit (writes nothing)")
    parser.add_argument("--no-env-probe", action="store_true",
                        help="with --go-template: do not hash the two manifests")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.go_template:
        env = default_env() if not args.no_env_probe else None
        if env is None:
            print(json.dumps({"code_sha256": {
                name: hash_file(os.path.join(HERE, name)) for name in REQUIRED_CODE},
                "processed_manifest": {"path": default_env().processed_manifest,
                                       "sha256": "<sha256 of that file>"},
                "cycling_manifest": {"path": default_env().cycling_manifest,
                                     "sha256": "<sha256 of that file>"},
                "note": "hashes of the two manifests were not computed"}, indent=2))
            return 0
        template = _go_template(env, fixture=None,
                                out_dir="/path/to/fresh/prep_out",
                                receipt="/path/to/fresh/prep_receipt.json")
        print(json.dumps(_json_safe(template), indent=2))
        return 0
    if args.go:
        return run_prep(args.go)
    return run_self_check(append_log=args.append_log)


if __name__ == "__main__":
    sys.exit(main())
