#!/usr/bin/env python3
"""A3-T C3 development inference (four arms, or a GO-pinned checkpoint subset;
as-of walker with Student-t innovations) -- synthetic self-check only by
default.

This entry point mirrors a3_infer.py's contract exactly (GO gate, streaming
as-of walker under no_grad, RSS cap, frozen a2_infer query contract, the
optional checkpoint_subset, receipt + consumed-GO registry); the model is the
A3-T Student-t innovation model (a3t_model.A3TStateModel), so:

* every RPT measurement update on the walker path is
  a3t_model.A3TStateModel.correct_rpt_t (the moment-matched robust update:
  w = (nu+1)/(nu+u^2/S), R_eff = sigma_y^2 / w, Joseph form, arm
  rate_update masking) -- the SAME method object the A3-T training replay
  calls (imported, not rewritten);
* the RPT innovation NLL along the filter path is nll_rpt_t (exact Student-t
  log density at the learned nu);
* prediction outputs keep every a3_infer column unchanged (nll_per_ah and
  covered_50/90/95 stay GAUSSIAN-form for panel comparability) and ADD the
  t columns: t_nll_per_ah / gauss_nll_per_ah side by side and
  t_covered_90 / t_covered_95 (t_{nu} quantiles at the learned nu -- the
  t tails are the entire point of A3-T's risk-scheduling repair);
* summary.json keeps the a3_infer structure (next_jump / rpt_innovations /
  fixed_horizons, overall / by_arm / by_model / by_arm_model) and adds, per
  group, t_nll / gauss_nll / cov90_t / cov90_gauss (cell-macro and pooled).

Real inference requires an APPROVED, unconsumed GO pinning the A3-T
checkpoint set (by default under a3t/runs/<run>/model_state_dict_<arm>.pt,
exactly the four arms or exactly the checkpoint_subset), the four source
manifests, the code-hash closure (11 files: a3t_infer/a3t_model + a3_model/
a3_train + 7 a2 files), a fresh output_dir + receipt_path, no_grad=true, an
RSS cap and a request_id absent from the consumed-GO registry.  Checkpoints
are loaded strict into A3TStateModel (an A3 Gaussian checkpoint is refused:
it lacks nu_raw / the multiplier parameters).  After full success the
request_id is registered (a3_train.register_consumed_go discipline).
Default mode is --self-check: synthetic cells only, 0 real payload reads, 0
real checkpoint files, 0 fits, 0 optimizer steps, 0 GO created or consumed.

Provenance: the GO validator, checkpoint loader, execute/_row_for_query/
_write_receipt/run_go and the self-check harness follow a3_infer.py's proven
shapes (copied and adapted, as a3_infer itself did from a2_infer.py); the
frozen query contract, manifest binding, role adapters, read auditing and
metric helpers are imported UNCHANGED from a2_infer.py.
"""
from __future__ import annotations

import argparse
import copy
import csv
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
_A3_DIR = os.path.dirname(HERE)
_A2_DIR = os.path.join(os.path.dirname(_A3_DIR), "multirate_state_A2_20261022")
if not os.path.isdir(_A3_DIR):
    raise ImportError("A3 code directory not found at %s" % _A3_DIR)
if not os.path.isdir(_A2_DIR):
    raise ImportError("A2 code directory not found at %s" % _A2_DIR)
for _p in (HERE, _A3_DIR, _A2_DIR):
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
    _under,
    _utc,
    _utc_now,
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
)
from a3t_model import (
    A3T_VERSION,
    NU_FLOOR,
    _run_events_a3t,
    build_arm_model_t,
)
from a3_train import (
    DEFAULT_CONSUMED_REGISTRY,
    load_consumed_request_ids,
    register_consumed_go,
)

# ---------------------------------------------------------------------------
# Frozen contract (A3-T values; the query contract objects ARE a2_infer's)
# ---------------------------------------------------------------------------
SCHEMA = "A3T_C3_INFERENCE_V1"
RECEIPT_SCHEMA = "A3T_C3_INFERENCE_RECEIPT_V1"
OWNER_THREAD_ID = "01a15c3a-1a06-7d61-8517-27b70b246183"
DATA_SCOPE = "C3_source63_development_only_no_C4_no_raw"
GO_STATUS = "APPROVED"
DEFAULT_DEV_CELLS = 63
DEFAULT_MAX_RSS_GB = 2.0
FILTER_DTYPE = torch.float64
OVER_ERROR_AH = (0.020, 0.050)
# Real import closure of a3t_infer.py: a3t files in the a3t/ directory, the
# reused A3 files in the parent A3 directory, the a2_* files in the A2
# directory (exactly the reuse discipline of a3t_model.py / a3t_train.py).
REQUIRED_CODE = (
    "a3t_infer.py", "a3t_model.py",
    "a3_model.py", "a3_train.py",
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
    "full": "full", "a3_full": "full", "a3t_full": "full",
    "norateupdate": "noRateUpdate", "no_rate_update": "noRateUpdate",
    "a3_no_rate_update": "noRateUpdate", "a3t_no_rate_update": "noRateUpdate",
    "noru": "noRateUpdate",
    "time": "time", "a3_time": "time", "a3t_time": "time",
    "time_only": "time",
    "noell": "noEll", "no_ell": "noEll", "a3_no_ell": "noEll",
    "a3t_no_ell": "noEll",
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
# Student-t tails: CDF (regularised incomplete beta, continued fraction),
# two-sided quantiles (cached per nu) and the t NLL in pure float math
# (math.lgamma; this build's torch.lgamma is only ~3e-6 accurate).
# ---------------------------------------------------------------------------
def _betacf(a, b, x):
    """Continued fraction for the regularised incomplete beta (NR 6.4)."""
    max_it, eps, fpmin = 300, 3e-15, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, max_it + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < eps:
            break
    return h


def _betainc_reg(a, b, x):
    """Regularised incomplete beta I_x(a, b) for 0 <= x <= 1."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_beta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    if x < (a + 1.0) / (a + b + 2.0):
        front = math.exp(a * math.log(x) + b * math.log1p(-x) - ln_beta) / a
        return front * _betacf(a, b, x)
    front = math.exp(b * math.log1p(-x) + a * math.log(x) - ln_beta) / b
    return 1.0 - front * _betacf(b, a, 1.0 - x)


def _t_cdf(x, df):
    """CDF of the standard Student-t with df > 0 degrees of freedom."""
    if x == 0.0:
        return 0.5
    tail = 0.5 * _betainc_reg(0.5 * df, 0.5, df / (df + x * x))
    return 1.0 - tail if x > 0.0 else tail


def _t_ppf(q, df):
    """Inverse t CDF by bracketing + bisection (monotone, exact to ~1e-12)."""
    if not 0.0 < q < 1.0:
        raise ValueError("t quantile level must be in (0, 1), got %r" % q)
    lo, hi = -1.0, 1.0
    while _t_cdf(hi, df) < q:
        hi *= 2.0
        if hi > 1e12:
            raise ValueError("t quantile bracket failed (df=%r q=%r)"
                             % (df, q))
    while _t_cdf(lo, df) > q:
        lo *= 2.0
        if lo < -1e12:
            raise ValueError("t quantile bracket failed (df=%r q=%r)"
                             % (df, q))
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _t_cdf(mid, df) < q:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-13 * max(1.0, abs(hi)):
            break
    return 0.5 * (lo + hi)


_T_Z_CACHE = {}


def _norm_ppf(q):
    """Standard normal quantile by bisection on the erf CDF (machine-exact;
    used for df >= 1e6 where t is the normal to < 1e-9 and the incomplete
    beta route loses precision)."""
    lo, hi = -10.0, 10.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        cdf = 0.5 * (1.0 + math.erf(mid / math.sqrt(2.0)))
        if cdf < q:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-14:
            break
    return 0.5 * (lo + hi)


def _t_z(df, level):
    """Two-sided t quantile z with P(|T_df| <= z) = level (e.g. 0.90)."""
    df = float(df)
    if df >= 1e6:
        return _norm_ppf(0.5 + 0.5 * float(level))
    key = (round(df, 12), float(level))
    if key not in _T_Z_CACHE:
        _T_Z_CACHE[key] = _t_ppf(0.5 + 0.5 * float(level), df)
    return _T_Z_CACHE[key]


def _t_nll(y, mean, var, df):
    """Student-t NLL of y under t(mean, scale^2 = var, df); var in Ah^2."""
    z2 = (float(y) - float(mean)) ** 2 / float(var)
    df = float(df)
    return (-math.lgamma((df + 1.0) * 0.5) + math.lgamma(df * 0.5)
            + 0.5 * math.log(df * math.pi * float(var))
            + 0.5 * (df + 1.0) * math.log1p(z2 / df))


# ---------------------------------------------------------------------------
# GO document (pure checks) -- structure follows a3_infer.validate_go_document
# ---------------------------------------------------------------------------
def _checkpoint_subset_a3t(go, problems):
    """Optional GO field checkpoint_subset (a3_infer's subset contract)."""
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


def _normalise_checkpoints_a3t(go, problems, expected_arms=None):
    """Normalise the GO checkpoints node against the resolved arm set."""
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


def validate_go_document_a3t(go, expected_cells=DEFAULT_DEV_CELLS):
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
        problems.append("GO device must be 'cpu' for the A3-T CPU model, "
                        "got %r" % (go.get("device"),))
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
    checkpoint_subset = _checkpoint_subset_a3t(go, problems)
    if go.get("arms") is not None:
        arms = go.get("arms")
        if checkpoint_subset is not None:
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
            problems.append("GO must pin %s (path + sha256)" % label)
            refs[label] = {"path": None, "sha256": None, "go_key": used,
                           "go_pinned": False}
            continue
        _check_abs_ref(path, sha, label, problems)
        refs[label] = {"path": path, "sha256": sha, "go_key": used,
                       "go_pinned": True}

    checkpoints = _normalise_checkpoints_a3t(go, problems,
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
            problems.append("GO expires_utc is not a timestamp: %r"
                            % (expires,))
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
# Code hashes / checkpoint loading (A3-T models; float64 filter copy)
# ---------------------------------------------------------------------------
def _code_path(name):
    if name.startswith("a3t_"):
        return os.path.join(HERE, name)
    if name.startswith("a3_"):
        return os.path.join(_A3_DIR, name)
    return os.path.join(_A2_DIR, name)


def _load_code_hashes_a3t(norm, stats):
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


def _load_arm_model_a3t(key, spec, stats):
    """Hash-verify one A3-T arm checkpoint and build its float64 filter model.

    The checkpoint state_dict is float32 (training dtype); the filter runs in
    float64.  strict=True: an A3 (Gaussian) checkpoint lacks nu_raw /
    q_ell_mult_raw / q_R_mult_raw and is refused here.
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
    model = build_arm_model_t(key, seed=42)
    try:
        model.load_state_dict(obj, strict=True)
    except Exception as exc:  # noqa: BLE001
        raise InferenceError("checkpoint %s does not match A3TStateModel "
                             "(an A3 Gaussian checkpoint is refused): %s"
                             % (key, exc))
    model.eval()
    for name, param in model.named_parameters():
        if not torch.all(torch.isfinite(param)):
            raise InferenceError("checkpoint %s has non-finite parameter %s"
                                 % (key, name))
    nu = float(model.nu_df())
    if not (NU_FLOOR < nu < 1e6) or not math.isfinite(nu):
        raise InferenceError("checkpoint %s has a degenerate nu=%r (must be "
                             "> %.1f and finite)" % (key, nu, NU_FLOOR))
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
        "nu": nu,
        "nu_floor": float(f64.nu_floor),
        "sigma_ell_base": float(f64.sigma_ell_base()),
        "sigma_R_base": float(f64.sigma_R_base()),
        "sigma_ell_mult": float(f64.sigma_ell_mult()),
        "sigma_R_mult": float(f64.sigma_R_mult()),
        "t_z90": _t_z(nu, 0.90),
        "t_z95": _t_z(nu, 0.95),
        "control_mean_is_identity": bool(torch.equal(
            f64.control_mean, torch.zeros_like(f64.control_mean))),
        "control_scale_is_identity": bool(torch.equal(
            f64.control_scale, torch.ones_like(f64.control_scale))),
    }
    return f64, info


def validate_go_bindings_a3t(norm, stats=None, registry_path=None):
    """All file/hash/role/output checks before any write.  Returns binding."""
    stats = stats or ReadStats()
    problems = []
    if not norm.get("output_dir"):
        return None, ["GO output_dir missing"]
    if not norm.get("receipt_path"):
        return None, ["GO receipt_path missing"]
    binding = dict(norm)
    try:
        code_hashes = _load_code_hashes_a3t(norm, stats)
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

    out_dir = _check_fresh_dir(norm["output_dir"], "output_dir", problems)
    receipt = _check_fresh_file(norm["receipt_path"], "receipt_path", problems)
    if out_dir:
        binding["output_dir"] = out_dir
    if receipt:
        binding["receipt_path"] = receipt
    if out_dir and receipt and \
            os.path.realpath(out_dir) == os.path.realpath(receipt):
        problems.append("output_dir and receipt_path must differ")
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
    arm_keys = list(norm.get("checkpoint_subset") or sorted(MODEL_ARMS))
    for key in arm_keys:
        spec = (norm.get("checkpoints") or {}).get(key)
        if not isinstance(spec, dict):
            problems.append("checkpoint %s missing from the GO" % key)
            continue
        try:
            model, info = _load_arm_model_a3t(key, spec, stats)
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
# Incremental A3-T as-of walker (a3_model segment engine + a3t_model's t
# update; one cell at a time)
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


class AsOfWalkerA3T(object):
    """Incremental A3-T as-of filter for one (cell, query arm, model arm).

    Semantics -- exactly the A3-T training replay (a3t_model._run_events_a3t):
      * events are buffered since the last RPT position; hitting an RPT event
        flushes the buffered segment with _segment_advance (a3_model) under
        the frozen linearization (a, b) carried from the last SCORED RPT
        update, then applies the moment-matched t measurement update
        model.correct_rpt_t with the arm's rate_update flag and refreshes
        (a, b) from the post-update mean -- the same method object training
        calls, never a rewrite;
      * the scored-RPT innovation NLL is model.nll_rpt_t (t) alongside the
        Gaussian form model.nll_rpt (inherited) for the a3-comparable column;
      * a query cut mid-segment flushes the partial buffer with the SAME
        carried (a, b): an exact affine-semigroup composition, so query
        timing never changes the filter;
      * delay7d keeps the base at q - 7d and applies only completed cycles in
        (q - 7d, q] to the snapshot; RPT events in that window are ghosts;
      * the tail interval (last event, q] propagates with masked control as a
        pseudo-event under the carried (a, b).
    All filter tensors are float64.
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
        # scored only: (epoch, innovation_ah, S_ah2, t_nll, gauss_nll)
        self.rpt_trace = []

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
        """Scored-RPT t + Gaussian innovation NLLs, then the t update."""
        self.n_rpt += 1
        if not bool(event.get("score", False)):
            return
        y = torch.tensor([float(event["capacity_ah"])], dtype=FILTER_DTYPE)
        mu_cap, _latent, S, _H = self.model.capacity_moments(
            self.base_m, self.base_P, self.q_ref)
        nu = y - mu_cap
        t_nll = self.model.nll_rpt_t(self.base_m, self.base_P,
                                     self.q_ref, y)
        g_nll = self.model.nll_rpt(self.base_m, self.base_P,
                                   self.q_ref, y)
        self.rpt_trace.append((float(event["source_epoch"]), float(nu),
                               float(S), float(t_nll), float(g_nll)))
        self.base_m, self.base_P, _, _ = self.model.correct_rpt_t(
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


def reference_asof_state_a3t(model, sequence, query_epoch, cfg, lag_seconds):
    """Authoritative non-incremental as-of filter (t update path): re-filters
    from the anchor for THIS query only.  Used by --self-check to validate
    AsOfWalkerA3T elementwise."""
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
                m, P, _, _ = model.correct_rpt_t(
                    m, P, model_q_ref(sequence), y,
                    rate_update=bool(cfg["rate_update"]))
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


def engine_full_replay_a3t(model, sequence, cfg):
    """a3t_model._run_events_a3t over the cell's full event sequence (the
    authoritative A3-T training engine, want_trace).  Returns (final state,
    t-NLL trace)."""
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
    m, P, _nll, _n, _frozen, trace, _gauss = _run_events_a3t(
        model, kind, dt, ctl, msk, y, score, q_ref, m0, P0, cfg,
        collect_nll=True, want_trace=True)
    return m, P, trace


# ---------------------------------------------------------------------------
# Prediction / output (a3_infer columns unchanged + the t columns)
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


def _csv_fields_a3t():
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
        "model_nu", "model_t_z90", "model_t_z95",
        "n_cycles_used", "n_rpt_used", "n_late_arrival_excluded",
        "held_control_epoch", "control_policy",
    ]
    controls = ["control_%02d" % i for i in range(CONTROL_DIM)]
    masks = ["control_mask_%02d" % i for i in range(CONTROL_DIM)]
    target = [
        "gap_weeks", "next_source_rpt_index", "next_source_stop_epoch",
        "target_available", "target_capacity_ah",
        "pred_mean_ah", "pred_latent_var_ah2", "pred_var_ah2", "pred_sd_ah",
        "innovation_ah", "abs_error_ah", "sq_error_ah2",
        "t_nll_per_ah", "gauss_nll_per_ah", "nll_per_ah",
        "covered_50", "covered_90", "covered_95",
        "t_covered_50", "t_covered_90", "t_covered_95",
    ]
    horizon = []
    for h in HORIZONS_WEEKS:
        tag = ("h%g" % h).replace(".", "p")
        horizon += [tag + "_mean_ah", tag + "_var_ah2", tag + "_sd_ah",
                    tag + "_target_epoch", tag + "_target_capacity_ah",
                    tag + "_nll_per_ah", tag + "_t_nll_per_ah",
                    tag + "_abs_error_ah",
                    tag + "_covered_95", tag + "_t_covered_95"]
    return core + controls + masks + target + horizon


CSV_FIELDS = _csv_fields_a3t()


class _CellAccumulatorA3T(_CellAccumulator):
    """a2_infer._CellAccumulator extended with the t-NLL / t-coverage sums
    and the over_20mAh / over_50mAh exceedance counters."""

    def add(self, cell_id, nll=None, abs_err=None, sq_err=None,
            cov50=None, cov90=None, cov95=None, t_nll=None, cov50_t=None,
            cov90_t=None, cov95_t=None, over20=None, over50=None,
            gauss_nll=None):
        # gauss_nll is accepted for call-site symmetry (it always equals the
        # nll payload value and is reported through the block() alias).
        rec = self.cells.setdefault(cell_id, {
            "n": 0, "sum_nll": 0.0, "sum_abs": 0.0, "sum_sq": 0.0,
            "n_cov50": 0, "n_cov90": 0, "n_cov95": 0,
            "sum_t_nll": 0.0, "n_cov50_t": 0, "n_cov90_t": 0,
            "n_cov95_t": 0, "n_over20": 0, "n_over50": 0})
        rec["n"] += 1
        if nll is not None:
            rec["sum_nll"] += float(nll)
        if t_nll is not None:
            rec["sum_t_nll"] += float(t_nll)
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
        if cov50_t is not None:
            rec["n_cov50_t"] += int(cov50_t)
        if cov90_t is not None:
            rec["n_cov90_t"] += int(cov90_t)
        if cov95_t is not None:
            rec["n_cov95_t"] += int(cov95_t)
        if over20 is not None:
            rec["n_over20"] += int(over20)
        if over50 is not None:
            rec["n_over50"] += int(over50)

    def block(self):
        out = super().block()
        cells = [c for c, rec in self.cells.items() if rec["n"] > 0]
        if cells:
            n = sum(self.cells[c]["n"] for c in cells)
            t_nll = [self.cells[c]["sum_t_nll"] / self.cells[c]["n"]
                     for c in cells]
            cov50t = [self.cells[c]["n_cov50_t"] / self.cells[c]["n"]
                      for c in cells]
            cov90t = [self.cells[c]["n_cov90_t"] / self.cells[c]["n"]
                      for c in cells]
            cov95t = [self.cells[c]["n_cov95_t"] / self.cells[c]["n"]
                      for c in cells]
            out.update({
                "t_nll_cell_macro": float(np.mean(t_nll)),
                "t_nll_pooled": float(
                    sum(self.cells[c]["sum_t_nll"] for c in cells) / n),
                "gauss_nll_cell_macro": out["nll_cell_macro"],
                "gauss_nll_pooled": out["nll_pooled"],
                "coverage_50_t_cell_macro": float(np.mean(cov50t)),
                "coverage_90_t_cell_macro": float(np.mean(cov90t)),
                "coverage_95_t_cell_macro": float(np.mean(cov95t)),
                "coverage_90_t_pooled": float(
                    sum(self.cells[c]["n_cov90_t"] for c in cells) / n),
                "coverage_95_t_pooled": float(
                    sum(self.cells[c]["n_cov95_t"] for c in cells) / n),
                "cov90_t_cell_macro": float(np.mean(cov90t)),
                "cov90_t_pooled": float(
                    sum(self.cells[c]["n_cov90_t"] for c in cells) / n),
                "cov90_gauss_cell_macro": out["coverage_90_cell_macro"],
                "cov90_gauss_pooled": float(
                    sum(self.cells[c]["n_cov90"] for c in cells) / n),
                "cov95_gauss_cell_macro": out["coverage_95_cell_macro"],
                "over_20mah_cell_macro": float(np.mean(
                    [self.cells[c]["n_over20"] / self.cells[c]["n"]
                     for c in cells])),
                "over_50mah_cell_macro": float(np.mean(
                    [self.cells[c]["n_over50"] / self.cells[c]["n"]
                     for c in cells])),
                "over_20mah_pooled": float(
                    sum(self.cells[c]["n_over20"] for c in cells) / n),
                "over_50mah_pooled": float(
                    sum(self.cells[c]["n_over50"] for c in cells) / n),
            })
        return out


class _MetricBookA3T(_MetricBook):
    """_MetricBook over the extended accumulator."""

    def __init__(self):
        super().__init__()
        self._acc = _CellAccumulatorA3T

    def add(self, key, cell_id, **kwargs):
        self.groups.setdefault(key, _CellAccumulatorA3T()) \
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


def _row_for_query_t(cell, arm, query, model_key, model, state, q_ref,
                     sequence):
    cfg = MODEL_ARMS[model_key]
    ctl_np, msk_np, policy, held_epoch = _control_for_output(state, cfg)
    ctl = torch.as_tensor(ctl_np.reshape(1, -1), dtype=state["m"].dtype,
                          device=state["m"].device)
    msk = torch.as_tensor(msk_np.reshape(1, -1), dtype=state["m"].dtype,
                          device=state["m"].device)
    q = float(query["query_epoch"])
    nu = float(model.nu_df())
    z50t = _t_z(nu, 0.50)
    z90t = _t_z(nu, 0.90)
    z95t = _t_z(nu, 0.95)
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
        "model_nu": nu,
        "model_t_z90": z90t,
        "model_t_z95": z95t,
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
            row[tag + "_t_nll_per_ah"] = ""
            row[tag + "_abs_error_ah"] = ""
            row[tag + "_covered_95"] = ""
            row[tag + "_t_covered_95"] = ""
        else:
            y = float(target["capacityAh"])
            row[tag + "_nll_per_ah"] = _gaussian_nll(
                y, pred["mean_ah"], pred["var_ah2"])
            row[tag + "_t_nll_per_ah"] = _t_nll(
                y, pred["mean_ah"], pred["var_ah2"], nu)
            row[tag + "_abs_error_ah"] = abs(y - pred["mean_ah"])
            row[tag + "_covered_95"] = _coverage(y, pred["mean_ah"],
                                                 pred["var_ah2"],
                                                 1.959963984540054)
            row[tag + "_t_covered_95"] = int(
                abs(y - pred["mean_ah"]) <= z95t
                * math.sqrt(max(pred["var_ah2"], 1e-30)))

    gap = query["gap_weeks"]
    row["gap_weeks"] = _blank(gap)
    row["next_source_rpt_index"] = _blank(query["next_source_rpt_index"])
    row["next_source_stop_epoch"] = _blank(query["next_source_stop_epoch"])
    row["target_capacity_ah"] = _blank(query["target_capacity_ah"])
    row["target_available"] = int(gap is not None)
    if gap is None:
        for key in ("pred_mean_ah", "pred_latent_var_ah2", "pred_var_ah2",
                    "pred_sd_ah", "innovation_ah", "abs_error_ah",
                    "sq_error_ah2", "t_nll_per_ah", "gauss_nll_per_ah",
                    "nll_per_ah", "covered_50", "covered_90", "covered_95",
                    "t_covered_50", "t_covered_90", "t_covered_95"):
            row[key] = ""
    else:
        pred = _advance_horizon(model, state["m"], state["P"], gap, ctl, msk,
                                q_ref, cfg)
        y = float(query["target_capacity_ah"])
        z = y - pred["mean_ah"]
        sd = math.sqrt(max(pred["var_ah2"], 1e-30))
        row["pred_mean_ah"] = pred["mean_ah"]
        row["pred_latent_var_ah2"] = pred["latent_var_ah2"]
        row["pred_var_ah2"] = pred["var_ah2"]
        row["pred_sd_ah"] = pred["sd_ah"]
        row["innovation_ah"] = z
        row["abs_error_ah"] = abs(z)
        row["sq_error_ah2"] = z * z
        row["t_nll_per_ah"] = _t_nll(y, pred["mean_ah"], pred["var_ah2"], nu)
        row["gauss_nll_per_ah"] = _gaussian_nll(
            y, pred["mean_ah"], pred["var_ah2"])
        row["nll_per_ah"] = row["gauss_nll_per_ah"]
        row["covered_50"] = _coverage(y, pred["mean_ah"], pred["var_ah2"],
                                      0.6744897501960817)
        row["covered_90"] = _coverage(y, pred["mean_ah"], pred["var_ah2"],
                                      1.6448536269514722)
        row["covered_95"] = _coverage(y, pred["mean_ah"], pred["var_ah2"],
                                      1.959963984540054)
        row["t_covered_50"] = int(abs(z) <= z50t * sd)
        row["t_covered_90"] = int(abs(z) <= z90t * sd)
        row["t_covered_95"] = int(abs(z) <= z95t * sd)
    return row


def _update_metrics(book, row):
    if row["target_available"] and row["t_nll_per_ah"] != "":
        payload = dict(
            nll=row["gauss_nll_per_ah"], t_nll=row["t_nll_per_ah"],
            abs_err=row["abs_error_ah"], sq_err=row["sq_error_ah2"],
            cov50=row["covered_50"], cov90=row["covered_90"],
            cov95=row["covered_95"],
            cov50_t=row["t_covered_50"], cov90_t=row["t_covered_90"],
            cov95_t=row["t_covered_95"],
            over20=int(row["abs_error_ah"] > OVER_ERROR_AH[0]),
            over50=int(row["abs_error_ah"] > OVER_ERROR_AH[1]))
        arm, model = row["arm"], row["model_key"]
        book.add(("arm_model", arm, model), row["cell_id"], **payload)
        book.add(("arm", arm), row["cell_id"], **payload)
        book.add(("model", model), row["cell_id"], **payload)
        book.add(("overall", "all"), row["cell_id"], **payload)
    for h in HORIZONS_WEEKS:
        tag = ("h%g" % h).replace(".", "p")
        if row[tag + "_t_nll_per_ah"] != "":
            book.add(("horizon", row["arm"], row["model_key"], h),
                     row["cell_id"],
                     nll=row[tag + "_nll_per_ah"],
                     t_nll=row[tag + "_t_nll_per_ah"],
                     abs_err=row[tag + "_abs_error_ah"],
                     sq_err=float(row[tag + "_abs_error_ah"]) ** 2,
                     cov95=row[tag + "_covered_95"],
                     cov95_t=row[tag + "_t_covered_95"])


def _update_rpt_metrics(book, arm, model_key, cell_id, rpt_trace):
    """RPT innovation scoring along the t filter path: the t NLL is the
    model's own innovation log score; the Gaussian form is reported alongside
    (nll / gauss_nll) for a3_infer compatibility; cov90 stays the Gaussian
    form exactly as in a3_infer (the t quantiles live in the prediction
    columns and the next_jump blocks)."""
    for _epoch, innovation, var, t_nll, g_nll in rpt_trace:
        sd = math.sqrt(max(float(var), 1e-30))
        payload = dict(
            nll=float(g_nll), gauss_nll=float(g_nll), t_nll=float(t_nll),
            abs_err=abs(float(innovation)),
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
    "nll": "GAUSSIAN NLL of the scored target under N(mean, total variance) "
           "in Ah^2 (same semantic as a3_infer; kept for panel "
           "comparability), cell-macro = mean over cells",
    "t_nll": "Student-t NLL at the checkpoint's learned nu with the same "
             "predicted mean/total variance (t_nll_cell_macro / t_nll_pooled)",
    "gauss_nll": "alias of nll (Gaussian), reported next to t_nll",
    "rmse": "sqrt(mean_cell MSE) with equal cell weight",
    "mae": "mean_cell mean absolute error",
    "cov90_t": "fraction with |y - mean| <= t_{nu}(0.90) * sd (t quantile "
               "at the learned nu), cell-macro",
    "cov90_gauss": "fraction with |y - mean| <= 1.6448536269514722 * sd "
                   "(Gaussian), cell-macro",
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
    csv_path = os.path.join(out_dir, "predictions_c3_a3t.csv")
    tmp_csv = csv_path + ".tmp"
    metric_book = _MetricBookA3T()
    arm_query_counts = {arm: 0 for arm in QUERY_ARMS}
    skipped = {"cells_fewer_than_4_rpt": 0, "cells_no_query": 0}
    skipped.update({arm + "_" + key: 0 for arm in QUERY_ARMS
                    for key in ("warmup", "visible_lt_min", "duplicate_anchor",
                                "visible_threshold")})
    cell_records = []
    n_rows = 0
    n_query_models = 0
    n_rpt_innovations = 0
    model_keys = sorted(models)
    checkpoint_subset = binding.get("checkpoint_subset")
    qref_by_cell = {}
    per_cell_queries = {}

    with torch.no_grad():   # whole body: the 30 GB autograd lesson
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
                                                    rpts_arm,
                                                    cutoff_epoch=None)
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
                        walkers[model_key] = AsOfWalkerA3T(
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
                                row = _row_for_query_t(
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
        "a3t_version": A3T_VERSION,
        "a3_version": VERSION,
        "go": binding.get("go_info", {}),
        "code_sha256": binding.get("code_sha256", {}),
        "sources": binding.get("sources", {}),
        "checkpoints": binding.get("checkpoint_info", {}),
        "nu_by_model": {k: float(models[k].nu_df()) for k in model_keys},
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
        "nu_by_model": summary.get("nu_by_model", {}) if summary else {},
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
    problems, norm = validate_go_document_a3t(go)
    if problems:
        print("REFUSED -- GO validation failed (%d problem(s)):" % len(problems))
        for problem in problems:
            print("  - %s" % problem)
        print("NO FILE WRITTEN. NO DATA READ. NO CHECKPOINT READ. "
              "NO GO CONSUMED.")
        return 3
    binding, problems = validate_go_bindings_a3t(norm, stats,
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
        print("GO ACCEPTED (A3-T C3 inference only): %s"
              % binding["go_info"]["path"])
        print("  go_sha256=%s" % go_sha)
        print("  cells=%d model_arms=%s device=cpu no_grad=True "
              "max_runtime=%ss max_rss_gb=%.2f"
              % (len(binding["dev_specs"]),
                 binding.get("model_arms") or sorted(MODEL_ARMS),
                 norm["max_runtime_seconds"], rss_cap_gb))
        for key in sorted(binding["models"]):
            info = binding["checkpoint_info"][key]
            print("  arm=%-12s nu=%.4f sigma_ell_mult=%.4f "
                  "sigma_R_mult=%.4f (checkpoint %s)"
                  % (key, info["nu"], info["sigma_ell_mult"],
                     info["sigma_R_mult"], info["sha256"][:16]))
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
        print("A3-T C3 INFERENCE COMPLETE: cells=%d queries=%d rows=%d"
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
        print("A3-T C3 INFERENCE FAILED: %s" % error)
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
_T_TABLE = {  # two-sided quantiles from the standard t table (6 d.p.)
    5.0: {0.90: 2.015048, 0.95: 2.570582},
    10.0: {0.90: 1.812461, 0.95: 2.228139},
    30.0: {0.90: 1.697261, 0.95: 2.042272},
}
_NORM_Z = {0.90: 1.6448536269514722, 0.95: 1.959963984540054,
           0.50: 0.6744897501960817}


def _synth_models_a3t(seed=42):
    """In-memory A3-T arm models (float64 filter copies); NO checkpoint."""
    models = {}
    for key in sorted(MODEL_ARMS):
        model = build_arm_model_t(key, seed=seed)
        model.eval()
        models[key] = model.double()
    return models


def _synth_binding_a3t(code_hashes=None, arms=None):
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
        "request_id": "a3t-c3infer-selfcheck-0001",
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
    cid = "G1C3"
    payload, doc = a2_infer._synth_payload(cid, 1_650_000_000.0, n_rpt=4)
    direct_ctl, direct_msk = a2_prep.cycle_control(doc["cycles"][0])
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
    assert build_queries is a2_infer.build_queries
    assert _b2_arm_records is a2_infer._b2_arm_records
    assert _validate_query_contract is a2_infer._validate_query_contract
    emit("  a2_prep role gate intact; adapters project the role only; "
         "query-grid code objects are a2_infer's (identity)")


def check_walker_method_reuse(_root, emit):
    """The walker's measurement update and innovation NLL are the a3t_model
    METHOD OBJECTS (the same code the training replay calls), not copies."""
    model = build_arm_model_t("full", seed=7).double().eval()
    assert AsOfWalkerA3T._apply_rpt is not None
    src = inspect_getsource(AsOfWalkerA3T._apply_rpt)
    assert "self.model.correct_rpt_t(" in src
    assert "self.model.nll_rpt_t(" in src
    assert "self.model.nll_rpt(" in src
    # and correct_rpt_t on the instance is the A3TStateModel method
    assert model.correct_rpt_t.__func__ is type(model).correct_rpt_t
    emit("  walker._apply_rpt calls model.correct_rpt_t / nll_rpt_t / "
         "nll_rpt (a3t_model methods, verified by source inspection)")


def inspect_getsource(fn):
    import inspect
    return inspect.getsource(fn)


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
    emit("  raw=10 sparse2=5 delay7d=9 (A2 frozen panel, key-for-key)")


def _synth_cell_and_arms(cid="G1C3", base=1_650_000_000.0, n_rpt=12,
                         **kwargs):
    payload, doc = a2_infer._synth_payload(cid, base, n_rpt=n_rpt, **kwargs)
    _cell, arms = a2_infer._build_synth_sequences(payload, doc)
    return payload, doc, arms


def check_walker_equivalence(_root, emit):
    _payload, _doc, arms = _synth_cell_and_arms()
    max_dm = max_dp = 0.0
    n_checked = 0
    n_bitexact = 0
    for arm in QUERY_ARMS:
        seq = arms[arm]["sequence"]
        lag = DELAY7D_SECONDS if arm == "delay7d" else 0.0
        for model_key in sorted(MODEL_ARMS):
            cfg = MODEL_ARMS[model_key]
            model = build_arm_model_t(model_key, seed=3).double().eval()
            walker = AsOfWalkerA3T(model, seq, lag, cfg)
            for q in arms[arm]["queries"]:
                with torch.no_grad():
                    st = walker.state_at(q["query_epoch"])
                    ref = reference_asof_state_a3t(
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
    # walker at the last event == the a3t_model training engine (t update
    # path), and the scored t-NLL trace must match elementwise.
    arm = "raw"
    seq = arms[arm]["sequence"]
    cfg = MODEL_ARMS["full"]
    model = build_arm_model_t("full", seed=3).double().eval()
    walker = AsOfWalkerA3T(model, seq, 0.0, cfg)
    last_epoch = max(float(e["source_epoch"]) for e in seq["events"])
    with torch.no_grad():
        st = walker.state_at(last_epoch)
        m_eng, P_eng, trace = engine_full_replay_a3t(model, seq, cfg)
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
    emit("  walker == reference re-filter (t update) on %d query/arm/model "
         "states (max|dm|=%.2e max|dP|=%.2e; %d bit-exact); walker == "
         "a3t_model engine at last event (err=%.2e); t NLLs == engine trace "
         "(max|dnll|=%.2e over %d scored RPTs)"
         % (n_checked, max_dm, max_dp, n_bitexact, d_eng, max_dnll,
            len(engine_nll)))


def check_t_columns_and_quantiles(_root, emit):
    """t NLL / gauss NLL double column correctness and t-quantile coverage."""
    # (a) quantile implementation vs the standard t table + normal limit
    for df, levels in _T_TABLE.items():
        for level, ref_z in levels.items():
            got = _t_z(df, level)
            assert abs(got - ref_z) < 5e-6, (df, level, got, ref_z)
    for level, z_inf in _NORM_Z.items():
        got = _t_z(1e9, level)
        assert abs(got - z_inf) < 1e-6, (level, got, z_inf)
    try:
        import mpmath as mp
        mp.mp.dps = 30
        for df in (2.5, 5.0, 12.3):
            for level in (0.90, 0.95):
                q = 0.5 + level / 2.0

                def cdf(x):
                    x = mp.mpf(x)
                    tail = 0.5 * mp.betainc(
                        mp.mpf(df) / 2, mp.mpf("0.5"), mp.mpf(0),
                        mp.mpf(df) / (df + x * x), regularized=True)
                    return float(1 - tail)

                lo, hi = mp.mpf(0), mp.mpf(8)
                for _ in range(80):
                    mid = (lo + hi) / 2
                    if cdf(mid) < q:
                        lo = mid
                    else:
                        hi = mid
                ref = float((lo + hi) / 2)
                assert abs(_t_z(df, level) - ref) < 1e-9, (df, level)
    except ImportError:
        pass
    # (b) t NLL formula equals the model's nll_rpt_t on identical (y, S)
    model = build_arm_model_t("full", 5).double().eval()
    q_ref = torch.tensor([0.28], dtype=FILTER_DTYPE)
    y = torch.tensor([0.2713], dtype=FILTER_DTYPE)
    m = torch.tensor([[0.03, -5.4, 0.004]], dtype=FILTER_DTYPE)
    P = torch.diag(torch.tensor([4e-6, 1e-3, 2e-6],
                                dtype=torch.float64)).reshape(1, 3, 3)
    with torch.no_grad():
        mu, _lat, S, _H = model.capacity_moments(m, P, q_ref)
        t_model = float(model.nll_rpt_t(m, P, q_ref, y)[0])
        g_model = float(model.nll_rpt(m, P, q_ref, y)[0])
    t_helper = _t_nll(float(y[0]), float(mu[0]), float(S[0]),
                      float(model.nu_df()))
    assert abs(t_helper - t_model) < 1e-10, (t_helper, t_model)
    # (c) nu -> inf: the two NLL columns converge
    with torch.no_grad():
        model.nu_raw.fill_(1e7)
        t_big = float(model.nll_rpt_t(m, P, q_ref, y)[0])
    assert abs(t_big - g_model) < 1e-4, (t_big, g_model)
    emit("  t quantiles == standard table (df 5/10/30, err<5e-6), -> normal z "
         "at nu=1e9; _t_nll == nll_rpt_t (<1e-10); t NLL -> gauss NLL at "
         "nu=1e7 (|d|=%.1e)" % abs(t_big - g_model))


def check_no_future_leakage(_root, emit):
    base_payload, base_doc, base_arms = _synth_cell_and_arms(
        "G1C3", n_rpt=12)
    fut_payload, fut_doc, fut_arms = _synth_cell_and_arms(
        "G1C3", n_rpt=12, future_extra=True)
    arm = "raw"
    cfg = MODEL_ARMS["full"]
    model = build_arm_model_t("full", seed=3).double().eval()
    seq_base = base_arms[arm]["sequence"]
    seq_fut = fut_arms[arm]["sequence"]
    assert len(seq_fut["events"]) > len(seq_base["events"])
    q = base_arms[arm]["queries"][-1]["query_epoch"]
    with torch.no_grad():
        a = AsOfWalkerA3T(model, seq_base, 0.0, cfg).state_at(q)
        b = AsOfWalkerA3T(model, seq_fut, 0.0, cfg).state_at(q)
    assert torch.max(torch.abs(a["m"] - b["m"])) == 0.0
    assert torch.max(torch.abs(a["P"] - b["P"])) == 0.0
    ref_a = reference_asof_state_a3t(model, seq_base, q, cfg, 0.0)
    ref_b = reference_asof_state_a3t(model, seq_fut, q, cfg, 0.0)
    assert torch.max(torch.abs(ref_a["m"] - ref_b["m"])) == 0.0
    qidx_base = [(x["query_epoch"], x["anchor_index"])
                 for x in base_arms[arm]["queries"]]
    qidx_fut = [(x["query_epoch"], x["anchor_index"])
                for x in fut_arms[arm]["queries"] if x["query_epoch"] <= q]
    assert qidx_base == qidx_fut
    emit("  appended future RPT/cycles leave the as-of state at q "
         "bit-identical and the query panel prefix unchanged")


def check_go_mutations(root, emit):
    good = _go_doc_for_self_check(root)
    problems, norm = validate_go_document_a3t(good, expected_cells=3)
    assert not problems, problems
    assert set(norm["checkpoints"]) == set(MODEL_ARMS)
    assert norm["no_grad"] is True and norm["max_rss_gb"] == 2.0
    mutations = []

    def mut(label, fn):
        item = copy.deepcopy(good)
        fn(item)
        mutations.append((label, item))

    mut("status", lambda g: g.__setitem__("status", "PENDING"))
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
    mut("code_missing_a3t_infer",
        lambda g: g["code_sha256"].pop("a3t_infer.py"))
    mut("code_missing_a3t_model",
        lambda g: g["code_sha256"].pop("a3t_model.py"))
    mut("code_missing_a3_model",
        lambda g: g["code_sha256"].pop("a3_model.py"))
    mut("code_bad_sha", lambda g: g["code_sha256"].__setitem__(
        "a3t_model.py", "z" * 64))
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
    mut("missing_rpt_manifest", lambda g: g.pop("rpt_manifest"))
    for label, doc in mutations:
        bad, _ = validate_go_document_a3t(doc, expected_cells=3)
        assert bad, "mutation %r was not rejected" % label
    emit("  valid GO accepted; %d refusal mutations rejected (incl. missing "
         "a3t_model.py / a3t_infer.py pins)" % len(mutations))


def check_binding_refusals(root, emit):
    import copy as _copy
    tree_root = os.path.join(root, "binding_fixture")
    tree = a2_infer._write_synth_tree(tree_root, n_cells=2)
    docs = {k: _copy.deepcopy(tree[k]) for k in
            ("cohort", "data_manifest", "cycling_manifest", "rpt_manifest")}
    man_paths = {"cohort": os.path.join(tree_root, "cohort.json"),
                 "data_manifest": os.path.join(tree_root,
                                               "data_manifest.json"),
                 "cycling_manifest": os.path.join(tree_root, "cycling.json"),
                 "rpt_manifest": os.path.join(tree_root, "rpt.json")}
    for label, path in man_paths.items():
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(tree[label], fh)
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
    bad_cohort = _copy.deepcopy(docs["cohort"])
    bad_cohort["roles"]["G1C3"] = "locked"
    try:
        _build_dev_specs(bad_cohort, docs["data_manifest"],
                         docs["cycling_manifest"], docs["rpt_manifest"],
                         tree_root, 2)
        raise AssertionError("cohort role mutation was not rejected")
    except InferenceError:
        pass

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
            "request_id": "a3t-c3infer-selfcheck-0002",
            "registry_path": registry or os.path.join(root, "registry.jsonl"),
        }
        if norm_override:
            norm.update(norm_override)
        return validate_go_bindings_a3t(norm, ReadStats(),
                                        registry_path=norm["registry_path"])

    binding, problems = _binding()
    assert binding is None and problems, "bindings must refuse here"
    assert any("not found" in p or "not loadable" in p for p in problems), \
        problems  # the fake checkpoint files do not exist
    bad_src = _copy.deepcopy(src_norm["sources"])
    bad_src["cohort"]["sha256"] = "c" * 64
    _b, problems = _binding({"sources": bad_src})
    assert any("sha256 mismatch" in p for p in problems), problems
    reg_path = os.path.join(root, "registry.jsonl")
    with open(reg_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"request_id": "a3t-c3infer-selfcheck-0002",
                             "go_sha256": "x", "finished_utc": "y"}) + "\n")
    _b, problems = _binding(registry=reg_path)
    assert any("already appears in the consumed-GO registry" in p
               for p in problems), problems
    stale_out = os.path.join(tree_root, "out_stale")
    os.makedirs(stale_out, exist_ok=True)
    with open(os.path.join(stale_out, "junk.txt"), "w") as fh:
        fh.write("x")
    _b, problems = _binding(out_dir=stale_out)
    assert any("fresh/empty" in p for p in problems), problems
    # checkpoint sha mismatch fires BEFORE any torch.load
    fake = os.path.join(root, "fake_full.bin")
    with open(fake, "w", encoding="utf-8") as fh:
        fh.write("this is not a checkpoint; the sha check must fire first")
    spec = {"path": fake, "sha256": "b" * 64}
    try:
        _load_arm_model_a3t("full", spec, ReadStats())
        raise AssertionError("wrong checkpoint sha256 was not rejected")
    except InferenceError as exc:
        assert "sha256 mismatch" in str(exc), str(exc)
    # A3 (Gaussian) checkpoints are refused: strict load into A3TStateModel
    from a3_model import build_arm_model as _build_a3
    a3_state = os.path.join(root, "a3_gauss_full.bin")
    torch.save(_build_a3("full", seed=1).state_dict(), a3_state)
    a3t_state = os.path.join(root, "a3t_ok_full.bin")
    torch.save(build_arm_model_t("full", seed=1).state_dict(), a3t_state)
    try:
        _load_arm_model_a3t("full", {"path": a3_state,
                                     "sha256": hash_file(a3_state)},
                            ReadStats())
        raise AssertionError("an A3 Gaussian checkpoint was accepted")
    except InferenceError as exc:
        assert "does not match A3TStateModel" in str(exc), str(exc)
    model_ok, info_ok = _load_arm_model_a3t(
        "full", {"path": a3t_state, "sha256": hash_file(a3t_state)},
        ReadStats())
    assert math.isfinite(info_ok["nu"]) and 2.0 < info_ok["nu"]
    assert "t_z95" in info_ok
    emit("  manifest/dev-specs positive path ok; refusals: manifest sha, "
         "consumed request_id, stale out_dir, checkpoint sha mismatch "
         "(pre-load), A3-Gaussian checkpoint refused (strict A3T load); "
         "A3-T checkpoint loads with nu=%r + t-quantiles in info"
         % info_ok["nu"])


def check_synthetic_pipeline(root, emit):
    tree_root = os.path.join(root, "pipeline_fixture")
    tree = a2_infer._write_synth_tree(tree_root, n_cells=3)
    specs, _roots = _build_dev_specs(
        tree["cohort"], tree["data_manifest"], tree["cycling_manifest"],
        tree["rpt_manifest"], tree_root, 3)
    stats = ReadStats()
    cells = [load_cell(spec, stats) for spec in specs]
    models = _synth_models_a3t()
    binding = _synth_binding_a3t()
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
    for key in ("t_nll_cell_macro", "gauss_nll_cell_macro", "nll_cell_macro",
                "rmse_cell_macro", "mae_cell_macro",
                "coverage_90_cell_macro", "coverage_90_t_cell_macro",
                "cov90_t_cell_macro", "cov90_gauss_cell_macro",
                "over_20mah_cell_macro"):
        assert key in nj["overall"], key
    assert len(nj["by_arm_model"]) == len(QUERY_ARMS) * len(MODEL_ARMS)
    assert len(nj["by_model"]) == len(MODEL_ARMS)
    assert len(nj["by_arm"]) == len(QUERY_ARMS)
    assert set(summary["nu_by_model"]) == set(MODEL_ARMS)
    assert all(2.0 < v < 1e6 for v in summary["nu_by_model"].values())
    rpt = summary["metrics"]["rpt_innovations"]["overall"]
    assert rpt["n_scored"] > 0
    assert "t_nll_cell_macro" in rpt and "gauss_nll_cell_macro" in rpt
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
    assert receipt["nu_by_model"] == summary["nu_by_model"]
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
    worst_pair = 0.0
    n_scored_rows = 0
    for r in rows:
        if r["model_key"] in ("time", "noEll"):
            assert all(abs(float(r["control_%02d" % i])) < 1e-12
                       and abs(float(r["control_mask_%02d" % i])) < 1e-12
                       for i in range(CONTROL_DIM))
            assert r["control_policy"] == "all_masked_time_arm"
        if r["model_key"] == "noEll":
            assert r["model_ell_state"] == "0"
            assert abs(float(r["state_ell"]) + 5.8) < 1e-6
        assert 2.0 < float(r["model_nu"]) < 1e6
        assert float(r["model_t_z95"]) > _NORM_Z[0.95] - 1e-6  # t >= gauss
        if r["target_available"] == "1":
            n_scored_rows += 1
            mean = float(r["pred_mean_ah"])
            var = float(r["pred_var_ah2"])
            y = float(r["target_capacity_ah"])
            nu = float(r["model_nu"])
            # gauss column == the a2_infer Gaussian NLL exactly
            nll = 0.5 * ((y - mean) ** 2 / var + math.log(var) + LOG_2PI)
            assert abs(nll - float(r["gauss_nll_per_ah"])) < 1e-9
            assert abs(nll - float(r["nll_per_ah"])) < 1e-9
            # t column == the t NLL at the row's nu
            t_nll = _t_nll(y, mean, var, nu)
            assert abs(t_nll - float(r["t_nll_per_ah"])) < 1e-9
            # coverage flags re-derived from the printed z values
            sd = math.sqrt(var)
            assert int(abs(y - mean) <= _NORM_Z[0.90] * sd) == \
                int(r["covered_90"] == "1")
            assert int(abs(y - mean) <= float(r["model_t_z90"]) * sd) == \
                int(r["t_covered_90"] == "1")
            assert int(abs(y - mean) <= float(r["model_t_z95"]) * sd) == \
                int(r["t_covered_95"] == "1")
            # t coverage is never narrower than Gaussian at the same rows
            if r["t_covered_90"] == "0":
                assert r["covered_90"] == "0"
            worst_pair = max(worst_pair,
                             abs(float(r["t_nll_per_ah"])
                                 - float(r["gauss_nll_per_ah"])))
    assert n_scored_rows > 0
    emit("  synthetic pipeline: 3 cells, %d rows (x4 arms), %d scored "
         "next-jump; t/gauss NLL double column + t coverage verified on all "
         "scored rows (max |t-gauss|=%.3f nats); summary carries t_nll/"
         "gauss_nll/cov90_t/cov90_gauss + nu_by_model; receipt carries nu"
         % (len(rows), n_scored_rows, worst_pair))


def check_subset_gate(root, emit):
    good = _go_doc_for_self_check(root)
    doc = copy.deepcopy(good)
    doc["checkpoint_subset"] = ["full"]
    doc["checkpoints"] = {"full": good["checkpoints"]["full"]}
    problems, norm = validate_go_document_a3t(doc, expected_cells=3)
    assert not problems, problems
    assert norm["checkpoint_subset"] == ["full"]
    assert set(norm["checkpoints"]) == {"full"}
    doc = copy.deepcopy(good)
    doc["checkpoint_subset"] = ["a3t_full"]
    doc["checkpoints"] = {"A3T_Full": good["checkpoints"]["full"]}
    problems, norm = validate_go_document_a3t(doc, expected_cells=3)
    assert not problems, problems
    assert norm["checkpoint_subset"] == ["full"]
    assert set(norm["checkpoints"]) == {"full"}
    problems, norm4 = validate_go_document_a3t(good, expected_cells=3)
    assert not problems, problems
    assert norm4["checkpoint_subset"] is None
    assert set(norm4["checkpoints"]) == set(MODEL_ARMS)
    doc = copy.deepcopy(good)
    doc["checkpoint_subset"] = None
    problems, norm_null = validate_go_document_a3t(doc, expected_cells=3)
    assert not problems, problems
    assert norm_null["checkpoint_subset"] is None
    assert set(norm_null["checkpoints"]) == set(MODEL_ARMS)
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
        problems, _ = validate_go_document_a3t(mut(fn), expected_cells=3)
        assert problems, "subset mutation %r was not refused" % label
    emit("  subset GO accepted (plain/a3t-alias/null/back-compat); %d subset "
         "refusal mutations rejected" % len(cases))


def check_subset_pipeline(root, emit):
    tree_root = os.path.join(root, "subset_fixture")
    tree = a2_infer._write_synth_tree(tree_root, n_cells=2)
    specs, _roots = _build_dev_specs(
        tree["cohort"], tree["data_manifest"], tree["cycling_manifest"],
        tree["rpt_manifest"], tree_root, 2)
    cells = [load_cell(spec, ReadStats()) for spec in specs]
    ref_binding = _synth_binding_a3t()
    ref_binding["stats"] = ReadStats()
    ref_summary, _ = execute_inference(
        cells, _synth_models_a3t(), ref_binding,
        os.path.join(tree_root, "out_ref"), deadline=None, progress=False)
    subset_models = {k: m for k, m in _synth_models_a3t().items()
                     if k == "full"}
    binding = _synth_binding_a3t(arms=["full"])
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
    assert len(summary["metrics"]["rpt_innovations"]["by_model"]) == \
        len(QUERY_ARMS)
    assert ({h["model_key"] for h in summary["metrics"]["fixed_horizons"]}
            == {"full"})
    assert set(summary["checkpoints"]) == {"full"}
    with open(os.path.join(out_dir, "predictions_c3_a3t.csv"), "r",
              encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == summary["counts"]["n_prediction_rows"]
    assert {r["model_key"] for r in rows} == {"full"}
    with open(ref_summary["outputs"]["predictions_csv"], "r",
              encoding="utf-8", newline="") as fh:
        ref_rows = [r for r in csv.DictReader(fh)
                    if r["model_key"] == "full"]
    assert rows == ref_rows
    assert ref_summary["checkpoint_subset"] is None
    assert ref_summary["counts"]["n_models"] == len(MODEL_ARMS)
    emit("  subset run: model_arms=['full'], n_rows==n_queries (%d), "
         "full-arm CSV rows bit-identical to the four-arm reference (%d "
         "rows); four-arm default untouched" % (len(rows), len(ref_rows)))


def check_float_discipline(_root, emit):
    model32 = build_arm_model_t("full", seed=5)
    assert str(next(model32.parameters()).dtype) == "torch.float32"
    model64 = model32.double()
    for p32, p64 in zip(model32.parameters(), model64.parameters()):
        assert torch.equal(p64, p32.to(torch.float64))  # exact cast
    _payload, _doc, arms = _synth_cell_and_arms()
    seq = arms["raw"]["sequence"]
    cfg = MODEL_ARMS["full"]
    walker = AsOfWalkerA3T(model64, seq, 0.0, cfg)
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
        float(model64.obs_sigma()) ** 2
    nu32 = float(model32.nu_df())
    nu64 = float(model64.nu_df())
    assert 2.0 < nu64 < 1e6 and abs(nu64 - nu32) < 1e-6
    emit("  float32 checkpoint params -> exact float64 filter; P symmetric "
         "(0.0), PSD (min eig %.3e), mu=Qref*exp(-D)+R exact, total var == "
         "latent + sigma_y^2 exact, nu=%.4f carried" % (min_eig, nu64))


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


def check_rss_gate(_root, emit):
    peak = _rss_gb()
    assert peak is None or peak > 0.05  # sane reading on this process
    if peak is not None:
        raised = False
        try:
            _check_rss(max(0.1, peak / 1000.0))  # absurdly low cap
        except _RssCapExceeded:
            raised = True
        assert raised, "RSS cap did not fire below the current peak"
        _check_rss(64.0)  # generous cap passes
    emit("  RSS gate: peak=%.3f GiB read; cap below the peak fires; "
         "generous cap passes" % (peak if peak is not None else -1.0))


def run_self_check(append_log=None, verbose=True):
    lines = []

    def emit(text=""):
        print(text)
        lines.append(text)

    emit("=" * 78)
    emit("A3-T C3 INFERENCE SELF-CHECK -- %s" % _utc_now())
    emit("mode: SYNTHETIC ONLY -- 0 real payload reads, 0 real checkpoint "
         "files, 0 fits, 0 optimizer steps, 0 GO created or consumed")
    emit("python %s | torch %s | numpy %s | a3t %s | a3 %s"
         % (sys.version.split()[0], torch.__version__, np.__version__,
            A3T_VERSION, VERSION))
    existing = {name: hash_file(_code_path(name)) for name in REQUIRED_CODE
                if os.path.isfile(_code_path(name))}
    emit("code_sha256: %s" % json.dumps(existing, sort_keys=True))
    emit("-" * 78)

    checks = [("adapter_reuse", check_adapter_reuse),
              ("walker_method_reuse", check_walker_method_reuse),
              ("query_grid_frozen", check_query_grid_frozen),
              ("walker_equivalence", check_walker_equivalence),
              ("t_columns_quantiles", check_t_columns_and_quantiles),
              ("no_future_leakage", check_no_future_leakage),
              ("go_mutations", check_go_mutations),
              ("binding_refusals", check_binding_refusals),
              ("synthetic_pipeline", check_synthetic_pipeline),
              ("subset_gate", check_subset_gate),
              ("subset_pipeline", check_subset_pipeline),
              ("float_discipline", check_float_discipline),
              ("registry_gate", check_registry_gate),
              ("rss_gate", check_rss_gate)]
    passed = failed = 0
    audit = _OpenAudit()
    tmp_root = tempfile.mkdtemp(prefix="a3t_infer_selfcheck_")
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
        real_root = os.environ.get("A3T_INFER_ROOT", "/home/yndx/zxk/rul")
        a3t_dir = os.path.join(real_root, "experiments",
                               "multirate_state_A3_rate_20261024", "a3t")
        forbidden = [os.path.join(real_root, "data"),
                     os.path.join(real_root, "reports"),
                     os.path.join(real_root, "automation"),
                     os.path.join(a3t_dir, "runs")]
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
                 "automation/a3t-runs (all under %s)"
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
    emit("REAL PAYLOAD READS: 0. REAL CHECKPOINT FILES READ: 0. FITS: 0. "
         "OPTIMIZER STEPS: 0.")
    emit("NO GO CREATED. NO GO CONSUMED. NO RECEIPT OUTSIDE THE TEMP FIXTURE.")
    emit("RESULT: %s" % ("OK (%d passed / %d failed)" % (passed, failed)
                         if failed == 0 else "FAILED (%d failed)" % failed))
    if append_log:
        block = ("\n===== a3t_infer self-check %s =====\n" % _utc_now()) + \
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
        description="A3-T C3 development inference: synthetic self-check by "
                    "default; real inference only under an APPROVED, "
                    "unconsumed GO.")
    parser.add_argument("--self-check", action="store_true",
                        help="run synthetic fixtures (default behaviour)")
    parser.add_argument("--go", default=None,
                        help="path to an APPROVED A3-T C3 inference GO json")
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
    print("A3-T C3 inference -- synthetic self-check (no GO supplied)")
    return run_self_check(append_log=args.append_log)


if __name__ == "__main__":
    sys.exit(main())
