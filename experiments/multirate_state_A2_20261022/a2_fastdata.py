"""Fast A2 data path: vectorised npz loader + windowed (truncated-BPTT) replay.

Why this module exists
----------------------
The first A2 training attempt built one Python dict per event (774,486 events) and
then advanced the filter one event at a time in Python; loading alone took more
than 22 minutes and a 6-fit x 3000-step budget was unreachable.  This module keeps
the same data contract and the same filter semantics but changes the constant:

* Loader: PREP already writes per-cell contiguous arrays (event_cell is
  non-decreasing).  A single bincount + cumsum yields the per-cell offsets, and
  all training tensors are built with vectorised slices/advanced indexing.  No
  per-event Python object is constructed on the hot path.

* Replay: between two RPT measurement updates the transition is affine with a
  diagonal state matrix F = diag(1, alpha).  The state at every event of such a
  block is therefore a prefix sum (D, P00), a prefix product (P01) or an affine
  scan (R, P11) of per-event scalars computed by the control network in a single
  batched call.  An associative log-depth scan composes the affine maps, so the
  autograd graph is O(log T) deep instead of O(T) nodes.  This is algebraically
  identical to the sequential recursion of a2_targets.replay_batch (verified to
  1e-9 in float64 by the fixtures); it just does not pay per-event Python and
  autograd dispatch.

Contract that is deliberately unchanged
---------------------------------------
* Capacity is state-only: Q = Q_ref * exp(-D) + R (no readout, no context).
* sigma is a standard deviation; every variance is the explicit sigma**2 and the
  Gaussian NLL is 0.5*(nu**2/S + log S + log 2*pi).
* Cycle events only advance the state; every arrived post-anchor RPT is scored
  as a sequential innovation before the measurement update.  The anchor reading
  is not an event (it defines Q_ref) and is therefore never scored.
* Loss is cell-macro: per-cell mean innovation NLL, then the mean over cells.
* noRPTupdate (use_rpt=False) still predicts and scores every RPT, it just never
  applies the measurement correction.
* use_cycle=False masks the control (time term only) exactly as replay_batch.

Burn-in
-------
Window start states are produced by a no-grad filter pass.  Two modes exist:

burn_in="exact" (default)
    Filter the whole prefix from the anchor.  Because the model is an exact
    linear-Gaussian filter, the window start state is then the full-sequence
    filtered state (float64 agreement about 1e-13), so a window loss equals the
    corresponding segment of the full-sequence replay.  With the block scan this
    costs O(prefix) vectorised work, not O(prefix) Python steps.

burn_in="last_w"
    Literal W-event truncation (burn_in_events, default 128).  This is kept
    because the task specified it, but it is an approximation, not an identity:
    the D drift accumulates and does not forget, so a window starting beyond
    event W does NOT see the same state as the full filter.  The fixture
    truncated_burnin_gap_is_real measures the resulting loss gap.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F

from a2_model import CONTROL_DIM, LOG_2PI
from a2_targets import hash_file

WEEK_SECONDS = 604800.0
NPZ_KEYS = (
    "cell_ids", "q_ref_ah", "anchor_source_epoch", "event_cell", "event_kind",
    "event_source", "event_available", "event_dt_weeks", "control",
    "control_mask", "capacity_ah", "score",
)


# --------------------------------------------------------------------- helpers
def _affine_scan(a, c):
    """Inclusive scan of x_t = a_t * x_{t-1} + c_t.

    Returns (A, C) with x_t = A_t * x_{-1} + C_t.  Hillis-Steele doubling:
    log2(T) steps, all vectorised over [B, T].
    """
    A, C = a, c
    T = a.shape[1]
    d = 1
    while d < T:
        A_prev = torch.cat([torch.ones_like(A[:, :d]), A[:, :-d]], dim=1)
        C_prev = torch.cat([torch.zeros_like(C[:, :d]), C[:, :-d]], dim=1)
        C = C + A * C_prev
        A = A * A_prev
        d <<= 1
    return A, C


def _event_scalars(model, kind, dt, control, control_mask, use_cycle):
    """Per-event transition scalars from ONE batched rate-network call.

    Returns dict of [B, T] tensors: d_inc, alpha, c, q00, q11 with
        D'   = D + d_inc
        R'   = alpha * R + c
        P00' = P00 + q00
        P01' = alpha * P01
        P11' = alpha**2 * P11 + q11
    i.e. exactly model.advance for a diagonal F, with the same formulas.
    """
    zero_c = torch.zeros_like(control)
    zero_m = torch.zeros_like(control_mask)
    if use_cycle:
        is_cycle = (kind == 1).unsqueeze(-1)
        ctl = torch.where(is_cycle, control, zero_c)
        msk = torch.where(is_cycle, control_mask, zero_m)
    else:
        ctl, msk = zero_c, zero_m
    msk = msk.clamp(0.0, 1.0)
    x = model.standardize_control(ctl)
    raw = model.rates(torch.cat([x * msk, msk], dim=-1))
    d_rate = F.softplus(model.base[0] + raw[..., 0])
    d_sigma = F.softplus(model.base[1] + raw[..., 1])
    lam = F.softplus(model.base[2] + raw[..., 2]) + 1e-6
    r_eq = model.r_eq_scale * torch.tanh(raw[..., 3])
    r_sigma = F.softplus(model.base[3] + raw[..., 4])
    dtw = dt.clamp_min(0.0)
    alpha = torch.exp(-lam * dtw)
    one_minus_alpha = -torch.expm1(-lam * dtw)
    q11 = r_sigma.square() * (-torch.expm1(-2.0 * lam * dtw)) / (2.0 * lam)
    return {
        "d_inc": d_rate * dtw,
        "alpha": alpha,
        "c": one_minus_alpha * r_eq,
        "q00": d_sigma.square() * dtw,
        "q11": q11,
    }


def _block_state(m, P, scal, a, b):
    """State after events [a, b) given the state before a (closed form).

    For a block whose decay product stays representable, the affine recursions
    use the exact cumprod/cumsum identity

        R_t = A_t * (R_0 + sum_k c_k / A_k),   A_t = prod_{j<=t} alpha_j

    which costs O(1) vectorised ops instead of O(log L).  Long or strongly
    decaying blocks fall back to the log-depth associative scan (no division,
    no underflow).
    """
    if b <= a:
        return m, P
    alpha = scal["alpha"][:, a:b]
    c = scal["c"][:, a:b]
    q11 = scal["q11"][:, a:b]
    a2 = alpha.square()
    A = torch.cumprod(alpha, dim=1)
    A2 = torch.cumprod(a2, dim=1)
    floor = 1e-30 if alpha.dtype == torch.float64 else 1e-12
    use_cumsum = (float(A[:, -1].min()) > floor) and \
                 (float(A2[:, -1].min()) > floor * floor)
    if use_cumsum:
        C = A * torch.cumsum(c / A, dim=1)
        C2 = A2 * torch.cumsum(q11 / A2, dim=1)
        a_last, c_last = A[:, -1], C[:, -1]
        a2_last, c2_last = A2[:, -1], C2[:, -1]
    else:
        a_last, c_last = _affine_scan(alpha, c)
        a2_last, c2_last = _affine_scan(a2, q11)
        a_last, c_last = a_last[:, -1], c_last[:, -1]
        a2_last, c2_last = a2_last[:, -1], c2_last[:, -1]
    m_d = m[:, 0] + scal["d_inc"][:, a:b].sum(dim=1)
    m_r = a_last * m[:, 1] + c_last
    p00 = P[:, 0, 0] + scal["q00"][:, a:b].sum(dim=1)
    p01 = P[:, 0, 1] * A[:, -1]
    p11 = a2_last * P[:, 1, 1] + c2_last
    m_new = torch.stack([m_d, m_r], dim=-1)
    P_new = torch.stack(
        [torch.stack([p00, p01], dim=-1), torch.stack([p01, p11], dim=-1)],
        dim=-2)
    return m_new, P_new


def _rpt_correct_fast(model, m, P, q_ref, y):
    """Joseph-form capacity update, fused for the 2-state filter.

    Algebraically identical to model.correct_rpt (same Joseph form, same
    sigma**2 observation variance), but written out for the 2x2 case so the
    no-grad burn-in does not pay for the general diagnostics path.
    """
    rv = model.obs_variance().to(dtype=m.dtype)
    qdet = q_ref * torch.exp(-m[:, 0])
    mu = qdet + m[:, 1]
    h0 = -qdet
    p00 = P[:, 0, 0]
    p01 = P[:, 0, 1]
    p11 = P[:, 1, 1]
    latent = h0 * h0 * p00 + 2.0 * h0 * p01 + p11
    S = latent + rv
    nu = y - mu
    k0 = (p00 * h0 + p01) / S
    k1 = (p01 * h0 + p11) / S
    m0 = m[:, 0] + k0 * nu
    m1 = m[:, 1] + k1 * nu
    a00 = 1.0 - k0 * h0
    a01 = -k0
    a10 = -k1 * h0
    a11 = 1.0 - k1
    np00 = (a00 * a00 * p00 + 2.0 * a00 * a01 * p01 + a01 * a01 * p11
            + k0 * k0 * rv)
    np01 = (a00 * a10 * p00 + (a00 * a11 + a01 * a10) * p01
            + a01 * a11 * p11 + k0 * k1 * rv)
    np11 = (a10 * a10 * p00 + 2.0 * a10 * a11 * p01 + a11 * a11 * p11
            + k1 * k1 * rv)
    m_new = torch.stack([m0, m1], dim=-1)
    P_new = torch.stack(
        [torch.stack([np00, np01], dim=-1),
         torch.stack([np01, np11], dim=-1)], dim=-2)
    return m_new, P_new


def _run_events(model, kind, dt, control, control_mask, y, score, q_ref, m, P,
                use_cycle=True, use_rpt=True, collect_nll=True):
    """Replay a padded [B, T] event block; returns (m, P, nll_sum, n_scored).

    Segment boundaries are the union of RPT positions over the batch.  Every
    segment is propagated in closed form (_block_state), so the Python loop runs
    once per RPT position, not once per event.
    """
    B, T = kind.shape
    if T == 0:
        zero = torch.zeros(B, dtype=m.dtype, device=m.device)
        return m, P, zero, torch.zeros(B, dtype=torch.long, device=m.device)
    scal = _event_scalars(model, kind, dt, control, control_mask, use_cycle)
    nll_sum = torch.zeros(B, dtype=m.dtype, device=m.device)
    n_scored = torch.zeros(B, dtype=torch.long, device=m.device)
    rpt_positions = torch.nonzero((kind == 2).any(dim=0),
                                  as_tuple=False).flatten().tolist()
    start = 0
    for r in rpt_positions:
        m, P = _block_state(m, P, scal, start, r + 1)
        is_rpt = kind[:, r] == 2
        hit = is_rpt & score[:, r]
        if collect_nll:
            mu, _, S, _ = model.capacity_moments(m, P, q_ref)
            step_nll = 0.5 * ((y[:, r] - mu).square() / S
                              + torch.log(S) + LOG_2PI)
            nll_sum = nll_sum + torch.where(hit, step_nll,
                                            torch.zeros_like(step_nll))
            n_scored = n_scored + hit.long()
        if use_rpt:
            if collect_nll:
                m_new, P_new, _, _ = model.correct_rpt(m, P, q_ref, y[:, r])
            else:
                m_new, P_new = _rpt_correct_fast(model, m, P, q_ref, y[:, r])
            m = torch.where(hit[:, None], m_new, m)
            P = torch.where(hit[:, None, None], P_new, P)
        start = r + 1
    if start < T:
        m, P = _block_state(m, P, scal, start, T)
    return m, P, nll_sum, n_scored


# ------------------------------------------------------------------ data class
class FastA2Data(object):
    """Compact in-memory training tensors built directly from a PREP npz."""

    def __init__(self, cell_ids, offsets, kind, dt, control, control_mask, y,
                 score, q_ref, anchor_source_epoch=None, manifest=None,
                 npz_path=None, npz_sha256=None, dtype=torch.float32):
        self.cell_ids = [str(c) for c in cell_ids]
        self.dtype = dtype
        self.offsets = np.ascontiguousarray(offsets, dtype=np.int64)
        self.counts = np.diff(self.offsets)
        self.kind = torch.as_tensor(np.ascontiguousarray(kind)).long()
        self.dt = torch.as_tensor(np.ascontiguousarray(dt)).to(dtype)
        self.control = torch.as_tensor(np.ascontiguousarray(control)).to(dtype)
        self.control_mask = torch.as_tensor(
            np.ascontiguousarray(control_mask)).to(dtype)
        self.y = torch.as_tensor(np.ascontiguousarray(y)).to(dtype)
        self.score = torch.as_tensor(np.ascontiguousarray(score)).bool()
        # Q_ref is a per-cell physical anchor; keep it in float64 so the fast
        # loader reproduces the slow loader's float(q_ref) exactly.
        self.q_ref = torch.as_tensor(np.ascontiguousarray(q_ref)).double()
        self.anchor_source_epoch = (
            None if anchor_source_epoch is None else
            np.asarray(anchor_source_epoch, dtype=np.float64))
        self.manifest = manifest
        self.npz_path = npz_path
        self.npz_sha256 = npz_sha256
        self._score_np = self.score.numpy()
        self._kind_np = self.kind.numpy()
        self._scored_cache = {}
        self.train_index = None
        self.val_index = None
        if manifest is not None:
            self._apply_manifest_split(manifest)

    # ------------------------------------------------------------- properties
    @property
    def n_cells(self):
        return len(self.cell_ids)

    @property
    def n_events(self):
        return int(self.offsets[-1])

    def cell_index(self, cell_id):
        return self.cell_ids.index(str(cell_id))

    # ---------------------------------------------------------------- loaders
    @classmethod
    def from_npz(cls, npz_path, manifest=None, verify_sha=None):
        if verify_sha:
            got = hash_file(npz_path)
            if str(verify_sha).lower() != got.lower():
                raise ValueError("prepared npz sha256 mismatch")
        with np.load(npz_path, allow_pickle=False) as z:
            missing = [k for k in NPZ_KEYS if k not in z.files]
            if missing:
                raise ValueError("npz is missing keys %r" % (missing,))
            arrays = {k: z[k] for k in NPZ_KEYS}
            npz_sha = verify_sha or hash_file(npz_path)
        cell_ids = [str(c) for c in arrays["cell_ids"].tolist()]
        n_cells = len(cell_ids)
        event_cell = arrays["event_cell"]
        n_events = int(event_cell.shape[0])
        if n_events != arrays["event_kind"].shape[0]:
            raise ValueError("event arrays disagree on length")
        counts = np.bincount(event_cell, minlength=n_cells).astype(np.int64)
        offsets = np.concatenate([[0], np.cumsum(counts)])
        if int(offsets[-1]) != n_events:
            raise ValueError("event_cell does not cover every event")
        expected = np.repeat(np.arange(n_cells, dtype=np.int64), counts)
        if not np.array_equal(event_cell, expected):
            raise ValueError("event_cell is not grouped/sorted per cell")
        if not np.all(np.isfinite(arrays["q_ref_ah"])) or \
                np.any(arrays["q_ref_ah"] <= 0):
            raise ValueError("q_ref must be finite and positive")
        if not set(np.unique(arrays["event_kind"]).tolist()) <= {1, 2}:
            raise ValueError("event_kind must be 1 (cycle) or 2 (rpt)")
        if np.any(arrays["event_dt_weeks"] < 0):
            raise ValueError("negative dt_weeks")
        if np.any(arrays["score"] & (arrays["event_kind"] != 2)):
            raise ValueError("only RPT events may be scored")
        return cls(cell_ids, offsets, arrays["event_kind"],
                   arrays["event_dt_weeks"], arrays["control"],
                   arrays["control_mask"], arrays["capacity_ah"],
                   arrays["score"], arrays["q_ref_ah"],
                   anchor_source_epoch=arrays["anchor_source_epoch"],
                   manifest=manifest, npz_path=npz_path, npz_sha256=npz_sha)

    @classmethod
    def from_manifest(cls, manifest_path, verify_sha=True):
        with open(manifest_path, "r", encoding="utf-8") as f:
            man = json.load(f)
        npz_path = man.get("prepared_npz")
        if not npz_path:
            raise ValueError("manifest has no prepared_npz")
        if not os.path.isabs(npz_path):
            npz_path = os.path.join(os.path.dirname(os.path.abspath(
                manifest_path)), npz_path)
        expected = man.get("prepared_npz_sha256")
        if verify_sha and not expected:
            raise ValueError("manifest must pin prepared_npz_sha256")
        data = cls.from_npz(npz_path, manifest=man,
                            verify_sha=expected if verify_sha else None)
        data.manifest_path = os.path.abspath(manifest_path)
        data.manifest_sha256 = hash_file(manifest_path)
        return data

    def _apply_manifest_split(self, man):
        split = man.get("split") or {}
        train_cells = [str(c) for c in split.get("train_cells", [])]
        val_cells = [str(c) for c in split.get("val_cells", [])]
        if not train_cells or not val_cells:
            raise ValueError("manifest split must list train_cells and val_cells")
        if set(train_cells) & set(val_cells):
            raise ValueError("split leaks cells")
        missing = (set(train_cells) | set(val_cells)) - set(self.cell_ids)
        if missing:
            raise ValueError("split references unknown cells: %r"
                             % sorted(missing)[:3])
        index = {c: i for i, c in enumerate(self.cell_ids)}
        self.train_index = np.asarray([index[c] for c in train_cells],
                                      dtype=np.int64)
        self.val_index = np.asarray([index[c] for c in val_cells],
                                    dtype=np.int64)

    @classmethod
    def from_sequences(cls, sequences, control_dim=CONTROL_DIM):
        """Test-only helper: build fast data from a2_targets-style sequences."""
        cell_ids, offsets = [], [0]
        kinds, dts, ctl, msk, ys, sc, qref, anchor = [], [], [], [], [], [], [], []
        for s in sequences:
            events = s["events"]
            for e in events:
                if e["kind"] == "cycle":
                    kinds.append(1)
                    ctl.append([float(v) for v in e["control"]])
                    msk.append([float(v) for v in e["control_mask"]])
                    ys.append(0.0)
                    sc.append(False)
                else:
                    kinds.append(2)
                    ctl.append([0.0] * control_dim)
                    msk.append([0.0] * control_dim)
                    ys.append(float(e["capacity_ah"]))
                    sc.append(bool(e.get("score", False)))
                dts.append(float(e["dt_weeks"]))
            offsets.append(offsets[-1] + len(events))
            cell_ids.append(str(s["cell_id"]))
            qref.append(float(s["q_ref_ah"]))
            anchor.append(float(s["anchor"]["source_epoch"]))
        return cls(cell_ids, np.asarray(offsets, dtype=np.int64),
                   np.asarray(kinds, dtype=np.int8),
                   np.asarray(dts, dtype=np.float64),
                   np.asarray(ctl, dtype=np.float64).reshape(-1, control_dim),
                   np.asarray(msk, dtype=np.float64).reshape(-1, control_dim),
                   np.asarray(ys, dtype=np.float64),
                   np.asarray(sc, dtype=bool), np.asarray(qref, dtype=np.float64),
                   anchor_source_epoch=np.asarray(anchor, dtype=np.float64),
                   dtype=torch.float64)

    def to_sequences(self, cells=None):
        """Test-only helper: convert back to a2_targets-style sequences (slow)."""
        cell_ids = self.cell_ids if cells is None else \
            [self.cell_ids[int(i)] for i in cells]
        index = {c: i for i, c in enumerate(self.cell_ids)}
        seqs = []
        for cid in cell_ids:
            i = index[cid]
            a, b = int(self.offsets[i]), int(self.offsets[i + 1])
            events = []
            for t in range(a, b):
                kind = int(self._kind_np[t])
                ev = {"kind": "cycle" if kind == 1 else "rpt",
                      "index": t - a,
                      "source_epoch": 0.0, "available_epoch": 0.0,
                      "dt_weeks": float(self.dt[t].item())}
                if kind == 1:
                    ev["control"] = self.control[t].tolist()
                    ev["control_mask"] = self.control_mask[t].tolist()
                else:
                    ev["capacity_ah"] = float(self.y[t].item())
                    ev["score"] = bool(self.score[t].item())
                events.append(ev)
            seqs.append({"cell_id": cid, "q_ref_ah": float(self.q_ref[i].item()),
                         "anchor": {"index": 0,
                                    "capacity_ah": float(self.q_ref[i].item()),
                                    "source_epoch": 0.0,
                                    "available_epoch": 0.0,
                                    "n_valid_arrived": 1},
                         "events": events})
        return seqs

    # --------------------------------------------------------------- indexing
    def scored_positions(self, i):
        i = int(i)
        got = self._scored_cache.get(i)
        if got is None:
            a, b = int(self.offsets[i]), int(self.offsets[i + 1])
            got = np.flatnonzero(self._score_np[a:b])
            self._scored_cache[i] = got
        return got

    def slice_tensors(self, i, a, b):
        base = int(self.offsets[int(i)])
        return {
            "kind": self.kind[base + a:base + b].unsqueeze(0),
            "dt": self.dt[base + a:base + b].unsqueeze(0),
            "control": self.control[base + a:base + b].unsqueeze(0),
            "control_mask": self.control_mask[base + a:base + b].unsqueeze(0),
            "y": self.y[base + a:base + b].unsqueeze(0),
            "score": self.score[base + a:base + b].unsqueeze(0),
            "q_ref": self.q_ref[int(i)].reshape(1),
        }

    def summary(self):
        return {
            "n_cells": self.n_cells,
            "n_events": self.n_events,
            "n_cycle_events": int((self._kind_np == 1).sum()),
            "n_rpt_events": int((self._kind_np == 2).sum()),
            "n_scored_rpt_events": int(self._score_np.sum()),
            "cells_with_scored_rpt": int(sum(
                1 for i in range(self.n_cells) if len(self.scored_positions(i)))),
            "min_events_per_cell": int(self.counts.min()),
            "max_events_per_cell": int(self.counts.max()),
            "mean_events_per_cell": float(self.counts.mean()),
            "npz_sha256": self.npz_sha256,
        }


def load_prepared_fast(manifest_path, verify_sha=True):
    """Fast replacement for a2_train.load_prepared_sequences.

    Returns a FastA2Data with train_index / val_index (cell indices from the
    manifest split) already attached.  The full manifest is kept in .manifest so
    the caller can record it verbatim.
    """
    return FastA2Data.from_manifest(manifest_path, verify_sha=verify_sha)


# --------------------------------------------------------------- standardizer
def fit_control_standardizer(data, train_index):
    """Vectorised train-only control standardisation (same rule as a2_targets).

    Only mask>0.5, finite values on cycle events of TRAIN cells contribute;
    per-dimension population std (ddof=0); constant / unseen dimensions get
    scale exactly 1.0 and are counted.
    """
    train_index = np.asarray(train_index, dtype=np.int64)
    in_train = np.zeros(data.n_cells, dtype=bool)
    in_train[train_index] = True
    event_in_train = in_train[np.asarray(
        np.repeat(np.arange(data.n_cells), data.counts))]
    kind = data._kind_np
    mask = data.control_mask.numpy()
    ctl = data.control.numpy()
    ok = (kind == 1)[:, None] & event_in_train[:, None] & (mask > 0.5) & \
        np.isfinite(ctl)
    count = ok.sum(axis=0).astype(np.float64)
    total = np.where(ok, ctl, 0.0).sum(axis=0, dtype=np.float64)
    total_sq = np.where(ok, np.square(ctl, dtype=np.float64), 0.0).sum(axis=0)
    mean = np.zeros(CONTROL_DIM, dtype=np.float64)
    var = np.zeros(CONTROL_DIM, dtype=np.float64)
    seen = count > 0
    mean[seen] = total[seen] / count[seen]
    var[seen] = np.maximum(total_sq[seen] / count[seen] - mean[seen] ** 2, 0.0)
    scale = np.sqrt(var)
    constant = (~seen) | (scale <= 1e-8) | (~np.isfinite(scale))
    scale = np.where(constant, 1.0, scale)
    return {
        "mean": torch.as_tensor(mean, dtype=torch.float64),
        "scale": torch.as_tensor(scale, dtype=torch.float64),
        "n_constant_scale_one_skipped": int(constant.sum()),
        "counts": torch.as_tensor(count, dtype=torch.float64),
    }


# ------------------------------------------------------------------ windows
class WindowBatch(object):
    """One padded batch of L-event windows (with their burn-in spans)."""

    def __init__(self, data, cell_index, start, window_events,
                 burn_in="exact", burn_in_events=128):
        self.data = data
        cell_index = np.asarray(cell_index, dtype=np.int64)
        start = np.asarray(start, dtype=np.int64)
        B = len(cell_index)
        L = int(window_events)
        if burn_in not in ("exact", "last_w"):
            raise ValueError("burn_in must be 'exact' or 'last_w'")
        self.burn_in = burn_in
        self.burn_in_events = int(burn_in_events)
        self.cell_index = torch.as_tensor(cell_index)
        self.start = torch.as_tensor(start)
        dt_ = data.dtype
        self.kind = torch.zeros(B, L, dtype=torch.long)
        self.dt = torch.zeros(B, L, dtype=dt_)
        self.control = torch.zeros(B, L, CONTROL_DIM, dtype=dt_)
        self.control_mask = torch.zeros(B, L, CONTROL_DIM, dtype=dt_)
        self.y = torch.zeros(B, L, dtype=dt_)
        self.score = torch.zeros(B, L, dtype=torch.bool)
        self.q_ref = torch.zeros(B, dtype=torch.float64)
        self.lengths = np.zeros(B, dtype=np.int64)
        burn_start = np.zeros(B, dtype=np.int64)
        burn_length = np.zeros(B, dtype=np.int64)
        for b in range(B):
            i = int(cell_index[b])
            s = int(start[b])
            n = int(data.counts[i])
            ln = max(0, min(L, n - s))
            if ln:
                base = int(data.offsets[i])
                sl = slice(base + s, base + s + ln)
                self.kind[b, :ln] = data.kind[sl]
                self.dt[b, :ln] = data.dt[sl]
                self.control[b, :ln] = data.control[sl]
                self.control_mask[b, :ln] = data.control_mask[sl]
                self.y[b, :ln] = data.y[sl]
                self.score[b, :ln] = data.score[sl]
            self.q_ref[b] = data.q_ref[i]
            self.lengths[b] = ln
            if burn_in == "exact":
                burn_start[b] = 0
                burn_length[b] = s
            else:
                burn_length[b] = min(self.burn_in_events, s)
                burn_start[b] = s - burn_length[b]
        self.burn_start = torch.as_tensor(burn_start)
        self.burn_length = torch.as_tensor(burn_length)
        self.cell_ids = [data.cell_ids[int(i)] for i in cell_index]

    @property
    def batch_size(self):
        return int(self.kind.shape[0])

    def to(self, device):
        for name in ("cell_index", "start", "kind", "dt", "control",
                     "control_mask", "y", "score", "q_ref", "burn_start",
                     "burn_length"):
            setattr(self, name, getattr(self, name).to(device))
        return self

    def describe(self):
        return {
            "batch_size": self.batch_size,
            "window_events": int(self.kind.shape[1]),
            "burn_in": self.burn_in,
            "burn_in_events": self.burn_in_events,
            "burn_length_min": int(self.burn_length.min()),
            "burn_length_max": int(self.burn_length.max()),
            "window_length_min": int(self.lengths.min()),
            "starts": [int(v) for v in self.start.tolist()],
        }


class WindowSampler(object):
    """Deterministic window sampler (RPT-containing windows by default)."""

    def __init__(self, data, cells, window_events=256, burn_in="exact",
                 burn_in_events=128, require_scored_rpt=True, batch_cells=None):
        cells = np.asarray(cells, dtype=np.int64)
        self.data = data
        self.window_events = int(window_events)
        self.burn_in = burn_in
        self.burn_in_events = int(burn_in_events)
        self.require_scored_rpt = bool(require_scored_rpt)
        scored = {int(i): data.scored_positions(int(i)) for i in cells}
        if self.require_scored_rpt:
            keep = [i for i in cells if len(scored[int(i)]) > 0]
            dropped = [data.cell_ids[int(i)] for i in cells
                       if len(scored[int(i)]) == 0]
            cells = np.asarray(keep, dtype=np.int64)
            self.dropped_cells = dropped
        else:
            self.dropped_cells = []
        if cells.size == 0:
            raise ValueError("no usable cell (none has a scored RPT)")
        self.cells = cells
        self.scored = scored
        self.batch_cells = int(batch_cells) if batch_cells else len(cells)

    def sample(self, rng):
        B = self.batch_cells
        cell_index = np.empty(B, dtype=np.int64)
        starts = np.empty(B, dtype=np.int64)
        for b in range(B):
            i = int(self.cells[rng.randrange(len(self.cells))])
            n = int(self.data.counts[i])
            L = min(self.window_events, n)
            if self.require_scored_rpt:
                pos = self.scored[i]
                p = int(pos[rng.randrange(len(pos))])
                lo = max(0, p - L + 1)
                hi = min(p, n - L)
                s = rng.randint(lo, hi) if hi > lo else lo
            else:
                s = rng.randint(0, max(0, n - L))
            cell_index[b] = i
            starts[b] = s
        return WindowBatch(self.data, cell_index, starts, self.window_events,
                           burn_in=self.burn_in,
                           burn_in_events=self.burn_in_events)

    def counts(self):
        """Number of valid RPT-containing windows per cell (diagnostic)."""
        out = {}
        for i in self.cells:
            i = int(i)
            n = int(self.data.counts[i])
            L = min(self.window_events, n)
            pos = self.scored[i]
            total = 0
            for p in pos:
                lo = max(0, int(p) - L + 1)
                hi = min(int(p), n - L)
                total += max(0, hi - lo + 1)
            out[self.data.cell_ids[i]] = int(total)
        return out


# ------------------------------------------------------------------- replay
def _burn_in_state(model, batch, use_cycle, use_rpt, dtype, device,
                   max_events=300000):
    """No-grad burn-in for the whole batch.

    Cells are right-aligned (events padded at the front with dt=0, which is the
    identity step) so one batched call produces every window start state.  The
    batch is split into chunks when the padded work would exceed max_events.
    """
    B = batch.batch_size
    data = batch.data
    max_len = int(batch.burn_length.max())
    if max_len == 0:
        m, P = model.initial_state(B, device=device, dtype=dtype)
        return m, P
    order = sorted(range(B), key=lambda b: int(batch.burn_length[b]))
    chunks, cur = [], []
    for b in order:
        trial = cur + [b]
        L_trial = max(int(batch.burn_length[x]) for x in trial)
        if cur and len(trial) * L_trial > max_events:
            chunks.append(cur)
            cur = [b]
        else:
            cur = trial
    chunks.append(cur)
    ms, Ps = [], []
    with torch.no_grad():
        for chunk in chunks:
            n = len(chunk)
            L = max(int(batch.burn_length[b]) for b in chunk)
            kind = torch.zeros(n, L, dtype=torch.long)
            dt_ = torch.zeros(n, L, dtype=dtype)
            ctl = torch.zeros(n, L, CONTROL_DIM, dtype=dtype)
            msk = torch.zeros(n, L, CONTROL_DIM, dtype=dtype)
            y = torch.zeros(n, L, dtype=dtype)
            score = torch.zeros(n, L, dtype=torch.bool)
            q_ref = torch.zeros(n, dtype=dtype)
            for row, b in enumerate(chunk):
                i = int(batch.cell_index[b])
                st = int(batch.burn_start[b])
                ln = int(batch.burn_length[b])
                if ln:
                    off = L - ln
                    sl = data.slice_tensors(i, st, st + ln)
                    kind[row, off:] = sl["kind"][0]
                    dt_[row, off:] = sl["dt"][0].to(dtype)
                    ctl[row, off:] = sl["control"][0].to(dtype)
                    msk[row, off:] = sl["control_mask"][0].to(dtype)
                    y[row, off:] = sl["y"][0].to(dtype)
                    score[row, off:] = sl["score"][0]
                q_ref[row] = batch.q_ref[b].to(dtype)
            m, P = model.initial_state(n, device=device, dtype=dtype)
            m, P, _, _ = _run_events(
                model, kind.to(device), dt_.to(device), ctl.to(device),
                msk.to(device), y.to(device), score.to(device),
                q_ref.to(device), m, P, use_cycle=use_cycle,
                use_rpt=use_rpt, collect_nll=False)
            ms.append(m)
            Ps.append(P)
    return torch.cat(ms, dim=0), torch.cat(Ps, dim=0)


def replay_windows(model, batch, use_cycle=True, use_rpt=True,
                   return_states=False, state=None):
    """Windowed replay: no-grad burn-in, then scored window (grad enabled).

    Returns per-cell mean innovation NLL (cell-macro loss), per-cell NLL,
    scored counts, and (optionally) the window-start state and final state.
    """
    p = next(model.parameters())
    dtype, device = p.dtype, p.device
    if state is None:
        m0, P0 = _burn_in_state(model, batch, use_cycle, use_rpt, dtype, device)
    else:
        m0, P0 = state
    m0 = m0.detach()
    P0 = P0.detach()
    kind = batch.kind.to(device=device)
    dt = batch.dt.to(device=device, dtype=dtype)
    control = batch.control.to(device=device, dtype=dtype)
    mask = batch.control_mask.to(device=device, dtype=dtype)
    y = batch.y.to(device=device, dtype=dtype)
    score = batch.score.to(device=device)
    q_ref = batch.q_ref.to(device=device, dtype=dtype)
    m, P, nll_sum, n_scored = _run_events(
        model, kind, dt, control, mask, y, score, q_ref, m0, P0,
        use_cycle=use_cycle, use_rpt=use_rpt, collect_nll=True)
    has = n_scored > 0
    per_cell = torch.where(has, nll_sum / n_scored.clamp_min(1).to(dtype),
                           torch.zeros_like(nll_sum))
    loss = per_cell[has].mean() if bool(has.any()) else nll_sum.sum() * 0.0
    out = {
        "loss_cell_macro": loss,
        "per_cell_nll": per_cell,
        "n_scored": n_scored,
        "final_state_mean": m,
        "final_state_cov": P,
    }
    if return_states:
        out["window_start_mean"] = m0
        out["window_start_cov"] = P0
    return out


def _chunk_by_length(data, cells, max_events=400000, max_batch=8):
    cells = [int(c) for c in cells]
    cells.sort(key=lambda i: int(data.counts[i]))
    chunks, cur = [], []
    for i in cells:
        trial = cur + [i]
        T = int(data.counts[trial].max())
        if cur and (len(trial) > max_batch or T * len(trial) > max_events):
            chunks.append(cur)
            cur = [i]
        else:
            cur = trial
    if cur:
        chunks.append(cur)
    return chunks


def replay_cells(model, data, cells, use_cycle=True, use_rpt=True):
    """Exact full-sequence cell replay (used for validation / equivalence).

    Returns {cell_index: per-cell mean NLL} with the same arithmetic as
    a2_targets.replay_batch (verified to 1e-9 in float64 by the fixtures).
    """
    p = next(model.parameters())
    dtype, device = p.dtype, p.device
    result = {}
    for chunk in _chunk_by_length(data, cells):
        B = len(chunk)
        T = max(int(data.counts[i]) for i in chunk)
        dt_ = data.dtype
        kind = torch.zeros(B, T, dtype=torch.long)
        dt = torch.zeros(B, T, dtype=dt_)
        control = torch.zeros(B, T, CONTROL_DIM, dtype=dt_)
        mask = torch.zeros(B, T, CONTROL_DIM, dtype=dt_)
        y = torch.zeros(B, T, dtype=dt_)
        score = torch.zeros(B, T, dtype=torch.bool)
        q_ref = torch.zeros(B, dtype=dt_)
        for b, i in enumerate(chunk):
            a, e = int(data.offsets[i]), int(data.offsets[i + 1])
            n = e - a
            kind[b, :n] = data.kind[a:e]
            dt[b, :n] = data.dt[a:e]
            control[b, :n] = data.control[a:e]
            mask[b, :n] = data.control_mask[a:e]
            y[b, :n] = data.y[a:e]
            score[b, :n] = data.score[a:e]
            q_ref[b] = data.q_ref[i]
        m_init, P_init = model.initial_state(B, device=device, dtype=dtype)
        m, P, nll_sum, n_scored = _run_events(
            model, kind.to(device), dt.to(device=device, dtype=dtype),
            control.to(device=device, dtype=dtype),
            mask.to(device=device, dtype=dtype),
            y.to(device=device, dtype=dtype), score.to(device),
            q_ref.to(device=device, dtype=dtype),
            m_init, P_init, use_cycle=use_cycle, use_rpt=use_rpt,
            collect_nll=True)
        per = torch.where(n_scored > 0,
                          nll_sum / n_scored.clamp_min(1).to(dtype),
                          torch.zeros_like(nll_sum))
        for b, i in enumerate(chunk):
            result[int(i)] = float(per[b])
    return result


def eval_cell_macro(model, data, cells, use_cycle=True, use_rpt=True):
    """Cell-macro mean NLL over full sequences (cells with >=1 scored RPT)."""
    per = replay_cells(model, data, cells, use_cycle=use_cycle, use_rpt=use_rpt)
    vals = list(per.values())
    if not vals:
        return float("nan"), per
    return float(sum(vals) / len(vals)), per


# ---------------------------------------------------------------- synthetic
def synthetic_fast_data(n_cells=16, n_events=1500, rpt_every=110, seed=0,
                        q_ref=0.28):
    """Synthetic FastA2Data with realistic event counts (no data access)."""
    rng = np.random.RandomState(seed)
    cells, offsets = [], [0]
    kinds, dts, ctl, msk, ys, sc, qref, anchor = [], [], [], [], [], [], [], []
    for i in range(n_cells):
        n = int(n_events * (0.6 + 0.8 * rng.rand()))
        n = max(n, 64)
        events = 0
        n_rpt = 0
        for k in range(n):
            dt = float(rng.uniform(0.05, 0.2))
            if k > 0 and k % rpt_every == 0:
                kinds.append(2)
                ctl.append([0.0] * CONTROL_DIM)
                msk.append([0.0] * CONTROL_DIM)
                n_rpt += 1
                ys.append(float(q_ref - 0.002 * n_rpt
                                + rng.normal(0, 2e-3)))
                sc.append(True)
                dts.append(dt)
                events += 1
            kinds.append(1)
            c = rng.normal(0, 1, CONTROL_DIM)
            m = (rng.rand(CONTROL_DIM) > 0.15).astype(np.float64)
            ctl.append((c * m).tolist())
            msk.append(m.tolist())
            ys.append(0.0)
            sc.append(False)
            dts.append(dt)
            events += 1
        offsets.append(offsets[-1] + events)
        cells.append("syn_%03d" % i)
        qref.append(q_ref)
        anchor.append(1_700_000_000.0)
    return FastA2Data(cells, np.asarray(offsets, dtype=np.int64),
                      np.asarray(kinds, dtype=np.int8),
                      np.asarray(dts, dtype=np.float32),
                      np.asarray(ctl, dtype=np.float32).reshape(-1, CONTROL_DIM),
                      np.asarray(msk, dtype=np.float32).reshape(-1, CONTROL_DIM),
                      np.asarray(ys, dtype=np.float32),
                      np.asarray(sc, dtype=bool),
                      np.asarray(qref, dtype=np.float64),
                      anchor_source_epoch=np.asarray(anchor, dtype=np.float64))


def synthetic_sequences_for_windows(n_cells=3, n_cycles=420, seed=0):
    """Long synthetic cell sequences (a2_targets format) for equivalence tests."""
    import random
    seqs = []
    for c in range(n_cells):
        rng = random.Random(seed + 1000 * c)
        q_ref = 0.28
        origin = 1_700_000_000.0
        events = []
        t = origin
        rpt_at = set(rng.sample(range(5, n_cycles - 1), max(3, n_cycles // 60)))
        n_rpt = 0
        for i in range(n_cycles):
            t += rng.uniform(0.15, 0.5) * WEEK_SECONDS
            ctl = [rng.gauss(0.0, 1.0) for _ in range(CONTROL_DIM)]
            mask = [1.0 if rng.random() > 0.15 else 0.0
                    for _ in range(CONTROL_DIM)]
            events.append({"kind": "cycle", "index": i, "source_epoch": t,
                           "available_epoch": t + 60.0, "control": ctl,
                           "control_mask": mask, "dt_weeks": 0.0})
            if i in rpt_at:
                n_rpt += 1
                y = q_ref - 0.004 * n_rpt + rng.gauss(0.0, 0.0015)
                tr = t + 3600.0
                events.append({"kind": "rpt", "index": i, "source_epoch": tr,
                               "available_epoch": tr + 120.0,
                               "capacity_ah": y, "score": True,
                               "dt_weeks": 0.0})
        prev = origin
        for e in events:
            e["dt_weeks"] = (e["source_epoch"] - prev) / WEEK_SECONDS
            prev = e["source_epoch"]
        seqs.append({"cell_id": "cell_%d" % c, "q_ref_ah": q_ref,
                     "anchor": {"index": 0, "capacity_ah": q_ref,
                                "source_epoch": origin,
                                "available_epoch": origin,
                                "n_valid_arrived": 1},
                     "events": events})
    return seqs


# --------------------------------------------------------------------- bench
def _rss_mb():
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except Exception:  # pragma: no cover - Windows fallback
        return float("nan")


def _set_threads(threads):
    if threads:
        torch.set_num_threads(int(threads))
    return int(torch.get_num_threads())


def bench_synthetic(batch_cells=8, window_events=256, burn_in_events=128,
                    steps=15, warmup=3, seed=42, threads=None):
    """Time one synthetic 'training step' (forward + backward, 0 optimizer steps)."""
    from a2_model import build_model
    out_threads = _set_threads(threads)
    torch.manual_seed(seed)
    data = synthetic_fast_data(n_cells=24, n_events=2200, seed=3)
    model = build_model(seed=seed)
    sampler = WindowSampler(data, np.arange(data.n_cells), window_events,
                            burn_in="exact", batch_cells=batch_cells)
    out = {"data": data.summary(), "batch_cells": batch_cells,
           "window_events": window_events, "burn_in_events": burn_in_events,
           "torch_threads": out_threads, "modes": {}}
    import random
    for mode in ("exact", "last_w"):
        sampler.burn_in = mode
        sampler.burn_in_events = burn_in_events
        rng = random.Random(seed)
        batches = [sampler.sample(rng) for _ in range(max(2, steps + warmup))]
        times, parts = [], {"burn": [], "window": [], "backward": []}
        loss = None
        for k in range(steps + warmup):
            b = batches[k % len(batches)]
            torch.manual_seed(1234)
            t0 = time.perf_counter()
            p = next(model.parameters())
            st = _burn_in_state(model, b, True, True, p.dtype, p.device)
            t1 = time.perf_counter()
            out_w = replay_windows(model, b, use_cycle=True, use_rpt=True,
                                   state=st)
            loss = out_w["loss_cell_macro"]
            t2 = time.perf_counter()
            model.zero_grad(set_to_none=True)
            loss.backward()
            t3 = time.perf_counter()
            if k >= warmup:
                times.append((t3 - t0) * 1e3)
                parts["burn"].append((t1 - t0) * 1e3)
                parts["window"].append((t2 - t1) * 1e3)
                parts["backward"].append((t3 - t2) * 1e3)
        times.sort()
        out["modes"][mode] = {
            "steps": steps,
            "mean_ms": float(np.mean(times)),
            "median_ms": float(np.median(times)),
            "p90_ms": float(np.percentile(times, 90)),
            "min_ms": float(np.min(times)),
            "max_ms": float(np.max(times)),
            "burn_mean_ms": float(np.mean(parts["burn"])),
            "window_forward_mean_ms": float(np.mean(parts["window"])),
            "backward_mean_ms": float(np.mean(parts["backward"])),
            "loss": float(loss),
        }
    out["under_100ms"] = all(v["mean_ms"] < 100.0
                             for v in out["modes"].values())
    out["rss_mb_after"] = _rss_mb()
    return out


def bench_npz(manifest_path, batch_cells=8, window_events=256,
              burn_in_events=128, steps=10, warmup=2, seed=42, threads=None):
    """Time the real prepared npz (PREP output only; no payload, no training)."""
    from a2_model import build_model
    out_threads = _set_threads(threads)
    out = {"torch_threads": out_threads}
    t0 = time.perf_counter()
    data = load_prepared_fast(manifest_path)
    out["load_seconds"] = time.perf_counter() - t0
    out["data"] = data.summary()
    out["load_rss_mb"] = _rss_mb()
    out["manifest"] = {
        "path": os.path.abspath(manifest_path),
        "sha256": getattr(data, "manifest_sha256", None),
        "npz_path": data.npz_path,
        "npz_sha256": data.npz_sha256,
    }
    t1 = time.perf_counter()
    std = fit_control_standardizer(data, data.train_index)
    out["standardizer_seconds"] = time.perf_counter() - t1
    out["standardizer"] = {
        "n_constant_scale_one_skipped": std["n_constant_scale_one_skipped"],
        "mean": [float(v) for v in std["mean"]],
        "scale": [float(v) for v in std["scale"]],
    }
    torch.manual_seed(seed)
    model = build_model(seed=seed)
    model.set_control_standardizer(std["mean"], std["scale"])
    import random
    out["modes"] = {}
    for mode in ("exact", "last_w"):
        sampler = WindowSampler(data, data.train_index, window_events,
                                burn_in=mode, burn_in_events=burn_in_events,
                                batch_cells=batch_cells)
        rng = random.Random(seed)
        batches = [sampler.sample(rng) for _ in range(steps + warmup)]
        times = []
        loss = None
        for k in range(steps + warmup):
            b = batches[k % len(batches)]
            t0 = time.perf_counter()
            o = replay_windows(model, b, use_cycle=True, use_rpt=True)
            loss = o["loss_cell_macro"]
            loss.backward()
            model.zero_grad(set_to_none=True)
            t1 = time.perf_counter()
            if k >= warmup:
                times.append((t1 - t0) * 1e3)
        times.sort()
        out["modes"][mode] = {
            "steps": steps, "mean_ms": float(np.mean(times)),
            "median_ms": float(np.median(times)),
            "p90_ms": float(np.percentile(times, 90)),
            "min_ms": float(np.min(times)), "max_ms": float(np.max(times)),
            "burn_length_mean": float(np.mean(
                [int(b.burn_length.max()) for b in batches])),
            "loss": float(loss),
        }
    out["rss_mb_after"] = _rss_mb()
    return out


def _main(argv=None):
    ap = argparse.ArgumentParser(
        description="a2_fastdata bench (synthetic by default)")
    ap.add_argument("--bench", action="store_true")
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--batch-cells", type=int, default=8)
    ap.add_argument("--window-events", type=int, default=256)
    ap.add_argument("--burn-in-events", type=int, default=128)
    ap.add_argument("--steps", type=int, default=15)
    ap.add_argument("--threads", type=int, default=min(8, os.cpu_count() or 8))
    args = ap.parse_args(argv)
    if not args.bench:
        ap.print_help()
        return 0
    if args.manifest:
        res = bench_npz(args.manifest, args.batch_cells, args.window_events,
                        args.burn_in_events, args.steps, threads=args.threads)
    else:
        res = bench_synthetic(args.batch_cells, args.window_events,
                              args.burn_in_events, args.steps,
                              threads=args.threads)
    print(json.dumps(res, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
