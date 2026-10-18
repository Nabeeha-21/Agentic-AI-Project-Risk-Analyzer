"""Turns an analysis Context into plain JSON for the React dashboard."""
from __future__ import annotations
from datetime import date, datetime, timedelta
import numpy as np
import pandas as pd

from .graph import downstream_tasks
from .models import Context

LEVEL_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


def _j(v):
    """Make any value JSON-safe."""
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if (v != v) else float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return v.isoformat()[:10]
    if isinstance(v, dict):
        return {str(k): _j(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_j(x) for x in v]
    if isinstance(v, np.ndarray):
        return [_j(x) for x in v.tolist()]
    return v


def mc_to_dict(mc: dict, bins: int = 30) -> dict:
    samples = np.asarray(mc["samples"])
    counts, edges = np.histogram(samples, bins=bins)
    return {"histogram": [{"x0": float(edges[i]), "x1": float(edges[i + 1]), "count": int(counts[i])} for i in range(len(counts))],
            "deadline_offset": mc["deadline_offset"], "on_time_prob": mc["on_time_prob"],
            "p50": str(mc["p50"]), "p80": str(mc["p80"]), "p90": str(mc["p90"]),
            "p50_offset": mc["p50_offset"], "p80_offset": mc["p80_offset"], "p90_offset": mc["p90_offset"], "runs": int(len(samples))}


def context_to_dict(ctx: Context, history_df: pd.DataFrame | None = None) -> dict:
    df, G, sched = ctx.tasks, ctx.graph, ctx.schedule
    worst, ids = {}, {}
    for r in ctx.risks:
        ids.setdefault(r.task_id, []).append(r.risk_id)
        if r.task_id not in worst or LEVEL_ORDER[r.level] < LEVEL_ORDER[worst[r.task_id]]:
            worst[r.task_id] = r.level
    cp = list(sched.critical_path)
    ts = pd.Timestamp(ctx.as_of)

    tasks = []
    for t, r in df.iterrows():
        tasks.append({
            "id": t, "name": r["name"], "owner": r["owner"], "status": r["status"], "progress": r["progress"],
            "expected_progress": round(r["expected_progress"], 1), "start": r["start_date"], "due": r["due_date"],
            "projected_finish": (ts + timedelta(days=float(sched.finish[t]))) if not r["is_done"] else None,
            "projected_start": (ts + timedelta(days=float(sched.start[t]))) if not r["is_done"] else None,
            "slip": round(sched.slip.get(t, 0.0), 1), "late_prob": ctx.task_late_prob.get(t, 0.0),
            "level": worst.get(t), "risk_ids": ids.get(t, []), "deps": list(r["deps"]),
            "downstream": len(downstream_tasks(G, t)), "on_critical_path": t in cp, "is_done": bool(r["is_done"]),
            "priority": r["priority"], "component": r["component"], "open_issues": int(r["open_issues"]),
            "open_critical": int(r["open_critical"]), "est_days": r["est_days"], "remaining_days": round(r["remaining_days"], 1),
            "drivers": ctx.task_drivers.get(t, []),
        })

    workload = []
    for owner, g in df.groupby("owner"):
        op = g[~g["is_done"]]
        workload.append({
            "owner": owner, "role": g["owner_role"].iloc[0], "capacity": float(g["owner_capacity"].iloc[0]),
            "load": int(g["owner_load"].iloc[0]), "remaining_days": round(float(op["remaining_days"].sum()), 1),
            "overloaded": bool(g["owner_load"].iloc[0] > g["owner_capacity"].iloc[0]),
            "tasks": [{"id": t, "name": n, "status": s, "progress": p, "on_critical_path": t in cp, "level": worst.get(t)}
                      for t, n, s, p in zip(op["task_id"], op["name"], op["status"], op["progress"])],
        })
    workload.sort(key=lambda w: (w["load"] - w["capacity"]), reverse=True)

    risks = [{
        "id": r.risk_id, "task_id": r.task_id, "task_name": r.task_name, "owner": r.owner, "category": r.category, "rule": r.rule,
        "title": r.title, "description": r.description, "probability": round(r.probability, 3), "impact": round(r.impact, 3),
        "score": r.score, "level": r.level, "base_prob": round(r.base_prob, 3), "ml_prob": round(r.ml_prob, 3),
        "root_cause": r.root_cause, "contributing_factors": r.contributing_factors, "evidence": r.evidence_lines,
        "explained_by": r.explained_by, "impact_info": _j(r.impact_info), "impact_text": r.impact_text,
    } for r in ctx.risks]

    actions = [{
        "id": a.action_id, "title": a.title, "description": a.description, "effort": a.effort, "scenario": _j(a.scenario),
        "risks": a.risk_keys, "target_task": a.target_task, "priority_score": a.priority_score, "rationale": a.rationale,
        "on_time_before": a.on_time_before, "on_time_after": a.on_time_after, "p80_days_saved": a.p80_days_saved,
        "simulated": bool(a.scenario),
    } for a in ctx.actions]

    s = ctx.summary
    hist = []
    if history_df is not None and len(history_df):
        hist = _j(history_df.drop(columns=["fingerprint"], errors="ignore").to_dict(orient="records"))

    return _j({
        "project": {"name": ctx.project_name, "as_of": ctx.as_of, "deadline": s["deadline"], "projected_finish": s["projected_finish"],
                    "deadline_slip_days": s["deadline_slip_days"], "overall_progress": s["overall_progress"],
                    "expected_progress": s["expected_progress"], "tasks": s["tasks"], "done": s["done"],
                    "in_progress": s["in_progress"], "not_started": s["not_started"], "critical_path": cp},
        "health": ctx.health, "tasks": tasks, "edges": [{"from": a, "to": b} for a, b in G.edges()],
        "critical_edges": [{"from": a, "to": b} for a, b in zip(cp, cp[1:])],
        "risks": risks, "workload": workload, "actions": actions, "scenarios": ctx.scenarios, "insights": ctx.insights,
        "monte_carlo": mc_to_dict(ctx.monte_carlo), "changes": ctx.changes, "trend": ctx.trend, "history": hist,
        "trace": ctx.trace, "timings": ctx.timings, "warnings": ctx.warnings, "model": ctx.model_info, "llm_used": ctx.llm_used,
    })
