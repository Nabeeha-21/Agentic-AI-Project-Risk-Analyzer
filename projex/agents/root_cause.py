"""Root Cause & Evidence Agent - explains WHY each risk exists, with the supporting facts.

Evidence lines are always computed from the data (never by the LLM). The LLM, when available, only writes the
narrative from those lines, so every claim in the explanation can be traced back to a data point.
"""
from __future__ import annotations
from .. import config
from ..graph import downstream_tasks
from ..models import Context, Risk
from .base import Agent

SYSTEM = ("You are the Root Cause agent of a project risk analyzer. Using ONLY the evidence lines provided, explain the most "
          "likely root cause of the risk. Do not invent facts or numbers. Return JSON with keys: "
          "root_cause (1-2 sentences), contributing_factors (list of up to 3 short strings).")


def gather_evidence(ctx: Context, r: Risk) -> list[str]:
    df, G, s = ctx.tasks, ctx.graph, ctx.schedule
    row = df.loc[r.task_id]
    lines = [f"{r.task_id} '{row['name']}' (owner {row['owner']}, priority {row['priority']}) is {row['progress']:.0f}% complete; "
             f"{row['expected_progress']:.0f}% expected by today (gap {row['progress_gap']:.0f} points)."]
    if row["days_overdue"] > 0:
        lines.append(f"It was due {row['due_date'].date()} and is {int(row['days_overdue'])} day(s) overdue.")
    else:
        lines.append(f"It is due {row['due_date'].date()} ({int(row['days_to_due'])} day(s) left); projected slip {s.slip.get(r.task_id, 0):+.0f} day(s).")
    incomplete = [d for d in row["deps"] if not df.loc[d, "is_done"]]
    if incomplete:
        lines.append("Waiting on unfinished prerequisites: " + ", ".join(
            f"{d} ({df.loc[d, 'progress']:.0f}% done, owner {df.loc[d, 'owner']}, {int(df.loc[d, 'days_overdue'])}d overdue)" for d in incomplete))
    if row["owner_load"] > row["owner_capacity"]:
        others = df[(df["owner"] == row["owner"]) & ~df["is_done"] & (df["task_id"] != r.task_id)]["task_id"].tolist()
        lines.append(f"Owner {row['owner']} has {int(row['owner_load'])} concurrent tasks (capacity {row['owner_capacity']:.0f}); other open tasks: {', '.join(others)}.")
    if row["open_issues"]:
        ids = df.attrs.get("open_issue_ids", {}).get(r.task_id, [])
        lines.append(f"{int(row['open_issues'])} open issue(s), {int(row['open_critical'])} critical/high ({', '.join(ids)}).")
    if row["has_git_data"]:
        lines.append(f"Git: {int(row['commits_14d'])} commit(s) in the last 14 days; last commit {int(row['days_since_commit'])} day(s) ago.")
    ds = downstream_tasks(G, r.task_id)
    if ds:
        lines.append(f"{len(ds)} downstream task(s) depend on it: {', '.join(ds[:8])}{'...' if len(ds) > 8 else ''}.")
    if r.task_id in s.critical_path:
        lines.append("It lies on the project's critical path, so any delay moves the final delivery date.")
    drivers = ctx.task_drivers.get(r.task_id, [])
    if drivers:
        lines.append("Statistical model drivers of lateness: " + ", ".join(drivers) + f" (late probability {ctx.task_late_prob.get(r.task_id, 0) * 100:.0f}%).")
    return lines


def rule_based_cause(ctx: Context, r: Risk) -> tuple[str, list[str]]:
    df = ctx.tasks
    row = df.loc[r.task_id]
    factors: list[str] = []
    incomplete = [d for d in row["deps"] if not df.loc[d, "is_done"]]
    overloaded = row["owner_load"] > row["owner_capacity"]
    if overloaded:
        factors.append(f"{row['owner']} is juggling {int(row['owner_load'])} tasks")
    if row["has_git_data"] and row["days_since_commit"] >= config.STALL_DAYS:
        factors.append(f"no commits for {int(row['days_since_commit'])} days")
    if row["open_critical"] >= 1:
        factors.append(f"{int(row['open_critical'])} open critical/high issues")
    if incomplete:
        factors.append("unfinished prerequisites (" + ", ".join(incomplete) + ")")
    if row["progress_gap"] >= config.BEHIND_PACE_POINTS:
        factors.append(f"progress {row['progress_gap']:.0f} points behind plan")

    cause = {
        "overdue": "The task has run past its due date; most likely the work was under-estimated or the owner lacked capacity",
        "behind_pace": "Delivery is slower than planned",
        "dependency_violation": "Work was started before its prerequisites were complete, so rework and blocking are likely",
        "projected_late": f"An upstream delay ({r.evidence.get('driver')}) propagates through the dependency chain",
        "critical_issues": "Unresolved high-severity defects are consuming effort and blocking completion",
        "issue_backlog": "Defects are accumulating faster than they are being closed",
        "stalled": "Development activity has stopped, which usually means the owner is blocked or has been pulled onto other work",
        "owner_overload": f"{r.owner} has more concurrent work than they can handle, slowing every task they own",
        "key_person": f"The critical path depends heavily on {r.owner}; any absence or delay stops the whole chain",
        "late_start": "The task has not started on time, which usually means it is blocked, unstaffed or deprioritised",
        "insufficient_time": "The remaining effort is larger than the time left, so the due date cannot be met at the current pace",
        "unassigned": "Nobody owns this task, so nobody is driving it",
        "bottleneck": "Many tasks wait on this one, so a small slip here is amplified downstream",
        "circular_dependency": "Tasks depend on each other in a loop, so none of them can ever start cleanly",
    }.get(r.rule, "Multiple warning signals were detected")
    if overloaded and r.rule not in ("owner_overload",):
        cause += f"; the owner's overload ({int(row['owner_load'])} concurrent tasks) is a likely amplifier"
    return cause + ".", factors[:3]


class RootCauseAgent(Agent):
    name = "Root Cause & Evidence Agent"

    def run(self, ctx: Context, llm=None) -> Context:
        used = 0
        for i, r in enumerate(ctx.risks):
            r.evidence_lines = gather_evidence(ctx, r)
            r.root_cause, r.contributing_factors = rule_based_cause(ctx, r)
            r.explained_by = "rules"
            if llm is not None and llm.available and i < config.LLM_MAX_RISKS:
                prompt = (f"Risk: {r.title} ({r.category}) on task {r.task_id} '{r.task_name}'.\n"
                          "Evidence:\n- " + "\n- ".join(r.evidence_lines))
                out = llm.complete_json(SYSTEM, prompt)
                if out and out.get("root_cause"):
                    r.root_cause = str(out["root_cause"]).strip()
                    r.contributing_factors = [str(x) for x in out.get("contributing_factors", [])][:3] or r.contributing_factors
                    r.explained_by = "llm"
                    used += 1
        ctx.llm_used = ctx.llm_used or used > 0
        ctx.log(self.name, f"Gathered evidence for {len(ctx.risks)} risks; {used} explained by the LLM, "
                           f"{len(ctx.risks) - used} by rule-based reasoning.")
        return ctx
