#!/usr/bin/env python3
"""Produces the numbers for your 'Results and Discussion' slide.   python evaluate.py"""
from datetime import date

from projex.data_collection import ProjectData
from projex.orchestrator import AIOrchestrator
from projex.sample_data import PLANTED_RISKS, build_resources, build_sample
from projex.whatif import simulate

as_of = date.today()
t, i, g = build_sample(as_of)
ctx = AIOrchestrator(record=False, db_path=":memory:").run(ProjectData(tasks=t.astype(str), issues=i, git=g.astype(str), resources=build_resources().astype(str), name="eval"), as_of)

found = {(r.task_id, r.rule) for r in ctx.risks}
hit = PLANTED_RISKS & found
print("1) EARLY RISK DETECTION")
print(f"   planted risks found: {len(hit)}/{len(PLANTED_RISKS)}  (recall {len(hit) / len(PLANTED_RISKS):.0%})")
print(f"   total risks reported: {len(ctx.risks)}  -> {sum(r.level in ('Critical', 'High') for r in ctx.risks)} Critical/High")
print("2) RISK PREDICTION")
print(f"   late-probability model: AUC {ctx.model_info['auc']} on held-out {ctx.model_info['data']} history ({ctx.model_info['test_rows']} rows)")
print(f"   Monte-Carlo chance of meeting deadline: {ctx.monte_carlo['on_time_prob']:.0%}  (P80 finish {ctx.monte_carlo['p80']}, deadline {ctx.summary['deadline']})")
print("3) ROOT CAUSE / EXPLAINABILITY")
print(f"   risks with evidence + cause: {sum(bool(r.evidence_lines and r.root_cause) for r in ctx.risks)}/{len(ctx.risks)}")
print(f"3b) PROJECT HEALTH SCORE: {ctx.health['score']}/100 ({ctx.health['label']}) - " + ", ".join(f"{c['name']} {c['score']:.0f}" for c in ctx.health["components"]))
print("4) WHAT-IF / IMPACT")
for w in ctx.scenarios:
    print(f"   {w['title']}: on-time chance {w['on_time_before']:.0%} -> {w['on_time_after']:.0%}, {w['tasks_affected']} tasks affected")
print("5) MITIGATION (before -> after, simulated)")
for a in [x for x in ctx.actions if x.on_time_after is not None][:4]:
    print(f"   {a.title}: on-time chance {a.on_time_before:.0%} -> {a.on_time_after:.0%}")
combo = [x.scenario for x in ctx.actions if x.on_time_after is not None][:3]
flat = [s for sc in combo for s in sc]
if flat:
    from projex.whatif import apply_scenario, monte_carlo
    from projex.graph import build_graph
    d2, G2 = apply_scenario(ctx.tasks, as_of, flat)
    m2 = monte_carlo(d2, G2, as_of, n=1000)
    m1 = monte_carlo(ctx.tasks, ctx.graph, as_of, n=1000)
    print(f"   top-3 actions combined: on-time chance {m1['on_time_prob']:.0%} -> {m2['on_time_prob']:.0%}")
print("6) CONTINUOUS MONITORING: run twice with changed data; see the Monitoring tab / run_cli.py --watch")
