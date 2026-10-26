#!/usr/bin/env python3
"""A2 C3 development inference (source63) -- code + synthetic self-check only.

What this file does
-------------------
* Reads the 63 C3 development cells only (cohort role == "development"), their
  frozen processed RPT JSON and their frozen cycling feature asset.
* Reuses a2_prep.py's 24-dimensional control extraction and cycle
  completion/arrival construction by importing its adapters.  a2_prep.py itself
  is NOT modified and its hard C3 refusal remains in force: this entry point is
  the separately authorised C3 consumer.
* Builds the same as-of query grid as the B2 C3 runner (raw / sparse2 / delay7d,
  anchor = last arrived valid RPT, >= 3 visible records, dedupe by
  (arm, anchor source index), skip queries whose visible capacity is already
  <= 0.20 Ah).
* For each A2 checkpoint (full / time / noRPTupdate) it filters the state at the
  query with a2_targets.replay_asof-compatible recurrence, advances the state by
  the observed next-source-RPT gap under the held-recent control policy, and
  reports the Gaussian next-capacity NLL in Ah plus fixed-calendar-horizon
  moments (1/4/12/32 weeks; scored only when a source RPT observation exists
  within the declared tolerance).
* Real inference requires an APPROVED_C3_INFERENCE GO with exact code /
  cohort / manifest / checkpoint hashes.  A refused GO writes nothing and does
  not consume the GO.  Default mode is --self-check: fabricated cells only,
  0 real payload reads, 0 checkpoint files, 0 fits, 0 optimizer steps.

Reuse and the two minimal wrappers
----------------------------------
a2_prep.cycle_control() and a2_prep.cycle_completion_epoch() are imported and
used unchanged.  The two record adapters
a2_prep.rpt_records_from_processed() and
a2_prep.cycle_records_from_features() hard-code role == "train" because PREP
must never touch C3.  C3 inference is authorised by the GO, so this file passes
a shallow role-projected copy (role="train") to those unmodified adapters after
independently proving the true role is "development" in the cohort, the
processed data manifest, the cycling manifest and the asset itself.  Only the
literal role gate is projected; every other adapter validation and all control
semantics stay in a2_prep.py.  See _development_rpt_records() and
_development_cycle_records().

The incremental as-of walker
----------------------------
a2_targets.replay_asof() is the authoritative as-of filter but re-filters from
the anchor for every query.  At C3 scale (63 cells x 3 arms x 3 models x 5
horizons) that is O(Q*E) and unnecessarily slow.  AsOfWalker implements the
same recurrence incrementally (one pass over the cell's events, state snapshot
at each monotone query), including the delay7d mixed-visibility case.  It is
checked elementwise against a2_targets.replay_asof() in --self-check for every
arm/model/query, which is why the fast path is allowed to replace the reference
only at inference time.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import shutil
import signal
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np
import torch

import a2_prep
import a2_targets
from a2_model import CONTROL_DIM, build_model
from a2_targets import LOG_2PI, WEEK_SECONDS, hash_file, replay_asof

# ---------------------------------------------------------------------------
# Frozen contract
# ---------------------------------------------------------------------------
SCHEMA = "A2_C3_INFERENCE_V1"
RECEIPT_SCHEMA = "A2_C3_INFERENCE_RECEIPT_V1"
OWNER_THREAD_ID = "01a15c3a-1a06-7d61-8517-27b70b246183"
DATA_SCOPE = "C3_source63_development_only_no_C4_no_raw"
GO_STATUS = "APPROVED_C3_INFERENCE"
DEFAULT_DEV_CELLS = 63
MIN_VISIBLE_RECORDS = 3
THRESHOLD_AH = 0.20
DELAY7D_SECONDS = 7.0 * 86400.0
HORIZONS_WEEKS = (1.0, 4.0, 12.0, 32.0)
HORIZON_TOLERANCE_WEEKS = 0.5
QUERY_ARMS = ("raw", "sparse2", "delay7d")
REQUIRED_CODE = ("a2_infer.py", "a2_model.py", "a2_targets.py",
                 "a2_prep.py", "a2_fastdata.py")
MODEL_ARMS = {
    "full": {"label": "A2_full_F2", "use_cycle": True, "use_rpt": True},
    "time": {"label": "A2_time_only", "use_cycle": False, "use_rpt": True},
    "noRPTupdate": {"label": "A2_no_RPT_update", "use_cycle": True,
                    "use_rpt": False},
}
_MODEL_ALIASES = {
    "full": "full", "a2_full_f2": "full",
    "time": "time", "a2_time_only": "time", "time_only": "time",
    "norptupdate": "noRPTupdate", "no_rpt_update": "noRPTupdate",
    "a2_no_rpt_update": "noRPTupdate", "no_rpt": "noRPTupdate",
}


def _canonical_model_key(value):
    text = str(value).strip()
    return _MODEL_ALIASES.get(text.lower(), text)
DEFAULT_ROOT = "/home/yndx/zxk/rul"


class InferenceError(RuntimeError):
    """Refusal or schema violation in the inference path."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _utc(epoch):
    return datetime.fromtimestamp(float(epoch), timezone.utc).isoformat()


def _finite(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)))


def _finite_or_none(value):
    return float(value) if _finite(value) else None


def _is_sha(value):
    if not isinstance(value, str):
        return False
    text = value.strip().lower()
    return len(text) == 64 and all(c in "0123456789abcdef" for c in text)


def _json_safe(obj):
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        value = float(obj)
        return value if math.isfinite(value) else None
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    return obj


def _atomic_json(path, payload):
    text = json.dumps(_json_safe(payload), indent=2, ensure_ascii=False) + "\n"
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return path


def _json_load(path, what):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise InferenceError("%s is not readable JSON: %s" % (what, exc))


def _abs_path(path):
    if not isinstance(path, str) or not path.strip():
        return None
    return os.path.abspath(os.path.expanduser(path))


def _under(path, root):
    path = os.path.realpath(path)
    root = os.path.realpath(root)
    return path == root or path.startswith(root + os.sep)


def _path_has_raw_component(path):
    parts = [p.lower() for p in os.path.realpath(path).split(os.sep)]
    return "raw" in parts


class ReadStats(object):
    """Audit counters for the receipt; never used to authorise reads."""

    def __init__(self):
        self.files_read = 0
        self.bytes_read = 0
        self.preflight_hash_files = 0
        self.preflight_hash_bytes = 0
        self.processed_cells = 0
        self.cycling_cells = 0
        self.checkpoint_files = 0
        self.rpt_assets = 0
        self.raw_reads = 0
        self.c4_reads = 0

    def note_file(self, path, count_bytes=True):
        self.files_read += 1
        if count_bytes:
            try:
                self.bytes_read += int(os.path.getsize(path))
            except OSError:
                pass

    def note_preflight_hash(self, path):
        self.preflight_hash_files += 1
        try:
            self.preflight_hash_bytes += int(os.path.getsize(path))
        except OSError:
            pass


def _read_bytes(path, what, stats=None, allowed_roots=None,
                forbid_payload=True):
    real = os.path.realpath(path)
    if allowed_roots is not None:
        if not any(_under(real, root) for root in allowed_roots):
            raise InferenceError("%s is outside the authorised roots: %s"
                                 % (what, path))
    if forbid_payload:
        low = real.lower()
        if _path_has_raw_component(real) or low.endswith((".pt", ".pth", ".ckpt")):
            raise InferenceError("%s points at a forbidden payload/checkpoint: %s"
                                 % (what, path))
    if not os.path.isfile(real):
        raise InferenceError("%s is not a regular file: %s" % (what, path))
    with open(real, "rb") as fh:
        blob = fh.read()
    if stats is not None:
        stats.note_file(real)
    return blob


def _hash_path(path):
    if not os.path.isfile(path):
        raise InferenceError("file not found: %s" % path)
    return hash_file(path)


# ---------------------------------------------------------------------------
# GO document (pure checks) and bindings (files/hashes)
# ---------------------------------------------------------------------------
def _go_ref(go, names):
    for name in names:
        node = go.get(name)
        if isinstance(node, dict) and ("path" in node or "sha256" in node):
            return node.get("path"), node.get("sha256"), name
    for name in names:
        path = go.get(name + "_path")
        sha = go.get(name + "_sha256")
        if path is not None or sha is not None:
            return path, sha, name
    return None, None, names[0]


def _check_abs_ref(path, sha, label, problems):
    if not isinstance(path, str) or not os.path.isabs(path):
        problems.append("%s.path must be an absolute path, got %r"
                        % (label, path))
    if not _is_sha(sha):
        problems.append("%s.sha256 must be a 64-hex digest, got %r"
                        % (label, sha))
    return path, sha


def _validate_query_contract(go, problems):
    qc = go.get("query_contract")
    contract = {
        "arms": list(QUERY_ARMS),
        "horizons_weeks": list(HORIZONS_WEEKS),
        "min_visible_records": MIN_VISIBLE_RECORDS,
        "query_threshold_ah": THRESHOLD_AH,
        "delay7d_seconds": DELAY7D_SECONDS,
        "horizon_tolerance_weeks": HORIZON_TOLERANCE_WEEKS,
        "dedupe": "(arm, query_anchor_source_rpt_index)",
    }
    if qc is None:
        return contract
    if not isinstance(qc, dict):
        problems.append("query_contract must be an object")
        return contract
    if "arms" in qc:
        arms = qc.get("arms")
        if not isinstance(arms, list) or sorted(map(str, arms)) != sorted(QUERY_ARMS):
            problems.append("query_contract.arms must be %r" % (list(QUERY_ARMS),))
        else:
            contract["arms"] = [str(a) for a in arms]
    if "horizons_weeks" in qc:
        try:
            horizons = tuple(sorted(float(x) for x in qc["horizons_weeks"]))
        except (TypeError, ValueError):
            horizons = None
            problems.append("query_contract.horizons_weeks must be numbers")
        if horizons is not None and horizons != tuple(sorted(HORIZONS_WEEKS)):
            problems.append("query_contract.horizons_weeks must be %r"
                            % (list(HORIZONS_WEEKS),))
        elif horizons is not None:
            contract["horizons_weeks"] = list(horizons)
    for key, expected in (("min_visible_records", MIN_VISIBLE_RECORDS),
                          ("query_threshold_ah", THRESHOLD_AH),
                          ("delay7d_seconds", DELAY7D_SECONDS)):
        if key in qc:
            try:
                value = float(qc[key])
            except (TypeError, ValueError):
                problems.append("query_contract.%s must be numeric" % key)
                continue
            if abs(value - float(expected)) > 1e-12:
                problems.append("query_contract.%s must be %r, got %r"
                                % (key, expected, qc[key]))
            else:
                contract[key] = value
    if "horizon_tolerance_weeks" in qc:
        try:
            tol = float(qc["horizon_tolerance_weeks"])
        except (TypeError, ValueError):
            tol = None
            problems.append("query_contract.horizon_tolerance_weeks must be numeric")
        if tol is not None:
            if not (0.0 < tol <= 2.0):
                problems.append("query_contract.horizon_tolerance_weeks must be in (0, 2]")
            else:
                contract["horizon_tolerance_weeks"] = tol
    if "dedupe" in qc:
        text = str(qc["dedupe"])
        if text != contract["dedupe"]:
            problems.append("query_contract.dedupe must be %r"
                            % contract["dedupe"])
        contract["dedupe"] = text
    return contract


def _normalise_checkpoints(go, problems):
    node = go.get("checkpoints")
    out = {}
    if isinstance(node, dict):
        for key, spec in node.items():
            out[_canonical_model_key(key)] = spec
    elif isinstance(node, list):
        for item in node:
            if not isinstance(item, dict):
                problems.append("checkpoints list entries must be objects")
                continue
            key = (item.get("model") or item.get("model_key")
                   or item.get("arm") or item.get("name"))
            key = _canonical_model_key(key) if key is not None else None
            if key is None:
                problems.append("checkpoints list entry has no model key")
                continue
            out[str(key)] = item
    else:
        problems.append("checkpoints must be an object or a list")
        return {}
    if set(out) != set(MODEL_ARMS):
        problems.append("checkpoints must pin exactly %r, got %r"
                        % (sorted(MODEL_ARMS), sorted(out)))
    normalised = {}
    for key in sorted(MODEL_ARMS):
        spec = out.get(key)
        if not isinstance(spec, dict):
            problems.append("checkpoint %s is missing or not an object" % key)
            continue
        path = spec.get("path")
        sha = spec.get("sha256")
        if not isinstance(path, str) or not path.strip():
            problems.append("checkpoint %s has no path" % key)
            continue
        if not _is_sha(sha):
            problems.append("checkpoint %s has no 64-hex sha256" % key)
            continue
        normalised[key] = {"path": path, "sha256": str(sha).strip().lower()}
        report = spec.get("fit_report")
        if isinstance(report, dict):
            normalised[key]["fit_report"] = {
                "path": report.get("path"),
                "sha256": report.get("sha256"),
            }
    return normalised


def validate_go_document(go, expected_cells=DEFAULT_DEV_CELLS):
    """Pure GO checks; no filesystem access and no writes."""
    problems = []
    if not isinstance(go, dict):
        return ["GO must be a JSON object"], None
    status = go.get("status")
    if status != GO_STATUS:
        problems.append("GO status is %r, not %s" % (status, GO_STATUS))
    if go.get("allow_inference") is not True:
        problems.append("GO must set allow_inference=true")
    if go.get("allow_fit") is not False:
        problems.append("GO must set allow_fit=false explicitly")
    if go.get("allow_train") is True:
        problems.append("GO must not authorise training (allow_train=true)")
    for key in ("fit_count", "max_fits", "fits"):
        if key in go and go.get(key) not in (0, None):
            problems.append("GO %s must be 0 for inference, got %r"
                            % (key, go.get(key)))
    for key in ("consumed_at", "consumed", "consumed_utc", "consumed_by"):
        if go.get(key):
            problems.append("GO already consumed (%s)" % key)
    if str(go.get("owner_thread_id")) != OWNER_THREAD_ID:
        problems.append("GO owner_thread_id must be %s" % OWNER_THREAD_ID)
    if str(go.get("data_scope")) != DATA_SCOPE:
        problems.append("GO data_scope must be %s" % DATA_SCOPE)
    device = str(go.get("device", "")).strip().lower()
    if device != "cpu":
        problems.append("GO device must be 'cpu' for the A2 CPU model, got %r"
                        % (go.get("device"),))
    try:
        runtime = int(go.get("max_runtime_seconds"))
    except (TypeError, ValueError):
        runtime = None
        problems.append("GO max_runtime_seconds must be an integer")
    if runtime is not None and not (60 <= runtime <= 21600):
        problems.append("GO max_runtime_seconds must be in 60..21600, got %r"
                        % runtime)
    try:
        expected = int(go.get("expected_cell_count", expected_cells))
    except (TypeError, ValueError):
        expected = None
        problems.append("GO expected_cell_count must be an integer")
    if expected is not None and expected != int(expected_cells):
        problems.append("GO expected_cell_count must be %d, got %r"
                        % (expected_cells, go.get("expected_cell_count")))

    code = (go.get("code_sha256") or go.get("code_hashes")
            or go.get("source_sha256"))
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
            if base in code_norm:
                problems.append("code_sha256 lists %s twice" % base)
            code_norm[base] = str(digest).strip().lower()
        for name in REQUIRED_CODE:
            if name not in code_norm:
                problems.append("GO code_sha256 does not pin %s" % name)

    refs = {}
    for label, names in (
            ("cohort", ("cohort", "cohort_manifest")),
            ("data_manifest", ("data_manifest", "manifest", "processed_manifest")),
            ("cycling_manifest", ("cycling_manifest", "cycling_features_manifest")),
            ("rpt_manifest", ("rpt_manifest", "rpt_features_manifest"))):
        path, sha, used = _go_ref(go, names)
        if label == "cycling_manifest" and path is None and sha is None:
            # Optional.  If absent, the frozen default cycling manifest next to
            # the cohort is used and its SHA256 is recorded (not GO-pinned).
            refs[label] = {"path": None, "sha256": None,
                           "go_key": "derived_default", "go_pinned": False}
            continue
        _check_abs_ref(path, sha, label, problems)
        refs[label] = {"path": path, "sha256": sha, "go_key": used,
                       "go_pinned": True}
    for label, node in (("cohort", go.get("cohort")),
                        ("data_manifest", go.get("data_manifest")),
                        ("cycling_manifest", go.get("cycling_manifest")),
                        ("rpt_manifest", go.get("rpt_manifest"))):
        if isinstance(node, dict) and node.get("path") and not node.get("sha256"):
            problems.append("%s.sha256 is required" % label)

    checkpoints = _normalise_checkpoints(go, problems)
    output_dir = go.get("output_dir", go.get("output_path"))
    receipt_path = go.get("receipt_path")
    if not isinstance(output_dir, str) or not os.path.isabs(output_dir):
        problems.append("GO output_dir must be an absolute path")
    if not isinstance(receipt_path, str) or not os.path.isabs(receipt_path):
        problems.append("GO receipt_path must be an absolute path")
    data_root = go.get("data_root")
    if data_root is not None and (not isinstance(data_root, str)
                                  or not os.path.isabs(data_root)):
        problems.append("GO data_root must be an absolute path when present")
    expires = go.get("expires_utc")
    if expires is not None:
        try:
            if a2_targets.epoch_seconds(expires) < time.time() - 1.0:
                problems.append("GO expired at %s" % expires)
        except (TypeError, ValueError):
            problems.append("GO expires_utc is not a timestamp: %r" % (expires,))
    issued = go.get("issued_utc")
    if issued is not None:
        try:
            a2_targets.epoch_seconds(issued)
        except (TypeError, ValueError):
            problems.append("GO issued_utc is not a timestamp: %r" % (issued,))
    contract = _validate_query_contract(go, problems)
    norm = {
        "raw": go,
        "status": status,
        "device": "cpu",
        "max_runtime_seconds": runtime,
        "expected_cell_count": expected,
        "code_sha256": code_norm,
        "sources": refs,
        "checkpoints": checkpoints,
        "output_dir": _abs_path(output_dir),
        "receipt_path": _abs_path(receipt_path),
        "data_root": _abs_path(data_root) if data_root else None,
        "query_contract": contract,
        "request_id": go.get("request_id"),
    }
    return problems, norm


def _check_fresh_dir(path, label, problems):
    real = os.path.realpath(path)
    if os.path.exists(real):
        if not os.path.isdir(real):
            problems.append("%s exists and is not a directory: %s" % (label, real))
            return None
        if os.listdir(real):
            problems.append("%s must be fresh/empty: %s" % (label, real))
            return None
    parent = os.path.dirname(real)
    if not os.path.isdir(parent):
        problems.append("%s parent directory does not exist: %s" % (label, parent))
        return None
    return real


def _check_fresh_file(path, label, problems):
    real = os.path.abspath(path)
    if os.path.exists(real):
        problems.append("%s already exists (refuse to overwrite): %s"
                        % (label, real))
        return None
    parent = os.path.dirname(real)
    if not os.path.isdir(parent):
        problems.append("%s parent directory does not exist: %s" % (label, parent))
        return None
    return real


def _build_dev_specs(cohort, data_manifest, cycling_manifest, rpt_manifest,
                     data_root, expected_cells):
    """Validate roles/ids/paths/SHA strings; return 63 dev specs.  No asset read."""
    problems = []
    if not isinstance(cohort, dict):
        raise InferenceError("cohort is not an object")
    roles = cohort.get("roles")
    if not isinstance(roles, dict) or not roles:
        raise InferenceError("cohort has no roles map")
    if str(cohort.get("status")) != "FROZEN_BEFORE_ANY_CAPACITY_PAYLOAD":
        raise InferenceError("cohort status is not frozen")
    dev = sorted(str(cid) for cid, role in roles.items()
                 if str(role) == "development")
    if len(dev) != int(expected_cells):
        problems.append("cohort yields %d development cells, expected %d"
                        % (len(dev), int(expected_cells)))
    if any(cid.endswith("C4") for cid in dev):
        problems.append("cohort development set contains a C4 cell")
    if any(not cid.endswith("C3") for cid in dev):
        problems.append("cohort development set contains a non-C3 cell")
    counts = cohort.get("counts") or {}
    if int(counts.get("development", -1)) != len(dev):
        problems.append("cohort counts.development is inconsistent")

    if not isinstance(data_manifest, dict):
        raise InferenceError("data manifest is not an object")
    if str(data_manifest.get("status")) != "PASS":
        problems.append("data manifest status is not PASS")
    files = data_manifest.get("files")
    if not isinstance(files, dict):
        raise InferenceError("data manifest has no files map")
    role_counts = data_manifest.get("role_counts") or {}
    if int(role_counts.get("development", -1)) != len(dev):
        problems.append("data manifest role_counts.development is inconsistent")
    if int(role_counts.get("locked", 0)) != 0:
        problems.append("data manifest reports locked cells")
    constraints = data_manifest.get("constraints") or {}
    if constraints.get("raw_curves_read") is not False:
        problems.append("data manifest does not forbid raw curve reads")
    if constraints.get("locked_payloads_read") is not False:
        problems.append("data manifest does not forbid locked payload reads")
    dev_in_manifest = sorted(str(c) for c, entry in files.items()
                             if isinstance(entry, dict)
                             and str(entry.get("role")) == "development")
    if dev_in_manifest != dev:
        problems.append("data manifest development set differs from cohort")

    if not isinstance(cycling_manifest, dict):
        raise InferenceError("cycling manifest is not an object")
    if str(cycling_manifest.get("status")) != "SUCCESS":
        problems.append("cycling manifest status is not SUCCESS")
    if int(cycling_manifest.get("C4", 0) or 0) != 0:
        problems.append("cycling manifest reports C4 cells")
    if int(cycling_manifest.get("development", -1)) != len(dev):
        problems.append("cycling manifest development count is inconsistent")
    cyc_inv = cycling_manifest.get("inventory")
    if not isinstance(cyc_inv, list):
        raise InferenceError("cycling manifest has no inventory list")
    cyc_map = {}
    for entry in cyc_inv:
        if not isinstance(entry, dict):
            problems.append("cycling inventory entry is not an object")
            continue
        cid = str(entry.get("cell_id"))
        if cid in cyc_map:
            problems.append("cycling inventory lists %s twice" % cid)
        cyc_map[cid] = entry
    if sorted(c for c, e in cyc_map.items()
               if str(e.get("role")) == "development") != dev:
        problems.append("cycling manifest development set differs from cohort")

    if not isinstance(rpt_manifest, dict):
        raise InferenceError("RPT manifest is not an object")
    if str(rpt_manifest.get("status")) != "ALL188_FEATURE_CACHE_COMPLETE":
        problems.append("RPT manifest status is not the frozen cache status")
    if int(rpt_manifest.get("development", -1)) != len(dev):
        problems.append("RPT manifest development count is inconsistent")
    if int(rpt_manifest.get("locked", 0)) != 0:
        problems.append("RPT manifest reports locked cells")
    rpt_inv = rpt_manifest.get("inventory")
    if not isinstance(rpt_inv, list):
        raise InferenceError("RPT manifest has no inventory list")
    rpt_map = {}
    for entry in rpt_inv:
        if not isinstance(entry, dict):
            problems.append("RPT inventory entry is not an object")
            continue
        cid = str(entry.get("cell_id"))
        if cid in rpt_map:
            problems.append("RPT inventory lists %s twice" % cid)
        rpt_map[cid] = entry
    if sorted(c for c, e in rpt_map.items()
               if str(e.get("role")) == "development") != dev:
        problems.append("RPT manifest development set differs from cohort")

    processed_root = os.path.join(data_root, "data", "processed",
                                  "ISU_ILCC_DataV2_v1")
    cycling_root = os.path.join(data_root, "reports",
                                "multisource_20261021_signals")
    rpt_root = os.path.join(cycling_root, "all188_rpt_features_v1")
    for root, label in ((processed_root, "processed root"),
                        (cycling_root, "cycling root"),
                        (rpt_root, "RPT root")):
        if not os.path.isdir(root):
            problems.append("%s does not exist: %s" % (label, root))

    specs = []
    for cid in dev:
        p_entry = files.get(cid) or {}
        c_entry = cyc_map.get(cid) or {}
        r_entry = rpt_map.get(cid) or {}
        if str(p_entry.get("role")) != "development":
            problems.append("processed asset %s role is not development" % cid)
        if str(c_entry.get("role")) != "development":
            problems.append("cycling asset %s role is not development" % cid)
        if str(r_entry.get("role")) != "development":
            problems.append("RPT asset %s role is not development" % cid)
        p_path = p_entry.get("path")
        c_path = c_entry.get("path")
        r_path = r_entry.get("path")
        p_sha = p_entry.get("sha256")
        c_sha = c_entry.get("sha256")
        r_sha = r_entry.get("sha256")
        p_real = c_real = r_real = None
        p_sha_n = c_sha_n = r_sha_n = None
        for label, path, sha, root, suffix in (
                ("processed", p_path, p_sha, processed_root, ".json"),
                ("cycling", c_path, c_sha, cycling_root, ".json.gz"),
                ("RPT", r_path, r_sha, rpt_root, ".json")):
            if not isinstance(path, str) or not path.strip():
                problems.append("%s asset %s has no path" % (label, cid))
                continue
            if not os.path.isabs(path):
                path = os.path.join(data_root, path)
            real = os.path.realpath(path)
            if not _under(real, root):
                problems.append("%s asset %s lives outside %s"
                                % (label, cid, root))
            if os.path.basename(real) != cid + suffix:
                problems.append("%s asset %s basename mismatch: %s"
                                % (label, cid, real))
            if not os.path.isfile(real):
                problems.append("%s asset %s is missing: %s"
                                % (label, cid, real))
            if not _is_sha(sha):
                problems.append("%s asset %s has no 64-hex sha256"
                                % (label, cid))
                continue
            if label == "processed":
                p_real, p_sha_n = real, str(sha).lower()
            elif label == "cycling":
                c_real, c_sha_n = real, str(sha).lower()
            else:
                r_real, r_sha_n = real, str(sha).lower()
        if None in (p_real, c_real, r_real):
            continue
        specs.append({
            "cell_id": cid,
            "processed_path": p_real,
            "processed_sha256": p_sha_n,
            "cycling_path": c_real,
            "cycling_sha256": c_sha_n,
            "rpt_path": r_real,
            "rpt_sha256": r_sha_n,
        })
    if problems:
        raise InferenceError("\n".join(problems))
    return specs, {"processed_root": processed_root,
                   "cycling_root": cycling_root,
                   "rpt_root": rpt_root}


def _load_manifest_sources(norm, stats):
    """Read and validate cohort + 3 manifests; return parsed documents."""
    srcs = norm["sources"]
    docs = {}
    for label in ("cohort", "data_manifest", "cycling_manifest", "rpt_manifest"):
        ref = srcs[label]
        path = ref["path"]
        if not os.path.isfile(path):
            raise InferenceError("%s not found: %s" % (label, path))
        digest = _hash_path(path)
        stats.note_preflight_hash(path)
        if digest != ref["sha256"].lower():
            raise InferenceError("%s sha256 mismatch: go=%s actual=%s"
                                 % (label, ref["sha256"], digest))
        docs[label] = _json_load(path, label)
        docs[label + "_path"] = os.path.abspath(path)
        docs[label + "_sha256"] = digest
    return docs


def _load_code_hashes(norm, stats):
    got = {}
    for name in REQUIRED_CODE:
        path = os.path.join(HERE, name)
        if not os.path.isfile(path):
            raise InferenceError("missing code file %s" % path)
        digest = _hash_path(path)
        stats.note_preflight_hash(path)
        expected = norm["code_sha256"].get(name)
        if expected is None:
            raise InferenceError("GO does not pin %s" % name)
        if digest != expected:
            raise InferenceError("code_sha256 mismatch for %s: go=%s actual=%s"
                                 % (name, expected, digest))
        got[name] = digest
    return got


def _load_checkpoint_model(key, spec, stats):
    path = spec["path"]
    if not os.path.isabs(path):
        path = os.path.join(HERE, path)
    if not os.path.isfile(path):
        raise InferenceError("checkpoint %s not found: %s" % (key, path))
    digest = _hash_path(path)
    stats.note_preflight_hash(path)
    stats.checkpoint_files += 1
    if digest != spec["sha256"]:
        raise InferenceError("checkpoint %s sha256 mismatch: go=%s actual=%s"
                             % (key, spec["sha256"], digest))
    try:
        try:
            obj = torch.load(path, map_location="cpu", weights_only=True)
        except TypeError:
            obj = torch.load(path, map_location="cpu")
    except Exception as exc:  # noqa: BLE001
        raise InferenceError("checkpoint %s is not loadable: %s" % (key, exc))
    if isinstance(obj, dict) and "state_dict" in obj:
        obj = obj["state_dict"]
    if not isinstance(obj, dict):
        raise InferenceError("checkpoint %s is not a state_dict" % key)
    model = build_model(seed=42)
    try:
        model.load_state_dict(obj, strict=True)
    except Exception as exc:  # noqa: BLE001
        raise InferenceError("checkpoint %s does not match A2StateModel: %s"
                             % (key, exc))
    model.eval()
    for name, param in model.named_parameters():
        if not torch.all(torch.isfinite(param)):
            raise InferenceError("checkpoint %s has non-finite parameter %s"
                                 % (key, name))
    info = {
        "path": os.path.abspath(path),
        "sha256": digest,
        "model_arm": MODEL_ARMS[key]["label"],
        "use_cycle": MODEL_ARMS[key]["use_cycle"],
        "use_rpt": MODEL_ARMS[key]["use_rpt"],
        "parameters": int(sum(p.numel() for p in model.parameters())),
        "obs_sigma_ah": float(model.obs_sigma().detach()),
        "control_mean_is_identity": bool(torch.equal(
            model.control_mean, torch.zeros_like(model.control_mean))),
        "control_scale_is_identity": bool(torch.equal(
            model.control_scale, torch.ones_like(model.control_scale))),
    }
    return model, info


def validate_go_bindings(norm, stats=None):
    """All file/hash/role/output checks before any write.  Returns binding."""
    stats = stats or ReadStats()
    problems = []
    binding = dict(norm)
    try:
        code_hashes = _load_code_hashes(norm, stats)
    except InferenceError as exc:
        return None, [str(exc)]
    binding["code_sha256"] = code_hashes

    cyc_ref = norm["sources"]["cycling_manifest"]
    if not cyc_ref.get("path"):
        cohort_path = norm["sources"]["cohort"]["path"]
        base_root = norm.get("data_root") or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(cohort_path))))
        default_cyc = os.path.join(base_root, "reports",
                                   "multisource_20261021_signals",
                                   "cycling_all188_feature_manifest.json")
        if not os.path.isfile(default_cyc):
            return None, ["cycling_manifest is absent from the GO and the "
                          "default cycling manifest is missing: %s" % default_cyc]
        digest = _hash_path(default_cyc)
        stats.note_preflight_hash(default_cyc)
        norm["sources"]["cycling_manifest"] = {
            "path": default_cyc, "sha256": digest,
            "go_key": "derived_default", "go_pinned": False}
        binding["sources"] = dict(norm["sources"])

    try:
        docs = _load_manifest_sources(norm, stats)
    except InferenceError as exc:
        return None, [str(exc)]
    binding["source_docs"] = docs
    binding["sources"] = {
        name: {"path": docs[name + "_path"], "sha256": docs[name + "_sha256"]}
        for name in ("cohort", "data_manifest", "cycling_manifest", "rpt_manifest")
    }

    data_root = norm.get("data_root")
    if not data_root:
        cohort_path = binding["sources"]["cohort"]["path"]
        data_root = os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(cohort_path))))
    data_root = os.path.realpath(data_root)
    if not os.path.isdir(data_root):
        return None, ["data_root does not exist: %s" % data_root]
    binding["data_root"] = data_root

    try:
        dev_specs, roots = _build_dev_specs(
            docs["cohort"], docs["data_manifest"], docs["cycling_manifest"],
            docs["rpt_manifest"], data_root, norm["expected_cell_count"])
    except InferenceError as exc:
        return None, [str(exc)]
    binding["dev_specs"] = dev_specs
    binding["roots"] = roots

    # Hash every development asset before the output directory exists.
    for spec in dev_specs:
        for path_key, sha_key in (("processed_path", "processed_sha256"),
                                  ("cycling_path", "cycling_sha256")):
            path = spec[path_key]
            digest = _hash_path(path)
            stats.note_preflight_hash(path)
            if digest != spec[sha_key]:
                problems.append("%s sha256 mismatch for %s: manifest=%s actual=%s"
                                % (path_key, spec["cell_id"], spec[sha_key],
                                   digest))
        if not os.path.isfile(spec["rpt_path"]):
            problems.append("RPT asset missing for %s: %s"
                            % (spec["cell_id"], spec["rpt_path"]))
    if problems:
        return None, problems

    models = {}
    checkpoint_info = {}
    for key in sorted(MODEL_ARMS):
        try:
            model, info = _load_checkpoint_model(key, norm["checkpoints"][key], stats)
        except InferenceError as exc:
            problems.append(str(exc))
            continue
        models[key] = model
        checkpoint_info[key] = info
    if problems:
        return None, problems
    binding["models"] = models
    binding["checkpoint_info"] = checkpoint_info

    out_dir = _check_fresh_dir(norm["output_dir"], "output_dir", problems)
    receipt = _check_fresh_file(norm["receipt_path"], "receipt_path", problems)
    if out_dir:
        binding["output_dir"] = out_dir
    if receipt:
        binding["receipt_path"] = receipt
    if out_dir and receipt and os.path.realpath(out_dir) == os.path.realpath(receipt):
        problems.append("output_dir and receipt_path must differ")
    # NOTE: data_root itself is NOT forbidden (the A2 experiment directory
    # lives under it); only the read-only data/reports trees are.
    forbidden = [roots["processed_root"], roots["cycling_root"],
                 roots["rpt_root"],
                 os.path.join(data_root, "data"),
                 os.path.join(data_root, "reports")]
    for label, path in (("output_dir", out_dir), ("receipt_path", receipt)):
        if not path:
            continue
        real = os.path.realpath(path)
        if _path_has_raw_component(real):
            problems.append("%s must not be inside a raw archive: %s" % (label, real))
        for root in forbidden:
            if _under(real, root):
                problems.append("%s must not be inside the read-only source root %s: %s"
                                % (label, root, real))
    if problems:
        return None, problems
    binding["reads_preflight"] = {
        "preflight_hash_files": stats.preflight_hash_files,
        "preflight_hash_bytes": stats.preflight_hash_bytes,
        "checkpoint_files": stats.checkpoint_files,
        "rpt_assets_read": 0,
    }
    return binding, []


# ---------------------------------------------------------------------------
# C3 adapters: role projection only
# ---------------------------------------------------------------------------
def _development_rpt_records(payload, cell_id):
    """a2_prep.rpt_records_from_processed with only the literal role gate projected.

    a2_prep refuses role != "train" by design.  C3 authorisation is a GO-level
    fact, so we prove the asset role is "development" here and pass a shallow
    copy whose role field is "train" to the unmodified adapter.  No other field
    or check is changed.
    """
    if not isinstance(payload, dict):
        raise InferenceError("processed cell %s is not an object" % cell_id)
    role = str(payload.get("role"))
    if role != "development":
        raise InferenceError("processed cell %s role is %r, not development"
                             % (cell_id, role))
    proxy = dict(payload)
    proxy["role"] = "train"
    try:
        return a2_prep.rpt_records_from_processed(proxy, cell_id)
    except a2_prep.PrepError as exc:
        raise InferenceError("processed cell %s adapter refused: %s"
                             % (cell_id, exc))


def _development_cycle_records(doc, cell_id):
    """a2_prep.cycle_records_from_features with only the role gate projected."""
    if not isinstance(doc, dict):
        raise InferenceError("cycling cell %s is not an object" % cell_id)
    role = str(doc.get("role"))
    if role != "development":
        raise InferenceError("cycling cell %s role is %r, not development"
                             % (cell_id, role))
    proxy = dict(doc)
    proxy["role"] = "train"
    try:
        return a2_prep.cycle_records_from_features(proxy, cell_id)
    except a2_prep.PrepError as exc:
        raise InferenceError("cycling cell %s adapter refused: %s"
                             % (cell_id, exc))


def load_cell(spec, stats):
    """Read one development cell and build its a2_targets records (no inference)."""
    cid = spec["cell_id"]
    blob = _read_bytes(spec["processed_path"], "processed cell %s" % cid,
                       stats=stats,
                       allowed_roots=[os.path.dirname(spec["processed_path"])])
    digest = hashlib.sha256(blob).hexdigest()
    if digest != spec["processed_sha256"]:
        raise InferenceError("processed cell %s sha256 mismatch" % cid)
    try:
        payload = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise InferenceError("processed cell %s is not UTF-8 JSON: %s" % (cid, exc))
    stats.processed_cells += 1

    rpts, rcount = _development_rpt_records(payload, cid)
    group_id = str(payload.get("group_id", ""))
    if len(rpts) < 4:
        return {"cell_id": cid, "group_id": group_id, "rpts": rpts,
                "cycles": [], "counts": rcount, "skip_reason":
                "fewer_than_4_valid_rpt"}

    cblob = _read_bytes(spec["cycling_path"], "cycling cell %s" % cid,
                        stats=stats,
                        allowed_roots=[os.path.dirname(spec["cycling_path"])])
    cdigest = hashlib.sha256(cblob).hexdigest()
    if cdigest != spec["cycling_sha256"]:
        raise InferenceError("cycling cell %s sha256 mismatch" % cid)
    try:
        doc = json.loads(gzip.decompress(cblob).decode("utf-8"))
    except (OSError, EOFError, UnicodeDecodeError, ValueError) as exc:
        raise InferenceError("cycling cell %s is not gzip JSON: %s" % (cid, exc))
    stats.cycling_cells += 1
    cycles, ccount = _development_cycle_records(doc, cid)
    counts = dict(rcount)
    counts.update(ccount)

    rows = sorted(({
        "source_rpt_index": int(r["source_rpt_index"]),
        "stop_epoch": float(r["source_epoch"]),
        "capacityAh": float(r["capacity_ah"]),
        "arrival_epoch": float(r["available_epoch"]),
    } for r in rpts), key=lambda r: (r["stop_epoch"], r["source_rpt_index"]))
    for a, b in zip(rows, rows[1:]):
        if b["stop_epoch"] <= a["stop_epoch"]:
            raise InferenceError("cell %s has non-increasing RPT stops" % cid)
    return {"cell_id": cid, "group_id": group_id, "rpts": rpts,
            "cycles": cycles, "rows": rows, "counts": counts,
            "skip_reason": None}


# ---------------------------------------------------------------------------
# B2-compatible arm retention and as-of query grid
# ---------------------------------------------------------------------------
def _b2_arm_records(rows, anchor_index, arm):
    """Exact retention/arrival rule of B2 data_protocol._arm_records.

    Copied as a six-line frozen rule (not a semantic re-implementation): the B2
    module lives in a different experiment tree and is not part of the A2 GO
    code hash set.  anchor_index is fixed at 1 (second valid source RPT), exactly
    as B2's infer_runner does.  delay7d shifts arrival by +7 days; raw and
    sparse2 keep arrival == source stop.
    """
    anchor_source = int(rows[anchor_index]["source_rpt_index"])
    lag = DELAY7D_SECONDS if arm == "delay7d" else 0.0
    selected = []
    for i, row in enumerate(rows):
        source = int(row["source_rpt_index"])
        if arm == "sparse2" and i > anchor_index and (source - anchor_source) % 2:
            continue
        item = dict(row)
        item["arrival_epoch"] = float(row["stop_epoch"]) + lag
        selected.append(item)
    return selected


def _rpt_records_for_arm(rpts, policy_rows):
    keep = {int(r["source_rpt_index"]) for r in policy_rows}
    arrival = {int(r["source_rpt_index"]): float(r["arrival_epoch"])
               for r in policy_rows}
    out = []
    for rec in rpts:
        idx = int(rec["source_rpt_index"])
        if idx not in keep:
            continue
        item = dict(rec)
        item["available_epoch"] = float(arrival[idx])
        out.append(item)
    out.sort(key=lambda r: (float(r["source_epoch"]), int(r["source_rpt_index"])))
    return out


def build_queries(cell, arm, policy_rows, threshold_ah=THRESHOLD_AH,
                  min_visible=MIN_VISIBLE_RECORDS):
    """B2-compatible as-of query list for one arm plus skip counters."""
    rows = cell["rows"]
    skipped = {"warmup": 0, "visible_lt_min": 0, "duplicate_anchor": 0,
               "visible_threshold": 0}
    queries = []
    seen = set()
    if len(rows) < 4:
        return queries, skipped, "fewer_than_4_valid_rpt"
    warmup_epoch = float(rows[1]["stop_epoch"]) + WEEK_SECONDS
    for qrow in rows:
        q = float(qrow["stop_epoch"])
        if q < warmup_epoch:
            skipped["warmup"] += 1
            continue
        visible = [r for r in policy_rows if float(r["arrival_epoch"]) <= q + 1e-9]
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
        if any(cap <= float(threshold_ah) for cap in caps):
            skipped["visible_threshold"] += 1
            continue
        next_rows = [r for r in rows if float(r["stop_epoch"]) > q + 1e-9]
        next_row = next_rows[0] if next_rows else None
        queries.append({
            "arm": arm,
            "query_epoch": q,
            "anchor_stop_epoch": float(anchor["stop_epoch"]),
            "anchor_arrival_epoch": float(anchor["arrival_epoch"]),
            "anchor_index": aidx,
            "visible_records": len(visible),
            "visible_source_indices": ";".join(
                str(int(r["source_rpt_index"])) for r in visible),
            "visible_capacity_min_ah": min(caps),
            "gap_weeks": (None if next_row is None else
                          (float(next_row["stop_epoch"]) - q) / WEEK_SECONDS),
            "next_source_rpt_index": (None if next_row is None else
                                      int(next_row["source_rpt_index"])),
            "next_source_stop_epoch": (None if next_row is None else
                                       float(next_row["stop_epoch"])),
            "target_capacity_ah": (None if next_row is None else
                                   float(next_row["capacityAh"])),
            "last_gap_weeks": ((float(visible[-1]["stop_epoch"])
                                - float(visible[-2]["stop_epoch"])) / WEEK_SECONDS),
        })
    return queries, skipped, None


# ---------------------------------------------------------------------------
# Incremental as-of walker (validated against replay_asof in self-check)
# ---------------------------------------------------------------------------
class AsOfWalker(object):
    """Monotone-query equivalent of a2_targets.replay_asof for one arm/model.

    The base state is kept at the last event source epoch and is NEVER advanced
    through the query gap; each snapshot starts from a copy and applies the
    zero-control gap.  This is exactly replay_asof's recurrence, which uses the
    next event's control over the interval since the previous event rather than
    over the query gap.  delay7d additionally keeps the full base prefix at
    q-7d and applies only completed cycles in (q-7d, q] to the snapshot.
    """

    def __init__(self, model, sequence, lag_seconds, use_cycle, use_rpt):
        self.model = model
        self.sequence = sequence
        self.events = sequence["events"]
        self.lag = float(lag_seconds)
        self.use_cycle = bool(use_cycle)
        self.use_rpt = bool(use_rpt)
        self.idx = 0
        self.prev = float(sequence["anchor"]["source_epoch"])
        self.base_m, self.base_P = model.initial_state(1)
        self.n_cycles = 0
        self.n_rpt = 0
        self.last_control = None
        self.last_control_mask = None
        self.last_control_epoch = None
        self.last_base_epoch = self.prev
        self.last_q = None
        self.zero = torch.zeros(1, model.control_dim, dtype=self.base_m.dtype,
                                device=self.base_m.device)

    def _ctl(self, event):
        if event["kind"] != "cycle" or not self.use_cycle:
            return self.zero, self.zero
        ctl = torch.as_tensor([event["control"]], dtype=self.base_m.dtype,
                              device=self.base_m.device)
        msk = torch.as_tensor([event["control_mask"]], dtype=self.base_m.dtype,
                              device=self.base_m.device)
        return ctl, msk

    def _advance(self, m, P, dt, event):
        ctl, msk = self._ctl(event)
        return self.model.advance(m, P, torch.tensor([dt], dtype=m.dtype,
                                                     device=m.device), ctl, msk)

    def _advance_base_to(self, cutoff):
        if cutoff < self.last_base_epoch - 1e-9:
            raise InferenceError("as-of walker queried out of order")
        while (self.idx < len(self.events)
               and float(self.events[self.idx]["source_epoch"]) <= cutoff + 1e-9):
            event = self.events[self.idx]
            dt = max(0.0, (float(event["source_epoch"]) - self.prev) / WEEK_SECONDS)
            self.base_m, self.base_P, _ = self._advance(
                self.base_m, self.base_P, dt, event)
            self.prev = float(event["source_epoch"])
            if event["kind"] == "cycle":
                self.n_cycles += 1
                if self.use_cycle:
                    self.last_control = torch.as_tensor(
                        [event["control"]], dtype=self.base_m.dtype,
                        device=self.base_m.device)
                    self.last_control_mask = torch.as_tensor(
                        [event["control_mask"]], dtype=self.base_m.dtype,
                        device=self.base_m.device)
                    self.last_control_epoch = self.prev
            else:
                self.n_rpt += 1
                if self.use_rpt and event.get("score", False):
                    q_ref = torch.tensor([self.sequence["q_ref_ah"]],
                                         dtype=self.base_m.dtype,
                                         device=self.base_m.device)
                    self.base_m, self.base_P, _, _ = self.model.correct_rpt(
                        self.base_m, self.base_P, q_ref,
                        [float(event["capacity_ah"])])
            self.idx += 1
            self.last_base_epoch = self.prev

    def state_at(self, query_epoch):
        q = float(query_epoch)
        if self.last_q is not None and q < self.last_q - 1e-9:
            raise InferenceError("as-of walker queries must be monotone")
        self.last_q = q
        cutoff = q - self.lag
        self._advance_base_to(cutoff)
        m = self.base_m.clone()
        P = self.base_P.clone()
        prev = self.prev
        last_control = self.last_control
        last_control_mask = self.last_control_mask
        last_control_epoch = self.last_control_epoch
        n_cycles = self.n_cycles
        n_rpt = self.n_rpt
        n_late = 0
        if self.lag > 0.0:
            j = self.idx
            while (j < len(self.events)
                   and float(self.events[j]["source_epoch"]) <= q + 1e-9):
                event = self.events[j]
                if event["kind"] == "cycle":
                    dt = max(0.0, (float(event["source_epoch"]) - prev)
                             / WEEK_SECONDS)
                    m, P, _ = self._advance(m, P, dt, event)
                    prev = float(event["source_epoch"])
                    n_cycles += 1
                    if self.use_cycle:
                        last_control = torch.as_tensor(
                            [event["control"]], dtype=m.dtype, device=m.device)
                        last_control_mask = torch.as_tensor(
                            [event["control_mask"]], dtype=m.dtype,
                            device=m.device)
                        last_control_epoch = prev
                else:
                    n_late += 1
                j += 1
        if q > prev + 1e-9:
            m, P, _ = self.model.advance(
                m, P, torch.tensor([(q - prev) / WEEK_SECONDS], dtype=m.dtype,
                                   device=m.device), self.zero, self.zero)
        return {
            "m": m, "P": P,
            "n_cycles_used": n_cycles, "n_rpt_used": n_rpt,
            "n_late_arrival_excluded": n_late,
            "last_control": last_control,
            "last_control_mask": last_control_mask,
            "last_control_epoch": last_control_epoch,
        }


# ---------------------------------------------------------------------------
# Prediction / output
# ---------------------------------------------------------------------------
def _moments(model, m, P, q_ref):
    mu, latent, total, _ = model.capacity_moments(m, P, q_ref)
    return {
        "mean_ah": float(mu.detach()),
        "latent_var_ah2": float(latent.detach()),
        "var_ah2": float(total.detach()),
        "sd_ah": float(torch.sqrt(total.detach())),
    }


def _advance_horizon(model, m, P, horizon_weeks, control, mask, q_ref):
    dt = float(horizon_weeks)
    m2, P2, _ = model.advance(
        m, P, torch.tensor([dt], dtype=m.dtype, device=m.device),
        control, mask)
    return _moments(model, m2, P2, q_ref)


def _gaussian_nll(y, mean, var):
    var = max(float(var), 1e-12)
    z = float(y) - float(mean)
    return 0.5 * (z * z / var + math.log(var) + LOG_2PI)


def _coverage(y, mean, var, z):
    return int(abs(float(y) - float(mean)) <= float(z) * math.sqrt(max(var, 1e-12)))


def _match_horizon_target(cell, q, horizon_weeks, tolerance_weeks):
    target_epoch = q + float(horizon_weeks) * WEEK_SECONDS
    best = None
    for row in cell["rows"]:
        delta = abs(float(row["stop_epoch"]) - target_epoch)
        if delta <= float(tolerance_weeks) * WEEK_SECONDS + 1e-9:
            key = (delta, float(row["stop_epoch"]),
                   int(row["source_rpt_index"]))
            if best is None or key < best[0]:
                best = (key, row)
    return None if best is None else best[1]


CONTROL_FIELDS = tuple(name for name, _ in a2_prep.CONTROL_FIELDS)
assert len(CONTROL_FIELDS) == CONTROL_DIM == 24


def _csv_fields():
    core = [
        "query_id", "cell_id", "group_id", "arm", "model_key", "model_arm",
        "model_use_cycle", "model_use_rpt",
        "query_epoch", "query_utc", "anchor_stop_epoch", "anchor_stop_utc",
        "anchor_arrival_epoch", "anchor_index", "visible_records",
        "visible_source_indices", "visible_capacity_min_ah",
        "qref_ah", "qref_anchor_stop_epoch", "qref_anchor_utc",
        "state_D", "state_R", "state_P00", "state_P01", "state_P11",
        "state_capacity_mean_ah", "state_capacity_latent_var_ah2",
        "state_capacity_total_var_ah2",
        "n_cycles_used", "n_rpt_used", "n_late_arrival_excluded",
        "held_control_epoch", "control_policy",
    ]
    controls = ["control_%02d" % i for i in range(CONTROL_DIM)]
    masks = ["control_mask_%02d" % i for i in range(CONTROL_DIM)]
    target = [
        "gap_weeks", "next_source_rpt_index", "next_source_stop_epoch",
        "target_available", "target_capacity_ah",
        "pred_mean_ah", "pred_latent_var_ah2", "pred_var_ah2", "pred_sd_ah",
        "innovation_ah", "abs_error_ah", "sq_error_ah2", "nll_per_ah",
        "covered_50", "covered_90", "covered_95",
    ]
    horizon = []
    for h in HORIZONS_WEEKS:
        tag = ("h%g" % h).replace(".", "p")
        horizon += [tag + "_mean_ah", tag + "_var_ah2", tag + "_sd_ah",
                    tag + "_target_epoch", tag + "_target_capacity_ah",
                    tag + "_nll_per_ah", tag + "_abs_error_ah",
                    tag + "_covered_95"]
    return core + controls + masks + target + horizon


CSV_FIELDS = _csv_fields()


def _blank(value):
    if value is None:
        return ""
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    return value


class _CellAccumulator(object):
    """Per-cell sums, then cell-macro means (equal cell weight)."""

    def __init__(self):
        self.cells = {}

    def add(self, cell_id, nll=None, abs_err=None, sq_err=None,
            cov50=None, cov90=None, cov95=None):
        rec = self.cells.setdefault(cell_id, {
            "n": 0, "sum_nll": 0.0, "sum_abs": 0.0, "sum_sq": 0.0,
            "n_cov50": 0, "n_cov90": 0, "n_cov95": 0})
        rec["n"] += 1
        if nll is not None:
            rec["sum_nll"] += float(nll)
        if abs_err is not None:
            rec["sum_abs"] += float(abs_err)
        if sq_err is not None:
            rec["sum_sq"] += float(sq_err)
        if cov50 is not None:
            rec["n_cov50"] += int(cov50)
        if cov90 is not None:
            rec["n_cov90"] += int(cov90)
        if cov95 is not None:
            rec["n_cov95"] += int(cov95)

    def block(self):
        cells = [c for c, rec in self.cells.items() if rec["n"] > 0]
        if not cells:
            return {"n_cells": 0, "n_scored": 0}
        nll = [self.cells[c]["sum_nll"] / self.cells[c]["n"] for c in cells]
        mae = [self.cells[c]["sum_abs"] / self.cells[c]["n"] for c in cells]
        mse = [self.cells[c]["sum_sq"] / self.cells[c]["n"] for c in cells]
        cov50 = [self.cells[c]["n_cov50"] / self.cells[c]["n"] for c in cells]
        cov90 = [self.cells[c]["n_cov90"] / self.cells[c]["n"] for c in cells]
        cov95 = [self.cells[c]["n_cov95"] / self.cells[c]["n"] for c in cells]
        n = sum(self.cells[c]["n"] for c in cells)
        pooled_nll = sum(self.cells[c]["sum_nll"] for c in cells) / n
        pooled_mse = sum(self.cells[c]["sum_sq"] for c in cells) / n
        pooled_mae = sum(self.cells[c]["sum_abs"] for c in cells) / n
        pooled_cov95 = sum(self.cells[c]["n_cov95"] for c in cells) / n
        return {
            "n_cells": len(cells),
            "n_scored": int(n),
            "nll_cell_macro": float(np.mean(nll)),
            "rmse_cell_macro": float(math.sqrt(np.mean(mse))),
            "mae_cell_macro": float(np.mean(mae)),
            "mean_cell_rmse": float(np.mean(np.sqrt(mse))),
            "coverage_50_cell_macro": float(np.mean(cov50)),
            "coverage_90_cell_macro": float(np.mean(cov90)),
            "coverage_95_cell_macro": float(np.mean(cov95)),
            "nll_pooled": float(pooled_nll),
            "rmse_pooled": float(math.sqrt(pooled_mse)),
            "mae_pooled": float(pooled_mae),
            "coverage_95_pooled": float(pooled_cov95),
        }


class _MetricBook(object):
    def __init__(self):
        self.groups = {}
        self.rows = {}

    def add(self, key, cell_id, **kwargs):
        self.groups.setdefault(key, _CellAccumulator()).add(cell_id, **kwargs)
        self.rows[key] = self.rows.get(key, 0) + 1

    def block(self, key):
        out = self.groups[key].block() if key in self.groups else {
            "n_cells": 0, "n_scored": 0}
        out["n_rows"] = int(self.rows.get(key, 0))
        return out


def _query_id(cell_id, arm, anchor_index, model_key):
    return "%s|%s|%s|%s" % (cell_id, arm, anchor_index, model_key)


def _control_for_output(state, model_cfg):
    if not model_cfg["use_cycle"]:
        z = np.zeros(CONTROL_DIM, dtype=float)
        return z, z, "all_masked_time_arm", None
    ctl = state["last_control"]
    msk = state["last_control_mask"]
    if ctl is None or msk is None:
        z = np.zeros(CONTROL_DIM, dtype=float)
        return z, z, "no_visible_cycle_all_masked", None
    return (ctl.detach().cpu().numpy().reshape(-1).astype(float),
            msk.detach().cpu().numpy().reshape(-1).astype(float),
            "held_recent_last_completed_cycle",
            state["last_control_epoch"])


def _row_for_query(cell, arm, query, model_key, model, state, q_ref,
                   sequence):
    cfg = MODEL_ARMS[model_key]
    ctl_np, msk_np, policy, held_epoch = _control_for_output(state, cfg)
    ctl = torch.as_tensor(ctl_np.reshape(1, -1), dtype=state["m"].dtype,
                          device=state["m"].device)
    msk = torch.as_tensor(msk_np.reshape(1, -1), dtype=state["m"].dtype,
                          device=state["m"].device)
    q = float(query["query_epoch"])
    base = _moments(model, state["m"], state["P"], q_ref)
    row = {
        "query_id": _query_id(cell["cell_id"], arm, query["anchor_index"],
                              model_key),
        "cell_id": cell["cell_id"], "group_id": cell["group_id"],
        "arm": arm, "model_key": model_key, "model_arm": cfg["label"],
        "model_use_cycle": int(cfg["use_cycle"]),
        "model_use_rpt": int(cfg["use_rpt"]),
        "query_epoch": q, "query_utc": _utc(q),
        "anchor_stop_epoch": query["anchor_stop_epoch"],
        "anchor_stop_utc": _utc(query["anchor_stop_epoch"]),
        "anchor_arrival_epoch": query["anchor_arrival_epoch"],
        "anchor_index": query["anchor_index"],
        "visible_records": query["visible_records"],
        "visible_source_indices": query["visible_source_indices"],
        "visible_capacity_min_ah": query["visible_capacity_min_ah"],
        "qref_ah": float(q_ref),
        "qref_anchor_stop_epoch": float(sequence["anchor"]["source_epoch"]),
        "qref_anchor_utc": _utc(sequence["anchor"]["source_epoch"]),
        "state_D": float(state["m"][0, 0]),
        "state_R": float(state["m"][0, 1]),
        "state_P00": float(state["P"][0, 0, 0]),
        "state_P01": float(state["P"][0, 0, 1]),
        "state_P11": float(state["P"][0, 1, 1]),
        "state_capacity_mean_ah": base["mean_ah"],
        "state_capacity_latent_var_ah2": base["latent_var_ah2"],
        "state_capacity_total_var_ah2": base["var_ah2"],
        "n_cycles_used": int(state["n_cycles_used"]),
        "n_rpt_used": int(state["n_rpt_used"]),
        "n_late_arrival_excluded": int(state["n_late_arrival_excluded"]),
        "held_control_epoch": _blank(held_epoch),
        "control_policy": policy,
    }
    for i in range(CONTROL_DIM):
        row["control_%02d" % i] = float(ctl_np[i])
        row["control_mask_%02d" % i] = float(msk_np[i])

    for h in HORIZONS_WEEKS:
        tag = ("h%g" % h).replace(".", "p")
        pred = _advance_horizon(model, state["m"], state["P"], h, ctl, msk,
                                q_ref)
        target = _match_horizon_target(cell, q, h,
                                       HORIZON_TOLERANCE_WEEKS)
        row[tag + "_mean_ah"] = pred["mean_ah"]
        row[tag + "_var_ah2"] = pred["var_ah2"]
        row[tag + "_sd_ah"] = pred["sd_ah"]
        row[tag + "_target_epoch"] = _blank(None if target is None
                                            else float(target["stop_epoch"]))
        row[tag + "_target_capacity_ah"] = _blank(
            None if target is None else float(target["capacityAh"]))
        if target is None:
            row[tag + "_nll_per_ah"] = ""
            row[tag + "_abs_error_ah"] = ""
            row[tag + "_covered_95"] = ""
        else:
            y = float(target["capacityAh"])
            nll = _gaussian_nll(y, pred["mean_ah"], pred["var_ah2"])
            row[tag + "_nll_per_ah"] = nll
            row[tag + "_abs_error_ah"] = abs(y - pred["mean_ah"])
            row[tag + "_covered_95"] = _coverage(y, pred["mean_ah"],
                                                 pred["var_ah2"], 1.959963984540054)

    gap = query["gap_weeks"]
    row["gap_weeks"] = _blank(gap)
    row["next_source_rpt_index"] = _blank(query["next_source_rpt_index"])
    row["next_source_stop_epoch"] = _blank(query["next_source_stop_epoch"])
    row["target_capacity_ah"] = _blank(query["target_capacity_ah"])
    row["target_available"] = int(gap is not None)
    if gap is None:
        row["pred_mean_ah"] = ""
        row["pred_latent_var_ah2"] = ""
        row["pred_var_ah2"] = ""
        row["pred_sd_ah"] = ""
        row["innovation_ah"] = ""
        row["abs_error_ah"] = ""
        row["sq_error_ah2"] = ""
        row["nll_per_ah"] = ""
        row["covered_50"] = ""
        row["covered_90"] = ""
        row["covered_95"] = ""
    else:
        pred = _advance_horizon(model, state["m"], state["P"], gap, ctl, msk,
                                q_ref)
        y = float(query["target_capacity_ah"])
        z = y - pred["mean_ah"]
        row["pred_mean_ah"] = pred["mean_ah"]
        row["pred_latent_var_ah2"] = pred["latent_var_ah2"]
        row["pred_var_ah2"] = pred["var_ah2"]
        row["pred_sd_ah"] = pred["sd_ah"]
        row["innovation_ah"] = z
        row["abs_error_ah"] = abs(z)
        row["sq_error_ah2"] = z * z
        row["nll_per_ah"] = _gaussian_nll(y, pred["mean_ah"], pred["var_ah2"])
        row["covered_50"] = _coverage(y, pred["mean_ah"], pred["var_ah2"],
                                      0.6744897501960817)
        row["covered_90"] = _coverage(y, pred["mean_ah"], pred["var_ah2"],
                                      1.6448536269514722)
        row["covered_95"] = _coverage(y, pred["mean_ah"], pred["var_ah2"],
                                      1.959963984540054)
    return row


def _update_metrics(book, row):
    if row["target_available"] and row["nll_per_ah"] != "":
        payload = dict(
            nll=row["nll_per_ah"], abs_err=row["abs_error_ah"],
            sq_err=row["sq_error_ah2"],
            cov50=row["covered_50"], cov90=row["covered_90"],
            cov95=row["covered_95"])
        arm, model = row["arm"], row["model_key"]
        book.add(("arm_model", arm, model), row["cell_id"], **payload)
        book.add(("arm", arm), row["cell_id"], **payload)
        book.add(("model", model), row["cell_id"], **payload)
        book.add(("overall", "all"), row["cell_id"], **payload)
    for h in HORIZONS_WEEKS:
        tag = ("h%g" % h).replace(".", "p")
        if row[tag + "_nll_per_ah"] != "":
            book.add(("horizon", row["arm"], row["model_key"], h),
                     row["cell_id"],
                     nll=row[tag + "_nll_per_ah"],
                     abs_err=row[tag + "_abs_error_ah"],
                     sq_err=float(row[tag + "_abs_error_ah"]) ** 2,
                     cov95=row[tag + "_covered_95"])


def _metric_rows(book, prefix):
    out = []
    for key, acc in book.groups.items():
        if not isinstance(key, tuple) or not key or key[0] != prefix:
            continue
        block = acc.block()
        item = {"key": list(key[1:])}
        item.update(block)
        out.append(item)
    out.sort(key=lambda x: [str(v) for v in x["key"]])
    return out


# ---------------------------------------------------------------------------
# Inference execution
# ---------------------------------------------------------------------------
def execute_inference(cells, models, binding, out_dir, deadline=None,
                      progress=True):
    """Run all query/arm/model predictions and write predictions CSV + summary."""
    stats = binding.get("stats") or ReadStats()
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "predictions_c3_a2.csv")
    tmp_csv = csv_path + ".tmp"
    metric_book = _MetricBook()
    arm_query_counts = {arm: 0 for arm in QUERY_ARMS}
    skipped = {"cells_fewer_than_4_rpt": 0, "cells_no_query": 0}
    skipped.update({arm + "_" + key: 0 for arm in QUERY_ARMS
                    for key in ("warmup", "visible_lt_min", "duplicate_anchor",
                                "visible_threshold")})
    cell_records = []
    n_rows = 0
    n_query_models = 0
    qref_by_cell = {}
    per_cell_queries = {}
    receipt_extra = {"n_cells": len(cells)}

    with open(tmp_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for ci, cell in enumerate(cells):
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError("inference runtime deadline reached")
            cid = cell["cell_id"]
            if cell.get("skip_reason"):
                skipped[cell["skip_reason"]] = skipped.get(
                    cell["skip_reason"], 0) + 1
                cell_records.append({"cell_id": cid,
                                     "group_id": cell.get("group_id", ""),
                                     "skipped": cell["skip_reason"]})
                if progress:
                    print("[cell %d/%d] %s skipped (%s)"
                          % (ci + 1, len(cells), cid, cell["skip_reason"]))
                continue
            qref = None
            cell_query_counts = {}
            arm_sequences = {}
            arm_queries = {}
            for arm in QUERY_ARMS:
                policy = _b2_arm_records(cell["rows"], 1, arm)
                rpts_arm = _rpt_records_for_arm(cell["rpts"], policy)
                try:
                    seq = a2_prep.cell_sequence(cid, cell["cycles"], rpts_arm,
                                                cutoff_epoch=None)
                except a2_prep.PrepError as exc:
                    raise InferenceError("cell %s arm %s sequence refused: %s"
                                         % (cid, arm, exc))
                if seq.get("anchor") is None:
                    raise InferenceError("cell %s arm %s has no anchor"
                                         % (cid, arm))
                if qref is None:
                    qref = float(seq["q_ref_ah"])
                    qref_by_cell[cid] = qref
                elif abs(qref - float(seq["q_ref_ah"])) > 1e-12:
                    raise InferenceError("cell %s q_ref differs across arms"
                                         % cid)
                queries, skips, why = build_queries(cell, arm, policy)
                if why:
                    raise InferenceError("cell %s arm %s query grid refused: %s"
                                         % (cid, arm, why))
                arm_sequences[arm] = seq
                arm_queries[arm] = queries
                cell_query_counts[arm] = len(queries)
                arm_query_counts[arm] += len(queries)
                for key, value in skips.items():
                    skipped[arm + "_" + key] += int(value)
            if sum(cell_query_counts.values()) == 0:
                skipped["cells_no_query"] += 1
            q_ref_t = torch.tensor([qref], dtype=torch.float32)
            for arm in QUERY_ARMS:
                seq = arm_sequences[arm]
                queries = arm_queries[arm]
                walkers = {}
                for model_key in sorted(MODEL_ARMS):
                    cfg = MODEL_ARMS[model_key]
                    walkers[model_key] = AsOfWalker(
                        models[model_key], seq,
                        DELAY7D_SECONDS if arm == "delay7d" else 0.0,
                        cfg["use_cycle"], cfg["use_rpt"])
                for query in queries:
                    if deadline is not None and time.monotonic() > deadline:
                        raise TimeoutError("inference runtime deadline reached")
                    for model_key in sorted(MODEL_ARMS):
                        if deadline is not None and time.monotonic() > deadline:
                            raise TimeoutError("inference runtime deadline reached")
                        # Inference must not build or retain autograd graphs: on real data
                        # the per-query loop otherwise leaks a graph per query and grows RSS
                        # without bound (observed 30 GB at cell 16/63).
                        with torch.no_grad():
                            state = walkers[model_key].state_at(query["query_epoch"])
                            row = _row_for_query(cell, arm, query, model_key,
                                                 models[model_key], state, qref,
                                                 seq)
                        writer.writerow({k: _blank(v) for k, v in row.items()})
                        _update_metrics(metric_book, row)
                        n_rows += 1
                        n_query_models += 1
            per_cell_queries[cid] = cell_query_counts
            cell_records.append({
                "cell_id": cid, "group_id": cell["group_id"],
                "q_ref_ah": qref,
                "qref_anchor_stop_epoch": float(seq["anchor"]["source_epoch"]),
                "n_valid_rpt": len(cell["rows"]),
                "n_cycles": len(cell["cycles"]),
                "n_queries": cell_query_counts,
                "counts": cell.get("counts", {}),
            })
            if progress:
                print("[cell %d/%d] %s qref=%.6f queries raw=%d sparse2=%d "
                      "delay7d=%d rows=%d"
                      % (ci + 1, len(cells), cid, qref,
                         cell_query_counts["raw"],
                         cell_query_counts["sparse2"],
                         cell_query_counts["delay7d"], n_rows))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_csv, csv_path)
    csv_sha = hash_file(csv_path)
    csv_bytes = os.path.getsize(csv_path)

    metrics = {
        "next_jump": {
            "overall": metric_book.block(("overall", "all")),
            "by_arm": [{"arm": k[1], **metric_book.block(k)}
                       for k in sorted(metric_book.groups)
                       if isinstance(k, tuple) and k[0] == "arm"],
            "by_model": [{"model_key": k[1], **metric_book.block(k)}
                         for k in sorted(metric_book.groups)
                         if isinstance(k, tuple) and k[0] == "model"],
            "by_arm_model": [
                {"arm": k[1], "model_key": k[2], **metric_book.block(k)}
                for k in sorted(metric_book.groups)
                if isinstance(k, tuple) and k[0] == "arm_model"],
        },
        "fixed_horizons": [],
    }
    for h in HORIZONS_WEEKS:
        for arm in QUERY_ARMS:
            for model_key in sorted(MODEL_ARMS):
                key = ("horizon", arm, model_key, h)
                if key not in metric_book.groups:
                    continue
                block = metric_book.block(key)
                metrics["fixed_horizons"].append({
                    "horizon_weeks": float(h), "arm": arm,
                    "model_key": model_key, **block,
                    "tolerance_weeks": HORIZON_TOLERANCE_WEEKS,
                })
    metrics["fixed_horizons"].sort(
        key=lambda x: (x["arm"], x["model_key"], x["horizon_weeks"]))

    summary = {
        "schema": SCHEMA,
        "status": "C3_INFERENCE_COMPLETE",
        "created_utc": _utc_now(),
        "go": binding.get("go_info", {}),
        "code_sha256": binding.get("code_sha256", {}),
        "sources": binding.get("sources", {}),
        "checkpoints": binding.get("checkpoint_info", {}),
        "query_contract": binding.get("query_contract", {}),
        "cells": cell_records,
        "counts": {
            "n_cells": len(cells),
            "n_cells_skipped": skipped.get("cells_fewer_than_4_rpt", 0)
                               + skipped.get("cells_no_query", 0),
            "n_queries": int(sum(arm_query_counts.values())),
            "n_queries_by_arm": arm_query_counts,
            "n_prediction_rows": int(n_rows),
            "n_query_models": int(n_query_models),
            "n_models": len(MODEL_ARMS),
            "n_query_arms": len(QUERY_ARMS),
        },
        "skipped": skipped,
        "metrics": metrics,
        "outputs": {
            "predictions_csv": csv_path,
            "predictions_csv_sha256": csv_sha,
            "predictions_csv_bytes": int(csv_bytes),
            "predictions_rows": int(n_rows),
        },
        "reads": {
            "processed_cells": int(stats.processed_cells),
            "cycling_cells": int(stats.cycling_cells),
            "files_read": int(stats.files_read),
            "bytes_read": int(stats.bytes_read),
            "preflight_hash_files": int(stats.preflight_hash_files),
            "preflight_hash_bytes": int(stats.preflight_hash_bytes),
            "checkpoint_files_read": int(stats.checkpoint_files),
            "rpt_assets_read": 0,
            "raw_archives_read": 0,
            "c4_cells_read": 0,
            "fits": 0,
            "optimizer_steps": 0,
        },
        "fits": 0,
        "optimizer_steps": 0,
    }
    summary_path = os.path.join(out_dir, "summary.json")
    _atomic_json(summary_path, summary)
    summary["outputs"]["summary_json"] = summary_path
    summary["outputs"]["summary_json_sha256"] = hash_file(summary_path)
    return summary, stats


def _write_receipt(out_dir, receipt_path, summary, status, error=None,
                   started=None, elapsed=None):
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": status,
        "created_utc": _utc_now(),
        "started_utc": started,
        "elapsed_seconds": elapsed,
        "consumes_go": False,
        "go_consumption": ("owned by the controller; this receipt never marks "
                           "a GO consumed"),
        "error": error,
        "go": summary.get("go", {}) if summary else {},
        "code_sha256": summary.get("code_sha256", {}) if summary else {},
        "sources": summary.get("sources", {}) if summary else {},
        "checkpoints": summary.get("checkpoints", {}) if summary else {},
        "counts": summary.get("counts", {}) if summary else {},
        "reads": summary.get("reads", {}) if summary else {},
        "outputs": summary.get("outputs", {}) if summary else {},
        "fits": 0,
        "optimizer_steps": 0,
    }
    out_receipt = os.path.join(out_dir, "receipt.json")
    _atomic_json(out_receipt, receipt)
    written = [out_receipt]
    if receipt_path and os.path.realpath(receipt_path) != os.path.realpath(out_receipt):
        if os.path.exists(receipt_path):
            raise InferenceError("receipt_path appeared after preflight: %s"
                                 % receipt_path)
        _atomic_json(receipt_path, receipt)
        written.append(receipt_path)
    return receipt, written


# ---------------------------------------------------------------------------
# Real GO-gated run
# ---------------------------------------------------------------------------
def run_go(go_path, threads=8, verbose=True):
    started = time.monotonic()
    start_iso = _utc_now()
    stats = ReadStats()
    try:
        go = _json_load(go_path, "GO")
    except InferenceError as exc:
        print("REFUSED -- %s" % exc)
        return 3
    problems, norm = validate_go_document(go)
    if problems:
        print("REFUSED -- GO validation failed (%d problem(s)):" % len(problems))
        for problem in problems:
            print("  - %s" % problem)
        print("NO FILE WRITTEN. NO DATA READ. NO CHECKPOINT READ. NO GO CONSUMED.")
        return 3
    binding, problems = validate_go_bindings(norm, stats)
    if problems:
        print("REFUSED -- GO binding/hash validation failed (%d problem(s)):"
              % len(problems))
        for problem in problems:
            print("  - %s" % problem)
        print("NO FILE WRITTEN. NO GO CONSUMED.")
        return 3
    binding["go_info"] = {
        "path": os.path.abspath(go_path),
        "sha256": hash_file(go_path),
        "status": norm["status"],
        "owner_thread_id": OWNER_THREAD_ID,
        "data_scope": DATA_SCOPE,
        "device": "cpu",
        "max_runtime_seconds": norm["max_runtime_seconds"],
        "request_id": norm.get("request_id"),
    }
    binding["stats"] = stats
    out_dir = binding["output_dir"]
    receipt_path = binding["receipt_path"]
    os.makedirs(out_dir, exist_ok=True)
    deadline = started + float(norm["max_runtime_seconds"])
    alarm_installed = False
    old_handler = None
    try:
        if hasattr(signal, "SIGALRM"):
            old_handler = signal.getsignal(signal.SIGALRM)
            def _alarm(_signum, _frame):
                raise TimeoutError("GO max_runtime_seconds reached")
            signal.signal(signal.SIGALRM, _alarm)
            signal.setitimer(signal.ITIMER_REAL,
                             max(1.0, deadline - time.monotonic()))
            alarm_installed = True
        torch.set_num_threads(max(1, int(threads)))
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass
        print("GO ACCEPTED (C3 inference only): %s" % binding["go_info"]["path"])
        print("  go_sha256=%s" % binding["go_info"]["sha256"])
        print("  cells=%d checkpoints=%d device=cpu max_runtime=%ss"
              % (len(binding["dev_specs"]), len(binding["models"]),
                 norm["max_runtime_seconds"]))
        cells = []
        for i, spec in enumerate(binding["dev_specs"]):
            if time.monotonic() > deadline:
                raise TimeoutError("runtime deadline before cell load")
            cell = load_cell(spec, stats)
            cells.append(cell)
            if verbose:
                print("  loaded cell %d/%d %s (%s)"
                      % (i + 1, len(binding["dev_specs"]), spec["cell_id"],
                         cell.get("skip_reason") or "ok"))
        summary, stats = execute_inference(
            cells, binding["models"], binding, out_dir, deadline=deadline,
            progress=verbose)
        summary["runtime_seconds"] = time.monotonic() - started
        summary["reads"] = {
            "processed_cells": int(stats.processed_cells),
            "cycling_cells": int(stats.cycling_cells),
            "files_read": int(stats.files_read),
            "bytes_read": int(stats.bytes_read),
            "preflight_hash_files": int(stats.preflight_hash_files),
            "preflight_hash_bytes": int(stats.preflight_hash_bytes),
            "checkpoint_files_read": int(stats.checkpoint_files),
            "rpt_assets_read": 0,
            "raw_archives_read": 0,
            "c4_cells_read": 0,
            "fits": 0,
            "optimizer_steps": 0,
        }
        summary["counts"]["n_cells_skipped"] = int(
            summary["counts"].get("n_cells_skipped", 0))
        receipt, written = _write_receipt(
            out_dir, receipt_path, summary, "C3_INFERENCE_COMPLETE",
            started=start_iso, elapsed=time.monotonic() - started)
        print("C3 INFERENCE COMPLETE: cells=%d queries=%d rows=%d"
              % (summary["counts"]["n_cells"],
                 summary["counts"]["n_queries"],
                 summary["counts"]["n_prediction_rows"]))
        print("  predictions=%s" % summary["outputs"]["predictions_csv"])
        print("  summary=%s" % summary["outputs"]["summary_json"])
        for path in written:
            print("  receipt=%s" % path)
        print("NO FIT. NO OPTIMIZER STEP. NO C4/RAW READ. GO NOT CONSUMED.")
        return 0
    except BaseException as exc:  # noqa: BLE001
        error = "%s: %s" % (type(exc).__name__, exc)
        print("C3 INFERENCE FAILED: %s" % error)
        traceback.print_exc(file=sys.stdout)
        try:
            if out_dir and os.path.isdir(out_dir):
                _write_receipt(out_dir, receipt_path, None, "C3_INFERENCE_FAILED",
                               error=error, started=start_iso,
                               elapsed=time.monotonic() - started)
                print("  failure receipt written (partial output retained for diagnosis)")
        except Exception as receipt_exc:  # noqa: BLE001
            print("  could not write failure receipt: %s" % receipt_exc)
        print("NO GO CONSUMED.")
        return 2
    finally:
        if alarm_installed:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)

# ---------------------------------------------------------------------------
# Self-check (synthetic only)
# ---------------------------------------------------------------------------
class _OpenAudit(object):
    """Record every path opened while active; used to prove 0 real reads."""

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


_DAY = 86400.0


def _synth_iso(epoch):
    return datetime.fromtimestamp(float(epoch), timezone.utc).isoformat()


def _synth_stats(last, mean=None, lo=None, hi=None):
    mean = float(last if mean is None else mean)
    lo = float(last if lo is None else lo)
    hi = float(last if hi is None else hi)
    return {"n": 100, "finite_n": 100, "first": float(last),
            "last": float(last), "min": lo, "max": hi, "mean": mean}


def _synth_cycle(cid, idx, start):
    ch_stop = start + 0.20 * _DAY
    di_start = ch_stop + 0.01 * _DAY
    di_stop = di_start + 0.20 * _DAY
    charge = {
        "start": _synth_iso(start), "stop": _synth_iso(ch_stop),
        "Q_sample_stats": _synth_stats(0.280 - 0.00001 * idx,
                                       mean=0.279, lo=0.278, hi=0.281),
        "V_V_sample_stats": _synth_stats(4.10, mean=4.10, lo=4.05, hi=4.15),
        "t_sample_stats": _synth_stats(1.0, mean=1.0, lo=0.9, hi=1.1),
        "E_sample_stats": _synth_stats(1.15, mean=1.15, lo=1.14, hi=1.16),
        "I_A_sample_stats": _synth_stats(0.0, mean=0.0, lo=-2.0, hi=2.0),
    }
    discharge = {
        "start": _synth_iso(di_start), "stop": _synth_iso(di_stop),
        "Q_sample_stats": _synth_stats(0.279 - 0.00001 * idx,
                                       mean=0.278, lo=0.277, hi=0.280),
        "V_V_sample_stats": _synth_stats(3.70, mean=3.70, lo=3.65, hi=3.75),
        "t_sample_stats": _synth_stats(1.0, mean=1.0, lo=0.9, hi=1.1),
        "E_sample_stats": _synth_stats(1.03, mean=1.03, lo=1.02, hi=1.04),
        "I_A_sample_stats": _synth_stats(0.0, mean=0.0, lo=-2.0, hi=2.0),
    }
    return {
        "cell_id": cid, "source_cycle_index": int(idx),
        "source_visible_at": _synth_iso(di_stop),
        "charge": charge, "discharge": discharge,
        "capacity_charge_source_units_unknown": 0.280,
        "capacity_discharge_source_units_unknown": 0.279,
        "observed_cycle_throughput_source_units": 0.559,
    }


def _synth_payload(cid, base, n_rpt=12, threshold_index=None,
                   future_extra=False, seed=0):
    rows = []
    for i in range(n_rpt):
        stop = base + i * WEEK_SECONDS
        cap = 0.285 - 0.00045 * i + 0.00002 * math.sin(i + seed)
        if threshold_index is not None and i == int(threshold_index):
            cap = 0.19
        rows.append({
            "source_rpt_index": i,
            "start": _synth_iso(stop - 3600.0),
            "stop": _synth_iso(stop),
            "capacityAh": float(cap),
            "valid": True,
            "calendar_age_seconds": i * WEEK_SECONDS,
            "capacity_visible_at": "stop",
            "observed_nominal80_endpoint": False,
        })
    if future_extra:
        stop = base + n_rpt * WEEK_SECONDS
        rows.append({
            "source_rpt_index": n_rpt,
            "start": _synth_iso(stop - 3600.0),
            "stop": _synth_iso(stop),
            "capacityAh": 0.10,
            "valid": True,
            "calendar_age_seconds": n_rpt * WEEK_SECONDS,
            "capacity_visible_at": "stop",
            "observed_nominal80_endpoint": True,
        })
    cycles = []
    t = float(base)
    end = float(base + (n_rpt - 1) * WEEK_SECONDS)
    if future_extra:
        end += 2.0 * WEEK_SECONDS
    idx = 0
    while t <= end + 1e-9:
        cycles.append(_synth_cycle(cid, idx, t))
        idx += 1
        t += 0.5 * _DAY
    payload = {
        "cell_id": cid, "group_id": "G" + cid[1:3] if len(cid) > 2 else "G1",
        "role": "development", "nominal_capacity_ah": 0.25,
        "baseline_stop": _synth_iso(base - WEEK_SECONDS),
        "records": rows,
    }
    doc = {"cell_id": cid, "role": "development", "cycles": cycles}
    return payload, doc


def _write_synth_tree(root, n_cells=3, threshold_cell=None):
    """Write fabricated cohort/manifests/cell assets under a temp root."""
    import copy
    data_dir = os.path.join(root, "data", "processed", "ISU_ILCC_DataV2_v1")
    cyc_dir = os.path.join(root, "reports", "multisource_20261021_signals",
                           "cycling_features_v3")
    rpt_dir = os.path.join(root, "reports", "multisource_20261021_signals",
                           "all188_rpt_features_v1")
    for path in (data_dir, cyc_dir, rpt_dir):
        os.makedirs(path, exist_ok=True)
    ids = ["G%dC3" % (i + 1) for i in range(n_cells)]
    base = 1_650_000_000.0
    payloads, docs = {}, {}
    files, cyc_inv, rpt_inv = {}, [], []
    for i, cid in enumerate(ids):
        threshold = threshold_cell if (threshold_cell is not None and i == 0) else None
        payload, doc = _synth_payload(cid, base + i * 3.0 * _DAY,
                                      n_rpt=12, threshold_index=threshold,
                                      seed=i)
        payloads[cid] = payload
        docs[cid] = doc
        p_path = os.path.join(data_dir, cid + ".json")
        c_path = os.path.join(cyc_dir, cid + ".json.gz")
        r_path = os.path.join(rpt_dir, cid + ".json")
        p_bytes = json.dumps(payload, indent=1).encode("utf-8")
        c_bytes = gzip.compress(json.dumps(doc).encode("utf-8"))
        with open(p_path, "wb") as fh:
            fh.write(p_bytes)
        with open(c_path, "wb") as fh:
            fh.write(c_bytes)
        with open(r_path, "wb") as fh:
            fh.write(b"{}")
        files[cid] = {"sha256": hashlib.sha256(p_bytes).hexdigest(),
                      "path": os.path.relpath(p_path, root).replace(os.sep, "/"),
                      "role": "development"}
        cyc_inv.append({"cell_id": cid, "role": "development",
                        "path": os.path.relpath(c_path, root).replace(os.sep, "/"),
                        "sha256": hashlib.sha256(c_bytes).hexdigest()})
        rpt_inv.append({"cell_id": cid, "role": "development",
                        "path": os.path.relpath(r_path, root).replace(os.sep, "/"),
                        "sha256": hashlib.sha256(b"{}").hexdigest()})
    cohort = {
        "status": "FROZEN_BEFORE_ANY_CAPACITY_PAYLOAD",
        "roles": {cid: "development" for cid in ids},
        "counts": {"development": n_cells, "train": 0, "locked": 0},
    }
    data_manifest = {
        "schema": "isu_ilcc_datav2_qualified_asset_v1", "status": "PASS",
        "files": files,
        "role_counts": {"train": 0, "development": n_cells, "locked": 0},
        "constraints": {"raw_curves_read": False, "locked_payloads_read": False},
    }
    cycling_manifest = {
        "status": "SUCCESS", "schema": "MULTISOURCE_CYCLING_FEATURES_ALL188_V1",
        "development": n_cells, "C4": 0, "inventory": cyc_inv,
    }
    rpt_manifest = {
        "status": "ALL188_FEATURE_CACHE_COMPLETE", "development": n_cells,
        "locked": 0, "inventory": rpt_inv,
    }
    return {"ids": ids, "payloads": payloads, "docs": docs,
            "cohort": cohort, "data_manifest": data_manifest,
            "cycling_manifest": cycling_manifest, "rpt_manifest": rpt_manifest}


def _synth_models():
    import copy
    states = {}
    for key in sorted(MODEL_ARMS):
        model = build_model(seed=42)
        states[key] = copy.deepcopy(model.state_dict())
    models = {}
    for key in sorted(MODEL_ARMS):
        model = build_model(seed=7)
        model.load_state_dict(states[key], strict=True)
        model.eval()
        models[key] = model
    return models, states


def _synth_binding(code_hashes=None):
    return {
        "code_sha256": code_hashes or {
            name: (hash_file(os.path.join(HERE, name))
                   if os.path.isfile(os.path.join(HERE, name)) else "0" * 64)
            for name in REQUIRED_CODE},
        "sources": {},
        "checkpoint_info": {},
        "query_contract": {
            "arms": list(QUERY_ARMS), "horizons_weeks": list(HORIZONS_WEEKS),
            "min_visible_records": MIN_VISIBLE_RECORDS,
            "query_threshold_ah": THRESHOLD_AH,
            "delay7d_seconds": DELAY7D_SECONDS,
            "horizon_tolerance_weeks": HORIZON_TOLERANCE_WEEKS,
            "dedupe": "(arm, query_anchor_source_rpt_index)",
        },
        "go_info": {"status": "SELF_CHECK", "device": "cpu"},
        "stats": ReadStats(),
    }


def check_control_reuse(_root, emit):
    import copy
    cid = "G1C3"
    _payload, doc = _synth_payload(cid, 1_650_000_000.0, n_rpt=4)
    direct_ctl = a2_prep.cycle_control(doc["cycles"][0])
    calls = {"control": 0, "completion": 0, "rpt_adapter": 0}
    orig_control = a2_prep.cycle_control
    orig_completion = a2_prep.cycle_completion_epoch
    orig_rpt = a2_prep.rpt_records_from_processed

    def wrapped_control(row):
        calls["control"] += 1
        return orig_control(row)

    def wrapped_completion(row):
        calls["completion"] += 1
        return orig_completion(row)

    def wrapped_rpt(payload, cell_id):
        calls["rpt_adapter"] += 1
        return orig_rpt(payload, cell_id)

    a2_prep.cycle_control = wrapped_control
    a2_prep.cycle_completion_epoch = wrapped_completion
    a2_prep.rpt_records_from_processed = wrapped_rpt
    try:
        try:
            a2_prep.cycle_records_from_features(copy.deepcopy(doc), cid)
            raise AssertionError("a2_prep must still refuse role=development")
        except a2_prep.PrepError:
            pass
        cycles, ccount = _development_cycle_records(copy.deepcopy(doc), cid)
        assert calls["control"] >= 1 and calls["completion"] >= 1
        assert len(cycles) == len(doc["cycles"])
        assert cycles[0]["control"] == direct_ctl[0]
        assert cycles[0]["control_mask"] == direct_ctl[1]
        rpts, rcount = _development_rpt_records(
            copy.deepcopy(_payload), cid)
        assert calls["rpt_adapter"] >= 1
        assert len(rpts) == len(_payload["records"])
        assert rcount["rpt_rows"] == len(_payload["records"])
        assert ccount["cycle_rows"] == len(doc["cycles"])
    finally:
        a2_prep.cycle_control = orig_control
        a2_prep.cycle_completion_epoch = orig_completion
        a2_prep.rpt_records_from_processed = orig_rpt
    emit("  reused a2_prep.cycle_control/cycle_completion via the adapters; "
         "role gate projected only after development proof")


def check_b2_grid(_root, emit):
    rows = []
    for i in range(12):
        rows.append({"source_rpt_index": i,
                     "stop_epoch": 1_650_000_000.0 + i * WEEK_SECONDS,
                     "capacityAh": 0.285 - 0.0005 * i,
                     "arrival_epoch": 1_650_000_000.0 + i * WEEK_SECONDS})
    cell = {"rows": rows}
    expected = {"raw": 10, "sparse2": 5, "delay7d": 9}
    for arm in QUERY_ARMS:
        policy = _b2_arm_records(rows, 1, arm)
        queries, skipped, why = build_queries(cell, arm, policy)
        assert why is None
        assert len(queries) == expected[arm], (arm, len(queries))
        assert len({(q["arm"], q["anchor_index"]) for q in queries}) == len(queries)
        assert all(q["visible_records"] >= 3 for q in queries)
        assert all(q["query_epoch"] >= rows[1]["stop_epoch"] + WEEK_SECONDS
                   for q in queries)
        assert all(q["visible_capacity_min_ah"] > THRESHOLD_AH for q in queries)
    # sparse2 retains 0,1,3,5,7,9,11; delay7d is +7d; raw keeps all.
    raw_idx = [q["anchor_index"] for q in build_queries(
        cell, "raw", _b2_arm_records(rows, 1, "raw"))[0]]
    sparse_idx = [q["anchor_index"] for q in build_queries(
        cell, "sparse2", _b2_arm_records(rows, 1, "sparse2"))[0]]
    delay_idx = [q["anchor_index"] for q in build_queries(
        cell, "delay7d", _b2_arm_records(rows, 1, "delay7d"))[0]]
    assert raw_idx == list(range(2, 12))
    assert sparse_idx == [3, 5, 7, 9, 11]
    assert delay_idx == list(range(2, 11))
    # Threshold at source index 6 skips raw/delay after it becomes visible;
    # sparse2 prunes index 6 (odd offset from anchor 1) and keeps its grid.
    thr_rows = [dict(r) for r in rows]
    thr_rows[6]["capacityAh"] = 0.19
    thr_cell = {"rows": thr_rows}
    thr_counts = {arm: len(build_queries(
        thr_cell, arm, _b2_arm_records(thr_rows, 1, arm))[0])
        for arm in QUERY_ARMS}
    assert thr_counts == {"raw": 4, "sparse2": 5, "delay7d": 4}, thr_counts
    emit("  raw=%d sparse2=%d delay7d=%d; threshold skip verified"
         % (expected["raw"], expected["sparse2"], expected["delay7d"]))


def _build_synth_sequences(payload, doc):
    cid = payload["cell_id"]
    rpts, _ = _development_rpt_records(payload, cid)
    cycles, _ = _development_cycle_records(doc, cid)
    rows = sorted(({"source_rpt_index": int(r["source_rpt_index"]),
                    "stop_epoch": float(r["source_epoch"]),
                    "capacityAh": float(r["capacity_ah"]),
                    "arrival_epoch": float(r["available_epoch"])}
                   for r in rpts), key=lambda r: (r["stop_epoch"],
                                                  r["source_rpt_index"]))
    cell = {"cell_id": cid, "group_id": "G1", "rpts": rpts,
            "cycles": cycles, "rows": rows, "counts": {}}
    out = {}
    for arm in QUERY_ARMS:
        policy = _b2_arm_records(rows, 1, arm)
        rpts_arm = _rpt_records_for_arm(rpts, policy)
        seq = a2_prep.cell_sequence(cid, cycles, rpts_arm, cutoff_epoch=None)
        queries, _skips, why = build_queries(cell, arm, policy)
        assert why is None and queries
        out[arm] = {"sequence": seq, "queries": queries, "policy": policy}
    return cell, out


def check_walker_equivalence(_root, emit):
    payload, doc = _synth_payload("G1C3", 1_650_000_000.0, n_rpt=12)
    cell, arms = _build_synth_sequences(payload, doc)
    max_dm = max_dp = max_dmu = max_dv = 0.0
    n_checked = 0
    for arm in QUERY_ARMS:
        seq = arms[arm]["sequence"]
        for model_key, cfg in sorted(MODEL_ARMS.items()):
            model = build_model(seed=42)
            model.eval()
            walker = AsOfWalker(model, seq,
                                DELAY7D_SECONDS if arm == "delay7d" else 0.0,
                                cfg["use_cycle"], cfg["use_rpt"])
            for q in arms[arm]["queries"]:
                st = walker.state_at(q["query_epoch"])
                ref = replay_asof(model, seq, q["query_epoch"],
                                  use_cycle=cfg["use_cycle"],
                                  use_rpt=cfg["use_rpt"])
                assert ref["available"]
                dm = float(torch.max(torch.abs(st["m"] - ref["m"])).detach())
                dp = float(torch.max(torch.abs(st["P"] - ref["P"])).detach())
                dmu = abs(float(st["m"][0, 0] - ref["m"][0, 0]))
                dv = abs(float(torch.max(torch.abs(st["P"] - ref["P"]))))
                max_dm = max(max_dm, dm)
                max_dp = max(max_dp, dp)
                max_dmu = max(max_dmu, dmu)
                max_dv = max(max_dv, dv)
                assert st["n_cycles_used"] == ref["n_cycles_used"]
                assert st["n_rpt_used"] == ref["n_rpt_used"]
                assert st["n_late_arrival_excluded"] == ref["n_late_arrival_excluded"]
                n_checked += 1
    assert max_dm < 1e-5 and max_dp < 1e-5
    emit("  walker == replay_asof on %d query/model/arm states "
         "(max|dm|=%.2e max|dP|=%.2e)" % (n_checked, max_dm, max_dp))


def check_no_future_leakage(_root, emit):
    import copy
    payload, doc = _synth_payload("G1C3", 1_650_000_000.0, n_rpt=12,
                                  future_extra=True)
    cell, arms = _build_synth_sequences(payload, doc)
    arm = "raw"
    seq = arms[arm]["sequence"]
    q = arms[arm]["queries"][-1]["query_epoch"]
    truncated = copy.deepcopy(seq)
    truncated["events"] = [e for e in truncated["events"]
                           if float(e["source_epoch"]) <= q + 1e-9]
    model = build_model(seed=42)
    model.eval()
    cfg = MODEL_ARMS["full"]
    w_full = AsOfWalker(model, seq, 0.0, cfg["use_cycle"], cfg["use_rpt"])
    w_trunc = AsOfWalker(model, truncated, 0.0, cfg["use_cycle"], cfg["use_rpt"])
    a = w_full.state_at(q)
    b = w_trunc.state_at(q)
    assert torch.allclose(a["m"], b["m"], atol=1e-6, rtol=0)
    assert torch.allclose(a["P"], b["P"], atol=1e-6, rtol=0)
    ref_a = replay_asof(model, seq, q, use_cycle=True, use_rpt=True)
    ref_b = replay_asof(model, truncated, q, use_cycle=True, use_rpt=True)
    assert torch.allclose(ref_a["m"], ref_b["m"], atol=1e-6, rtol=0)
    emit("  future appended RPT/cycles do not change the as-of state at q")


def _go_doc_for_self_check(root):
    code = {name: "a" * 64 for name in REQUIRED_CODE}
    ck = {}
    for key in sorted(MODEL_ARMS):
        ck[key] = {"path": os.path.join(root, key + ".pt"),
                   "sha256": "b" * 64}
    return {
        "status": GO_STATUS, "allow_inference": True, "allow_fit": False,
        "owner_thread_id": OWNER_THREAD_ID, "data_scope": DATA_SCOPE,
        "device": "cpu", "max_runtime_seconds": 3600,
        "expected_cell_count": 3,
        "code_sha256": code,
        "cohort": {"path": os.path.join(root, "cohort.json"),
                   "sha256": "c" * 64},
        "data_manifest": {"path": os.path.join(root, "data_manifest.json"),
                          "sha256": "d" * 64},
        "cycling_manifest": {"path": os.path.join(root, "cycling.json"),
                             "sha256": "e" * 64},
        "rpt_manifest": {"path": os.path.join(root, "rpt.json"),
                         "sha256": "f" * 64},
        "checkpoints": ck,
        "output_dir": os.path.join(root, "out"),
        "receipt_path": os.path.join(root, "receipt.json"),
        "query_contract": {
            "arms": list(QUERY_ARMS),
            "horizons_weeks": list(HORIZONS_WEEKS),
            "min_visible_records": MIN_VISIBLE_RECORDS,
            "query_threshold_ah": THRESHOLD_AH,
            "delay7d_seconds": DELAY7D_SECONDS,
            "horizon_tolerance_weeks": HORIZON_TOLERANCE_WEEKS,
        },
    }


def check_go_structure(root, emit):
    import copy
    good = _go_doc_for_self_check(root)
    problems, norm = validate_go_document(good, expected_cells=3)
    assert not problems, problems
    assert set(norm["checkpoints"]) == set(MODEL_ARMS)
    mutations = []

    def mut(label, fn):
        item = copy.deepcopy(good)
        fn(item)
        mutations.append((label, item))

    mut("status", lambda g: g.__setitem__("status", "APPROVED"))
    mut("allow_inference", lambda g: g.__setitem__("allow_inference", False))
    mut("allow_fit", lambda g: g.__setitem__("allow_fit", True))
    mut("owner", lambda g: g.__setitem__("owner_thread_id", "0" * 36))
    mut("scope", lambda g: g.__setitem__("data_scope", "C3_C4"))
    mut("device", lambda g: g.__setitem__("device", "cuda:0"))
    mut("runtime", lambda g: g.__setitem__("max_runtime_seconds", 0))
    mut("consumed", lambda g: g.__setitem__("consumed_at", "2026-01-01"))
    mut("code_missing", lambda g: g["code_sha256"].pop("a2_fastdata.py"))
    mut("checkpoint_missing", lambda g: g["checkpoints"].pop("time"))
    mut("cells", lambda g: g.__setitem__("expected_cell_count", 63))
    mut("horizon", lambda g: g["query_contract"].__setitem__(
        "horizons_weeks", [1, 4, 12]))
    for label, doc in mutations:
        bad, _ = validate_go_document(doc, expected_cells=3)
        assert bad, "mutation %r was not rejected" % label
    emit("  valid GO accepted; %d refusal mutations rejected" % len(mutations))


def check_manifest_roles(root, emit):
    import copy
    tree = _write_synth_tree(os.path.join(root, "manifest_fixture"), n_cells=2)
    docs = {k: copy.deepcopy(tree[k]) for k in
            ("cohort", "data_manifest", "cycling_manifest", "rpt_manifest")}
    specs, roots = _build_dev_specs(
        docs["cohort"], docs["data_manifest"], docs["cycling_manifest"],
        docs["rpt_manifest"], os.path.join(root, "manifest_fixture"), 2)
    assert len(specs) == 2
    assert all(s["cell_id"].endswith("C3") for s in specs)
    bad_cases = []
    bad = copy.deepcopy(docs["cohort"])
    bad["roles"]["G1C3"] = "locked"
    bad_cases.append(("cohort_role", bad, docs["data_manifest"],
                      docs["cycling_manifest"], docs["rpt_manifest"]))
    bad2 = copy.deepcopy(docs["data_manifest"])
    bad2["status"] = "FAIL"
    bad_cases.append(("manifest_status", docs["cohort"], bad2,
                      docs["cycling_manifest"], docs["rpt_manifest"]))
    bad3 = copy.deepcopy(docs["cycling_manifest"])
    bad3["inventory"][0]["role"] = "train"
    bad_cases.append(("cycling_role", docs["cohort"], docs["data_manifest"],
                      bad3, docs["rpt_manifest"]))
    bad4 = copy.deepcopy(docs["rpt_manifest"])
    bad4["inventory"][0]["role"] = "train"
    bad_cases.append(("rpt_role", docs["cohort"], docs["data_manifest"],
                      docs["cycling_manifest"], bad4))
    for label, co, dm, cm, rm in bad_cases:
        try:
            _build_dev_specs(co, dm, cm, rm,
                             os.path.join(root, "manifest_fixture"), 2)
            raise AssertionError("manifest mutation %r was not rejected" % label)
        except InferenceError:
            pass
    emit("  role/status/cohort refusals verified on fabricated manifests")


def check_pipeline(root, emit):
    import copy
    tree_root = os.path.join(root, "pipeline_fixture")
    tree = _write_synth_tree(tree_root, n_cells=3)
    specs, _roots = _build_dev_specs(
        tree["cohort"], tree["data_manifest"], tree["cycling_manifest"],
        tree["rpt_manifest"], tree_root, 3)
    stats = ReadStats()
    cells = [load_cell(spec, stats) for spec in specs]
    models, _states = _synth_models()
    binding = _synth_binding()
    binding["stats"] = stats
    out_dir = os.path.join(tree_root, "out")
    receipt_path = os.path.join(tree_root, "receipt.json")
    summary, stats = execute_inference(cells, models, binding, out_dir,
                                       deadline=None, progress=False)
    receipt, written = _write_receipt(out_dir, receipt_path, summary,
                                      "C3_INFERENCE_COMPLETE",
                                      started=_utc_now(), elapsed=0.0)
    assert summary["status"] == "C3_INFERENCE_COMPLETE"
    assert summary["counts"]["n_cells"] == 3
    assert summary["counts"]["n_prediction_rows"] == 3 * summary["counts"]["n_queries"]
    assert summary["counts"]["n_prediction_rows"] > 0
    assert summary["metrics"]["next_jump"]["overall"]["n_scored"] > 0
    assert summary["metrics"]["fixed_horizons"]
    assert any(h["n_scored"] > 0 for h in summary["metrics"]["fixed_horizons"])
    assert summary["fits"] == 0 and summary["optimizer_steps"] == 0
    assert summary["reads"]["checkpoint_files_read"] == 0
    assert summary["reads"]["raw_archives_read"] == 0
    assert summary["reads"]["c4_cells_read"] == 0
    assert receipt["consumes_go"] is False
    csv_path = summary["outputs"]["predictions_csv"]
    assert os.path.isfile(csv_path)
    with open(csv_path, "r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == summary["counts"]["n_prediction_rows"]
    assert len({r["query_id"] for r in rows}) == len(rows)
    assert all(float(r["visible_capacity_min_ah"]) > THRESHOLD_AH for r in rows)
    qrefs = {}
    for r in rows:
        qrefs.setdefault(r["cell_id"], set()).add(round(float(r["qref_ah"]), 12))
        if r["model_key"] == "time":
            assert all(abs(float(r["control_%02d" % i])) < 1e-12
                       and abs(float(r["control_mask_%02d" % i])) < 1e-12
                       for i in range(CONTROL_DIM))
        if r["target_available"] == "1":
            mean = float(r["pred_mean_ah"])
            var = float(r["pred_var_ah2"])
            y = float(r["target_capacity_ah"])
            nll = 0.5 * ((y - mean) ** 2 / var + math.log(var) + LOG_2PI)
            assert abs(nll - float(r["nll_per_ah"])) < 1e-9
    assert all(len(v) == 1 for v in qrefs.values())
    assert any(float(r["control_%02d" % 0]) != 0.0
               for r in rows if r["model_key"] == "full")
    emit("  synthetic pipeline: 3 cells, %d query rows, %d scored next-jump, "
         "%d fixed-horizon groups"
         % (len(rows), summary["metrics"]["next_jump"]["overall"]["n_scored"],
            len(summary["metrics"]["fixed_horizons"])))


def run_self_check(append_log=None, verbose=True):
    lines = []

    def emit(text=""):
        print(text)
        lines.append(text)

    emit("=" * 78)
    emit("A2 C3 INFERENCE SELF-CHECK -- %s" % _utc_now())
    emit("mode: SYNTHETIC ONLY -- 0 real payload reads, 0 checkpoint files, "
         "0 fits, 0 optimizer steps")
    emit("python %s | torch %s | numpy %s"
         % (sys.version.split()[0], torch.__version__, np.__version__))
    existing = {name: hash_file(os.path.join(HERE, name))
                for name in REQUIRED_CODE
                if os.path.isfile(os.path.join(HERE, name))}
    emit("code_sha256: %s" % json.dumps(existing, sort_keys=True))
    emit("-" * 78)

    checks = [("control_reuse", check_control_reuse),
              ("b2_query_grid", check_b2_grid),
              ("walker_equivalence", check_walker_equivalence),
              ("no_future_leakage", check_no_future_leakage),
              ("go_structure", check_go_structure),
              ("manifest_roles", check_manifest_roles),
              ("synthetic_pipeline", check_pipeline)]
    passed = failed = 0
    audit = _OpenAudit()
    tmp_root = tempfile.mkdtemp(prefix="a2_infer_selfcheck_")
    try:
        with audit:
            for name, fn in checks:
                try:
                    fn(tmp_root, emit)
                    emit("[PASS] %-20s" % name)
                    passed += 1
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    emit("[FAIL] %-20s %s" % (name, exc))
                    traceback.print_exc(file=sys.stdout)
        real_root = os.environ.get("A2_PREP_ROOT", DEFAULT_ROOT)
        forbidden = [os.path.join(real_root, "data"),
                     os.path.join(real_root, "reports"),
                     os.path.join(real_root, "automation"),
                     os.path.join(real_root, "experiments",
                                  "trajectory_b2_joint_marked_renewal_20261021")]
        bad = audit.under(forbidden)
        pt_opens = [p for p in audit.paths
                    if p.lower().endswith((".pt", ".pth", ".ckpt"))]
        if bad:
            failed += 1
            emit("[FAIL] %-20s opened %d forbidden path(s): %r"
                 % ("no_real_payload", len(bad), bad[:3]))
        else:
            passed += 1
            emit("[PASS] %-20s %d paths opened; 0 under real data/reports/"
                 "automation/B2 (all under %s)"
                 % ("no_real_payload", len(audit.paths),
                    os.path.basename(tmp_root)))
        if pt_opens:
            failed += 1
            emit("[FAIL] %-20s opened checkpoint file(s): %r"
                 % ("no_checkpoint_file", pt_opens[:3]))
        else:
            passed += 1
            emit("[PASS] %-20s 0 .pt/.pth/.ckpt files opened"
                 % "no_checkpoint_file")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    emit("-" * 78)
    emit("SUMMARY: %d passed, %d failed, %d total"
         % (passed, failed, passed + failed))
    emit("REAL PAYLOAD READS: 0. CHECKPOINT FILES READ: 0. FITS: 0. "
         "OPTIMIZER STEPS: 0.")
    emit("NO GO CREATED. NO GO CONSUMED. NO RECEIPT OUTSIDE THE TEMP FIXTURE.")
    emit("RESULT: %s" % ("OK" if failed == 0 else "FAILED"))
    if append_log:
        block = ("\n===== a2_infer self-check %s =====\n" % _utc_now()) + \
                "\n".join(lines) + "\n"
        with open(append_log, "a", encoding="utf-8") as fh:
            fh.write(block)
        print("APPENDED %d lines to %s (append-only, no truncation)"
              % (len(lines) + 2, append_log))
    return 0 if failed == 0 else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="A2 C3 development inference: synthetic self-check by "
                    "default; real inference only under an APPROVED_C3_INFERENCE GO.")
    parser.add_argument("--self-check", action="store_true",
                        help="run synthetic fixtures (default behaviour)")
    parser.add_argument("--go", default=None,
                        help="path to an APPROVED_C3_INFERENCE GO json")
    parser.add_argument("--threads", type=int,
                        default=min(8, os.cpu_count() or 8),
                        help="torch CPU threads for real inference")
    parser.add_argument("--append-log", default=None,
                        help="append self-check output to this log (append-only)")
    parser.add_argument("--verbose", action="store_true",
                        help="with --go: per-cell progress")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.go and args.self_check:
        print("REFUSED -- choose either --self-check or --go, not both")
        return 2
    if args.go:
        return run_go(args.go, threads=args.threads, verbose=True)
    print("A2 C3 inference -- synthetic self-check (no GO supplied)")
    return run_self_check(append_log=args.append_log)


if __name__ == "__main__":
    sys.exit(main())

