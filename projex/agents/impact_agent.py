"""Impact Agent - quantifies what happens to the PROJECT if each risk materialises (the task slips a further 5 days)."""
from __future__ import annotations
from ..graph import build_graph, downstream_tasks
from ..models import Context
from ..whatif import monte_carlo, simulate
from .base import Agent

DELAY = 5
MAX_TASKS = 12


class ImpactAgent(Agent):
    name = "Impact Agent"

    def run(self, ctx: Context, llm=None) -> Context:
        df, G = ctx.tasks, ctx.graph
        base = monte_carlo(df, G, ctx.as_of, n=600)
        cache: dict[str, dict] = {}
        for r in ctx.risks:
            if r.task_id not in cache and len(cache) >= MAX_TASKS:
                continue
            if r.task_id not in cache:
                sim = simulate(df, ctx.as_of, [{"type": "delay", "task_id": r.task_id, "days": DELAY}])
                mc = monte_carlo(sim["tasks_after"], build_graph(sim["tasks_after"]), ctx.as_of, n=600)
                cache[r.task_id] = {
                    "delay_days": DELAY, "project_shift_days": sim["project_shift_days"],
                    "tasks_delayed": len(sim["changed_tasks"]), "downstream": len(downstream_tasks(G, r.task_id)),
                    "on_time_before": base["on_time_prob"], "on_time_after": mc["on_time_prob"],
                    "new_finish": str(sim["scenario"].project_finish),
                    "p80_shift_days": round(mc["p80_offset"] - base["p80_offset"], 1),
                }
            r.impact_info = cache[r.task_id]
            i = r.impact_info
            r.impact_text = (f"If {r.task_id} slips a further {DELAY} days: {i['tasks_delayed']} task(s) are pushed back, the 80%-confidence finish "
                             f"moves {i['p80_shift_days']:+.1f} day(s) and the chance of meeting the deadline goes "
                             f"{i['on_time_before'] * 100:.0f}% → {i['on_time_after'] * 100:.0f}%.")
        ctx.log(self.name, f"Quantified the project-level impact of {len(cache)} risky tasks (+{DELAY} day slip, Monte-Carlo).")
        return ctx
