"""A2 data contract, as-of replay, cell split and train-only standardisation.

This module never reads payload, processed datasets or checkpoints.  It operates
on compact per-cell records supplied by a future PREP-only step:

  cycle record:  {"source_epoch": float, "available_epoch": float,
                  "control": 24 floats, "control_mask": 24 floats}
  rpt record:    {"source_epoch": float, "available_epoch": float,
                  "capacity_ah": float, "valid": bool}

Semantics (see README_A2_ZH.md for the assumptions):
  * Q_ref is the valid RPT capacity with the EARLIEST ARRIVAL among records that
    have arrived by the cutoff.  Ties break by source stop, then record index.
  * The anchor record defines the time origin and the state prior D=R=0.  It is
    not scored again as an innovation (no double counting of the same reading).
  * Records whose source stop precedes the anchor stop are pre-anchor history and
    are excluded, even if they arrive later (no negative-time propagation).
  * Query-time replay uses only records with source <= query AND arrival <= query.
  * Future forecasts use the last completed cycle control at or before the query,
    held constant; no realised future input is ever consumed.
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone

import torch

WEEK_SECONDS = 604800.0
CONTROL_DIM = 24
LOG_2PI = math.log(2.0 * math.pi)

_SOURCE_KEYS = ("source_epoch", "stop_epoch", "source_time", "stop")
_AVAIL_KEYS = ("available_epoch", "arrival_epoch", "available_at", "arrival",
               "source_visible_at")


def epoch_seconds(value):
    """Parse an ISO-8601 string or a numeric epoch into float seconds."""
    if isinstance(value, (int, float)):
        v = float(value)
        if not math.isfinite(v):
            raise ValueError("non-finite timestamp")
        return v
    if value is None:
        raise ValueError("timestamp is required")
    s = str(value).strip()
    if not s:
        raise ValueError("empty timestamp")
    if "." in s and not s.replace(".", "").replace("+", "").replace("-", "").isdigit():
        head, tail = s.split(".", 1)
        digits = "".join(c for c in tail if c.isdigit())
        suffix = tail[len(digits):]
        s = head + "." + digits[:6].ljust(6, "0") + suffix
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def _record_epoch(rec, keys, what):
    for k in keys:
        if k in rec and rec[k] is not None:
            return epoch_seconds(rec[k])
    raise ValueError("record is missing %s" % what)


def _finite(x):
    return isinstance(x, (int, float)) and math.isfinite(float(x))


def _valid_flag(rec):
    return rec.get("valid", rec.get("data_v2_valid", False)) is True


def first_arrived_anchor(rpt_records, cutoff_epoch=None):
    """Earliest-arrival valid RPT; returns None when nothing has arrived."""
    candidates = []
    for i, rec in enumerate(rpt_records):
        if not _valid_flag(rec):
            continue
        y = rec.get("capacity_ah", rec.get("capacityAh"))
        if not _finite(y):
            continue
        y = float(y)
        if y <= 0:
            continue
        stop = _record_epoch(rec, _SOURCE_KEYS, "source stop")
        arrived = _record_epoch(rec, _AVAIL_KEYS, "arrival/available time")
        if arrived < stop:
            raise ValueError("RPT arrival precedes source stop")
        if cutoff_epoch is not None and arrived > float(cutoff_epoch) + 1e-9:
            continue
        candidates.append((arrived, stop, i, y))
    if not candidates:
        return None
    candidates.sort(key=lambda z: (z[0], z[1], z[2]))
    arrived, stop, idx, y = candidates[0]
    return {
        "index": idx,
        "capacity_ah": y,
        "source_epoch": stop,
        "available_epoch": arrived,
        "n_valid_arrived": len(candidates),
    }


def build_cell_sequence(cell_id, cycle_records, rpt_records, cutoff_epoch=None,
                        assume_cycle_arrival_equal_source=False):
    """Flatten one cell into the ordered event sequence consumed by replay.

    Events are ordered by (source stop, cycle-before-RPT, record index).  Each
    event stores dt_weeks since the previous event (anchor stop for the first).
    """
    anchor = first_arrived_anchor(rpt_records, cutoff_epoch)
    base = {
        "cell_id": str(cell_id),
        "q_ref_ah": None,
        "anchor": None,
        "events": [],
        "n_cycle_used": 0,
        "n_cycle_pre_anchor_excluded": 0,
        "n_cycle_late_excluded": 0,
        "n_rpt_scored": 0,
        "n_rpt_pre_anchor_excluded": 0,
        "n_rpt_late_excluded": 0,
        "n_rpt_future_excluded": 0,
        "assumed_cycle_arrival": 0,
    }
    if anchor is None:
        return base
    q_ref = float(anchor["capacity_ah"])
    if not (q_ref > 0):
        raise ValueError("Q_ref must be positive")
    origin = float(anchor["source_epoch"])
    base["q_ref_ah"] = q_ref
    base["anchor"] = dict(anchor)

    events = []
    assumed = 0
    for i, rec in enumerate(cycle_records):
        stop = _record_epoch(rec, _SOURCE_KEYS, "cycle source stop")
        try:
            arrived = _record_epoch(rec, _AVAIL_KEYS, "cycle availability")
        except ValueError:
            if not assume_cycle_arrival_equal_source:
                raise
            arrived = stop
            assumed += 1
        if arrived < stop:
            raise ValueError("cycle availability precedes source completion")
        if stop < origin - 1e-9:
            base["n_cycle_pre_anchor_excluded"] += 1
            continue
        if cutoff_epoch is not None and arrived > float(cutoff_epoch) + 1e-9:
            base["n_cycle_late_excluded"] += 1
            continue
        ctl = rec.get("control")
        if ctl is None:
            ctl = [0.0] * CONTROL_DIM
        cmask = rec.get("control_mask")
        if cmask is None:
            cmask = [0.0] * CONTROL_DIM
        events.append({
            "kind": "cycle", "index": i, "source_epoch": stop,
            "available_epoch": arrived,
            "control": [float(v) for v in ctl],
            "control_mask": [float(v) for v in cmask],
        })

    for i, rec in enumerate(rpt_records):
        if not _valid_flag(rec):
            continue
        y = rec.get("capacity_ah", rec.get("capacityAh"))
        if not _finite(y):
            continue
        stop = _record_epoch(rec, _SOURCE_KEYS, "RPT source stop")
        arrived = _record_epoch(rec, _AVAIL_KEYS, "RPT arrival")
        if arrived < stop:
            raise ValueError("RPT arrival precedes source stop")
        if stop < origin - 1e-9:
            base["n_rpt_pre_anchor_excluded"] += 1
            continue
        if cutoff_epoch is not None and stop > float(cutoff_epoch) + 1e-9:
            base["n_rpt_future_excluded"] += 1
            continue
        if cutoff_epoch is not None and arrived > float(cutoff_epoch) + 1e-9:
            base["n_rpt_late_excluded"] += 1
            continue
        if i == anchor["index"]:
            continue
        events.append({
            "kind": "rpt", "index": i, "source_epoch": stop,
            "available_epoch": arrived, "capacity_ah": float(y),
            "score": True,
        })

    events.sort(key=lambda e: (e["source_epoch"], 0 if e["kind"] == "cycle" else 1,
                               e["index"]))
    prev = origin
    kept = []
    for e in events:
        dt = (e["source_epoch"] - prev) / WEEK_SECONDS
        if dt < -1e-9:
            raise ValueError("event order produced negative dt")
        e["dt_weeks"] = max(0.0, dt)
        prev = e["source_epoch"]
        kept.append(e)
        if e["kind"] == "cycle":
            base["n_cycle_used"] += 1
        else:
            base["n_rpt_scored"] += 1
    base["events"] = kept
    base["assumed_cycle_arrival"] = assumed
    return base


class A2SequenceBatch(object):
    """Padded batch of cell sequences for replay / sequential-NLL training."""

    def __init__(self, kind, dt, control, control_mask, y, score, q_ref,
                 cell_ids, lengths):
        self.kind = kind            # long [B,T]: 0 pad, 1 cycle, 2 rpt
        self.dt = dt                # float [B,T]
        self.control = control      # float [B,T,24]
        self.control_mask = control_mask
        self.y = y                  # float [B,T]
        self.score = score          # bool [B,T]
        self.q_ref = q_ref          # float [B]
        self.cell_ids = list(cell_ids)
        self.lengths = lengths

    @property
    def batch_size(self):
        return int(self.kind.shape[0])

    def to(self, device):
        for name in ("kind", "dt", "control", "control_mask", "y", "score", "q_ref"):
            setattr(self, name, getattr(self, name).to(device))
        return self

    @classmethod
    def from_sequences(cls, sequences, dtype=torch.float32):
        seqs = list(sequences)
        if not seqs:
            raise ValueError("empty sequence list")
        for s in seqs:
            if s.get("q_ref_ah") is None or s.get("anchor") is None:
                raise ValueError("sequence for cell %r has no anchor" % s.get("cell_id"))
        B = len(seqs)
        T = max(1, max(len(s["events"]) for s in seqs))
        kind = torch.zeros((B, T), dtype=torch.long)
        dt = torch.zeros((B, T), dtype=dtype)
        control = torch.zeros((B, T, CONTROL_DIM), dtype=dtype)
        control_mask = torch.zeros((B, T, CONTROL_DIM), dtype=dtype)
        y = torch.zeros((B, T), dtype=dtype)
        score = torch.zeros((B, T), dtype=torch.bool)
        q_ref = torch.zeros((B,), dtype=dtype)
        lengths = []
        for b, s in enumerate(seqs):
            q_ref[b] = float(s["q_ref_ah"])
            lengths.append(len(s["events"]))
            for t, e in enumerate(s["events"]):
                kind[b, t] = 1 if e["kind"] == "cycle" else 2
                dt[b, t] = float(e["dt_weeks"])
                if e["kind"] == "cycle":
                    control[b, t] = torch.as_tensor(e["control"], dtype=dtype).reshape(-1)
                    control_mask[b, t] = torch.as_tensor(e["control_mask"], dtype=dtype).reshape(-1)
                else:
                    y[b, t] = float(e["capacity_ah"])
                    score[b, t] = bool(e.get("score", False))
        return cls(kind, dt, control, control_mask, y, score, q_ref,
                   [s["cell_id"] for s in seqs], lengths)


def replay_batch(model, batch, use_cycle=True, use_rpt=True):
    """Replay padded sequences; returns sequential RPT innovation NLL per cell.

    Loss convention: cell-macro mean of per-cell mean innovation NLL.  The anchor
    reading is excluded from scoring (it defines Q_ref).
    """
    device = next(model.parameters()).device
    B, T = batch.kind.shape
    p0 = next(model.parameters())
    dtype = p0.dtype
    m = model.prior_mean.to(device=device, dtype=dtype).reshape(1, 2).expand(B, 2).clone()
    P = model.prior_cov.to(device=device, dtype=dtype).expand(B, 2, 2).clone()
    nll_sum = torch.zeros(B, device=device, dtype=dtype)
    n_scored = torch.zeros(B, device=device, dtype=torch.long)
    pred = torch.full((B, T), float("nan"), device=device, dtype=dtype)
    innov_var = torch.full((B, T), float("nan"), device=device, dtype=dtype)
    innovation = torch.full((B, T), float("nan"), device=device, dtype=dtype)
    cap_var_before = torch.full((B, T), float("nan"), device=device, dtype=dtype)
    cap_var_after = torch.full((B, T), float("nan"), device=device, dtype=dtype)
    q_ref = batch.q_ref.to(device=device, dtype=dtype)
    control = batch.control.to(device=device, dtype=dtype)
    control_mask = batch.control_mask.to(device=device, dtype=dtype)
    dt_all = batch.dt.to(device=device, dtype=dtype)
    y_all = batch.y.to(device=device, dtype=dtype)
    score_all = batch.score.to(device=device)
    kind = batch.kind.to(device=device)
    zero = torch.zeros_like(control[0, 0])

    for t in range(T):
        kt = kind[:, t]
        dt = dt_all[:, t]
        ctl = control[:, t]
        msk = control_mask[:, t]
        cycle_mask = (kt == 1) & bool(use_cycle)
        ctl = torch.where(cycle_mask[:, None], ctl, zero.expand_as(ctl))
        msk = torch.where(cycle_mask[:, None], msk, zero.expand_as(msk))
        m, P, _ = model.advance(m, P, dt, ctl, msk)

        is_rpt = kt == 2
        if bool(is_rpt.any()):
            mu, latent, S, _ = model.capacity_moments(m, P, q_ref)
            y = y_all[:, t]
            step_nll = 0.5 * ((y - mu).square() / S + torch.log(S) + LOG_2PI)
            # Every arrived post-anchor RPT is predicted and scored in all arms.
            score_hit = is_rpt & score_all[:, t]
            nll_sum = nll_sum + torch.where(score_hit, step_nll,
                                            torch.zeros_like(step_nll))
            n_scored = n_scored + score_hit.long()
            nan_t = torch.full_like(mu, float("nan"))
            pred[:, t] = torch.where(is_rpt, mu, nan_t)
            innov_var[:, t] = torch.where(is_rpt, S, nan_t)
            innovation[:, t] = torch.where(is_rpt, y - mu, nan_t)
            cap_var_before[:, t] = torch.where(is_rpt, latent, nan_t)
            # The noRPTupdate arm never applies the measurement correction.
            if bool(use_rpt) and bool(score_hit.any()):
                m_new, P_new, _, diag = model.correct_rpt(m, P, q_ref, y)
                m = torch.where(score_hit[:, None], m_new, m)
                P = torch.where(score_hit[:, None, None], P_new, P)
                cap_var_after[:, t] = torch.where(score_hit,
                                                  diag["capacity_var_after_ah2"],
                                                  cap_var_after[:, t])

    has = n_scored > 0
    per_cell = torch.where(has, nll_sum / n_scored.clamp_min(1).to(dtype),
                           torch.zeros_like(nll_sum))
    loss = per_cell[has].mean() if bool(has.any()) else nll_sum.sum() * 0.0
    return {
        "loss_cell_macro": loss,
        "per_cell_nll": per_cell,
        "n_scored": n_scored,
        "predicted_capacity_ah": pred,
        "innovation_ah": innovation,
        "innovation_var_ah2": innov_var,
        "capacity_var_before_ah2": cap_var_before,
        "capacity_var_after_ah2": cap_var_after,
        "final_state_mean": m,
        "final_state_cov": P,
    }


def replay_asof(model, sequence, query_epoch, use_cycle=True, use_rpt=True):
    """Filter one cell at a query time using only records arrived by then."""
    if sequence.get("anchor") is None:
        return {"available": False, "reason": "no arrived anchor at query",
                "q_ref_ah": None, "m": None, "P": None}
    q = float(query_epoch)
    anchor = sequence["anchor"]
    origin = float(anchor["source_epoch"])
    q_ref = torch.tensor([float(sequence["q_ref_ah"])],
                         device=next(model.parameters()).device,
                         dtype=next(model.parameters()).dtype)
    m, P = model.initial_state(1)
    prev = origin
    n_cycles = 0
    n_rpt = 0
    n_late = 0
    last_control = None
    last_mask = None
    last_control_epoch = None
    zero = torch.zeros(1, model.control_dim, device=m.device, dtype=m.dtype)

    for e in sequence["events"]:
        if e["source_epoch"] > q + 1e-9:
            break
        if e["available_epoch"] > q + 1e-9:
            n_late += 1
            continue
        dt = max(0.0, (e["source_epoch"] - prev) / WEEK_SECONDS)
        if e["kind"] == "cycle":
            ctl = torch.as_tensor([e["control"]], device=m.device, dtype=m.dtype)
            msk = torch.as_tensor([e["control_mask"]], device=m.device, dtype=m.dtype)
            if not use_cycle:
                ctl = zero
                msk = zero
            m, P, _ = model.advance(m, P, torch.tensor([dt], device=m.device,
                                                       dtype=m.dtype), ctl, msk)
            last_control = torch.as_tensor([e["control"]], device=m.device, dtype=m.dtype)
            last_mask = torch.as_tensor([e["control_mask"]], device=m.device, dtype=m.dtype)
            last_control_epoch = e["source_epoch"]
            n_cycles += 1
        else:
            m, P, _ = model.advance(m, P, torch.tensor([dt], device=m.device,
                                                       dtype=m.dtype), zero, zero)
            if use_rpt and e.get("score", False):
                m, P, _, _ = model.correct_rpt(m, P, q_ref, [e["capacity_ah"]])
            n_rpt += 1
        prev = e["source_epoch"]

    # Unobserved (last event, query] interval: zero-control (time-term only)
    # propagation.  This deliberately avoids injecting invented operations into
    # the filtered state; the held-recent control is used only for the forecast.
    if q > prev + 1e-9:
        m, P, _ = model.advance(m, P, torch.tensor([(q - prev) / WEEK_SECONDS],
                                                   device=m.device, dtype=m.dtype),
                                zero, zero)
    mu, latent_var, total_var, H = model.capacity_moments(m, P, q_ref)
    return {
        "available": True,
        "q_ref_ah": float(sequence["q_ref_ah"]),
        "m": m, "P": P,
        "capacity_mean_ah": mu, "capacity_latent_var_ah2": latent_var,
        "capacity_total_var_ah2": total_var, "H": H,
        "n_cycles_used": n_cycles, "n_rpt_used": n_rpt,
        "n_late_arrival_excluded": n_late,
        "last_control": last_control, "last_control_mask": last_mask,
        "last_control_epoch": last_control_epoch,
        "anchor_epoch": origin,
    }


def forecast_capacity(model, sequence, query_epoch, horizon_weeks,
                      use_cycle=True, use_rpt=True, grid_steps=1):
    """Forecast capacity at query+horizon under the held-recent control policy."""
    h = float(horizon_weeks)
    if not math.isfinite(h) or h < 0:
        raise ValueError("horizon must be finite and non-negative")
    st = replay_asof(model, sequence, query_epoch, use_cycle=use_cycle,
                     use_rpt=use_rpt)
    if not st["available"]:
        return {"available": False, "reason": st["reason"]}
    m, P = st["m"], st["P"]
    if use_cycle and st["last_control"] is not None:
        ctl, msk = st["last_control"], st["last_control_mask"]
    else:
        ctl = torch.zeros(1, model.control_dim, device=m.device, dtype=m.dtype)
        msk = torch.zeros_like(ctl)
    steps = int(grid_steps)
    if steps < 1:
        raise ValueError("grid_steps must be >= 1")
    dt = h / steps
    for _ in range(steps):
        m, P, _ = model.advance(m, P, torch.tensor([dt], device=m.device,
                                                   dtype=m.dtype), ctl, msk)
    q_ref = torch.tensor([st["q_ref_ah"]], device=m.device, dtype=m.dtype)
    mu, latent_var, total_var, _ = model.capacity_moments(m, P, q_ref)
    return {
        "available": True,
        "capacity_mean_ah": mu, "capacity_latent_var_ah2": latent_var,
        "capacity_total_var_ah2": total_var, "capacity_sd_ah": torch.sqrt(total_var),
        "m": m, "P": P,
        "n_cycles_used": st["n_cycles_used"], "n_rpt_used": st["n_rpt_used"],
        "n_late_arrival_excluded": st["n_late_arrival_excluded"],
        "held_control_epoch": st["last_control_epoch"],
        "policy": "last completed cycle control at/before query, held constant",
    }


def split_cells_by_hash(cell_ids, n_val, seed=42):
    """Cell-grouped split: stable SHA256 order, never an index range."""
    ids = [str(c) for c in cell_ids]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate cell ids")
    n_val = int(n_val)
    if n_val < 0 or n_val >= len(ids):
        raise ValueError("n_val must be in [0, n_cells)")
    ordered = sorted(ids, key=lambda c: hashlib.sha256(
        ("%d:%s" % (int(seed), c)).encode("utf-8")).hexdigest())
    val = ordered[:n_val]
    train = ordered[n_val:]
    assert not (set(train) & set(val))
    assert set(train) | set(val) == set(ids)
    return train, val


class TrainControlStandardizer(object):
    """Control standardisation fitted on TRAIN cells only -> model buffers."""

    def __init__(self, control_dim=CONTROL_DIM):
        self.control_dim = int(control_dim)
        self.mean = torch.zeros(self.control_dim, dtype=torch.float64)
        self.scale = torch.ones(self.control_dim, dtype=torch.float64)
        self.n_constant_skipped = 0
        self.fitted = False

    def fit(self, train_sequences):
        c = self.control_dim
        total = torch.zeros(c, dtype=torch.float64)
        total_sq = torch.zeros(c, dtype=torch.float64)
        count = torch.zeros(c, dtype=torch.float64)
        for seq in train_sequences:
            for e in seq["events"]:
                if e["kind"] != "cycle":
                    continue
                x = torch.as_tensor(e["control"], dtype=torch.float64).reshape(-1)
                mask = torch.as_tensor(e["control_mask"], dtype=torch.float64).reshape(-1)
                if x.numel() != c or mask.numel() != c:
                    raise ValueError("control dimension mismatch")
                ok = torch.isfinite(x) & (mask > 0.5)
                total[ok] += x[ok]
                total_sq[ok] += x[ok].square()
                count[ok] += 1.0
        mean = torch.zeros(c, dtype=torch.float64)
        var = torch.zeros(c, dtype=torch.float64)
        seen = count > 0
        mean[seen] = total[seen] / count[seen]
        var[seen] = (total_sq[seen] / count[seen] - mean[seen].square()).clamp_min(0.0)
        scale = torch.sqrt(var)
        constant = (~seen) | (scale <= 1e-8) | (~torch.isfinite(scale))
        scale = torch.where(constant, torch.ones_like(scale), scale)
        self.mean = mean
        self.scale = scale
        self.n_constant_skipped = int(constant.sum().item())
        self.fitted = True
        return self

    def apply_to_model(self, model):
        if not self.fitted:
            raise RuntimeError("standardizer must be fitted on train cells first")
        model.set_control_standardizer(self.mean, self.scale)
        return {
            "n_constant_scale_one_skipped": self.n_constant_skipped,
            "mean": self.mean.tolist(),
            "scale": self.scale.tolist(),
        }


def hash_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
