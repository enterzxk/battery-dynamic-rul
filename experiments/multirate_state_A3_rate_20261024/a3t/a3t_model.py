"""A3-T: A3 state-space model with Student-t innovations (observation residuals).

Frozen design (experiments/multirate_state_A3_rate_20261024/a3t/, 2026-10-24).
Everything structural is REUSED from a3_model.A3StateModel (byte-frozen):

  * the state x = (D, ell, R), the frozen-linearization discretization (exact
    affine semigroup, carried (a, b)), the integrated-OU covariance closed
    forms, the four ablation arms (full / noRateUpdate / time / noEll) with
    behaviour flags only, the explicit anchor prior, the control summary /
    standardisation and the Joseph-form update geometry;

  * A3TStateModel is a SUBCLASS of A3StateModel.  The two model changes are
    additive parameters plus accessor overrides:

    1. Student-t innovation.  Each scored RPT innovation u_r is modelled as
           u_r ~ t(0, S_r, nu),   S_r = H_r P H_r' + sigma_y^2   (scale S_r),
       with degrees of freedom nu = nu_floor + softplus(nu_raw) > nu_floor = 2
       (documented lower bound: nu <= 2 has no posterior variance).  The
       innovation NLL is the negated exact Student-t log density,
           -lgamma((nu+1)/2) + lgamma(nu/2) + 0.5*log(nu*pi*S)
             + ((nu+1)/2)*log1p(u^2/(nu*S)),
       which converges to the A3 Gaussian NLL as nu -> inf (fixture).

    2. Learnable process-noise multipliers.  The EFFECTIVE process noises are
           sigma_ell_eff = sigma_ell_base * softplus(q_ell_mult_raw),
           sigma_R_eff  = sigma_R_base  * softplus(q_R_mult_raw)
       (both multipliers init exactly 1.0).  Because A3's propagation machinery
       (advance / _segment_advance / frozen_coeffs) reads sigma through the
       accessor, overriding sigma_ell()/sigma_R() routes the multiplier through
       ALL reused dynamics with zero code changes there.

MEASUREMENT UPDATE -- moment-matched (robust) Student-t update.
Model the t innovation via its Gamma scale mixture: u|xi ~ N(0, S/xi) with
xi ~ Gamma(nu/2, nu/2).  The posterior mean of the mixing weight given the
innovation is (conjugate, one EM/M-step in closed form)
    w = E[xi | u] = (nu + 1) / (nu + u^2 / S)   in  (0, (nu+1)/nu],
(w = 1 exactly at nu -> inf; w < 1 for large |u|, w slightly > 1 for tiny |u|).
The update then runs the UNCHANGED A3 Gaussian/Joseph geometry with the
innovation-weighted effective measurement variance
    R_eff = sigma_y^2 / w,   K = P H'/ (H P H' + R_eff),
    m1 = m + K u,  P1 = (I-KH)P(I-KH)' + K R_eff K'   (Joseph form),
including the noRateUpdate gain masking (ell component zeroed BEFORE the
Joseph update).  This is the standard robust-filtering approximation: a
Gaussian-form update whose covariance is corrected by the innovation weight.
Verified against the exact 1-D t posterior by quadrature (fixture): in the
measurement-dominated regime (H P H' <= 0.25 sigma_y^2) the moment-matched
mean tracks the exact t posterior mean to < 0.05 sigma_y and the variance to
< 0.05 sigma_y^2 over nu in {3,5,12}, |u| <= 6 sigma_y; the prior-dominated
regime degrades smoothly (documented approximation, not an identity).

Degeneration: nu -> inf (and multipliers 1) reduces A3-T to A3 exactly
(NLL, update and full replay agree to rounding; fixture).

This module is implementation-only: it never reads payload, processed
datasets, checkpoints or GO files.  All fixtures live in a3t_fixtures.py and
use synthetic tensors only.
"""
from __future__ import annotations

import math
import os
import sys

import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
_A3_DIR = os.path.dirname(_HERE)
_A2_DIR = os.path.join(os.path.dirname(_A3_DIR), "multirate_state_A2_20261022")
if not os.path.isdir(_A3_DIR):
    raise ImportError("A3 code directory not found at %s" % _A3_DIR)
if not os.path.isdir(_A2_DIR):
    raise ImportError("A2 code directory not found at %s" % _A2_DIR)
for _p in (_A3_DIR, _A2_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from a3_model import (  # noqa: E402  (reused, unchanged)
    ARM_CONFIGS, A3StateModel, CONTROL_DIM, LOG_2PI, VERSION as A3_VERSION,
    _PARAM_FLOOR, _event_scalars_a3, _inv_softplus, _segment_advance,
    _softplus_floor,
)

A3T_VERSION = "a3t-impl-20261024-r1"

# Documented a-priori choices (NOT tuned on any evaluation split): a moderate
# nu init lets the fit move either way; the hard floor nu > 2 keeps the t
# posterior variance finite (nu <= 2 is Cauchy-like, no variance); multiplier
# init exactly 1.0 makes A3-T start identical to A3; the weight floor only
# guards float32 overflow of sigma_y^2 / w for absurd (>1e6-sigma) innovations.
NU_FLOOR = 2.0
NU_INIT = 10.0
Q_MULT_INIT = 1.0
_W_FLOOR = 1e-6


class A3TStateModel(A3StateModel):
    """A3 three-state model with Student-t innovations and learnable process
    multipliers.  All A3 structure is inherited; only accessors are overridden
    and three additive parameters registered (after the parent's RNG draws, so
    the mu_net initialisation is bit-identical to A3 for the same seed)."""

    def __init__(self,
                 control_dim: int = CONTROL_DIM,
                 hidden: int = 32,
                 nu_init: float = NU_INIT,
                 nu_floor: float = NU_FLOOR,
                 q_ell_mult_init: float = Q_MULT_INIT,
                 q_r_mult_init: float = Q_MULT_INIT,
                 **kwargs) -> None:
        super().__init__(control_dim=control_dim, hidden=hidden, **kwargs)
        if not (math.isfinite(float(nu_floor)) and float(nu_floor) >= 2.0):
            raise ValueError("nu_floor must be >= 2 (finite posterior "
                             "variance requires nu > 2)")
        if not (float(nu_init) > float(nu_floor)):
            raise ValueError("nu_init must exceed nu_floor")
        for name, value in (("q_ell_mult_init", q_ell_mult_init),
                            ("q_r_mult_init", q_r_mult_init)):
            if value <= 0:
                raise ValueError("%s is a positive multiplier and must be > 0"
                                 % name)
        self.nu_floor = float(nu_floor)
        self.register_parameter("nu_raw", torch.nn.Parameter(torch.tensor(
            _inv_softplus(float(nu_init) - float(nu_floor)),
            dtype=torch.float32)))
        self.register_parameter("q_ell_mult_raw", torch.nn.Parameter(
            torch.tensor(_inv_softplus(float(q_ell_mult_init)),
                         dtype=torch.float32)))
        self.register_parameter("q_R_mult_raw", torch.nn.Parameter(
            torch.tensor(_inv_softplus(float(q_r_mult_init)),
                         dtype=torch.float32)))

    # ------------------------------------------------- t degrees of freedom
    def nu_df(self):
        """Student-t degrees of freedom nu = nu_floor + softplus(nu_raw) > 2."""
        return self.nu_floor + _softplus_floor(self.nu_raw)

    # --------------------------------------------- process-noise multipliers
    def sigma_ell_mult(self):
        """Learnable multiplier on the ell diffusion sigma (init exactly 1)."""
        return _softplus_floor(self.q_ell_mult_raw)

    def sigma_R_mult(self):
        """Learnable multiplier on the R diffusion sigma (init exactly 1)."""
        return _softplus_floor(self.q_R_mult_raw)

    def sigma_ell_base(self):
        """Parent (unmultiplied) ell diffusion sigma, 1/sqrt(week)."""
        return _softplus_floor(self.sigma_ell_raw)

    def sigma_R_base(self):
        """Parent (unmultiplied) R diffusion sigma, Ah/sqrt(week)."""
        return _softplus_floor(self.sigma_R_raw)

    def sigma_ell(self):
        """EFFECTIVE ell diffusion sigma = base * multiplier (routed through
        every reused A3 propagation routine)."""
        return self.sigma_ell_base() * self.sigma_ell_mult()

    def sigma_R(self):
        """EFFECTIVE R diffusion sigma = base * multiplier."""
        return self.sigma_R_base() * self.sigma_R_mult()

    # ------------------------------------------------------- t innovation NLL
    def t_weight(self, innovation, innovation_var):
        """Posterior mixing weight w = E[xi | u] = (nu+1)/(nu + u^2/S).

        w in (0, (nu+1)/nu]:  w -> 0 for outliers (update shuts down),
        w = (nu+1)/nu at u = 0, w -> 1 as nu -> inf (A3 limit).  The floor
        only prevents float32 overflow of sigma_y^2 / w.
        """
        nu = self.nu_df().to(innovation_var.dtype)
        z2 = innovation.square() / innovation_var
        return ((nu + 1.0) / (nu + z2)).clamp_min(_W_FLOOR)

    def nll_rpt_t(self, m, P, q_ref_ah, observed_capacity_ah):
        """Student-t innovation NLL; S is the scale-squared in Ah^2, nu > 2.

        nll = -lgamma((nu+1)/2) + lgamma(nu/2) + 0.5*log(nu*pi*S)
              + 0.5*(nu+1)*log1p(u^2/(nu*S))   -->  Gaussian NLL as nu -> inf
        (the negated t log density; equals -StudentT.log_prob exactly).
        """
        y = torch.as_tensor(observed_capacity_ah, device=m.device,
                            dtype=m.dtype).reshape(-1)
        b = m.shape[0]
        if y.numel() == 1:
            y = y.expand(b)
        mu, _, S, _ = self.capacity_moments(m, P, q_ref_ah)
        u = y - mu
        nu = self.nu_df().to(S.dtype)
        z2_over_nu = u.square() / (nu * S)
        return (-torch.lgamma((nu + 1.0) * 0.5) + torch.lgamma(nu * 0.5)
                + 0.5 * torch.log(nu * math.pi * S)
                + 0.5 * (nu + 1.0) * torch.log1p(z2_over_nu))

    # ------------------------------------------- moment-matched t update
    def correct_rpt_t(self, m, P, q_ref_ah, observed_capacity_ah,
                      rate_update: bool = True):
        """Joseph-form 3x3 RPT update with the innovation-weighted effective
        measurement variance R_eff = sigma_y^2 / w (A3 geometry, t weight).

        With rate_update=False the ell component of the gain is zeroed BEFORE
        the Joseph update exactly like A3.correct_rpt.  Returns
        (m1, P1, nll_t, diag) where nll_t is the t innovation NLL.
        """
        b = m.shape[0]
        y = torch.as_tensor(observed_capacity_ah, device=m.device,
                            dtype=m.dtype).reshape(-1)
        if y.numel() == 1:
            y = y.expand(b)
        if y.shape != (b,) or torch.any(~torch.isfinite(y)):
            raise ValueError("observed capacity shape/value error")
        mu, latent_var, S, H = self.capacity_moments(m, P, q_ref_ah)
        innovation = y - mu
        w = self.t_weight(innovation, S)
        rv_eff = self.obs_variance().to(dtype=m.dtype) / w
        S_eff = (latent_var + rv_eff).clamp_min(_PARAM_FLOOR)
        K = (P @ H[:, :, None]).squeeze(-1) / S_eff[:, None]
        if not rate_update:
            gain_mask = torch.tensor([1.0, 0.0, 1.0], device=m.device,
                                     dtype=m.dtype)
            K = K * gain_mask
        m1 = m + K * innovation[:, None]
        eye = torch.eye(3, device=m.device, dtype=m.dtype).expand(b, 3, 3)
        A = eye - K[:, :, None] * H[:, None, :]
        P1 = A @ P @ A.transpose(-1, -2) + \
            (K[:, :, None] * rv_eff[:, None, None]) @ K[:, None, :]
        P1 = 0.5 * (P1 + P1.transpose(-1, -2))
        cap_var_after = (H[:, None, :] @ P1 @ H[:, :, None]).reshape(-1) \
            .clamp_min(0.0)
        nu = self.nu_df().to(S.dtype)
        nll = (-torch.lgamma((nu + 1.0) * 0.5) + torch.lgamma(nu * 0.5)
               + 0.5 * torch.log(nu * math.pi * S)
               + 0.5 * (nu + 1.0)
               * torch.log1p(innovation.square() / (nu * S)))
        diag = {
            "predicted_capacity_ah": mu,
            "innovation_ah": innovation,
            "innovation_var_ah2": S,
            "t_weight": w,
            "effective_obs_var_ah2": rv_eff,
            "capacity_var_before_ah2": latent_var,
            "capacity_var_after_ah2": cap_var_after,
            "gain": K,
        }
        return m1, P1, nll, diag

    # ------------------------------------------------------------- diagnostics
    def model_summary(self):
        out = dict(super().model_summary())
        out.update({
            "version": A3T_VERSION,
            "a3_version": A3_VERSION,
            "nu": float(self.nu_df()),
            "nu_floor": float(self.nu_floor),
            "sigma_ell_base": float(self.sigma_ell_base()),
            "sigma_R_base": float(self.sigma_R_base()),
            "sigma_ell_mult": float(self.sigma_ell_mult()),
            "sigma_R_mult": float(self.sigma_R_mult()),
            "sigma_ell_effective": float(self.sigma_ell()),
            "sigma_R_effective": float(self.sigma_R()),
        })
        return out


# ===================================================================== replay
def _run_events_a3t(model, kind, dt, control, control_mask, y, score, q_ref,
                    m, P, cfg, frozen=None, collect_nll=True,
                    want_trace=False):
    """A3 event replay with t innovations: identical segment structure to
    a3_model._run_events_a3 (union RPT split points, carried frozen (a, b),
    per-cell scored mask); only the innovation NLL (Student-t) and the
    measurement update (correct_rpt_t) differ.  A parallel Gaussian-form NLL
    (same predictive mu/S) is accumulated for A3-comparable reporting.
    Returns (m, P, nll_sum, n_scored, frozen, trace, gauss_sum)."""
    B, T = kind.shape
    dtype = m.dtype
    nll_sum = torch.zeros(B, dtype=dtype, device=m.device)
    gauss_sum = torch.zeros(B, dtype=dtype, device=m.device)
    n_scored = torch.zeros(B, dtype=torch.long, device=m.device)
    trace = torch.full((B, T), float("nan"), dtype=dtype, device=m.device) \
        if want_trace else None
    if frozen is None:
        a_lin, b_gain = model.frozen_linearization(m[:, 1].detach())
    else:
        a_lin, b_gain = frozen
    if T == 0:
        return m, P, nll_sum, n_scored, (a_lin, b_gain), trace, gauss_sum
    scal = _event_scalars_a3(model, kind, dt, control, control_mask,
                             cfg["mu_from_control"])
    q_ref = q_ref.reshape(-1)
    y_all = y
    score_all = score
    start = 0
    for r in torch.nonzero((kind == 2).any(dim=0), as_tuple=False) \
            .flatten().tolist():
        m, P = _segment_advance(model, m, P, scal, start, r + 1, a_lin,
                                b_gain, cfg["ell_state"])
        is_rpt = kind[:, r] == 2
        hit = is_rpt & score_all[:, r]
        if bool(hit.any()):
            mu_cap, _, S, _ = model.capacity_moments(m, P, q_ref)
            nu_inn = y_all[:, r] - mu_cap
            step_nll = model.nll_rpt_t(m, P, q_ref, y_all[:, r])
            gauss_nll = 0.5 * (nu_inn.square() / S + torch.log(S) + LOG_2PI)
            if collect_nll:
                nll_sum = nll_sum + torch.where(hit, step_nll,
                                                torch.zeros_like(step_nll))
                gauss_sum = gauss_sum + torch.where(hit, gauss_nll,
                                                    torch.zeros_like(gauss_nll))
                n_scored = n_scored + hit.long()
            if want_trace:
                trace[:, r] = torch.where(hit, step_nll,
                                          torch.full_like(step_nll,
                                                          float("nan")))
            m_new, P_new, _, _ = model.correct_rpt_t(
                m, P, q_ref, y_all[:, r], rate_update=cfg["rate_update"])
            m = torch.where(hit[:, None], m_new, m)
            P = torch.where(hit[:, None, None], P_new, P)
            a_new, b_new = model.frozen_linearization(m[:, 1])
            a_lin = torch.where(hit, a_new, a_lin)
            b_gain = torch.where(hit, b_new, b_gain)
        start = r + 1
    if start < T:
        m, P = _segment_advance(model, m, P, scal, start, T, a_lin, b_gain,
                                cfg["ell_state"])
    return m, P, nll_sum, n_scored, (a_lin, b_gain), trace, gauss_sum


def _burn_in_state_a3t(model, batch, cfg, dtype, device, max_events=300000):
    """No-grad burn-in for one WindowBatch under the t filter (mirrors
    a3_model._burn_in_state_a3 with _run_events_a3t; results scattered back
    to the original batch order).  Returns (m, P, (a, b))."""
    B = batch.batch_size
    max_len = int(batch.burn_length.max())
    if max_len == 0:
        m, P = model.initial_state(B, device=device, dtype=dtype)
        a, b = model.frozen_linearization(m[:, 1])
        return m, P, (a, b)
    order = sorted(range(B), key=lambda k: int(batch.burn_length[k]))
    chunks, cur = [], []
    for k in order:
        trial = cur + [k]
        if cur and len(trial) * max(int(batch.burn_length[x])
                                    for x in trial) > max_events:
            chunks.append(cur)
            cur = [k]
        else:
            cur = trial
    chunks.append(cur)
    m_out = torch.empty(B, 3, dtype=dtype)
    P_out = torch.empty(B, 3, 3, dtype=dtype)
    a_out = torch.empty(B, dtype=dtype)
    b_out = torch.empty(B, dtype=dtype)
    with torch.no_grad():
        for chunk in chunks:
            n = len(chunk)
            L = max(int(batch.burn_length[k]) for k in chunk)
            kind = torch.zeros(n, L, dtype=torch.long)
            dt_ = torch.zeros(n, L, dtype=dtype)
            ctl = torch.zeros(n, L, model.control_dim, dtype=dtype)
            msk = torch.zeros(n, L, model.control_dim, dtype=dtype)
            y = torch.zeros(n, L, dtype=dtype)
            score = torch.zeros(n, L, dtype=torch.bool)
            q_ref = torch.zeros(n, dtype=dtype)
            for row, k in enumerate(chunk):
                i = int(batch.cell_index[k])
                st = int(batch.burn_start[k])
                ln = int(batch.burn_length[k])
                if ln:
                    off = L - ln
                    sl = batch.data.slice_tensors(i, st, st + ln)
                    kind[row, off:] = sl["kind"][0]
                    dt_[row, off:] = sl["dt"][0].to(dtype)
                    ctl[row, off:] = sl["control"][0].to(dtype)
                    msk[row, off:] = sl["control_mask"][0].to(dtype)
                    y[row, off:] = sl["y"][0].to(dtype)
                    score[row, off:] = sl["score"][0]
                q_ref[row] = batch.q_ref[k].to(dtype)
            m_c, P_c = model.initial_state(n, device=device, dtype=dtype)
            m_c, P_c, _, _, (a_c, b_c), _, _ = _run_events_a3t(
                model, kind.to(device), dt_.to(device), ctl.to(device),
                msk.to(device), y.to(device), score.to(device),
                q_ref.to(device), m_c, P_c, cfg, collect_nll=False)
            m_c = m_c.cpu()
            P_c = P_c.cpu()
            for row, k in enumerate(chunk):
                m_out[k] = m_c[row]
                P_out[k] = P_c[row]
                a_out[k] = a_c[row].cpu()
                b_out[k] = b_c[row].cpu()
    return m_out.to(device), P_out.to(device), (a_out.to(device),
                                                b_out.to(device))


def replay_windows_a3t(model, batch, cfg, state=None, return_states=False):
    """Windowed t-filter replay: no-grad burn-in, then scored window (grad
    enabled).  Same contract as a3_model.replay_windows_a3 plus the parallel
    Gaussian-form NLL.  Returns the cell-macro mean t innovation NLL loss,
    per-cell NLLs (t and Gaussian), scored counts and the final state."""
    p = next(model.parameters())
    dtype, device = p.dtype, p.device
    if state is None:
        m0, P0, frozen0 = _burn_in_state_a3t(model, batch, cfg, dtype, device)
    else:
        m0, P0, frozen0 = state
    m0 = m0.detach()
    P0 = P0.detach()
    frozen0 = (frozen0[0].detach(), frozen0[1].detach())
    m, P, nll_sum, n_scored, _, _, gauss_sum = _run_events_a3t(
        model, batch.kind.to(device), batch.dt.to(device=device, dtype=dtype),
        batch.control.to(device=device, dtype=dtype),
        batch.control_mask.to(device=device, dtype=dtype),
        batch.y.to(device=device, dtype=dtype), batch.score.to(device),
        batch.q_ref.to(device=device, dtype=dtype), m0, P0, cfg,
        frozen=frozen0, collect_nll=True)
    has = n_scored > 0
    per_cell = torch.where(has, nll_sum / n_scored.clamp_min(1).to(dtype),
                           torch.zeros_like(nll_sum))
    per_cell_g = torch.where(has, gauss_sum / n_scored.clamp_min(1).to(dtype),
                             torch.zeros_like(gauss_sum))
    loss = per_cell[has].mean() if bool(has.any()) else nll_sum.sum() * 0.0
    loss_g = per_cell_g[has].mean() if bool(has.any()) \
        else gauss_sum.sum() * 0.0
    out = {
        "loss_cell_macro": loss,
        "loss_cell_macro_gauss": loss_g,
        "per_cell_nll": per_cell,
        "per_cell_nll_gauss": per_cell_g,
        "n_scored": n_scored,
        "final_state_mean": m,
        "final_state_cov": P,
    }
    if return_states:
        out["window_start_mean"] = m0
        out["window_start_cov"] = P0
        out["window_start_frozen"] = frozen0
    return out


def _replay_cells_a3t(model, data, cells, cfg, want_trace=False):
    """Exact full-sequence t-filter replay.  Returns (t_per, gauss_per,
    traces): per-cell mean t NLL, per-cell mean Gaussian-form NLL (same
    predictive mu/S) and optional per-RPT-position t NLL traces."""
    from a2_fastdata import _chunk_by_length
    p = next(model.parameters())
    dtype, device = p.dtype, p.device
    t_per, g_per, traces = {}, {}, {}
    for chunk in _chunk_by_length(data, cells):
        B = len(chunk)
        T = max(int(data.counts[i]) for i in chunk)
        kind = torch.zeros(B, T, dtype=torch.long)
        dt = torch.zeros(B, T, dtype=dtype)
        control = torch.zeros(B, T, model.control_dim, dtype=dtype)
        mask = torch.zeros(B, T, model.control_dim, dtype=dtype)
        y = torch.zeros(B, T, dtype=dtype)
        score = torch.zeros(B, T, dtype=torch.bool)
        q_ref = torch.zeros(B, dtype=dtype)
        for row, i in enumerate(chunk):
            a, e = int(data.offsets[i]), int(data.offsets[i + 1])
            n = e - a
            kind[row, :n] = data.kind[a:e]
            dt[row, :n] = data.dt[a:e]
            control[row, :n] = data.control[a:e]
            mask[row, :n] = data.control_mask[a:e]
            y[row, :n] = data.y[a:e]
            score[row, :n] = data.score[a:e]
            q_ref[row] = data.q_ref[i]
        m_init, P_init = model.initial_state(B, device=device, dtype=dtype)
        _, _, nll_sum, n_scored, _, trace, gauss_sum = _run_events_a3t(
            model, kind.to(device), dt.to(device), control.to(device),
            mask.to(device), y.to(device), score.to(device),
            q_ref.to(device), m_init, P_init, cfg, collect_nll=True,
            want_trace=want_trace)
        per = torch.where(n_scored > 0,
                          nll_sum / n_scored.clamp_min(1).to(dtype),
                          torch.zeros_like(nll_sum))
        per_g = torch.where(n_scored > 0,
                            gauss_sum / n_scored.clamp_min(1).to(dtype),
                            torch.zeros_like(gauss_sum))
        for row, i in enumerate(chunk):
            t_per[int(i)] = float(per[row])
            g_per[int(i)] = float(per_g[row])
            if want_trace:
                traces[int(i)] = trace[row].detach().cpu()
    return t_per, g_per, traces


def replay_cells_a3t(model, data, cells, cfg, want_trace=False):
    """Per-cell mean t innovation NLL over full sequences (A3 contract)."""
    t_per, _, traces = _replay_cells_a3t(model, data, cells, cfg,
                                         want_trace=want_trace)
    if want_trace:
        return t_per, traces
    return t_per


def eval_cell_macro_a3t(model, data, cells, cfg):
    """Cell-macro mean t innovation NLL (cells with >= 1 scored RPT)."""
    scored = [int(i) for i in cells
              if len(data.scored_positions(int(i))) > 0]
    if not scored:
        return float("nan"), {}
    per = replay_cells_a3t(model, data, scored, cfg)
    return float(sum(per.values()) / len(per)), per


def eval_pair_cell_macro_a3t(model, data, cells, cfg):
    """Both the t and the Gaussian-form cell-macro NLL on the SAME cells
    (same exclusion rule) for direct A3-comparable reporting."""
    scored = [int(i) for i in cells
              if len(data.scored_positions(int(i))) > 0]
    if not scored:
        return {"nll_t": float("nan"), "nll_gauss": float("nan"),
                "n_cells_scored": 0, "per_cell_t": {}}
    t_per, g_per, _ = _replay_cells_a3t(model, data, scored, cfg)
    return {
        "nll_t": float(sum(t_per.values()) / len(t_per)),
        "nll_gauss": float(sum(g_per.values()) / len(g_per)),
        "n_cells_scored": len(scored),
        "per_cell_t": t_per,
    }


def build_model_t(seed: int = 42, **kwargs) -> A3TStateModel:
    """Deterministically initialised A3-T model (mu_net init bit-identical to
    A3's build_model for the same seed; extra parameters are constants)."""
    torch.manual_seed(int(seed))
    return A3TStateModel(**kwargs)


def build_arm_model_t(arm_key, seed=42, **kwargs):
    """A3-T model for one arm: the SAME ARM_CONFIGS as A3 (behaviour flags
    only), with the arm's structural prior overrides applied."""
    cfg = ARM_CONFIGS[arm_key]
    if cfg.get("prior_sd_ell") is not None:
        kwargs.setdefault("prior_sd_ell", cfg["prior_sd_ell"])
    return build_model_t(seed, **kwargs)
