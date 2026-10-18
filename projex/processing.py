"""Processing Layer (data preparation): cleaning + validation happen in data_collection.prepare();
this step does FEATURE EXTRACTION - dependency graph, baseline schedule, critical path, project summary."""
from __future__ import annotations
from .graph import build_graph, compute_schedule, find_cycles
from .models import Context


class ProcessingLayer:
    name = "Processing Layer"

    def run(self, ctx: Context, llm=None) -> Context:
        df = ctx.tasks
        G = build_graph(df)
        ctx.graph = G
        cycles = find_cycles(G)
        if cycles:
            ctx.warnings.append("Circular dependencies found: " + "; ".join(" -> ".join(c + [c[0]]) for c in cycles))
        ctx.schedule = compute_schedule(df, G, ctx.as_of)
        s = ctx.schedule
        w = df["est_days"]
        overall = float((df["progress"] * w).sum() / w.sum())
        expected = float((df["expected_progress"] * w).sum() / w.sum())
        ctx.summary = {
            "tasks": int(len(df)), "done": int(df["is_done"].sum()), "in_progress": int(df["in_progress"].sum()),
            "not_started": int((df["status"] == "Not started").sum()),
            "overall_progress": round(overall, 1), "expected_progress": round(expected, 1),
            "deadline": s.deadline, "projected_finish": s.project_finish,
            "deadline_slip_days": round(s.deadline_slip, 1), "critical_path": s.critical_path,
            "open_issues": int(df["open_issues"].sum()), "cycles": cycles,
        }
        ctx.log(self.name, f"Cleaned & validated {len(df)} tasks ({len(ctx.warnings)} warning(s)); extracted features: "
                           f"{G.number_of_edges()} dependency links, critical path of {len(s.critical_path)} tasks. "
                           f"Progress {overall:.0f}% vs {expected:.0f}% expected; projected finish {s.project_finish} vs deadline {s.deadline}.")
        return ctx
