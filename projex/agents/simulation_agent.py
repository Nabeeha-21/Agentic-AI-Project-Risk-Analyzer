"""Simulation Agent - runs standard what-if scenarios automatically (the dashboard's What-If Simulator runs custom ones)."""
from __future__ import annotations
from ..graph import build_graph
from ..models import Context
from ..whatif import describe, monte_carlo, simulate
from .base import Agent


class SimulationAgent(Agent):
    name = "Simulation Agent"

    def run(self, ctx: Context, llm=None) -> Context:
        df = ctx.tasks
        open_df = df[~df["is_done"]]
        scenarios: list[tuple[str, list[dict]]] = []
        if ctx.risks:
            t = ctx.risks[0].task_id
            scenarios.append((f"Top-risk task {t} slips 5 more days", [{"type": "delay", "task_id": t, "days": 5}]))
            scenarios.append((f"Add one engineer to {t}", [{"type": "add_resource", "task_id": t, "count": 1}]))
        if len(open_df):
            busiest = open_df.groupby("owner")["owner_load"].first().sort_values(ascending=False).index[0]
            tasks = open_df[(open_df["owner"] == busiest) & (open_df["in_progress"] | (open_df["owner_load"] > 0))]["task_id"].tolist()[:4]
            scenarios.append((f"{busiest} is unavailable for 5 days", [{"type": "delay", "task_id": x, "days": 5} for x in tasks]))
            ip = open_df[open_df["in_progress"]]["task_id"].tolist()
            scenarios.append(("Scope creep: +20% work on every in-progress task", [{"type": "scope_creep", "task_id": x, "pct": 20} for x in ip]))
        base = monte_carlo(df, ctx.graph, ctx.as_of, n=600)
        out = []
        for title, sc in scenarios:
            if not sc:
                continue
            sim = simulate(df, ctx.as_of, sc)
            mc = monte_carlo(sim["tasks_after"], build_graph(sim["tasks_after"]), ctx.as_of, n=600)
            out.append({"title": title, "changes": [describe(a) for a in sc], "scenario": sc,
                        "tasks_affected": len(sim["changed_tasks"]), "project_shift_days": sim["project_shift_days"],
                        "p80_shift_days": round(mc["p80_offset"] - base["p80_offset"], 1),
                        "on_time_before": base["on_time_prob"], "on_time_after": mc["on_time_prob"]})
        ctx.scenarios = out
        if out:
            w = min(out, key=lambda x: x["on_time_after"])
            ctx.log(self.name, f"Ran {len(out)} standard what-if scenarios. Worst case: '{w['title']}' → chance of meeting the deadline "
                               f"{w['on_time_before'] * 100:.0f}% → {w['on_time_after'] * 100:.0f}%.")
        else:
            ctx.log(self.name, "Nothing to simulate.")
        return ctx
