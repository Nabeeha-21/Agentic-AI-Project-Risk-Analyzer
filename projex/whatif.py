"""What-if simulation + Monte-Carlo forecasting (used by the What-If, Mitigation and Prediction agents).

Scenario = list of actions, each a dict:
  {"type": "delay",        "task_id": "T07", "days": 5}          task takes N extra days
  {"type": "add_resource", "task_id": "T07", "count": 1}         extra people (diminishing returns)
  {"type": "reassign",     "task_id": "T12", "new_owner": "Anita"}
  {"type": "descope",      "task_id": "T25"}                     remove the remaining work
  {"type": "reduce_scope", "task_id": "T16", "pct": 30}          cut 30% of remaining work
  {"type": "scope_creep",  "task_id": "T16", "pct": 20}          add 20% more work
  {"type": "decouple",     "task_id": "T10", "dependency": "T07"}  remove a dependency link (e.g. work against a stub)
"""
from __future__ import annotations
from datetime import date
import numpy as np
import pandas as pd

from . import config
from .data_collection import compute_owner_load
from .graph import build_graph, compute_schedule, effective_remaining, forward_pass, _to_date

SCENARIO_TYPES = ["delay", "add_resource", "reassign", "descope", "reduce_scope", "scope_creep", "decouple"]


def describe(a: dict) -> str:
    t = a["type"]
    if t == "delay":
        return f"{a['task_id']} takes {a['days']} extra day(s)"
    if t == "add_resource":
        return f"Add {a.get('count', 1)} person(s) to {a['task_id']}"
    if t == "reassign":
        return f"Reassign {a['task_id']} to {a['new_owner']}"
    if t == "descope":
        return f"Descope {a['task_id']}"
    if t == "reduce_scope":
        return f"Cut {a['pct']}% of remaining work on {a['task_id']}"
    if t == "scope_creep":
        return f"Scope creep: +{a['pct']}% work on {a['task_id']}"
    if t == "decouple":
        return f"Decouple {a['task_id']} from {a['dependency']}"
    return str(a)


def apply_scenario(df: pd.DataFrame, as_of: date, scenario: list[dict]):
    d = df.copy()
    cap = d.groupby("owner")["owner_capacity"].first().to_dict()
    d["extra_days"] = 0.0
    d["speedup"] = 1.0
    d["deps"] = [list(x) for x in d["deps"]]
    for a in scenario:
        t, tid = a["type"], a.get("task_id")
        if tid not in d.index:
            raise ValueError(f"Unknown task in scenario: {tid}")
        if t == "delay":
            d.at[tid, "extra_days"] += float(a["days"])
        elif t == "add_resource":
            d.at[tid, "speedup"] *= 1.0 + config.RESOURCE_GAIN * int(a.get("count", 1))
        elif t == "reassign":
            d.at[tid, "owner"] = a["new_owner"]
        elif t == "descope":
            d.at[tid, "remaining_days"] = 0.0
        elif t == "reduce_scope":
            d.at[tid, "remaining_days"] *= max(0.0, 1 - float(a["pct"]) / 100.0)
        elif t == "scope_creep":
            d.at[tid, "remaining_days"] *= 1 + float(a["pct"]) / 100.0
        elif t == "decouple":
            d.at[tid, "deps"] = [x for x in d.at[tid, "deps"] if x != a["dependency"]]
        else:
            raise ValueError(f"Unknown scenario type: {t}")
    d["owner_capacity"] = d["owner"].map(cap).fillna(float(config.OWNER_CAPACITY))
    d["owner_load"] = d["owner"].map(compute_owner_load(d, as_of)).fillna(0).astype(int)
    return d, build_graph(d)


def simulate(df: pd.DataFrame, as_of: date, scenario: list[dict]) -> dict:
    base_G = build_graph(df)
    base = compute_schedule(df, base_G, as_of)
    d2, G2 = apply_scenario(df, as_of, scenario)
    new = compute_schedule(d2, G2, as_of)
    changed = []
    for t in df["task_id"]:
        shift = new.finish[t] - base.finish[t]
        if abs(shift) >= 0.5:
            changed.append({"task_id": t, "name": df.loc[t, "name"],
                            "before": _to_date(as_of, base.finish[t]), "after": _to_date(as_of, new.finish[t]),
                            "shift_days": round(shift, 1)})
    changed.sort(key=lambda x: -abs(x["shift_days"]))
    return {
        "baseline": base, "scenario": new,
        "project_shift_days": round(new.project_finish_offset - base.project_finish_offset, 1),
        "deadline_slip_before": round(base.deadline_slip, 1),
        "deadline_slip_after": round(new.deadline_slip, 1),
        "changed_tasks": changed,
        "scenario_text": [describe(a) for a in scenario],
        "tasks_after": d2,
    }


def monte_carlo(df: pd.DataFrame, G, as_of: date, n: int = 2000, seed: int = 7) -> dict:
    """Sample task durations from a triangular distribution (optimistic 0.85x, likely 1x, pessimistic 1.5x+)."""
    rng = np.random.default_rng(seed)
    base = effective_remaining(df)
    pess = 1.5 + 0.1 * np.minimum(df["open_critical"].values, 5)
    mult = rng.triangular(0.85, 1.0, pess, size=(n, len(df)))
    dur = base[None, :] * mult
    _, finish, _ = forward_pass(df, G, as_of, dur)
    proj = finish.max(axis=1)
    deadline_off = float((df["due_date"].max() - pd.Timestamp(as_of)).days)
    q = lambda p: float(np.percentile(proj, p))
    return {
        "samples": proj, "deadline_offset": deadline_off,
        "p50": _to_date(as_of, q(50)), "p80": _to_date(as_of, q(80)), "p90": _to_date(as_of, q(90)),
        "p50_offset": q(50), "p80_offset": q(80), "p90_offset": q(90),
        "on_time_prob": float((proj <= deadline_off + 1e-9).mean()),
    }
