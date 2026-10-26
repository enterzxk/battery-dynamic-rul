"""A3 state-space model: individual degradation-rate state (ell).

Frozen design (experiments/multirate_state_A3_rate_20261024/PROTOCOL.md, 2026-10-24).

State x = (D, ell, R) with explicit initial prior at the anchor:
    dD     = softplus(ell) * dt          (mean drift strictly positive)
    dell   = -kappa * (ell - mu_theta(u)) * dt + sigma_ell * dW1
    dR     = -lambda * R * dt + sigma_R * dW2
    y      = Q_ref * exp(-D) + R + eps,  eps ~ N(0, sigma_y^2)

kappa = softplus(kappa_raw), sigma_ell = softplus(sigma_ell_raw),
lambda = softplus(lambda_raw), sigma_R = softplus(sigma_R_raw),
sigma_y = softplus(obs_sigma_raw) are global softplus parameters (no control
input, no dt input).  mu_theta(u) is the only control-dependent piece: a small
network over the SAME standardised 24-d past-only cycle-control summary and its
missingness mask that A2 uses (no dt column, no future input), offset by the
shared scalar mu_base so the "time" arm (mu = mu_0 = mu_base) is nested in the
"full" arm.

UNITS AND SIGMA DISCIPLINE (same as A2, corrected 2026-10-22):
Every noise quantity produced by the model is a STANDARD DEVIATION.  Variances
are always the explicit square sigma**2 (sigma_y^2 in Ah^2, variance rates
sigma_ell^2 and sigma_R^2 per week).  The Gaussian NLL is
0.5*(nu^2/S + log S + log 2*pi) with S a variance in Ah^2.  Nothing is ever
squared twice.  D and ell are dimensionless; rates are 1/week.

DISCRETIZATION -- exact affine semigroup under a frozen linearization.
softplus(ell) is nonlinear in the state, so each inter-update segment is
propagated with the drift linearized ONCE at the segment's last measurement
update (or at the anchor prior before the first update):
    dD = (a + b*ell) dt,   a = softplus(l0) - b*l0,   b = sigmoid(l0),
and the resulting linear time-invariant SDE (piecewise-constant mu per event;
noise entering ell and R only, coupled into D through the frozen gain b) is
integrated IN CLOSED FORM over the segment.  Consequences:
  * the frozen-coefficient discretization is an EXACT affine semigroup:
    one shot over [0, t1+t2] equals the composition of [0,t1] and [t1,t1+t2]
    to float64 rounding (< 1e-10; fixture semigroup_grid_invariance);
  * the linearization (a, b) is CARRIED state, refreshed only at measurement
    updates.  A window whose burn-in is exact therefore starts from exactly the
    full-replay state AND the same carried (a, b), so window losses equal the
    corresponding segment of the full replay (fixture window_loss_equals_full);
  * a batched replay may split a cell's segment at OTHER cells' update
    positions; with the carried (a, b) this composition is exact (same
    semigroup property), so batching never changes a cell's filter.

Covariance prediction uses the exact block closed forms of the frozen linear
SDE (integrated-OU covariances; series fallback for kappa*T < 1e-3 against
catastrophic cancellation).  Measurement update: sequential RPT innovation NLL
followed by the 3x3 Joseph-form update of (D, ell, R); ell has no direct
observation (H_ell = 0) and is informed only through its correlation with D
built by the dynamics.  The Joseph form keeps P symmetric positive definite;
with rate_update=False the ell component of the Kalman gain is zeroed before
the Joseph update, so ell receives neither mean nor (direct) variance
information from measurements.

ARMS (ARM_CONFIGS; one shared parameterisation, behaviour flags only):
    full          mu from control, ell measured-updated
    noRateUpdate  mu from control, ell NOT measured-updated (only D, R)
    time          mu = mu_0 (control masked), ell measured-updated
    noEll         ell removed: ell = softplus(c) point mass, dD = c*dt
                  exactly (no ell noise, no ell update; D is still corrected
                  by RPT updates through its anchor prior variance).  This is
                  the A2-type degenerate control arm.

This module is implementation-only: it never reads payload, processed
datasets, checkpoints or GO files.  All fixtures live in a3_fixtures.py and
use synthetic tensors only.

NOTE FOR THE CONTROLLER (found while reusing A2 code, A2 untouched):
a2_fastdata._burn_in_state returns burn-in rows concatenated in chunk
(sorted-by-length) order WITHOUT scattering back to the original batch order,
so with mixed burn lengths the burn-in states are assigned to the wrong batch
rows (verified on synthetic data: rows follow the sorted order to 1e-17).
A3's _burn_in_state_a3 below scatters results back explicitly.
"""
from __future__ import annotations

import math
import os
import sys

import torch
from torch import nn
import torch.nn.functional as F

_HERE = os.path.dirname(os.path.abspath(__file__))
_A2_DIR = os.path.join(os.path.dirname(_HERE), "multirate_state_A2_20261022")
if not os.path.isdir(_A2_DIR):
    raise ImportError("A2 code directory not found at %s" % _A2_DIR)
if _A2_DIR not in sys.path:
    sys.path.insert(0, _A2_DIR)

from a2_fastdata import _affine_scan  # reused unchanged from A2 (no rewrite)

VERSION = "a3-impl-20261024-r1"

CONTROL_DIM = 24
STATE_DIM = 3
WEEK_SECONDS = 604800.0
LOG_2PI = math.log(2.0 * math.pi)

# Numerical floor for positive softplus parameters.  Far below every physical
# scale in this model (rates ~1e-3..1/week, sigmas ~1e-3..1); it only prevents
# float32 underflow to exactly zero (division by kappa, log of variance).
_PARAM_FLOOR = 1e-8

# Initial values are documented a-priori choices from A2/A1 evidence
# (Q_ref ~ 0.28 Ah, sensor-noise floor sigma_y ~ 2e-3 Ah, D rate ~ 3e-3/week,
# R relaxation ~ 0.05/week, sigma_R ~ 2e-3 Ah/sqrt(week)); NOT tuned on any
# evaluation split.  ell lives in log-rate space: softplus(-5.8) ~ 3e-3/week.
_KAPPA_INIT_PER_WEEK = 0.25
_SIGMA_ELL_INIT = 0.5
_LAMBDA_INIT_PER_WEEK = 0.049
_SIGMA_R_INIT_AH = 2e-3
_SIGMA_OBS_INIT_AH = 2e-3
_C_RATE_INIT_PER_WEEK = 3e-3
_PRIOR_MEAN_ELL = -5.8
_PRIOR_SD_ELL = 1.0
_PRIOR_SD_D = 5e-3
_PRIOR_SD_R = 5e-3

ARM_CONFIGS = {
    "full": {
        "label": "A3_full",
        "mu_from_control": True,
        "rate_update": True,
        "ell_state": True,
        "prior_sd_ell": None,
        "description": "individual rate state ell driven by mu_theta(u), "
                       "ell measured-updated through the D correlation",
    },
    "noRateUpdate": {
        "label": "A3_no_rate_update",
        "mu_from_control": True,
        "rate_update": False,
        "ell_state": True,
        "prior_sd_ell": None,
        "description": "same as full but the ell component of the Kalman gain "
                       "is zeroed: only D and R accept measurement updates",
    },
    "time": {
        "label": "A3_time",
        "mu_from_control": False,
        "rate_update": True,
        "ell_state": True,
        "prior_sd_ell": None,
        "description": "mu_theta(u) replaced by the constant mu_0 = mu_base "
                       "(control masked), ell measured-updated",
    },
    "noEll": {
        "label": "A3_no_ell",
        "mu_from_control": False,
        "rate_update": False,
        "ell_state": False,
        "prior_sd_ell": 0.0,
        "description": "ell removed: ell = softplus(c) point mass, dD = c*dt "
                       "exactly; A2-type degenerate control arm.  The ell "
                       "prior variance is structurally zero (point mass) so "
                       "the Joseph update cannot leak phantom ell variance "
                       "into the capacity covariance.",
    },
}


def build_arm_model(arm_key, seed=42, **kwargs):
    """Model for one arm: identical initialisation, with the arm's structural
    prior overrides applied (noEll collapses the ell prior to a point mass)."""
    cfg = ARM_CONFIGS[arm_key]
    if cfg.get("prior_sd_ell") is not None:
        kwargs.setdefault("prior_sd_ell", cfg["prior_sd_ell"])
    return build_model(seed, **kwargs)


def _softplus_floor(raw):
    return F.softplus(raw).clamp_min(_PARAM_FLOOR)


class A3StateModel(nn.Module):
    """Three-dimensional continuous-time capacity state (D, ell, R)."""

    def __init__(self,
                 control_dim: int = CONTROL_DIM,
                 hidden: int = 32,
                 kappa_init: float = _KAPPA_INIT_PER_WEEK,
                 sigma_ell_init: float = _SIGMA_ELL_INIT,
                 lambda_init: float = _LAMBDA_INIT_PER_WEEK,
                 sigma_r_init_ah: float = _SIGMA_R_INIT_AH,
                 obs_sigma_init_ah: float = _SIGMA_OBS_INIT_AH,
                 c_rate_init: float = _C_RATE_INIT_PER_WEEK,
                 prior_mean_ell: float = _PRIOR_MEAN_ELL,
                 prior_sd_ell: float = _PRIOR_SD_ELL,
                 prior_sd_d: float = _PRIOR_SD_D,
                 prior_sd_r: float = _PRIOR_SD_R) -> None:
        super().__init__()
        for name, value in (("kappa_init", kappa_init),
                            ("sigma_ell_init", sigma_ell_init),
                            ("lambda_init", lambda_init),
                            ("sigma_r_init_ah", sigma_r_init_ah),
                            ("obs_sigma_init_ah", obs_sigma_init_ah),
                            ("c_rate_init", c_rate_init)):
            if value <= 0:
                raise ValueError("%s is a standard deviation or rate and must "
                                 "be > 0" % name)
        for name, value in (("prior_sd_ell", prior_sd_ell),
                            ("prior_sd_d", prior_sd_d),
                            ("prior_sd_r", prior_sd_r)):
            if value < 0:
                raise ValueError("%s must be >= 0" % name)
        self.control_dim = int(control_dim)
        self.hidden = int(hidden)

        # mu_theta(u): ONLY the cycle-control summary and its mask enter the
        # network (2*control_dim inputs).  No dt column, by design.
        self.mu_net = nn.Sequential(
            nn.Linear(2 * self.control_dim, self.hidden), nn.SiLU(),
            nn.Linear(self.hidden, self.hidden), nn.SiLU(),
            nn.Linear(self.hidden, 1),
        )
        # Shared OU target offset: the time arm uses exactly this scalar.
        self.mu_base = nn.Parameter(
            torch.tensor(float(prior_mean_ell), dtype=torch.float32))
        # Softplus logits for strictly positive global parameters.
        self.register_parameter("kappa_raw", nn.Parameter(torch.tensor(
            _inv_softplus(kappa_init), dtype=torch.float32)))
        self.register_parameter("sigma_ell_raw", nn.Parameter(torch.tensor(
            _inv_softplus(sigma_ell_init), dtype=torch.float32)))
        self.register_parameter("lambda_raw", nn.Parameter(torch.tensor(
            _inv_softplus(lambda_init), dtype=torch.float32)))
        self.register_parameter("sigma_R_raw", nn.Parameter(torch.tensor(
            _inv_softplus(sigma_r_init_ah), dtype=torch.float32)))
        # Raw logit; softplus(raw) is the RPT observation SIGMA in Ah.
        self.register_parameter("obs_sigma_raw", nn.Parameter(torch.tensor(
            _inv_softplus(obs_sigma_init_ah), dtype=torch.float32)))
        # noEll arm: dD = c*dt with c = softplus(c_raw).
        self.register_parameter("c_raw", nn.Parameter(torch.tensor(
            _inv_softplus(c_rate_init), dtype=torch.float32)))

        # Explicit, fixed initial prior at the anchor (D = R = 0 because Q_ref
        # is the anchor measurement; ell gets a documented diffuse log-rate
        # prior).  Not learned, not taken from any future input.
        self.register_buffer("prior_mean", torch.tensor(
            [0.0, float(prior_mean_ell), 0.0], dtype=torch.float32))
        self.register_buffer("prior_cov", torch.diag(torch.tensor(
            [prior_sd_d ** 2, prior_sd_ell ** 2, prior_sd_r ** 2],
            dtype=torch.float32)))
        # Train-only control standardisation; identity until fitted.
        self.register_buffer("control_mean",
                             torch.zeros(self.control_dim, dtype=torch.float32))
        self.register_buffer("control_scale",
                             torch.ones(self.control_dim, dtype=torch.float32))
        self.register_buffer("control_n_constant_skipped",
                             torch.zeros((), dtype=torch.long))

    # ------------------------------------------------------- positive params
    def kappa(self):
        """OU relaxation rate of ell, 1/week (softplus, floored)."""
        return _softplus_floor(self.kappa_raw)

    def sigma_ell(self):
        """ell diffusion STANDARD DEVIATION, 1/sqrt(week)."""
        return _softplus_floor(self.sigma_ell_raw)

    def lam(self):
        """OU relaxation rate of R, 1/week."""
        return _softplus_floor(self.lambda_raw)

    def sigma_R(self):
        """R diffusion STANDARD DEVIATION, Ah/sqrt(week)."""
        return _softplus_floor(self.sigma_R_raw)

    def obs_sigma(self):
        """RPT observation STANDARD DEVIATION in Ah."""
        return _softplus_floor(self.obs_sigma_raw)

    def obs_variance(self):
        """RPT observation variance in Ah^2 == sigma_y**2 (explicit square)."""
        return self.obs_sigma().square()

    def c_rate(self):
        """noEll arm drift c = softplus(c_raw), 1/week (dD = c*dt)."""
        return _softplus_floor(self.c_raw)

    # ------------------------------------------------------------------ prior
    def initial_state(self, batch: int = 1, device=None, dtype=None):
        """Return (m, P) expanded from the explicit anchor prior."""
        p = next(self.parameters())
        device = device or p.device
        dtype = dtype or p.dtype
        m = self.prior_mean.to(device=device, dtype=dtype) \
            .reshape(1, 3).expand(batch, 3).clone()
        P = self.prior_cov.to(device=device, dtype=dtype) \
            .reshape(1, 3, 3).expand(batch, 3, 3).clone()
        return m, P

    # --------------------------------------------------------- standardisation
    def set_control_standardizer(self, mean, scale) -> None:
        mean = torch.as_tensor(mean, dtype=torch.float32).reshape(-1)
        scale = torch.as_tensor(scale, dtype=torch.float32).reshape(-1)
        if mean.numel() != self.control_dim or scale.numel() != self.control_dim:
            raise ValueError("standardizer dimension mismatch")
        if not torch.all(torch.isfinite(mean)):
            raise ValueError("non-finite control mean")
        scale = torch.where(torch.isfinite(scale) & (scale > 1e-8), scale,
                            torch.ones_like(scale))
        self.register_buffer("control_mean", mean.clone())
        self.register_buffer("control_scale", scale.clone())

    def standardize_control(self, x):
        x = torch.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        return (x - self.control_mean.to(x.dtype)) / self.control_scale.to(x.dtype)

    # ----------------------------------------------------------- mu_theta(u)
    def mu_events(self, kind, control, control_mask, mu_from_control: bool):
        """Per-event OU target mu [B, T] from ONE batched network call.

        Cycle events contribute their standardised past-only control summary
        and mask; non-cycle events and the masked-out time arm contribute the
        constant mu_0 path (control masked exactly like A2's use_cycle=False).
        """
        B, T = kind.shape
        dtype = control.dtype if control is not None else \
            next(self.parameters()).dtype
        if not mu_from_control:
            return self.mu_base.to(dtype).reshape(1, 1).expand(B, T)
        zero_c = torch.zeros_like(control)
        zero_m = torch.zeros_like(control_mask)
        is_cycle = (kind == 1).unsqueeze(-1)
        ctl = torch.where(is_cycle, control, zero_c)
        msk = torch.where(is_cycle, control_mask, zero_m).clamp(0.0, 1.0)
        x = self.standardize_control(ctl)
        raw = self.mu_net(torch.cat([x * msk, msk], dim=-1))[..., 0]
        return self.mu_base.to(dtype) + raw

    def mu_point(self, control, control_mask, mu_from_control: bool):
        """mu for a single control vector [B] (test/dynamics API)."""
        B = control.shape[0] if control is not None else 1
        dtype = next(self.parameters()).dtype
        if not mu_from_control:
            return self.mu_base.to(dtype).reshape(1).expand(B)
        if control is None:
            control = torch.zeros(B, self.control_dim, dtype=dtype)
            control_mask = torch.zeros_like(control)
        msk = torch.as_tensor(control_mask, dtype=dtype,
                              device=control.device).clamp(0.0, 1.0)
        x = self.standardize_control(control.to(dtype))
        raw = self.mu_net(torch.cat([x * msk, msk], dim=-1))[..., 0]
        return self.mu_base.to(dtype) + raw

    # ------------------------------------------------------- linearization
    def frozen_linearization(self, ell_mean):
        """Frozen drift coefficients (a, b) of dD = (a + b*ell) dt around
        ell = ell_mean: b = sigmoid(ell_mean), a = softplus(ell_mean) - b*ell_mean."""
        ell_mean = torch.as_tensor(ell_mean)
        b = torch.sigmoid(ell_mean)
        a = F.softplus(ell_mean) - b * ell_mean
        return a, b

    def frozen_coeffs(self, ell_lin, mu):
        """Coefficient dict for the frozen linear SDE with constant mu."""
        ell_lin = torch.as_tensor(ell_lin, dtype=torch.float64)
        a, b = self.frozen_linearization(ell_lin)
        return {
            "kappa": self.kappa().double(),
            "sigma_ell2": self.sigma_ell().double().square(),
            "lam": self.lam().double(),
            "sigma_R2": self.sigma_R().double().square(),
            "a": a, "b": b, "mu": torch.as_tensor(mu, dtype=torch.float64),
        }

    # -------------------------------------------------------------- dynamics
    def advance(self, m, P, dt_weeks, control=None, control_mask=None,
                cfg=None):
        """Single-interval propagation (test/dynamics API).

        Treats the interval as one cycle event carrying `control`; the
        linearization is frozen at the interval start (the same convention the
        segment engine uses at measurement updates).
        """
        cfg = cfg or ARM_CONFIGS["full"]
        if m.shape[-1] != 3 or P.shape[-2:] != (3, 3):
            raise ValueError("state shape mismatch")
        b = m.shape[0]
        dt = torch.as_tensor(dt_weeks, device=m.device, dtype=m.dtype) \
            .reshape(-1)
        if dt.numel() == 1:
            dt = dt.expand(b)
        if dt.shape != (b,) or torch.any(~torch.isfinite(dt)) or \
                torch.any(dt < 0):
            raise ValueError("dt must be finite, non-negative, shape (B,)")
        dtype = m.dtype
        kind = torch.ones((b, 1), dtype=torch.long, device=m.device)
        dt_t = dt.reshape(b, 1)
        if control is None:
            ctl = torch.zeros((b, 1, self.control_dim), dtype=dtype,
                              device=m.device)
            msk = torch.zeros_like(ctl)
        else:
            ctl = torch.as_tensor(control, device=m.device, dtype=dtype) \
                .reshape(b, 1, self.control_dim)
            msk = torch.as_tensor(control_mask, device=m.device, dtype=dtype) \
                .reshape(b, 1, self.control_dim)
        scal = _event_scalars_a3(self, kind, dt_t, ctl, msk,
                                 cfg["mu_from_control"])
        a_lin, b_gain = self.frozen_linearization(m[:, 1])
        m1, P1 = _segment_advance(self, m, P, scal, 0, 1, a_lin, b_gain,
                                  cfg["ell_state"])
        return m1, P1

    def advance_from_coeffs(self, m, P, dt_weeks, coeffs):
        """Exact affine-semigroup step of the frozen linear SDE (constant mu).

        One shot over dt equals the composition of any partition of dt with
        the same coefficients, to float64 rounding.  Used by the grid
        invariance fixture.
        """
        if m.shape[-1] != 3 or P.shape[-2:] != (3, 3):
            raise ValueError("state shape mismatch")
        dtype = m.dtype
        kap = coeffs["kappa"].to(dtype)
        s2 = coeffs["sigma_ell2"].to(dtype)
        lam = coeffs["lam"].to(dtype)
        sR2 = coeffs["sigma_R2"].to(dtype)
        a = coeffs["a"].to(dtype)
        b = coeffs["b"].to(dtype)
        mu = coeffs["mu"].to(dtype)
        dt = torch.as_tensor(dt_weeks, device=m.device, dtype=dtype)
        alpha = torch.exp(-kap * dt)
        beta = torch.exp(-lam * dt)
        phi = -torch.expm1(-kap * dt) / kap
        w = b * phi
        c_d = a * dt + b * mu * (dt - phi)
        m1 = torch.stack([
            m[..., 0] + w * m[..., 1] + c_d,
            alpha * m[..., 1] + (1.0 - alpha) * mu,
            beta * m[..., 2],
        ], dim=-1)
        q_ell = s2 * (-torch.expm1(-2.0 * kap * dt)) / (2.0 * kap)
        q_R = sR2 * (-torch.expm1(-2.0 * lam * dt)) / (2.0 * lam)
        phi_T = phi
        i2_T = q_ell / s2
        x = kap * dt
        small = x < 1e-3
        cross = torch.where(
            small,
            dt * dt * (0.5 - 0.5 * x + 7.0 * x.square() / 24.0),
            (phi_T - i2_T) / kap)
        h = torch.where(
            small,
            dt ** 3 * (1.0 / 3.0 - 7.0 * x / 12.0 + 13.0 * x.square() / 20.0),
            (dt - 2.0 * phi_T + i2_T) / kap.square())
        q_DD = b.square() * s2 * h
        q_Dell = b * s2 * cross
        eye = torch.eye(3, device=m.device, dtype=dtype)
        F = eye.clone()
        F[..., 0, 1] = w
        F[..., 1, 1] = alpha
        F[..., 2, 2] = beta
        Q = torch.zeros((3, 3), device=m.device, dtype=dtype) \
            .expand(m.shape[:-1] + (3, 3)).clone()
        Q[..., 0, 0] = q_DD
        Q[..., 0, 1] = q_Dell
        Q[..., 1, 0] = q_Dell
        Q[..., 1, 1] = q_ell
        Q[..., 2, 2] = q_R
        P1 = F @ P @ F.transpose(-1, -2) + Q
        P1 = 0.5 * (P1 + P1.transpose(-1, -2))
        return m1, P1

    # -------------------------------------------------------------- capacity
    def capacity_moments(self, m, P, q_ref_ah):
        """State-only capacity mean/variance; no learned readout exists.

        Returns (mean Ah, latent variance Ah^2 = HPH^T, total variance Ah^2,
        H) with H = [-Q_ref*exp(-m_D), 0, 1] in (D, ell, R) ordering: R is
        observed, ell has NO direct observation and is informed only through
        its dynamics-built correlation with D.
        """
        b = m.shape[0]
        q0 = torch.as_tensor(q_ref_ah, device=m.device, dtype=m.dtype) \
            .reshape(-1)
        if q0.numel() == 1:
            q0 = q0.expand(b)
        if q0.shape != (b,) or torch.any(~torch.isfinite(q0)) or \
                torch.any(q0 <= 0):
            raise ValueError("q_ref must be finite and positive")
        q_det = q0 * torch.exp(-m[:, 0])
        mu = q_det + m[:, 2]
        H = torch.stack([-q_det, torch.zeros_like(q_det),
                         torch.ones_like(q_det)], dim=-1)
        latent_var = (H[:, None, :] @ P @ H[:, :, None]).reshape(-1) \
            .clamp_min(0.0)
        rv = self.obs_variance().to(dtype=m.dtype).reshape(-1)
        total_var = latent_var + rv
        return mu, latent_var, total_var, H

    def correct_rpt(self, m, P, q_ref_ah, observed_capacity_ah,
                    rate_update: bool = True):
        """Joseph-form 3x3 capacity measurement update; returns innovation NLL.

        With rate_update=False (arm noRateUpdate) the ell component of the
        Kalman gain is zeroed BEFORE the Joseph update, so ell receives no
        measurement information while the joint covariance stays PSD.
        """
        b = m.shape[0]
        y = torch.as_tensor(observed_capacity_ah, device=m.device,
                            dtype=m.dtype).reshape(-1)
        if y.numel() == 1:
            y = y.expand(b)
        if y.shape != (b,) or torch.any(~torch.isfinite(y)):
            raise ValueError("observed capacity shape/value error")
        mu, latent_var, S, H = self.capacity_moments(m, P, q_ref_ah)
        rv = (S - latent_var).clamp_min(1e-14)
        innovation = y - mu
        K = (P @ H[:, :, None]).squeeze(-1) / S[:, None]
        if not rate_update:
            gain_mask = torch.tensor([1.0, 0.0, 1.0], device=m.device,
                                     dtype=m.dtype)
            K = K * gain_mask
        m1 = m + K * innovation[:, None]
        eye = torch.eye(3, device=m.device, dtype=m.dtype).expand(b, 3, 3)
        A = eye - K[:, :, None] * H[:, None, :]
        P1 = A @ P @ A.transpose(-1, -2) + \
            (K[:, :, None] * rv[:, None, None]) @ K[:, None, :]
        P1 = 0.5 * (P1 + P1.transpose(-1, -2))
        cap_var_after = (H[:, None, :] @ P1 @ H[:, :, None]).reshape(-1) \
            .clamp_min(0.0)
        nll = 0.5 * (innovation.square() / S + torch.log(S) + LOG_2PI)
        diag = {
            "predicted_capacity_ah": mu,
            "innovation_ah": innovation,
            "innovation_var_ah2": S,
            "capacity_var_before_ah2": latent_var,
            "capacity_var_after_ah2": cap_var_after,
            "gain": K,
        }
        return m1, P1, nll, diag

    def nll_rpt(self, m, P, q_ref_ah, observed_capacity_ah):
        """Sequential RPT innovation NLL; S is a variance in Ah^2."""
        y = torch.as_tensor(observed_capacity_ah, device=m.device,
                            dtype=m.dtype).reshape(-1)
        b = m.shape[0]
        if y.numel() == 1:
            y = y.expand(b)
        mu, _, S, _ = self.capacity_moments(m, P, q_ref_ah)
        return 0.5 * ((y - mu).square() / S + torch.log(S) + LOG_2PI)

    # ------------------------------------------------------------- diagnostics
    def model_summary(self):
        n = sum(p.numel() for p in self.parameters())
        return {
            "version": VERSION,
            "parameters": int(n),
            "control_dim": int(self.control_dim),
            "state_dim": STATE_DIM,
            "mu_net_in_features": int(self.mu_net[0].in_features),
            "kappa_per_week": float(self.kappa()),
            "sigma_ell_per_sqrt_week": float(self.sigma_ell()),
            "lambda_per_week": float(self.lam()),
            "sigma_R_ah_per_sqrt_week": float(self.sigma_R()),
            "obs_sigma_ah": float(self.obs_sigma()),
            "obs_variance_ah2": float(self.obs_variance()),
            "c_rate_per_week_noEll": float(self.c_rate()),
            "mu_base": float(self.mu_base),
            "prior_mean": self.prior_mean.tolist(),
            "prior_sd": [math.sqrt(float(self.prior_cov[0, 0])),
                         math.sqrt(float(self.prior_cov[1, 1])),
                         math.sqrt(float(self.prior_cov[2, 2]))],
        }


def _inv_softplus(value):
    return math.log(math.expm1(float(value)))


# ===================================================================== replay
def _event_scalars_a3(model, kind, dt, control, control_mask,
                      mu_from_control):
    """Per-event control-only scalars from ONE batched mu network call.

    Returns [B, T] tensors: mu, alpha = exp(-kappa*dt), phi = (1-alpha)/kappa,
    c = (1-alpha)*mu, dt.  All are state-independent (control-only), exactly
    like A2's _event_scalars.
    """
    dtw = dt.clamp_min(0.0)
    mu = model.mu_events(kind, control, control_mask, mu_from_control)
    kap = model.kappa().to(dtw.dtype)
    alpha = torch.exp(-kap * dtw)
    phi = -torch.expm1(-kap * dtw) / kap
    return {"mu": mu, "alpha": alpha, "phi": phi, "c": (1.0 - alpha) * mu,
            "dt": dtw}


def _segment_advance(model, m, P, scal, lo, hi, a_lin, b_gain, ell_state):
    """Closed-form propagation over events [lo, hi) with the FROZEN
    linearization (a_lin, b_gain) [B] carried from the last measurement update.

    Exact affine transition of the frozen linear SDE:
        D1   = D0 + (b*G1)*ell0 + (a*T + b*G0)
        ell1 = A_end*ell0 + C_end          (exact piecewise-constant-mu path)
        R1   = exp(-lambda*T)*R0
    with the exact integrated-OU covariance block (series fallback for
    kappa*T < 1e-3).  Splitting [lo, hi) at arbitrary points and composing with
    the same frozen coefficients is exact (affine semigroup).
    """
    if hi <= lo:
        return m, P
    B = m.shape[0]
    dtype = m.dtype
    dt = scal["dt"][:, lo:hi]
    T = dt.sum(dim=1)
    kap = model.kappa().to(dtype)
    lam = model.lam().to(dtype)
    sR2 = model.sigma_R().to(dtype).square()
    q_R = sR2 * (-torch.expm1(-2.0 * lam * T)) / (2.0 * lam)
    beta_end = torch.exp(-lam * T)
    if not ell_state:
        # noEll: ell = softplus(c) point mass, dD = c*dt exactly (no ell or D
        # process noise; D is still corrected by RPT updates through its
        # anchor prior variance).
        c_rate = model.c_rate().to(dtype)
        m1 = torch.stack([m[:, 0] + c_rate * T, m[:, 1], beta_end * m[:, 2]],
                         dim=-1)
        F = torch.eye(3, device=m.device, dtype=dtype) \
            .expand(B, 3, 3).clone()
        F[:, 2, 2] = beta_end
        Q = torch.zeros((B, 3, 3), device=m.device, dtype=dtype)
        Q[:, 2, 2] = q_R
        P1 = F @ P @ F.transpose(-1, -2) + Q
        return m1, 0.5 * (P1 + P1.transpose(-1, -2))
    alpha = scal["alpha"][:, lo:hi]
    phi = scal["phi"][:, lo:hi]
    mu = scal["mu"][:, lo:hi]
    c = scal["c"][:, lo:hi]
    A = torch.cumprod(alpha, dim=1)
    floor = 1e-30 if dtype == torch.float64 else 1e-12
    if float(A[:, -1].min()) > floor:
        C = A * torch.cumsum(c / A, dim=1)
    else:
        A, C = _affine_scan(alpha, c)
    A_end = A[:, -1]
    C_end = C[:, -1]
    # The integral of the mean path over event j uses the state at the START
    # of event j: ell_start_j = A_{j-1}*ell0 + C_{j-1} (EXCLUSIVE prefix).
    A_excl = torch.cat([torch.ones_like(A[:, :1]), A[:, :-1]], dim=1)
    C_excl = torch.cat([torch.zeros_like(C[:, :1]), C[:, :-1]], dim=1)
    G1 = (A_excl * phi).sum(dim=1)
    G0 = (C_excl * phi).sum(dim=1) + (mu * (dt - phi)).sum(dim=1)
    w = b_gain * G1
    c_d = a_lin * T + b_gain * G0
    D1 = m[:, 0] + w * m[:, 1] + c_d
    ell1 = A_end * m[:, 1] + C_end
    s2 = model.sigma_ell().to(dtype).square()
    q_ell = s2 * (-torch.expm1(-2.0 * kap * T)) / (2.0 * kap)
    i2_T = q_ell / s2
    phi_T = -torch.expm1(-kap * T) / kap
    x = kap * T
    small = x < 1e-3
    cross = torch.where(
        small,
        T * T * (0.5 - 0.5 * x + 7.0 * x.square() / 24.0),
        (phi_T - i2_T) / kap)
    h = torch.where(
        small,
        T ** 3 * (1.0 / 3.0 - 7.0 * x / 12.0 + 13.0 * x.square() / 20.0),
        (T - 2.0 * phi_T + i2_T) / kap.square())
    q_DD = b_gain.square() * s2 * h
    q_Dell = b_gain * s2 * cross
    F = torch.eye(3, device=m.device, dtype=dtype).expand(B, 3, 3).clone()
    F[:, 0, 1] = w
    F[:, 1, 1] = A_end
    F[:, 2, 2] = beta_end
    Q = torch.zeros((B, 3, 3), device=m.device, dtype=dtype)
    Q[:, 0, 0] = q_DD
    Q[:, 0, 1] = q_Dell
    Q[:, 1, 0] = q_Dell
    Q[:, 1, 1] = q_ell
    Q[:, 2, 2] = q_R
    m1 = torch.stack([D1, ell1, beta_end * m[:, 2]], dim=-1)
    P1 = F @ P @ F.transpose(-1, -2) + Q
    return m1, 0.5 * (P1 + P1.transpose(-1, -2))


def _run_events_a3(model, kind, dt, control, control_mask, y, score, q_ref,
                   m, P, cfg, frozen=None, collect_nll=True, want_trace=False):
    """Replay a padded [B, T] event block under one arm configuration.

    Segment boundaries are the union of RPT positions over the batch; each
    cell's linearization (a, b) is frozen at ITS OWN last measurement update
    and carried exactly across any foreign split points (exact semigroup), so
    batching never changes a cell's filter.  Returns
    (m, P, nll_sum, n_scored, frozen, trace) with trace = per-RPT-position
    NLL ([B, T], nan elsewhere) when want_trace.
    """
    B, T = kind.shape
    dtype = m.dtype
    nll_sum = torch.zeros(B, dtype=dtype, device=m.device)
    n_scored = torch.zeros(B, dtype=torch.long, device=m.device)
    trace = torch.full((B, T), float("nan"), dtype=dtype, device=m.device) \
        if want_trace else None
    if frozen is None:
        a_lin, b_gain = model.frozen_linearization(m[:, 1].detach())
    else:
        a_lin, b_gain = frozen
    if T == 0:
        return m, P, nll_sum, n_scored, (a_lin, b_gain), trace
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
            nu = y_all[:, r] - mu_cap
            step_nll = 0.5 * (nu.square() / S + torch.log(S) + LOG_2PI)
            if collect_nll:
                nll_sum = nll_sum + torch.where(hit, step_nll,
                                                torch.zeros_like(step_nll))
                n_scored = n_scored + hit.long()
            if want_trace:
                trace[:, r] = torch.where(hit, step_nll,
                                          torch.full_like(step_nll,
                                                          float("nan")))
            m_new, P_new, _, _ = model.correct_rpt(
                m, P, q_ref, y_all[:, r], rate_update=cfg["rate_update"])
            m = torch.where(hit[:, None], m_new, m)
            P = torch.where(hit[:, None, None], P_new, P)
            # Refresh the frozen linearization from the post-update mean of
            # the cells that were actually updated.
            a_new, b_new = model.frozen_linearization(m[:, 1])
            a_lin = torch.where(hit, a_new, a_lin)
            b_gain = torch.where(hit, b_new, b_gain)
        start = r + 1
    if start < T:
        m, P = _segment_advance(model, m, P, scal, start, T, a_lin, b_gain,
                                cfg["ell_state"])
    return m, P, nll_sum, n_scored, (a_lin, b_gain), trace


def _burn_in_state_a3(model, batch, cfg, dtype, device, max_events=300000):
    """No-grad burn-in for one WindowBatch (exact or last_w spans).

    Cells are right-aligned (padded at the front with dt = 0, the identity
    step) so one batched call produces every window start state.  Results are
    SCATTERED BACK to the original batch order (a2_fastdata._burn_in_state
    returns chunk order; see the module docstring note).  Returns
    (m, P, (a, b)) where (a, b) is the carried linearization at the window
    start.
    """
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
            m_c, P_c, _, _, (a_c, b_c), _ = _run_events_a3(
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


def replay_windows_a3(model, batch, cfg, state=None, return_states=False):
    """Windowed replay: no-grad burn-in, then scored window (grad enabled).

    Same contract as a2_fastdata.replay_windows, with the carried frozen
    linearization threaded through the window start.  Returns the cell-macro
    mean innovation NLL loss, per-cell NLL, scored counts and final state.
    """
    p = next(model.parameters())
    dtype, device = p.dtype, p.device
    if state is None:
        m0, P0, frozen0 = _burn_in_state_a3(model, batch, cfg, dtype, device)
    else:
        m0, P0, frozen0 = state
    m0 = m0.detach()
    P0 = P0.detach()
    frozen0 = (frozen0[0].detach(), frozen0[1].detach())
    m, P, nll_sum, n_scored, _, _ = _run_events_a3(
        model, batch.kind.to(device), batch.dt.to(device=device, dtype=dtype),
        batch.control.to(device=device, dtype=dtype),
        batch.control_mask.to(device=device, dtype=dtype),
        batch.y.to(device=device, dtype=dtype), batch.score.to(device),
        batch.q_ref.to(device=device, dtype=dtype), m0, P0, cfg,
        frozen=frozen0, collect_nll=True)
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
        out["window_start_frozen"] = frozen0
    return out


def replay_cells_a3(model, data, cells, cfg, want_trace=False):
    """Exact full-sequence cell replay (validation / equivalence reference).

    Returns {cell_index: per-cell mean innovation NLL}; with want_trace also
    {cell_index: ([T] per-RPT-position NLL, nan elsewhere)}.
    """
    from a2_fastdata import _chunk_by_length
    p = next(model.parameters())
    dtype, device = p.dtype, p.device
    result, traces = {}, {}
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
        m, P, nll_sum, n_scored, _, trace = _run_events_a3(
            model, kind.to(device), dt.to(device), control.to(device),
            mask.to(device), y.to(device), score.to(device),
            q_ref.to(device), m_init, P_init, cfg, collect_nll=True,
            want_trace=want_trace)
        per = torch.where(n_scored > 0,
                          nll_sum / n_scored.clamp_min(1).to(dtype),
                          torch.zeros_like(nll_sum))
        for row, i in enumerate(chunk):
            result[int(i)] = float(per[row])
            if want_trace:
                traces[int(i)] = trace[row].detach().cpu()
    if want_trace:
        return result, traces
    return result


def eval_cell_macro_a3(model, data, cells, cfg):
    """Cell-macro mean NLL over full sequences (cells with >= 1 scored RPT).

    Cells without a scored RPT are excluded from the mean (they carry no
    innovation information), matching the documented semantics.
    """
    scored = [int(i) for i in cells
              if len(data.scored_positions(int(i))) > 0]
    if not scored:
        return float("nan"), {}
    per = replay_cells_a3(model, data, scored, cfg)
    return float(sum(per.values()) / len(per)), per


def build_model(seed: int = 42, **kwargs) -> A3StateModel:
    """Deterministically initialised model; identical across ablation arms."""
    torch.manual_seed(int(seed))
    return A3StateModel(**kwargs)
