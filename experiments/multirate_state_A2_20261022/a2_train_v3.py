"""A2 training entry point v3: burn-in scatter-back fix + full-125 refit.

Why v3 (R1b control arm, 2026-10-24)
------------------------------------
a2_fastdata._burn_in_state chunks the batch by sorted burn-length and returns
torch.cat(chunk states) -- the rows come back in *sorted-chunk* order, not the
original batch order.  With mixed burn lengths the windowed training loss
therefore pairs some cells with another cell's burn-in state (verified on the
server: output rows equal sorted-order exactly, to 1e-17).  Selection and C3
evaluation are unaffected (single-cell sequential replay), so every reported
A2 number is a true measurement of its checkpoints -- but A2's *training* was
handicapped, and A3 ships with the corrected scatter-back.  v3 exists so the
A2-vs-A3 comparison attributes differences to the rate-state mechanism, not to
this bug: a2_fastdata.py stays byte-identical; this entry rebinds the module
attribute a2_fastdata._burn_in_state to a corrected copy at import time (the
call in replay_windows resolves the module global at call time) and adds a
permutation-invariance fixture to the default self-check.

Protocol otherwise mirrors a3_train.py / the repaired full-125 protocol:
selection on the 100 internal train cells (val 25), frozen selected steps,
final refit on ALL 125 cells with the standardizer refit on all 125 and
sampling seed 43.  GO gate = a2_train.validate_go (HERE pointed here) plus
A3-style checks: fresh request_id against the consumed-GO registry,
refit_scope == "all125", fresh out_dir, fits budget, window contract.

Default behaviour (no arguments) is --self-check: legacy + fast fixtures plus
the v3 permutation fixture, on synthetic tensors only.
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

from a2_fastdata import (  # noqa: E402
    CONTROL_DIM, WindowSampler, _run_events, bench_npz, bench_synthetic,
    eval_cell_macro, fit_control_standardizer, load_prepared_fast,
    replay_windows, synthetic_fast_data,
)
from a2_fixtures import run_all  # noqa: E402
from a2_fixtures_fast import run_all_fast  # noqa: E402
from a2_model import build_model  # noqa: E402
from a2_targets import hash_file  # noqa: E402
import a2_fastdata  # noqa: E402
import a2_train  # noqa: E402

REQUIRED_GO_FILES = ("a2_fastdata.py", "a2_train_v3.py")
REFIT_SCOPE_REQUIRED = "all125"
DEFAULT_CONSUMED_REGISTRY = \
    "/home/yndx/zxk/rul/experiments/state/consumed_gos.jsonl"
LOCK_PATHS = (
    "/home/yndx/zxk/rul/automation/state/online_survival_cpu.lock",
    "/home/yndx/zxk/rul/automation/locks/isu_irregular_rul_cpu.lock",
)


class SharedCpuLock(object):
    """One of the two shared project CPU lock files (flock, exclusive)."""

    def __init__(self, paths=None):
        self._paths = list(paths or LOCK_PATHS)
        self._handle = None

    def acquire(self):
        import fcntl
        for path in self._paths:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            handle = open(path, "a+")
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._handle = handle
                return os.path.basename(path)
            except OSError:
                handle.close()
        import fcntl
        handle = open(self._paths[0], "a+")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        self._handle = handle
        return os.path.basename(self._paths[0]) + " (blocking)"

    def release(self):
        if self._handle is not None:
            import fcntl
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None


# ------------------------------------------------------------ burn-in fix v3
def _burn_in_state_v3(model, batch, use_cycle, use_rpt, dtype, device,
                      max_events=300000):
    """Corrected copy of a2_fastdata._burn_in_state (chunking by sorted burn
    length) that scatters chunk results back to the original batch order."""
    B = batch.batch_size
    data = batch.data
    max_len = int(batch.burn_length.max())
    if max_len == 0:
        m, P = model.initial_state(B, device=device, dtype=dtype)
        return m, P
    order = sorted(range(B), key=lambda b: int(batch.burn_length[b]))
    chunks, cur = [], []
    for b in order:
        trial = cur + [b]
        L_trial = max(int(batch.burn_length[x]) for x in trial)
        if cur and len(trial) * L_trial > max_events:
            chunks.append(cur)
            cur = [b]
        else:
            cur = trial
    chunks.append(cur)
    p = next(model.parameters())
    m1, P1 = model.initial_state(1, device=device, dtype=dtype)
    d = int(m1.shape[-1])
    m_out = torch.empty(B, d, device=device, dtype=dtype)
    P_out = torch.empty(B, d, d, device=device, dtype=dtype)
    with torch.no_grad():
        for chunk in chunks:
            n = len(chunk)
            L = max(int(batch.burn_length[b]) for b in chunk)
            kind = torch.zeros(n, L, dtype=torch.long)
            dt_ = torch.zeros(n, L, dtype=dtype)
            ctl = torch.zeros(n, L, CONTROL_DIM, dtype=dtype)
            msk = torch.zeros(n, L, CONTROL_DIM, dtype=dtype)
            y = torch.zeros(n, L, dtype=dtype)
            score = torch.zeros(n, L, dtype=torch.bool)
            q_ref = torch.zeros(n, dtype=dtype)
            for row, b in enumerate(chunk):
                i = int(batch.cell_index[b])
                st = int(batch.burn_start[b])
                ln = int(batch.burn_length[b])
                if ln:
                    off = L - ln
                    sl = data.slice_tensors(i, st, st + ln)
                    kind[row, off:] = sl["kind"][0]
                    dt_[row, off:] = sl["dt"][0].to(dtype)
                    ctl[row, off:] = sl["control"][0].to(dtype)
                    msk[row, off:] = sl["control_mask"][0].to(dtype)
                    y[row, off:] = sl["y"][0].to(dtype)
                    score[row, off:] = sl["score"][0]
                q_ref[row] = batch.q_ref[b].to(dtype)
            m, P = model.initial_state(n, device=device, dtype=dtype)
            m, P, _, _ = _run_events(
                model, kind.to(device), dt_.to(device), ctl.to(device),
                msk.to(device), y.to(device), score.to(device),
                q_ref.to(device), m, P, use_cycle=use_cycle,
                use_rpt=use_rpt, collect_nll=False)
            for row, b in enumerate(chunk):
                m_out[b] = m[row]
                P_out[b] = P[row]
    return m_out, P_out


_ORIGINAL_BURN_IN = a2_fastdata._burn_in_state  # captured before the rebind
a2_fastdata._burn_in_state = _burn_in_state_v3


def _fixture_burn_in_scatter_back():
    """v3-specific fixture: every row of the batched corrected burn-in equals
    the single-cell ground truth for the SAME window, while the pre-fix
    batched version (sorted-chunk order) differs on the same batch — so the
    test actually discriminates the bug.  float32 tolerance 1e-5 (the
    pre-fix mismatch is O(state magnitude), not rounding)."""
    from a2_fastdata import WindowBatch
    original = _ORIGINAL_BURN_IN
    data = synthetic_fast_data(n_cells=6, n_events=900, seed=321)
    model = build_model(seed=11)
    dtype = next(model.parameters()).dtype
    device = next(model.parameters()).device
    sampler = WindowSampler(data, np.arange(data.n_cells), 256,
                            burn_in="exact", batch_cells=6)
    truth_bad = None
    for seed in range(1, 31):
        batch = sampler.sample(random.Random(seed))
        lens = [int(x) for x in batch.burn_length.tolist()]
        if len(set(lens)) < 2:
            continue
        m, P = _burn_in_state_v3(model, batch, True, True, dtype, device)
        m_truth = torch.empty_like(m)
        P_truth = torch.empty_like(P)
        for b in range(batch.batch_size):
            one = WindowBatch(data, [int(batch.cell_index[b])],
                              [int(batch.start[b])], 256, burn_in="exact",
                              burn_in_events=128)
            m1, P1 = original(model, one, True, True, dtype, device)
            m_truth[b] = m1[0]
            P_truth[b] = P1[0]
        dv3 = max(float((m - m_truth).abs().max()),
                  float((P - P_truth).abs().max()))
        if dv3 >= 1e-5:
            continue
        m_bad, P_bad = original(model, batch, True, True, dtype, device)
        dbad = max(float((m_bad - m_truth).abs().max()),
                   float((P_bad - P_truth).abs().max()))
        if dbad > 1e-4:
            truth_bad = (seed, lens, dv3, dbad)
            break
    assert truth_bad is not None, "no seed discriminated the pre-fix bug"
    seed, lens, dv3, dbad = truth_bad
    return ("burn_in_scatter_back_vs_single_cell seed=%d max|v3-truth|=%.2e "
            "max|prefix-truth|=%.2e (lens %r) -- fixture discriminates"
            % (seed, dv3, dbad, sorted(lens)))


# --------------------------------------------------------------- GO validation
def validate_v3(go, manifest_path, args):
    """A3-style additions on top of a2_train.validate_go (HERE pointed here)."""
    problems = []
    code = go.get("code_sha256") or go.get("code_hashes")
    if isinstance(code, dict):
        pinned = {os.path.basename(str(k)) for k in code}
        for need in REQUIRED_GO_FILES:
            if need not in pinned:
                problems.append("GO must pin %s in code_sha256" % need)
    if "A2-V3" not in " ".join(str(go.get(k, "")) for k in
                               ("scope", "task", "purpose", "allowed_scope",
                                "title")).upper():
        problems.append("GO scope does not name A2-V3")
    rid = go.get("request_id")
    if not rid:
        problems.append("GO has no request_id (required for the consumed-GO "
                        "registry)")
    elif not request_id_is_fresh(rid):
        problems.append("request_id %r already appears in the consumed-GO "
                        "registry" % str(rid))
    if go.get("refit_scope") != REFIT_SCOPE_REQUIRED:
        problems.append("GO refit_scope must be %r" % REFIT_SCOPE_REQUIRED)
    go_man = go.get("prepared_manifest")
    if not go_man:
        problems.append("GO must pin prepared_manifest")
    elif manifest_path and os.path.abspath(str(go_man)) != \
            os.path.abspath(manifest_path):
        problems.append("GO prepared_manifest does not match --manifest")
    expected = go.get("prepared_manifest_sha256")
    if not expected:
        problems.append("GO must pin prepared_manifest_sha256")
    elif manifest_path and os.path.exists(manifest_path):
        got = hash_file(manifest_path)
        if str(expected).lower() != got.lower():
            problems.append("manifest sha256 mismatch")
    out_dir = go.get("out_dir")
    if not out_dir:
        problems.append("GO must pin out_dir")
    elif os.path.exists(str(out_dir)):
        problems.append("GO out_dir already exists (must be fresh)")
    fits = go.get("fits_in_this_go")
    if fits is not None and int(fits) < 6:
        problems.append("GO fits_in_this_go=%s but the three-arm run needs 6"
                        % fits)
    for key, value in (("window_events", args.window_events),
                       ("burn_in", args.burn_in),
                       ("burn_in_events", args.burn_in_events),
                       ("batch_cells", args.batch_cells),
                       ("seed", args.seed)):
        if key in go and go[key] != value:
            problems.append("GO %s=%r but command line asks for %r"
                            % (key, go[key], value))
    return problems


def request_id_is_fresh(request_id, path=DEFAULT_CONSUMED_REGISTRY):
    consumed = set()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if not rec.get("request_id"):
                    raise ValueError("consumed-GO registry line without "
                                     "request_id in %s" % path)
                consumed.add(str(rec["request_id"]))
    return str(request_id) not in consumed


def register_consumed_go(path, request_id, go_sha256, finished_utc):
    rid = str(request_id)
    if not request_id_is_fresh(rid, path):
        raise RuntimeError("request_id %r already registered" % rid)
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"request_id": rid, "go_sha256": str(go_sha256),
                            "finished_utc": str(finished_utc)},
                           ensure_ascii=True, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="A2 v3 (burn-in scatter-back fix, full-125 refit): "
                    "self-check by default; guarded training.")
    p.add_argument("--self-check", action="store_true")
    p.add_argument("--run-train", action="store_true",
                   help="guarded training path; requires --go and --manifest")
    p.add_argument("--go", default=None)
    p.add_argument("--manifest", default=None)
    p.add_argument("--arm", default="all", choices=["all", "full", "time",
                                                    "noRPTupdate"])
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--refit-seed", type=int, default=43)
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
    p.add_argument("--threads", type=int, default=min(8, os.cpu_count() or 8))
    return p.parse_args(argv)


def print_header_v3(mode):
    print("=" * 78)
    print("A2 v3 (burn-in scatter-back fix + full-125 refit) -- %s" %
          datetime.now(timezone.utc).isoformat())
    print("python %s | torch %s | threads %d" % (
        sys.version.split()[0], torch.__version__, torch.get_num_threads()))
    print("mode: %s" % mode)
    print("a2_fastdata.py stays byte-identical on disk; the module attribute "
          "_burn_in_state is rebound in-process to the corrected copy")
    print("=" * 78)


def _train_steps(data, cells, cfg, args, n_steps, seed, model, opt,
                 do_validation, val_every, patience):
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


def train_one_arm(data, cfg, args, all_cells):
    std_sel = fit_control_standardizer(data, data.train_index)
    model = build_model(seed=args.seed)
    model.set_control_standardizer(std_sel["mean"], std_sel["scale"])
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                            lr=args.lr, weight_decay=args.weight_decay)
    selection = _train_steps(data, data.train_index, cfg, args, args.steps,
                             args.seed, model, opt, True, args.val_every,
                             args.patience)
    selected_steps = max(1, int(selection["best"]["step"]))
    std_refit = fit_control_standardizer(data, all_cells)
    refit = build_model(seed=args.seed)
    refit.set_control_standardizer(std_refit["mean"], std_refit["scale"])
    opt2 = torch.optim.AdamW(
        [p for p in refit.parameters() if p.requires_grad],
        lr=args.lr, weight_decay=args.weight_decay)
    refit_info = _train_steps(data, all_cells, cfg, args, selected_steps,
                              args.refit_seed, refit, opt2, False,
                              args.val_every, args.patience)
    return {
        "arm": cfg["label"], "arm_key": args.arm if args.arm != "all"
        else cfg.get("arm_key", args.arm),
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
        "burn_in_fix": "scatter-back (a2_train_v3)",
        "standardizer": {
            "n_constant_scale_one_skipped":
                std_sel["n_constant_scale_one_skipped"]},
        "refit_standardizer_on_all_cells": {
            "mean": [float(v) for v in std_refit["mean"]],
            "scale": [float(v) for v in std_refit["scale"]]},
        "model": refit, "optimizer_steps": selected_steps,
    }


def run_train(args):
    problems, go = validate_go_v3(args)
    if problems:
        print("REFUSED -- GO validation failed:")
        for p in problems:
            print("  - %s" % p)
        return 3
    if not args.manifest:
        print("REFUSED -- no PREP-only manifest supplied.")
        return 4
    lock = SharedCpuLock()
    lock_name = lock.acquire()
    try:
        return _run_train_locked(args, go)
    finally:
        lock.release()


def _run_train_locked(args, go):
    t0 = time.time()
    data = load_prepared_fast(args.manifest)
    all_cells = np.sort(np.concatenate([np.asarray(data.train_index,
                                                    dtype=np.int64),
                                        np.asarray(data.val_index,
                                                   dtype=np.int64)]))
    print("prepared (fast loader): %d cells, %d events; %d selection / %d "
          "validation cells; refit on all %d cells" % (
              data.n_cells, data.n_events, len(data.train_index),
              len(data.val_index), len(all_cells)))
    out_dir = os.path.abspath(str(args.out_dir or go["out_dir"]))
    if os.path.exists(out_dir):
        print("REFUSED -- out_dir exists: %s" % out_dir)
        return 5
    os.makedirs(out_dir, exist_ok=False)
    go_sha = hash_file(args.go)
    arms = ["full", "time", "noRPTupdate"] if args.arm == "all" else [args.arm]
    for arm_key in arms:
        cfg = dict(a2_train.ARM_CONFIGS[arm_key])
        cfg["arm_key"] = arm_key
        args.arm = arm_key
        t1 = time.time()
        result = train_one_arm(data, cfg, args, all_cells)
        model = result.pop("model")
        result.update({
            "entry_point": "a2_train_v3.py", "version": "a2-v3-burnin-20261024",
            "go": os.path.abspath(args.go), "go_sha256": go_sha,
            "go_request_id": str(go.get("request_id")),
            "manifest": os.path.abspath(args.manifest),
            "manifest_sha256": hash_file(args.manifest),
            "seed": args.seed, "refit_seed": args.refit_seed,
            "elapsed_seconds": time.time() - t1,
            "model_summary": a2_train._model_summary(model),
        })
        torch.save(model.state_dict(),
                   os.path.join(out_dir, "model_state_dict_%s.pt" % arm_key))
        with open(os.path.join(out_dir, "fit_report_%s.json" % arm_key),
                  "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print("FIT DONE: arm=%s selected_steps=%d best_val_nll=%.6f "
              "refit_cells=%d" % (arm_key, result["selected_steps"],
                                  result["best_val_nll"],
                                  result["n_fit_cells"]["refit"]))
    finished = datetime.now(timezone.utc).isoformat()
    register_consumed_go(DEFAULT_CONSUMED_REGISTRY, go.get("request_id"),
                         go_sha, finished)
    print("registered consumed GO: request_id=%s finished_utc=%s"
          % (go.get("request_id"), finished))
    print("ALL FITS DONE: %d arms, %d fits, elapsed %.1f s"
          % (len(arms), 2 * len(arms), time.time() - t0))
    return 0


def validate_go_v3(args):
    saved_here = a2_train.HERE
    a2_train.HERE = _HERE
    try:
        problems, go = a2_train.validate_go(
            args.go, args.steps, "full" if args.arm == "all" else args.arm)
    finally:
        a2_train.HERE = saved_here
    base = [p for p in problems if p != "GO scope does not name A2"]
    if go is not None:
        base = base + validate_v3(go, args.manifest, args)
    return base, go


def main(argv=None):
    args = parse_args(argv)
    torch.set_num_threads(int(args.threads))
    if args.run_train:
        print_header_v3("TRAIN (GO-gated)")
        return run_train(args)
    print_header_v3("SELF-CHECK")
    old = run_all(verbose=False)
    fast = run_all_fast(verbose=False)
    v3msg = _fixture_burn_in_scatter_back()
    print("[PASS] %s" % v3msg)
    ok = old["n_fail"] == 0 and fast["n_fail"] == 0
    print("NO TRAINING PERFORMED. NO PAYLOAD READ. NO CHECKPOINT READ.")
    print("RESULT: %s (legacy %d/%d, fast %d/%d, v3 fixture 1/1)" % (
        "OK" if ok else "FAILED", old["n_pass"], old["n_pass"] + old["n_fail"],
        fast["n_pass"], fast["n_pass"] + fast["n_fail"]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
