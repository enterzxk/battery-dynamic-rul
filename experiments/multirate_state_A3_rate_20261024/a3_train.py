"""A3 training entry point: GO-gated, default synthetic self-check.

Safety design (mirrors a2_train.py / a2_train_v2.py; one guard reused)
----------------------------------------------------------------------
* With no arguments (or --self-check) this program runs the synthetic A3
  fixtures only: no payload, no processed dataset, no checkpoint, no optimizer
  step, no GO created or consumed, no file written except stdout.
* --run-train refuses to do anything unless it is given an APPROVED, fresh GO
  that pins the SHA256 of a3_model.py / a3_train.py, the PREP manifest path and
  sha, a fresh out-dir, refit_scope == "all125", all four A3 arms, and a
  request_id that does NOT appear in the consumed-GO registry
  /home/yndx/zxk/rul/experiments/state/consumed_gos.jsonl.  Even then it only
  reads that compact manifest npz (never raw payload) and, after a fully
  successful run, APPENDS one line {"request_id", "go_sha256", "finished_utc"}
  to the registry (creating the file if absent) so the same GO can never be
  consumed twice (GO-mutation re-consumption event of 2026-10-23).
* Training structure (protocol section 4): window BPTT via a2_fastdata;
  selection on the manifest's internal train cells with validation on the val
  cells; the selected step count is FROZEN and the final refit runs on ALL 125
  cells with the control standardizer refitted on all 125 cells and sampling
  seed 43 (selection seed 42).  One GO covers 4 arms x 2 fits = 8 fits; the
  default --arm all runs all four arms in one process so the single request_id
  is registered exactly once.

REUSE vs ADAPTATION NOTE: a2_train.validate_go is reused as the base guard.
It hardcodes two A2 things: the scope check requires the literal "A2" and code
hashes resolve against a2_train.HERE (the A2 directory).  The wrapper below
temporarily points a2_train.HERE at the A3 directory and drops the base
guard's single "GO scope does not name A2" complaint (fail-closed: if that
message text ever changes, A3 GOs are refused, never waved through), then adds
the A3-specific checks.
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import json
import os
import random
import sys
import time
from datetime import datetime, timezone

import numpy as np
import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
_A2_DIR = os.path.join(os.path.dirname(_HERE), "multirate_state_A2_20261022")
if not os.path.isdir(_A2_DIR):
    raise ImportError("A2 code directory not found at %s" % _A2_DIR)
if _A2_DIR not in sys.path:
    sys.path.insert(0, _A2_DIR)

from a2_fastdata import (  # noqa: E402  (reused, unchanged)
    WindowSampler, fit_control_standardizer, load_prepared_fast,
    synthetic_fast_data,
)
from a2_targets import hash_file  # noqa: E402  (reused, unchanged)
import a2_train  # noqa: E402  (base GO guard owner, byte-identical on disk)

from a3_model import (  # noqa: E402
    ARM_CONFIGS, VERSION, build_arm_model, build_model, eval_cell_macro_a3,
    replay_windows_a3,
)

REQUIRED_GO_FILES = ("a3_model.py", "a3_train.py")
REFIT_SCOPE_REQUIRED = "all125"
DEFAULT_CONSUMED_REGISTRY = \
    "/home/yndx/zxk/rul/experiments/state/consumed_gos.jsonl"
LOCK_PATHS = (
    "/home/yndx/zxk/rul/automation/state/online_survival_cpu.lock",
    "/home/yndx/zxk/rul/automation/locks/isu_irregular_rul_cpu.lock",
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="A3 state-space model: self-check by default; training "
                    "only under an exact, unconsumed GO.")
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
    print("A3 individual-rate state model -- %s" %
          datetime.now(timezone.utc).isoformat())
    print("version %s | python %s | torch %s | threads %d | cuda %s" % (
        VERSION, sys.version.split()[0], torch.__version__,
        torch.get_num_threads(), torch.cuda.is_available()))
    print("mode: %s" % mode)
    print("scope: synthetic tensors by default; training only under an exact, "
          "unconsumed GO")
    print("=" * 78)


# ------------------------------------------------------- consumed-GO registry
def load_consumed_request_ids(path):
    """Set of request_ids in the consumed-GO registry (jsonl, append-only).

    A missing file is an empty registry (fresh).  A malformed line raises:
    fail-closed, never fail-open.
    """
    consumed = set()
    if not os.path.exists(path):
        return consumed
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            rid = rec.get("request_id")
            if not rid:
                raise ValueError("consumed-GO registry line without "
                                 "request_id in %s" % path)
            consumed.add(str(rid))
    return consumed


def request_id_is_fresh(request_id, path=DEFAULT_CONSUMED_REGISTRY):
    return str(request_id) not in load_consumed_request_ids(path)


def register_consumed_go(path, request_id, go_sha256, finished_utc):
    """Append one {"request_id","go_sha256","finished_utc"} line (create the
    file if absent).  Refuses (raises) if the request_id is already present."""
    rid = str(request_id)
    if rid in load_consumed_request_ids(path):
        raise RuntimeError("request_id %r already registered in %s -- GO "
                           "double consumption refused" % (rid, path))
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    line = json.dumps({"request_id": rid, "go_sha256": str(go_sha256),
                       "finished_utc": str(finished_utc)},
                      ensure_ascii=True, sort_keys=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())
    return line


# --------------------------------------------------------------- GO validation
def _a3_scope_text(go):
    return " ".join(str(go.get(k, "")) for k in
                    ("scope", "task", "purpose", "allowed_scope", "title")) \
        .upper()


def validate_go_a3(go_path, steps, arm, manifest_path=None,
                   registry_path=DEFAULT_CONSUMED_REGISTRY, expect=None):
    """Base guard (a2_train.validate_go, HERE pointed at the A3 dir) plus the
    A3-specific checks.  Returns (problems, go); never consumes or rewrites."""
    problems = []
    saved_here = a2_train.HERE
    a2_train.HERE = _HERE
    try:
        base_problems, go = a2_train.validate_go(
            go_path, steps, "full" if arm == "all" else arm)
    finally:
        a2_train.HERE = saved_here
    # The base guard requires the literal "A2" in the scope; A3 GOs name A3.
    # Drop exactly that complaint and require A3 instead (fail-closed).
    base_problems = [p for p in base_problems
                     if p != "GO scope does not name A2"]
    problems.extend(base_problems)
    if go is None:
        return problems, None
    if "A3" not in _a3_scope_text(go):
        problems.append("GO scope does not name A3")
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
    code = go.get("code_sha256") or go.get("code_hashes")
    if isinstance(code, dict):
        pinned = {os.path.basename(str(k)) for k in code}
        for need in REQUIRED_GO_FILES:
            if need not in pinned:
                problems.append("GO must pin %s in code_sha256" % need)
    # -- all four arms inside the GO arms list
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


# ------------------------------------------------------------------ CPU locks
class SharedCpuLock(object):
    """One of the two shared CPU lock files (flock, exclusive).

    Protocol: CPU 8 threads + two shared CPU locks, so at most two training
    processes share the box.  Try both non-blocking, fall back to blocking on
    the first.
    """

    def __init__(self, paths=None):
        self._paths = list(paths or LOCK_PATHS)
        self._handle = None

    def acquire(self):
        for path in self._paths:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            handle = open(path, "a+")
            try:
                fcntl.flock(handle.fileno(),
                            fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._handle = handle
                return os.path.basename(path)
            except OSError:
                handle.close()
        handle = open(self._paths[0], "a+")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        self._handle = handle
        return os.path.basename(self._paths[0]) + " (blocking)"

    def release(self):
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None


# ------------------------------------------------------------------- training
def _train_steps(data, cells, cfg, args, n_steps, seed, model, opt,
                 do_validation, val_every, patience):
    """Windowed truncated-BPTT steps (structure of a2_train_v2._train_steps)."""
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
        out = replay_windows_a3(model, batch, cfg)
        loss = out["loss_cell_macro"]
        if not torch.isfinite(loss):
            raise RuntimeError("non-finite training loss at step %d" % step)
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        last_loss = float(loss)
        if do_validation and (step % int(val_every) == 0 or step == n_steps):
            val, _ = eval_cell_macro_a3(model, data, data.val_index, cfg)
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


def train_one_arm(data, cfg, args, all_cells):
    """Selection on the internal train cells -> frozen steps -> full refit.

    selection: 100 internal train cells, standardizer on those cells, seed 42.
    refit:     ALL cells (125), standardizer refitted on all cells, frozen
               selected step count, sampling seed --refit-seed (43).
    """
    # ---- selection
    std_sel = fit_control_standardizer(data, data.train_index)
    model = build_arm_model(cfg["arm_key"], args.seed)
    model.set_control_standardizer(std_sel["mean"], std_sel["scale"])
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                            lr=args.lr, weight_decay=args.weight_decay)
    selection = _train_steps(data, data.train_index, cfg, args, args.steps,
                             args.seed, model, opt, True, args.val_every,
                             args.patience)
    selected_steps = max(1, int(selection["best"]["step"]))
    # ---- frozen-steps refit on all cells (fullrefit protocol)
    std_refit = fit_control_standardizer(data, all_cells)
    refit = build_arm_model(cfg["arm_key"], args.seed)
    refit.set_control_standardizer(std_refit["mean"], std_refit["scale"])
    opt2 = torch.optim.AdamW(
        [p for p in refit.parameters() if p.requires_grad],
        lr=args.lr, weight_decay=args.weight_decay)
    refit_info = _train_steps(data, all_cells, cfg, args, selected_steps,
                              args.refit_seed, refit, opt2, False,
                              args.val_every, args.patience)
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
    problems, go = validate_go_a3(args.go, args.steps, args.arm,
                                  args.manifest,
                                  DEFAULT_CONSUMED_REGISTRY, expect)
    if problems:
        print("REFUSED -- GO validation failed:")
        for p in problems:
            print("  - %s" % p)
        return 3
    if not args.manifest:
        print("REFUSED -- no PREP-only manifest supplied; A3 will not read "
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
            result = train_one_arm(data, cfg, args, all_cells)
            model = result.pop("model")
            result.update({
                "entry_point": "a3_train.py", "version": VERSION,
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
            print("FIT DONE: arm=%s selected_steps=%d best_val_nll=%.6f "
                  "refit_cells=%d -> %s"
                  % (arm_key, result["selected_steps"],
                     result["best_val_nll"],
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
        model = build_arm_model(arm_key, seed=7)
        model.set_control_standardizer(std["mean"], std["scale"])
        with torch.no_grad():
            out = replay_windows_a3(model, batch, cfg)
        print("  %-12s loss_cell_macro=%+.6f  scored=%s" % (
            arm_key, float(out["loss_cell_macro"]),
            out["n_scored"].tolist()))
    print("  (forward only -- no backward, no optimiser, no data)")


def main(argv=None):
    args = parse_args(argv)
    torch.set_num_threads(int(args.threads))
    if args.run_train:
        print_header("TRAIN (GO-gated)")
        return run_train(args)
    print_header("SELF-CHECK" if not args.dry_run else "SELF-CHECK + DRY-RUN")
    import a3_fixtures
    results = a3_fixtures.run_all(verbose=True,
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
