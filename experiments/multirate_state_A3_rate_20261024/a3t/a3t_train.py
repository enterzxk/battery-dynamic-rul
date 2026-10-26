"""A3-T training entry point: GO-gated, default synthetic self-check.

Safety design (mirrors a3_train.py; the guard, registry and lock code is
REUSED from the byte-frozen A3/A2 modules):
* With no arguments (or --self-check) this program runs the synthetic A3-T
  fixtures only: no payload, no processed dataset, no checkpoint, no optimizer
  step, no GO created or consumed, no file written except stdout.
* --run-train refuses to do anything unless it is given an APPROVED, fresh GO
  that pins the SHA256 of a3t_model.py / a3t_train.py (resolved in this a3t/
  directory; pins of the reused A3 files are verified against the parent A3
  directory), the PREP manifest path and sha, a fresh out-dir,
  refit_scope == "all125", all four A3 arms, and a request_id that does NOT
  appear in the consumed-GO registry
  /home/yndx/zxk/rul/experiments/state/consumed_gos.jsonl.  Even then it only
  reads that compact manifest npz (never raw payload) and, after a fully
  successful run, APPENDS one line to the registry (creating the file if
  absent) so the same GO can never be consumed twice.  The registry append,
  the freshness check and the shared CPU locks are the REUSED a3_train
  implementations (imported, not rewritten).
* Training structure (identical to A3): window BPTT via a2_fastdata;
  selection on the manifest's internal train cells with validation on the val
  cells; the selected step count is FROZEN and the final refit runs on ALL
  125 cells with the control standardizer refitted on all 125 cells and
  sampling seed 43 (selection seed 42).  One GO covers 4 arms x 2 fits = 8
  fits; the default --arm all runs all four arms in one process so the single
  request_id is registered exactly once.
* fit_report additions over A3: the learned nu, the learned process-noise
  multipliers, and a refit-model validation evaluation on the SAME val cells
  with BOTH the t NLL and the Gaussian-form NLL (direct comparison against
  the A3 Gaussian reports).
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

from a2_fastdata import (  # noqa: E402  (reused, unchanged)
    WindowSampler, fit_control_standardizer, load_prepared_fast,
    synthetic_fast_data,
)
from a2_targets import hash_file  # noqa: E402  (reused, unchanged)
import a2_train  # noqa: E402  (base GO guard owner, byte-identical on disk)
import a3_train  # noqa: E402  (registry / lock owner, byte-identical on disk)
from a3_model import ARM_CONFIGS, VERSION as A3_VERSION  # noqa: E402

from a3t_model import (  # noqa: E402
    A3T_VERSION, build_arm_model_t, eval_cell_macro_a3t,
    eval_pair_cell_macro_a3t, replay_windows_a3t,
)

# Registry / lock / scope constants REUSED from a3_train (single owner).
REFIT_SCOPE_REQUIRED = a3_train.REFIT_SCOPE_REQUIRED
DEFAULT_CONSUMED_REGISTRY = a3_train.DEFAULT_CONSUMED_REGISTRY
LOCK_PATHS = a3_train.LOCK_PATHS
SharedCpuLock = a3_train.SharedCpuLock
load_consumed_request_ids = a3_train.load_consumed_request_ids
request_id_is_fresh = a3_train.request_id_is_fresh
register_consumed_go = a3_train.register_consumed_go

REQUIRED_GO_FILES = ("a3t_model.py", "a3t_train.py")
# Reused A3/A2 files the GO may pin in addition; resolved against their real
# directories (the base guard only resolves pins against a2_train.HERE, which
# points at this a3t/ directory, so a parent pin looks "missing" there).
_PARENT_PIN_FILES = ("a3_model.py", "a3_train.py", "a3_fixtures.py",
                     "a2_fastdata.py", "a2_targets.py", "a2_train.py")


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="A3-T Student-t innovation model: self-check by default; "
                    "training only under an exact, unconsumed GO.")
    p.add_argument("--self-check", action="store_true",
                   help="run all synthetic fixtures (default behaviour)")
    p.add_argument("--dry-run", action="store_true",
                   help="self-check plus a synthetic four-arm forward probe")
    p.add_argument("--run-train", action="store_true",
                   help="guarded training path; requires --go and --manifest")
    p.add_argument("--go", default=None,
                   help="path to an APPROVED, unconsumed exact-hash GO json")
    p.add_argument("--manifest", default=None,
                   help="PREP compact npz manifest json (PREP v2 cache only)")
    p.add_argument("--arm", default="all",
                   choices=["all"] + sorted(ARM_CONFIGS),
                   help="'all' runs the four arms of the training GO in one "
                        "process (one registry entry)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--refit-seed", type=int, default=43,
                   help="sampling seed of the frozen-steps full-125 refit")
    p.add_argument("--steps", type=int, default=3000)
    p.add_argument("--batch-cells", type=int, default=8)
    p.add_argument("--window-events", type=int, default=256)
    p.add_argument("--burn-in", default="exact", choices=("exact", "last_w"))
    p.add_argument("--burn-in-events", type=int, default=128)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--val-every", type=int, default=50)
    p.add_argument("--patience", type=int, default=6)
    p.add_argument("--out-dir", default=None,
                   help="override the GO out-dir (GO must still pin one)")
    p.add_argument("--threads", type=int,
                   default=min(8, os.cpu_count() or 8))
    return p.parse_args(argv)


def print_header(mode):
    print("=" * 78)
    print("A3-T Student-t innovation model -- %s" %
          datetime.now(timezone.utc).isoformat())
    print("version %s (a3 %s) | python %s | torch %s | threads %d | cuda %s" % (
        A3T_VERSION, A3_VERSION, sys.version.split()[0], torch.__version__,
        torch.get_num_threads(), torch.cuda.is_available()))
    print("mode: %s" % mode)
    print("scope: synthetic tensors by default; training only under an exact, "
          "unconsumed GO")
    print("=" * 78)


# --------------------------------------------------------------- GO validation
def _a3t_scope_compact(go):
    text = " ".join(str(go.get(k, "")) for k in
                    ("scope", "task", "purpose", "allowed_scope", "title")) \
        .upper()
    return "".join(ch for ch in text if ch.isalnum())


def validate_go_a3t(go_path, steps, arm, manifest_path=None,
                    registry_path=DEFAULT_CONSUMED_REGISTRY, expect=None):
    """Base guard (a2_train.validate_go, HERE pointed at the a3t dir) plus the
    A3-T-specific checks.  Returns (problems, go); never consumes or rewrites.

    Fail-closed message handling:
      * the base guard requires the literal "A2" in the scope; that one
        complaint is dropped and replaced by the requirement that the scope
        names A3T (any of 'A3T' / 'A3-T' / 'A3 T' normalise to A3T);
      * pins of reused A3/A2 files look "missing" against the a3t dir; each
        such complaint is dropped ONLY when the pinned sha256 actually matches
        the file in its real directory, otherwise an explicit mismatch is
        added.  Any other complaint is kept verbatim.
    """
    problems = []
    saved_here = a2_train.HERE
    a2_train.HERE = _HERE
    try:
        base_problems, go = a2_train.validate_go(
            go_path, steps, "full" if arm == "all" else arm)
    finally:
        a2_train.HERE = saved_here
    base_problems = [p for p in base_problems
                     if p != "GO scope does not name A2"]
    if go is None:
        problems.extend(base_problems)
        return problems, None
    # resolve parent-file pins against their real directories
    code = go.get("code_sha256") or go.get("code_hashes")
    if isinstance(code, dict):
        for name, expected in code.items():
            base = os.path.basename(str(name))
            if base not in _PARENT_PIN_FILES:
                continue
            missing_msg = "missing file %s" % os.path.join(_HERE, base)
            candidates = [_A3_DIR, _A2_DIR]
            actual = None
            for cand in candidates:
                path = os.path.join(cand, base)
                if os.path.exists(path):
                    actual = hash_file(path)
                    break
            if actual is not None and str(expected).lower() == actual.lower():
                if missing_msg in base_problems:
                    base_problems.remove(missing_msg)
            else:
                problems.append(
                    "pinned reused file %s does not match its directory "
                    "copy (go=%s actual=%s)" % (
                        base, str(expected)[:16],
                        "none" if actual is None else actual[:16]))
    problems.extend(base_problems)
    if "A3T" not in _a3t_scope_compact(go):
        problems.append("GO scope does not name A3T")
    # -- request_id freshness against the consumed-GO registry
    rid = go.get("request_id")
    if not rid:
        problems.append("GO has no request_id (required for the consumed-GO "
                        "registry)")
    else:
        try:
            if not request_id_is_fresh(rid, registry_path):
                problems.append(
                    "request_id %r already appears in the consumed-GO "
                    "registry %s" % (str(rid), registry_path))
        except Exception as exc:  # noqa: BLE001 - fail closed
            problems.append("consumed-GO registry %s unreadable: %s"
                            % (registry_path, exc))
    # -- refit scope
    if go.get("refit_scope") != REFIT_SCOPE_REQUIRED:
        problems.append("GO refit_scope must be %r (selection steps frozen, "
                        "refit on all 125 cells, standardizer fit on all 125);"
                        " got %r" % (REFIT_SCOPE_REQUIRED,
                                     go.get("refit_scope")))
    # -- pinned code files
    if isinstance(code, dict):
        pinned = {os.path.basename(str(k)) for k in code}
        for need in REQUIRED_GO_FILES:
            if need not in pinned:
                problems.append("GO must pin %s in code_sha256" % need)
    # -- all four arms inside the GO arms list (same arms as A3)
    arms = go.get("arms")
    if isinstance(arms, list) and arms:
        missing = sorted(set(ARM_CONFIGS) - {str(a) for a in arms})
        if missing:
            problems.append("GO arms list is missing A3 arms %r" % missing)
    # -- manifest path + sha pinned by the GO and matching --manifest
    go_man = go.get("prepared_manifest")
    if not go_man:
        problems.append("GO must pin prepared_manifest (PREP v2 compact npz "
                        "manifest)")
    elif manifest_path and os.path.abspath(str(go_man)) != \
            os.path.abspath(manifest_path):
        problems.append("GO prepared_manifest does not match --manifest")
    expected_sha = go.get("prepared_manifest_sha256")
    if not expected_sha:
        problems.append("GO must pin prepared_manifest_sha256")
    elif manifest_path and os.path.exists(manifest_path):
        got = hash_file(manifest_path)
        if str(expected_sha).lower() != got.lower():
            problems.append("manifest sha256 mismatch: go=%s actual=%s"
                            % (str(expected_sha)[:16], got[:16]))
    # -- fresh out-dir
    out_dir = go.get("out_dir")
    if not out_dir:
        problems.append("GO must pin out_dir")
    elif os.path.exists(str(out_dir)):
        problems.append("GO out_dir already exists (must be fresh): %s"
                        % str(out_dir))
    # -- fits budget
    fits = go.get("fits_in_this_go")
    if fits is not None:
        need = 8 if arm == "all" else 2
        if int(fits) < need:
            problems.append("GO fits_in_this_go=%s but this run needs %d"
                            % (fits, need))
    # -- window / optimisation contract identical to the command line
    for key, value in (expect or {}).items():
        if key in go and go[key] != value:
            problems.append("GO %s=%r but command line asks for %r"
                            % (key, go[key], value))
    return problems, go


# ------------------------------------------------------------------- training
def _train_steps_t(data, cells, cfg, args, n_steps, seed, model, opt,
                   do_validation, val_every, patience):
    """Windowed truncated-BPTT steps under the t innovation NLL (structure of
    a3_train._train_steps)."""
    params = [p for p in model.parameters() if p.requires_grad]
    sampler = WindowSampler(data, np.asarray(cells, dtype=np.int64),
                            args.window_events, burn_in=args.burn_in,
                            burn_in_events=args.burn_in_events,
                            batch_cells=args.batch_cells)
    rng = random.Random(seed)
    history, best, stale = [], {"val_nll": float("inf"), "step": 0,
                                "state": None}, 0
    last_loss = None
    step = 0
    for step in range(1, int(n_steps) + 1):
        model.train()
        batch = sampler.sample(rng)
        out = replay_windows_a3t(model, batch, cfg)
        loss = out["loss_cell_macro"]
        if not torch.isfinite(loss):
            raise RuntimeError("non-finite training loss at step %d" % step)
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        last_loss = float(loss)
        if do_validation and (step % int(val_every) == 0 or step == n_steps):
            val, _ = eval_cell_macro_a3t(model, data, data.val_index, cfg)
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


def train_one_arm_t(data, cfg, args, all_cells):
    """Selection on the internal train cells -> frozen steps -> full refit,
    identical structure to a3_train.train_one_arm, with the A3-T model and
    t innovation NLL, plus the nu/multiplier report."""
    # ---- selection
    std_sel = fit_control_standardizer(data, data.train_index)
    model = build_arm_model_t(cfg["arm_key"], args.seed)
    model.set_control_standardizer(std_sel["mean"], std_sel["scale"])
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                            lr=args.lr, weight_decay=args.weight_decay)
    selection = _train_steps_t(data, data.train_index, cfg, args, args.steps,
                               args.seed, model, opt, True, args.val_every,
                               args.patience)
    selected_steps = max(1, int(selection["best"]["step"]))
    # ---- frozen-steps refit on all cells (fullrefit protocol)
    std_refit = fit_control_standardizer(data, all_cells)
    refit = build_arm_model_t(cfg["arm_key"], args.seed)
    refit.set_control_standardizer(std_refit["mean"], std_refit["scale"])
    opt2 = torch.optim.AdamW(
        [p for p in refit.parameters() if p.requires_grad],
        lr=args.lr, weight_decay=args.weight_decay)
    refit_info = _train_steps_t(data, all_cells, cfg, args, selected_steps,
                                args.refit_seed, refit, opt2, False,
                                args.val_every, args.patience)
    # ---- refit-model validation on the SAME val cells as A3, both NLL forms
    val_pair = eval_pair_cell_macro_a3t(refit, data, data.val_index, cfg)
    return {
        "arm": cfg["label"], "arm_key": cfg["arm_key"],
        "refit_scope": REFIT_SCOPE_REQUIRED,
        "n_fit_cells": {"selection": int(len(data.train_index)),
                        "refit": int(len(all_cells))},
        "selected_steps": selected_steps,
        "best_val_nll": selection["best"]["val_nll"],
        "history": selection["history"],
        "selection_steps_run": selection["steps_run"],
        "refit_steps_run": refit_info["steps_run"],
        "refit_last_train_loss": refit_info["last_loss"],
        "refit_sampling_seed": int(args.refit_seed),
        "a3t_params": {
            "nu_learned": float(refit.nu_df()),
            "nu_floor": float(refit.nu_floor),
            "sigma_ell_mult_learned": float(refit.sigma_ell_mult()),
            "sigma_R_mult_learned": float(refit.sigma_R_mult()),
            "sigma_ell_effective": float(refit.sigma_ell()),
            "sigma_R_effective": float(refit.sigma_R()),
        },
        "refit_val_eval_on_manifest_val_cells": val_pair,
        "selection_standardizer": {
            "n_constant_scale_one_skipped":
                std_sel["n_constant_scale_one_skipped"]},
        "refit_standardizer_on_all_cells": {
            "n_constant_scale_one_skipped":
                std_refit["n_constant_scale_one_skipped"],
            "mean": [float(v) for v in std_refit["mean"]],
            "scale": [float(v) for v in std_refit["scale"]]},
        "model": refit,
    }


def run_train(args):
    expect = {"window_events": args.window_events, "burn_in": args.burn_in,
              "burn_in_events": args.burn_in_events,
              "batch_cells": args.batch_cells, "seed": args.seed}
    problems, go = validate_go_a3t(args.go, args.steps, args.arm,
                                   args.manifest,
                                   DEFAULT_CONSUMED_REGISTRY, expect)
    if problems:
        print("REFUSED -- GO validation failed:")
        for p in problems:
            print("  - %s" % p)
        return 3
    if not args.manifest:
        print("REFUSED -- no PREP-only manifest supplied; A3-T will not read "
              "payload.")
        return 4
    lock = SharedCpuLock()
    lock_name = lock.acquire()
    try:
        t0 = time.time()
        data = load_prepared_fast(args.manifest)
        load_seconds = time.time() - t0
        all_cells = np.sort(np.concatenate([np.asarray(data.train_index,
                                                        dtype=np.int64),
                                            np.asarray(data.val_index,
                                                       dtype=np.int64)]))
        print("prepared (fast loader): %d cells, %d events in %.2f s; "
              "%d selection / %d validation cells; refit on all %d cells"
              % (data.n_cells, data.n_events, load_seconds,
                 len(data.train_index), len(data.val_index), len(all_cells)))
        out_dir = os.path.abspath(str(args.out_dir or go["out_dir"]))
        if os.path.exists(out_dir):
            print("REFUSED -- effective out_dir already exists (must be "
                  "fresh): %s" % out_dir)
            return 5
        os.makedirs(out_dir, exist_ok=False)
        go_sha = hash_file(args.go)
        arms_to_run = list(ARM_CONFIGS) if args.arm == "all" else [args.arm]
        reports = {}
        for arm_key in arms_to_run:
            cfg = dict(ARM_CONFIGS[arm_key])
            cfg["arm_key"] = arm_key
            t1 = time.time()
            result = train_one_arm_t(data, cfg, args, all_cells)
            model = result.pop("model")
            result.update({
                "entry_point": "a3t_train.py", "version": A3T_VERSION,
                "a3_version": A3_VERSION,
                "go": os.path.abspath(args.go), "go_sha256": go_sha,
                "go_request_id": str(go.get("request_id")),
                "manifest": os.path.abspath(args.manifest),
                "manifest_sha256": hash_file(args.manifest),
                "seed": args.seed,
                "window": {"window_events": args.window_events,
                           "burn_in": args.burn_in,
                           "burn_in_events": args.burn_in_events,
                           "batch_cells": args.batch_cells},
                "elapsed_seconds": time.time() - t1,
                "model_summary": model.model_summary(),
            })
            torch.save(model.state_dict(),
                       os.path.join(out_dir, "model_state_dict_%s.pt"
                                    % arm_key))
            path = os.path.join(out_dir, "fit_report_%s.json" % arm_key)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            reports[arm_key] = result
            vp = result["refit_val_eval_on_manifest_val_cells"]
            print("FIT DONE: arm=%s selected_steps=%d best_val_nll=%.6f "
                  "nu=%.3f q_ell_mult=%.4f q_R_mult=%.4f refit_val(t/g)="
                  "%.6f/%.6f refit_cells=%d -> %s"
                  % (arm_key, result["selected_steps"],
                     result["best_val_nll"],
                     result["a3t_params"]["nu_learned"],
                     result["a3t_params"]["sigma_ell_mult_learned"],
                     result["a3t_params"]["sigma_R_mult_learned"],
                     vp["nll_t"], vp["nll_gauss"],
                     result["n_fit_cells"]["refit"], path))
        with open(os.path.join(out_dir, "consumption_record.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"request_id": str(go.get("request_id")),
                       "go_sha256": go_sha,
                       "fits_in_this_go": int(len(arms_to_run) * 2),
                       "arms": arms_to_run,
                       "refit_scope": REFIT_SCOPE_REQUIRED,
                       "out_dir": out_dir}, f, indent=2)
        finished = datetime.now(timezone.utc).isoformat()
        register_consumed_go(DEFAULT_CONSUMED_REGISTRY,
                             go.get("request_id"), go_sha, finished)
        print("registered consumed GO: request_id=%s go_sha256=%s "
              "finished_utc=%s" % (go.get("request_id"), go_sha[:16],
                                   finished))
        print("ALL FITS DONE: %d arm(s), %d fits, elapsed %.1f s"
              % (len(arms_to_run), 2 * len(arms_to_run),
                 time.time() - t0))
        return 0
    finally:
        lock.release()


# ------------------------------------------------------------------ self-check
def _dry_run_probe():
    data = synthetic_fast_data(n_cells=4, n_events=900, rpt_every=110,
                               seed=123)
    std = fit_control_standardizer(data, np.arange(data.n_cells))
    sampler = WindowSampler(data, np.arange(data.n_cells), 256,
                            burn_in="exact", batch_cells=4)
    batch = sampler.sample(random.Random(5))
    print("synthetic window batch: cells=%s kind=%s dt=%s" % (
        batch.cell_ids, tuple(batch.kind.shape), tuple(batch.dt.shape)))
    for arm_key in sorted(ARM_CONFIGS):
        cfg = dict(ARM_CONFIGS[arm_key])
        cfg["arm_key"] = arm_key
        model = build_arm_model_t(arm_key, seed=7)
        model.set_control_standardizer(std["mean"], std["scale"])
        with torch.no_grad():
            out = replay_windows_a3t(model, batch, cfg)
        print("  %-12s loss_cell_macro(t)=%+.6f gauss=%+.6f scored=%s" % (
            arm_key, float(out["loss_cell_macro"]),
            float(out["loss_cell_macro_gauss"]),
            out["n_scored"].tolist()))
    print("  (forward only -- no backward, no optimiser, no data)")


def main(argv=None):
    args = parse_args(argv)
    torch.set_num_threads(int(args.threads))
    if args.run_train:
        print_header("TRAIN (GO-gated)")
        return run_train(args)
    print_header("SELF-CHECK" if not args.dry_run else "SELF-CHECK + DRY-RUN")
    import a3t_fixtures
    results = a3t_fixtures.run_all(verbose=True,
                                    audit=True)
    print("-" * 78)
    if args.dry_run:
        _dry_run_probe()
        print("-" * 78)
    print("NO TRAINING PERFORMED. NO PAYLOAD READ. NO CHECKPOINT READ. "
          "NO GO CREATED OR CONSUMED.")
    print("RESULT: %s (%d passed / %d failed)" %
          ("OK" if results["n_fail"] == 0 else "FAILED",
           results["n_pass"], results["n_fail"]))
    return 0 if results["n_fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
