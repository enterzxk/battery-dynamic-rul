"""A2 training entry point v2: vectorised loader + windowed truncated-BPTT.

Why v2
------
The first A2 training attempt (a2_train.py --run-train) never reached its first
fit: load_prepared_sequences built one Python dict per event (774,486 events,
more than 22 minutes) and replay_batch advanced the filter one event per Python
step.  This entry keeps a2_train.py's safety contract (default self-check, GO
gated training, no payload/checkpoint/receipt access) and replaces only the data
path and the replay with a2_fastdata:

* loader: npz arrays -> per-cell offsets -> tensors in under a second;
* training: one L=256 event window per sampled cell, no-grad burn-in, window
  loss == the corresponding segment of the full-sequence replay (exact burn-in);
* evaluation: exact full-cell replay (identical to a2_targets.replay_batch).

a2_train.py is intentionally left byte-identical (sha 11cf19e4...).  It remains
the reference implementation and the owner of the GO gate; this file imports its
validate_go / ARM_CONFIGS / _model_summary so there is exactly one guard.

Default behaviour (no arguments) is --self-check: the 16 original fixtures plus
the 11 fast-path fixtures, on synthetic tensors only.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import random
import sys
import time
from datetime import datetime, timezone

import numpy as np
import torch

from a2_fastdata import (
    WindowSampler, bench_npz, bench_synthetic, eval_cell_macro,
    fit_control_standardizer, load_prepared_fast, replay_windows,
)
from a2_fixtures import run_all
from a2_fixtures_fast import run_all_fast
from a2_model import build_model
from a2_targets import hash_file
from a2_train import (
    ARM_CONFIGS, HERE, _model_summary, validate_go,
)

REQUIRED_GO_FILES = ("a2_fastdata.py", "a2_train_v2.py")


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="A2 v2: self-check by default; --bench; guarded windowed training.")
    p.add_argument("--self-check", action="store_true",
                   help="run all synthetic fixtures (default behaviour)")
    p.add_argument("--dry-run", action="store_true",
                   help="self-check plus a synthetic 3-arm windowed forward probe")
    p.add_argument("--bench", action="store_true",
                   help="time a synthetic training step (no training, 0 optimizer steps)")
    p.add_argument("--bench-npz", action="store_true",
                   help="with --bench: also time the prepared npz (PREP output only)")
    p.add_argument("--run-train", action="store_true",
                   help="guarded training path; requires --go and --manifest")
    p.add_argument("--go", default=None, help="path to an APPROVED exact-hash GO json")
    p.add_argument("--manifest", default=None,
                   help="PREP compact npz manifest json")
    p.add_argument("--arm", default="full", choices=sorted(ARM_CONFIGS))
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--steps", type=int, default=3000)
    p.add_argument("--batch-cells", type=int, default=8)
    p.add_argument("--window-events", type=int, default=256)
    p.add_argument("--burn-in", default="exact", choices=("exact", "last_w"))
    p.add_argument("--burn-in-events", type=int, default=128)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--val-every", type=int, default=50)
    p.add_argument("--patience", type=int, default=6)
    p.add_argument("--out-dir", default=None)
    p.add_argument("--threads", type=int, default=min(8, os.cpu_count() or 8),
                   help="torch CPU threads (32 threads on the shared lab box is "
                        "pathologically slow for small tensors)")
    p.add_argument("--bench-steps", type=int, default=20)
    return p.parse_args(argv)


def print_header_v2(mode):
    print("=" * 78)
    print("A2 v2 (fast data path) -- %s" % datetime.now(timezone.utc).isoformat())
    print("python %s | torch %s | threads %d | cuda %s" % (
        sys.version.split()[0], torch.__version__, torch.get_num_threads(),
        torch.cuda.is_available()))
    print("mode: %s" % mode)
    print("code: a2_fastdata.py + a2_train_v2.py (a2_train.py unchanged)")
    print("scope: synthetic tensors by default; training only under an exact GO")
    print("=" * 78)


# --------------------------------------------------------------- dry-run probe
def _dry_run_probe():
    import a2_fastdata as fd
    data = fd.synthetic_fast_data(n_cells=4, n_events=900, seed=123)
    model = build_model(seed=7)
    sampler = WindowSampler(data, np.arange(data.n_cells), 256,
                            burn_in="exact", batch_cells=4)
    batch = sampler.sample(random.Random(5))
    print("synthetic window batch: cells=%s kind=%s control=%s" % (
        batch.cell_ids, tuple(batch.kind.shape), tuple(batch.control.shape)))
    for arm, cfg in sorted(ARM_CONFIGS.items()):
        with torch.no_grad():
            out = replay_windows(model, batch, use_cycle=cfg["use_cycle"],
                                 use_rpt=cfg["use_rpt"])
        print("  %-12s loss_cell_macro=%+.6f  scored=%s" % (
            arm, float(out["loss_cell_macro"]), out["n_scored"].tolist()))
    print("  (forward only -- no backward, no optimiser, no data)")


# --------------------------------------------------------------- GO validation
def validate_v2(go, manifest_path, args):
    """Extra v2 checks on top of a2_train.validate_go."""
    problems = []
    code = go.get("code_sha256") or go.get("code_hashes")
    if isinstance(code, dict):
        pinned = {os.path.basename(str(k)) for k in code}
        for need in REQUIRED_GO_FILES:
            if need not in pinned:
                problems.append("GO must pin %s in code_sha256 (this entry "
                                "point refuses unpinned fast-path code)" % need)
    go_man = go.get("prepared_manifest")
    if go_man and manifest_path and \
            os.path.abspath(str(go_man)) != os.path.abspath(manifest_path):
        problems.append("GO prepared_manifest does not match --manifest")
    expected = go.get("prepared_manifest_sha256")
    if expected and manifest_path:
        got = hash_file(manifest_path)
        if str(expected).lower() != got.lower():
            problems.append("manifest sha256 mismatch: go=%s actual=%s"
                            % (str(expected)[:16], got[:16]))
    for key, value in (("window_events", args.window_events),
                       ("burn_in", args.burn_in),
                       ("burn_in_events", args.burn_in_events),
                       ("batch_cells", args.batch_cells),
                       ("seed", args.seed)):
        if key in go and go[key] != value:
            problems.append("GO %s=%r but command line asks for %r"
                            % (key, go[key], value))
    return problems


# -------------------------------------------------------------------- training
def _train_steps(data, cfg, args, n_steps, seed, sampler, model, opt,
                 do_validation, val_every, patience):
    params = [p for p in model.parameters() if p.requires_grad]
    rng = random.Random(seed)
    history, best, stale = [], {"val_nll": float("inf"), "step": 0,
                                "state": None}, 0
    last_loss = None
    for step in range(1, int(n_steps) + 1):
        model.train()
        batch = sampler.sample(rng)
        out = replay_windows(model, batch, use_cycle=cfg["use_cycle"],
                             use_rpt=cfg["use_rpt"])
        loss = out["loss_cell_macro"]
        if not torch.isfinite(loss):
            raise RuntimeError("non-finite training loss at step %d" % step)
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        last_loss = float(loss)
        if do_validation and (step % int(val_every) == 0 or step == n_steps):
            val = eval_cell_macro(model, data, data.val_index,
                                  use_cycle=cfg["use_cycle"],
                                  use_rpt=cfg["use_rpt"])[0]
            history.append({"step": step, "train_loss": last_loss,
                            "val_nll": val})
            if val < best["val_nll"] - 1e-6:
                best = {"val_nll": val, "step": step,
                        "state": copy.deepcopy(model.state_dict())}
                stale = 0
            else:
                stale += 1
            if stale >= int(patience):
                break
    return {"history": history, "best": best, "last_loss": last_loss,
            "steps_run": step}


def train_one_arm(data, cfg, args):
    std = fit_control_standardizer(data, data.train_index)
    sampler = WindowSampler(data, data.train_index, args.window_events,
                            burn_in=args.burn_in,
                            burn_in_events=args.burn_in_events,
                            batch_cells=args.batch_cells)
    model = build_model(seed=args.seed)
    model.set_control_standardizer(std["mean"], std["scale"])
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                            lr=args.lr, weight_decay=args.weight_decay)
    selection = _train_steps(data, cfg, args, args.steps, args.seed, sampler,
                             model, opt, True, args.val_every, args.patience)
    selected_steps = max(1, int(selection["best"]["step"]))
    # Full refit (same 100 train cells, same seed init, fresh RNG), as before.
    refit = build_model(seed=args.seed)
    refit.set_control_standardizer(std["mean"], std["scale"])
    opt2 = torch.optim.AdamW([p for p in refit.parameters() if p.requires_grad],
                             lr=args.lr, weight_decay=args.weight_decay)
    refit_sampler = WindowSampler(data, data.train_index, args.window_events,
                                  burn_in=args.burn_in,
                                  burn_in_events=args.burn_in_events,
                                  batch_cells=args.batch_cells)
    refit_info = _train_steps(data, cfg, args, selected_steps, args.seed + 1,
                              refit_sampler, refit, opt2, False,
                              args.val_every, args.patience)
    return {
        "arm": cfg["label"], "arm_key": args.arm,
        "selected_steps": selected_steps,
        "best_val_nll": selection["best"]["val_nll"],
        "history": selection["history"],
        "selection_steps_run": selection["steps_run"],
        "refit_last_train_loss": refit_info["last_loss"],
        "standardizer": {
            "n_constant_scale_one_skipped":
                std["n_constant_scale_one_skipped"],
            "mean": [float(v) for v in std["mean"]],
            "scale": [float(v) for v in std["scale"]],
        },
        "model": refit, "optimizer_steps": selected_steps,
    }


def run_train(args):
    if torch.get_num_threads() > 16:
        print("note: torch threads = %d; small-tensor throughput on a shared "
              "box is usually best at 4-8 (use --threads)" % torch.get_num_threads())
    problems, go = validate_go(args.go, args.steps, args.arm)
    if go is not None:
        problems = problems + validate_v2(go, args.manifest, args)
    if problems:
        print("REFUSED -- GO validation failed:")
        for p in problems:
            print("  - %s" % p)
        return 3
    if not args.manifest:
        print("REFUSED -- no PREP-only manifest supplied; A2 will not read payload.")
        return 4
    t0 = time.time()
    data = load_prepared_fast(args.manifest)
    load_seconds = time.time() - t0
    print("prepared (fast loader): %d cells, %d events in %.2f s; "
          "%d train / %d val cells" % (
              data.n_cells, data.n_events, load_seconds,
              len(data.train_index), len(data.val_index)))
    cfg = ARM_CONFIGS[args.arm]
    out_dir = args.out_dir or os.path.join(
        HERE, "runs", "a2_%s_%s" % (args.arm, datetime.now(timezone.utc)
                                    .strftime("%Y%m%dT%H%M%SZ")))
    os.makedirs(out_dir, exist_ok=True)
    t1 = time.time()
    result = train_one_arm(data, cfg, args)
    model = result.pop("model")
    result.update({
        "entry_point": "a2_train_v2.py",
        "go": os.path.abspath(args.go), "go_sha256": hash_file(args.go),
        "manifest": os.path.abspath(args.manifest),
        "manifest_sha256": hash_file(args.manifest),
        "loader": {"npz_path": data.npz_path, "npz_sha256": data.npz_sha256,
                   "n_cells": data.n_cells, "n_events": data.n_events,
                   "load_seconds": load_seconds},
        "window": {"window_events": args.window_events,
                   "burn_in": args.burn_in,
                   "burn_in_events": args.burn_in_events,
                   "batch_cells": args.batch_cells},
        "seed": args.seed, "torch_threads": int(torch.get_num_threads()),
        "elapsed_seconds": time.time() - t1,
        "model_summary": _model_summary(model),
        "arms": {k: {kk: vv for kk, vv in v.items() if kk != "description"}
                 for k, v in ARM_CONFIGS.items()},
    })
    torch.save(model.state_dict(), os.path.join(out_dir, "model_state_dict.pt"))
    with open(os.path.join(out_dir, "fit_report.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print("wrote %s" % out_dir)
    print("FIT DONE: arm=%s selected_steps=%d best_val_nll=%.6f"
          % (args.arm, result["selected_steps"], result["best_val_nll"]))
    return 0


def run_bench(args):
    res = {}
    res["synthetic"] = bench_synthetic(
        batch_cells=args.batch_cells, window_events=args.window_events,
        burn_in_events=args.burn_in_events, steps=args.bench_steps,
        threads=args.threads, seed=args.seed)
    if args.bench_npz:
        if not args.manifest:
            print("REFUSED -- --bench-npz needs --manifest (PREP output only)")
            return 4
        res["prepared_npz"] = bench_npz(
            args.manifest, batch_cells=args.batch_cells,
            window_events=args.window_events,
            burn_in_events=args.burn_in_events, steps=args.bench_steps,
            threads=args.threads, seed=args.seed)
    print(json.dumps(res, indent=2, default=str))
    return 0


def main(argv=None):
    args = parse_args(argv)
    torch.set_num_threads(int(args.threads))
    if args.run_train:
        print_header_v2("TRAIN")
        return run_train(args)
    if args.bench:
        print_header_v2("BENCH (no training, 0 optimizer steps)")
        return run_bench(args)
    print_header_v2("SELF-CHECK" if not args.dry_run else "SELF-CHECK + DRY-RUN")
    print("arms: %s" % json.dumps({k: v["label"]
                                   for k, v in ARM_CONFIGS.items()}))
    print("-" * 78)
    old = run_all(verbose=True)
    print("-" * 78)
    fast = run_all_fast(verbose=True)
    print("-" * 78)
    if args.dry_run:
        _dry_run_probe()
        print("-" * 78)
    ok = old["n_fail"] == 0 and fast["n_fail"] == 0
    print("NO TRAINING PERFORMED. NO PAYLOAD READ. NO CHECKPOINT READ.")
    print("RESULT: %s (legacy %d/%d, fast %d/%d)" % (
        "OK" if ok else "FAILED", old["n_pass"],
        old["n_pass"] + old["n_fail"], fast["n_pass"],
        fast["n_pass"] + fast["n_fail"]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
