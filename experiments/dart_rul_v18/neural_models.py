"""Four fixed DART V18 neural distribution models and their training API."""
from __future__ import annotations
import json
import os
import random
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np
import torch
from torch import nn

from distributions import (
    RULDistribution, torch_hazards_to_logits, torch_logcdf,
    torch_log_density, torch_log_survival,
)

FEATURES = 74
EPOCHS = 300
LR = 1e-3
MODEL_NAMES = ("risk_query", "joint_query", "dart_joint", "dart_split")


def _cell_equal_weights(rows):
    cells = [str(r["cell_id"]) for r in rows]
    if not rows or any(c == "None" for c in cells):
        raise ValueError("training rows need cell_id")
    unique, counts = np.unique(cells, return_counts=True)
    lookup = {c: n for c, n in zip(unique, counts)}
    w = np.asarray([1.0 / (len(unique) * lookup[c]) for c in cells], dtype=np.float64)
    return w / w.sum()


def _weighted_scaler(x, weights):
    mean = np.sum(x * weights[:, None], axis=0)
    var = np.sum((x - mean) ** 2 * weights[:, None], axis=0)
    scale = np.sqrt(var)
    scale[scale == 0] = 1.0
    return mean, scale


def _prepare(train, seed):
    if not train:
        raise ValueError("train must be nonempty")
    if any(r.get("role")!="train" for r in train):
        raise ValueError("train role only")
    q = np.asarray([r["x_query"] for r in train], dtype=np.float64)
    a = np.asarray([r["x_anchor"] for r in train], dtype=np.float64)
    if q.shape != (len(train), FEATURES) or a.shape != q.shape:
        raise ValueError("x_query/x_anchor must each have shape (N, 74)")
    if not np.all(np.isfinite(q)) or not np.all(np.isfinite(a)):
        raise ValueError("features must be finite")
    delta = np.asarray([r["delta_weeks"] for r in train], dtype=np.float64)
    event = np.asarray([r["y_event"] for r in train], dtype=np.int64)
    target = np.asarray([np.nan if r.get("target_rul_weeks") is None else float(r["target_rul_weeks"]) for r in train])
    known = np.asarray([bool(r.get("known_event", False)) for r in train])
    if np.any(~np.isfinite(delta)) or np.any(delta < 0):
        raise ValueError("delta_weeks must be finite and nonnegative")
    if np.any((event != 0) & (event != 1)):
        raise ValueError("y_event must be 0 or 1")
    if np.any((~np.isnan(target)) & ((target < 0) | (~np.isfinite(target)))):
        raise ValueError("targets must be finite nonnegative weeks or None")
    # A known positive target means a future event after this query; current event
    # labels only supervise the CDF. Do not derive supervision from meta fields.
    weights = _cell_equal_weights(train)
    q_mu, q_sd = _weighted_scaler(q, weights)
    a_mu, a_sd = _weighted_scaler(a, weights)
    torch.manual_seed(int(seed)); np.random.seed(int(seed)); random.seed(int(seed))
    torch.set_num_threads(4)
    data = {
        "x_query": torch.as_tensor((q - q_mu) / q_sd, dtype=torch.float64),
        "x_anchor": torch.as_tensor((a - a_mu) / a_sd, dtype=torch.float64),
        "delta": torch.as_tensor(delta, dtype=torch.float64),
        "event": torch.as_tensor(event, dtype=torch.int64),
        "target": torch.as_tensor(target, dtype=torch.float64),
        "known": torch.as_tensor(known, dtype=torch.bool),
        "weight": torch.as_tensor(weights, dtype=torch.float64),
    }
    scalers = {"x_query": {"mean": q_mu.tolist(), "scale": q_sd.tolist()},
               "x_anchor": {"mean": a_mu.tolist(), "scale": a_sd.tolist()}}
    return data, scalers


class _SharedMLP(nn.Module):
    def __init__(self, out_dim: int):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(FEATURES, 48), nn.SiLU(),
                                 nn.Linear(48, 48), nn.SiLU(),
                                 nn.Linear(48, out_dim))
    def forward(self, x):
        return self.net(x)


class _SplitMLP(nn.Module):
    def __init__(self):
        super().__init__()
        self.atom_net = nn.Sequential(nn.Linear(FEATURES, 32), nn.SiLU(),
                                      nn.Linear(32, 32), nn.SiLU(),
                                      nn.Linear(32, 1))
        self.positive_net = nn.Sequential(nn.Linear(FEATURES, 32), nn.SiLU(),
                                          nn.Linear(32, 32), nn.SiLU(),
                                          nn.Linear(32, 17))
    def forward(self, x):
        atom = self.atom_net(x).squeeze(-1)
        pos = torch.nn.functional.logsigmoid(-atom).unsqueeze(-1) + torch.log_softmax(self.positive_net(x), dim=-1)
        return torch.cat([torch.nn.functional.logsigmoid(atom).unsqueeze(-1), pos], dim=-1)


class _Predictor:
    def __init__(self, name, module, scaler, input_key, family):
        self.name, self.module, self.scaler = name, module, scaler
        self.input_key, self.family = input_key, family
        self.module.eval()
    def _logits(self, example):
        x = np.asarray(example[self.input_key], dtype=np.float64)
        if x.shape != (FEATURES,) or not np.all(np.isfinite(x)):
            raise ValueError(f"{self.input_key} must be a finite length-74 vector")
        s = self.scaler[self.input_key]
        xt = torch.as_tensor((x - np.asarray(s["mean"])) / np.asarray(s["scale"]), dtype=torch.float64).unsqueeze(0)
        with torch.no_grad():
            raw = self.module(xt)
            logits = torch_hazards_to_logits(raw) if self.family == "hazard" else raw
            probs = torch.softmax(logits, dim=-1).squeeze(0).cpu().numpy()
        return probs
    def predict(self, example):
        pmf = self._logits(example)
        delta = float(example["delta_weeks"]) if self.name.startswith("dart_") else 0.0
        return RULDistribution(pmf, delta)


def _make_model(name):
    if name == "risk_query": return _SharedMLP(17), "hazard", "x_query"
    if name == "joint_query": return _SharedMLP(18), "joint", "x_query"
    if name == "dart_joint": return _SharedMLP(18), "joint", "x_anchor"
    if name == "dart_split": return _SplitMLP(), "joint", "x_anchor"
    raise KeyError(name)


def _losses(logits, data, model_name):
    # logits are normalized family logits/log-probabilities for anchor RUL.
    target = data["target"]; delta = data["delta"]; event = data["event"]
    loss = torch.empty_like(delta)
    event_rows = event == 1
    if event_rows.any():
        threshold=delta[event_rows] if model_name.startswith("dart_") else torch.zeros_like(delta[event_rows])
        loss[event_rows] = -torch_logcdf(logits[event_rows], threshold)
    future = torch.isfinite(target) & (target > 0)
    if future.any():
        anchor_target = target[future] + (delta[future] if model_name.startswith("dart_") else 0.0)
        loss[future] = -torch_log_density(logits[future], anchor_target)
    no_target = (~torch.isfinite(target)) | (target <= 0)
    no_event = (event == 0) & no_target
    if no_event.any():
        threshold = delta[no_event] if model_name.startswith("dart_") else torch.zeros_like(delta[no_event])
        loss[no_event] = -torch_log_survival(logits[no_event], threshold)
    return loss


def _atomic_checkpoint(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, temp)
    os.replace(temp, path)


def train_models(train, seed, output_dir, epochs=300, on_fit=None, on_step=None):
    """Fit the four fixed models with full-batch cell-equal Adam updates.

    Each epoch is one optimizer step. Models are marked complete only after all
    requested epochs. Checkpoints are atomically replaced every 10 steps and at
    completion so partial progress remains inspectable after an exception.
    """
    if int(epochs) != EPOCHS:
        raise ValueError("V18 freezes epochs=300; no early stop or epoch tuning")
    data, scalers = _prepare(train, seed)
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    predictors = {}
    for name in MODEL_NAMES:
        module, family, input_key = _make_model(name)
        module = module.to(dtype=torch.float64)
        params = sum(p.numel() for p in module.parameters())
        opt = torch.optim.Adam(module.parameters(), lr=LR)
        if on_fit: on_fit("start", name)
        last_loss = None
        for step in range(1, EPOCHS + 1):
            module.train(); opt.zero_grad(set_to_none=True)
            raw = module(data[input_key])
            logits = torch_hazards_to_logits(raw) if family == "hazard" else raw
            per_row = _losses(logits, data, name)
            loss = (per_row * data["weight"]).sum()
            if not torch.isfinite(loss):
                raise FloatingPointError(f"{name} nonfinite full-batch loss at step {step}")
            loss.backward()
            if any(p.grad is not None and not torch.isfinite(p.grad).all() for p in module.parameters()):
                raise FloatingPointError(f"{name} nonfinite gradient at step {step}")
            value = float(loss.detach())
            opt.step()
            last_loss = value
            if on_step: on_step(name, step, value)
            if step % 10 == 0 or step == EPOCHS:
                _atomic_checkpoint(out / f"{name}.checkpoint.pt", {
                    "model": name, "seed": int(seed), "step": step,
                    "epochs_requested": EPOCHS, "complete": step == EPOCHS,
                    "model_state_dict": module.state_dict(),
                    "optimizer_state_dict": opt.state_dict(), "scalers": scalers,
                    "parameter_count": params, "last_loss": value,
                })
        module.eval()
        predictors[name] = _Predictor(name, module, scalers, input_key, family)
        if on_fit: on_fit("complete", name)
    manifest = {
        "seed": int(seed), "epochs": EPOCHS, "optimizer_steps_per_model": EPOCHS,
        "lr": LR, "dtype": "float64", "threads": 4, "device": "cpu",
        "parameters": {n: sum(p.numel() for p in _make_model(n)[0].parameters()) for n in MODEL_NAMES},
        "scalers": scalers, "fit_complete": True,
        "fit_contract": "fullbatch; cell-equal loss; train-only cell-equal input scaling; no early stopping",
    }
    tmp=out/"training_manifest.json.tmp"
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, out/"training_manifest.json")
    return predictors


def parameter_counts():
    return {name: sum(p.numel() for p in _make_model(name)[0].parameters()) for name in MODEL_NAMES}
