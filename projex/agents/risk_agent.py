"""Risk Agent - schedule / technical / quality risk detection (rule-based; probability is added by the Intelligence Layer)."""
from __future__ import annotations
from .. import config
from ..models import Context
from .base import Agent, new_risk


class RiskAgent(Agent):
    name = "Risk Agent"

    def run(self, ctx: Context, llm=None) -> Context:
        df = ctx.tasks
        before = len(ctx.risks)
        issue_ids = df.attrs.get("open_issue_ids", {})
        for _, r in df[~df["is_done"]].iterrows():
            tid = r["task_id"]
            days_since_start = (ctx.as_of - r["start_date"].date()).days
            overdue = r["days_overdue"] > 0
            if overdue:
                new_risk(ctx, r, "Schedule", "overdue", "Task is past its due date",
                         f"{tid} was due {int(r['days_overdue'])} day(s) ago and is only {r['progress']:.0f}% complete.",
                         0.6 + 0.04 * r["days_overdue"] + 0.15 * (1 - r["progress"] / 100),
                         {"days_overdue": int(r["days_overdue"]), "progress": r["progress"]})
            elif r["in_progress"] and r["progress_gap"] >= config.BEHIND_PACE_POINTS:
                new_risk(ctx, r, "Schedule", "behind_pace", "Progress is behind the planned pace",
                         f"{tid} is {r['progress']:.0f}% complete but should be about {r['expected_progress']:.0f}% by now.",
                         0.35 + r["progress_gap"] / 100,
                         {"progress": r["progress"], "expected": round(r["expected_progress"], 1), "gap": round(r["progress_gap"], 1)})
            elif (not r["in_progress"]) and days_since_start >= 3:
                new_risk(ctx, r, "Schedule", "late_start", "Task has not started although its start date passed",
                         f"{tid} was planned to start {days_since_start} days ago but has no progress.",
                         0.4 + 0.04 * days_since_start, {"days_since_planned_start": days_since_start})
            if (not overdue) and r["remaining_days"] > r["days_to_due"] + 1:
                new_risk(ctx, r, "Schedule", "insufficient_time", "Remaining work exceeds the time left",
                         f"{tid} needs about {r['remaining_days']:.1f} more working day(s) but only {int(r['days_to_due'])} remain before the due date.",
                         0.5 + 0.05 * (r["remaining_days"] - r["days_to_due"]),
                         {"remaining_days": round(r["remaining_days"], 1), "days_left": int(r["days_to_due"])})
            if r["open_critical"] >= config.ISSUE_HIGH_THRESHOLD:
                new_risk(ctx, r, "Technical", "critical_issues", "Open critical/high-severity issues",
                         f"{tid} has {int(r['open_critical'])} open critical/high issues ({int(r['open_issues'])} open in total).",
                         0.4 + 0.12 * r["open_critical"],
                         {"open_critical": int(r["open_critical"]), "open_issues": int(r["open_issues"]), "issue_ids": issue_ids.get(tid, [])})
            elif r["open_issues"] >= config.ISSUE_TOTAL_THRESHOLD:
                new_risk(ctx, r, "Quality", "issue_backlog", "Large backlog of open issues",
                         f"{tid} has {int(r['open_issues'])} open issues.", 0.3 + 0.05 * r["open_issues"],
                         {"open_issues": int(r["open_issues"])})
            if r["in_progress"] and r["has_git_data"] and r["days_since_commit"] >= config.STALL_DAYS:
                new_risk(ctx, r, "Technical", "stalled", "Work appears stalled (no recent commits)",
                         f"No commits on {tid} for {int(r['days_since_commit'])} days although it is in progress.",
                         0.45 + 0.02 * r["days_since_commit"],
                         {"days_since_commit": int(r["days_since_commit"]), "commits_14d": int(r["commits_14d"])})
        ctx.log(self.name, f"Found {len(ctx.risks) - before} schedule/technical/quality risks.")
        return ctx
