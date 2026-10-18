"""Trends & Insights - plain-English observations generated from the analysis (all numbers come from the data)."""
from __future__ import annotations
from .graph import downstream_tasks
from .models import Context


def build_insights(ctx: Context) -> list[dict]:
    df, s, mc, out = ctx.tasks, ctx.summary, ctx.monte_carlo, []
    add = lambda level, text: out.append({"level": level, "text": text})

    p = mc["on_time_prob"] * 100
    lvl = "critical" if p < 30 else "warning" if p < 70 else "good"
    add(lvl, f"There is a {p:.0f}% chance of meeting the {s['deadline']} deadline (80% confidence finish: {mc['p80']}).")
    if ctx.risks:
        r = ctx.risks[0]
        add("critical" if r.level in ("Critical", "High") else "warning",
            f"Highest-priority risk: {r.title.lower()} on {r.task_id} '{r.task_name}' (score {r.score}, {r.level}).")
    open_df = df[~df["is_done"]]
    if len(open_df):
        load = open_df.groupby("owner").agg(load=("owner_load", "first"), cap=("owner_capacity", "first"))
        worst = (load["load"] - load["cap"]).sort_values(ascending=False)
        if len(worst) and worst.iloc[0] > 0:
            o = worst.index[0]
            cp_n = sum(t in set(ctx.schedule.critical_path) for t in open_df[open_df["owner"] == o]["task_id"])
            add("warning", f"{o} is carrying {int(load.loc[o, 'load'])} concurrent tasks (capacity {load.loc[o, 'cap']:.0f})"
                           + (f", including {cp_n} on the critical path." if cp_n else "."))
        biggest = max(open_df["task_id"], key=lambda t: len(downstream_tasks(ctx.graph, t)))
        n = len(downstream_tasks(ctx.graph, biggest))
        if n >= 3:
            add("info", f"{biggest} '{df.loc[biggest, 'name']}' is the biggest bottleneck: {n} tasks depend on it (progress {df.loc[biggest, 'progress']:.0f}%).")
    bugs = df[df["open_critical"] >= 2]
    for t in bugs["task_id"][:2]:
        add("warning", f"{t} has {int(df.loc[t, 'open_critical'])} open critical/high issues.")
    ontrack = int(((~df["is_done"]) & (df["progress_gap"] < 10) & (df["days_overdue"] == 0)).sum())
    if ontrack:
        add("good", f"{ontrack} open task(s) are on track (less than 10 points behind plan).")
    tr = ctx.trend
    if tr and tr.get("runs", 0) >= 2:
        add("good" if tr["label"] == "Improving" else "warning" if tr["label"] == "Declining" else "info",
            f"Health trend over the last {tr['runs']} analyses: {tr['label'].lower()} ({tr['slope']:+.1f} points per run; next run forecast {tr['forecast']:.0f}).")
    return out
