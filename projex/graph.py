"""Dependency graph + schedule engine (critical path, Monte Carlo core).

Time is handled as float day-offsets from the `as_of` date (0 = today). A task that is done finishes at 0.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
import math
import networkx as nx
import numpy as np
import pandas as pd

from . import config


@dataclass
class ScheduleResult:
    start: dict = field(default_factory=dict)          # task_id -> offset (days)
    finish: dict = field(default_factory=dict)         # task_id -> offset (days)
    slip: dict = field(default_factory=dict)           # task_id -> days late vs due date (can be negative)
    project_finish_offset: float = 0.0
    project_finish: date = None
    deadline: date = None
    deadline_slip: float = 0.0
    critical_path: list = field(default_factory=list)


def build_graph(df: pd.DataFrame) -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_nodes_from(df["task_id"])
    for tid, deps in zip(df["task_id"], df["deps"]):
        for d in deps:
            G.add_edge(d, tid)           # d must finish before tid
    return G


def find_cycles(G: nx.DiGraph, limit: int = 5) -> list[list[str]]:
    cycles = []
    for c in nx.simple_cycles(G):
        cycles.append(c)
        if len(cycles) >= limit:
            break
    return cycles


def make_acyclic(G: nx.DiGraph) -> nx.DiGraph:
    H = G.copy()
    while True:
        try:
            cyc = nx.find_cycle(H)
        except nx.NetworkXNoCycle:
            return H
        H.remove_edge(*cyc[-1])


def downstream_tasks(G: nx.DiGraph, tid: str) -> list[str]:
    return sorted(nx.descendants(G, tid)) if tid in G else []


def effective_remaining(df: pd.DataFrame) -> np.ndarray:
    """Remaining work (days) after overload penalty, extra delay and added resources."""
    extra = df["extra_days"].values if "extra_days" in df else 0.0
    speed = df["speedup"].values if "speedup" in df else 1.0
    overload = 1.0 + config.OVERLOAD_PENALTY * np.maximum(0, df["owner_load"].values - df["owner_capacity"].values)
    rem = df["remaining_days"].values * overload / speed + np.where(df["is_done"].values, 0.0, extra)
    return np.where(df["is_done"].values, 0.0, rem)


def forward_pass(df: pd.DataFrame, G: nx.DiGraph, as_of: date, durations: np.ndarray) -> tuple[np.ndarray, np.ndarray, list]:
    """durations: (n_sims, n_tasks) in df row order. Returns (start, finish, order) with the same shape."""
    H = make_acyclic(G)
    idx = {t: i for i, t in enumerate(df["task_id"])}
    order = [t for t in nx.topological_sort(H) if t in idx]
    n_sims = durations.shape[0]
    ts = pd.Timestamp(as_of)
    plan_start = ((df["start_date"] - ts).dt.days).clip(lower=0).values.astype(float)
    in_prog = df["in_progress"].values
    done = df["is_done"].values
    start = np.zeros((n_sims, len(df)))
    finish = np.zeros((n_sims, len(df)))
    for t in order:
        i = idx[t]
        if done[i]:
            continue
        deps = [idx[d] for d in H.predecessors(t) if d in idx]
        dep_fin = np.max(finish[:, deps], axis=1) if deps else np.zeros(n_sims)
        if in_prog[i]:
            s = np.zeros(n_sims)
            f = np.maximum(s + durations[:, i], dep_fin)   # work already started; cannot end before prerequisites
        else:
            s = np.maximum(dep_fin, plan_start[i])
            f = s + durations[:, i]
        start[:, i], finish[:, i] = s, f
    return start, finish, order


def _to_date(as_of: date, offset: float) -> date:
    return as_of + timedelta(days=int(math.ceil(offset - 1e-9)))


def compute_schedule(df: pd.DataFrame, G: nx.DiGraph, as_of: date) -> ScheduleResult:
    dur = effective_remaining(df)[None, :]
    start, finish, order = forward_pass(df, G, as_of, dur)
    ids = list(df["task_id"])
    res = ScheduleResult()
    ts = pd.Timestamp(as_of)
    due_off = ((df["due_date"] - ts).dt.days).values.astype(float)
    for i, t in enumerate(ids):
        res.start[t] = float(start[0, i])
        res.finish[t] = float(finish[0, i])
        res.slip[t] = 0.0 if df["is_done"].iloc[i] else float(finish[0, i] - due_off[i])
    open_mask = ~df["is_done"].values
    res.project_finish_offset = float(finish[0].max()) if open_mask.any() else 0.0
    res.project_finish = _to_date(as_of, res.project_finish_offset)
    res.deadline = df["due_date"].max().date()
    res.deadline_slip = res.project_finish_offset - float((pd.Timestamp(res.deadline) - ts).days)
    # critical path = longest dependency chain: walk back from the last-finishing task along the prerequisite that finishes last
    if open_mask.any():
        H = make_acyclic(G)
        cur = ids[int(np.argmax(finish[0]))]
        path = [cur]
        while True:
            preds = [p for p in H.predecessors(cur) if not df.loc[p, "is_done"]]
            if not preds:
                break
            nxt = max(preds, key=lambda p: res.finish[p])     # the prerequisite that finishes last drives this task
            path.append(nxt)
            cur = nxt
        res.critical_path = list(reversed(path))
    return res
