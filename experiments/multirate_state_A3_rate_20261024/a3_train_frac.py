"""A3 fraction-pool training entry point: R2 data-efficiency, stage A.

GO-gated like a3_train.py; the default behaviour (no arguments, or
--self-check) is a synthetic self-check.

Safety design (mirrors a3_train.py; no new guard type is introduced)
--------------------------------------------------------------------
* Self-check mode runs synthetic fixtures only: no payload (data/, reports/,
  prep_inputs/, prep_v2), no processed dataset, no checkpoint (run1_fits/
  included), no real manifest or npz read, no GO created or consumed, no
  checkpoint file written.  The only files touched are temp fixtures under the
  system temp dir and the APPENDED SELF_CHECK_LOG.txt (unless
  --no-log-append).
* --run-train refuses to do anything unless it is given an APPROVED, fresh GO
  that pins the SHA256 of a3_model.py / a3_train.py / a3_train_frac.py, the
  fraction and fraction_seed of the run, the PREP manifest path + sha, a fresh
  out_dir, refit_scope == "frac_pool", arms == ["full"], fits_in_this_go >= 2
  (one selection fit + one frozen-steps refit), and a request_id absent from
  the consumed-GO registry /home/yndx/zxk/rul/experiments/state/
  consumed_gos.jsonl.  After a fully successful run it APPENDS the request_id
  to that registry via a3_train.register_consumed_go (append-once,
  duplicate-refusing), so the same GO can never be consumed twice.
* Frozen subset semantics (R2 stage A; full contract in README_A3_FRAC_ZH.md):
  - pool = the 125 PREP manifest cells (100 internal train + 25 internal val),
    enforced at load time, fail-closed;
  - chosen = round(fraction * 125) cells sampled without replacement from the
    SORTED cell-id list via numpy default_rng(fraction_seed).choice indices;
  - selection split inside the chosen subset: membership of the original
    100/25 split; if the chosen original-val part has < 3 cells, fall back to
    a 20% holdout of the chosen subset drawn by CONTINUING the same rng stream
    right after the subset draw (frozen design decision);
  - final refit on ALL chosen cells with the control standardizer fitted on
    the chosen cells and sampling seed --refit-seed (43) -- the R1 protocol
    structure applied to the fraction pool; one arm (full) only, 2 fits/GO.

REUSE vs ADAPTATION NOTE: a3_train.py and a3_model.py are byte-frozen on disk
and imported unchanged; nothing is monkey-patched.  The gate re-implements the
validate_go_a3 pattern on the same base guard (a2_train.validate_go with
a2_train.HERE temporarily pointed at the A3 directory so pinned code hashes
resolve there; the base guard's single "GO scope does not name A2" complaint
dropped -- fail-closed: if that text ever changes, frac GOs are refused, never
waved through), plus frac-specific checks.  The training core is
a3_train.train_one_arm (which itself drives a3_train._train_steps) reused
verbatim on a shallow-copy data view whose train/val split attributes point at
the fraction selection subset; the inherited report label is then corrected to
refit_scope "frac_pool" and the fraction bookkeeping fields are attached (the
only place the frac path deliberately deviates from the all125 labelling, and
the only mutation of anything train_one_arm returns).
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
import traceback
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
    fit_control_standardizer, load_prepared_fast, synthetic_fast_data,
)
from a2_targets import hash_file  # noqa: E402  (reused, unchanged)
import a2_train  # noqa: E402  (base GO guard owner, byte-identical on disk)

import a3_train  # noqa: E402  (byte-frozen; helpers reused, never modified)
from a3_model import ARM_CONFIGS, VERSION  # noqa: E402

REQUIRED_GO_FILES_FRAC = ("a3_model.py", "a3_train.py", "a3_train_frac.py")
REFIT_SCOPE_FRAC = "frac_pool"
ARM_KEY_ALLOWED = "full"
FRACTION_CHOICES = (0.25, 0.5, 1.0)
DEFAULT_FRACTION = 0.25
DEFAULT_FRACTION_SEED = 42
EXPECTED_POOL_CELLS = 125
EXPECTED_TRAIN_CELLS = 100
EXPECTED_VAL_CELLS = 25
# Frozen design decisions for the selection-val fallback (README section 3):
FALLBACK_VAL_MIN_CELLS = 3    # original-val part below 3 cells -> fallback
FALLBACK_VAL_FRACTION = 0.20  # hold out round(0.20 * k) cells via rng
SELF_CHECK_LOG_NAME = "SELF_CHECK_LOG.txt"
RUL_ROOT = "/home/yndx/zxk/rul"

# Window/optimisation contract pinned by a3_train and inherited verbatim.
_EXPECT_CONTRACT = {"window_events": 256, "burn_in": "exact",
                    "burn_in_events": 128, "batch_cells": 8, "seed": 42}


# ------------------------------------------------------------------ arguments
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="A3 fraction-pool training (R2 data efficiency, stage A):"
                    " self-check by default; training only under an exact, "
                    "unconsumed GO pinning the fraction.")
    p.add_argument("--self-check", action="store_true",
                   help="run all synthetic fixtures (default behaviour)")
    p.add_argument("--run-train", action="store_true",
                   help="guarded training path; requires --go and --manifest")
    p.add_argument("--go", default=None,
                   help="path to an APPROVED, unconsumed exact-hash frac GO json")
    p.add_argument("--manifest", default=None,
                   help="PREP compact npz manifest json (PREP v2 cache only)")
    p.add_argument("--arm", default=ARM_KEY_ALLOWED, choices=[ARM_KEY_ALLOWED],
                   help="the frac entry trains A3_full only")
    p.add_argument("--fraction", type=float, default=DEFAULT_FRACTION,
                   choices=list(FRACTION_CHOICES),
                   help="fraction of the 125-cell pool used for BOTH selection "
                        "and refit (0.25 -> 31, 0.5 -> 62, 1.0 -> 125 cells)")
    p.add_argument("--fraction-seed", type=int, default=DEFAULT_FRACTION_SEED,
                   help="numpy default_rng seed of the without-replacement "
                        "subset draw over the sorted cell-id list")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--refit-seed", type=int, default=43,
                   help="sampling seed of the frozen-steps refit on the "
                        "chosen pool (R1 protocol: 43)")
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
    p.add_argument("--no-log-append", action="store_true",
                   help="self-check: do not append SELF_CHECK_LOG.txt")
    return p.parse_args(argv)


def print_header(mode):
    print("=" * 78)
    print("A3 fraction-pool training (R2 stage A) -- %s"
          % datetime.now(timezone.utc).isoformat())
    print("version %s | python %s | torch %s | numpy %s | threads %d | "
          "cuda %s" % (VERSION, sys.version.split()[0], torch.__version__,
                       np.__version__, torch.get_num_threads(),
                       torch.cuda.is_available()))
    print("mode: %s" % mode)
    print("scope: synthetic tensors by default; training only under an exact, "
          "unconsumed GO pinning fraction/fraction_seed")
    print("=" * 78)


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ------------------------------------------------- frozen subset semantics
def select_fraction_cells(cell_ids, train_cell_ids, val_cell_ids, fraction,
                          fraction_seed):
    """Frozen R2 stage-A subset semantics (README_A3_FRAC_ZH.md section 3).

    1. pool = sorted unique str(cell_ids); k = int(round(fraction * len(pool))).
    2. Chosen cells: numpy default_rng(fraction_seed).choice(len(pool), size=k,
       replace=False) -- INDICES into the sorted id list -- then the chosen ids
       are sorted again.  Same seed => same subset; fraction 1.0 => the whole
       sorted pool.
    3. Selection split inside the chosen subset by membership of the ORIGINAL
       train/val split: sel = chosen & original-val if it has >= 3 cells
       (design threshold), else FALLBACK -- continue the SAME rng stream
       (right after the subset draw), permutation(k), hold out the first
       max(1, round(0.20 * k)) entries as selection val; the remaining chosen
       cells (original train AND original val alike) become selection train.
       The fallback affects the selection stage only; the refit always uses
       all chosen cells.
    Returns a plain-dict record (JSON-serialisable; goes into the fit report).
    """
    fraction = float(fraction)
    if not (0.0 < fraction <= 1.0):
        raise ValueError("fraction must be in (0, 1]; got %r" % fraction)
    all_sorted = sorted({str(c) for c in cell_ids})
    n_pool = len(all_sorted)
    k = int(round(fraction * n_pool))
    k = max(1, min(k, n_pool))
    rng = np.random.default_rng(int(fraction_seed))
    idx = rng.choice(n_pool, size=k, replace=False)
    chosen = sorted(all_sorted[int(i)] for i in idx)
    train_set = {str(c) for c in train_cell_ids}
    val_set = {str(c) for c in val_cell_ids}
    sel_train = [c for c in chosen if c in train_set]
    sel_val = [c for c in chosen if c in val_set]
    info = {
        "fraction": fraction,
        "fraction_seed": int(fraction_seed),
        "n_pool_cells": int(n_pool),
        "n_chosen_cells": int(len(chosen)),
        "selected_cell_ids": chosen,
        "fallback_val_min_cells": int(FALLBACK_VAL_MIN_CELLS),
        "fallback_val_fraction": float(FALLBACK_VAL_FRACTION),
        "selection_val_fallback_used": False,
        "selection_val_source": "original_val_split",
    }
    if len(sel_val) >= FALLBACK_VAL_MIN_CELLS:
        selection_train, selection_val = sel_train, sel_val
    else:
        perm = rng.permutation(len(chosen))
        n_hold = max(1, int(round(FALLBACK_VAL_FRACTION * len(chosen))))
        hold = sorted(int(i) for i in perm[:n_hold])
        selection_val = [chosen[i] for i in hold]
        hold_set = set(hold)
        selection_train = [c for j, c in enumerate(chosen) if j not in hold_set]
        info["selection_val_fallback_used"] = True
        info["selection_val_source"] = "rng_holdout_20pct"
    info["selection_train_cell_ids"] = sorted(selection_train)
    info["selection_val_cell_ids"] = sorted(selection_val)
    info["n_selection_train"] = int(len(info["selection_train_cell_ids"]))
    info["n_selection_val"] = int(len(info["selection_val_cell_ids"]))
    return info


def build_frac_data_view(data, selection_train_ids, selection_val_ids):
    """Shallow copy of a FastA2Data whose split attributes point at the
    fraction selection subset.

    The copy shares every event tensor (no data duplication, nothing loaded
    again) and carries its own train_index / val_index; the ORIGINAL object's
    split attributes are never touched.  This is plain OOP attribute
    assignment on a copy -- not a monkey-patch of a2_fastdata.
    """
    view = copy.copy(data)
    index = {c: i for i, c in enumerate(data.cell_ids)}
    missing = ({str(c) for c in selection_train_ids} |
               {str(c) for c in selection_val_ids}) - set(data.cell_ids)
    if missing:
        raise ValueError("selection split references unknown cells: %r"
                         % sorted(missing)[:3])
    view.train_index = np.asarray(
        sorted(index[str(c)] for c in selection_train_ids), dtype=np.int64)
    view.val_index = np.asarray(
        sorted(index[str(c)] for c in selection_val_ids), dtype=np.int64)
    return view


def frac_train_one_arm(data_view, cfg, args, pool_cell_index, subset_info):
    """a3_train.train_one_arm reused verbatim on the fraction-pool view.

    train_one_arm(selection cells = data_view.train_index, refit cells =
    pool_cell_index) IS the frozen frac protocol: selection + early stopping
    on the fraction selection subset (standardizer on those cells, seed
    args.seed), then the frozen-steps refit on ALL chosen pool cells with the
    control standardizer fitted on the chosen pool and sampling seed
    args.refit_seed.  The only adaptation: the inherited "all125" refit_scope
    label is corrected to "frac_pool" and the fraction bookkeeping is
    attached; no training behaviour is altered.
    """
    result = a3_train.train_one_arm(data_view, cfg, args, pool_cell_index)
    model = result.pop("model")
    result["refit_scope"] = REFIT_SCOPE_FRAC
    result["refit_scope_note"] = (
        "fraction-pool refit: selection steps frozen from the fraction "
        "selection subset; the final refit and the control standardizer run "
        "on ALL chosen fraction-pool cells only (sampling seed refit_seed)")
    result["fraction"] = float(subset_info["fraction"])
    result["fraction_seed"] = int(subset_info["fraction_seed"])
    result["n_pool_cells"] = int(subset_info["n_pool_cells"])
    result["n_chosen_cells"] = int(subset_info["n_chosen_cells"])
    result["selected_cell_ids"] = list(subset_info["selected_cell_ids"])
    result["selection_train_cell_ids"] = \
        list(subset_info["selection_train_cell_ids"])
    result["selection_val_cell_ids"] = \
        list(subset_info["selection_val_cell_ids"])
    result["n_selection_train"] = int(subset_info["n_selection_train"])
    result["n_selection_val"] = int(subset_info["n_selection_val"])
    result["selection_val_source"] = str(subset_info["selection_val_source"])
    result["selection_val_fallback_used"] = \
        bool(subset_info["selection_val_fallback_used"])
    result["refit_n_cells"] = int(len(pool_cell_index))
    result["model"] = model
    return result


# --------------------------------------------------------------- GO validation
def validate_go_frac(go_path, steps, arm, manifest_path=None, fraction=None,
                     fraction_seed=None,
                     registry_path=a3_train.DEFAULT_CONSUMED_REGISTRY,
                     expect=None):
    """The validate_go_a3 gate pattern applied to a frac GO.

    Base guard (a2_train.validate_go, HERE pointed at the A3 dir so pinned
    hashes resolve there) + frac-specific checks.  Returns (problems, go);
    never consumes or rewrites anything.
    """
    problems = []
    if arm != ARM_KEY_ALLOWED:
        problems.append("the frac entry trains arm %r only; got %r"
                        % (ARM_KEY_ALLOWED, arm))
    saved_here = a2_train.HERE
    a2_train.HERE = _HERE
    try:
        base_problems, go = a2_train.validate_go(go_path, steps, arm)
    finally:
        a2_train.HERE = saved_here
    # The base guard requires the literal "A2" in the scope; A3 GOs name A3.
    # Drop exactly that complaint and require A3 instead (fail-closed).
    base_problems = [p for p in base_problems
                     if p != "GO scope does not name A2"]
    problems.extend(base_problems)
    if go is None:
        return problems, None
    if "A3" not in a3_train._a3_scope_text(go):
        problems.append("GO scope does not name A3")
    # -- request_id freshness against the consumed-GO registry (same helper
    #    and same default registry as a3_train)
    rid = go.get("request_id")
    if not rid:
        problems.append("GO has no request_id (required for the consumed-GO "
                        "registry)")
    else:
        try:
            if not a3_train.request_id_is_fresh(rid, registry_path):
                problems.append(
                    "request_id %r already appears in the consumed-GO "
                    "registry %s" % (str(rid), registry_path))
        except Exception as exc:  # noqa: BLE001 - fail closed
            problems.append("consumed-GO registry %s unreadable: %s"
                            % (registry_path, exc))
    # -- refit scope: the frac pool, not all125
    if go.get("refit_scope") != REFIT_SCOPE_FRAC:
        problems.append("GO refit_scope must be %r (selection steps frozen, "
                        "refit + standardizer on the chosen fraction pool "
                        "only); got %r"
                        % (REFIT_SCOPE_FRAC, go.get("refit_scope")))
    # -- pinned code files: the three frac entry files
    code = go.get("code_sha256") or go.get("code_hashes")
    if isinstance(code, dict):
        pinned = {os.path.basename(str(k)) for k in code}
        for need in REQUIRED_GO_FILES_FRAC:
            if need not in pinned:
                problems.append("GO must pin %s in code_sha256" % need)
    # -- arms exactly ["full"]
    arms = go.get("arms")
    if not (isinstance(arms, list) and arms == [ARM_KEY_ALLOWED]):
        problems.append("GO arms must be exactly [%r] (the frac entry trains "
                        "A3_full only); got %r" % (ARM_KEY_ALLOWED, arms))
    # -- fraction pinned, legal, and matching the command line
    go_frac = go.get("fraction")
    legal = False
    try:
        fv = float(go_frac)
        legal = any(fv == float(c) for c in FRACTION_CHOICES)
    except (TypeError, ValueError):
        legal = False
    if not legal:
        problems.append("GO fraction must be one of %r; got %r"
                        % (list(FRACTION_CHOICES), go_frac))
    if fraction is not None:
        try:
            same = float(go_frac) == float(fraction)
        except (TypeError, ValueError):
            same = False
        if not same:
            problems.append("GO fraction=%r but command line asks for %r"
                            % (go_frac, float(fraction)))
    elif go_frac is None:
        problems.append("GO must pin fraction")
    # -- fraction_seed pinned and matching the command line
    go_seed = go.get("fraction_seed")
    if fraction_seed is not None:
        try:
            same_seed = int(go_seed) == int(fraction_seed)
        except (TypeError, ValueError):
            same_seed = False
        if not same_seed:
            problems.append("GO fraction_seed=%r but command line asks for %r"
                            % (go_seed, int(fraction_seed)))
    elif go_seed is None:
        problems.append("GO must pin fraction_seed")
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
    # -- fits budget: one arm -> selection + frozen-steps refit = 2 fits
    fits = go.get("fits_in_this_go")
    if fits is not None:
        if int(fits) < 2:
            problems.append("GO fits_in_this_go=%s but this run needs 2 "
                            "(selection + frozen-steps refit)" % fits)
    # -- window / optimisation contract identical to the command line
    for key, value in (expect or {}).items():
        if key in go and go[key] != value:
            problems.append("GO %s=%r but command line asks for %r"
                            % (key, go[key], value))
    return problems, go


# ------------------------------------------------------------------- training
def run_train_frac(args):
    expect = {"window_events": args.window_events, "burn_in": args.burn_in,
              "burn_in_events": args.burn_in_events,
              "batch_cells": args.batch_cells, "seed": args.seed}
    problems, go = validate_go_frac(args.go, args.steps, args.arm,
                                    args.manifest, args.fraction,
                                    args.fraction_seed,
                                    a3_train.DEFAULT_CONSUMED_REGISTRY, expect)
    if problems:
        print("REFUSED -- GO validation failed:")
        for p in problems:
            print("  - %s" % p)
        return 3
    if not args.manifest:
        print("REFUSED -- no PREP-only manifest supplied; A3 frac will not "
              "read payload.")
        return 4
    lock = a3_train.SharedCpuLock()
    lock_name = lock.acquire()
    try:
        t0 = time.time()
        data = load_prepared_fast(args.manifest)
        load_seconds = time.time() - t0
        train_ids = [data.cell_ids[int(i)] for i in data.train_index]
        val_ids = [data.cell_ids[int(i)] for i in data.val_index]
        if int(data.n_cells) != EXPECTED_POOL_CELLS or \
                len(train_ids) != EXPECTED_TRAIN_CELLS or \
                len(val_ids) != EXPECTED_VAL_CELLS or \
                set(train_ids) | set(val_ids) != set(data.cell_ids):
            print("REFUSED -- manifest pool shape violates the frozen R2 "
                  "design (need %d cells = %d internal train + %d internal "
                  "val covering every cell); got %d cells, %d train, %d val"
                  % (EXPECTED_POOL_CELLS, EXPECTED_TRAIN_CELLS,
                     EXPECTED_VAL_CELLS, int(data.n_cells), len(train_ids),
                     len(val_ids)))
            return 6
        subset = select_fraction_cells(data.cell_ids, train_ids, val_ids,
                                       args.fraction, args.fraction_seed)
        print("prepared (fast loader): %d cells, %d events in %.2f s; "
              "fraction %s seed %d -> %d of %d cells chosen "
              "(selection: %d train / %d val, source %s); refit on all %d "
              "chosen cells"
              % (data.n_cells, data.n_events, load_seconds,
                 args.fraction, args.fraction_seed, subset["n_chosen_cells"],
                 subset["n_pool_cells"], subset["n_selection_train"],
                 subset["n_selection_val"], subset["selection_val_source"],
                 subset["n_chosen_cells"]))
        out_dir = os.path.abspath(str(args.out_dir or go["out_dir"]))
        if os.path.exists(out_dir):
            print("REFUSED -- effective out_dir already exists (must be "
                  "fresh): %s" % out_dir)
            return 5
        os.makedirs(out_dir, exist_ok=False)
        go_sha = hash_file(args.go)
        view = build_frac_data_view(data, subset["selection_train_cell_ids"],
                                    subset["selection_val_cell_ids"])
        pool_index = np.asarray(
            [data.cell_index(c) for c in subset["selected_cell_ids"]],
            dtype=np.int64)
        cfg = dict(ARM_CONFIGS[args.arm])
        cfg["arm_key"] = args.arm
        t1 = time.time()
        result = frac_train_one_arm(view, cfg, args, pool_index, subset)
        model = result.pop("model")
        result.update({
            "entry_point": "a3_train_frac.py", "version": VERSION,
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
                   os.path.join(out_dir, "model_state_dict_%s.pt" % args.arm))
        path = os.path.join(out_dir, "fit_report_%s.json" % args.arm)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        with open(os.path.join(out_dir, "consumption_record.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"request_id": str(go.get("request_id")),
                       "go_sha256": go_sha,
                       "fits_in_this_go": 2,
                       "arms": [args.arm],
                       "refit_scope": REFIT_SCOPE_FRAC,
                       "fraction": float(args.fraction),
                       "fraction_seed": int(args.fraction_seed),
                       "n_pool_cells": int(subset["n_pool_cells"]),
                       "n_chosen_cells": int(subset["n_chosen_cells"]),
                       "out_dir": out_dir}, f, indent=2)
        finished = datetime.now(timezone.utc).isoformat()
        a3_train.register_consumed_go(a3_train.DEFAULT_CONSUMED_REGISTRY,
                                      go.get("request_id"), go_sha, finished)
        print("FIT DONE: arm=%s fraction=%s chosen_cells=%d "
              "selected_steps=%d best_val_nll=%.6f refit_cells=%d -> %s"
              % (args.arm, args.fraction, subset["n_chosen_cells"],
                 result["selected_steps"], result["best_val_nll"],
                 result["refit_n_cells"], path))
        print("registered consumed GO: request_id=%s go_sha256=%s "
              "finished_utc=%s" % (go.get("request_id"), go_sha[:16],
                                   finished))
        print("ALL FITS DONE: 1 arm (%s), 2 fits, elapsed %.1f s"
              % (args.arm, time.time() - t0))
        return 0
    finally:
        lock.release()


# ------------------------------------------------------------------ self-check
_SMOKE_REPORT = {}


def test_fraction_sampling_determinism():
    ids = ["sim_%03d" % i for i in range(125)]
    train_ids, val_ids = ids[:100], ids[100:]
    seen = {}
    for fraction, expect_k in ((0.25, 31), (0.5, 62), (1.0, 125)):
        a = select_fraction_cells(ids, train_ids, val_ids, fraction, 42)
        b = select_fraction_cells(ids, train_ids, val_ids, fraction, 42)
        _assert(a["selected_cell_ids"] == b["selected_cell_ids"],
                "same seed must reproduce the same subset (f=%s)" % fraction)
        _assert(a == b, "full subset record must be deterministic (f=%s)"
                % fraction)
        got = len(a["selected_cell_ids"])
        _assert(got == expect_k == int(round(fraction * 125)),
                "f=%s must pick %d cells, got %d" % (fraction, expect_k, got))
        _assert(a["selected_cell_ids"] == sorted(a["selected_cell_ids"]),
                "chosen ids must be sorted")
        _assert(len(set(a["selected_cell_ids"])) == got,
                "chosen ids must be unique")
        _assert(set(a["selected_cell_ids"]) <= set(ids),
                "chosen ids must come from the pool")
        seen[fraction] = a["selected_cell_ids"]
    c = select_fraction_cells(ids, train_ids, val_ids, 0.25, 43)
    _assert(c["selected_cell_ids"] != seen[0.25],
            "different fraction_seed must give a different subset")
    return ("seed 42 deterministic; k=31/62/125 for f=0.25/0.5/1.0; "
            "seed 43 differs; chosen sorted+unique")


def test_fraction_full_pool_identity():
    ids = ["sim_%03d" % i for i in range(125)]
    train_ids, val_ids = ids[:100], ids[100:]
    a = select_fraction_cells(ids, train_ids, val_ids, 1.0, 42)
    _assert(a["selected_cell_ids"] == ids,
            "f=1.0 must reproduce the full sorted pool exactly")
    _assert(not a["selection_val_fallback_used"] and
            a["selection_val_source"] == "original_val_split",
            "f=1.0 keeps the original split (25 val cells >= threshold)")
    _assert(a["selection_train_cell_ids"] == train_ids and
            a["selection_val_cell_ids"] == val_ids,
            "f=1.0 selection split must equal the original 100/25 split")
    _assert(a["n_selection_train"] == 100 and a["n_selection_val"] == 25,
            "f=1.0 selection sizes must be 100/25")
    return ("f=1.0: chosen == all 125 sorted ids; selection split == "
            "original 100/25; no fallback")


def test_selection_split_original_and_fallback():
    # -- primary branch, guaranteed: f=1.0 on 10 cells with 3 original-val
    ids10 = ["u_%02d" % i for i in range(10)]
    tr7, va3 = ids10[:7], ids10[7:]
    a = select_fraction_cells(ids10, tr7, va3, 1.0, 42)
    _assert(a["selection_val_source"] == "original_val_split" and
            not a["selection_val_fallback_used"],
            ">= 3 original-val cells must use the original split")
    _assert(a["selection_train_cell_ids"] == sorted(tr7) and
            a["selection_val_cell_ids"] == sorted(va3),
            "primary branch must slice the chosen subset by original "
            "train/val membership")
    # -- fallback branch, guaranteed: 9 train / 1 val, f=0.5 -> k=5, val
    #    part <= 1 < 3
    idsB = ["v_%02d" % i for i in range(10)]
    trB, vaB = idsB[:9], idsB[9:]
    b = select_fraction_cells(idsB, trB, vaB, 0.5, 42)
    _assert(b["n_chosen_cells"] == 5, "f=0.5 on 10 cells must choose 5")
    _assert(b["selection_val_fallback_used"] and
            b["selection_val_source"] == "rng_holdout_20pct",
            "original-val part < 3 must trigger the fallback")
    n_hold = max(1, int(round(FALLBACK_VAL_FRACTION * 5)))
    _assert(b["n_selection_val"] == n_hold == 1 and
            b["n_selection_train"] == 5 - n_hold,
            "fallback holdout must be round(0.2*k) cells")
    st, sv = set(b["selection_train_cell_ids"]), \
        set(b["selection_val_cell_ids"])
    _assert(not (st & sv) and st | sv == set(b["selected_cell_ids"]),
            "fallback split must partition the chosen subset")
    # exact replication of the rng continuation (same stream after the draw)
    rng = np.random.default_rng(42)
    idx = rng.choice(10, size=5, replace=False)
    chosen = sorted(idsB[int(i)] for i in idx)
    _assert(b["selected_cell_ids"] == chosen,
            "subset draw replication mismatch")
    perm = rng.permutation(5)
    expect_val = sorted(chosen[int(i)] for i in perm[:n_hold])
    _assert(b["selection_val_cell_ids"] == expect_val,
            "fallback holdout must continue the same rng stream after the "
            "subset draw")
    # -- boundary: exactly 2 original-val chosen -> fallback; exactly 3 -> primary
    idsC = ["w_%02d" % i for i in range(12)]
    c = select_fraction_cells(idsC, idsC[:10], idsC[10:], 1.0, 42)
    _assert(c["selection_val_fallback_used"] and
            c["n_selection_val"] == int(round(0.2 * 12)) == 2,
            "2 original-val cells (< 3) must fall back at f=1.0")
    idsD = ["x_%02d" % i for i in range(12)]
    d = select_fraction_cells(idsD, idsD[:9], idsD[9:], 1.0, 42)
    _assert(not d["selection_val_fallback_used"] and
            d["selection_val_cell_ids"] == sorted(idsD[9:]),
            "3 original-val cells must keep the original split at f=1.0")
    return ("original-split branch and rng-holdout fallback verified "
            "(rng continuation replicated bit-exactly); boundary 2 vs 3 "
            "original-val cells switches the branch")


def test_frac_data_view_isolation():
    data = synthetic_fast_data(n_cells=5, n_events=300, rpt_every=50, seed=5)
    _assert(data.train_index is None and data.val_index is None,
            "synthetic data starts without a split")
    control_ref, kind_ref = data.control, data.kind
    view = build_frac_data_view(data, data.cell_ids[:3], data.cell_ids[3:])
    _assert(view is not data, "view must be a distinct object")
    _assert(np.array_equal(view.train_index, [0, 1, 2]) and
            np.array_equal(view.val_index, [3, 4]),
            "view split attributes must point at the requested cells")
    _assert(view.control is control_ref and view.kind is kind_ref and
            view.y is data.y,
            "view must share the event tensors (no re-load, no copy)")
    _assert(data.train_index is None and data.val_index is None,
            "building a view must not touch the original split attributes")
    data.train_index = np.arange(3, dtype=np.int64)
    data.val_index = np.arange(3, 5, dtype=np.int64)
    snapshot = (data.train_index.copy(), data.val_index.copy())
    view2 = build_frac_data_view(data, [data.cell_ids[4]], [data.cell_ids[0]])
    _assert(np.array_equal(view2.train_index, [4]) and
            np.array_equal(view2.val_index, [0]),
            "second view must carry its own split")
    _assert(np.array_equal(data.train_index, snapshot[0]) and
            np.array_equal(data.val_index, snapshot[1]),
            "original split attributes must remain untouched")
    return ("shallow view shares event tensors, owns its split attributes; "
            "original object never mutated (single vs existing split)")


def test_fraction_smoke_train_loop():
    data = synthetic_fast_data(n_cells=6, n_events=500, rpt_every=50, seed=77)
    train_ids, val_ids = data.cell_ids[:4], data.cell_ids[4:]
    sub = select_fraction_cells(data.cell_ids, train_ids, val_ids, 0.5, 42)
    view = build_frac_data_view(data, sub["selection_train_cell_ids"],
                                sub["selection_val_cell_ids"])
    pool = np.asarray([data.cell_index(c)
                       for c in sub["selected_cell_ids"]], dtype=np.int64)
    args = argparse.Namespace(steps=2, seed=42, refit_seed=43, batch_cells=2,
                              window_events=64, burn_in="exact",
                              burn_in_events=8, lr=1e-3, weight_decay=1e-4,
                              val_every=1, patience=6)
    cfg = dict(ARM_CONFIGS[ARM_KEY_ALLOWED])
    cfg["arm_key"] = ARM_KEY_ALLOWED
    t0 = time.time()
    result = frac_train_one_arm(view, cfg, args, pool, sub)
    elapsed = time.time() - t0
    model = result.pop("model")
    _assert(result["refit_scope"] == REFIT_SCOPE_FRAC,
            "frac report must be relabelled refit_scope=frac_pool")
    _assert(result["refit_n_cells"] == len(pool) ==
            result["n_chosen_cells"],
            "refit must run on exactly the chosen pool cells")
    _assert(result["n_fit_cells"] == {"selection": len(view.train_index),
                                      "refit": len(pool)},
            "n_fit_cells must count the fraction selection/refit cells")
    _assert(int(result["selected_steps"]) >= 1,
            "frozen-steps refit needs >= 1 selected step")
    _assert(np.isfinite(result["best_val_nll"]) and
            np.isfinite(result["refit_last_train_loss"]),
            "selection/refit losses must be finite")
    _assert(result["fraction"] == 0.5 and result["fraction_seed"] == 42,
            "fraction bookkeeping must be recorded")
    _assert(result["n_selection_train"] + result["n_selection_val"] ==
            result["n_chosen_cells"] and
            set(result["selection_train_cell_ids"]) |
            set(result["selection_val_cell_ids"]) ==
            set(result["selected_cell_ids"]),
            "selection split must partition the chosen subset")
    # refit standardizer must be fitted on the CHOSEN POOL (a2_fastdata rule)
    std = fit_control_standardizer(data, pool)
    _assert(np.array_equal(
        np.asarray(result["refit_standardizer_on_all_cells"]["mean"],
                   dtype=np.float64), std["mean"].numpy()) and
        np.array_equal(
            np.asarray(result["refit_standardizer_on_all_cells"]["scale"],
                       dtype=np.float64), std["scale"].numpy()),
        "refit standardizer must equal fit_control_standardizer on the "
        "chosen pool")
    _assert(result["refit_sampling_seed"] == 43,
            "refit sampling seed must be 43 (R1 protocol)")
    _assert(bool(model.model_summary()), "model summary must be present")
    _SMOKE_REPORT["report"] = result
    return ("synthetic 6-cell pool f=0.5: chosen=%d (sel_train=%d / "
            "sel_val=%d), selected_steps=%d, refit loss %.4f, "
            "pool-standardizer exact, refit seed 43, %.1f s"
            % (result["n_chosen_cells"], result["n_selection_train"],
               result["n_selection_val"], result["selected_steps"],
               result["refit_last_train_loss"], elapsed))


def test_frac_report_fields_and_refit_scope():
    report = _SMOKE_REPORT.get("report")
    _assert(report is not None, "smoke fixture must run first")
    required = ("fraction", "fraction_seed", "n_pool_cells",
                "n_chosen_cells", "selected_cell_ids", "n_selection_train",
                "n_selection_val", "selection_train_cell_ids",
                "selection_val_cell_ids", "selection_val_source",
                "selection_val_fallback_used", "selected_steps",
                "refit_n_cells", "refit_scope", "refit_sampling_seed")
    missing = [k for k in required if k not in report]
    _assert(not missing, "fit_report is missing required fields: %r" % missing)
    _assert(report["refit_scope"] == "frac_pool",
            "refit_scope must be frac_pool")
    _assert(isinstance(report["selected_cell_ids"], list) and
            report["selected_cell_ids"],
            "selected_cell_ids must be a non-empty list of cell ids")
    return ("all %d required frac fit_report fields present (fraction, "
            "fraction_seed, n_pool_cells, selected cell ids, "
            "n_selection_train/val, selected_steps, refit_n_cells); "
            "refit_scope=frac_pool" % len(required))


_DELETE = object()  # sentinel: remove the key entirely


def _synthetic_frac_go(tmp):
    """Write a well-formed synthetic frac GO; return (go_path, manifest_path).

    The manifest is a tiny temp JSON stand-in -- it is only hashed by the
    gate, never loaded.  Code hashes are the REAL hashes of the three pinned
    files in the A3 directory (own code files, allowed opens).
    """
    code_hashes = {name: hash_file(os.path.join(_HERE, name))
                   for name in REQUIRED_GO_FILES_FRAC}
    manifest_path = os.path.join(tmp, "synthetic_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"synthetic": True,
                   "note": "gate-test stand-in only; never loaded"}, f)
    go = {
        "status": "APPROVED", "allow_fit": True, "allow_train": True,
        "scope": "A3 FRAC TRAIN/FIT: fraction-pool data-efficiency run "
                 "(R2 stage A), arm full only, selection on the fraction "
                 "selection subset + frozen-steps refit on the chosen "
                 "fraction pool, exactly 2 fits in this GO",
        "request_id": "SYNTHETIC_A3_FRAC_GO_20261024_T1",
        "owner_thread_id": "synthetic-self-check",
        "issued_utc": "2026-10-24T00:00:00Z",
        "issued_by": {"controller": "synthetic self-check fixture"},
        "code_sha256": code_hashes,
        "max_steps": 3000,
        "arms": ["full"],
        "fraction": 0.25,
        "fraction_seed": 42,
        "seed": 42,
        "refit_seed": 43,
        "batch_cells": 8,
        "window_events": 256,
        "burn_in": "exact",
        "burn_in_events": 128,
        "lr": 0.001,
        "weight_decay": 0.0001,
        "val_every": 50,
        "patience": 6,
        "threads": 8,
        "refit_scope": REFIT_SCOPE_FRAC,
        "fits_in_this_go": 2,
        "prepared_manifest": manifest_path,
        "prepared_manifest_sha256": hash_file(manifest_path),
        "out_dir": os.path.join(tmp, "out_frac_synthetic"),
        "data_scope": "synthetic gate-test stand-in only; no real data",
    }
    return go, manifest_path


def _write_go(tmp, go, name="GO_synthetic_frac.json"):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(go, f, indent=2)
    return path


def test_frac_go_accepts_wellformed():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        registry = os.path.join(tmp, "consumed_registry_tmp.jsonl")
        go, manifest_path = _synthetic_frac_go(tmp)
        go_path = _write_go(tmp, go)
        problems, got = validate_go_frac(go_path, 3000, ARM_KEY_ALLOWED,
                                         manifest_path, 0.25, 42, registry,
                                         _EXPECT_CONTRACT)
        _assert(not problems, "well-formed frac GO refused: %r" % problems)
        _assert(got.get("fraction") == 0.25 and got.get("arms") == ["full"],
                "accepted GO must expose fraction/arms")
    return ("well-formed synthetic frac GO accepted with 0 problems "
            "(temp registry + temp manifest stand-in only)")


def test_frac_go_separated_from_all125_gate():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        registry = os.path.join(tmp, "consumed_registry_tmp.jsonl")
        go, manifest_path = _synthetic_frac_go(tmp)
        go_path = _write_go(tmp, go)
        problems, _ = a3_train.validate_go_a3(go_path, 3000,
                                              ARM_KEY_ALLOWED,
                                              manifest_path, registry)
        _assert(problems, "the all125 gate must refuse a frac GO "
                          "(gate separation)")
        _assert(any("refit_scope" in p for p in problems),
                "the all125 refusal must name refit_scope; got %r" % problems)
    return ("a3_train.validate_go_a3 refuses the frac GO (%d complaints, "
            "incl. refit_scope) -- the separate frac gate is required"
            % len(problems))


def test_frac_go_refuses_mutations():
    import tempfile
    base_hashes = {name: hash_file(os.path.join(_HERE, name))
                   for name in REQUIRED_GO_FILES_FRAC}
    names = sorted(base_hashes)

    def hashes_with(corrupt=None, drop=None):
        h = dict(base_hashes)
        if corrupt is not None:
            h[names[corrupt]] = "0" * 64
        if drop:
            h.pop(drop, None)
        return h

    cases = [
        ("wrong hash a3_model.py", {"code_sha256": hashes_with(0)}),
        ("wrong hash a3_train.py", {"code_sha256": hashes_with(1)}),
        ("wrong hash a3_train_frac.py", {"code_sha256": hashes_with(2)}),
        ("a3_train_frac.py not pinned",
         {"code_sha256": hashes_with(drop="a3_train_frac.py")}),
        ("status not APPROVED", {"status": "PROPOSED"}),
        ("allow_fit/allow_train false",
         {"allow_fit": False, "allow_train": False}),
        ("already-consumed marker",
         {"consumed_at": "2026-10-24T00:00:00Z"}),
        ("scope without A3", {"scope": "FRAC TRAIN/FIT: fraction-pool run"}),
        ("refit_scope all125", {"refit_scope": "all125"}),
        ("refit_scope missing", {"refit_scope": _DELETE}),
        ("arms two arms", {"arms": ["full", "time"]}),
        ("arms not a list", {"arms": "full"}),
        ("fraction 0.5 vs pinned 0.25", {"fraction": 0.5}),
        ("fraction 0.3 illegal", {"fraction": 0.3}),
        ("fraction missing", {"fraction": _DELETE}),
        ("fraction_seed mismatch", {"fraction_seed": 7}),
        ("fraction_seed missing", {"fraction_seed": _DELETE}),
        ("request_id reused", None),          # pre-registered below
        ("manifest sha mismatch", {"prepared_manifest_sha256": "0" * 64}),
        ("manifest path differs", None),      # other --manifest below
        ("out_dir not fresh", None),          # pre-created below
        ("max_steps too small", {"max_steps": 2999}),
        ("window contract changed", {"window_events": 128}),
        ("fits_in_this_go too small", {"fits_in_this_go": 1}),
    ]
    refused = 0
    labels = []
    for label, mut in cases:
        with tempfile.TemporaryDirectory() as tmp:
            registry = os.path.join(tmp, "consumed_registry_tmp.jsonl")
            go, manifest_path = _synthetic_frac_go(tmp)
            if label == "request_id reused":
                a3_train.register_consumed_go(
                    registry, go["request_id"], "0" * 64,
                    "2026-10-24T00:00:00Z")
            if mut is not None:
                for key, value in mut.items():
                    if value is _DELETE:
                        go.pop(key, None)
                    else:
                        go[key] = value
            go_path = _write_go(tmp, go)
            if label == "out_dir not fresh":
                os.makedirs(go["out_dir"], exist_ok=True)
            mp = manifest_path
            if label == "manifest path differs":
                mp = os.path.join(tmp, "other_manifest.json")
                with open(mp, "w", encoding="utf-8") as f:
                    json.dump({"synthetic": True}, f)
            problems, _ = validate_go_frac(go_path, 3000, ARM_KEY_ALLOWED,
                                           mp, 0.25, 42, registry,
                                           _EXPECT_CONTRACT)
            _assert(problems, "mutation %r was NOT refused (gate hole)"
                    % label)
            refused += 1
            labels.append(label)
    _assert(refused >= 10, "expected >= 10 refused mutations, got %d"
            % refused)
    return ("%d/%d mutations refused: code hashes x3 + missing pin, status, "
            "allow flags, consumed marker, scope, refit_scope (all125/"
            "missing), arms (extra/not-a-list), fraction (mismatch/"
            "illegal/missing), fraction_seed (mismatch/missing), request_id "
            "reuse, manifest sha/path, stale out_dir, max_steps, window "
            "contract, fits budget" % (refused, len(cases)))


def test_consumed_registry_append_and_duplicate_refusal():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "consumed_registry_tmp.jsonl")
        line = a3_train.register_consumed_go(
            path, "SYN_FRAC_RID_1", "ab" * 32, "2026-10-24T00:00:00+00:00")
        with open(path, "r", encoding="utf-8") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
        _assert(len(lines) == 1, "append must add exactly one line")
        rec = json.loads(lines[0])
        _assert(set(rec) == {"request_id", "go_sha256", "finished_utc"} and
                rec["request_id"] == "SYN_FRAC_RID_1",
                "registry line fields must be exactly "
                "request_id/go_sha256/finished_utc")
        _assert(line == lines[0], "returned line must match the file")
        doubled = False
        try:
            a3_train.register_consumed_go(path, "SYN_FRAC_RID_1", "ab" * 32,
                                          "again")
        except RuntimeError:
            doubled = False
        else:
            doubled = True
        _assert(not doubled, "duplicate request_id must be refused")
        with open(path, "r", encoding="utf-8") as f:
            _assert(len([ln for ln in f.read().splitlines() if ln.strip()])
                    == 1, "refused duplicate must not append")
        bad = os.path.join(tmp, "bad_registry_tmp.jsonl")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("not-json\n")
        failed = False
        try:
            a3_train.load_consumed_request_ids(bad)
        except Exception:  # noqa: BLE001 - expected
            failed = True
        _assert(failed, "malformed registry line must fail closed")
    return ("append-once verified (exact fields), duplicate refused, "
            "malformed line fail-closed (a3_train helpers, temp path only)")


FRAC_FIXTURES = (
    ("fraction_sampling_determinism", test_fraction_sampling_determinism),
    ("fraction_full_pool_identity", test_fraction_full_pool_identity),
    ("selection_split_original_and_fallback",
     test_selection_split_original_and_fallback),
    ("frac_data_view_isolation", test_frac_data_view_isolation),
    ("fraction_smoke_train_loop", test_fraction_smoke_train_loop),
    ("frac_report_fields_and_refit_scope",
     test_frac_report_fields_and_refit_scope),
    ("frac_go_accepts_wellformed", test_frac_go_accepts_wellformed),
    ("frac_go_separated_from_all125_gate",
     test_frac_go_separated_from_all125_gate),
    ("frac_go_refuses_mutations", test_frac_go_refuses_mutations),
    ("consumed_registry_append_and_duplicate_refusal",
     test_consumed_registry_append_and_duplicate_refusal),
)


def _frac_is_forbidden(path, tmp_prefix):
    """a3_fixtures rule (data/reports/prep_inputs, prep_v2, real registry,
    A2 runs/prep, .npz) plus the frac-specific adds: run1_fits and the
    checkpoints tree."""
    import a3_fixtures
    if a3_fixtures._is_forbidden_path(path, tmp_prefix):
        return True
    p = str(path)
    if p.startswith(tmp_prefix):
        return False
    if "run1_fits" in p:
        return True
    if p.startswith(RUL_ROOT + "/checkpoints"):
        return True
    return False


def run_self_check():
    """Run the synthetic frac fixtures; returns (text_lines, n_fail,
    code_hashes).  Prints progress live."""
    import tempfile
    import a3_fixtures  # own-directory harness, reused unchanged
    out = []

    def emit(line):
        print(line)
        out.append(line)

    results = []
    auditor = a3_fixtures.OpenAuditor()
    auditor.__enter__()
    try:
        for name, fn in FRAC_FIXTURES:
            try:
                detail = fn()
                results.append((name, True, str(detail)))
                emit("[PASS] %-48s %s" % (name, detail))
            except Exception as exc:  # noqa: BLE001 - fail loud, keep going
                results.append((name, False,
                                "%s: %s" % (type(exc).__name__, exc)))
                emit("[FAIL] %-48s %s: %s"
                     % (name, type(exc).__name__, exc))
                for ln in traceback.format_exc().rstrip().splitlines():
                    emit("       " + ln)
    finally:
        auditor.__exit__(None, None, None)
        tmp_prefix = tempfile.gettempdir()
        forbidden = [p for p in auditor.paths
                     if _frac_is_forbidden(p, tmp_prefix)]
        emit("[AUDIT] global open() audit: %d paths recorded, %d forbidden"
             % (len(auditor.paths), len(forbidden)))
        for p in forbidden[:5]:
            emit("[AUDIT]   forbidden open: %s" % p)
        if forbidden:
            results.append(("global_no_payload_audit", False,
                            "forbidden opens: %r" % forbidden[:5]))
    n_pass = sum(1 for r in results if r[1])
    n_fail = len(results) - n_pass
    emit("-" * 78)
    emit("NO TRAINING PERFORMED. NO PAYLOAD READ. NO CHECKPOINT READ "
         "(run1_fits included). NO GO CREATED OR CONSUMED.")
    emit("RESULT: %s (%d passed / %d failed)"
         % ("OK" if n_fail == 0 else "FAILED", n_pass, n_fail))
    code_hashes = {name: hash_file(os.path.join(_HERE, name))
                   for name in REQUIRED_GO_FILES_FRAC}
    return out, n_fail, code_hashes


def append_self_check_log(lines, code_hashes):
    """Append-only: add this run's report to SELF_CHECK_LOG.txt."""
    stamp = datetime.now(timezone.utc).isoformat()
    header = [
        "===== a3_train_frac self-check %s =====" % stamp,
        "=" * 78,
        "A3 FRACTION-POOL TRAIN (R2 data-efficiency stage A) -- %s" % stamp,
        "mode: SYNTHETIC ONLY -- 0 real fits | 0 payload reads (data/, "
        "reports/, prep_inputs/, prep_v2) | 0 checkpoint reads (run1_fits "
        "included) | 0 GO created or consumed",
        "python %s | torch %s | numpy %s | model %s"
        % (sys.version.split()[0], torch.__version__, np.__version__, VERSION),
        "code_sha256: %s" % json.dumps(code_hashes, sort_keys=True),
        "-" * 78,
    ]
    with open(os.path.join(_HERE, SELF_CHECK_LOG_NAME), "a",
              encoding="utf-8") as f:
        f.write("\n".join(header + list(lines)) + "\n")
        f.flush()
        os.fsync(f.fileno())


def main(argv=None):
    args = parse_args(argv)
    torch.set_num_threads(int(args.threads))
    if args.run_train:
        print_header("TRAIN FRAC (GO-gated)")
        return run_train_frac(args)
    print_header("SELF-CHECK (synthetic only)")
    out, n_fail, code_hashes = run_self_check()
    if not args.no_log_append:
        append_self_check_log(out, code_hashes)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
