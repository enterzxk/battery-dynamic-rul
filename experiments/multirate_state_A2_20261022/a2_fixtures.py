"""Synthetic-only unit fixtures for the A2 prototype.

Every fixture uses small random tensors / fabricated records; nothing here reads
research payload, processed datasets, checkpoints or saved predictions, and no
optimiser step is taken (one backward pass in the gradient fixture only).
"""
from __future__ import annotations

import copy
import inspect
import math
import random
import traceback

import torch

from a2_model import build_model, CONTROL_DIM, THRESHOLD_AH
from a2_targets import (
    A2SequenceBatch, TrainControlStandardizer, build_cell_sequence,
    forecast_capacity, replay_asof, replay_batch, split_cells_by_hash,
)

LOG_2PI = math.log(2.0 * math.pi)


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _close(a, b, atol=1e-8, rtol=1e-7):
    return torch.allclose(torch.as_tensor(a, dtype=torch.float64),
                          torch.as_tensor(b, dtype=torch.float64),
                          atol=atol, rtol=rtol)


def _control(seed=0, dim=CONTROL_DIM):
    g = torch.Generator().manual_seed(seed)
    return torch.randn(dim, generator=g), torch.ones(dim)


def _psd(b=1, seed=0):
    g = torch.Generator().manual_seed(seed)
    A = torch.randn(b, 2, 2, generator=g)
    return A @ A.transpose(-1, -2) + 0.01 * torch.eye(2)


def synthetic_sequence(cell_id="cell_0", seed=0, n_cycles=8, n_rpt=3,
                       q_ref=0.28, origin=1_700_000_000.0):
    """Fabricate one anchored cell sequence (dt in weeks, events sorted)."""
    rng = random.Random(seed)
    events = []
    t = origin
    rpt_positions = set(rng.sample(range(1, n_cycles), min(n_rpt, n_cycles - 1)))
    for i in range(n_cycles):
        t += rng.uniform(0.25, 0.75) * 604800.0
        ctl = [rng.gauss(0.0, 1.0) for _ in range(CONTROL_DIM)]
        mask = [1.0 if rng.random() > 0.15 else 0.0 for _ in range(CONTROL_DIM)]
        events.append({
            "kind": "cycle", "index": i, "source_epoch": t,
            "available_epoch": t + 60.0, "control": ctl, "control_mask": mask,
            "dt_weeks": 0.0,
        })
        if i in rpt_positions:
            y = q_ref - 0.004 * (len([e for e in events if e["kind"] == "rpt"]) + 1)
            y += rng.gauss(0.0, 0.002)
            tr = t + 3600.0
            events.append({
                "kind": "rpt", "index": i, "source_epoch": tr,
                "available_epoch": tr + 120.0, "capacity_ah": y, "score": True,
                "dt_weeks": 0.0,
            })
    prev = origin
    for e in events:
        e["dt_weeks"] = (e["source_epoch"] - prev) / 604800.0
        prev = e["source_epoch"]
    return {
        "cell_id": cell_id, "q_ref_ah": q_ref,
        "anchor": {"index": 0, "capacity_ah": q_ref, "source_epoch": origin,
                   "available_epoch": origin, "n_valid_arrived": 1},
        "events": events, "n_cycle_used": n_cycles, "n_rpt_scored": len(rpt_positions),
        "n_cycle_pre_anchor_excluded": 0, "n_cycle_late_excluded": 0,
        "n_rpt_pre_anchor_excluded": 0, "n_rpt_late_excluded": 0,
        "n_rpt_future_excluded": 0, "assumed_cycle_arrival": 0,
    }


def synthetic_sequences(n=4, seed=0):
    return [synthetic_sequence("cell_%d" % i, seed=seed + i, n_cycles=6 + i % 3,
                               n_rpt=2 + i % 2) for i in range(n)]


# --------------------------------------------------------------------- fixtures
def test_dt_not_an_input():
    model = build_model(seed=1).double()
    _assert(model.rates[0].in_features == 2 * model.control_dim,
            "rate network must consume only [control, mask] (no dt column)")
    _assert("dt" not in inspect.signature(model.transition_parameters).parameters,
            "transition_parameters must not take dt")
    m, P = model.initial_state(1)
    m = m + torch.tensor([[0.13, 0.02]], dtype=torch.float64)
    ctl, msk = _control(3)
    ctl, msk = ctl.double()[None], msk.double()[None]
    m1, _, _ = model.advance(m, P, 0.5, ctl, msk)
    m2, _, _ = model.advance(m, P, 2.0, ctl, msk)
    d1 = (m1[0, 0] - m[0, 0]).item()
    d2 = (m2[0, 0] - m[0, 0]).item()
    _assert(abs(d2 - 4.0 * d1) < 1e-12, "D mean drift must be exactly linear in dt")
    return "no dt input (in_features=%d); D drift exactly linear in dt" % (2 * model.control_dim)


def test_grid_invariance():
    model = build_model(seed=2).double()
    m, P = model.initial_state(1)
    P = _psd(1, seed=7).double()
    ctl, msk = _control(4)
    ctl, msk = ctl.double()[None], msk.double()[None]
    m1, P1, _ = model.advance(m, P, 2.0, ctl, msk)
    m2, P2 = m.clone(), P.clone()
    for dt in (0.75, 0.75, 0.5):
        m2, P2, _ = model.advance(m2, P2, dt, ctl, msk)
    _assert(_close(m1, m2, atol=1e-12), "mean differs under re-gridding")
    _assert(_close(P1, P2, atol=1e-12, rtol=1e-10), "covariance differs under re-gridding")
    m3, P3 = m.clone(), P.clone()
    for _ in range(97):
        m3, P3, _ = model.advance(m3, P3, 2.0 / 97.0, ctl, msk)
    _assert(_close(m1, m3, atol=1e-10), "97-step mean differs")
    _assert(_close(P1, P3, atol=1e-10, rtol=1e-9), "97-step covariance differs")

    seq = synthetic_sequence(seed=5)
    q = seq["events"][-1]["source_epoch"]
    f1 = forecast_capacity(model, seq, q, horizon_weeks=3.0, grid_steps=1)
    f2 = forecast_capacity(model, seq, q, horizon_weeks=3.0, grid_steps=43)
    _assert(_close(f1["capacity_mean_ah"], f2["capacity_mean_ah"], atol=1e-10),
            "forecast mean not grid invariant")
    _assert(_close(f1["capacity_total_var_ah2"], f2["capacity_total_var_ah2"],
                   atol=1e-10, rtol=1e-9), "forecast variance not grid invariant")
    return "1-step == uneven 3-step == 97-step; forecast 1 vs 43 substeps"


def test_sigma_is_std_variance_is_square():
    """Controller-corrected semantics: network output is sigma in Ah."""
    model = build_model(seed=3).double()
    sigma = float(model.obs_sigma())
    var = float(model.obs_variance())
    _assert(0.9e-3 <= sigma <= 1.1e-2, "obs sigma %.4g Ah outside the 1e-3..1e-2 Ah band" % sigma)
    _assert(0.9e-6 <= var <= 1.1e-4, "obs variance %.4g Ah^2 outside 1e-6..1e-4 band" % var)
    _assert(abs(var - sigma ** 2) < 1e-18, "variance must equal sigma**2")
    _assert(abs(sigma - 2e-3) < 5e-4, "initial obs sigma should be ~2e-3 Ah, got %.4g" % sigma)
    # A1's mistake must be impossible here: 0.0025 is NOT our variance.
    _assert(abs(var - 0.0025) > 1e-4, "0.0025 must not be interpreted as a variance")
    _assert(abs(sigma - 0.0025) < 5e-3, "0.0025 sits in the sigma band, not the variance band")

    m, P = model.initial_state(1)
    q_ref, y = 0.28, 0.271
    mu, latent, S, _ = model.capacity_moments(m, P, [q_ref])
    total_sigma = math.sqrt(float(S))
    _assert(abs(float(S) - (float(latent) + var)) < 1e-15,
            "total variance must be latent + sigma**2")
    # sigma-form Gaussian NLL: 0.5*z^2 + log(sigma) + 0.5*log(2*pi)
    manual_sigma = 0.5 * ((y - float(mu)) / total_sigma) ** 2 + math.log(total_sigma) + 0.5 * LOG_2PI
    # variance-form Gaussian NLL: 0.5*(innov^2/S + log S) + 0.5*log(2*pi)
    manual_var = 0.5 * ((y - float(mu)) ** 2 / float(S) + math.log(float(S))) + 0.5 * LOG_2PI
    nll = float(model.nll_rpt(m, P, [q_ref], [y])[0])
    _assert(abs(nll - manual_sigma) < 1e-12, "NLL is not the sigma-form Gaussian NLL")
    _assert(abs(nll - manual_var) < 1e-12, "NLL is not the sigma^2-variance Gaussian NLL")

    # process noise: sigma -> variance rate sigma**2 exactly once
    ctl, msk = _control(9)
    m0, P0 = model.initial_state(1)
    _, P1, pr = model.advance(m0, P0, 1.0, ctl.double()[None], msk.double()[None])
    d_var_rate = float(pr["d_sigma_per_sqrt_week"][0]) ** 2
    _assert(abs(float(P1[0, 0, 0] - P0[0, 0, 0]) - d_var_rate) < 1e-12,
            "D variance increment must be sigma_d**2 * dt")

    _, _, _, diag = model.correct_rpt(m, P, [q_ref], [y])
    _assert("observation_sigma_ah" in diag and "observation_var_ah2" in diag,
            "diagnostics must report sigma and sigma^2 explicitly")
    _assert(abs(float(diag["observation_var_ah2"][0])
                - float(diag["observation_sigma_ah"][0]) ** 2) < 1e-18,
            "reported sigma^2 != reported variance")
    return "sigma=%.3g Ah, sigma^2=%.3g Ah^2; sigma-form NLL == variance-form NLL" % (sigma, var)


def test_qref_anchor():
    base = 1_700_000_000.0
    day = 86400.0
    rpts = [
        {"source_epoch": base + 1 * day, "available_epoch": base + 2 * day,
         "capacity_ah": 0.290, "valid": False},
        {"source_epoch": base + 10 * day, "available_epoch": base + 12 * day,
         "capacity_ah": 0.281, "valid": True},
        {"source_epoch": base + 20 * day, "available_epoch": base + 22 * day,
         "capacity_ah": 0.276, "valid": True},
        {"source_epoch": base + 5 * day, "available_epoch": base + 40 * day,
         "capacity_ah": 0.300, "valid": True},
    ]
    cycles = [
        {"source_epoch": base + 8 * day, "available_epoch": base + 8 * day,
         "control": [1.0] * CONTROL_DIM, "control_mask": [1.0] * CONTROL_DIM},
        {"source_epoch": base + 11 * day, "available_epoch": base + 11 * day,
         "control": [2.0] * CONTROL_DIM, "control_mask": [1.0] * CONTROL_DIM},
        {"source_epoch": base + 25 * day, "available_epoch": base + 25 * day,
         "control": [3.0] * CONTROL_DIM, "control_mask": [1.0] * CONTROL_DIM},
    ]
    cutoff = base + 30 * day
    seq = build_cell_sequence("c", cycles, rpts, cutoff_epoch=cutoff)
    _assert(seq["q_ref_ah"] == 0.281, "Q_ref must be the first ARRIVED valid RPT (.281)")
    _assert(seq["anchor"]["index"] == 1, "anchor index wrong")
    _assert(seq["n_cycle_pre_anchor_excluded"] == 1, "pre-anchor cycle must be excluded")
    _assert(seq["n_rpt_pre_anchor_excluded"] == 1, "late-arriving pre-anchor RPT excluded")
    _assert(seq["n_rpt_scored"] == 1, "only one post-anchor RPT is scored")
    _assert([e["kind"] for e in seq["events"]] == ["cycle", "rpt", "cycle"],
            "event order wrong: %r" % [e["kind"] for e in seq["events"]])
    _assert(abs(seq["events"][1]["capacity_ah"] - 0.276) < 1e-12, "scored RPT value wrong")

    mutated = copy.deepcopy(rpts)
    mutated[2]["capacity_ah"] = 0.20
    seq2 = build_cell_sequence("c", cycles, mutated, cutoff_epoch=cutoff)
    _assert(seq2["q_ref_ah"] == 0.281, "Q_ref must be anchored once")

    early = build_cell_sequence("c", cycles, rpts, cutoff_epoch=base + 11 * day)
    _assert(early["q_ref_ah"] is None, "no anchor before first arrival")
    _assert(early["events"] == [], "pre-anchor sequence must be empty")

    rpts2 = [
        {"source_epoch": base + 10 * day, "available_epoch": base + 20 * day,
         "capacity_ah": 0.281, "valid": True},
        {"source_epoch": base + 15 * day, "available_epoch": base + 16 * day,
         "capacity_ah": 0.272, "valid": True},
    ]
    seq3 = build_cell_sequence("c", cycles, rpts2, cutoff_epoch=base + 30 * day)
    _assert(seq3["q_ref_ah"] == 0.272, "earliest arrival must define the anchor")
    _assert(seq3["anchor"]["source_epoch"] == base + 15 * day, "anchor origin wrong")
    _assert(seq3["n_rpt_pre_anchor_excluded"] == 1, "earlier-source RPT is pre-anchor")
    return "anchor=.281; invalid/late/pre-anchor handled; pre-anchor query -> no state"


def test_no_future_input_leakage():
    base = 1_700_000_000.0
    day = 86400.0
    rpts = [
        {"source_epoch": base + 10 * day, "available_epoch": base + 10.5 * day,
         "capacity_ah": 0.280, "valid": True},
        {"source_epoch": base + 20 * day, "available_epoch": base + 20.5 * day,
         "capacity_ah": 0.274, "valid": True},
        {"source_epoch": base + 22 * day, "available_epoch": base + 40 * day,
         "capacity_ah": 0.270, "valid": True},
        {"source_epoch": base + 35 * day, "available_epoch": base + 35.5 * day,
         "capacity_ah": 0.260, "valid": True},
    ]
    cycles = [
        {"source_epoch": base + 11 * day, "available_epoch": base + 11 * day,
         "control": [0.5] * CONTROL_DIM, "control_mask": [1.0] * CONTROL_DIM},
        {"source_epoch": base + 19 * day, "available_epoch": base + 19 * day,
         "control": [0.7] * CONTROL_DIM, "control_mask": [1.0] * CONTROL_DIM},
        {"source_epoch": base + 24 * day, "available_epoch": base + 26 * day,
         "control": [9.0] * CONTROL_DIM, "control_mask": [1.0] * CONTROL_DIM},
        {"source_epoch": base + 33 * day, "available_epoch": base + 33 * day,
         "control": [-9.0] * CONTROL_DIM, "control_mask": [1.0] * CONTROL_DIM},
    ]
    cutoff = base + 40 * day
    seq = build_cell_sequence("c", cycles, rpts, cutoff_epoch=cutoff)
    model = build_model(seed=4).double()
    q = base + 25 * day
    st1 = replay_asof(model, seq, q)
    _assert(st1["available"], "state must be available after anchor")
    # at q=25d two records have source<=q but arrival>q: RPT@22d (arrives 40d)
    # and cycle@24d (arrives 26d).  Both must be gated, not used.
    _assert(st1["n_late_arrival_excluded"] == 2, "late-arriving records must be gated")
    _assert(st1["n_cycles_used"] == 2, "future/late cycles must not be used")

    mut = copy.deepcopy(seq)
    last_t = seq["events"][-1]["source_epoch"]
    mut["events"].append({"kind": "cycle", "index": 99,
                          "source_epoch": base + 26 * day,
                          "available_epoch": base + 26 * day,
                          "control": [123.0] * CONTROL_DIM,
                          "control_mask": [1.0] * CONTROL_DIM,
                          "dt_weeks": (base + 26 * day - last_t) / 604800.0})
    mut["events"].append({"kind": "rpt", "index": 99,
                          "source_epoch": base + 27 * day,
                          "available_epoch": base + 27 * day,
                          "capacity_ah": 0.10, "score": True,
                          "dt_weeks": 1.0 / 7.0})
    st2 = replay_asof(model, mut, q)
    _assert(_close(st1["m"], st2["m"], atol=0.0), "future event changed state mean")
    _assert(_close(st1["P"], st2["P"], atol=0.0), "future event changed state covariance")
    f1 = forecast_capacity(model, seq, q, 2.0)
    f2 = forecast_capacity(model, mut, q, 2.0)
    _assert(_close(f1["capacity_mean_ah"], f2["capacity_mean_ah"], atol=0.0),
            "future event changed forecast mean")
    _assert(_close(f1["capacity_total_var_ah2"], f2["capacity_total_var_ah2"], atol=0.0),
            "future event changed forecast variance")

    st3 = replay_asof(model, seq, base + 23 * day)
    _assert(st3["n_late_arrival_excluded"] == 1, "source<q, arrival>q must stay excluded")
    _assert(st3["n_rpt_used"] == 1, "only the RPT arrived by q may be used")
    return "future/late records never enter state or forecast (exact equality)"


def test_cell_grouped_split():
    ids = ["cell_%03d" % i for i in range(125)]
    train, val = split_cells_by_hash(ids, 25, seed=42)
    _assert(len(train) == 100 and len(val) == 25, "split sizes wrong")
    _assert(not (set(train) & set(val)), "cell leakage across split")
    _assert(set(train) | set(val) == set(ids), "split lost cells")
    train2, val2 = split_cells_by_hash(list(reversed(ids)), 25, seed=42)
    _assert(train2 == train and val2 == val, "split must not depend on input order")
    _, v3 = split_cells_by_hash(ids, 25, seed=43)
    _assert(v3 != val, "different seed should change the cell split")
    _assert(sorted(train) != ids[:100], "split must not be an index range")
    return "125 cells -> 100 train / 25 val, disjoint, hash-based, order-invariant"


def test_standardizer_buffers():
    model = build_model(seed=5).double()
    train = synthetic_sequences(3, seed=10)
    for s in train:
        for e in s["events"]:
            if e["kind"] == "cycle":
                e["control"][0] = 7.0
                e["control_mask"] = [1.0, 1.0] + [0.0] * (CONTROL_DIM - 2)
    val = synthetic_sequences(1, seed=99)[0]
    for e in val["events"]:
        if e["kind"] == "cycle":
            e["control"][0] = 7.0
            e["control"][1] = 1e6
            e["control_mask"] = [1.0, 1.0] + [0.0] * (CONTROL_DIM - 2)

    sd = TrainControlStandardizer().fit(train)
    _assert(float(sd.scale[0]) == 1.0, "constant column must use scale 1 (skipped)")
    _assert(abs(float(sd.mean[0]) - 7.0) < 1e-12, "constant mean wrong")
    _assert(sd.n_constant_skipped == CONTROL_DIM - 1,
            "expected %d skipped dims, got %d" % (CONTROL_DIM - 1, sd.n_constant_skipped))
    vals = torch.tensor([e["control"][1] for s in train for e in s["events"]
                         if e["kind"] == "cycle"], dtype=torch.float64)
    _assert(abs(float(sd.scale[1]) - float(vals.std(unbiased=False))) < 1e-12,
            "scale must be population std from train cells only")
    info = sd.apply_to_model(model)
    buf = dict(model.named_buffers())
    _assert("control_mean" in buf, "mean not stored as buffer")
    _assert("control_scale" in buf, "scale not stored as buffer")
    x = torch.tensor([7.0] + [0.0] * (CONTROL_DIM - 1), dtype=torch.float64)
    _assert(abs(float(model.standardize_control(x)[0])) < 1e-12,
            "constant feature is not centred to 0")
    _assert(info["n_constant_scale_one_skipped"] == CONTROL_DIM - 1, "skip count wrong")
    return "train-only stats in buffers; constant scale=1; val outlier ignored"


def test_capacity_variance_hph():
    model = build_model(seed=6).double()
    m, P = model.initial_state(1)
    m = m + torch.tensor([[0.21, 0.015]], dtype=torch.float64)
    P = _psd(1, seed=11).double()
    q = 0.281
    mu, latent, S, H = model.capacity_moments(m, P, [q])
    qdet = q * math.exp(-float(m[0, 0]))
    manual = (qdet ** 2) * float(P[0, 0, 0]) + float(P[0, 1, 1]) \
        - 2.0 * qdet * float(P[0, 0, 1])
    _assert(abs(float(latent) - manual) < 1e-12, "HPH^T mismatch")
    _assert(abs(float(mu) - (qdet + float(m[0, 1]))) < 1e-12, "state-only mean mismatch")
    _assert(abs(float(S) - (manual + float(model.obs_variance()))) < 1e-12,
            "total variance must add sigma^2")
    m1, P1, nll, diag = model.correct_rpt(m, P, [q], [0.272])
    _assert(bool(torch.isfinite(nll).all()), "non-finite NLL")
    _assert(_close(P1, P1.transpose(-1, -2), atol=1e-14), "P not symmetric")
    eig = torch.linalg.eigvalsh(P1)
    _assert(float(eig.min()) > -1e-12, "P not PSD after Joseph update")
    _assert(float(diag["capacity_var_after_ah2"]) < float(diag["capacity_var_before_ah2"]),
            "informative RPT update should shrink capacity variance")
    return "latent var == q^2 e^-2D P00 + P11 - 2q e^-D P01; Joseph PSD"


def test_d_can_decrease_after_update():
    model = build_model(seed=7).double()
    m, P = model.initial_state(1)
    m, P, _ = model.advance(m, P, 5.0)
    d_before = float(m[0, 0])
    _assert(d_before > 0.0, "positive drift should increase D")
    mu, _, _, _ = model.capacity_moments(m, P, [0.28])
    m1, _, _, _ = model.correct_rpt(m, P, [0.28], [float(mu) + 0.15])
    _assert(float(m1[0, 0]) < d_before, "Gaussian update can lower D; must be allowed")
    return "non-negative drift, but RPT update may lower D (no pathwise claim)"


def test_no_readout_bypass():
    model = build_model(seed=8).double()
    _assert(not hasattr(model, "readout"), "A2 must not have an F0/readout mean bypass")
    _assert(not hasattr(model, "context_dim"), "A2 has no query-context input")
    params = list(inspect.signature(model.capacity_moments).parameters)
    _assert(params[:2] == ["m", "P"], "capacity_moments must be state-only")
    _assert(not any("context" in p or "query" in p for p in params),
            "capacity_moments must not consume query/context features")
    m = torch.tensor([[0.17, 0.013]], dtype=torch.float64)
    mu = model.capacity_moments(m, model.prior_cov.double()[None], [0.2795])[0]
    manual = 0.2795 * math.exp(-0.17) + 0.013
    _assert(abs(float(mu) - manual) < 1e-12, "capacity mean is not Qref*exp(-D)+R")
    return "Q == Qref*exp(-D)+R exactly; no readout/context network"


def test_replay_matches_manual_loop():
    model = build_model(seed=9).double()
    seqs = synthetic_sequences(3, seed=20)
    batch = A2SequenceBatch.from_sequences(seqs, dtype=torch.float64)
    out = replay_batch(model, batch)
    for b, seq in enumerate(seqs):
        m = model.prior_mean.double()[None]
        P = model.prior_cov.double()[None]
        q_ref = torch.tensor([seq["q_ref_ah"]], dtype=torch.float64)
        tot, n = 0.0, 0
        for e in seq["events"]:
            dt = torch.tensor([e["dt_weeks"]], dtype=torch.float64)
            if e["kind"] == "cycle":
                ctl = torch.as_tensor([e["control"]], dtype=torch.float64)
                msk = torch.as_tensor([e["control_mask"]], dtype=torch.float64)
                m, P, _ = model.advance(m, P, dt, ctl, msk)
            else:
                zero = torch.zeros(1, CONTROL_DIM, dtype=torch.float64)
                m, P, _ = model.advance(m, P, dt, zero, zero)
                tot += float(model.nll_rpt(m, P, q_ref, [e["capacity_ah"]]))
                n += 1
                m, P, _, _ = model.correct_rpt(m, P, q_ref, [e["capacity_ah"]])
        ref = tot / max(1, n)
        got = float(out["per_cell_nll"][b])
        _assert(abs(ref - got) < 1e-9, "batch replay != manual loop (%.6g vs %.6g)" % (got, ref))
        _assert(_close(out["final_state_mean"][b], m[0], atol=1e-9), "final mean mismatch")
    return "padded batch replay reproduces the sequential cell loop"


def test_three_arms_share_model():
    model = build_model(seed=10).double()
    n_params = sum(p.numel() for p in model.parameters())
    seqs = synthetic_sequences(3, seed=30)
    batch = A2SequenceBatch.from_sequences(seqs, dtype=torch.float64)
    outs = {}
    for arm, (uc, ur) in {"full": (True, True), "time": (False, True),
                          "noRPTupdate": (True, False)}.items():
        out = replay_batch(model, batch, use_cycle=uc, use_rpt=ur)
        _assert(bool(torch.isfinite(out["loss_cell_macro"])), "%s loss not finite" % arm)
        outs[arm] = out
    _assert(abs(float(outs["full"]["loss_cell_macro"])
                - float(outs["time"]["loss_cell_macro"])) > 1e-12,
            "time arm must differ from full")
    _assert(abs(float(outs["full"]["loss_cell_macro"])
                - float(outs["noRPTupdate"]["loss_cell_macro"])) > 1e-12,
            "noRPTupdate arm must differ from full")
    model2 = build_model(seed=10).double()
    _assert(n_params == sum(p.numel() for p in model2.parameters()), "parameter count differs")
    for (k, v), (k2, v2) in zip(model.state_dict().items(), model2.state_dict().items()):
        _assert(k == k2 and _close(v, v2, atol=0.0), "same-seed init differs at %s" % k)
    return "one parameterisation, 3 flag combinations; same-seed init identical (%d params)" % n_params


def test_noRPT_arm_still_scored():
    """Regression: the noRPTupdate arm predicts and is scored, it just never updates."""
    model = build_model(seed=13).double()
    seqs = synthetic_sequences(3, seed=50)
    batch = A2SequenceBatch.from_sequences(seqs, dtype=torch.float64)
    full = replay_batch(model, batch, use_cycle=True, use_rpt=True)
    no = replay_batch(model, batch, use_cycle=True, use_rpt=False)
    _assert(bool((no["n_scored"] > 0).all()), "noRPT arm must still score every RPT")
    _assert(torch.equal(no["n_scored"], full["n_scored"]), "scored counts must match")
    _assert(float(no["loss_cell_macro"]) != float(full["loss_cell_macro"]),
            "noRPT arm must not silently equal full")
    _assert(bool(torch.isfinite(no["per_cell_nll"]).all()), "non-finite noRPT NLL")
    # its capacity variance never contracts at an RPT (no measurement update)
    before = no["capacity_var_before_ah2"]
    after = no["capacity_var_after_ah2"]
    finite = torch.isfinite(after)
    _assert(bool((after[finite] >= before[finite] - 1e-15).all()),
            "noRPT arm must not shrink capacity variance via an update")
    return "noRPT scores every RPT, never corrects, variance never contracts"


def test_four_flag_combinations_supported():
    """Both ablation switches are independent; all four cells are runnable."""
    model = build_model(seed=14).double()
    batch = A2SequenceBatch.from_sequences(synthetic_sequences(2, seed=60),
                                           dtype=torch.float64)
    losses = {}
    for uc in (True, False):
        for ur in (True, False):
            out = replay_batch(model, batch, use_cycle=uc, use_rpt=ur)
            _assert(bool(torch.isfinite(out["loss_cell_macro"])),
                    "combination cycle=%s rpt=%s not finite" % (uc, ur))
            losses[(uc, ur)] = float(out["loss_cell_macro"])
    _assert(len(set(round(v, 12) for v in losses.values())) == 4,
            "the four mechanism configurations must be distinguishable")
    return "4 flag cells finite and distinct; 3 official arms use the one-factor-at-a-time set"


def test_gradients_flow():
    model = build_model(seed=11)
    seqs = synthetic_sequences(3, seed=40)
    batch = A2SequenceBatch.from_sequences(seqs)
    out = replay_batch(model, batch)
    out["loss_cell_macro"].backward()
    g = model.rates[0].weight.grad
    _assert(g is not None and bool(torch.isfinite(g).all()) and float(g.abs().sum()) > 0,
            "rate network receives no gradient")
    go = model.obs_sigma_raw.grad
    _assert(go is not None and bool(torch.isfinite(go).all()),
            "obs sigma gets no finite gradient")
    return "synthetic backward pass only (no optimiser step); finite non-zero grads"


def test_prior_is_explicit():
    model = build_model(seed=12, prior_sd_D=0.004, prior_sd_R=0.006)
    _assert(_close(model.prior_mean, torch.zeros(2), atol=0.0), "prior mean must be explicit")
    _assert(_close(model.prior_cov,
                   torch.diag(torch.tensor([0.004 ** 2, 0.006 ** 2])), atol=1e-16),
            "prior covariance must equal the declared variances")
    st = model.initial_state(2)
    _assert(st[0].shape == (2, 2) and st[1].shape == (2, 2, 2), "prior batch shape wrong")
    return "D0=R0=0, Var(D0)=1.6e-5, Var(R0)=3.6e-5 Ah^2, explicit and fixed"


FIXTURES = [
    ("dt_not_an_input", test_dt_not_an_input),
    ("grid_invariance", test_grid_invariance),
    ("sigma_is_std_variance_is_square", test_sigma_is_std_variance_is_square),
    ("qref_anchor", test_qref_anchor),
    ("no_future_input_leakage", test_no_future_input_leakage),
    ("cell_grouped_split", test_cell_grouped_split),
    ("standardizer_buffers", test_standardizer_buffers),
    ("capacity_variance_hph", test_capacity_variance_hph),
    ("d_can_decrease_after_update", test_d_can_decrease_after_update),
    ("no_readout_bypass", test_no_readout_bypass),
    ("replay_matches_manual_loop", test_replay_matches_manual_loop),
    ("three_arms_share_model", test_three_arms_share_model),
    ("noRPT_arm_still_scored", test_noRPT_arm_still_scored),
    ("four_flag_combinations", test_four_flag_combinations_supported),
    ("gradients_flow", test_gradients_flow),
    ("prior_is_explicit", test_prior_is_explicit),
]


def run_all(verbose=True):
    results = []
    for name, fn in FIXTURES:
        try:
            detail = fn()
            results.append({"name": name, "passed": True, "detail": detail})
            if verbose:
                print("[PASS] %-32s %s" % (name, detail))
        except Exception as exc:  # noqa: BLE001 - harness reports every fixture
            results.append({"name": name, "passed": False, "detail": str(exc)})
            if verbose:
                print("[FAIL] %-32s %s" % (name, exc))
                traceback.print_exc()
    n_pass = sum(1 for r in results if r["passed"])
    if verbose:
        print("SUMMARY: %d passed, %d failed, %d total" %
              (n_pass, len(results) - n_pass, len(results)))
    return {"results": results, "n_pass": n_pass, "n_fail": len(results) - n_pass}
