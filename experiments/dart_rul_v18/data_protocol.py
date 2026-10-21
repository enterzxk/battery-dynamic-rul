"""V18 full-window arrival-time examples; labels are kept separate from features."""
from __future__ import annotations

import hashlib
from functools import lru_cache
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path("/home/yndx/zxk/rul")
OLD_BASELINES = ROOT / "experiments/isu_irregular_rul_seed42_v1"
DAY = 86400.0
WEEK = 7.0 * DAY
ARMS = ("raw", "sparse2", "delay7d")


@lru_cache(maxsize=1)
def _old_features():
    import importlib.util
    source = OLD_BASELINES / "baselines.py"
    spec = importlib.util.spec_from_file_location("dart_v18_source_baselines", source)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load frozen source baseline features")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.features


def _feature_view(cell, records, query_epoch):
    """Build only the old causal feature input from records visible by query_epoch."""
    if not records:
        raise ValueError("feature view requires visible records")
    latest = records[-1]
    view = {
        "cell_id": str(cell["cell_id"]),
        "group_id": str(cell["group_id"]),
        "role": str(cell["role"]),
        "nominal_capacity_ah": float(cell["nominal_capacity_ah"]),
        "origin_stop_epoch": float(query_epoch),
        "origin_age_weeks": float(latest["calendar_age_weeks"]) +
                            (float(query_epoch) - float(latest["stop_epoch"])) / WEEK,
        "visible_records": records,
    }
    return np.asarray(_old_features()(view), dtype=float)


def _history_key(records):
    pairs = [(int(r["source_rpt_index"]), float(r["arrival_epoch"])) for r in records]
    return json.dumps(pairs, separators=(",", ":"), ensure_ascii=True)


def _arm_records(rows, anchor_index, arm):
    anchor_source = int(rows[anchor_index]["source_rpt_index"])
    lag = 7.0 * DAY if arm == "delay7d" else 0.0
    selected = []
    for i, row in enumerate(rows):
        source = int(row["source_rpt_index"])
        if arm == "sparse2" and i > anchor_index and (source - anchor_source) % 2:
            continue
        item = dict(row)
        item["arrival_epoch"] = float(row["stop_epoch"]) + lag
        selected.append(item)
    return selected


def make_examples(cells):
    """Return arm-balanced per-query examples from already-loaded reviewed cells."""
    out = []
    for cell in cells:
        rows = sorted(cell["records"],
                      key=lambda r: (float(r["stop_epoch"]), int(r["source_rpt_index"])))
        if len(rows) < 2:
            raise ValueError("cell has fewer than two valid source RPTs")
        anchor_index = 1
        anchor = rows[anchor_index]
        anchor_epoch = float(anchor["stop_epoch"])
        event = next((r for r in rows if float(r["capacityAh"]) <= 0.20), None)
        event_epoch = None if event is None else float(event["stop_epoch"])
        arms = {arm: _arm_records(rows, anchor_index, arm) for arm in ARMS}

        for query in rows:
            q = float(query["stop_epoch"])
            if q < anchor_epoch + WEEK:
                continue
            visible_by_arm = {
                arm: [dict(r) for r in arm_rows if float(r["arrival_epoch"]) <= q]
                for arm, arm_rows in arms.items()
            }
            # Keep the same query set in every arm.
            if any(len(visible_by_arm[arm]) < 3 for arm in ARMS):
                continue

            for arm in ARMS:
                visible = visible_by_arm[arm]
                latest_arrival = max(float(r["arrival_epoch"]) for r in visible)
                # The latest arrival can differ from sample time for delay7d.
                q_features = _feature_view(cell, visible, q)
                a_features = _feature_view(cell, visible, latest_arrival)
                target = None if event_epoch is None else max(0.0, (event_epoch - q) / WEEK)
                y_event = 0 if event_epoch is None else int(event_epoch <= q)
                out.append({
                    "cell_id": str(cell["cell_id"]),
                    "group_id": str(cell["group_id"]),
                    "role": str(cell["role"]),
                    "arm": arm,
                    "query_epoch": q,
                    "origin_age_weeks": float(query["calendar_age_weeks"]),
                    "anchor_age_weeks": float(anchor["calendar_age_weeks"]),
                    "last_arrival_epoch": latest_arrival,
                    "delta_weeks": (q - latest_arrival) / WEEK,
                    "elapsed_from_warmup_weeks": (q - anchor_epoch) / WEEK,
                    "warmup_epoch": anchor_epoch,
                    "known_event": any(float(r["capacityAh"]) <= 0.20 for r in visible),
                    "y_event": y_event,
                    "target_rul_weeks": target,
                    "event_time_epoch": event_epoch,
                    "visible_records": visible,
                    "x_query": q_features,
                    "x_anchor": a_features,
                    "history_key": _history_key(visible),
                })
    return out


def build_dataset(cells):
    return make_examples(cells)


def weight_cells(examples):
    """Each cell has equal total mass; its arms and common queries are equal-weight."""
    if not examples:
        raise ValueError("cannot weight an empty example set")
    counts = {}
    for item in examples:
        counts[item["cell_id"]] = counts.get(item["cell_id"], 0) + 1
    n_cells = len(counts)
    return np.asarray([1.0 / counts[x["cell_id"]] for x in examples], dtype=float)


def label_contract_sha256():
    contract = {
        "anchor": "second valid source RPT",
        "query": "source valid RPT stop >= anchor+7d through record end",
        "arms": list(ARMS),
        "sparse2": "keep all through anchor; later source index parity relative to anchor",
        "delay7d": "arrival=source stop+7d",
        "common_queries": "all arms have >=3 arrived records",
        "event": "first valid source Q<=0.20 Ah",
        "no_event": "y_event=0 in observed window; target_rul_weeks=None",
        "feature_clock": "sample and arrival timestamps unchanged; visible sample<=arrival<=query",
    }
    return hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
