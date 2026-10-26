"""A2 entry point: default self-check / dry-run.  It never trains by default.

Safety design
-------------
* With no arguments (or --self-check / --dry-run) this program runs synthetic unit
  fixtures only: no payload, no processed dataset, no checkpoint, no optimiser
  step, no file written outside stdout.
* --run-train refuses to do anything unless it is given an APPROVED, unconsumed
  GO that binds the SHA256 of this directory's code, plus a compact PREP output
  manifest.  Even then it only reads that compact npz (never raw payload) and it
  never writes a GO receipt: consumption and approval belong to the controller.
* No global flag (new_fits_allowed or similar) is read or modified.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone

import torch

from a2_fixtures import run_all, synthetic_sequences
from a2_model import A2StateModel, build_model, CONTROL_DIM
from a2_targets import (
    A2SequenceBatch, TrainControlStandardizer, hash_file, replay_batch,
    split_cells_by_hash,
)

HERE = os.path.dirname(os.path.abspath(__file__))

ARM_CONFIGS = {
    "full": {"label": "A2_full_F2", "use_cycle": True, "use_rpt": True,
             "description": "cycle-driven F2 advance + RPT measurement update"},
    "time": {"label": "A2_time_only", "use_cycle": False, "use_rpt": True,
             "description": "time/calendar term only (control masked), RPT update kept"},
    "noRPTupdate": {"label": "A2_no_RPT_update", "use_cycle": True, "use_rpt": False,
                    "description": "cycle advance, anchor only, no RPT measurement update"},
}


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="A2 state prototype: self-check by default, training only under an exact GO.")
    p.add_argument("--self-check", action="store_true",
                   help="run synthetic fixtures (default behaviour)")
    p.add_argument("--dry-run", action="store_true",
                   help="self-check plus a synthetic 3-arm forward probe; no optimiser step")
    p.add_argument("--run-train", action="store_true",
                   help="guarded training path; requires --go and --manifest")
    p.add_argument("--go", default=None, help="path to an APPROVED exact-hash GO json")
    p.add_argument("--manifest", default=None, help="PREP-only compact npz manifest json")
    p.add_argument("--arm", default="full", choices=sorted(ARM_CONFIGS))
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--val-cells", type=int, default=25)
    p.add_argument("--steps", type=int, default=3000)
    p.add_argument("--batch-cells", type=int, default=8)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--val-every", type=int, default=50)
    p.add_argument("--patience", type=int, default=6)
    p.add_argument("--out-dir", default=None)
    return p.parse_args(argv)


def _model_summary(model):
    n = sum(p.numel() for p in model.parameters())
    return {
        "parameters": int(n),
        "control_dim": int(model.control_dim),
        "hidden": int(model.hidden),
        "obs_sigma_ah": float(model.obs_sigma()),
        "obs_variance_ah2": float(model.obs_variance()),
        "prior_mean": model.prior_mean.tolist(),
        "prior_var": [float(model.prior_cov[0, 0]), float(model.prior_cov[1, 1])],
        "prior_sd": [math.sqrt(float(model.prior_cov[0, 0])),
                     math.sqrt(float(model.prior_cov[1, 1]))],
        "control_mean_is_identity": bool(torch.equal(
            model.control_mean, torch.zeros_like(model.control_mean))),
        "control_scale_is_identity": bool(torch.equal(
            model.control_scale, torch.ones_like(model.control_scale))),
    }


def print_header():
    print("=" * 78)
    print("A2 state prototype -- %s" % datetime.now(timezone.utc).isoformat())
    print("python %s | torch %s | cuda %s" % (sys.version.split()[0], torch.__version__,
                                              torch.cuda.is_available()))
    print("mode: %s" % ("TRAIN" if "--run-train" in sys.argv else "SELF-CHECK/DRY-RUN"))
    print("scope: synthetic tensors only; no payload, no checkpoint, no optimizer step")
    print("=" * 78)


def _dry_run_probe():
    model = build_model(seed=7)
    seqs = synthetic_sequences(3, seed=123)
    batch = A2SequenceBatch.from_sequences(seqs)
    print("synthetic batch: kind=%s control=%s dt=%s" %
          (tuple(batch.kind.shape), tuple(batch.control.shape), tuple(batch.dt.shape)))
    for arm, cfg in sorted(ARM_CONFIGS.items()):
        with torch.no_grad():
            out = replay_batch(model, batch, use_cycle=cfg["use_cycle"],
                               use_rpt=cfg["use_rpt"])
        print("  %-12s loss_cell_macro=%+.6f  scored=%s" %
              (arm, float(out["loss_cell_macro"]),
               out["n_scored"].tolist()))
    print("  (forward only -- no backward, no optimiser, no data)")


# --------------------------------------------------------------- GO validation
def _sha_ok(path, expected):
    if not os.path.exists(path):
        return "missing file %s" % path
    got = hash_file(path)
    if str(expected).lower() != got.lower():
        return "sha256 mismatch for %s: go=%s actual=%s" % (
            os.path.basename(path), expected, got)
    return None


def validate_go(go_path, steps, arm):
    """Return (problems, go_data).  Never consumes or rewrites the GO."""
    problems = []
    if not go_path or not os.path.exists(go_path):
        return ["GO file not found: %r" % (go_path,)], None
    try:
        with open(go_path, "r", encoding="utf-8") as f:
            go = json.load(f)
    except Exception as exc:  # noqa: BLE001
        return ["GO is not readable JSON: %s" % exc], None
    status = str(go.get("status", go.get("approval_status", ""))).upper()
    if status != "APPROVED":
        problems.append("GO status is %r, not APPROVED" % status)
    if go.get("allow_fit") is not True and go.get("allow_train") is not True:
        problems.append("GO does not set allow_fit/allow_train true")
    for key in ("consumed_at", "consumed", "consumed_utc"):
        if go.get(key):
            problems.append("GO already consumed (%s)" % key)
    scope = " ".join(str(go.get(k, "")) for k in
                    ("scope", "task", "purpose", "allowed_scope", "title")).upper()
    if "A2" not in scope:
        problems.append("GO scope does not name A2")
    if "TRAIN" not in scope and "FIT" not in scope:
        problems.append("GO scope does not authorise TRAIN/FIT")
    code = go.get("code_sha256") or go.get("code_hashes")
    if not isinstance(code, dict) or not code:
        problems.append("GO must bind code_sha256 hashes")
    else:
        for name, expected in code.items():
            msg = _sha_ok(os.path.join(HERE, os.path.basename(str(name))), expected)
            if msg:
                problems.append(msg)
    max_steps = go.get("max_steps")
    if max_steps is None and isinstance(go.get("budget"), dict):
        max_steps = go["budget"].get("max_steps")
    if max_steps is not None and int(steps) > int(max_steps):
        problems.append("requested steps %d exceed GO max_steps %s" % (steps, max_steps))
    arms = go.get("arms")
    if isinstance(arms, list) and arms and arm not in arms:
        problems.append("arm %r not in GO arms %r" % (arm, arms))
    return problems, go


# ------------------------------------------------------------- prepared loader
def load_prepared_sequences(manifest_path):
    """Load the compact PREP output (npz) -- never raw payload.

    Expected npz keys (flat, ragged via offsets):
      cell_ids [N] str, q_ref_ah [N], anchor_source_epoch [N],
      event_cell [E] int, event_kind [E] int8 (1 cycle, 2 rpt),
      event_source [E] float64, event_available [E] float64,
      event_dt_weeks [E] float32, control [E,24] float32,
      control_mask [E,24] float32, capacity_ah [E] float32, score [E] bool
    """
    import numpy as np

    with open(manifest_path, "r", encoding="utf-8") as f:
        man = json.load(f)
    npz_path = man.get("prepared_npz")
    if not npz_path:
        raise ValueError("manifest has no prepared_npz")
    if not os.path.isabs(npz_path):
        npz_path = os.path.join(os.path.dirname(os.path.abspath(manifest_path)), npz_path)
    expected = man.get("prepared_npz_sha256")
    if not expected:
        raise ValueError("manifest must pin prepared_npz_sha256")
    got = hash_file(npz_path)
    if str(expected).lower() != got.lower():
        raise ValueError("prepared npz sha256 mismatch")
    z = np.load(npz_path, allow_pickle=False)
    cells = [str(c) for c in z["cell_ids"].tolist()]
    seqs = {c: {"cell_id": c, "q_ref_ah": float(z["q_ref_ah"][i]),
                "anchor": {"index": -1, "capacity_ah": float(z["q_ref_ah"][i]),
                           "source_epoch": float(z["anchor_source_epoch"][i]),
                           "available_epoch": float(z["anchor_source_epoch"][i]),
                           "n_valid_arrived": 1},
                "events": []} for i, c in enumerate(cells)}
    for i in range(z["event_cell"].shape[0]):
        c = cells[int(z["event_cell"][i])]
        kind = "cycle" if int(z["event_kind"][i]) == 1 else "rpt"
        e = {"kind": kind, "index": int(i),
             "source_epoch": float(z["event_source"][i]),
             "available_epoch": float(z["event_available"][i]),
             "dt_weeks": float(z["event_dt_weeks"][i])}
        if kind == "cycle":
            e["control"] = z["control"][i].astype(float).tolist()
            e["control_mask"] = z["control_mask"][i].astype(float).tolist()
        else:
            e["capacity_ah"] = float(z["capacity_ah"][i])
            e["score"] = bool(z["score"][i])
        seqs[c]["events"].append(e)
    split = man.get("split") or {}
    train_cells = [str(c) for c in split.get("train_cells", [])]
    val_cells = [str(c) for c in split.get("val_cells", [])]
    if not train_cells or not val_cells:
        raise ValueError("manifest split must list train_cells and val_cells")
    if set(train_cells) & set(val_cells):
        raise ValueError("split leaks cells")
    missing = (set(train_cells) | set(val_cells)) - set(cells)
    if missing:
        raise ValueError("split references unknown cells: %r" % sorted(missing)[:3])
    return [seqs[c] for c in train_cells], [seqs[c] for c in val_cells], man


# ---------------------------------------------------------------- training bits
def _eval_loss(model, seqs, cfg, batch_cells=8):
    model.eval()
    vals = []
    with torch.no_grad():
        for i in range(0, len(seqs), batch_cells):
            batch = A2SequenceBatch.from_sequences(seqs[i:i + batch_cells])
            out = replay_batch(model, batch, use_cycle=cfg["use_cycle"],
                               use_rpt=cfg["use_rpt"])
            keep = out["n_scored"] > 0
            if bool(keep.any()):
                vals.append(out["per_cell_nll"][keep].detach().cpu())
    if not vals:
        raise RuntimeError("no scored validation innovations")
    return float(torch.cat(vals).mean())


def _sample_batch(seqs, rng, batch_cells):
    idx = [rng.randrange(len(seqs)) for _ in range(min(batch_cells, len(seqs)))]
    return A2SequenceBatch.from_sequences([seqs[i] for i in idx])


def train_one_arm(train_seqs, val_seqs, cfg, args):
    import random
    rng = random.Random(args.seed)
    model = build_model(seed=args.seed)
    std = TrainControlStandardizer().fit(train_seqs).apply_to_model(model)
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=args.lr, weight_decay=args.weight_decay)
    best = {"val_nll": float("inf"), "step": 0, "state": None}
    history = []
    stale = 0
    step = 0
    for step in range(1, int(args.steps) + 1):
        model.train()
        batch = _sample_batch(train_seqs, rng, args.batch_cells)
        out = replay_batch(model, batch, use_cycle=cfg["use_cycle"],
                           use_rpt=cfg["use_rpt"])
        loss = out["loss_cell_macro"]
        if not torch.isfinite(loss):
            raise RuntimeError("non-finite training loss at step %d" % step)
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        if step % int(args.val_every) == 0 or step == int(args.steps):
            val = _eval_loss(model, val_seqs, cfg)
            history.append({"step": step, "train_loss": float(loss), "val_nll": val})
            if val < best["val_nll"] - 1e-6:
                best = {"val_nll": val, "step": step,
                        "state": copy.deepcopy(model.state_dict())}
                stale = 0
            else:
                stale += 1
            if stale >= int(args.patience):
                break
    selected_steps = max(1, int(best["step"]))
    # Full refit on all train cells for the selected number of steps.
    refit = build_model(seed=args.seed)
    TrainControlStandardizer().fit(train_seqs).apply_to_model(refit)
    opt2 = torch.optim.AdamW([p for p in refit.parameters() if p.requires_grad],
                             lr=args.lr, weight_decay=args.weight_decay)
    rng2 = random.Random(args.seed + 1)
    for _ in range(selected_steps):
        batch = _sample_batch(train_seqs, rng2, args.batch_cells)
        out = replay_batch(refit, batch, use_cycle=cfg["use_cycle"],
                           use_rpt=cfg["use_rpt"])
        opt2.zero_grad()
        out["loss_cell_macro"].backward()
        torch.nn.utils.clip_grad_norm_(
            [p for p in refit.parameters() if p.requires_grad], 1.0)
        opt2.step()
    return {
        "arm": cfg["label"], "selected_steps": selected_steps,
        "best_val_nll": best["val_nll"], "history": history,
        "standardizer": {"n_constant_skipped": std["n_constant_scale_one_skipped"]},
        "model": refit, "optimizer_steps": selected_steps,
    }


def run_train(args):
    problems, go = validate_go(args.go, args.steps, args.arm)
    if problems:
        print("REFUSED -- GO validation failed:")
        for p in problems:
            print("  - %s" % p)
        return 3
    if not args.manifest:
        print("REFUSED -- no PREP-only manifest supplied; A2 will not read payload.")
        return 4
    train_seqs, val_seqs, man = load_prepared_sequences(args.manifest)
    print("prepared: %d train cells, %d val cells (cell-grouped, from manifest)" %
          (len(train_seqs), len(val_seqs)))
    cfg = ARM_CONFIGS[args.arm]
    out_dir = args.out_dir or os.path.join(
        HERE, "runs", "a2_%s_%s" % (args.arm, datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")))
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()
    result = train_one_arm(train_seqs, val_seqs, cfg, args)
    model = result.pop("model")
    result.update({
        "go": os.path.abspath(args.go), "go_sha256": hash_file(args.go),
        "manifest": os.path.abspath(args.manifest),
        "manifest_sha256": hash_file(args.manifest),
        "seed": args.seed, "elapsed_seconds": time.time() - t0,
        "model_summary": _model_summary(model),
        "arms": {k: {kk: vv for kk, vv in v.items() if kk != "description"}
                 for k, v in ARM_CONFIGS.items()},
    })
    torch.save(model.state_dict(), os.path.join(out_dir, "model_state_dict.pt"))
    with open(os.path.join(out_dir, "fit_report.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print("wrote %s" % out_dir)
    return 0


def main(argv=None):
    args = parse_args(argv)
    if args.run_train:
        print_header()
        return run_train(args)
    print_header()
    model = build_model(seed=args.seed)
    print("model summary: %s" % json.dumps(_model_summary(model), sort_keys=True))
    print("arms: %s" % json.dumps({k: v["label"] for k, v in ARM_CONFIGS.items()}))
    print("-" * 78)
    res = run_all(verbose=True)
    print("-" * 78)
    if args.dry_run:
        _dry_run_probe()
        print("-" * 78)
    print("NO TRAINING PERFORMED. NO PAYLOAD READ. NO CHECKPOINT READ.")
    print("RESULT: %s (%d passed / %d failed)" %
          ("OK" if res["n_fail"] == 0 else "FAILED", res["n_pass"], res["n_fail"]))
    return 0 if res["n_fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
