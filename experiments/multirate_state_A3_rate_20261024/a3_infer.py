#!/usr/bin/env python3
"""A3 C3 development inference (four arms, or a GO-pinned checkpoint subset;
as-of walker) -- synthetic self-check only by default.

What this file does
-------------------
* Reads the 63 C3 development cells only (cohort role == "development"), their
  frozen processed RPT JSON and their frozen cycling feature asset.
* Reuses a2_infer.py's FROZEN QUERY CONTRACT unchanged by import: the B2
  retention rule (_b2_arm_records), the as-of query grid (build_queries:
  raw / sparse2 / delay7d, anchor = last arrived valid RPT, >= 3 visible
  records, dedupe by (arm, anchor source index), skip queries whose visible
  capacity is already <= 0.20 Ah), the horizon matching and the A2 validation
  constants.  The A3 panel is therefore key-for-key identical to the A2 C3
  panel (2,326 keys: raw 903 / sparse2 463 / delay7d 960 on the same cells).
* For each A3 checkpoint named by the GO (by default all FOUR arms: full /
  noRateUpdate / time / noEll; the optional GO field `checkpoint_subset`
  restricts inference to a subset of arms, e.g. ["full"] for the R2 stage-A
  fraction-pool checkpoints) it
  filters the A3 state x = (D, ell, R) incrementally with a3_model's segment
  engine (frozen linearization (a, b) carried from the last scored RPT
  measurement update; a query-time split of a segment is an exact affine
  semigroup composition, documented in a3_model.py), scores RPT innovations
  under the A3 observation model, and reports state-only capacity moments
  Q = Q_ref*exp(-D) + R, variance HPH^T + sigma_y^2 (Ah^2), the next-jump
  Gaussian NLL and fixed-calendar-horizon moments (1/4/12/32 weeks).
* Real inference requires an APPROVED, unconsumed GO pinning: the checkpoint
  path+sha256 set (exactly the four arms, or exactly the arms of the optional
  `checkpoint_subset` list), cohort / data / rpt / cycling manifest path+sha256,
  the code
  hash closure, a fresh output_dir, no_grad=true, an RSS cap, and a request_id
  absent from /home/yndx/zxk/rul/experiments/state/consumed_gos.jsonl.  After
  a fully successful run the request_id is registered there (append-only, the
  a3_train.register_consumed_go discipline).  A refused GO writes nothing.
  Default mode is --self-check: synthetic cells only, 0 real payload reads,
  0 checkpoint files, 0 fits, 0 optimizer steps, 0 GO created or consumed.

Reuse map (read-only reuse; nothing in A2 or a3_model is modified)
------------------------------------------------------------------
* Imported from a2_infer.py unchanged: the frozen contract constants
  (QUERY_ARMS, HORIZONS_WEEKS, MIN_VISIBLE_RECORDS, THRESHOLD_AH,
  DELAY7D_SECONDS, HORIZON_TOLERANCE_WEEKS), build_queries + _b2_arm_records
  + _rpt_records_for_arm (the query grid itself), _validate_query_contract,
  the manifest binding helpers (_build_dev_specs, _load_manifest_sources),
  the role-projection adapters (_development_rpt_records,
  _development_cycle_records), load_cell, ReadStats/_read_bytes/_hash_path
  and the small json/csv/metric helpers (_CellAccumulator, _MetricBook,
  _match_horizon_target, _gaussian_nll, _coverage, ...).
* Imported from a3_model.py: ARM_CONFIGS, build_arm_model and the segment
  engine internals _event_scalars_a3 / _segment_advance (the walker composes
  exactly these, so it IS the a3_model filter, incrementally).
* Imported from a3_train.py: DEFAULT_CONSUMED_REGISTRY,
  load_consumed_request_ids, register_consumed_go (the GO gating pattern of
  a2_train.validate_go / a3_train.validate_go_a3).
* COPIED (with this note as provenance): the GO-document validator structure,
  the checkpoint loader, execute/_row_for_query/_write_receipt/run_go and the
  self-check harness follow a2_infer.py's proven shapes.  They could not be
  imported because they hard-code A2's 3 arms / 2-dim state / GO status; A3
  needs 4 arms, the 3-dim (D, ell, R) state columns, status APPROVED, the
  no_grad + RSS-cap GO fields and the consumed-GO registration.

Code-hash pins
--------------
The A3 tree has NO a3_targets.py / a3_fastdata.py: A3 reuses a2_targets.py and
a2_fastdata.py by import (exactly like a3_model.py and a3_train.py already
do).  REQUIRED_CODE below is therefore the real import closure of this entry
point: 3 A3 files + 7 A2 files.  A GO pinning a3_targets.py /
a3_fastdata.py instead would be refused (unknown files are not hashed, known
files must all be pinned).
"""
from __future__ import annotations

import argparse
import copy
import csv
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
_A2_DIR = os.path.join(os.path.dirname(HERE), "multirate_state_A2_20261022")
if not os.path.isdir(_A2_DIR):
    raise ImportError("A2 code directory not found at %s" % _A2_DIR)
for _p in (HERE, _A2_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
import torch

import a2_prep
import a2_infer
from a2_infer import (  # noqa: F401  (reused unchanged from A2)
    DELAY7D_SECONDS,
    HORIZONS_WEEKS,
    HORIZON_TOLERANCE_WEEKS,
    MIN_VISIBLE_RECORDS,
    QUERY_ARMS,
    THRESHOLD_AH,
    InferenceError,
    ReadStats,
    _CellAccumulator,
    _MetricBook,
    _OpenAudit,
    _b2_arm_records,
    _blank,
    _build_dev_specs,
    _check_abs_ref,
    _check_fresh_dir,
    _check_fresh_file,
    _coverage,
    _development_cycle_records,
    _development_rpt_records,
    _finite,
    _finite_or_none,
    _gaussian_nll,
    _go_ref,
    _hash_path,
    _is_sha,
    _json_load,
    _json_safe,
    _load_manifest_sources,
    _match_horizon_target,
    _path_has_raw_component,
    _query_id,
    _rpt_records_for_arm,
    _read_bytes,
    _utc,
    _utc_now,
    _under,
    _validate_query_contract,
    build_queries,
    load_cell,
)
from a2_targets import hash_file
from a3_model import (
    ARM_CONFIGS,
    CONTROL_DIM,
    LOG_2PI,
    VERSION,
    WEEK_SECONDS,
    _event_scalars_a3,
    _segment_advance,
    build_arm_model,
)
from a3_train import (
    DEFAULT_CONSUMED_REGISTRY,
    load_consumed_request_ids,
    register_consumed_go,
)

# ---------------------------------------------------------------------------
# Frozen contract (A3 values; the query contract objects ARE a2_infer's)
# ---------------------------------------------------------------------------
SCHEMA = "A3_C3_INFERENCE_V1"
RECEIPT_SCHEMA = "A3_C3_INFERENCE_RECEIPT_V1"
OWNER_THREAD_ID = "01a15c3a-1a06-7d61-8517-27b70b246183"
DATA_SCOPE = "C3_source63_development_only_no_C4_no_raw"
GO_STATUS = "APPROVED"
DEFAULT_DEV_CELLS = 63
DEFAULT_MAX_RSS_GB = 2.0
FILTER_DTYPE = torch.float64
OVER_ERROR_AH = (0.020, 0.050)  # "over_20mAh" / "over_50mAh" exceedance cuts
# Real import closure of a3_infer.py (see module docstring): A3 files live in
# the A3 directory, a2_* files in the A2 directory.
REQUIRED_CODE = (
    "a3_infer.py", "a3_model.py", "a3_train.py",
    "a2_infer.py", "a2_prep.py", "a2_targets.py", "a2_fastdata.py",
    "a2_model.py", "a2_train.py", "a2_fixtures.py",
)
MODEL_ARMS = {
    key: {
        "label": ARM_CONFIGS[key]["label"],
        "mu_from_control": bool(ARM_CONFIGS[key]["mu_from_control"]),
        "rate_update": bool(ARM_CONFIGS[key]["rate_update"]),
        "ell_state": bool(ARM_CONFIGS[key]["ell_state"]),
    }
    for key in ARM_CONFIGS
}
_MODEL_ALIASES = {
    "full": "full", "a3_full": "full",
    "norateupdate": "noRateUpdate", "no_rate_update": "noRateUpdate",
    "a3_no_rate_update": "noRateUpdate", "noru": "noRateUpdate",
    "time": "time", "a3_time": "time", "time_only": "time",
    "noell": "noEll", "no_ell": "noEll", "a3_no_ell": "noEll",
}


def _canonical_model_key(value):
    text = str(value).strip()
    return _MODEL_ALIASES.get(text.lower(), text)


class _RssCapExceeded(RuntimeError):
    """The inference process grew beyond the GO's RSS cap."""


def _rss_gb():
    """Peak RSS of this process in GiB (ru_maxrss is KB on Linux), or None."""
    try:
        import resource
        return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) \
            * 1024.0 / 1e9
    except Exception:  # noqa: BLE001  (non-Unix dev boxes)
        return None


def _check_rss(cap_gb):
    peak = _rss_gb()
    if peak is not None and peak > float(cap_gb):
        raise _RssCapExceeded(
            "RSS peak %.3f GiB exceeds the GO cap %.3f GiB"
            % (peak, float(cap_gb)))


# ---------------------------------------------------------------------------
# GO document (pure checks) -- structure follows a2_infer.validate_go_document
# (copied shape; A3 arms / status / no_grad / RSS / request_id differ)
# ---------------------------------------------------------------------------
def _checkpoint_subset_a3(go, problems):
    """Validate the optional GO field ``checkpoint_subset`` (R2 stage A).

    Absent / None -> None: the historical exactly-four-arms contract,
    bit-for-bit backward compatible.  Present -> must be a non-empty list of
    KNOWN A3 arm keys (canonicalised through _canonical_model_key, order
    free); duplicates and unknown arms are refused.  Returns the sorted tuple
    of arm keys, or None after recording at least one problem for every
    malformed shape (the GO is then refused -- a malformed subset never
    silently falls back to the four-arm contract).
    """
    node = go.get("checkpoint_subset")
    if node is None:
        return None
    if not isinstance(node, list) or not node:
        problems.append("GO checkpoint_subset must be a non-empty list of A3 "
                        "arm keys, got %r" % (node,))
        return None
    resolved = []
    for item in node:
        key = _canonical_model_key(item)
        if key not in MODEL_ARMS:
            problems.append("GO checkpoint_subset contains unknown A3 arm %r "
                            "(known arms: %r)" % (item, sorted(MODEL_ARMS)))
            continue
        if key in resolved:
            problems.append("GO checkpoint_subset lists arm %r twice" % key)
            continue
        resolved.append(key)
    if len(resolved) != len(node):
        return None
    return tuple(sorted(resolved))


def _normalise_checkpoints_a3(go, problems, expected_arms=None):
    """Normalise the GO checkpoints node against the resolved arm set.

    ``expected_arms`` is the resolved ``checkpoint_subset`` (sorted tuple) or
    None for the default exactly-four-arms contract.  The checkpoints node
    must pin EXACTLY the expected arms: an arm missing from the subset, or a
    checkpoint pinned outside the subset, is a refusal.
    """
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
    expected = set(expected_arms) if expected_arms else set(MODEL_ARMS)
    if set(out) != expected:
        problems.append("checkpoints must pin exactly %r (checkpoint_subset="
                        "%r), got %r"
                        % (sorted(expected),
                           sorted(expected_arms) if expected_arms else None,
                           sorted(out)))
    normalised = {}
    for key in sorted(expected):
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
    return normalised


def validate_go_document_a3(go, expected_cells=DEFAULT_DEV_CELLS):
    """Pure GO checks; no filesystem access and no writes."""
    problems = []
    if not isinstance(go, dict):
        return ["GO must be a JSON object"], None
    status = str(go.get("status", ""))
    if status != GO_STATUS:
        problems.append("GO status is %r, not %s" % (status, GO_STATUS))
    if go.get("allow_inference") is not True:
        problems.append("GO must set allow_inference=true")
    if go.get("allow_fit") is not False:
        problems.append("GO must set allow_fit=false explicitly")
    if go.get("allow_train") is True:
        problems.append("GO must not authorise training (allow_train=true)")
    if go.get("allow_C4") is True:
        problems.append("GO must not authorise C4 (allow_C4=true)")
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
        problems.append("GO device must be 'cpu' for the A3 CPU model, got %r"
                        % (go.get("device"),))
    if go.get("no_grad") is not True:
        problems.append("GO must pin no_grad=true (the 2026-10-22 30 GB RSS "
                        "incident is forbidden to repeat)")
    cap = go.get("max_rss_gb", DEFAULT_MAX_RSS_GB)
    try:
        cap = float(cap)
    except (TypeError, ValueError):
        problems.append("GO max_rss_gb must be a number, got %r"
                        % (go.get("max_rss_gb"),))
        cap = None
    if cap is not None and not (0.1 <= cap <= 64.0):
        problems.append("GO max_rss_gb must be in [0.1, 64], got %r" % cap)
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
    request_id = go.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        problems.append("GO has no request_id (required for the consumed-GO "
                        "registry)")
    registry = go.get("registry")
    if registry is not None and os.path.abspath(str(registry)) != \
            os.path.abspath(DEFAULT_CONSUMED_REGISTRY):
        problems.append("GO registry must be the canonical consumed-GO "
                        "registry %s, got %r"
                        % (DEFAULT_CONSUMED_REGISTRY, registry))
    checkpoint_subset = _checkpoint_subset_a3(go, problems)
    if go.get("arms") is not None:
        arms = go.get("arms")
        if checkpoint_subset is not None:
            # With a checkpoint_subset the arms list (if given) must name
            # exactly the subset (aliases canonicalised).
            if not isinstance(arms, list) or \
                    sorted(_canonical_model_key(str(a)) for a in arms) != \
                    list(checkpoint_subset):
                problems.append("GO arms %r must equal checkpoint_subset %r"
                                % (arms, list(checkpoint_subset)))
        elif not isinstance(arms, list) or \
                sorted(str(a) for a in arms) != sorted(MODEL_ARMS):
            problems.append("GO arms must be %r" % (sorted(MODEL_ARMS),))

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
            ("data_manifest", ("data_manifest", "manifest",
                               "processed_manifest")),
            ("cycling_manifest", ("cycling_manifest",
                                  "cycling_features_manifest")),
            ("rpt_manifest", ("rpt_manifest", "rpt_features_manifest"))):
        path, sha, used = _go_ref(go, names)
        if path is None and sha is None:
            # Stricter than A2: A3's GO must pin all four sources explicitly.
            problems.append("GO must pin %s (path + sha256)" % label)
            refs[label] = {"path": None, "sha256": None, "go_key": used,
                           "go_pinned": False}
            continue
        _check_abs_ref(path, sha, label, problems)
        refs[label] = {"path": path, "sha256": sha, "go_key": used,
                       "go_pinned": True}

    checkpoints = _normalise_checkpoints_a3(go, problems,
                                            expected_arms=checkpoint_subset)
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
            from a2_targets import epoch_seconds
            if epoch_seconds(expires) < time.time() - 1.0:
                problems.append("GO expired at %s" % expires)
        except (TypeError, ValueError):
            problems.append("GO expires_utc is not a timestamp: %r" % (expires,))
    issued = go.get("issued_utc")
    if issued is not None:
        try:
            from a2_targets import epoch_seconds
            epoch_seconds(issued)
        except (TypeError, ValueError):
            problems.append("GO issued_utc is not a timestamp: %r" % (issued,))
    contract = _validate_query_contract(go, problems)
    norm = {
        "raw": go,
        "status": status,
        "device": "cpu",
        "no_grad": go.get("no_grad") is True,
        "max_rss_gb": cap,
        "max_runtime_seconds": runtime,
        "expected_cell_count": expected,
        "code_sha256": code_norm,
        "sources": refs,
        "checkpoints": checkpoints,
        "checkpoint_subset":
            list(checkpoint_subset) if checkpoint_subset else None,
        "output_dir": os.path.abspath(os.path.expanduser(output_dir))
        if isinstance(output_dir, str) and output_dir else None,
        "receipt_path": os.path.abspath(os.path.expanduser(receipt_path))
        if isinstance(receipt_path, str) and receipt_path else None,
        "data_root": os.path.abspath(os.path.expanduser(data_root))
        if isinstance(data_root, str) and data_root else None,
        "query_contract": contract,
        "request_id": request_id,
        "registry_path": os.path.abspath(
            str(registry or DEFAULT_CONSUMED_REGISTRY)),
    }
    return problems, norm


# ---------------------------------------------------------------------------
# Code hashes / checkpoint loading (A3 models; float64 filter copy)
# ---------------------------------------------------------------------------
def _code_path(name):
    if name.startswith("a2_"):
        return os.path.join(_A2_DIR, name)
    return os.path.join(HERE, name)


def _load_code_hashes_a3(norm, stats):
    got = {}
    for name in REQUIRED_CODE:
        path = _code_path(name)
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


def _load_arm_model_a3(key, spec, stats):
    """Hash-verify one A3 arm checkpoint and build its float64 filter model.

    The checkpoint state_dict itself is float32 (training dtype); the filter
    runs in float64 (a3_fixtures discipline: model.double()).
    """
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
        except TypeError:  # older torch without weights_only
            obj = torch.load(path, map_location="cpu")
    except Exception as exc:  # noqa: BLE001
        raise InferenceError("checkpoint %s is not loadable: %s" % (key, exc))
    if isinstance(obj, dict) and "state_dict" in obj:
        obj = obj["state_dict"]
    if not isinstance(obj, dict):
        raise InferenceError("checkpoint %s is not a state_dict" % key)
    model = build_arm_model(key, seed=42)
    try:
        model.load_state_dict(obj, strict=True)
    except Exception as exc:  # noqa: BLE001
        raise InferenceError("checkpoint %s does not match A3StateModel: %s"
                             % (key, exc))
    model.eval()
    for name, param in model.named_parameters():
        if not torch.all(torch.isfinite(param)):
            raise InferenceError("checkpoint %s has non-finite parameter %s"
                                 % (key, name))
    param_dtype = str(next(model.parameters()).dtype)
    f64 = model.double()
    f64.eval()
    info = {
        "path": os.path.abspath(path),
        "sha256": digest,
        "model_arm": MODEL_ARMS[key]["label"],
        "mu_from_control": MODEL_ARMS[key]["mu_from_control"],
        "rate_update": MODEL_ARMS[key]["rate_update"],
        "ell_state": MODEL_ARMS[key]["ell_state"],
        "checkpoint_param_dtype": param_dtype,
        "filter_dtype": "torch.float64",
        "parameters": int(sum(p.numel() for p in f64.parameters())),
        "kappa_per_week": float(f64.kappa()),
        "sigma_ell_per_sqrt_week": float(f64.sigma_ell()),
        "lambda_per_week": float(f64.lam()),
        "sigma_R_ah_per_sqrt_week": float(f64.sigma_R()),
        "obs_sigma_ah": float(f64.obs_sigma()),
        "mu_base": float(f64.mu_base),
        "control_mean_is_identity": bool(torch.equal(
            f64.control_mean, torch.zeros_like(f64.control_mean))),
        "control_scale_is_identity": bool(torch.equal(
            f64.control_scale, torch.ones_like(f64.control_scale))),
    }
    return f64, info


def validate_go_bindings_a3(norm, stats=None, registry_path=None):
    """All file/hash/role/output checks before any write.  Returns binding."""
    stats = stats or ReadStats()
    problems = []
    if not norm.get("output_dir"):
        return None, ["GO output_dir missing"]
    if not norm.get("receipt_path"):
        return None, ["GO receipt_path missing"]
    binding = dict(norm)
    try:
        code_hashes = _load_code_hashes_a3(norm, stats)
    except InferenceError as exc:
        return None, [str(exc)]
    binding["code_sha256"] = code_hashes

    try:
        docs = _load_manifest_sources(norm, stats)
    except InferenceError as exc:
        return None, [str(exc)]
    binding["source_docs"] = docs
    binding["sources"] = {
        name: {"path": docs[name + "_path"], "sha256": docs[name + "_sha256"]}
        for name in ("cohort", "data_manifest", "cycling_manifest",
                     "rpt_manifest")
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
                problems.append("%s sha256 mismatch for %s: manifest=%s "
                                "actual=%s"
                                % (path_key, spec["cell_id"], spec[sha_key],
                                   digest))
        if not os.path.isfile(spec["rpt_path"]):
            problems.append("RPT asset missing for %s: %s"
                            % (spec["cell_id"], spec["rpt_path"]))
    if problems:
        return None, problems

    # request_id freshness against the consumed-GO registry (fail-closed).
    registry = registry_path or norm.get("registry_path") \
        or DEFAULT_CONSUMED_REGISTRY
    binding["registry_path"] = os.path.abspath(registry)
    request_id = norm.get("request_id")
    if not request_id:
        problems.append("GO has no request_id")
    else:
        try:
            consumed = load_consumed_request_ids(registry)
        except Exception as exc:  # noqa: BLE001 -- fail closed
            problems.append("consumed-GO registry %s unreadable: %s"
                            % (registry, exc))
            consumed = None
        if consumed is not None and str(request_id) in consumed:
            problems.append("request_id %r already appears in the consumed-GO "
                            "registry %s" % (str(request_id), registry))

    # Fresh output paths and forbidden-root checks BEFORE the (heavier)
    # checkpoint loads, so cheap refusals always surface in the problem list.
    out_dir = _check_fresh_dir(norm["output_dir"], "output_dir", problems)
    receipt = _check_fresh_file(norm["receipt_path"], "receipt_path", problems)
    if out_dir:
        binding["output_dir"] = out_dir
    if receipt:
        binding["receipt_path"] = receipt
    if out_dir and receipt and \
            os.path.realpath(out_dir) == os.path.realpath(receipt):
        problems.append("output_dir and receipt_path must differ")
    # NOTE: data_root itself is NOT forbidden (the A3 experiment directory
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
            problems.append("%s must not be inside a raw archive: %s"
                            % (label, real))
        for root in forbidden:
            if _under(real, root):
                problems.append("%s must not be inside the read-only source "
                                "root %s: %s" % (label, root, real))

    models = {}
    checkpoint_info = {}
    # checkpoint_subset (optional): load ONLY the subset's checkpoints; the
    # default contract (no subset) loads exactly the four A3 arms.
    arm_keys = list(norm.get("checkpoint_subset") or sorted(MODEL_ARMS))
    for key in arm_keys:
        spec = (norm.get("checkpoints") or {}).get(key)
        if not isinstance(spec, dict):
            problems.append("checkpoint %s missing from the GO" % key)
            continue
        try:
            model, info = _load_arm_model_a3(key, spec, stats)
        except InferenceError as exc:
            problems.append(str(exc))
            continue
        models[key] = model
        checkpoint_info[key] = info
    if problems:
        return None, problems
    binding["models"] = models
    binding["model_arms"] = arm_keys
    binding["checkpoint_subset"] = norm.get("checkpoint_subset")
    binding["checkpoint_info"] = checkpoint_info
    binding["reads_preflight"] = {
        "preflight_hash_files": stats.preflight_hash_files,
        "preflight_hash_bytes": stats.preflight_hash_bytes,
        "checkpoint_files": stats.checkpoint_files,
        "rpt_assets_read": 0,
    }
    return binding, []


# ---------------------------------------------------------------------------
# Incremental A3 as-of walker (a3_model segment engine, one cell at a time)
# ---------------------------------------------------------------------------
def _single_event_scalars(model, kind_code, dt_weeks, ctl, msk,
                          mu_from_control):
    """_event_scalars_a3 for ONE event ([1, 1] block)."""
    kind = torch.tensor([[int(kind_code)]], dtype=torch.long)
    dt = torch.tensor([[float(dt_weeks)]], dtype=FILTER_DTYPE)
    ctl_t = torch.zeros(1, 1, model.control_dim, dtype=FILTER_DTYPE)
    msk_t = torch.zeros(1, 1, model.control_dim, dtype=FILTER_DTYPE)
    if ctl is not None:
        ctl_t[0, 0] = torch.as_tensor(ctl, dtype=FILTER_DTYPE)
        msk_t[0, 0] = torch.as_tensor(msk, dtype=FILTER_DTYPE)
    scal = _event_scalars_a3(model, kind, dt, ctl_t, msk_t, mu_from_control)
    return scal


class AsOfWalkerA3(object):
    """Incremental A3 as-of filter for one (cell, query arm, model arm).

    Semantics -- exactly a3_model's segment engine (_run_events_a3):
      * events are buffered since the last RPT position; hitting an RPT event
        flushes the buffered segment with _segment_advance under the frozen
        linearization (a, b) carried from the last SCORED RPT update, then
        applies the Joseph measurement update correct_rpt with the arm's
        rate_update flag and refreshes (a, b) from the post-update mean;
      * a query cut mid-segment flushes the partial buffer with the SAME
        carried (a, b); composing the pieces is an exact affine semigroup
        (documented guarantee of a3_model.py), so query timing never changes
        the filter;
      * delay7d keeps the base at q - 7d and applies only completed cycles in
        (q - 7d, q] to the snapshot; RPT events in that window are ghosts
        (counted as n_late_arrival_excluded, never applied), exactly like
        a2_infer.AsOfWalker;
      * the tail interval (last event, q] propagates with masked control as a
        pseudo-event under the carried (a, b) (A2's "no invented operations"
        as-of convention).
    All filter tensors are float64; the model is a float32 checkpoint state
    cast to float64 (a3_fixtures discipline).
    """

    def __init__(self, model, sequence, lag_seconds, cfg):
        self.model = model
        self.cfg = cfg
        self.mu_from_control = bool(cfg["mu_from_control"])
        self.ell_state = bool(cfg["ell_state"])
        self.rate_update = bool(cfg["rate_update"])
        self.events = sequence["events"]
        self.lag = float(lag_seconds)
        self.q_ref = torch.tensor([float(sequence["q_ref_ah"])],
                                  dtype=FILTER_DTYPE)
        self.idx = 0
        self.prev = float(sequence["anchor"]["source_epoch"])
        self.base_m, self.base_P = model.initial_state(
            1, dtype=FILTER_DTYPE)
        self.a_lin, self.b_gain = model.frozen_linearization(
            self.base_m[:, 1])
        self._buf = []  # (kind_code, dt_weeks, control, control_mask)
        self.n_cycles = 0
        self.n_rpt = 0
        self.last_control = None
        self.last_control_mask = None
        self.last_control_epoch = None
        self.last_q = None
        self.last_base_epoch = self.prev
        self.rpt_trace = []  # (epoch, innovation_ah, var_ah2, nll) scored only

    # -- segment engine -----------------------------------------------------
    def _flush(self):
        """Advance the buffered segment with the carried frozen (a, b)."""
        n = len(self._buf)
        if n == 0:
            return
        kind = torch.tensor([[row[0] for row in self._buf]],
                            dtype=torch.long)
        dt = torch.tensor([[row[1] for row in self._buf]],
                          dtype=FILTER_DTYPE)
        ctl = torch.zeros(1, n, self.model.control_dim, dtype=FILTER_DTYPE)
        msk = torch.zeros(1, n, self.model.control_dim, dtype=FILTER_DTYPE)
        for j, (k, _d, c, m) in enumerate(self._buf):
            if k == 1 and c is not None:
                ctl[0, j] = torch.as_tensor(c, dtype=FILTER_DTYPE)
                msk[0, j] = torch.as_tensor(m, dtype=FILTER_DTYPE)
        scal = _event_scalars_a3(self.model, kind, dt, ctl, msk,
                                 self.mu_from_control)
        self.base_m, self.base_P = _segment_advance(
            self.model, self.base_m, self.base_P, scal, 0, n,
            self.a_lin, self.b_gain, self.ell_state)
        self._buf = []

    def _apply_rpt(self, event):
        """Scored-RPT innovation NLL + Joseph update (arm's rate_update)."""
        self.n_rpt += 1
        if not bool(event.get("score", False)):
            return
        y = torch.tensor([float(event["capacity_ah"])], dtype=FILTER_DTYPE)
        mu_cap, _latent, S, _H = self.model.capacity_moments(
            self.base_m, self.base_P, self.q_ref)
        nu = y - mu_cap
        nll = 0.5 * (nu.square() / S + torch.log(S) + LOG_2PI)
        self.rpt_trace.append((float(event["source_epoch"]), float(nu),
                               float(S), float(nll)))
        self.base_m, self.base_P, _, _ = self.model.correct_rpt(
            self.base_m, self.base_P, self.q_ref, y,
            rate_update=self.rate_update)
        self.a_lin, self.b_gain = self.model.frozen_linearization(
            self.base_m[:, 1])

    def _advance_base_to(self, cutoff):
        if cutoff < self.last_base_epoch - 1e-9:
            raise InferenceError("as-of walker moved backwards")
        while (self.idx < len(self.events)
               and float(self.events[self.idx]["source_epoch"])
               <= cutoff + 1e-9):
            event = self.events[self.idx]
            dt = max(0.0, (float(event["source_epoch"]) - self.prev)
                     / WEEK_SECONDS)
            if event["kind"] == "cycle":
                self._buf.append((1, dt, event["control"],
                                  event["control_mask"]))
                self.prev = float(event["source_epoch"])
                self.n_cycles += 1
                self.last_control = torch.tensor(
                    [event["control"]], dtype=FILTER_DTYPE)
                self.last_control_mask = torch.tensor(
                    [event["control_mask"]], dtype=FILTER_DTYPE)
                self.last_control_epoch = self.prev
            else:
                self._buf.append((2, dt, None, None))
                self.prev = float(event["source_epoch"])
                self._flush()          # RPT position ends the segment
                self._apply_rpt(event)
            self.idx += 1
            self.last_base_epoch = self.prev

    # -- queries -------------------------------------------------------------
    def state_at(self, query_epoch):
        q = float(query_epoch)
        if self.last_q is not None and q < self.last_q - 1e-9:
            raise InferenceError("as-of walker queries must be monotone")
        self.last_q = q
        cutoff = q - self.lag
        self._advance_base_to(cutoff)
        self._flush()  # partial segment up to the cutoff, carried (a, b)
        m = self.base_m.clone()
        P = self.base_P.clone()
        prev = self.prev
        a_lin, b_gain = self.a_lin, self.b_gain
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
                    scal = _single_event_scalars(
                        self.model, 1, dt, event["control"],
                        event["control_mask"], self.mu_from_control)
                    m, P = _segment_advance(
                        self.model, m, P, scal, 0, 1, a_lin, b_gain,
                        self.ell_state)
                    prev = float(event["source_epoch"])
                    n_cycles += 1
                    last_control = torch.tensor(
                        [event["control"]], dtype=FILTER_DTYPE)
                    last_control_mask = torch.tensor(
                        [event["control_mask"]], dtype=FILTER_DTYPE)
                    last_control_epoch = prev
                else:
                    n_late += 1  # ghost: arrived after the query cutoff
                j += 1
        if q > prev + 1e-9:
            scal = _single_event_scalars(self.model, 1,
                                         (q - prev) / WEEK_SECONDS,
                                         None, None, self.mu_from_control)
            m, P = _segment_advance(self.model, m, P, scal, 0, 1,
                                    a_lin, b_gain, self.ell_state)
        return {
            "m": m, "P": P,
            "n_cycles_used": n_cycles, "n_rpt_used": n_rpt,
            "n_late_arrival_excluded": n_late,
            "last_control": last_control,
            "last_control_mask": last_control_mask,
            "last_control_epoch": last_control_epoch,
        }


def reference_asof_state_a3(model, sequence, query_epoch, cfg, lag_seconds):
    """Authoritative non-incremental as-of filter (role of a2_targets
    .replay_asof for A3): re-filters from the anchor for THIS query only,
    O(events).  Used by --self-check to validate AsOfWalkerA3 elementwise.
    Segment flushes are one-shot _segment_advance calls with the carried
    (a, b) -- the same primitives as the walker."""
    events = sequence["events"]
    lag = float(lag_seconds)
    q = float(query_epoch)
    m, P = model.initial_state(1, dtype=FILTER_DTYPE)
    a_lin, b_gain = model.frozen_linearization(m[:, 1])
    prev = float(sequence["anchor"]["source_epoch"])
    n_cycles = n_rpt = n_late = 0
    last_control = None
    last_mask = None
    last_epoch = None
    buf = []

    def flush():
        nonlocal m, P
        if not buf:
            return
        kind = torch.tensor([[row[0] for row in buf]], dtype=torch.long)
        dt = torch.tensor([[row[1] for row in buf]], dtype=FILTER_DTYPE)
        ctl = torch.zeros(1, len(buf), model.control_dim,
                          dtype=FILTER_DTYPE)
        msk = torch.zeros(1, len(buf), model.control_dim,
                          dtype=FILTER_DTYPE)
        for j, (k, _d, c, mk) in enumerate(buf):
            if k == 1 and c is not None:
                ctl[0, j] = torch.as_tensor(c, dtype=FILTER_DTYPE)
                msk[0, j] = torch.as_tensor(mk, dtype=FILTER_DTYPE)
        scal = _event_scalars_a3(model, kind, dt, ctl, msk,
                                 cfg["mu_from_control"])
        m, P = _segment_advance(model, m, P, scal, 0, len(buf),
                                a_lin, b_gain, cfg["ell_state"])
        buf.clear()

    cutoff = q - lag
    for event in events:
        if float(event["source_epoch"]) > cutoff + 1e-9:
            break
        dt = max(0.0, (float(event["source_epoch"]) - prev) / WEEK_SECONDS)
        if event["kind"] == "cycle":
            buf.append((1, dt, event["control"], event["control_mask"]))
            prev = float(event["source_epoch"])
            n_cycles += 1
            last_control = torch.tensor([event["control"]],
                                        dtype=FILTER_DTYPE)
            last_mask = torch.tensor([event["control_mask"]],
                                     dtype=FILTER_DTYPE)
            last_epoch = prev
        else:
            buf.append((2, dt, None, None))
            prev = float(event["source_epoch"])
            flush()
            n_rpt += 1
            if bool(event.get("score", False)):
                y = torch.tensor([float(event["capacity_ah"])],
                                 dtype=FILTER_DTYPE)
                m, P, _, _ = model.correct_rpt(m, P, model_q_ref(sequence), y,
                                               rate_update=bool(
                                                   cfg["rate_update"]))
                a_lin, b_gain = model.frozen_linearization(m[:, 1])
    flush()
    if lag > 0.0:
        for event in events:
            if float(event["source_epoch"]) <= cutoff + 1e-9:
                continue
            if float(event["source_epoch"]) > q + 1e-9:
                break
            if event["kind"] == "cycle":
                dt = max(0.0, (float(event["source_epoch"]) - prev)
                         / WEEK_SECONDS)
                scal = _single_event_scalars(model, 1, dt, event["control"],
                                             event["control_mask"],
                                             cfg["mu_from_control"])
                m, P = _segment_advance(model, m, P, scal, 0, 1,
                                        a_lin, b_gain, cfg["ell_state"])
                prev = float(event["source_epoch"])
                n_cycles += 1
                last_control = torch.tensor([event["control"]],
                                            dtype=FILTER_DTYPE)
                last_mask = torch.tensor([event["control_mask"]],
                                         dtype=FILTER_DTYPE)
                last_epoch = prev
            else:
                n_late += 1
    if q > prev + 1e-9:
        scal = _single_event_scalars(model, 1, (q - prev) / WEEK_SECONDS,
                                     None, None, cfg["mu_from_control"])
        m, P = _segment_advance(model, m, P, scal, 0, 1, a_lin, b_gain,
                                cfg["ell_state"])
    return {"m": m, "P": P, "n_cycles_used": n_cycles, "n_rpt_used": n_rpt,
            "n_late_arrival_excluded": n_late, "last_control": last_control,
            "last_control_mask": last_mask,
            "last_control_epoch": last_epoch}


def model_q_ref(sequence):
    return torch.tensor([float(sequence["q_ref_ah"])], dtype=FILTER_DTYPE)


def engine_full_replay_a3(model, sequence, cfg):
    """a3_model._run_events_a3 over the cell's full event sequence (the
    authoritative batch engine, want_trace).  Returns (final state, trace)."""
    events = sequence["events"]
    T = len(events)
    kind = torch.zeros(1, T, dtype=torch.long)
    dt = torch.zeros(1, T, dtype=FILTER_DTYPE)
    ctl = torch.zeros(1, T, model.control_dim, dtype=FILTER_DTYPE)
    msk = torch.zeros(1, T, model.control_dim, dtype=FILTER_DTYPE)
    y = torch.zeros(1, T, dtype=FILTER_DTYPE)
    score = torch.zeros(1, T, dtype=torch.bool)
    prev = float(sequence["anchor"]["source_epoch"])
    for t, event in enumerate(events):
        dt[0, t] = max(0.0, (float(event["source_epoch"]) - prev)
                       / WEEK_SECONDS)
        prev = float(event["source_epoch"])
        if event["kind"] == "cycle":
            kind[0, t] = 1
            ctl[0, t] = torch.as_tensor(event["control"], dtype=FILTER_DTYPE)
            msk[0, t] = torch.as_tensor(event["control_mask"],
                                        dtype=FILTER_DTYPE)
        else:
            kind[0, t] = 2
            y[0, t] = float(event["capacity_ah"])
            score[0, t] = bool(event.get("score", False))
    m0, P0 = model.initial_state(1, dtype=FILTER_DTYPE)
    q_ref = model_q_ref(sequence)
    m, P, _nll, _n, _frozen, trace = _run_events_a3_wrapped(
        model, kind, dt, ctl, msk, y, score, q_ref, m0, P0, cfg)
    return m, P, trace


def _run_events_a3_wrapped(model, kind, dt, ctl, msk, y, score, q_ref,
                           m0, P0, cfg):
    from a3_model import _run_events_a3
    return _run_events_a3(model, kind, dt, ctl, msk, y, score, q_ref,
                          m0, P0, cfg, collect_nll=True, want_trace=True)


# ---------------------------------------------------------------------------
# Prediction / output (A3 columns: 3-dim state + model_ell_state; all other
# column names identical to a2_infer.CSV_FIELDS)
# ---------------------------------------------------------------------------
def _moments(model, m, P, q_ref):
    mu, latent, total, _ = model.capacity_moments(m, P, q_ref)
    return {
        "mean_ah": float(mu.detach()),
        "latent_var_ah2": float(latent.detach()),
        "var_ah2": float(total.detach()),
        "sd_ah": float(torch.sqrt(total.detach())),
    }


def _advance_horizon(model, m, P, horizon_weeks, control, mask, q_ref, cfg):
    dt = float(horizon_weeks)
    m2, P2 = model.advance(m, P, torch.tensor([dt], dtype=m.dtype,
                                              device=m.device),
                           control, mask, cfg)
    return _moments(model, m2, P2, q_ref)


CONTROL_FIELDS = tuple(name for name, _ in a2_prep.CONTROL_FIELDS)
assert len(CONTROL_FIELDS) == CONTROL_DIM == 24


def _csv_fields_a3():
    core = [
        "query_id", "cell_id", "group_id", "arm", "model_key", "model_arm",
        "model_use_cycle", "model_use_rpt", "model_ell_state",
        "query_epoch", "query_utc", "anchor_stop_epoch", "anchor_stop_utc",
        "anchor_arrival_epoch", "anchor_index", "visible_records",
        "visible_source_indices", "visible_capacity_min_ah",
        "qref_ah", "qref_anchor_stop_epoch", "qref_anchor_utc",
        "state_D", "state_ell", "state_R",
        "state_P00", "state_P01", "state_P02",
        "state_P11", "state_P12", "state_P22",
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


CSV_FIELDS = _csv_fields_a3()


class _CellAccumulatorA3(_CellAccumulator):
    """a2_infer._CellAccumulator extended with over_20mAh / over_50mAh
    exceedance counters (copied + extended; the base lacks the counters)."""

    def add(self, cell_id, nll=None, abs_err=None, sq_err=None,
            cov50=None, cov90=None, cov95=None, over20=None, over50=None):
        rec = self.cells.setdefault(cell_id, {
            "n": 0, "sum_nll": 0.0, "sum_abs": 0.0, "sum_sq": 0.0,
            "n_cov50": 0, "n_cov90": 0, "n_cov95": 0,
            "n_over20": 0, "n_over50": 0})
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
        if over20 is not None:
            rec["n_over20"] += int(over20)
        if over50 is not None:
            rec["n_over50"] += int(over50)

    def block(self):
        out = super().block()
        cells = [c for c, rec in self.cells.items() if rec["n"] > 0]
        if cells:
            n = sum(self.cells[c]["n"] for c in cells)
            out["over_20mah_cell_macro"] = float(np.mean(
                [self.cells[c]["n_over20"] / self.cells[c]["n"]
                 for c in cells]))
            out["over_50mah_cell_macro"] = float(np.mean(
                [self.cells[c]["n_over50"] / self.cells[c]["n"]
                 for c in cells]))
            out["over_20mah_pooled"] = float(
                sum(self.cells[c]["n_over20"] for c in cells) / n)
            out["over_50mah_pooled"] = float(
                sum(self.cells[c]["n_over50"] for c in cells) / n)
        return out


class _MetricBookA3(_MetricBook):
    """_MetricBook over the extended accumulator."""

    def __init__(self):
        super().__init__()
        self._acc = _CellAccumulatorA3

    def add(self, key, cell_id, **kwargs):
        self.groups.setdefault(key, _CellAccumulatorA3()) \
            .add(cell_id, **kwargs)
        self.rows[key] = self.rows.get(key, 0) + 1


def _control_for_output(state, model_cfg):
    if not model_cfg["mu_from_control"]:
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
        "model_use_cycle": int(cfg["mu_from_control"]),
        "model_use_rpt": int(cfg["rate_update"]),
        "model_ell_state": int(cfg["ell_state"]),
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
        "state_ell": float(state["m"][0, 1]),
        "state_R": float(state["m"][0, 2]),
        "state_P00": float(state["P"][0, 0, 0]),
        "state_P01": float(state["P"][0, 0, 1]),
        "state_P02": float(state["P"][0, 0, 2]),
        "state_P11": float(state["P"][0, 1, 1]),
        "state_P12": float(state["P"][0, 1, 2]),
        "state_P22": float(state["P"][0, 2, 2]),
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
                                q_ref, cfg)
        target = _match_horizon_target(cell, q, h, HORIZON_TOLERANCE_WEEKS)
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
                                                 pred["var_ah2"],
                                                 1.959963984540054)

    gap = query["gap_weeks"]
    row["gap_weeks"] = _blank(gap)
    row["next_source_rpt_index"] = _blank(query["next_source_rpt_index"])
    row["next_source_stop_epoch"] = _blank(query["next_source_stop_epoch"])
    row["target_capacity_ah"] = _blank(query["target_capacity_ah"])
    row["target_available"] = int(gap is not None)
    if gap is None:
        for key in ("pred_mean_ah", "pred_latent_var_ah2", "pred_var_ah2",
                    "pred_sd_ah", "innovation_ah", "abs_error_ah",
                    "sq_error_ah2", "nll_per_ah", "covered_50", "covered_90",
                    "covered_95"):
            row[key] = ""
    else:
        pred = _advance_horizon(model, state["m"], state["P"], gap, ctl, msk,
                                q_ref, cfg)
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
            cov95=row["covered_95"],
            over20=int(row["abs_error_ah"] > OVER_ERROR_AH[0]),
            over50=int(row["abs_error_ah"] > OVER_ERROR_AH[1]))
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


def _update_rpt_metrics(book, arm, model_key, cell_id, rpt_trace):
    """RPT innovation scoring along the filter path (A3 observation model)."""
    for _epoch, innovation, var, nll in rpt_trace:
        sd = math.sqrt(max(float(var), 1e-30))
        payload = dict(
            nll=float(nll), abs_err=abs(float(innovation)),
            sq_err=float(innovation) ** 2,
            cov90=int(abs(float(innovation)) <= 1.6448536269514722 * sd))
        book.add(("rpt_model", arm, model_key), cell_id, **payload)
        book.add(("rpt_arm", arm), cell_id, **payload)
        book.add(("rpt_overall", "all"), cell_id, **payload)


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


METRIC_DEFINITIONS = {
    "nll": "Gaussian NLL of the scored target under the predicted "
           "N(mean, total variance) in Ah^2; cell-macro = mean over cells",
    "rmse": "sqrt(mean_cell MSE) with equal cell weight",
    "cov90": "fraction with |y - mean| <= 1.6448536269514722 * sd, "
             "cell-macro",
    "over_20mah": "fraction of scored queries with |error| > 0.020 Ah, "
                  "cell-macro",
    "over_50mah": "fraction of scored queries with |error| > 0.050 Ah, "
                  "cell-macro",
}


# ---------------------------------------------------------------------------
# Inference execution
# ---------------------------------------------------------------------------
def execute_inference(cells, models, binding, out_dir, deadline=None,
                      progress=True, rss_cap_gb=None, rss_check=None):
    """Run all query/arm/model predictions; write predictions CSV + summary."""
    stats = binding.get("stats") or ReadStats()
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "predictions_c3_a3.csv")
    tmp_csv = csv_path + ".tmp"
    metric_book = _MetricBookA3()
    arm_query_counts = {arm: 0 for arm in QUERY_ARMS}
    skipped = {"cells_fewer_than_4_rpt": 0, "cells_no_query": 0}
    skipped.update({arm + "_" + key: 0 for arm in QUERY_ARMS
                    for key in ("warmup", "visible_lt_min", "duplicate_anchor",
                                "visible_threshold")})
    cell_records = []
    n_rows = 0
    n_query_models = 0
    n_rpt_innovations = 0
    # The models dict is the single source of truth for which arms run: the
    # full four-arm set by default, or exactly the GO's checkpoint_subset.
    model_keys = sorted(models)
    checkpoint_subset = binding.get("checkpoint_subset")
    qref_by_cell = {}
    per_cell_queries = {}

    with torch.no_grad():   # whole body: the 30 GB autograd lesson, belt+braces
        with open(tmp_csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS,
                                    extrasaction="ignore")
            writer.writeheader()
            for ci, cell in enumerate(cells):
                if deadline is not None and time.monotonic() > deadline:
                    raise TimeoutError("inference runtime deadline reached")
                if rss_check is not None:
                    rss_check()
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
                        seq = a2_prep.cell_sequence(cid, cell["cycles"],
                                                    rpts_arm, cutoff_epoch=None)
                    except a2_prep.PrepError as exc:
                        raise InferenceError(
                            "cell %s arm %s sequence refused: %s"
                            % (cid, arm, exc))
                    if seq.get("anchor") is None:
                        raise InferenceError("cell %s arm %s has no anchor"
                                             % (cid, arm))
                    if qref is None:
                        qref = float(seq["q_ref_ah"])
                        qref_by_cell[cid] = qref
                    elif abs(qref - float(seq["q_ref_ah"])) > 1e-12:
                        raise InferenceError(
                            "cell %s q_ref differs across arms" % cid)
                    queries, skips, why = build_queries(cell, arm, policy)
                    if why:
                        raise InferenceError(
                            "cell %s arm %s query grid refused: %s"
                            % (cid, arm, why))
                    arm_sequences[arm] = seq
                    arm_queries[arm] = queries
                    cell_query_counts[arm] = len(queries)
                    arm_query_counts[arm] += len(queries)
                    for key, value in skips.items():
                        skipped[arm + "_" + key] += int(value)
                if sum(cell_query_counts.values()) == 0:
                    skipped["cells_no_query"] += 1
                q_ref_t = torch.tensor([qref], dtype=FILTER_DTYPE)
                for arm in QUERY_ARMS:
                    seq = arm_sequences[arm]
                    queries = arm_queries[arm]
                    walkers = {}
                    for model_key in model_keys:
                        cfg = MODEL_ARMS[model_key]
                        walkers[model_key] = AsOfWalkerA3(
                            models[model_key], seq,
                            DELAY7D_SECONDS if arm == "delay7d" else 0.0,
                            cfg)
                    for qi, query in enumerate(queries):
                        if deadline is not None and \
                                time.monotonic() > deadline:
                            raise TimeoutError(
                                "inference runtime deadline reached")
                        if rss_check is not None and qi % 25 == 0:
                            rss_check()
                        for model_key in model_keys:
                            with torch.no_grad():
                                state = walkers[model_key].state_at(
                                    query["query_epoch"])
                                row = _row_for_query(
                                    cell, arm, query, model_key,
                                    models[model_key], state, qref, seq)
                            writer.writerow({k: _blank(v)
                                             for k, v in row.items()})
                            _update_metrics(metric_book, row)
                            n_rows += 1
                            n_query_models += 1
                    for model_key in model_keys:
                        trace = walkers[model_key].rpt_trace
                        n_rpt_innovations += len(trace)
                        _update_rpt_metrics(metric_book, arm, model_key,
                                            cid, trace)
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
        "rpt_innovations": {
            "overall": metric_book.block(("rpt_overall", "all")),
            "by_arm": [{"arm": k[1], **metric_book.block(k)}
                       for k in sorted(metric_book.groups)
                       if isinstance(k, tuple) and k[0] == "rpt_arm"],
            "by_model": [{"model_key": k[1], **metric_book.block(k)}
                         for k in sorted(metric_book.groups)
                         if isinstance(k, tuple) and k[0] == "rpt_model"],
        },
        "fixed_horizons": [],
        "metric_definitions": METRIC_DEFINITIONS,
    }
    for h in HORIZONS_WEEKS:
        for arm in QUERY_ARMS:
            for model_key in model_keys:
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
        "model_arms": {k: {kk: vv for kk, vv in v.items()}
                       for k, v in sorted(MODEL_ARMS.items())
                       if k in model_keys},
        "checkpoint_subset": checkpoint_subset,
        "filter_dtype": "torch.float64",
        "cells": cell_records,
        "counts": {
            "n_cells": len(cells),
            "n_cells_skipped": skipped.get("cells_fewer_than_4_rpt", 0)
                               + skipped.get("cells_no_query", 0),
            "n_queries": int(sum(arm_query_counts.values())),
            "n_queries_by_arm": arm_query_counts,
            "n_prediction_rows": int(n_rows),
            "n_query_models": int(n_query_models),
            "n_models": len(model_keys),
            "n_query_arms": len(QUERY_ARMS),
            "n_scored_rpt_innovations": int(n_rpt_innovations),
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


def _atomic_json(path, payload):
    text = json.dumps(_json_safe(payload), indent=2, ensure_ascii=False) + "\n"
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return path


def _write_receipt(out_dir, receipt_path, summary, status, error=None,
                   started=None, elapsed=None, registration=None,
                   rss_peak_gb=None):
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": status,
        "created_utc": _utc_now(),
        "started_utc": started,
        "elapsed_seconds": elapsed,
        "rss_peak_gb": rss_peak_gb,
        "consumes_go": bool(registration),
        "go_consumption": (
            "request_id registered in the canonical consumed-GO registry "
            "after full success (a3_train.register_consumed_go)"
            if registration else
            "nothing registered: refused/failed runs and synthetic "
            "self-checks never touch the registry"),
        "registration": registration,
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
        "c4_cells_read": 0,
    }
    out_receipt = os.path.join(out_dir, "receipt.json")
    _atomic_json(out_receipt, receipt)
    written = [out_receipt]
    if receipt_path and \
            os.path.realpath(receipt_path) != os.path.realpath(out_receipt):
        if os.path.exists(receipt_path):
            raise InferenceError("receipt_path appeared after preflight: %s"
                                 % receipt_path)
        _atomic_json(receipt_path, receipt)
        written.append(receipt_path)
    return receipt, written


# ---------------------------------------------------------------------------
# Real GO-gated run
# ---------------------------------------------------------------------------
def run_go(go_path, threads=8, verbose=True,
           registry_path=None):
    started = time.monotonic()
    start_iso = _utc_now()
    stats = ReadStats()
    out_dir = None
    receipt_path = None
    try:
        go = _json_load(go_path, "GO")
    except InferenceError as exc:
        print("REFUSED -- %s" % exc)
        return 3
    problems, norm = validate_go_document_a3(go)
    if problems:
        print("REFUSED -- GO validation failed (%d problem(s)):" % len(problems))
        for problem in problems:
            print("  - %s" % problem)
        print("NO FILE WRITTEN. NO DATA READ. NO CHECKPOINT READ. "
              "NO GO CONSUMED.")
        return 3
    binding, problems = validate_go_bindings_a3(norm, stats,
                                                registry_path=registry_path)
    if problems:
        print("REFUSED -- GO binding/hash validation failed (%d problem(s)):"
              % len(problems))
        for problem in problems:
            print("  - %s" % problem)
        print("NO FILE WRITTEN. NO GO CONSUMED.")
        return 3
    go_sha = hash_file(go_path)
    binding["go_info"] = {
        "path": os.path.abspath(go_path),
        "sha256": go_sha,
        "status": norm["status"],
        "owner_thread_id": OWNER_THREAD_ID,
        "data_scope": DATA_SCOPE,
        "device": "cpu",
        "no_grad": True,
        "max_rss_gb": norm["max_rss_gb"],
        "max_runtime_seconds": norm["max_runtime_seconds"],
        "request_id": norm.get("request_id"),
        "checkpoint_subset": norm.get("checkpoint_subset"),
    }
    binding["stats"] = stats
    out_dir = binding["output_dir"]
    receipt_path = binding["receipt_path"]
    rss_cap_gb = float(norm["max_rss_gb"] or DEFAULT_MAX_RSS_GB)
    os.makedirs(out_dir, exist_ok=True)
    deadline = started + float(norm["max_runtime_seconds"])

    def rss_check():
        _check_rss(rss_cap_gb)

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
        print("GO ACCEPTED (A3 C3 inference only): %s"
              % binding["go_info"]["path"])
        print("  go_sha256=%s" % go_sha)
        print("  cells=%d model_arms=%s device=cpu no_grad=True "
              "max_runtime=%ss max_rss_gb=%.2f"
              % (len(binding["dev_specs"]),
                 binding.get("model_arms") or sorted(MODEL_ARMS),
                 norm["max_runtime_seconds"], rss_cap_gb))
        cells = []
        for i, spec in enumerate(binding["dev_specs"]):
            if time.monotonic() > deadline:
                raise TimeoutError("runtime deadline before cell load")
            rss_check()
            cell = load_cell(spec, stats)
            cells.append(cell)
            if verbose:
                print("  loaded cell %d/%d %s (%s)"
                      % (i + 1, len(binding["dev_specs"]), spec["cell_id"],
                         cell.get("skip_reason") or "ok"))
        summary, stats = execute_inference(
            cells, binding["models"], binding, out_dir, deadline=deadline,
            progress=verbose, rss_cap_gb=rss_cap_gb, rss_check=rss_check)
        summary["runtime_seconds"] = time.monotonic() - started
        summary["rss_peak_gb"] = _rss_gb()
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
        # GO consumption: register the request_id only after a fully
        # successful inference (a3_train.register_consumed_go discipline).
        registration = None
        request_id = norm.get("request_id")
        if request_id:
            finished = _utc_now()
            line = register_consumed_go(binding["registry_path"], request_id,
                                        go_sha, finished)
            registration = {"request_id": str(request_id),
                            "go_sha256": go_sha,
                            "finished_utc": finished,
                            "registry": binding["registry_path"],
                            "line": line}
        summary["go_consumption"] = registration
        receipt, written = _write_receipt(
            out_dir, receipt_path, summary, "C3_INFERENCE_COMPLETE",
            started=start_iso, elapsed=time.monotonic() - started,
            registration=registration, rss_peak_gb=summary["rss_peak_gb"])
        print("A3 C3 INFERENCE COMPLETE: cells=%d queries=%d rows=%d"
              % (summary["counts"]["n_cells"],
                 summary["counts"]["n_queries"],
                 summary["counts"]["n_prediction_rows"]))
        print("  predictions=%s" % summary["outputs"]["predictions_csv"])
        print("  summary=%s" % summary["outputs"]["summary_json"])
        for path in written:
            print("  receipt=%s" % path)
        if registration:
            print("  registered consumed GO: request_id=%s registry=%s"
                  % (registration["request_id"],
                     registration["registry"]))
        print("NO FIT. NO OPTIMIZER STEP. NO C4/RAW READ.")
        return 0
    except BaseException as exc:  # noqa: BLE001
        error = "%s: %s" % (type(exc).__name__, exc)
        print("A3 C3 INFERENCE FAILED: %s" % error)
        traceback.print_exc(file=sys.stdout)
        try:
            if out_dir and os.path.isdir(out_dir):
                _write_receipt(out_dir, receipt_path, None,
                               "C3_INFERENCE_FAILED", error=error,
                               started=start_iso,
                               elapsed=time.monotonic() - started,
                               rss_peak_gb=_rss_gb())
                print("  failure receipt written (partial output retained "
                      "for diagnosis)")
        except Exception as receipt_exc:  # noqa: BLE001
            print("  could not write failure receipt: %s" % receipt_exc)
        print("NO GO CONSUMED (request_id not registered).")
        return 2
    finally:
        if alarm_installed:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)


# ---------------------------------------------------------------------------
# Self-check (synthetic only)
# ---------------------------------------------------------------------------
_DAY = 86400.0
_Z9 = "0" * 64


def _synth_models_a3(seed=42):
    """In-memory A3 arm models (float64 filter copies); NO checkpoint file."""
    models = {}
    for key in sorted(MODEL_ARMS):
        model = build_arm_model(key, seed=seed)
        model.eval()
        models[key] = model.double()
    return models


def _synth_binding_a3(code_hashes=None, arms=None):
    """Synthetic binding; arms=None -> the full four-arm default, otherwise
    exactly the given checkpoint_subset (checkpoint_info restricted too)."""
    keys = sorted(arms) if arms else sorted(MODEL_ARMS)
    return {
        "code_sha256": code_hashes or {
            name: "a" * 64 for name in REQUIRED_CODE},
        "sources": {},
        "checkpoint_subset": sorted(arms) if arms else None,
        "model_arms": keys,
        "checkpoint_info": {
            key: {"path": "synthetic://%s" % key, "sha256": "synthetic",
                  "note": "self-check builds models in memory; no checkpoint "
                          "file is read"}
            for key in keys},
        "query_contract": {
            "arms": list(QUERY_ARMS),
            "horizons_weeks": list(HORIZONS_WEEKS),
            "min_visible_records": MIN_VISIBLE_RECORDS,
            "query_threshold_ah": THRESHOLD_AH,
            "delay7d_seconds": DELAY7D_SECONDS,
            "horizon_tolerance_weeks": HORIZON_TOLERANCE_WEEKS,
            "dedupe": "(arm, query_anchor_source_rpt_index)",
        },
        "go_info": {"status": "SELF_CHECK", "device": "cpu"},
        "stats": ReadStats(),
    }


def _go_doc_for_self_check(root):
    code = {name: "a" * 64 for name in REQUIRED_CODE}
    ck = {}
    for key in sorted(MODEL_ARMS):
        ck[key] = {"path": os.path.join(root, key + ".pt"),
                   "sha256": "b" * 64}
    return {
        "status": GO_STATUS, "allow_inference": True, "allow_fit": False,
        "allow_train": False, "allow_C4": False, "no_grad": True,
        "max_rss_gb": 2.0,
        "owner_thread_id": OWNER_THREAD_ID, "data_scope": DATA_SCOPE,
        "device": "cpu", "max_runtime_seconds": 3600,
        "expected_cell_count": 3,
        "request_id": "a3-c3infer-selfcheck-0001",
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


def check_adapter_reuse(_root, emit):
    import copy
    cid = "G1C3"
    payload, doc = a2_infer._synth_payload(cid, 1_650_000_000.0, n_rpt=4)
    direct_ctl, direct_msk = a2_prep.cycle_control(doc["cycles"][0])
    # a2_prep itself must still refuse C3 (the role gate is intact).
    try:
        a2_prep.cycle_records_from_features(copy.deepcopy(doc), cid)
        raise AssertionError("a2_prep must still refuse role=development")
    except a2_prep.PrepError:
        pass
    cycles, ccount = _development_cycle_records(copy.deepcopy(doc), cid)
    rpts, rcount = _development_rpt_records(copy.deepcopy(payload), cid)
    assert len(cycles) == len(doc["cycles"])
    assert cycles[0]["control"] == direct_ctl
    assert cycles[0]["control_mask"] == direct_msk
    assert len(rpts) == len(payload["records"])
    assert rcount["rpt_rows"] == len(payload["records"])
    assert ccount["cycle_rows"] == len(doc["cycles"])
    # The query grid is a2_infer's own frozen code object, not a re-write.
    assert build_queries is a2_infer.build_queries
    assert _b2_arm_records is a2_infer._b2_arm_records
    assert _validate_query_contract is a2_infer._validate_query_contract
    emit("  a2_prep role gate intact; adapters project the role only; "
         "query-grid code objects are a2_infer's (identity)")


def check_query_grid_frozen(_root, emit):
    assert QUERY_ARMS == ("raw", "sparse2", "delay7d")
    assert HORIZONS_WEEKS == (1.0, 4.0, 12.0, 32.0)
    assert MIN_VISIBLE_RECORDS == 3 and THRESHOLD_AH == 0.20
    assert DELAY7D_SECONDS == 7.0 * 86400.0
    assert HORIZON_TOLERANCE_WEEKS == 0.5
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
        assert len({(q["arm"], q["anchor_index"]) for q in queries}) == \
            len(queries)
        assert all(q["visible_records"] >= 3 for q in queries)
        assert all(q["query_epoch"] >= rows[1]["stop_epoch"] + WEEK_SECONDS
                   for q in queries)
        assert all(q["visible_capacity_min_ah"] > THRESHOLD_AH
                   for q in queries)
    raw_idx = [q["anchor_index"] for q in build_queries(
        cell, "raw", _b2_arm_records(rows, 1, "raw"))[0]]
    sparse_idx = [q["anchor_index"] for q in build_queries(
        cell, "sparse2", _b2_arm_records(rows, 1, "sparse2"))[0]]
    delay_idx = [q["anchor_index"] for q in build_queries(
        cell, "delay7d", _b2_arm_records(rows, 1, "delay7d"))[0]]
    assert raw_idx == list(range(2, 12))
    assert sparse_idx == [3, 5, 7, 9, 11]
    assert delay_idx == list(range(2, 11))
    thr_rows = [dict(r) for r in rows]
    thr_rows[6]["capacityAh"] = 0.19
    thr_cell = {"rows": thr_rows}
    thr_counts = {arm: len(build_queries(
        thr_cell, arm, _b2_arm_records(thr_rows, 1, arm))[0])
        for arm in QUERY_ARMS}
    assert thr_counts == {"raw": 4, "sparse2": 5, "delay7d": 4}, thr_counts
    emit("  raw=%d sparse2=%d delay7d=%d (A2 frozen panel); threshold skip "
         "raw=4/sparse2=5/delay7d=4 verified"
         % (expected["raw"], expected["sparse2"], expected["delay7d"]))


def _synth_cell_and_arms(cid="G1C3", base=1_650_000_000.0, n_rpt=12,
                         **kwargs):
    payload, doc = a2_infer._synth_payload(cid, base, n_rpt=n_rpt, **kwargs)
    # a2_infer._build_synth_sequences returns (cell, per_arm_dict).
    _cell, arms = a2_infer._build_synth_sequences(payload, doc)
    return payload, doc, arms


def check_walker_equivalence(_root, emit):
    _payload, _doc, arms = _synth_cell_and_arms()
    max_dm = max_dp = max_dcnt = 0.0
    n_checked = 0
    n_bitexact = 0
    for arm in QUERY_ARMS:
        seq = arms[arm]["sequence"]
        lag = DELAY7D_SECONDS if arm == "delay7d" else 0.0
        for model_key in sorted(MODEL_ARMS):
            cfg = MODEL_ARMS[model_key]
            model = build_arm_model(model_key, seed=3).double().eval()
            walker = AsOfWalkerA3(model, seq, lag, cfg)
            for q in arms[arm]["queries"]:
                with torch.no_grad():
                    st = walker.state_at(q["query_epoch"])
                    ref = reference_asof_state_a3(
                        model, seq, q["query_epoch"], cfg, lag)
                dm = float(torch.max(torch.abs(st["m"] - ref["m"])))
                dp = float(torch.max(torch.abs(st["P"] - ref["P"])))
                max_dm = max(max_dm, dm)
                max_dp = max(max_dp, dp)
                if dm == 0.0 and dp == 0.0:
                    n_bitexact += 1
                assert st["n_cycles_used"] == ref["n_cycles_used"]
                assert st["n_rpt_used"] == ref["n_rpt_used"]
                assert st["n_late_arrival_excluded"] == \
                    ref["n_late_arrival_excluded"]
                n_checked += 1
    # The lag-0 walker at the last event must equal a3_model's own batch
    # engine (_run_events_a3) exactly, and the scored-RPT innovation NLLs
    # must equal the engine's want_trace values elementwise.
    arm = "raw"
    seq = arms[arm]["sequence"]
    cfg = MODEL_ARMS["full"]
    model = build_arm_model("full", seed=3).double().eval()
    walker = AsOfWalkerA3(model, seq, 0.0, cfg)
    last_epoch = max(float(e["source_epoch"]) for e in seq["events"])
    with torch.no_grad():
        st = walker.state_at(last_epoch)
        m_eng, P_eng, trace = engine_full_replay_a3(model, seq, cfg)
    d_eng = max(float(torch.max(torch.abs(st["m"] - m_eng))),
                float(torch.max(torch.abs(st["P"] - P_eng))))
    scored = [t for t in range(trace.shape[1])
              if not math.isnan(float(trace[0, t]))]
    walker_nll = [row[3] for row in walker.rpt_trace]
    engine_nll = [float(trace[0, t]) for t in scored]
    assert len(walker_nll) == len(engine_nll), \
        (len(walker_nll), len(engine_nll))
    max_dnll = max(abs(a - b) for a, b in zip(walker_nll, engine_nll))
    assert max_dm < 1e-9 and max_dp < 1e-9 and d_eng < 1e-9 \
        and max_dnll < 1e-9, (max_dm, max_dp, d_eng, max_dnll)
    emit("  walker == reference re-filter on %d query/arm/model states "
         "(max|dm|=%.2e max|dP|=%.2e; %d bit-exact); walker == a3_model "
         "engine at last event (max err=%.2e); RPT NLLs == engine trace "
         "(max|dnll|=%.2e over %d scored RPTs)"
         % (n_checked, max_dm, max_dp, n_bitexact, d_eng, max_dnll,
            len(engine_nll)))


def check_no_future_leakage(_root, emit):
    base_payload, base_doc, base_arms = _synth_cell_and_arms(
        "G1C3", n_rpt=12)
    fut_payload, fut_doc, fut_arms = _synth_cell_and_arms(
        "G1C3", n_rpt=12, future_extra=True)
    arm = "raw"
    cfg = MODEL_ARMS["full"]
    model = build_arm_model("full", seed=3).double().eval()
    seq_base = base_arms[arm]["sequence"]
    seq_fut = fut_arms[arm]["sequence"]
    assert len(seq_fut["events"]) > len(seq_base["events"])
    q = base_arms[arm]["queries"][-1]["query_epoch"]
    with torch.no_grad():
        a = AsOfWalkerA3(model, seq_base, 0.0, cfg).state_at(q)
        b = AsOfWalkerA3(model, seq_fut, 0.0, cfg).state_at(q)
    assert torch.max(torch.abs(a["m"] - b["m"])) == 0.0
    assert torch.max(torch.abs(a["P"] - b["P"])) == 0.0
    ref_a = reference_asof_state_a3(model, seq_base, q, cfg, 0.0)
    ref_b = reference_asof_state_a3(model, seq_fut, q, cfg, 0.0)
    assert torch.max(torch.abs(ref_a["m"] - ref_b["m"])) == 0.0
    # Prefix invariance of the frozen panel: the appended records create no
    # new query at or before q and change no earlier anchor set.
    qidx_base = [(x["query_epoch"], x["anchor_index"])
                 for x in base_arms[arm]["queries"]]
    qidx_fut = [(x["query_epoch"], x["anchor_index"])
                for x in fut_arms[arm]["queries"] if x["query_epoch"] <= q]
    assert qidx_base == qidx_fut
    emit("  appended future RPT/cycles leave the as-of state at q bit-"
         "identical and the query panel prefix unchanged")


def check_go_mutations(root, emit):
    good = _go_doc_for_self_check(root)
    problems, norm = validate_go_document_a3(good, expected_cells=3)
    assert not problems, problems
    assert set(norm["checkpoints"]) == set(MODEL_ARMS)
    assert norm["no_grad"] is True and norm["max_rss_gb"] == 2.0
    mutations = []

    def mut(label, fn):
        item = copy.deepcopy(good)
        fn(item)
        mutations.append((label, item))

    mut("status", lambda g: g.__setitem__("status", "APPROVED_C3_INFERENCE"))
    mut("allow_inference", lambda g: g.__setitem__("allow_inference", False))
    mut("allow_fit", lambda g: g.__setitem__("allow_fit", True))
    mut("allow_train", lambda g: g.__setitem__("allow_train", True))
    mut("allow_C4", lambda g: g.__setitem__("allow_C4", True))
    mut("owner", lambda g: g.__setitem__("owner_thread_id", "0" * 36))
    mut("scope", lambda g: g.__setitem__("data_scope", "C3_C4"))
    mut("device", lambda g: g.__setitem__("device", "cuda:0"))
    mut("runtime", lambda g: g.__setitem__("max_runtime_seconds", 0))
    mut("consumed", lambda g: g.__setitem__("consumed_at", "2026-01-01"))
    mut("no_grad_missing", lambda g: g.pop("no_grad"))
    mut("no_grad_false", lambda g: g.__setitem__("no_grad", False))
    mut("rss_cap", lambda g: g.__setitem__("max_rss_gb", 0.0))
    mut("code_missing", lambda g: g["code_sha256"].pop("a2_fastdata.py"))
    mut("code_bad_sha", lambda g: g["code_sha256"].__setitem__(
        "a3_model.py", "z" * 64))
    mut("checkpoint_missing", lambda g: g["checkpoints"].pop("noEll"))
    mut("checkpoint_sha_format", lambda g:
        g["checkpoints"]["time"].__setitem__("sha256", "not-a-hash"))
    mut("cells", lambda g: g.__setitem__("expected_cell_count", 63))
    mut("output_dir_relative", lambda g: g.__setitem__("output_dir", "out"))
    mut("receipt_relative", lambda g: g.__setitem__("receipt_path", "r.json"))
    mut("request_id_missing", lambda g: g.pop("request_id"))
    mut("horizon", lambda g: g["query_contract"].__setitem__(
        "horizons_weeks", [1, 4, 12]))
    mut("arms_list", lambda g: g.__setitem__("arms", ["full", "time"]))
    mut("registry_noncanonical", lambda g: g.__setitem__(
        "registry", "/tmp/evil_registry.jsonl"))
    mut("fits_nonzero", lambda g: g.__setitem__("fits", 2))
    for label, doc in mutations:
        bad, _ = validate_go_document_a3(doc, expected_cells=3)
        assert bad, "mutation %r was not rejected" % label
    emit("  valid GO accepted; %d refusal mutations rejected (status, flags, "
         "owner/scope/device, no_grad/RSS, code+checkpoint hashes, fresh "
         "paths, request_id, frozen query contract, registry pin)"
         % len(mutations))


def check_binding_refusals(root, emit):
    import copy as _copy
    tree_root = os.path.join(root, "binding_fixture")
    tree = a2_infer._write_synth_tree(tree_root, n_cells=2)
    docs = {k: _copy.deepcopy(tree[k]) for k in
            ("cohort", "data_manifest", "cycling_manifest", "rpt_manifest")}
    # The synth tree writes only the per-cell assets; materialise the four
    # manifest documents too (a2_infer._write_synth_tree returns them).
    man_paths = {"cohort": os.path.join(tree_root, "cohort.json"),
                 "data_manifest": os.path.join(tree_root,
                                               "data_manifest.json"),
                 "cycling_manifest": os.path.join(tree_root, "cycling.json"),
                 "rpt_manifest": os.path.join(tree_root, "rpt.json")}
    for label, path in man_paths.items():
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(tree[label], fh)
    # Positive: real hashes -> manifests load, dev specs resolve to C3 cells.
    src_norm = {
        "sources": {
            label: {"path": path, "sha256": hash_file(path)}
            for label, path in man_paths.items()
        },
        "expected_cell_count": 2,
    }
    stats = ReadStats()
    loaded = _load_manifest_sources(src_norm, stats)
    specs, _roots = _build_dev_specs(
        loaded["cohort"], loaded["data_manifest"],
        loaded["cycling_manifest"], loaded["rpt_manifest"], tree_root, 2)
    assert len(specs) == 2
    assert all(s["cell_id"].endswith("C3") for s in specs)
    # Role mutations stay refused (a2_infer._build_dev_specs reused).
    bad_cohort = _copy.deepcopy(docs["cohort"])
    bad_cohort["roles"]["G1C3"] = "locked"
    try:
        _build_dev_specs(bad_cohort, docs["data_manifest"],
                         docs["cycling_manifest"], docs["rpt_manifest"],
                         tree_root, 2)
        raise AssertionError("cohort role mutation was not rejected")
    except InferenceError:
        pass
    # GO-level binding refusals.
    def _binding(norm_override=None, registry=None, out_dir=None):
        norm = {
            "code_sha256": {name: hash_file(_code_path(name))
                            for name in REQUIRED_CODE},
            "sources": src_norm["sources"],
            "expected_cell_count": 2,
            "data_root": tree_root,
            "output_dir": out_dir or os.path.join(tree_root, "out_fresh"),
            "receipt_path": os.path.join(tree_root, "receipt_fresh.json"),
            "checkpoints": {key: {"path": os.path.join(root, key + ".bin"),
                                  "sha256": "b" * 64}
                            for key in sorted(MODEL_ARMS)},
            "request_id": "a3-c3infer-selfcheck-0002",
            "registry_path": registry or os.path.join(root, "registry.jsonl"),
        }
        if norm_override:
            norm.update(norm_override)
        return validate_go_bindings_a3(norm, ReadStats(),
                                       registry_path=norm["registry_path"])

    binding, problems = _binding()
    assert binding is None and problems, "bindings must refuse here"
    assert any("not found" in p or "not loadable" in p for p in problems), \
        problems  # the fake checkpoint files do not exist
    # (a) manifest sha mismatch
    bad_src = _copy.deepcopy(src_norm["sources"])
    bad_src["cohort"]["sha256"] = "c" * 64
    _b, problems = _binding({"sources": bad_src})
    assert any("sha256 mismatch" in p for p in problems), problems
    # (b) request_id already in the consumed-GO registry
    reg_path = os.path.join(root, "registry.jsonl")
    with open(reg_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"request_id": "a3-c3infer-selfcheck-0002",
                             "go_sha256": "x", "finished_utc": "y"}) + "\n")
    _b, problems = _binding(registry=reg_path)
    assert any("already appears in the consumed-GO registry" in p
               for p in problems), problems
    # (c) output_dir not fresh
    stale_out = os.path.join(tree_root, "out_stale")
    os.makedirs(stale_out, exist_ok=True)
    with open(os.path.join(stale_out, "junk.txt"), "w") as fh:
        fh.write("x")
    _b, problems = _binding(out_dir=stale_out)
    assert any("fresh/empty" in p for p in problems), problems
    # (d) checkpoint sha256 mismatch refuses BEFORE any torch.load
    fake = os.path.join(root, "fake_full.bin")
    with open(fake, "w", encoding="utf-8") as fh:
        fh.write("this is not a checkpoint; the sha check must fire first")
    spec = {"path": fake, "sha256": "b" * 64}
    try:
        _load_arm_model_a3("full", spec, ReadStats())
        raise AssertionError("wrong checkpoint sha256 was not rejected")
    except InferenceError as exc:
        assert "sha256 mismatch" in str(exc), str(exc)
    emit("  manifest hashing/dev-specs positive path ok; refusals: manifest "
         "sha, consumed request_id, stale out_dir, checkpoint sha mismatch "
         "(pre-load)")


def check_synthetic_pipeline(root, emit):
    tree_root = os.path.join(root, "pipeline_fixture")
    tree = a2_infer._write_synth_tree(tree_root, n_cells=3)
    specs, _roots = _build_dev_specs(
        tree["cohort"], tree["data_manifest"], tree["cycling_manifest"],
        tree["rpt_manifest"], tree_root, 3)
    stats = ReadStats()
    cells = [load_cell(spec, stats) for spec in specs]
    models = _synth_models_a3()
    binding = _synth_binding_a3()
    binding["stats"] = stats
    out_dir = os.path.join(tree_root, "out")
    receipt_path = os.path.join(tree_root, "receipt.json")
    summary, stats = execute_inference(cells, models, binding, out_dir,
                                       deadline=None, progress=False)
    receipt, written = _write_receipt(out_dir, receipt_path, summary,
                                      "C3_INFERENCE_COMPLETE",
                                      started=_utc_now(), elapsed=0.0,
                                      registration=None,
                                      rss_peak_gb=_rss_gb())
    assert summary["status"] == "C3_INFERENCE_COMPLETE"
    assert summary["counts"]["n_cells"] == 3
    assert summary["counts"]["n_prediction_rows"] == \
        4 * summary["counts"]["n_queries"]
    assert summary["counts"]["n_prediction_rows"] > 0
    nj = summary["metrics"]["next_jump"]
    assert nj["overall"]["n_scored"] > 0
    assert len(nj["by_arm_model"]) == len(QUERY_ARMS) * len(MODEL_ARMS)
    assert len(nj["by_model"]) == len(MODEL_ARMS)
    assert len(nj["by_arm"]) == len(QUERY_ARMS)
    for key in ("nll_cell_macro", "rmse_cell_macro", "mae_cell_macro",
                "coverage_90_cell_macro", "over_20mah_cell_macro",
                "over_50mah_cell_macro"):
        assert key in nj["overall"], key
    assert nj["overall"]["rmse_cell_macro"] >= 0.0
    assert summary["metrics"]["rpt_innovations"]["overall"]["n_scored"] > 0
    assert summary["metrics"]["fixed_horizons"]
    assert any(h["n_scored"] > 0
               for h in summary["metrics"]["fixed_horizons"])
    assert summary["fits"] == 0 and summary["optimizer_steps"] == 0
    assert summary["reads"]["checkpoint_files_read"] == 0
    assert summary["reads"]["raw_archives_read"] == 0
    assert summary["reads"]["c4_cells_read"] == 0
    assert receipt["consumes_go"] is False
    assert receipt["registration"] is None
    assert receipt["fits"] == 0 and receipt["c4_cells_read"] == 0
    csv_path = summary["outputs"]["predictions_csv"]
    assert os.path.isfile(csv_path)
    with open(csv_path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert tuple(reader.fieldnames) == tuple(CSV_FIELDS)
        rows = list(reader)
    assert len(rows) == summary["counts"]["n_prediction_rows"]
    assert len({r["query_id"] for r in rows}) == len(rows)
    assert {r["model_key"] for r in rows} == set(MODEL_ARMS)
    assert all(float(r["visible_capacity_min_ah"]) > THRESHOLD_AH
               for r in rows)
    qrefs = {}
    for r in rows:
        qrefs.setdefault(r["cell_id"], set()).add(
            round(float(r["qref_ah"]), 12))
        if r["model_key"] in ("time", "noEll"):
            assert all(abs(float(r["control_%02d" % i])) < 1e-12
                       and abs(float(r["control_mask_%02d" % i])) < 1e-12
                       for i in range(CONTROL_DIM))
            assert r["control_policy"] == "all_masked_time_arm"
        if r["model_key"] == "full" and r["arm"] == "raw":
            pass  # full/raw rows carry the held cycle control (asserted below)
        if r["model_key"] == "noEll":
            assert r["model_ell_state"] == "0"
            # ell is a point mass at the float32 prior mean (-5.8 exactly in
            # float32 becomes -5.8000001907348633 in float64).
            assert abs(float(r["state_ell"]) + 5.8) < 1e-6
        if r["target_available"] == "1":
            mean = float(r["pred_mean_ah"])
            var = float(r["pred_var_ah2"])
            y = float(r["target_capacity_ah"])
            nll = 0.5 * ((y - mean) ** 2 / var + math.log(var) + LOG_2PI)
            assert abs(nll - float(r["nll_per_ah"])) < 1e-9
    assert all(len(v) == 1 for v in qrefs.values())
    assert any(float(r["control_%02d" % 0]) != 0.0
               for r in rows if r["model_key"] == "full")
    emit("  synthetic pipeline: 3 cells, %d query rows (x4 arms), %d scored "
         "next-jump, %d scored RPT innovations, %d fixed-horizon groups; "
         "CSV header/state columns/receipt verified"
         % (len(rows), nj["overall"]["n_scored"],
            summary["metrics"]["rpt_innovations"]["overall"]["n_scored"],
            len(summary["metrics"]["fixed_horizons"])))


def check_subset_gate(root, emit):
    """checkpoint_subset GO gate (R2 stage A): positive paths + refusals."""
    good = _go_doc_for_self_check(root)
    # -- positive: subset ["full"] pins only the full checkpoint
    doc = copy.deepcopy(good)
    doc["checkpoint_subset"] = ["full"]
    doc["checkpoints"] = {"full": good["checkpoints"]["full"]}
    problems, norm = validate_go_document_a3(doc, expected_cells=3)
    assert not problems, problems
    assert norm["checkpoint_subset"] == ["full"]
    assert set(norm["checkpoints"]) == {"full"}
    # -- positive: alias canonicalisation in the subset and the ck keys
    doc = copy.deepcopy(good)
    doc["checkpoint_subset"] = ["a3_full"]
    doc["checkpoints"] = {"A3_Full": good["checkpoints"]["full"]}
    problems, norm = validate_go_document_a3(doc, expected_cells=3)
    assert not problems, problems
    assert norm["checkpoint_subset"] == ["full"]
    assert set(norm["checkpoints"]) == {"full"}
    # -- backward compat: absent subset -> exactly four arms (unchanged)
    problems, norm4 = validate_go_document_a3(good, expected_cells=3)
    assert not problems, problems
    assert norm4["checkpoint_subset"] is None
    assert set(norm4["checkpoints"]) == set(MODEL_ARMS)
    # -- backward compat: explicit null subset behaves as absent
    doc = copy.deepcopy(good)
    doc["checkpoint_subset"] = None
    problems, norm_null = validate_go_document_a3(doc, expected_cells=3)
    assert not problems, problems
    assert norm_null["checkpoint_subset"] is None
    assert set(norm_null["checkpoints"]) == set(MODEL_ARMS)
    # -- refusal mutations (checkpoint_subset family)
    full_ck = good["checkpoints"]["full"]

    def mut(fn):
        d = copy.deepcopy(good)
        fn(d)
        return d

    cases = [
        ("subset_empty",
         lambda g: g.__setitem__("checkpoint_subset", [])),
        ("subset_not_a_list",
         lambda g: g.__setitem__("checkpoint_subset", "full")),
        ("subset_unknown_arm",
         lambda g: g.__setitem__("checkpoint_subset", ["full", "ghost"])),
        ("subset_all_unknown",
         lambda g: g.__setitem__("checkpoint_subset", ["noSuchArm"])),
        ("subset_duplicate",
         lambda g: g.__setitem__("checkpoint_subset", ["full", "full"])),
        ("subset_checkpoint_missing",
         lambda g: (g.__setitem__("checkpoint_subset", ["full", "time"]),
                    g.__setitem__("checkpoints", {"full": full_ck}))),
        ("subset_checkpoint_extra",
         lambda g: (g.__setitem__("checkpoint_subset", ["full"]),
                    g.__setitem__("checkpoints",
                                  dict(good["checkpoints"])))),
        ("subset_checkpoints_empty",
         lambda g: (g.__setitem__("checkpoint_subset", ["full"]),
                    g.__setitem__("checkpoints", {}))),
        ("subset_arms_mismatch",
         lambda g: (g.__setitem__("checkpoint_subset", ["full"]),
                    g.__setitem__("checkpoints", {"full": full_ck}),
                    g.__setitem__("arms", ["full", "time"]))),
        ("subset_arms_four",
         lambda g: (g.__setitem__("checkpoint_subset", ["full"]),
                    g.__setitem__("checkpoints", {"full": full_ck}),
                    g.__setitem__("arms", sorted(MODEL_ARMS)))),
    ]
    for label, fn in cases:
        problems, _ = validate_go_document_a3(mut(fn), expected_cells=3)
        assert problems, "subset mutation %r was not refused" % label
    emit("  subset GO accepted (plain/alias/null/back-compat); %d subset "
         "refusal mutations rejected (empty, non-list, unknown, all-unknown, "
         "duplicate, checkpoints missing/extra/empty, arms mismatch/four)"
         % len(cases))


def check_subset_pipeline(root, emit):
    """checkpoint_subset behaviour: subset-only outputs + four-arm equality."""
    tree_root = os.path.join(root, "subset_fixture")
    tree = a2_infer._write_synth_tree(tree_root, n_cells=2)
    specs, _roots = _build_dev_specs(
        tree["cohort"], tree["data_manifest"], tree["cycling_manifest"],
        tree["rpt_manifest"], tree_root, 2)
    cells = [load_cell(spec, ReadStats()) for spec in specs]
    # four-arm reference run (deterministic synthetic models, no checkpoints)
    ref_binding = _synth_binding_a3()
    ref_binding["stats"] = ReadStats()
    ref_summary, _ = execute_inference(
        cells, _synth_models_a3(), ref_binding,
        os.path.join(tree_root, "out_ref"), deadline=None, progress=False)
    # subset run: ONLY the full arm (fresh deterministic model instance)
    subset_models = {k: m for k, m in _synth_models_a3().items()
                     if k == "full"}
    binding = _synth_binding_a3(arms=["full"])
    binding["stats"] = ReadStats()
    out_dir = os.path.join(tree_root, "out_subset")
    summary, _ = execute_inference(cells, subset_models, binding, out_dir,
                                   deadline=None, progress=False)
    assert summary["checkpoint_subset"] == ["full"]
    assert set(summary["model_arms"]) == {"full"}
    assert summary["counts"]["n_models"] == 1
    assert summary["counts"]["n_prediction_rows"] == \
        summary["counts"]["n_queries"] > 0
    nj = summary["metrics"]["next_jump"]
    assert [m["model_key"] for m in nj["by_model"]] == ["full"]
    assert len(nj["by_arm_model"]) == len(QUERY_ARMS)
    assert all(m["model_key"] == "full" for m in nj["by_arm_model"])
    # NOTE (pre-existing labelling, deliberately unchanged): the
    # rpt_innovations groups are ("rpt_model", query_arm, model_key) and the
    # summary labels k[1] (the query arm) as "model_key".  The subset
    # property is that only (query_arm, "full") groups exist -- exactly one
    # group per query arm, all from the subset model.
    assert len(summary["metrics"]["rpt_innovations"]["by_model"]) == \
        len(QUERY_ARMS)
    assert ({h["model_key"] for h in summary["metrics"]["fixed_horizons"]}
            == {"full"})
    assert set(summary["checkpoints"]) == {"full"}
    with open(os.path.join(out_dir, "predictions_c3_a3.csv"), "r",
              encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == summary["counts"]["n_prediction_rows"]
    # model_key column format unchanged; only subset arms appear
    assert {r["model_key"] for r in rows} == {"full"}
    # backward compatibility: the four-arm run's full-arm rows are reproduced
    # bit-for-bit by the subset run (deterministic synthetic model instances)
    with open(ref_summary["outputs"]["predictions_csv"], "r",
              encoding="utf-8", newline="") as fh:
        ref_rows = [r for r in csv.DictReader(fh)
                    if r["model_key"] == "full"]
    assert rows == ref_rows
    # the four-arm default is untouched
    assert ref_summary["checkpoint_subset"] is None
    assert ref_summary["counts"]["n_models"] == len(MODEL_ARMS)
    assert len(ref_summary["metrics"]["next_jump"]["by_model"]) == \
        len(MODEL_ARMS)
    emit("  subset run: model_arms=['full'], n_rows==n_queries (%d), "
         "by_model/fixed-horizons/checkpoint_info full-only; full-arm CSV "
         "rows bit-identical to the four-arm reference (%d rows); four-arm "
         "default untouched" % (len(rows), len(ref_rows)))


def check_float_discipline(_root, emit):
    model32 = build_arm_model("full", seed=5)
    assert str(next(model32.parameters()).dtype) == "torch.float32"
    model64 = model32.double()
    for p32, p64 in zip(model32.parameters(), model64.parameters()):
        assert torch.equal(p64, p32.to(torch.float64))  # exact cast
    _payload, _doc, arms = _synth_cell_and_arms()
    seq = arms["raw"]["sequence"]
    cfg = MODEL_ARMS["full"]
    walker = AsOfWalkerA3(model64, seq, 0.0, cfg)
    with torch.no_grad():
        q = arms["raw"]["queries"][3]["query_epoch"]
        st = walker.state_at(q)
    assert st["m"].dtype == FILTER_DTYPE
    assert st["P"].dtype == FILTER_DTYPE
    assert not st["m"].requires_grad and not st["P"].requires_grad
    P = st["P"][0]
    assert float(torch.max(torch.abs(P - P.transpose(0, 1)))) == 0.0
    min_eig = float(torch.linalg.eigvalsh(P).min())
    assert min_eig > 0.0, min_eig
    q_ref = model_q_ref(seq)
    mu, latent, total, _H = model64.capacity_moments(st["m"], st["P"], q_ref)
    manual = float(q_ref[0]) * math.exp(-float(st["m"][0, 0])) \
        + float(st["m"][0, 2])
    assert abs(float(mu) - manual) < 1e-12
    assert float(total) == float(latent) + float(model64.obs_variance())
    assert float(model64.obs_variance()) == \
        float(model64.obs_sigma()) ** 2  # sigma squared, never squared twice
    emit("  float32 checkpoint params -> exact float64 filter; P symmetric "
         "(0.0), PSD (min eig %.3e), mu=Qref*exp(-D)+R exact, "
         "total var == latent + sigma_y^2 exact" % min_eig)


def check_registry_gate(root, emit):
    reg = os.path.join(root, "consumed.jsonl")
    assert load_consumed_request_ids(reg) == set()  # missing file = fresh
    line = register_consumed_go(reg, "rid-1", "sha-1", "utc-1")
    rec = json.loads(line)
    assert rec == {"request_id": "rid-1", "go_sha256": "sha-1",
                   "finished_utc": "utc-1"}
    assert load_consumed_request_ids(reg) == {"rid-1"}
    try:
        register_consumed_go(reg, "rid-1", "sha-1", "utc-1")
        raise AssertionError("duplicate registration was not refused")
    except RuntimeError:
        pass
    with open(reg, "a", encoding="utf-8") as fh:
        fh.write("this line is not json\n")
    try:
        load_consumed_request_ids(reg)
        raise AssertionError("malformed registry line did not fail closed")
    except ValueError:
        pass
    emit("  registry append-once verified (exact fields), duplicate refused, "
         "malformed line fails closed (a3_train helpers, temp path only)")


def run_self_check(append_log=None, verbose=True):
    lines = []

    def emit(text=""):
        print(text)
        lines.append(text)

    emit("=" * 78)
    emit("A3 C3 INFERENCE SELF-CHECK -- %s" % _utc_now())
    emit("mode: SYNTHETIC ONLY -- 0 real payload reads, 0 checkpoint files, "
         "0 fits, 0 optimizer steps, 0 GO created or consumed")
    emit("python %s | torch %s | numpy %s | model %s"
         % (sys.version.split()[0], torch.__version__, np.__version__,
            VERSION))
    existing = {name: hash_file(_code_path(name)) for name in REQUIRED_CODE
                if os.path.isfile(_code_path(name))}
    emit("code_sha256: %s" % json.dumps(existing, sort_keys=True))
    emit("-" * 78)

    checks = [("adapter_reuse", check_adapter_reuse),
              ("query_grid_frozen", check_query_grid_frozen),
              ("walker_equivalence", check_walker_equivalence),
              ("no_future_leakage", check_no_future_leakage),
              ("go_mutations", check_go_mutations),
              ("binding_refusals", check_binding_refusals),
              ("synthetic_pipeline", check_synthetic_pipeline),
              ("subset_gate", check_subset_gate),
              ("subset_pipeline", check_subset_pipeline),
              ("float_discipline", check_float_discipline),
              ("registry_gate", check_registry_gate)]
    passed = failed = 0
    audit = _OpenAudit()
    tmp_root = tempfile.mkdtemp(prefix="a3_infer_selfcheck_")
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
        real_root = os.environ.get("A3_INFER_ROOT", "/home/yndx/zxk/rul")
        forbidden = [os.path.join(real_root, "data"),
                     os.path.join(real_root, "reports"),
                     os.path.join(real_root, "automation"),
                     os.path.join(real_root, "experiments",
                                  "multirate_state_A3_rate_20261024",
                                  "run1_fits")]
        bad = audit.under(forbidden)
        pt_opens = [p for p in audit.paths
                    if p.lower().endswith((".pt", ".pth", ".ckpt"))]
        npz_opens = [p for p in audit.paths
                     if p.lower().endswith(".npz")]
        if bad:
            failed += 1
            emit("[FAIL] %-20s opened %d forbidden path(s): %r"
                 % ("no_real_payload", len(bad), bad[:3]))
        else:
            passed += 1
            emit("[PASS] %-20s %d paths opened; 0 under real data/reports/"
                 "automation/run1_fits (all under %s)"
                 % ("no_real_payload", len(audit.paths),
                    os.path.basename(tmp_root)))
        if pt_opens or npz_opens:
            failed += 1
            emit("[FAIL] %-20s opened checkpoint/npz file(s): %r"
                 % ("no_checkpoint_file", (pt_opens + npz_opens)[:3]))
        else:
            passed += 1
            emit("[PASS] %-20s 0 .pt/.pth/.ckpt and 0 .npz files opened"
                 % "no_checkpoint_file")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    emit("-" * 78)
    emit("SUMMARY: %d passed, %d failed, %d total"
         % (passed, failed, passed + failed))
    emit("REAL PAYLOAD READS: 0. CHECKPOINT FILES READ: 0. FITS: 0. "
         "OPTIMIZER STEPS: 0.")
    emit("NO GO CREATED. NO GO CONSUMED. NO RECEIPT OUTSIDE THE TEMP FIXTURE.")
    emit("RESULT: %s" % ("OK (%d passed / %d failed)" % (passed, failed)
                         if failed == 0 else "FAILED (%d failed)" % failed))
    if append_log:
        block = ("\n===== a3_infer self-check %s =====\n" % _utc_now()) + \
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
        description="A3 C3 development inference: synthetic self-check by "
                    "default; real inference only under an APPROVED, "
                    "unconsumed GO.")
    parser.add_argument("--self-check", action="store_true",
                        help="run synthetic fixtures (default behaviour)")
    parser.add_argument("--go", default=None,
                        help="path to an APPROVED A3 C3 inference GO json")
    parser.add_argument("--threads", type=int,
                        default=min(8, os.cpu_count() or 8),
                        help="torch CPU threads for real inference")
    parser.add_argument("--append-log", default=None,
                        help="append self-check output to this log "
                             "(append-only)")
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
    print("A3 C3 inference -- synthetic self-check (no GO supplied)")
    return run_self_check(append_log=args.append_log)


if __name__ == "__main__":
    sys.exit(main())
