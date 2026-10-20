"""Strict adapter for reviewed per-cell raw-RPT records; never reads source archives."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json, math, re


def _dt(value):
    if not value:
        raise ValueError("missing RPT stop/start timestamp")
    text=re.sub(r"(\.\d{6})000(?=$|[+-])",r"\1",value.replace("Z","+00:00"))
    d = datetime.fromisoformat(text)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def normalize_cell(payload, expected_role, allowed_roles=("train", "development")):
    cid = str(payload["cell_id"])
    role = payload["role"]
    if role not in allowed_roles or role != expected_role:
        raise ValueError("role mismatch or forbidden role for " + cid)
    nominal = float(payload.get("nominal_capacity_ah", 0.25))
    if not math.isfinite(nominal) or abs(nominal-0.25)>1e-9:
        raise ValueError("unexpected nominal capacity; ISU protocol fixes 0.25 Ah")
    baseline_stop = _dt(payload.get("baseline_stop"))
    rows = []
    for raw in payload["records"]:
        if not all(k in raw for k in ("source_rpt_index","start","stop","capacityAh","valid")):
            raise ValueError("record misses required raw-RPT field")
        flag=raw["valid"]
        if isinstance(flag,str):
            if flag.lower() not in ("true","false","1","0","yes","no"):
                raise ValueError("invalid valid flag")
            flag=flag.lower() in ("true","1","yes")
        if not isinstance(flag,(bool,int)):
            raise ValueError("valid must be boolean or 0/1")
        if not flag:
            continue
        stop = _dt(raw["stop"])
        start = _dt(raw["start"])
        if stop < start:
            raise ValueError("RPT stop precedes start")
        age = (stop - baseline_stop).total_seconds() / 604800.0
        q = float(raw["capacityAh"])
        if not math.isfinite(age) or not math.isfinite(q) or age < 0 or q < 0:
            raise ValueError("nonfinite or negative age/capacity")
        rows.append({
            "source_rpt_index": int(raw["source_rpt_index"]),
            "start": start.isoformat(),
            "stop": stop.isoformat(),
            "stop_epoch": stop.timestamp(),
            "capacityAh": q,
            "valid": True,
            "calendar_age_weeks": age,
        })
    rows.sort(key=lambda r: (r["stop_epoch"], r["source_rpt_index"]))
    if len(rows) < 2 or any(b["stop_epoch"] <= a["stop_epoch"] for a,b in zip(rows,rows[1:])):
        raise ValueError("need at least two valid RPTs with strictly increasing stop times")
    event = next((r for r in rows if r["capacityAh"] <= 0.20), None)
    return {
        "cell_id": cid, "group_id": str(payload["group_id"]), "role": role,
        "nominal_capacity_ah": nominal, "baseline_stop": baseline_stop.isoformat(),
        "records": rows,
        "source_observed_event_stop_epoch": event["stop_epoch"] if event else None,
        "source_observed_event_age_weeks": event["calendar_age_weeks"] if event else None,
        "event_observed": event is not None,
    }


def load_reviewed_cell(path, expected_role):
    with open(path, "r", encoding="utf-8") as f:
        return normalize_cell(json.load(f), expected_role)


def build_origins(cell, delay_days=0, sparse=False):
    """Common source-RPT origins; visibility is by arrival time, labels stay dense."""
    rows = cell["records"]
    event_time = cell["source_observed_event_stop_epoch"]
    if event_time is None:
        return []
    eligible = [i for i,r in enumerate(rows) if r["stop_epoch"] < event_time]
    if len(eligible) < 2:
        return []
    anchor = rows[eligible[1]]["stop_epoch"]
    lag = delay_days * 86400.0
    visible_indices = set(eligible)
    if sparse:
        visible_indices = set(i for i in eligible if i <= eligible[1] or (rows[i]["source_rpt_index"]-rows[eligible[1]]["source_rpt_index"]) % 2 == 0)
    out = []
    for origin in rows:
        t = origin["stop_epoch"]
        if t < anchor + 7*86400.0 or t >= event_time:
            continue
        visible = [dict(r,arrival_epoch=r["stop_epoch"]+lag) for i,r in enumerate(rows)
                   if i in visible_indices and r["stop_epoch"] + lag <= t]
        # No future values; the event endpoint is a fixed dense source label.
        visible = [r for r in visible if r["stop_epoch"] < event_time]
        if len(visible) < 2:
            continue
        out.append({
            "origin_stop_epoch": t,
            "origin_age_weeks": origin["calendar_age_weeks"],
            "anchor_age_weeks": next(r["calendar_age_weeks"] for r in rows if r["stop_epoch"]==anchor),
            "event_rul_from_anchor": (event_time-anchor)/604800.0,
            "health_visible": True,
            "event_alert_visible": False,
            "visible_records": visible,
            "target_rul_weeks": (event_time-t)/604800.0,
            "cell_id": cell["cell_id"], "group_id": cell["group_id"],
            "role": cell["role"], "nominal_capacity_ah": cell["nominal_capacity_ah"],
            "arm": "delayed7d" if delay_days else ("sparse2rpt" if sparse else "raw"),
        })
    return out

