"""Resource Agent - overloaded people, key-person dependency and unassigned work."""
from __future__ import annotations
import pandas as pd

from ..graph import downstream_tasks
from ..models import Context
from .base import Agent, new_risk


class ResourceAgent(Agent):
    name = "Resource Agent"

    def run(self, ctx: Context, llm=None) -> Context:
        df, G = ctx.tasks, ctx.graph
        before = len(ctx.risks)
        open_df = df[~df["is_done"]]
        horizon = pd.Timestamp(ctx.as_of) + pd.Timedelta(days=7)
        cp = set(ctx.schedule.critical_path)

        for owner, g in open_df.groupby("owner"):
            load, cap = int(g["owner_load"].iloc[0]), float(g["owner_capacity"].iloc[0])
            if owner == "Unassigned":
                for _, r in g.iterrows():
                    new_risk(ctx, r, "Resource", "unassigned", "Task has no owner",
                             f"{r['task_id']} is not assigned to anyone.", 0.5, {})
                continue
            if load > cap:
                mine = g[g["in_progress"] | (g["start_date"] <= horizon)]
                anchor = mine.assign(_d=[len(downstream_tasks(G, t)) for t in mine["task_id"]]).sort_values(
                    ["priority_weight", "_d"], ascending=False).iloc[0]
                new_risk(ctx, anchor, "Resource", "owner_overload", f"{owner} is overloaded",
                         f"{owner} has {load} concurrent tasks (comfortable capacity is {cap:.0f}).",
                         0.35 + 0.12 * (load - cap),
                         {"owner": owner, "load": load, "capacity": cap, "tasks": mine["task_id"].tolist()})
            on_path = [t for t in g["task_id"] if t in cp]
            if len(on_path) >= 3:
                anchor = df.loc[on_path[0]]
                new_risk(ctx, anchor, "Resource", "key_person", f"Key-person dependency on {owner}",
                         f"{owner} owns {len(on_path)} tasks on the critical path ({', '.join(on_path)}); their absence would stop the project.",
                         0.35 + 0.08 * len(on_path), {"owner": owner, "critical_path_tasks": on_path})
        ctx.log(self.name, f"Found {len(ctx.risks) - before} resource risks (overload, key-person, unassigned work).")
        return ctx
