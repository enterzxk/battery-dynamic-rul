"""Synthetic-only fixtures for the FAST A2 path (a2_fastdata + windowed BPTT).

Every fixture uses fabricated records/tensors; no payload, no processed dataset,
no checkpoint, and no optimiser step (one backward pass in the gradient fixture).

The point of these fixtures is to prove that the fast path is not a new model:
  1. the vectorised npz loader reproduces the slow a2_train loader exactly;
  2. the block-scan replay reproduces a2_targets.replay_batch (1e-9, float64);
  3. a window loss equals the corresponding segment of the full replay (1e-9);
  4. the no-grad burn-in produces the full-sequence filtered state at the window
     start and carries no gradient;
  5. the literal W=128 truncation is NOT exact (measured, not hidden);
  6. cell split / standardisation, cell-macro loss, anchor exclusion, noRPTupdate
     semantics and sigma semantics are unchanged.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import tempfile

import numpy as np
import torch

from a2_fixtures import synthetic_sequences
from a2_model import CONTROL_DIM, build_model
from a2_targets import (
    A2SequenceBatch, TrainControlStandardizer, hash_file, replay_batch,
    split_cells_by_hash,
)
import a2_train
import a2_fastdata as fd

LOG_2PI = math.log(2.0 * math.pi)


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _close(a, b, atol=1e-9, rtol=0.0):
    return torch.allclose(torch.as_tensor(a, dtype=torch.float64),
                          torch.as_tensor(b, dtype=torch.float64),
                          atol=atol, rtol=rtol)


# --------------------------------------------------------------------- helpers
def _arrays_from_sequences(sequences):
    """Flat float32 arrays exactly like a2_prep._flatten (slow reference path)."""
    cell_ids, kinds, src, avail, dt, ctl, msk, cap, score = [], [], [], [], [], [], [], [], []
    counts = []
    for s in sequences:
        cell_ids.append(str(s["cell_id"]))
        for e in s["events"]:
            kind = 1 if e["kind"] == "cycle" else 2
            kinds.append(kind)
            src.append(0.0)
            avail.append(0.0)
            dt.append(float(e["dt_weeks"]))
            if kind == 1:
                ctl.append([float(v) for v in e["control"]])
                msk.append([float(v) for v in e["control_mask"]])
                cap.append(0.0)
                score.append(False)
            else:
                ctl.append([0.0] * CONTROL_DIM)
                msk.append([0.0] * CONTROL_DIM)
                cap.append(float(e["capacity_ah"]))
                score.append(bool(e.get("score", False)))
        counts.append(len(s["events"]))
    n_cells = len(cell_ids)
    event_cell = np.repeat(np.arange(n_cells, dtype=np.int64), counts)
    arrays = {
        "cell_ids": np.asarray(cell_ids, dtype=str),
        "q_ref_ah": np.asarray([float(s["q_ref_ah"]) for s in sequences]),
        "anchor_source_epoch": np.asarray(
            [float(s["anchor"]["source_epoch"]) for s in sequences]),
        "event_cell": event_cell,
        "event_kind": np.asarray(kinds, dtype=np.int8),
        "event_source": np.asarray(src, dtype=np.float64),
        "event_available": np.asarray(avail, dtype=np.float64),
        "event_dt_weeks": np.asarray(dt, dtype=np.float32),
        "control": np.asarray(ctl, dtype=np.float32).reshape(-1, CONTROL_DIM),
        "control_mask": np.asarray(msk, dtype=np.float32).reshape(-1, CONTROL_DIM),
        "capacity_ah": np.asarray(cap, dtype=np.float32),
        "score": np.asarray(score, dtype=bool),
    }
    return arrays


def _write_synthetic_prep(sequences, tmpdir, n_val=1):
    arrays = _arrays_from_sequences(sequences)
    npz_path = os.path.join(tmpdir, "a2_prep_sequences.npz")
    np.savez_compressed(npz_path, **arrays)
    ids = [str(c) for c in arrays["cell_ids"]]
    train, val = split_cells_by_hash(ids, n_val, seed=42)
    man = {
        "schema": "A2_PREP_V1",
        "prepared_npz": os.path.basename(npz_path),
        "prepared_npz_sha256": hash_file(npz_path),
        "split": {"train_cells": train, "val_cells": val, "n_val": n_val,
                  "seed": 42},
    }
    man_path = os.path.join(tmpdir, "manifest.json")
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(man, f)
    return man_path, man


def _per_event_nll(ref):
    var = ref["innovation_var_ah2"]
    return 0.5 * (ref["innovation_ah"].square() / var
                  + torch.log(var) + LOG_2PI)


def _sequential_state_at(model, seq, upto, use_rpt=True):
    """Reference full-sequence filter state after events [0, upto) (float64)."""
    m = model.prior_mean.double()[None]
    P = model.prior_cov.double()[None]
    zero = torch.zeros(1, CONTROL_DIM, dtype=torch.float64)
    q_ref = torch.tensor([seq["q_ref_ah"]], dtype=torch.float64)
    for e in seq["events"][:upto]:
        dt = torch.tensor([e["dt_weeks"]], dtype=torch.float64)
        if e["kind"] == "cycle":
            ctl = torch.as_tensor([e["control"]], dtype=torch.float64)
            msk = torch.as_tensor([e["control_mask"]], dtype=torch.float64)
            m, P, _ = model.advance(m, P, dt, ctl, msk)
        else:
            m, P, _ = model.advance(m, P, dt, zero, zero)
            if use_rpt and e.get("score", False):
                m, P, _, _ = model.correct_rpt(m, P, q_ref,
                                               [e["capacity_ah"]])
    return m[0], P[0]


# --------------------------------------------------------------------- fixtures
def test_fast_loader_matches_slow():
    """Vectorised npz loader == a2_train.load_prepared_sequences."""
    seqs = synthetic_sequences(5, seed=31)
    tmpdir = tempfile.mkdtemp(prefix="a2_fast_loader_")
    try:
        man_path, man = _write_synthetic_prep(seqs, tmpdir, n_val=2)
        fast = fd.load_prepared_fast(man_path)
        slow_train, slow_val, slow_man = a2_train.load_prepared_sequences(man_path)
        _assert([fast.cell_ids[int(i)] for i in fast.train_index]
                == slow_man["split"]["train_cells"],
                "train split differs from the manifest")
        _assert([fast.cell_ids[int(i)] for i in fast.val_index]
                == slow_man["split"]["val_cells"],
                "val split differs from the manifest")
        _assert(fast.n_events == sum(len(s["events"]) for s in seqs),
                "event count differs")
        for cid in fast.cell_ids:
            i = fast.cell_index(cid)
            slow = slow_train[0] if cid == slow_train[0]["cell_id"] else None
            for s in slow_train + slow_val:
                if s["cell_id"] == cid:
                    slow = s
                    break
            events = slow["events"]
            a, b = int(fast.offsets[i]), int(fast.offsets[i + 1])
            _assert(b - a == len(events), "event count differs for %s" % cid)
            _assert(abs(float(fast.q_ref[i]) - slow["q_ref_ah"]) < 1e-12,
                    "Q_ref differs for %s" % cid)
            for t, e in enumerate(events):
                _assert(int(fast.kind[a + t]) == (1 if e["kind"] == "cycle" else 2),
                        "event kind differs")
                _assert(abs(float(fast.dt[a + t]) - float(e["dt_weeks"])) < 1e-12,
                        "dt differs")
                if e["kind"] == "cycle":
                    _assert(_close(fast.control[a + t],
                                   torch.tensor(e["control"], dtype=torch.float64),
                                   atol=0.0), "control differs")
                    _assert(_close(fast.control_mask[a + t],
                                   torch.tensor(e["control_mask"],
                                                dtype=torch.float64),
                                   atol=0.0), "control mask differs")
                else:
                    _assert(abs(float(fast.y[a + t]) - e["capacity_ah"]) < 1e-12,
                            "capacity differs")
                    _assert(bool(fast.score[a + t]) == bool(e["score"]),
                            "score flag differs")
        # standardiser equivalence (train-only, ddof=0, constant handling)
        slow_std = TrainControlStandardizer().fit(slow_train)
        fast_std = fd.fit_control_standardizer(fast, fast.train_index)
        _assert(_close(slow_std.mean, fast_std["mean"], atol=1e-12),
                "standardiser mean differs")
        _assert(_close(slow_std.scale, fast_std["scale"], atol=1e-12),
                "standardiser scale differs")
        _assert(slow_std.n_constant_skipped
                == fast_std["n_constant_scale_one_skipped"],
                "constant-scale count differs")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return "npz loader bit-identical to slow loader; split+standardiser identical"


def test_scan_matches_sequential_advance():
    """Closed-form block propagation == model.advance (1e-12, float64)."""
    model = build_model(seed=3).double()
    g = torch.Generator().manual_seed(11)
    B, T = 4, 37
    kind = torch.ones(B, T, dtype=torch.long)
    kind[:, -3:] = 2
    dt = torch.rand(B, T, generator=g, dtype=torch.float64) * 0.5
    ctl = torch.randn(B, T, CONTROL_DIM, generator=g, dtype=torch.float64)
    msk = (torch.rand(B, T, CONTROL_DIM, generator=g, dtype=torch.float64) > 0.2)
    m = torch.randn(B, 2, generator=g, dtype=torch.float64) * 0.1
    P = torch.eye(2, dtype=torch.float64)[None].repeat(B, 1, 1) * 1e-3
    m_ref, P_ref = m.clone(), P.clone()
    for t in range(T):
        c = ctl[:, t] if int(kind[0, t]) == 1 else torch.zeros(B, CONTROL_DIM,
                                                               dtype=torch.float64)
        k = msk[:, t] if int(kind[0, t]) == 1 else torch.zeros(B, CONTROL_DIM,
                                                               dtype=torch.float64)
        m_ref, P_ref, _ = model.advance(m_ref, P_ref, dt[:, t], c, k)
    scal = fd._event_scalars(model, kind, dt, ctl, msk, True)
    m2, P2 = m.clone(), P.clone()
    for a, b in ((0, 1), (1, 5), (5, 20), (20, T)):
        m2, P2 = fd._block_state(m2, P2, scal, a, b)
    _assert(_close(m2, m_ref, atol=1e-12), "block mean differs from sequential")
    _assert(_close(P2, P_ref, atol=1e-12), "block covariance differs")
    # force the associative-scan fallback with strongly decaying steps
    dt_big = torch.full((B, T), 40.0, dtype=torch.float64)
    scal_big = fd._event_scalars(model, kind, dt_big, ctl, msk, True)
    _assert(float(scal_big["alpha"].prod(dim=1).min()) < 1e-30,
            "test did not force the scan fallback")
    m3, P3 = fd._block_state(m.clone(), P.clone(), scal_big, 0, T)
    m4, P4 = m.clone(), P.clone()
    for t in range(T):
        c = ctl[:, t] if int(kind[0, t]) == 1 else torch.zeros(
            B, CONTROL_DIM, dtype=torch.float64)
        k = msk[:, t] if int(kind[0, t]) == 1 else torch.zeros(
            B, CONTROL_DIM, dtype=torch.float64)
        m4, P4, _ = model.advance(m4, P4, dt_big[:, t], c, k)
    _assert(_close(m3, m4, atol=1e-12), "scan fallback mean differs")
    _assert(_close(P3, P4, atol=1e-12), "scan fallback covariance differs")
    return "closed-form block == sequential advance (and scan fallback)"


def test_fast_replay_matches_full_cells():
    """replay_cells == replay_batch per-cell NLL for all four flag combos."""
    model = build_model(seed=9).double()
    seqs = fd.synthetic_sequences_for_windows(n_cells=3, n_cycles=300, seed=21)
    data = fd.FastA2Data.from_sequences(seqs)
    batch = A2SequenceBatch.from_sequences(seqs, dtype=torch.float64)
    worst = 0.0
    for use_cycle in (True, False):
        for use_rpt in (True, False):
            ref = replay_batch(model, batch, use_cycle=use_cycle,
                               use_rpt=use_rpt)
            got = fd.replay_cells(model, data, list(range(3)),
                                  use_cycle=use_cycle, use_rpt=use_rpt)
            for i in range(3):
                diff = abs(float(ref["per_cell_nll"][i]) - got[i])
                worst = max(worst, diff)
                _assert(diff < 1e-9, "per-cell NLL differs (%.3e)" % diff)
    return "full-cell fast replay == replay_batch (worst %.2e)" % worst


def test_window_loss_equals_full_replay():
    """Window loss == the same segment of the full replay at 1e-9."""
    model = build_model(seed=9).double()
    seqs = fd.synthetic_sequences_for_windows(n_cells=3, n_cycles=420, seed=20)
    data = fd.FastA2Data.from_sequences(seqs)
    batch = A2SequenceBatch.from_sequences(seqs, dtype=torch.float64)
    ref = replay_batch(model, batch)
    nll = _per_event_nll(ref)
    worst = 0.0
    cases = [(0, 100), (37, 256), (150, 256), (300, 100)]
    for start, L in cases:
        for ci in range(3):
            b = fd.WindowBatch(data, [ci], [start], L, burn_in="exact")
            out = fd.replay_windows(model, b)
            hit = torch.zeros(batch.kind.shape[1], dtype=torch.bool)
            hit[start:start + L] = True
            hit = hit & (batch.kind[ci] == 2) & batch.score[ci]
            if not bool(hit.any()):
                continue
            seg = float(nll[ci][hit].mean())
            got = float(out["per_cell_nll"][0])
            worst = max(worst, abs(got - seg))
            _assert(abs(got - seg) < 1e-9,
                    "window loss != full segment (start=%d L=%d cell=%d: "
                    "%.3e vs %.3e)" % (start, L, ci, got, seg))
            _assert(int(out["n_scored"][0]) == int(hit.sum()),
                    "scored count differs from the full segment")
    # arms: time-only (control masked) and noRPTupdate still match the segment
    for use_cycle, use_rpt in ((False, True), (True, False)):
        ref2 = replay_batch(model, batch, use_cycle=use_cycle, use_rpt=use_rpt)
        nll2 = _per_event_nll(ref2)
        b = fd.WindowBatch(data, [0], [150], 256, burn_in="exact")
        out = fd.replay_windows(model, b, use_cycle=use_cycle, use_rpt=use_rpt)
        hit = torch.zeros(batch.kind.shape[1], dtype=torch.bool)
        hit[150:406] = True
        hit = hit & (batch.kind[0] == 2) & batch.score[0]
        seg = float(nll2[0][hit].mean())
        _assert(abs(float(out["per_cell_nll"][0]) - seg) < 1e-9,
                "arm cycle=%s rpt=%s window != full segment" % (use_cycle,
                                                               use_rpt))
    return "4 window placements x 3 arms match full replay (worst %.2e)" % worst


def test_burnin_nograd_and_exact_start():
    """Burn-in state == full-prefix filtered state; no gradient path."""
    model = build_model(seed=9).double()
    seqs = fd.synthetic_sequences_for_windows(n_cells=2, n_cycles=420, seed=22)
    data = fd.FastA2Data.from_sequences(seqs)
    start = 250
    b = fd.WindowBatch(data, [0], [start], 120, burn_in="exact")
    out = fd.replay_windows(model, b, return_states=True)
    _assert(int(b.burn_length[0]) == start, "exact burn-in must cover the prefix")
    m_ref, P_ref = _sequential_state_at(model, seqs[0], start)
    m_got = out["window_start_mean"][0]
    P_got = out["window_start_cov"][0]
    _assert(_close(m_got, m_ref, atol=1e-9), "burn-in mean != full filter state")
    _assert(_close(P_got, P_ref, atol=1e-9), "burn-in cov != full filter state")
    _assert(m_got.requires_grad is False and P_got.requires_grad is False,
            "window start state must be detached")
    _assert(m_got.grad_fn is None and P_got.grad_fn is None,
            "window start state must have no grad_fn")
    # same numbers when the burn-in runs with grad enabled (then detached)
    with torch.enable_grad():
        m2, P2 = fd._burn_in_state(model, b, True, True, torch.float64,
                                   torch.device("cpu"))
    _assert(m2.grad_fn is None and P2.grad_fn is None,
            "burn-in must be inside no_grad")
    _assert(_close(m2, m_got, atol=0.0), "burn-in value depends on grad mode")
    # gradients only flow through the window, not through the burn-in prefix
    out["loss_cell_macro"].backward()
    g = model.rates[0].weight.grad
    _assert(g is not None and bool(torch.isfinite(g).all())
            and float(g.abs().sum()) > 0, "no gradient through the window")
    return "burn-in == full filter at window start; detached; grads flow"


def test_truncated_burnin_gap_is_real():
    """Diagnostic: literal W=128 truncation is not equal to the full filter."""
    model = build_model(seed=9).double()
    seqs = fd.synthetic_sequences_for_windows(n_cells=1, n_cycles=420, seed=23)
    data = fd.FastA2Data.from_sequences(seqs)
    start, L = 300, 120
    exact = fd.replay_windows(
        model, fd.WindowBatch(data, [0], [start], L, burn_in="exact"))
    trunc = fd.replay_windows(
        model, fd.WindowBatch(data, [0], [start], L, burn_in="last_w",
                              burn_in_events=128))
    gap = abs(float(exact["per_cell_nll"][0]) - float(trunc["per_cell_nll"][0]))
    _assert(gap > 1e-6,
            "W=128 truncation should differ from the exact prefix (gap %.3e); "
            "if this ever becomes zero the model lost its D drift" % gap)
    _assert(int(trunc["n_scored"][0]) == int(exact["n_scored"][0]),
            "both modes must score the same RPTs")
    return ("W=128 truncation changes the window loss by %.3e nats "
            "(D drift does not forget); exact mode is the default" % gap)


def test_cell_macro_and_anchor_exclusion():
    """Cell-macro mean, no anchor scoring, per-cell normalisation."""
    model = build_model(seed=9).double()
    seqs = fd.synthetic_sequences_for_windows(n_cells=4, n_cycles=260, seed=24)
    data = fd.FastA2Data.from_sequences(seqs)
    starts = [10, 40, 90, 130]
    b = fd.WindowBatch(data, [0, 1, 2, 3], starts, 128, burn_in="exact")
    out = fd.replay_windows(model, b)
    per = out["per_cell_nll"].detach()
    manual = per.mean()
    _assert(abs(float(out["loss_cell_macro"]) - float(manual)) < 1e-12,
            "loss is not the cell-macro mean of per-cell NLL")
    _assert(bool((out["n_scored"] > 0).all()), "window scored no RPT")
    # the anchor reading is not an event, so it can never be scored: every
    # scored position in the window must be an RPT with score=True
    for row in range(4):
        a, e = int(data.offsets[row]), int(data.offsets[row + 1])
        _assert(int(data.score[a:e].sum()) >= int(out["n_scored"][row]),
                "more scored innovations than scored RPT events")
    # per-cell normalisation: each cell contributes one mean, not a sum
    n = out["n_scored"].to(torch.float64)
    weighted = float((per * n).sum() / n.sum())
    _assert(abs(weighted - float(per.mean())) > 1e-9 or len(set(n.tolist())) == 1,
            "cell-macro and global-pooling must be distinguishable")
    return "cell-macro mean verified; only scored post-anchor RPTs contribute"


def test_noRPT_arm_predicts_without_updating():
    """noRPTupdate scores every RPT but never applies the correction."""
    model = build_model(seed=13).double()
    seqs = fd.synthetic_sequences_for_windows(n_cells=3, n_cycles=320, seed=25)
    data = fd.FastA2Data.from_sequences(seqs)
    b = fd.WindowBatch(data, [0, 1, 2], [120, 140, 160], 200, burn_in="exact")
    full = fd.replay_windows(model, b, use_cycle=True, use_rpt=True)
    no = fd.replay_windows(model, b, use_cycle=True, use_rpt=False)
    _assert(torch.equal(no["n_scored"], full["n_scored"]),
            "noRPT arm must still score every RPT")
    _assert(float(no["loss_cell_macro"]) != float(full["loss_cell_macro"]),
            "noRPT arm must not silently equal full")
    # manual prediction-only replay of the same window
    for row in range(3):
        i = int(b.cell_index[row])
        a = int(b.start[row])
        L = int(b.lengths[row])
        seq = seqs[i]
        m, P = _sequential_state_at(model, seq, a, use_rpt=False)
        m = m[None]
        P = P[None]
        q_ref = torch.tensor([seq["q_ref_ah"]], dtype=torch.float64)
        nll, n = 0.0, 0
        zero = torch.zeros(1, CONTROL_DIM, dtype=torch.float64)
        for t in range(L):
            e = seq["events"][a + t]
            dt = torch.tensor([e["dt_weeks"]], dtype=torch.float64)
            if e["kind"] == "cycle":
                ctl = torch.as_tensor([e["control"]], dtype=torch.float64)
                msk = torch.as_tensor([e["control_mask"]], dtype=torch.float64)
                m, P, _ = model.advance(m, P, dt, ctl, msk)
            else:
                m, P, _ = model.advance(m, P, dt, zero, zero)
                nll += float(model.nll_rpt(m, P, q_ref, [e["capacity_ah"]]))
                n += 1
        ref = nll / max(1, n)
        _assert(abs(ref - float(no["per_cell_nll"][row])) < 1e-9,
                "noRPT window NLL != manual prediction-only loop")
    return "noRPT scores every RPT, never corrects (matches manual loop)"


def test_sigma_and_fast_update_semantics():
    """sigma is a std; the fused Joseph update equals model.correct_rpt."""
    model = build_model(seed=3).double()
    sigma = float(model.obs_sigma())
    var = float(model.obs_variance())
    _assert(abs(var - sigma ** 2) < 1e-18, "obs variance != sigma**2")
    _assert(0.9e-3 <= sigma <= 1.1e-2, "obs sigma outside the Ah band")
    g = torch.Generator().manual_seed(5)
    m = torch.randn(7, 2, generator=g, dtype=torch.float64) * 0.05
    A = torch.randn(7, 2, 2, generator=g, dtype=torch.float64)
    P = A @ A.transpose(-1, -2) * 1e-4 + torch.eye(2) * 1e-8
    q_ref = torch.full((7,), 0.28, dtype=torch.float64)
    y = torch.full((7,), 0.272, dtype=torch.float64)
    m_ref, P_ref, nll_ref, diag = model.correct_rpt(m, P, q_ref, y)
    m_fast, P_fast = fd._rpt_correct_fast(model, m, P, q_ref, y)
    _assert(_close(m_fast, m_ref, atol=1e-12), "fused update mean differs")
    _assert(_close(P_fast, P_ref, atol=1e-14), "fused update covariance differs")
    mu, latent, S, _ = model.capacity_moments(m, P, q_ref)
    manual = 0.5 * ((y - mu).square() / S + torch.log(S) + LOG_2PI)
    _assert(_close(manual, nll_ref, atol=1e-12), "NLL is not sigma-form")
    return "sigma=%.3g Ah, sigma^2=%.3g Ah^2; fused update == correct_rpt" % (
        sigma, var)


def test_standardizer_train_only_no_regression():
    """Constant columns -> scale 1; val outliers excluded (same rule)."""
    seqs = fd.synthetic_sequences_for_windows(n_cells=4, n_cycles=80, seed=26)
    train = seqs[:3]
    val = seqs[3:]
    for s in train:
        for e in s["events"]:
            if e["kind"] == "cycle":
                e["control"][0] = 7.0
                e["control_mask"] = [1.0, 1.0] + [0.0] * (CONTROL_DIM - 2)
    for e in val[0]["events"]:
        if e["kind"] == "cycle":
            e["control"][0] = 7.0
            e["control"][1] = 1e6
            e["control_mask"] = [1.0, 1.0] + [0.0] * (CONTROL_DIM - 2)
    data = fd.FastA2Data.from_sequences(seqs)
    std = fd.fit_control_standardizer(data, [0, 1, 2])
    _assert(float(std["scale"][0]) == 1.0, "constant column must use scale 1")
    _assert(abs(float(std["mean"][0]) - 7.0) < 1e-12, "constant mean wrong")
    _assert(std["n_constant_scale_one_skipped"] == CONTROL_DIM - 1,
            "expected %d skipped dims" % (CONTROL_DIM - 1))
    _assert(abs(float(std["scale"][1]) - 1.0) > 1e-6,
            "varying column should not be constant")
    vals = torch.tensor([e["control"][1] for s in train for e in s["events"]
                         if e["kind"] == "cycle"], dtype=torch.float64)
    _assert(abs(float(std["scale"][1]) - float(vals.std(unbiased=False))) < 1e-9,
            "scale must be the train-only population std")
    model = build_model(seed=5).double()
    model.set_control_standardizer(std["mean"], std["scale"])
    x = torch.tensor([7.0] + [0.0] * (CONTROL_DIM - 1), dtype=torch.float64)
    _assert(abs(float(model.standardize_control(x)[0])) < 1e-12,
            "constant feature is not centred")
    return "train-only stats; constant scale=1; val outlier ignored"


def test_window_batch_shapes_and_padding():
    """Padding is the identity step; short cells are handled, never mis-indexed."""
    data = fd.synthetic_fast_data(n_cells=3, n_events=120, seed=8)
    short = int(np.argmin(data.counts))
    _assert(int(data.counts[short]) < 256, "test needs a short cell")
    b = fd.WindowBatch(data, [short], [0], 256, burn_in="exact")
    _assert(int(b.lengths[0]) == int(data.counts[short]), "window length wrong")
    model = build_model(seed=11).double()
    out = fd.replay_windows(model, b, return_states=True)
    _assert(bool(torch.isfinite(out["loss_cell_macro"])), "padded window NaN")
    # padded positions must be identity: replay the same window without padding
    L = int(b.lengths[0])
    b2 = fd.WindowBatch(data, [short], [0], L, burn_in="exact")
    out2 = fd.replay_windows(model, b2)
    _assert(abs(float(out["loss_cell_macro"])
                - float(out2["loss_cell_macro"])) < 1e-12,
            "padding changed the window loss")
    return "short cell padded with dt=0 identity steps; loss unchanged"


FIXTURES = [
    ("fast_loader_matches_slow", test_fast_loader_matches_slow),
    ("scan_matches_sequential_advance", test_scan_matches_sequential_advance),
    ("fast_replay_matches_full_cells", test_fast_replay_matches_full_cells),
    ("window_loss_equals_full_replay", test_window_loss_equals_full_replay),
    ("burnin_nograd_and_exact_start", test_burnin_nograd_and_exact_start),
    ("truncated_burnin_gap_is_real", test_truncated_burnin_gap_is_real),
    ("cell_macro_and_anchor_exclusion", test_cell_macro_and_anchor_exclusion),
    ("noRPT_arm_predicts_without_updating",
     test_noRPT_arm_predicts_without_updating),
    ("sigma_and_fast_update_semantics", test_sigma_and_fast_update_semantics),
    ("standardizer_train_only_no_regression",
     test_standardizer_train_only_no_regression),
    ("window_batch_shapes_and_padding", test_window_batch_shapes_and_padding),
]


def run_all_fast(verbose=True):
    import traceback
    results = []
    for name, fn in FIXTURES:
        try:
            detail = fn()
            results.append({"name": name, "passed": True, "detail": detail})
            if verbose:
                print("[PASS] %-36s %s" % (name, detail))
        except Exception as exc:  # noqa: BLE001 - harness reports every fixture
            results.append({"name": name, "passed": False, "detail": str(exc)})
            if verbose:
                print("[FAIL] %-36s %s" % (name, exc))
                traceback.print_exc()
    n_pass = sum(1 for r in results if r["passed"])
    if verbose:
        print("SUMMARY: %d passed, %d failed, %d total" %
              (n_pass, len(results) - n_pass, len(results)))
    return {"results": results, "n_pass": n_pass,
            "n_fail": len(results) - n_pass}


if __name__ == "__main__":
    import sys
    res = run_all_fast(verbose=True)
    sys.exit(0 if res["n_fail"] == 0 else 1)
