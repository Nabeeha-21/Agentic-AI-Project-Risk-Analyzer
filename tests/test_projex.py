"""Run with:  pytest -q"""
from datetime import date

import pandas as pd
import pytest

from projex.data_collection import ProjectData, prepare
from projex.graph import build_graph, compute_schedule, find_cycles
from projex.orchestrator import AIOrchestrator
from projex.sample_data import PLANTED_RISKS, build_resources, build_sample
from projex.whatif import monte_carlo, simulate

AS_OF = date(2026, 10, 10)


@pytest.fixture(scope="module")
def project():
    t, i, g = build_sample(AS_OF)
    return ProjectData(tasks=t.astype(str), issues=i, git=g.astype(str), resources=build_resources().astype(str), name="test")


@pytest.fixture(scope="module")
def ctx(project):
    return AIOrchestrator(db_path=":memory:", record=False).run(project, AS_OF)


def test_preprocessing(project):
    df, warnings = prepare(project, AS_OF)
    assert warnings == []
    assert df.loc["T07", "days_overdue"] == 5
    assert df.loc["T07", "progress_gap"] > 50
    assert df.loc["T12", "days_since_commit"] == 15
    assert df.loc["T15", "open_critical"] == 3
    assert df.loc["T12", "owner_load"] == 5            # Ravi is overloaded


def test_bad_data_is_reported_not_crashing():
    t = pd.DataFrame({"task_id": ["A", "A", "B"], "name": ["a", "a2", "b"], "owner": ["x", "x", ""],
                      "start_date": ["2026-10-01", "2026-10-01", "not-a-date"], "due_date": ["2026-10-20"] * 3,
                      "est_days": ["5", "5", "x"], "progress": ["50%", "50", "10"], "dependencies": ["", "", "ZZZ"]})
    df, warnings = prepare(ProjectData(tasks=t), AS_OF)
    assert len(warnings) >= 2 and list(df.index) == ["A"]


def test_no_cycles_in_sample(ctx):
    assert find_cycles(ctx.graph) == []


def test_cycle_detection():
    t = pd.DataFrame({"task_id": ["A", "B"], "name": ["a", "b"], "owner": ["x", "y"], "start_date": ["2026-10-01"] * 2,
                      "due_date": ["2026-10-20"] * 2, "est_days": ["5", "5"], "progress": ["0", "0"], "dependencies": ["B", "A"]})
    df, _ = prepare(ProjectData(tasks=t), AS_OF)
    G = build_graph(df)
    assert find_cycles(G)
    compute_schedule(df, G, AS_OF)                      # must not crash on cyclic data


def test_detection_recall_on_planted_risks(ctx):
    found = {(r.task_id, r.rule) for r in ctx.risks}
    missing = PLANTED_RISKS - found
    assert not missing, f"planted risks not detected: {missing}"


def test_scores_and_ranking(ctx):
    scores = [r.score for r in ctx.risks]
    assert scores == sorted(scores, reverse=True)
    assert all(0 <= r.probability <= 1 and 0 <= r.impact <= 1 for r in ctx.risks)
    assert ctx.risks[0].task_id == "T07"


def test_every_risk_has_evidence_and_cause(ctx):
    for r in ctx.risks:
        assert r.evidence_lines and r.root_cause


def test_what_if_delay_and_resource(ctx):
    df = ctx.tasks
    delay = simulate(df, AS_OF, [{"type": "delay", "task_id": "T07", "days": 10}])
    assert delay["scenario"].finish["T07"] > delay["baseline"].finish["T07"]
    fast = simulate(df, AS_OF, [{"type": "add_resource", "task_id": "T07", "count": 1}])
    assert fast["scenario"].finish["T07"] < fast["baseline"].finish["T07"]
    reassign = simulate(df, AS_OF, [{"type": "reassign", "task_id": "T25", "new_owner": "Meena"}])
    assert reassign["tasks_after"].loc["T07", "owner_load"] == 4


def test_monte_carlo(ctx):
    mc = monte_carlo(ctx.tasks, ctx.graph, AS_OF, n=500)
    assert 0 <= mc["on_time_prob"] <= 1 and mc["p50_offset"] <= mc["p90_offset"]


def test_mitigation_actions_are_simulated_and_ranked(ctx):
    assert ctx.actions
    prios = [a.priority_score for a in ctx.actions]
    assert prios == sorted(prios, reverse=True)
    assert any(a.on_time_after is not None and a.on_time_after > a.on_time_before for a in ctx.actions)


def test_monitoring_detects_changes(project):
    import tempfile, os                                   # a temp file DB (":memory:" is per-connection)
    path = os.path.join(tempfile.mkdtemp(), "t.db")
    pipe = AIOrchestrator(db_path=path, record=True)
    first = pipe.run(project, AS_OF)
    assert first.changes["first_run"]
    again = pipe.run(project, AS_OF)
    assert again.changes["unchanged"]
    # fix the stalled/overdue work: mark T07 done -> risks must be resolved
    fixed = ProjectData(tasks=project.tasks.copy(), issues=project.issues, git=project.git, resources=project.resources, name="test")
    fixed.tasks.loc[fixed.tasks["task_id"] == "T07", "progress"] = "100"
    third = pipe.run(fixed, AS_OF)
    assert "T07:overdue" in third.changes["resolved"]


def test_health_score_and_components(ctx):
    h = ctx.health
    assert 0 <= h["score"] <= 100 and len(h["components"]) == 5
    assert abs(sum(c["weight"] for c in h["components"]) - 1.0) < 1e-9


def test_all_seven_agents_ran(ctx):
    names = {t["agent"] for t in ctx.trace}
    for a in ["Risk Agent", "Dependency Agent", "Resource Agent", "Root Cause & Evidence Agent", "Impact Agent",
              "Simulation Agent", "Recommendation Agent", "AI Orchestrator"]:
        assert a in names, a


def test_impact_and_scenarios(ctx):
    assert all(r.impact_text for r in ctx.risks[:5])
    assert ctx.scenarios and all(0 <= s["on_time_after"] <= 1 for s in ctx.scenarios)


def test_resources_capacity_is_used(project):
    p2 = ProjectData(tasks=project.tasks, issues=project.issues, git=project.git, name="t2",
                     resources=pd.DataFrame({"name": ["Ravi"], "capacity": ["6"]}))
    c = AIOrchestrator(db_path=":memory:", record=False).run(p2, AS_OF)
    assert not any(r.rule == "owner_overload" and r.owner == "Ravi" for r in c.risks)   # capacity 6 >= load 5
    assert any("missing from resources" in w for w in c.warnings)
