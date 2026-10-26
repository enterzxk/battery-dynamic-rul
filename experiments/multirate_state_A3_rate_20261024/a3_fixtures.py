"""Synthetic-only fixtures for the A3 individual-rate state model.

Every fixture uses fabricated tensors/records; no payload, no processed
dataset, no checkpoint, no real GO, no optimiser run beyond single backward
passes used to probe gradient flow.  The fixture set proves:

 1. softplus(ell) > 0 everywhere and the D mean path is strictly increasing
    under fine-grid propagation (drift monotonicity); noEll D = c*t exactly;
 2. the frozen-linearization discretization is an EXACT affine semigroup
    (one shot over an interval == the composition of its parts, < 1e-10 in
    float64), including through the segment engine with carried coefficients;
 3. the 3x3 Joseph update is symmetric PSD, equals the standard Kalman
    covariance, and the noRateUpdate gain masking leaves ell untouched;
 4. ell is OBSERVABLE: a synthetic cell with a high true rate shrinks the ell
    posterior dramatically (and noRateUpdate does not shrink at all);
 5. the four-arm ablation structure (time mu constant; noRateUpdate ell trace
    == full ell trace when unobserved and != when observed; noEll == A2-type
    degeneration with a structurally zero ell prior);
 6. a window loss equals the corresponding segment of the full replay and the
    exact burn-in reproduces the full-filter window-start state (reusing the
    A2 window mechanism: WindowSampler / WindowBatch);
 7. OU channel closed forms; 8. sigma-is-a-std semantics; 9. explicit prior
    and state-only capacity map; 10. dt is not a network input and there is no
    future leakage; 11. gradients flow in every arm (and unused parameters get
    no gradient); 12. the train entry refuses >= 12 GO mutation classes;
 13. a no-payload open() audit records zero forbidden paths; 14. the consumed
    GO registry appends once and refuses duplicates (fail-closed on malformed
    lines); 15. cell-macro loss and anchor/score exclusion; 16. all four arms
    forward finite on one synthetic batch; 17. the selection -> frozen-steps
    -> full-refit training structure runs end-to-end on synthetic cells.
"""
from __future__ import annotations

import copy
import json
import math
import os
import random
import sys
import tempfile
import traceback

import numpy as np
import torch
import torch.nn.functional as F

_HERE = os.path.dirname(os.path.abspath(__file__))
_A2_DIR = os.path.join(os.path.dirname(_HERE), "multirate_state_A2_20261022")
if not os.path.isdir(_A2_DIR):
    raise ImportError("A2 code directory not found at %s" % _A2_DIR)
if _A2_DIR not in sys.path:
    sys.path.insert(0, _A2_DIR)

from a2_fastdata import (  # noqa: E402  (reused, unchanged)
    FastA2Data, WindowSampler, fit_control_standardizer,
    synthetic_fast_data, synthetic_sequences_for_windows,
)
from a2_targets import hash_file  # noqa: E402  (reused, unchanged)

from a3_model import (  # noqa: E402
    ARM_CONFIGS, CONTROL_DIM, LOG_2PI, VERSION, _burn_in_state_a3,
    _event_scalars_a3, _run_events_a3, _segment_advance, build_arm_model,
    build_model, eval_cell_macro_a3, replay_cells_a3, replay_windows_a3,
)
import a3_train  # noqa: E402

A3_ROOT = "/home/yndx/zxk/rul"
# Paths the self-check must NEVER open: raw/derived payload, reports, the A2
# PREP cache, the real consumed-GO registry, and any npz outside tmpdir.
FORBIDDEN_PREFIXES = (
    A3_ROOT + "/data",
    A3_ROOT + "/reports",
    A3_ROOT + "/prep_inputs",
)
FORBIDDEN_MARKERS = (
    "prep_v2_20261022",
    "consumed_gos.jsonl",
    "multirate_state_A2_20261022/runs",
    "multirate_state_A2_20261022/prep",
    "/GO_A2_",
)


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _close(a, b, atol=1e-9, rtol=0.0):
    return torch.allclose(torch.as_tensor(a, dtype=torch.float64),
                          torch.as_tensor(b, dtype=torch.float64),
                          atol=atol, rtol=rtol)


def _rand_spd(dim, scale=0.5):
    A = torch.randn(dim, dim, dtype=torch.float64)
    return A @ A.transpose(0, 1) + torch.eye(dim, dtype=torch.float64) * scale


def _is_forbidden_path(path, tmp_prefix):
    p = str(path)
    if p.startswith(tmp_prefix):
        return False
    for pref in FORBIDDEN_PREFIXES:
        if p.startswith(pref):
            return True
    for marker in FORBIDDEN_MARKERS:
        if marker in p:
            return True
    if p.endswith(".npz"):
        return True
    return False


class OpenAuditor(object):
    """Record every builtins.open target while a synthetic workload runs."""

    def __init__(self):
        self.paths = []
        self._orig = None

    def __enter__(self):
        import builtins
        self._orig = builtins.open
        auditor = self

        def wrapped(file, *args, **kwargs):
            try:
                auditor.paths.append(os.path.abspath(os.fspath(file)))
            except Exception:  # noqa: BLE001 - record, never block
                auditor.paths.append(repr(file))
            return auditor._orig(file, *args, **kwargs)

        builtins.open = wrapped
        return self

    def __exit__(self, *exc):
        import builtins
        builtins.open = self._orig
        return False


# --------------------------------------------------------------------- fixtures
def test_softplus_positive_and_D_mean_monotone():
    model = build_arm_model("full", 3).double()
    ells = torch.tensor([-30.0, -20.0, -8.0, -5.8, -3.0, 0.0, 2.0, 10.0,
                         30.0], dtype=torch.float64)
    sp = F.softplus(ells)
    _assert(bool((sp > 0).all()), "softplus(ell) must be > 0, min=%g"
            % float(sp.min()))
    min_sp = float(sp.min())
    # fine-grid mean path: strictly increasing D under the time arm
    # (mu = mu_base) and under the full arm with random controls.
    dt = 1e-3
    worst = float("inf")
    for ell0 in (-20.0, -8.0, -5.8, -3.0, 0.0, 2.0):
        m = torch.tensor([[0.0, ell0, 0.0]], dtype=torch.float64)
        P = torch.diag(torch.tensor([1e-6, 0.5, 1e-6],
                                    dtype=torch.float64)).reshape(1, 3, 3)
        prev = float(m[0, 0])
        for _ in range(1500):
            m, P = model.advance(m, P, dt, None, None, ARM_CONFIGS["time"])
            d = float(m[0, 0]) - prev
            _assert(d > 0.0, "D mean decreased (time arm, ell0=%g): %g"
                    % (ell0, d))
            worst = min(worst, d)
            prev = float(m[0, 0])
    torch.manual_seed(31)
    for ell0 in (-6.5, -5.0, -4.0, -3.0):
        m = torch.tensor([[0.0, ell0, 0.0]], dtype=torch.float64)
        P = torch.diag(torch.tensor([1e-6, 0.5, 1e-6],
                                    dtype=torch.float64)).reshape(1, 3, 3)
        prev = float(m[0, 0])
        for _ in range(800):
            ctl = torch.randn(1, 1, CONTROL_DIM, dtype=torch.float64) * 0.5
            msk = (torch.rand(1, 1, CONTROL_DIM, dtype=torch.float64)
                   > 0.2).double()
            m, P = model.advance(m, P, dt, ctl, msk, ARM_CONFIGS["full"])
            d = float(m[0, 0]) - prev
            _assert(d > 0.0, "D mean decreased (full arm, ell0=%g): %g"
                    % (ell0, d))
            worst = min(worst, d)
            prev = float(m[0, 0])
    # noEll: D == c*t exactly; ell and its variance frozen.
    cfg = ARM_CONFIGS["noEll"]
    c = float(model.c_rate())
    m = torch.tensor([[0.0, -5.8, 0.0]], dtype=torch.float64)
    P = torch.diag(torch.tensor([2.5e-5, 0.0, 2.5e-5],
                                dtype=torch.float64)).reshape(1, 3, 3)
    m0 = m.clone()
    P0 = P.clone()
    T = 0.0
    for k in range(1, 101):
        ctl = torch.randn(1, 1, CONTROL_DIM, dtype=torch.float64)
        msk = (torch.rand(1, 1, CONTROL_DIM, dtype=torch.float64)
               > 0.2).double()
        m, P = model.advance(m, P, 0.05, ctl, msk, cfg)
        T += 0.05
        _assert(abs(float(m[0, 0]) - c * T) < 1e-12,
                "noEll D path != c*t at step %d" % k)
        _assert(float(m[0, 1]) == float(m0[0, 1]), "noEll ell moved")
        _assert(float(P[0, 1, 1]) == float(P0[0, 1, 1]), "noEll ell var moved")
    m_one, _ = model.advance(m0, P0, 5.0, None, None, cfg)
    _assert(_close(m_one[0, 0], c * 5.0, atol=1e-12), "noEll one-shot D")
    return "min softplus=%.3e; min D increment=%.3e; noEll D==c*t (|err|<1e-12, c=%.5f/wk)" % (
        min_sp, worst, c)


def test_semigroup_grid_invariance():
    model = build_arm_model("full", 4).double()
    torch.manual_seed(6)
    worst = 0.0
    checked = 0
    for trial in range(4):
        ell_lin = float(torch.empty(1).uniform_(-8.0, -2.0))
        mu = float(torch.empty(1).uniform_(-7.0, -4.5))
        coeffs = model.frozen_coeffs(ell_lin, mu)
        m = torch.randn(1, 3, dtype=torch.float64) * 0.1
        P = _rand_spd(3, 0.5)
        for dt1, dt2 in ((0.3, 0.7), (1e-3, 2.0), (0.5, 0.5)):
            one_m, one_P = model.advance_from_coeffs(m, P, dt1 + dt2, coeffs)
            mid_m, mid_P = model.advance_from_coeffs(m, P, dt1, coeffs)
            two_m, two_P = model.advance_from_coeffs(mid_m, mid_P, dt2,
                                                     coeffs)
            worst = max(worst,
                        float((one_m - two_m).abs().max()),
                        float((one_P - two_P).abs().max()))
            checked += 1
    _assert(worst < 1e-10,
            "frozen-coefficient semigroup violated: %g" % worst)
    # event-level semigroup through the segment engine with CARRIED (a, b):
    kind = torch.ones(1, 2, dtype=torch.long)
    dt = torch.tensor([[0.3, 0.7]], dtype=torch.float64)
    ctl = torch.randn(1, 2, CONTROL_DIM, dtype=torch.float64) * 0.3
    msk = (torch.rand(1, 2, CONTROL_DIM, dtype=torch.float64) > 0.2).double()
    scal = _event_scalars_a3(model, kind, dt, ctl, msk, True)
    m = torch.tensor([[0.05, -4.2, 0.01]], dtype=torch.float64)
    P = _rand_spd(3, 0.3)
    a, b = model.frozen_linearization(m[:, 1])
    m_one, P_one = _segment_advance(model, m, P, scal, 0, 2, a, b, True)
    m_mid, P_mid = _segment_advance(model, m, P, scal, 0, 1, a, b, True)
    m_two, P_two = _segment_advance(model, m_mid, P_mid, scal, 1, 2, a, b,
                                    True)
    seg_worst = max(float((m_one - m_two).abs().max()),
                    float((P_one - P_two).abs().max()))
    _assert(seg_worst < 1e-10,
            "carried-frozen segment semigroup violated: %g" % seg_worst)
    # diagnostic (documented, not an identity): refreezing the linearization
    # at each sub-step differs only at linearization order.
    saved_mu = float(model.mu_base)
    with torch.no_grad():
        model.mu_base.fill_(-1.0)
    m = torch.tensor([[0.1, -3.0, 0.02]], dtype=torch.float64)
    P = _rand_spd(3, 0.2)
    ctl = torch.zeros(1, 1, CONTROL_DIM, dtype=torch.float64)
    msk = torch.zeros_like(ctl)
    m_one, _ = model.advance(m, P, 0.5, ctl, msk, ARM_CONFIGS["full"])
    m_a, P_a = model.advance(m, P, 0.25, ctl, msk, ARM_CONFIGS["full"])
    m_two, _ = model.advance(m_a, P_a, 0.25, ctl, msk, ARM_CONFIGS["full"])
    gap = float((m_two - m_one).abs().max())
    with torch.no_grad():
        model.mu_base.fill_(saved_mu)
    _assert(0.0 < gap < 0.05,
            "refreeze gap out of expected linearization-order band: %g" % gap)
    return "frozen semigroup max|err|=%.3e over %d splits; segment engine %.3e; refreeze gap=%.3e (linearization-order, reported)" % (
        worst, checked, seg_worst, gap)


def test_joseph_update_symmetry_psd_kalman_equivalence():
    model = build_arm_model("full", 5).double()
    torch.manual_seed(7)
    q_ref = torch.tensor([0.28], dtype=torch.float64)
    worst_sym = 0.0
    worst_kalman = 0.0
    min_eig = float("inf")
    for _ in range(6):
        m = torch.randn(1, 3, dtype=torch.float64) * 0.3
        m[0, 1] += -5.0
        P = _rand_spd(3, 0.3).reshape(1, 3, 3)
        y = torch.tensor([0.27], dtype=torch.float64)
        m1, P1, nll, diag = model.correct_rpt(m, P, q_ref, y,
                                              rate_update=True)
        worst_sym = max(worst_sym,
                        float((P1 - P1.transpose(1, 2)).abs().max()))
        min_eig = min(min_eig, float(torch.linalg.eigvalsh(P1[0]).min()))
        mu, latent, S, H = model.capacity_moments(m, P, q_ref)
        K = (P @ H[:, :, None]).squeeze(-1) / S[:, None]
        eye = torch.eye(3, dtype=torch.float64)
        P_std = (eye - K[:, :, None] * H[:, None, :]) @ P
        worst_kalman = max(worst_kalman,
                           float((P1[0] - P_std[0]).abs().max()))
        _assert(_close(diag["gain"], K, atol=1e-12), "gain != PH'/S")
        _assert(float(diag["capacity_var_after_ah2"][0]) <=
                float(diag["capacity_var_before_ah2"][0]) + 1e-12,
                "capacity variance increased after update")
        nll_manual = 0.5 * ((y - mu).square() / S + torch.log(S) + LOG_2PI)
        _assert(_close(nll, nll_manual, atol=1e-12), "NLL formula mismatch")
    _assert(worst_sym < 1e-12, "Joseph covariance not symmetric: %g"
            % worst_sym)
    _assert(min_eig > -1e-12, "Joseph covariance not PSD: %g" % min_eig)
    _assert(worst_kalman < 1e-12,
            "Joseph != standard Kalman covariance: %g" % worst_kalman)
    # noRateUpdate: ell gain exactly zero, ell mean/var untouched
    m1n, P1n, _, diag_n = model.correct_rpt(m, P, q_ref, y,
                                            rate_update=False)
    _assert(float(diag_n["gain"][0, 1]) == 0.0, "noRateUpdate gain_ell != 0")
    _assert(float(m1n[0, 1]) == float(m[0, 1]), "noRateUpdate moved ell mean")
    _assert(_close(P1n[0, 1, 1], P[0, 1, 1], atol=1e-14),
            "noRateUpdate changed ell variance")
    _assert(float((P1n - P1n.transpose(1, 2)).abs().max()) < 1e-12 and
            float(torch.linalg.eigvalsh(P1n[0]).min()) > -1e-12,
            "noRateUpdate Joseph covariance not symmetric PSD")
    return "sym=%.2e, PSD min eig=%.3e, |Joseph-standardKF|=%.2e, gain_ell(noRateUpdate)=0, ell var unchanged" % (
        worst_sym, min_eig, worst_kalman)


def test_ell_observability_posterior_shrinkage():
    q_ref = 0.28
    ell_true = -4.0
    g_true = float(F.softplus(torch.tensor(ell_true, dtype=torch.float64)))
    n_obs, dt = 120, 1.0
    rng = np.random.RandomState(10)
    y = np.array([q_ref * math.exp(-g_true * (k + 1))
                  + rng.normal(0.0, 5e-4) for k in range(n_obs)])
    y_t = torch.tensor(y, dtype=torch.float64).reshape(-1)

    def run(kappa, sigma_ell, rate_update):
        model = build_arm_model("full", 9).double()
        with torch.no_grad():
            model.obs_sigma_raw.fill_(math.log(math.expm1(5e-4)))
            model.kappa_raw.fill_(math.log(math.expm1(kappa)))
            model.sigma_ell_raw.fill_(math.log(math.expm1(sigma_ell)))
        m, P = model.initial_state(1, dtype=torch.float64)
        prior_var = float(P[0, 1, 1])
        for k in range(n_obs):
            m, P = model.advance(m, P, dt, None, None, ARM_CONFIGS["full"])
            m, P, _, _ = model.correct_rpt(m, P, q_ref, y_t[k:k + 1],
                                           rate_update=rate_update)
        return model, m, P, prior_var

    # clean sub-case: ell essentially constant (kappa, sigma_ell -> 1e-4)
    _, m, P, prior_var = run(1e-4, 1e-4, True)
    ratio = float(P[0, 1, 1]) / prior_var
    d_err = abs(float(m[0, 0]) - g_true * n_obs)
    ell_post = float(m[0, 1])
    _assert(ratio < 0.02,
            "ell posterior did not shrink (clean): ratio=%g" % ratio)
    _assert(d_err < 0.05, "D mean does not track truth: err=%g" % d_err)
    _assert(ell_post > -5.0,
            "ell posterior mean did not move toward the true rate: %g"
            % ell_post)
    # dynamics sub-case: default OU on ell still shrinks the posterior
    _, m2, P2, prior_var2 = run(float(build_model(0).kappa()),
                                float(build_model(0).sigma_ell()), True)
    ratio2 = float(P2[0, 1, 1]) / prior_var2
    _assert(ratio2 < 0.5,
            "ell posterior did not shrink (OU): ratio=%g" % ratio2)
    # contrast: noRateUpdate's ell posterior equals its own prediction-only
    # trajectory (the OU prediction legitimately evolves; measurements must
    # not touch it).
    model_nr, m3, P3, _ = run(1e-4, 1e-4, False)
    prior_var_nr = float(model_nr.prior_cov[1, 1])
    m_pd, P_pd = model_nr.initial_state(1, dtype=torch.float64)
    for k in range(n_obs):
        m_pd, P_pd = model_nr.advance(m_pd, P_pd, dt, None, None,
                                      ARM_CONFIGS["full"])
    _assert(_close(m3[0, 1], m_pd[0, 1], atol=1e-14),
            "noRateUpdate ell mean moved relative to prediction-only")
    _assert(_close(P3[0, 1, 1], P_pd[0, 1, 1], atol=1e-14),
            "noRateUpdate ell variance moved relative to prediction-only")
    _assert(float(P3[0, 1, 1]) > 0.5 * prior_var_nr,
            "unexpected: ell variance collapsed even without updates")
    return "clean: var ratio=%.3e, |D-Dtrue|=%.4f, ell post=%.3f; OU: ratio=%.3e; noRateUpdate: ell == prediction-only (err<1e-14)" % (
        ratio, d_err, ell_post, ratio2)


def test_four_arm_ablation_structure():
    model = build_arm_model("full", 11).double()
    torch.manual_seed(12)
    T = 8
    kind = torch.tensor([[1, 1, 2, 1, 1, 2, 1, 1]], dtype=torch.long)
    dt = torch.rand(1, T, dtype=torch.float64) * 0.4 + 0.05
    ctl = torch.randn(1, T, CONTROL_DIM, dtype=torch.float64) * 0.5
    msk = (torch.rand(1, T, CONTROL_DIM, dtype=torch.float64) > 0.2).double()
    y = torch.zeros(1, T, dtype=torch.float64)
    y[0, 2] = 0.271
    y[0, 5] = 0.266
    score_true = torch.zeros(1, T, dtype=torch.bool)
    score_true[0, [2, 5]] = True
    score_false = torch.zeros(1, T, dtype=torch.bool)
    q_ref = torch.tensor([0.28], dtype=torch.float64)
    m0, P0 = model.initial_state(1, dtype=torch.float64)

    # (i) time arm mu is exactly mu_base for arbitrary controls; full differs
    scal_t = _event_scalars_a3(model, kind, dt, ctl, msk, False)
    _assert(float((scal_t["mu"] - model.mu_base.double()).abs().max()) == 0.0,
            "time arm mu != mu_base")
    scal_f = _event_scalars_a3(model, kind, dt, ctl, msk, True)
    _assert(float((scal_f["mu"] - scal_t["mu"]).abs().max()) > 1e-6,
            "full arm mu did not react to controls")

    # (ii) noRateUpdate: ell trace == prediction-only trace; full moves ell
    m_nr, P_nr, _, ns_nr, _, _ = _run_events_a3(
        model, kind, dt, ctl, msk, y, score_true, q_ref, m0, P0,
        ARM_CONFIGS["noRateUpdate"])
    m_pd, P_pd, _, _, _, _ = _run_events_a3(
        model, kind, dt, ctl, msk, y, score_false, q_ref, m0, P0,
        ARM_CONFIGS["noRateUpdate"])
    _assert(_close(m_nr[0, 1], m_pd[0, 1], atol=1e-14),
            "noRateUpdate ell mean moved under observations")
    _assert(_close(P_nr[0, 1, 1], P_pd[0, 1, 1], atol=1e-14),
            "noRateUpdate ell variance moved under observations")
    m_nr_un, _, _, _, _, _ = _run_events_a3(
        model, kind, dt, ctl, msk, y, score_false, q_ref, m0, P0,
        ARM_CONFIGS["noRateUpdate"])
    m_fu_un, _, _, _, _, _ = _run_events_a3(
        model, kind, dt, ctl, msk, y, score_false, q_ref, m0, P0,
        ARM_CONFIGS["full"])
    _assert(float((m_nr_un - m_fu_un).abs().max()) == 0.0,
            "full and noRateUpdate ell trajectories differ without "
            "observations")
    m_fu, _, _, _, _, _ = _run_events_a3(
        model, kind, dt, ctl, msk, y, score_true, q_ref, m0, P0,
        ARM_CONFIGS["full"])
    d_ell = float((m_fu[0, 1] - m_nr[0, 1]).abs().max())
    _assert(d_ell > 1e-9,
            "full and noRateUpdate ell posterior identical DESPITE "
            "observations (%g)" % d_ell)

    # (iii) noEll: D == c*t on observation-free spans; ell channel inert
    cfg_ne = ARM_CONFIGS["noEll"]
    model_ne = build_arm_model("noEll", 11).double()
    c = float(model_ne.c_rate())
    m0_ne, P0_ne = model_ne.initial_state(1, dtype=torch.float64)
    _assert(float(P0_ne[0, 1, 1]) == 0.0,
            "noEll prior ell variance must be structurally zero")
    m_ne, P_ne, _, _, _, _ = _run_events_a3(
        model_ne, kind, dt, ctl, msk, y, score_false, q_ref, m0_ne, P0_ne,
        cfg_ne)
    T_total = float(dt.sum())
    _assert(_close(m_ne[0, 0], c * T_total, atol=1e-12),
            "noEll D != c*t over the observation-free sequence")
    _assert(float(P_ne[0, 0, 0]) == float(P0_ne[0, 0, 0]),
            "noEll D variance moved without D process noise")
    _assert(float(P_ne[0, 1, 1]) == 0.0 and float(P_ne[0, 0, 1]) == 0.0,
            "noEll ell channel not inert (point-mass prior required)")
    m_ne_u, P_ne_u, _, ns_ne, _, _ = _run_events_a3(
        model_ne, kind, dt, ctl, msk, y, score_true, q_ref, m0_ne, P0_ne,
        cfg_ne)
    _assert(int(ns_ne[0]) == 2, "noEll scored RPT count wrong")
    _assert(float(P_ne_u[0, 0, 0]) < float(P0[0, 0, 0]),
            "noEll D not corrected by RPT updates")
    _assert(float(P_ne_u[0, 1, 1]) == 0.0,
            "noEll ell variance leaked after update")
    m_full_c, _, _, _, _, _ = _run_events_a3(
        model, kind, dt, ctl, msk, y, score_false, q_ref, m0, P0,
        ARM_CONFIGS["full"])
    _assert(abs(float(m_full_c[0, 0]) - c * T_total) > 1e-9,
            "full arm D path indistinguishable from noEll c*t")
    return "time mu==mu_base exact; full-vs-noRateUpdate ell delta=%.3e (obs) / 0 (no obs); noEll D==c*t (err<1e-12), ell channel inert" % d_ell


def test_window_loss_equals_full_replay():
    seqs = synthetic_sequences_for_windows(n_cells=3, n_cycles=420, seed=5)
    data = FastA2Data.from_sequences(seqs)  # float64
    model = build_arm_model("full", 13).double()
    std = fit_control_standardizer(data, np.arange(data.n_cells))
    model.set_control_standardizer(std["mean"], std["scale"])
    cfg = ARM_CONFIGS["full"]
    worst_state = 0.0
    worst_loss = 0.0
    n_windows = 0
    for ci in range(data.n_cells):
        _, trace = replay_cells_a3(model, data, [ci], cfg, want_trace=True)
        trace = trace[ci]
        sampler = WindowSampler(data, np.array([ci]), window_events=256,
                                burn_in="exact", batch_cells=1)
        rng = random.Random(100 + ci)
        for _ in range(3):
            batch = sampler.sample(rng)
            out = replay_windows_a3(model, batch, cfg, return_states=True)
            s = int(batch.start[0])
            L = int(batch.lengths[0])
            # burn-in state == exact prefix replay state (and carries no grad)
            m_ref, P_ref = model.initial_state(1, dtype=torch.float64)
            if s > 0:
                sl = data.slice_tensors(ci, 0, s)
                m_ref, P_ref, _, _, _, _ = _run_events_a3(
                    model, sl["kind"], sl["dt"], sl["control"],
                    sl["control_mask"], sl["y"], sl["score"], sl["q_ref"],
                    m_ref, P_ref, cfg, collect_nll=False)
            m0 = out["window_start_mean"]
            P0 = out["window_start_cov"]
            _assert(not m0.requires_grad and not P0.requires_grad,
                    "burn-in state carries gradient")
            worst_state = max(worst_state,
                              float((m0 - m_ref).abs().max()),
                              float((P0 - P_ref).abs().max()))
            scored_local = [t for t in range(L)
                            if int(batch.kind[0, t]) == 2
                            and bool(batch.score[0, t])]
            _assert(scored_local, "sampled window without scored RPT")
            ref = [float(trace[s + t]) for t in scored_local]
            per_cell = float(out["per_cell_nll"][0])
            worst_loss = max(worst_loss,
                             abs(per_cell - sum(ref) / len(ref)))
            n_windows += 1
    _assert(worst_state < 1e-11,
            "burn-in state != full-filter window start: %g" % worst_state)
    _assert(worst_loss < 1e-9,
            "window loss != full-replay segment mean: %g" % worst_loss)
    return "%d windows (3 cells, L=256, exact burn-in): max state err=%.2e, max window-vs-full loss err=%.2e (float64)" % (
        n_windows, worst_state, worst_loss)


def test_ou_channels_closed_form():
    model = build_arm_model("time", 14).double()
    m = torch.tensor([[0.3, -4.0, 0.05]], dtype=torch.float64)
    P = torch.diag(torch.tensor([0.1, 0.2, 0.01],
                                dtype=torch.float64)).reshape(1, 3, 3)
    dt = 0.7
    m1, P1 = model.advance(m, P, dt, None, None, ARM_CONFIGS["time"])
    kap = float(model.kappa())
    lam = float(model.lam())
    s2 = float(model.sigma_ell().square())
    sR2 = float(model.sigma_R().square())
    mu = float(model.mu_base)
    alpha = math.exp(-kap * dt)
    beta = math.exp(-lam * dt)
    _assert(_close(m1[0, 1], mu + alpha * (m[0, 1] - mu), atol=1e-12),
            "ell mean != OU closed form")
    _assert(_close(m1[0, 2], beta * m[0, 2], atol=1e-12),
            "R mean != OU closed form")
    # compare the prediction INCREMENT (the prior ell/R variances also decay)
    _assert(_close(P1[0, 1, 1] - alpha ** 2 * P[0, 1, 1],
                   s2 * (1 - alpha ** 2) / (2 * kap), atol=1e-12),
            "ell variance increment != integrated-OU form")
    _assert(_close(P1[0, 2, 2] - beta ** 2 * P[0, 2, 2],
                   sR2 * (1 - beta ** 2) / (2 * lam), atol=1e-12),
            "R variance increment != integrated-OU form")
    # full arm: relaxation toward the control-dependent mu from the same call
    ctl = torch.randn(1, 1, CONTROL_DIM, dtype=torch.float64)
    msk = (torch.rand(1, 1, CONTROL_DIM, dtype=torch.float64) > 0.2).double()
    m2, _ = model.advance(m, P, dt, ctl, msk, ARM_CONFIGS["full"])
    mu_f = float(model.mu_point(ctl, msk, True)[0])
    _assert(_close(m2[0, 1], mu_f + alpha * (m[0, 1] - mu_f), atol=1e-12),
            "ell mean != OU closed form (full arm)")
    return "ell/R OU closed forms match to 1e-12 (kappa=%.3f, lambda=%.3f /wk)" % (
        kap, lam)


def test_sigma_semantics_std_not_variance():
    model = build_arm_model("full", 15).double()
    sig = float(model.obs_sigma())
    var = float(model.obs_variance())
    _assert(_close(var, sig ** 2, atol=0.0),
            "obs_variance != obs_sigma**2 (sigma must be a std, squared "
            "exactly once)")
    _assert(_close(math.sqrt(var), sig, atol=1e-15),
            "variance sqrt != sigma")
    _assert(1e-4 <= sig <= 1e-2,
            "obs sigma init outside the documented 1e-4..1e-2 Ah band: %g"
            % sig)
    for name, fn in (("kappa", model.kappa), ("sigma_ell", model.sigma_ell),
                     ("lambda", model.lam), ("sigma_R", model.sigma_R),
                     ("c_rate", model.c_rate)):
        value = float(fn())
        _assert(value > 0.0, "%s must be > 0" % name)
    with torch.no_grad():
        model.kappa_raw.fill_(-50.0)
        model.sigma_ell_raw.fill_(-50.0)
        model.lambda_raw.fill_(-50.0)
        model.sigma_R_raw.fill_(-50.0)
        model.obs_sigma_raw.fill_(-50.0)
        model.c_raw.fill_(-50.0)
    floor = 1e-8
    for name, fn in (("kappa", model.kappa), ("sigma_ell", model.sigma_ell),
                     ("lambda", model.lam), ("sigma_R", model.sigma_R),
                     ("obs_sigma", model.obs_sigma),
                     ("c_rate", model.c_rate)):
        _assert(float(fn()) == floor, "%s floor != %g" % (name, floor))
    _assert(float(model.obs_variance()) == floor ** 2,
            "floored variance != sigma**2")
    # NLL uses S = HPH' + sigma_y^2 with S a variance (Ah^2)
    torch.manual_seed(16)
    m = torch.randn(2, 3, dtype=torch.float64) * 0.2
    m[:, 1] -= 5.0
    P = _rand_spd(3, 0.3).expand(2, 3, 3).contiguous()
    q_ref = torch.tensor([0.28, 0.31], dtype=torch.float64)
    y = torch.tensor([0.27, 0.30], dtype=torch.float64)
    mu, latent, S, _ = model.capacity_moments(m, P, q_ref)
    _assert(_close(S - latent,
                   torch.full_like(S, float(model.obs_variance())),
                   atol=1e-14), "S != latent + sigma_y^2")
    nll = model.nll_rpt(m, P, q_ref, y)
    manual = 0.5 * ((y - mu).square() / S + torch.log(S) + LOG_2PI)
    _assert(_close(nll, manual, atol=1e-14), "NLL formula mismatch")
    return "sigma_y=%.4g Ah, variance==sigma^2 exact, floor=%g active at raw=-50, NLL=S-variance form" % (
        sig, floor)


def test_prior_explicit_and_state_only_map():
    model = build_arm_model("full", 17).double()
    param_names = {n for n, _ in model.named_parameters()}
    expected = {"mu_net.0.weight", "mu_net.0.bias", "mu_net.2.weight",
                "mu_net.2.bias", "mu_net.4.weight", "mu_net.4.bias",
                "mu_base", "kappa_raw", "sigma_ell_raw", "lambda_raw",
                "sigma_R_raw", "obs_sigma_raw", "c_raw"}
    _assert(param_names == expected,
            "unexpected parameter set: %r" % sorted(param_names))
    buffers = dict(model.named_buffers())
    for name in ("prior_mean", "prior_cov", "control_mean", "control_scale"):
        _assert(name in buffers, "missing buffer %s" % name)
    m, P = model.initial_state(2, dtype=torch.float64)
    _assert(_close(m[0], model.prior_mean, atol=0.0),
            "initial_state mean != prior_mean")
    _assert(_close(P[0], model.prior_cov, atol=0.0),
            "initial_state cov != prior_cov")
    _assert(float(model.prior_mean[0]) == 0.0 and
            float(model.prior_mean[2]) == 0.0,
            "anchor prior must set D=R=0 (Q_ref is the anchor reading)")
    _assert(float(model.prior_cov[1, 1]) > 0.0,
            "ell prior variance must be explicit and positive")
    # state-only capacity map: mu = Q_ref*exp(-D) + R exactly; no readout
    torch.manual_seed(18)
    mm = torch.randn(4, 3, dtype=torch.float64) * 0.5
    PP = _rand_spd(3, 0.2).expand(4, 3, 3).contiguous()
    q_ref = torch.tensor([0.28, 0.30, 0.26, 0.29], dtype=torch.float64)
    mu, latent, total, H = model.capacity_moments(mm, PP, q_ref)
    expected_mu = q_ref * torch.exp(-mm[:, 0]) + mm[:, 2]
    _assert(_close(mu, expected_mu, atol=1e-12),
            "capacity map is not Q_ref*exp(-D)+R")
    H_expected = torch.stack([-q_ref * torch.exp(-mm[:, 0]),
                              torch.zeros(4, dtype=torch.float64),
                              torch.ones(4, dtype=torch.float64)], dim=-1)
    _assert(_close(H, H_expected, atol=1e-12), "H row mismatch")
    _assert(_close(total - latent,
                   torch.full_like(total, float(model.obs_variance())),
                   atol=1e-14), "total variance != latent + sigma_y^2")
    return "params == 13 expected (single mu_net, no readout); explicit D=R=0 anchor prior; capacity map exact to 1e-12"


def test_dt_not_input_and_no_future_leak():
    model = build_arm_model("full", 19).double()
    _assert(model.mu_net[0].in_features == 2 * CONTROL_DIM,
            "mu network input is not [control*mask, mask] (%d)" %
            model.mu_net[0].in_features)
    kind = torch.ones(1, 2, dtype=torch.long)
    ctl = torch.randn(1, 2, CONTROL_DIM, dtype=torch.float64)
    msk = (torch.rand(1, 2, CONTROL_DIM, dtype=torch.float64) > 0.2).double()
    sa = _event_scalars_a3(model, kind, torch.tensor([[0.05, 0.05]],
                                                     dtype=torch.float64),
                           ctl, msk, True)
    sb = _event_scalars_a3(model, kind, torch.tensor([[0.05, 8.0]],
                                                     dtype=torch.float64),
                           ctl, msk, True)
    _assert(float((sa["mu"] - sb["mu"]).abs().max()) == 0.0,
            "dt changed the network output (dt must not be an input)")
    _assert(float((sa["alpha"] - sb["alpha"]).abs().max()) > 1e-3,
            "dt does not reach the dynamics scalars (unexpected)")
    # no future leakage: shared prefix up to the first RPT, divergent cycle
    # controls between the two RPTs -> earlier innovation unchanged, later one
    # legitimately different.
    T = 10
    kind = torch.tensor([[1, 1, 2, 1, 1, 1, 2, 1, 1, 1]], dtype=torch.long)
    dt = torch.rand(1, T, dtype=torch.float64) * 0.3 + 0.05
    ctl = torch.randn(1, T, CONTROL_DIM, dtype=torch.float64) * 0.5
    ctl_b = ctl.clone()
    ctl_b[0, 3:6] = torch.randn(3, CONTROL_DIM, dtype=torch.float64) + 2.0
    msk = (torch.rand(1, T, CONTROL_DIM, dtype=torch.float64) > 0.2).double()
    y = torch.zeros(1, T, dtype=torch.float64)
    y[0, 2] = 0.272
    y[0, 6] = 0.268
    score = torch.zeros(1, T, dtype=torch.bool)
    score[0, [2, 6]] = True
    q_ref = torch.tensor([0.28], dtype=torch.float64)
    m0, P0 = model.initial_state(1, dtype=torch.float64)
    _, _, _, _, _, tr_a = _run_events_a3(model, kind, dt, ctl, msk, y,
                                         score, q_ref, m0, P0,
                                         ARM_CONFIGS["full"],
                                         want_trace=True)
    _, _, _, _, _, tr_b = _run_events_a3(model, kind, dt, ctl_b, msk, y,
                                         score, q_ref, m0, P0,
                                         ARM_CONFIGS["full"],
                                         want_trace=True)
    _assert(float(abs(tr_a[0, 2] - tr_b[0, 2])) < 1e-14,
            "future control changed an earlier innovation NLL")
    _assert(float(abs(tr_a[0, 6] - tr_b[0, 6])) > 1e-9,
            "divergent controls did not reach the later innovation "
            "(test wiring broken)")
    return "mu_net input=48 (no dt); mu identical across dt; earlier innovation identical (err<1e-14), later innovation diverges under divergent controls"


def test_gradients_flow_all_arms():
    data = synthetic_fast_data(n_cells=6, n_events=400, rpt_every=40, seed=21)
    std = fit_control_standardizer(data, np.arange(data.n_cells))
    sampler = WindowSampler(data, np.arange(data.n_cells), 200,
                            burn_in="exact", batch_cells=2)
    batch = sampler.sample(random.Random(3))
    expect_params = ("mu_net.0.weight", "mu_base", "kappa_raw",
                     "sigma_ell_raw", "lambda_raw", "sigma_R_raw",
                     "obs_sigma_raw")
    summary = {}
    for arm_key in ("full", "noRateUpdate", "time", "noEll"):
        model = build_arm_model(arm_key, 22)
        model.set_control_standardizer(std["mean"], std["scale"])
        cfg = dict(ARM_CONFIGS[arm_key])
        cfg["arm_key"] = arm_key
        out = replay_windows_a3(model, batch, cfg)
        loss = out["loss_cell_macro"]
        _assert(bool(torch.isfinite(loss)), "%s loss not finite" % arm_key)
        model.zero_grad(set_to_none=True)
        loss.backward()
        norms = {}
        for name, p in model.named_parameters():
            g = p.grad
            if g is None:
                norms[name] = None
            else:
                norm = float(g.norm())
                norms[name] = norm
                _assert(math.isfinite(norm) and norm >= 0.0,
                        "%s non-finite grad in %s" % (name, arm_key))
        if arm_key in ("full", "noRateUpdate"):
            for name in expect_params:
                _assert(norms.get(name) is not None and norms[name] > 0.0,
                        "%s: %s grad missing/zero" % (arm_key, name))
        elif arm_key == "time":
            _assert(norms.get("mu_net.0.weight") is None,
                    "time arm should not train mu_net")
            _assert(norms.get("mu_base") is not None
                    and norms["mu_base"] > 0.0, "time arm mu_base grad")
        else:  # noEll
            _assert(norms.get("mu_net.0.weight") is None,
                    "noEll arm should not train mu_net")
            _assert(norms.get("kappa_raw") is None,
                    "noEll arm should not train kappa")
            _assert(norms.get("c_raw") is not None and norms["c_raw"] > 0.0,
                    "noEll c_raw grad missing")
            _assert(norms.get("obs_sigma_raw") is not None
                    and norms["obs_sigma_raw"] > 0.0,
                    "noEll obs_sigma grad missing")
        summary[arm_key] = norms
    return "grads flow in all 4 arms (full mu_net=%.2e, kappa=%.2e, sigma_y=%.2e; noEll c=%.2e; unused params get none)" % (
        summary["full"]["mu_net.0.weight"], summary["full"]["kappa_raw"],
        summary["full"]["obs_sigma_raw"], summary["noEll"]["c_raw"])


# --------------------------------------------------------- GO-gate fixtures
_EXPECT = {"window_events": 256, "burn_in": "exact", "burn_in_events": 128,
           "batch_cells": 8, "seed": 42}


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
    return path


def _valid_go(tmpdir, registry_path):
    manifest_path = os.path.join(tmpdir, "manifest_fixture.json")
    _write_json(manifest_path, {
        "prepared_npz": "SYNTHETIC_ONLY_no_npz_written_or_read.npz",
        "prepared_npz_sha256": "0" * 64,
        "note": "fixture stub: validation only hashes this manifest json; "
                "the self-check never opens any npz",
        "split": {"train_cells": ["synthetic_1"], "val_cells":
                  ["synthetic_2"]},
    })
    go = {
        "status": "APPROVED",
        "allow_fit": True,
        "allow_train": True,
        "scope": "A3 TRAIN/FIT: four-arm individual-rate state model (ell), "
                 "selection 100 + refit all125, exactly 8 fits in this GO",
        "request_id": "a3-selfcheck-go-0001",
        "issued_utc": "2026-10-24T00:00:00+00:00",
        "code_sha256": {
            "a3_model.py": hash_file(os.path.join(_HERE, "a3_model.py")),
            "a3_train.py": hash_file(os.path.join(_HERE, "a3_train.py")),
        },
        "max_steps": 3000,
        "arms": sorted(ARM_CONFIGS),
        "refit_scope": "all125",
        "seed": 42, "batch_cells": 8, "window_events": 256,
        "burn_in": "exact", "burn_in_events": 128,
        "lr": 1e-3, "weight_decay": 1e-4, "val_every": 50, "patience": 6,
        "threads": 8,
        "fits_in_this_go": 8,
        "prepared_manifest": manifest_path,
        "prepared_manifest_sha256": hash_file(manifest_path),
        "out_dir": os.path.join(tmpdir, "out_fresh"),
    }
    _ = registry_path
    return go, manifest_path


def _validate(go_obj, tmpdir, manifest_path, registry_path, arm="all",
              steps=100):
    path = _write_json(os.path.join(tmpdir, "go_current.json"), go_obj)
    return a3_train.validate_go_a3(path, steps, arm, manifest_path,
                                   registry_path, _EXPECT)


def test_go_accepts_wellformed_and_refuses_mutations():
    with tempfile.TemporaryDirectory() as tmp:
        registry = os.path.join(tmp, "registry_tmp.jsonl")
        base, manifest = _valid_go(tmp, registry)
        problems, go = _validate(base, tmp, manifest, registry)
        _assert(not problems and go is not None,
                "well-formed A3 GO rejected: %r" % problems)
        single_problems, _ = _validate(base, tmp, manifest, registry,
                                       arm="full")
        _assert(not single_problems,
                "single-arm validation of a four-arm GO failed")
        mutations = [
            ("status_pending", lambda g: g.update(status="PENDING")),
            ("no_allow_fit", lambda g: [g.pop(k) for k in
                                        ("allow_fit", "allow_train")]),
            ("consumed_marker", lambda g: g.update(
                consumed_utc="2026-10-23T00:00:00+00:00")),
            ("scope_without_A3", lambda g: g.update(
                scope="TRAIN/FIT four-arm model, 8 fits")),
            ("scope_without_trainfit", lambda g: g.update(
                scope="A3 evaluation only")),
            ("bad_a3_model_hash", lambda g: g["code_sha256"].update(
                **{"a3_model.py": "0" * 64})),
            ("a3_train_not_pinned", lambda g: g["code_sha256"].pop(
                "a3_train.py")),
            ("bad_manifest_sha", lambda g: g.update(
                prepared_manifest_sha256="1" * 64)),
            ("wrong_manifest_path", lambda g: g.update(
                prepared_manifest=os.path.join(tmp, "other.json"))),
            ("reused_request_id", None),  # handled below (needs a registry)
            ("refit_scope_wrong", lambda g: g.update(refit_scope="train100")),
            ("refit_scope_missing", lambda g: g.pop("refit_scope")),
            ("arms_incomplete", lambda g: g.update(arms=["full"])),
            ("max_steps_exceeded", lambda g: g.update(max_steps=50)),
            ("out_dir_exists", None),  # handled below (needs a real dir)
            ("window_mismatch", lambda g: g.update(window_events=128)),
            ("request_id_missing", lambda g: g.pop("request_id")),
        ]
        refused = []
        for name, mutate in mutations:
            go = copy.deepcopy(base)
            if name == "reused_request_id":
                reg2 = os.path.join(tmp, "registry_used.jsonl")
                a3_train.register_consumed_go(reg2, go["request_id"],
                                              "f" * 64, "2026-10-24T00:00:00")
                problems, _ = _validate(go, tmp, manifest, reg2)
            elif name == "out_dir_exists":
                existing = os.path.join(tmp, "out_exists")
                os.makedirs(existing)
                go["out_dir"] = existing
                problems, _ = _validate(go, tmp, manifest, registry)
            else:
                mutate(go)
                problems, _ = _validate(go, tmp, manifest, registry)
            _assert(problems, "mutation %r was ACCEPTED" % name)
            refused.append(name)
        # GO file missing
        problems, go = a3_train.validate_go_a3(
            os.path.join(tmp, "no_such_go.json"), 100, "all", manifest,
            registry, _EXPECT)
        _assert(problems and go is None, "missing GO file not refused")
        refused.append("go_file_missing")
        _assert(len(refused) >= 12,
                "expected >= 12 refused mutations, got %d" % len(refused))
        return "%d/18 mutations refused (hash, manifest, request_id reuse, " \
               "refit_scope, arms, budget, out_dir, window contract)" % len(refused)


def test_no_payload_open_audit():
    with tempfile.TemporaryDirectory() as tmp:
        with OpenAuditor() as aud:
            model = build_arm_model("full", 21)
            data = synthetic_fast_data(n_cells=4, n_events=300,
                                       rpt_every=70, seed=2)
            std = fit_control_standardizer(data, np.arange(data.n_cells))
            model.set_control_standardizer(std["mean"], std["scale"])
            sampler = WindowSampler(data, np.arange(data.n_cells), 128,
                                    burn_in="exact", batch_cells=2)
            batch = sampler.sample(random.Random(1))
            for arm_key in ARM_CONFIGS:
                cfg = dict(ARM_CONFIGS[arm_key])
                cfg["arm_key"] = arm_key
                out = replay_windows_a3(model, batch, cfg)
                model.zero_grad(set_to_none=True)
                out["loss_cell_macro"].backward()
            registry = os.path.join(tmp, "registry_tmp.jsonl")
            base, manifest = _valid_go(tmp, registry)
            problems, _ = _validate(base, tmp, manifest, registry)
            _assert(not problems, "GO validation inside audit failed")
            a3_train.register_consumed_go(registry, "audit-rid", "a" * 64,
                                          "2026-10-24T00:00:00+00:00")
            _assert(not a3_train.request_id_is_fresh("audit-rid", registry),
                    "registry check inside audit failed")
        recorded = aud.paths
        tmp_prefix = os.path.abspath(tmp)
        forbidden = [p for p in recorded
                     if _is_forbidden_path(p, tmp_prefix)]
        _assert(not forbidden, "forbidden open() during self-check: %r"
                % forbidden[:5])
        npz = [p for p in recorded if p.endswith(".npz")]
        _assert(not npz, "an npz was opened during the self-check: %r" % npz)
        n_tmp = sum(1 for p in recorded if p.startswith(tmp_prefix))
        n_code = sum(1 for p in recorded if p.startswith(_HERE))
        return "recorded %d open() calls: %d tmp fixtures, %d own code files, 0 forbidden, 0 npz" % (
            len(recorded), n_tmp, n_code)


def test_consumed_registry_append_and_duplicate_refusal():
    with tempfile.TemporaryDirectory() as tmp:
        registry = os.path.join(tmp, "registry_tmp.jsonl")
        _assert(a3_train.request_id_is_fresh("rid-A", registry),
                "fresh id refused on an empty registry")
        _assert(not os.path.exists(registry),
                "freshness check must not create the registry file")
        line = a3_train.register_consumed_go(registry, "rid-A", "deadbeef",
                                             "2026-10-24T00:00:00+00:00")
        rec = json.loads(line)
        _assert(set(rec) == {"request_id", "go_sha256", "finished_utc"},
                "registry line fields wrong: %r" % sorted(rec))
        _assert(not a3_train.request_id_is_fresh("rid-A", registry),
                "consumed id still reported fresh")
        _assert(a3_train.request_id_is_fresh("rid-B", registry),
                "unrelated id reported consumed")
        raised = False
        try:
            a3_train.register_consumed_go(registry, "rid-A", "x", "t")
        except RuntimeError:
            raised = True
        _assert(raised, "duplicate registration was not refused")
        with open(registry, "a", encoding="utf-8") as f:
            f.write("not-json\n")
        try:
            a3_train.load_consumed_request_ids(registry)
            raise AssertionError("malformed registry line accepted "
                                 "(fail-open)")
        except ValueError:
            pass
        with open(registry, "r", encoding="utf-8") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
        _assert(len(lines) == 2 and json.loads(lines[0])["request_id"]
                == "rid-A", "registry content corrupted")
        return "append-once verified (1 line, exact fields), duplicate refused, malformed line fail-closed"


def test_cell_macro_loss_and_anchor_exclusion():
    def make_seq(cell_id, n_cycles, rpts):
        origin = 1_700_000_000.0
        events = []
        t = origin
        r_at = {r[0]: r for r in rpts}
        for i in range(n_cycles):
            t += 0.3 * 604800.0
            ctl = [0.1 * ((j % 5) - 2) for j in range(CONTROL_DIM)]
            msk = [1.0] * CONTROL_DIM
            events.append({"kind": "cycle", "index": i,
                           "source_epoch": t, "available_epoch": t + 60.0,
                           "control": ctl, "control_mask": msk,
                           "dt_weeks": 0.0})
            if i in r_at:
                _, cap, sc = r_at[i]
                events.append({"kind": "rpt", "index": i,
                               "source_epoch": t + 3600.0,
                               "available_epoch": t + 3720.0,
                               "capacity_ah": cap, "score": sc,
                               "dt_weeks": 0.0})
        prev = origin
        for e in events:
            e["dt_weeks"] = (e["source_epoch"] - prev) / 604800.0
            prev = e["source_epoch"]
        return {"cell_id": cell_id, "q_ref_ah": 0.28,
                "anchor": {"index": 0, "capacity_ah": 0.28,
                           "source_epoch": origin,
                           "available_epoch": origin,
                           "n_valid_arrived": 1},
                "events": events}

    seqs = [make_seq("cellA", 40, [(10, 0.275, True), (20, 0.270, True),
                                   (30, 0.266, True)]),
            make_seq("cellB", 30, []),
            make_seq("cellC", 30, [(8, 0.276, False), (16, 0.272, True)])]
    data = FastA2Data.from_sequences(seqs)
    model = build_arm_model("full", 23).double()
    cfg = ARM_CONFIGS["full"]
    per = replay_cells_a3(model, data, [0, 1, 2], cfg)
    _assert(per[1] == 0.0, "cell without scored RPT must contribute 0")
    _, trace = replay_cells_a3(model, data, [0], cfg, want_trace=True)
    scored = [v for v in trace[0].tolist() if not math.isnan(v)]
    _assert(len(scored) == 3, "cellA scored count wrong")
    _assert(_close(per[0], sum(scored) / 3.0, atol=1e-12),
            "per-cell NLL != mean of its innovation NLLs")
    macro, per2 = eval_cell_macro_a3(model, data, [0, 1, 2], cfg)
    _assert(set(per2) == {0, 2},
            "eval included a cell without scored RPTs")
    _assert(_close(macro, (per[0] + per[2]) / 2.0, atol=1e-12),
            "cell-macro mean wrong")
    _, trace_c = replay_cells_a3(model, data, [2], cfg, want_trace=True)
    scored_c = [v for v in trace_c[2].tolist() if not math.isnan(v)]
    _assert(len(scored_c) == 1,
            "score=False RPT was scored (anchor/score exclusion broken)")
    _assert(_close(per[2], scored_c[0], atol=1e-12),
            "unscored RPT contributed to the cell NLL")
    return "cell-macro = mean over cells with scored RPTs; score=False RPT excluded; per-cell == mean of its NLLs (err<1e-12)"


def test_four_arm_forward_probe_finite():
    data = synthetic_fast_data(n_cells=4, n_events=600, rpt_every=90, seed=8)
    std = fit_control_standardizer(data, np.arange(data.n_cells))
    sampler = WindowSampler(data, np.arange(data.n_cells), 200,
                            burn_in="exact", batch_cells=4)
    batch = sampler.sample(random.Random(9))
    losses = {}
    for arm_key in sorted(ARM_CONFIGS):
        model = build_arm_model(arm_key, 24)
        model.set_control_standardizer(std["mean"], std["scale"])
        cfg = dict(ARM_CONFIGS[arm_key])
        cfg["arm_key"] = arm_key
        out = replay_windows_a3(model, batch, cfg)
        loss = float(out["loss_cell_macro"])
        _assert(math.isfinite(loss), "%s loss not finite" % arm_key)
        losses[arm_key] = loss
    _assert(abs(losses["full"] - losses["time"]) > 1e-9,
            "full and time losses identical on control-carrying data")
    kind = torch.ones(1, 3, dtype=torch.long)
    dt = torch.full((1, 3), 0.2, dtype=torch.float32)
    ctl = torch.randn(1, 3, CONTROL_DIM, dtype=torch.float32)
    msk = torch.ones_like(ctl)
    model_t = build_arm_model("time", 24)
    mu_time = _event_scalars_a3(model_t, kind, dt, ctl, msk, False)["mu"]
    _assert(float((mu_time - model_t.mu_base).abs().max()) == 0.0,
            "time arm mu not constant")
    return "all four arms finite on one synthetic batch: %s; full-vs-time delta=%.3e" % (
        ", ".join("%s=%.4f" % (k, v) for k, v in sorted(losses.items())),
        abs(losses["full"] - losses["time"]))


def test_train_loop_synthetic_smoke():
    """Selection -> frozen steps -> full refit, exercised end-to-end on
    synthetic cells only (no GO, no manifest, no files written)."""
    seqs = synthetic_sequences_for_windows(n_cells=6, n_cycles=200, seed=33)
    data = FastA2Data.from_sequences(seqs)
    idx = np.arange(data.n_cells)
    data.train_index = idx[:4]
    data.val_index = idx[4:]
    args = a3_train.parse_args(["--steps", "4", "--val-every", "2",
                                "--patience", "2", "--batch-cells", "2",
                                "--window-events", "128",
                                "--burn-in-events", "64"])
    _assert(args.refit_seed == 43, "refit sampling seed default must be 43")
    all_cells = np.sort(np.concatenate([data.train_index, data.val_index]))
    losses = {}
    for arm_key in sorted(ARM_CONFIGS):
        cfg = dict(ARM_CONFIGS[arm_key])
        cfg["arm_key"] = arm_key
        result = a3_train.train_one_arm(data, cfg, args, all_cells)
        model = result.pop("model")
        _assert(result["selected_steps"] >= 1, "%s: no selection step"
                % arm_key)
        _assert(result["n_fit_cells"] == {"selection": 4, "refit": 6},
                "%s: n_fit_cells wrong: %r" % (arm_key, result["n_fit_cells"]))
        _assert(result["refit_scope"] == "all125", "%s: refit_scope wrong"
                % arm_key)
        _assert(result["refit_sampling_seed"] == 43,
                "%s: refit sampling seed wrong" % arm_key)
        _assert("refit_standardizer_on_all_cells" in result,
                "%s: refit standardizer (all cells) missing" % arm_key)
        for name, p in model.named_parameters():
            _assert(bool(torch.isfinite(p).all()),
                    "%s: non-finite parameter %s" % (arm_key, name))
        losses[arm_key] = result["refit_last_train_loss"]
        _assert(math.isfinite(losses[arm_key]),
                "%s: non-finite refit loss" % arm_key)
    return "selection(4 cells, 4 steps, val on 2) -> frozen-steps refit(6 cells, seed 43) works for all arms; refit losses %s" % (
        ", ".join("%s=%.4f" % (k, v) for k, v in sorted(losses.items())))


FIXTURES = (
    ("softplus_positive_and_D_mean_monotone",
     test_softplus_positive_and_D_mean_monotone),
    ("semigroup_grid_invariance", test_semigroup_grid_invariance),
    ("joseph_update_symmetry_psd_kalman_equivalence",
     test_joseph_update_symmetry_psd_kalman_equivalence),
    ("ell_observability_posterior_shrinkage",
     test_ell_observability_posterior_shrinkage),
    ("four_arm_ablation_structure", test_four_arm_ablation_structure),
    ("window_loss_equals_full_replay", test_window_loss_equals_full_replay),
    ("ou_channels_closed_form", test_ou_channels_closed_form),
    ("sigma_semantics_std_not_variance",
     test_sigma_semantics_std_not_variance),
    ("prior_explicit_and_state_only_map",
     test_prior_explicit_and_state_only_map),
    ("dt_not_input_and_no_future_leak",
     test_dt_not_input_and_no_future_leak),
    ("gradients_flow_all_arms", test_gradients_flow_all_arms),
    ("go_accepts_wellformed_and_refuses_mutations",
     test_go_accepts_wellformed_and_refuses_mutations),
    ("no_payload_open_audit", test_no_payload_open_audit),
    ("consumed_registry_append_and_duplicate_refusal",
     test_consumed_registry_append_and_duplicate_refusal),
    ("cell_macro_loss_and_anchor_exclusion",
     test_cell_macro_loss_and_anchor_exclusion),
    ("four_arm_forward_probe_finite", test_four_arm_forward_probe_finite),
    ("train_loop_synthetic_smoke", test_train_loop_synthetic_smoke),
)


def run_all(verbose=True, audit=False):
    results = []
    auditor = OpenAuditor() if audit else None
    if auditor is not None:
        auditor.__enter__()
    try:
        for name, fn in FIXTURES:
            try:
                detail = fn()
                results.append({"name": name, "passed": True,
                                "detail": detail})
                if verbose:
                    print("[PASS] %-46s %s" % (name, detail))
            except Exception as exc:  # noqa: BLE001 - report every fixture
                results.append({"name": name, "passed": False,
                                "detail": str(exc)})
                if verbose:
                    print("[FAIL] %-46s %s" % (name, exc))
                    traceback.print_exc()
    finally:
        if auditor is not None:
            auditor.__exit__(None, None, None)
            forbidden = [p for p in auditor.paths
                         if _is_forbidden_path(p, tempfile.gettempdir())]
            if verbose:
                print("[AUDIT] global open() audit: %d paths recorded, "
                      "%d forbidden" % (len(auditor.paths), len(forbidden)))
            if forbidden:
                results.append({
                    "name": "global_no_payload_audit",
                    "passed": False,
                    "detail": "forbidden opens: %r" % forbidden[:5]})
    n_pass = sum(1 for r in results if r["passed"])
    if verbose:
        print("SUMMARY: %d passed, %d failed, %d total" %
              (n_pass, len(results) - n_pass, len(results)))
    return {"results": results, "n_pass": n_pass,
            "n_fail": len(results) - n_pass}


if __name__ == "__main__":
    res = run_all(verbose=True, audit=True)
    sys.exit(0 if res["n_fail"] == 0 else 1)
