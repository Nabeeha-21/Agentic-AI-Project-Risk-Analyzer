"""Markdown risk report (what the 'Risk Report' output box in the architecture diagram produces)."""
from __future__ import annotations
from .models import Context


def build_markdown_report(ctx: Context) -> str:
    s, mc = ctx.summary, ctx.monte_carlo
    L = [f"# PROJEX Risk Report - {ctx.project_name}", f"*Analysis date: {ctx.as_of}*", ""]
    h = ctx.health
    L += ["## 1. Project health",
          f"- **Project Health Score: {h['score']} / 100 ({h['label']})** - " + ", ".join(f"{c['name']} {c['score']:.0f}" for c in h["components"]),
          f"- Tasks: {s['tasks']} ({s['done']} done, {s['in_progress']} in progress, {s['not_started']} not started)",
          f"- Overall progress: {s['overall_progress']}% (expected {s['expected_progress']}%)",
          f"- Deadline: {s['deadline']} | Projected finish: {s['projected_finish']} ({s['deadline_slip_days']:+} days)",
          f"- Probability of meeting the deadline (Monte-Carlo): {mc.get('on_time_prob', 0) * 100:.0f}%  "
          f"(P50 {mc.get('p50')}, P80 {mc.get('p80')}, P90 {mc.get('p90')})",
          f"- Critical path: {' → '.join(s['critical_path'])}", ""]
    if ctx.warnings:
        L += ["### Data-quality warnings"] + [f"- {w}" for w in ctx.warnings] + [""]
    L += ["## 2. Ranked risks", "| ID | Level | Score | Task | Category | Risk | P | Impact |", "|---|---|---|---|---|---|---|---|"]
    for r in ctx.risks:
        L.append(f"| {r.risk_id} | {r.level} | {r.score} | {r.task_id} {r.task_name} | {r.category} | {r.title} | {r.probability:.2f} | {r.impact:.2f} |")
    L += ["", "## 3. Root causes and evidence"]
    for r in ctx.risks[:8]:
        L += [f"### {r.risk_id} - {r.title} ({r.task_id}, {r.level})", f"**Root cause:** {r.root_cause}", ""]
        if r.contributing_factors:
            L += ["**Contributing factors:** " + "; ".join(r.contributing_factors), ""]
        L += ["**Evidence:**"] + [f"- {e}" for e in r.evidence_lines]
        if r.impact_text:
            L += ["", f"**Impact:** {r.impact_text}"]
        L += [""]
    if ctx.scenarios:
        L += ["## 4. What-if scenarios"] + [
            f"- {w['title']}: chance of meeting the deadline {w['on_time_before'] * 100:.0f}% → {w['on_time_after'] * 100:.0f}%, "
            f"{w['tasks_affected']} tasks affected" for w in ctx.scenarios] + [""]
    L += ["## 5. Recommended mitigations (ranked by simulated benefit per effort)"]
    for i, a in enumerate(ctx.actions, 1):
        L += [f"{i}. **{a.title}** (effort {a.effort}/3) - {a.description}", f"   - {a.rationale}"]
    if ctx.insights:
        L += ["", "## 6. Insights"] + [f"- {i['text']}" for i in ctx.insights]
    ch = ctx.changes
    if ch and not ch.get("first_run"):
        L += ["", "## 7. Changes since the previous analysis",
              f"- New: {', '.join(ch['new']) or '-'}", f"- Resolved: {', '.join(ch['resolved']) or '-'}",
              f"- Escalated: {', '.join(ch['escalated']) or '-'}", f"- Improved: {', '.join(ch['improved']) or '-'}"]
    return "\n".join(L)
