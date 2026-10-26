"""A2 capacity-state model prototype (implementation only; no data access).

Capacity map (state-only, no F0/readout mean bypass):

    Q(t) = Q_ref * exp(-D(t)) + R(t)

with state mean m = [D, R] and covariance P (2x2).  Q_ref is the first ARRIVED
valid RPT capacity of the cell and is anchored once per cell (see a2_targets).

Contract encoded here
---------------------
1. The control network consumes ONLY standardised 24-d control features and
   their missingness mask.  It never receives dt.  With a control held constant
   the transition is therefore an exact affine semigroup, so propagating an
   interval in one step or in many sub-steps gives the same moments.

2. SIGMA SEMANTICS (corrected 2026-10-22 by controller clarification).
   Every noise quantity produced by the network is a STANDARD DEVIATION sigma
   (Ah for capacity, Ah/sqrt(week) for the R diffusion, D/sqrt(week) for the D
   diffusion).  Variances are always the explicit square sigma**2 (Ah^2, or
   variance rate per week), and the Gaussian log density uses log(sigma):
   0.5*log(2*pi*sigma^2) = log(sigma) + 0.5*log(2*pi).

   A1's defect was the opposite reading: it interpreted softplus(-6)=0.0025 as a
   VARIANCE, giving sigma = 0.05 Ah, far too large, hence a negligible RPT update
   gain.  A2 initialises sigma_obs ~ 2e-3 Ah (variance ~ 4e-6 Ah^2), asserts the
   1e-3..1e-2 Ah and 1e-6..1e-4 Ah^2 bands in fixtures, and never squares twice.

3. D's mean drift is non-negative by construction (softplus rate), but D is a
   Gaussian latent: an RPT measurement update can decrease it.  We therefore
   never claim pathwise irreversibility.

4. Physical capacity uncertainty is H P H^T in Ah^2.  trace(P) mixes D (dimension-
   less) and R (Ah) and is never reported as a capacity uncertainty.
"""
from __future__ import annotations

import math

import torch
from torch import nn
import torch.nn.functional as F

WEEK_SECONDS = 604800.0
THRESHOLD_AH = 0.20
CONTROL_DIM = 24
LOG_2PI = math.log(2.0 * math.pi)

# Softplus logits for the control-only rates.  Initialisation values only, from
# A1 evidence (Q_ref ~ .28 Ah, threshold .20 Ah, sensor-noise floor ~.002 Ah
# sigma), NOT tuned on any evaluation split.
#   d_rate  ~ 0.003/week (logit -5.7)     sigma_d ~ 0.005 /sqrt(week)
#   lambda  ~ 0.049/week (logit -3.0)     sigma_r ~ 0.002 Ah/sqrt(week)
_BASE_INIT = (-5.7, -5.3, -3.0, -6.2)
_SIGMA_OBS_INIT_AH = 2e-3


class A2StateModel(nn.Module):
    """Two-dimensional continuous-time capacity state (D damage, R offset)."""

    def __init__(self, control_dim: int = CONTROL_DIM, hidden: int = 32,
                 base_init=_BASE_INIT, obs_sigma_init_ah: float = _SIGMA_OBS_INIT_AH,
                 prior_sd_D: float = 5e-3, prior_sd_R: float = 5e-3,
                 r_eq_scale: float = 0.15) -> None:
        super().__init__()
        if obs_sigma_init_ah <= 0:
            raise ValueError("obs_sigma_init_ah is a standard deviation in Ah and must be > 0")
        if prior_sd_D < 0 or prior_sd_R < 0:
            raise ValueError("prior standard deviations must be >= 0")
        self.control_dim = int(control_dim)
        self.hidden = int(hidden)
        self.r_eq_scale = float(r_eq_scale)

        # inputs: standardised control and its mask.  Deliberately NO dt column.
        self.rates = nn.Sequential(
            nn.Linear(2 * self.control_dim, self.hidden), nn.SiLU(),
            nn.Linear(self.hidden, self.hidden), nn.SiLU(),
            nn.Linear(self.hidden, 5),
        )
        # output order: D mean rate, sigma_D, OU relaxation rate, R equilibrium,
        #               sigma_R.  Both sigma outputs are STANDARD DEVIATIONS.
        self.base = nn.Parameter(torch.tensor(base_init, dtype=torch.float32))
        # Raw logit; softplus(raw) is the RPT observation SIGMA in Ah.
        init_raw = math.log(math.expm1(float(obs_sigma_init_ah)))
        self.obs_sigma_raw = nn.Parameter(torch.tensor(init_raw, dtype=torch.float32))

        # Explicit, fixed initial prior at the anchor (D=R=0 because Q_ref is the
        # anchor measurement).  Prior variances are a stated assumption, not
        # learned and not taken from any future input.
        self.register_buffer("prior_mean", torch.zeros(2, dtype=torch.float32))
        self.register_buffer(
            "prior_cov",
            torch.diag(torch.tensor([prior_sd_D ** 2, prior_sd_R ** 2],
                                    dtype=torch.float32)),
        )
        # Train-only control standardisation; identity until fitted.
        self.register_buffer("control_mean", torch.zeros(self.control_dim,
                                                         dtype=torch.float32))
        self.register_buffer("control_scale", torch.ones(self.control_dim,
                                                         dtype=torch.float32))
        self.register_buffer("control_n_constant_skipped",
                             torch.zeros((), dtype=torch.long))

    # ------------------------------------------------------------------ prior
    def initial_state(self, batch: int = 1, device=None, dtype=None):
        """Return (m, P) expanded from the explicit anchor prior."""
        p = next(self.parameters())
        device = device or p.device
        dtype = dtype or p.dtype
        m = self.prior_mean.to(device=device, dtype=dtype).reshape(1, 2).expand(batch, 2).clone()
        P = self.prior_cov.to(device=device, dtype=dtype).reshape(1, 2, 2).expand(batch, 2, 2).clone()
        return m, P

    # ------------------------------------------------------- noise / variance
    def obs_sigma(self):
        """RPT observation STANDARD DEVIATION in Ah (network output)."""
        return F.softplus(self.obs_sigma_raw)

    def obs_variance(self):
        """RPT observation variance in Ah^2 == sigma**2 (explicit square)."""
        return self.obs_sigma().square()

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
        return (x - self.control_mean) / self.control_scale

    # -------------------------------------------------------------- dynamics
    def transition_parameters(self, control=None, control_mask=None, batch: int = 1):
        """Control-only rates and SIGMA values; no dt argument by design."""
        p = next(self.parameters())
        device, dtype = p.device, p.dtype
        if control is None:
            x = torch.zeros(batch, self.control_dim, device=device, dtype=dtype)
            mask = torch.zeros_like(x)
        else:
            x = torch.as_tensor(control, device=device, dtype=dtype)
            if x.ndim == 1:
                x = x[None, :].expand(batch, -1)
            if x.shape != (batch, self.control_dim):
                raise ValueError("control shape mismatch")
            if control_mask is None:
                mask = torch.isfinite(x).to(dtype)
            else:
                mask = torch.as_tensor(control_mask, device=device, dtype=dtype)
                if mask.ndim == 1:
                    mask = mask[None, :].expand(batch, -1)
                if mask.shape != x.shape:
                    raise ValueError("control mask shape mismatch")
                mask = mask.clamp(0.0, 1.0)
            x = torch.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        x = self.standardize_control(x)
        raw = self.rates(torch.cat([x * mask, mask], dim=-1))
        d_rate = F.softplus(self.base[0] + raw[:, 0])
        d_sigma = F.softplus(self.base[1] + raw[:, 1])
        lam = F.softplus(self.base[2] + raw[:, 2]) + 1e-6
        r_eq = self.r_eq_scale * torch.tanh(raw[:, 3])
        r_sigma = F.softplus(self.base[3] + raw[:, 4])
        return {
            "d_rate_per_week": d_rate,
            "d_sigma_per_sqrt_week": d_sigma,
            "r_relax_rate_per_week": lam,
            "r_eq_ah": r_eq,
            "r_sigma_per_sqrt_week": r_sigma,
        }

    def advance(self, m, P, dt_weeks, control=None, control_mask=None):
        """Exact affine-semigroup propagation over dt with a constant control."""
        if m.shape[-1] != 2 or P.shape[-2:] != (2, 2):
            raise ValueError("state shape mismatch")
        b = m.shape[0]
        dt = torch.as_tensor(dt_weeks, device=m.device, dtype=m.dtype).reshape(-1)
        if dt.numel() == 1:
            dt = dt.expand(b)
        if dt.shape != (b,):
            raise ValueError("dt shape mismatch")
        if torch.any(~torch.isfinite(dt)) or torch.any(dt < 0):
            raise ValueError("dt must be finite and non-negative")
        pr = self.transition_parameters(control, control_mask, b)
        lam = pr["r_relax_rate_per_week"]
        alpha = torch.exp(-lam * dt)
        # 1 - alpha and the integrated OU variance, both via expm1 for stability.
        one_minus_alpha = -torch.expm1(-lam * dt)
        # variance rate == sigma**2 (explicit square of the network sigma)
        d_var_rate = pr["d_sigma_per_sqrt_week"].square()
        r_var_rate = pr["r_sigma_per_sqrt_week"].square()
        ou_var = r_var_rate * (-torch.expm1(-2.0 * lam * dt)) / (2.0 * lam)
        m1 = torch.stack(
            [m[:, 0] + pr["d_rate_per_week"] * dt,
             alpha * m[:, 1] + one_minus_alpha * pr["r_eq_ah"]],
            dim=-1,
        )
        Fm = torch.zeros((b, 2, 2), device=m.device, dtype=m.dtype)
        Fm[:, 0, 0] = 1.0
        Fm[:, 1, 1] = alpha
        Q = torch.zeros_like(P)
        Q[:, 0, 0] = d_var_rate * dt
        Q[:, 1, 1] = ou_var
        P1 = Fm @ P @ Fm.transpose(-1, -2) + Q
        P1 = 0.5 * (P1 + P1.transpose(-1, -2))
        return m1, P1, pr

    # -------------------------------------------------------------- capacity
    def capacity_moments(self, m, P, q_ref_ah, obs_sigma=None, obs_var=None):
        """State-only capacity mean/variance; no learned readout is involved.

        Returns (mean Ah, latent variance Ah^2 = HPH^T, total variance Ah^2, H).
        The observation variance is sigma**2.
        """
        b = m.shape[0]
        q0 = torch.as_tensor(q_ref_ah, device=m.device, dtype=m.dtype).reshape(-1)
        if q0.numel() == 1:
            q0 = q0.expand(b)
        if q0.shape != (b,):
            raise ValueError("q_ref shape mismatch")
        if torch.any(~torch.isfinite(q0)) or torch.any(q0 <= 0):
            raise ValueError("q_ref must be finite and positive")
        q_det = q0 * torch.exp(-m[:, 0])
        mu = q_det + m[:, 1]
        H = torch.stack([-q_det, torch.ones_like(q_det)], dim=-1)
        latent_var = (H[:, None, :] @ P @ H[:, :, None]).reshape(-1).clamp_min(0.0)
        if obs_var is not None:
            rv = torch.as_tensor(obs_var, device=m.device, dtype=m.dtype).reshape(-1)
        elif obs_sigma is not None:
            sg = torch.as_tensor(obs_sigma, device=m.device, dtype=m.dtype).reshape(-1)
            rv = sg.square()
        else:
            rv = self.obs_variance().to(dtype=m.dtype).reshape(-1)
        if rv.numel() == 1:
            rv = rv.expand_as(latent_var)
        if rv.shape != latent_var.shape or torch.any(rv <= 0):
            raise ValueError("observation variance must be positive Ah^2")
        total_var = latent_var + rv
        return mu, latent_var, total_var, H

    def correct_rpt(self, m, P, q_ref_ah, observed_capacity_ah,
                    obs_sigma=None, obs_var=None):
        """Joseph-form capacity measurement update; returns innovation NLL."""
        b = m.shape[0]
        y = torch.as_tensor(observed_capacity_ah, device=m.device, dtype=m.dtype).reshape(-1)
        if y.numel() == 1:
            y = y.expand(b)
        if y.shape != (b,) or torch.any(~torch.isfinite(y)):
            raise ValueError("observed capacity shape/value error")
        mu, latent_var, S, H = self.capacity_moments(m, P, q_ref_ah,
                                                     obs_sigma=obs_sigma,
                                                     obs_var=obs_var)
        rv = (S - latent_var).clamp_min(1e-14)
        innovation = y - mu
        K = (P @ H[:, :, None]).squeeze(-1) / S[:, None]
        m1 = m + K * innovation[:, None]
        eye = torch.eye(2, device=m.device, dtype=m.dtype).expand(b, 2, 2)
        A = eye - K[:, :, None] * H[:, None, :]
        P1 = A @ P @ A.transpose(-1, -2) + (K[:, :, None] * rv[:, None, None]) @ K[:, None, :]
        P1 = 0.5 * (P1 + P1.transpose(-1, -2))
        cap_var_after = (H[:, None, :] @ P1 @ H[:, :, None]).reshape(-1).clamp_min(0.0)
        nll = 0.5 * (innovation.square() / S + torch.log(S) + LOG_2PI)
        diag = {
            "predicted_capacity_ah": mu,
            "innovation_ah": innovation,
            "innovation_sd_ah": torch.sqrt(S),
            "innovation_var_ah2": S,
            "capacity_var_before_ah2": latent_var,
            "capacity_var_after_ah2": cap_var_after,
            "observation_sigma_ah": torch.sqrt(rv),
            "observation_var_ah2": rv,
            "gain": K,
            "state_mean_correction": m1 - m,
        }
        return m1, P1, nll, diag

    def nll_rpt(self, m, P, q_ref_ah, observed_capacity_ah,
                obs_sigma=None, obs_var=None):
        """Gaussian innovation NLL: variance is sigma**2 (Ah^2)."""
        y = torch.as_tensor(observed_capacity_ah, device=m.device, dtype=m.dtype).reshape(-1)
        b = m.shape[0]
        if y.numel() == 1:
            y = y.expand(b)
        mu, _, S, _ = self.capacity_moments(m, P, q_ref_ah,
                                            obs_sigma=obs_sigma, obs_var=obs_var)
        return 0.5 * ((y - mu).square() / S + torch.log(S) + LOG_2PI)

    # ------------------------------------------------------------- diagnostics
    def linearized_threshold_probability(self, m, P, q_ref_ah,
                                         threshold_ah: float = THRESHOLD_AH):
        """Diagnostic only: linearised P(Q <= threshold).

        Q = Q_ref*exp(-D)+R is not Gaussian, so this is a first-order Gaussian
        approximation.  It is NOT an event probability, a first-passage
        probability or a substitute for an observed source event target.
        """
        mu, latent_var, _, _ = self.capacity_moments(m, P, q_ref_ah)
        sd = torch.sqrt(latent_var.clamp_min(1e-12))
        z = (float(threshold_ah) - mu) / (math.sqrt(2.0) * sd)
        return (0.5 * (1.0 + torch.erf(z))).clamp(1e-6, 1.0 - 1e-6)


def build_model(seed: int = 42, **kwargs) -> A2StateModel:
    """Deterministically initialised model; identical across ablation arms."""
    torch.manual_seed(int(seed))
    return A2StateModel(**kwargs)
