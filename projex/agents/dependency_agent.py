"""Dependency Agent - dependency violations, cascading delays, bottlenecks and circular dependencies."""
from __future__ import annotations
from .. import config
from ..graph import downstream_tasks
from ..models import Context
from .base import Agent, new_risk


class DependencyAgent(Agent):
    name = "Dependency Agent"

    def run(self, ctx: Context, llm=None) -> Context:
        df, G, sched = ctx.tasks, ctx.graph, ctx.schedule
        before = len(ctx.risks)
        open_df = df[~df["is_done"]]
        for _, r in open_df.iterrows():
            tid = r["task_id"]
            incomplete = [d for d in r["deps"] if not df.loc[d, "is_done"]]
            slip = sched.slip.get(tid, 0.0)
            if r["progress"] > 0 and incomplete:
                new_risk(ctx, r, "Dependency", "dependency_violation", "Work started before prerequisites finished",
                         f"{tid} is in progress but depends on unfinished task(s): {', '.join(incomplete)}.",
                         0.55 + 0.1 * len(incomplete), {"incomplete_deps": incomplete})
            if slip >= 2 and r["days_overdue"] == 0 and r["progress_gap"] < config.BEHIND_PACE_POINTS and incomplete:
                driver = max(incomplete, key=lambda d: sched.finish.get(d, 0))
                new_risk(ctx, r, "Dependency", "projected_late", "Projected to finish late because of upstream delays",
                         f"{tid} cannot finish before {driver} (projected {sched.finish[driver]:.0f} day(s) from now), "
                         f"so it is projected to be {slip:.0f} day(s) late.", 0.4 + 0.04 * slip,
                         {"projected_slip_days": round(slip, 1), "driver": driver})
        flagged = {r.task_id for r in ctx.risks}
        for _, r in open_df.iterrows():
            ds = downstream_tasks(G, r["task_id"])
            if len(ds) >= config.BOTTLENECK_DOWNSTREAM and r["task_id"] not in flagged and (r["progress_gap"] >= 10 or sched.slip.get(r["task_id"], 0) > 0):
                new_risk(ctx, r, "Dependency", "bottleneck", f"Bottleneck: {len(ds)} tasks depend on this one",
                         f"{r['task_id']} is slipping and blocks {len(ds)} downstream tasks.", 0.35 + 0.03 * len(ds), {"downstream": ds})
        for cyc in ctx.summary.get("cycles", []):
            new_risk(ctx, df.loc[cyc[0]], "Dependency", "circular_dependency", "Circular dependency",
                     "Tasks depend on each other in a loop: " + " -> ".join(cyc + [cyc[0]]), 0.95, {"cycle": cyc})
        ctx.log(self.name, f"Found {len(ctx.risks) - before} dependency risks (violations, cascades, bottlenecks, cycles).")
        return ctx
