"""Recommendation Agent - proposes concrete actions, SIMULATES each one with the what-if engine and ranks them."""
from __future__ import annotations
from .. import config
from ..graph import downstream_tasks
from ..models import Action, Context
from ..graph import build_graph
from ..whatif import monte_carlo, simulate
from .base import Agent

SYSTEM = ("You are the Recommendation agent of a project risk analyzer. Write 2 sentences explaining why this action is "
          "recommended, using ONLY the numbers given. No new facts.")


class RecommendationAgent(Agent):
    name = "Recommendation Agent"

    def _candidates(self, ctx: Context) -> list[Action]:
        df, G = ctx.tasks, ctx.graph
        acts: dict[str, Action] = {}
        risks = [r for r in ctx.risks if r.level in ("Critical", "High", "Medium")][:10]

        def add(key, title, desc, effort, scenario, r, target=None):
            if key in acts:
                acts[key].risk_keys.append(r.key)
                return
            acts[key] = Action(action_id=f"A{len(acts) + 1:02d}", title=title, description=desc, effort=effort,
                               scenario=scenario, risk_keys=[r.key], target_task=target or r.task_id)

        owners_load = df[~df["is_done"]].groupby("owner")["owner_load"].first().to_dict()
        caps = df.groupby("owner")["owner_capacity"].first().to_dict()
        for o in df["owner"].unique():
            owners_load.setdefault(o, 0)

        for r in risks:
            row = df.loc[r.task_id]
            incomplete = [d for d in row["deps"] if not df.loc[d, "is_done"]]
            if r.rule in ("overdue", "behind_pace", "critical_issues", "issue_backlog", "bottleneck", "stalled"):
                add(f"res:{r.task_id}", f"Add one engineer to {r.task_id}",
                    f"Assign an extra developer to '{row['name']}' to recover lost time (assumes {int(config.RESOURCE_GAIN * 100)}% productivity gain).",
                    2, [{"type": "add_resource", "task_id": r.task_id, "count": 1}], r)
            if r.rule in ("dependency_violation", "projected_late", "overdue", "behind_pace"):
                blockers = incomplete if r.rule != "projected_late" else [r.evidence.get("driver")]
                for b in [x for x in blockers if x]:
                    add(f"res:{b}", f"Fast-track {b} with extra capacity",
                        f"'{df.loc[b, 'name']}' blocks {r.task_id}; adding an engineer there shortens the whole chain.",
                        2, [{"type": "add_resource", "task_id": b, "count": 1}], r, target=b)
                    if r.rule == "dependency_violation":
                        add(f"dec:{r.task_id}:{b}", f"Decouple {r.task_id} from {b} (use a stub/mock)",
                            f"Define an interface contract and let '{row['name']}' proceed against a mock of '{df.loc[b, 'name']}'.",
                            2, [{"type": "decouple", "task_id": r.task_id, "dependency": b}], r)
            if r.rule == "stalled":
                add(f"proc:{r.task_id}", f"Unblock {r.task_id}: 15-minute check-in with {row['owner']}",
                    "Find out what is blocking progress (access, requirements, waiting on someone) and clear it this week.", 1, [], r)
            if r.rule in ("critical_issues", "issue_backlog"):
                add(f"proc:bugs:{r.task_id}", f"Bug-triage session for {r.task_id}",
                    "Review open defects, close duplicates, and fix critical/high issues before building new features.", 1, [], r)
            if r.rule in ("overdue", "behind_pace") and row["priority_weight"] <= 1.0:
                add(f"scope:{r.task_id}", f"Trim 30% of scope on {r.task_id}",
                    f"Agree with the stakeholder to defer the least important 30% of '{row['name']}'.",
                    3, [{"type": "reduce_scope", "task_id": r.task_id, "pct": 30}], r)
            if r.rule in ("owner_overload", "key_person") or row["owner_load"] > row["owner_capacity"]:
                owner = row["owner"]
                if f"rebal:{owner}" in acts or f"rebal1:{owner}" in acts:
                    continue
                mine = df[(df["owner"] == owner) & ~df["is_done"]].copy()
                mine["_cp"] = mine["task_id"].isin(ctx.schedule.critical_path)
                mine["_d"] = [len(downstream_tasks(G, t)) for t in mine["task_id"]]
                mine = mine.sort_values(["in_progress", "_cp", "priority_weight", "_d"])   # easiest to hand over first
                need = int(owners_load.get(owner, 0) - caps.get(owner, config.OWNER_CAPACITY))
                loads = dict(owners_load)
                moves = []
                for _, t in mine.head(max(need, 1)).iterrows():
                    cand = sorted((o for o in loads if o not in (owner, "Unassigned")), key=lambda o: loads[o] - caps.get(o, config.OWNER_CAPACITY))
                    if not cand:
                        break
                    moves.append({"type": "reassign", "task_id": t["task_id"], "new_owner": cand[0]})
                    loads[cand[0]] += 1
                if moves:
                    add(f"rebal1:{owner}", f"Hand {moves[0]['task_id']} over to {moves[0]['new_owner']}",
                        f"Move '{df.loc[moves[0]['task_id'], 'name']}' from {owner} to {moves[0]['new_owner']} (currently has the most spare capacity).",
                        1, moves[:1], r, target=r.task_id)
                    if len(moves) > 1:
                        txt = ", ".join(f"{m['task_id']}→{m['new_owner']}" for m in moves)
                        add(f"rebal:{owner}", f"Rebalance {owner}'s workload to capacity",
                            f"Reassign {len(moves)} tasks ({txt}) so {owner} is back to about {caps.get(owner, config.OWNER_CAPACITY):.0f} concurrent tasks.",
                            2, moves, r, target=r.task_id)
        return list(acts.values())

    def run(self, ctx: Context, llm=None) -> Context:
        df = ctx.tasks
        score_of = {r.key: r.score for r in ctx.risks}
        base_mc = monte_carlo(df, ctx.graph, ctx.as_of, n=1000)
        final: list[Action] = []
        for a in self._candidates(ctx):
            best_risk = max((score_of.get(k, 0) for k in a.risk_keys), default=0)
            if a.scenario:
                sim = simulate(df, ctx.as_of, a.scenario)
                mc = monte_carlo(sim["tasks_after"], build_graph(sim["tasks_after"]), ctx.as_of, n=1000)
                a.project_days_saved = round(-sim["project_shift_days"], 1)
                a.on_time_before, a.on_time_after = base_mc["on_time_prob"], mc["on_time_prob"]
                a.p80_days_saved = round(base_mc["p80_offset"] - mc["p80_offset"], 1)
                a.target_slip_before = round(sim["baseline"].slip.get(a.target_task, 0.0), 1)
                a.target_slip_after = round(sim["scenario"].slip.get(a.target_task, 0.0), 1)
                gain = (max(a.project_days_saved, 0) + 0.5 * max(a.p80_days_saved, 0)
                        + 10.0 * max(a.on_time_after - a.on_time_before, 0)
                        + 0.3 * max(a.target_slip_before - a.target_slip_after, 0))
                if gain < 0.2:
                    continue                       # simulated and found useless -> don't recommend
                a.priority_score = round((gain + best_risk / 25.0) / a.effort, 2)
                a.rationale = (f"Simulation: chance of meeting the deadline {a.on_time_before * 100:.0f}% → {a.on_time_after * 100:.0f}%; "
                               f"80%-confidence finish {a.p80_days_saved:+.1f} day(s) earlier; "
                               f"{a.target_task} slip {a.target_slip_before:+.0f} → {a.target_slip_after:+.0f} day(s).")
            else:
                a.priority_score = round((best_risk / 25.0) / a.effort, 2)
                a.rationale = "Process action (cannot be simulated); recommended because it addresses a high-scoring risk at low cost."
            final.append(a)
        final.sort(key=lambda x: x.priority_score, reverse=True)
        ctx.actions = final[:12]
        for i, a in enumerate(ctx.actions, 1):
            a.action_id = f"A{i:02d}"

        if llm is not None and llm.available:
            for a in ctx.actions[:3]:
                txt = llm.complete(SYSTEM, f"Action: {a.title}. {a.description} {a.rationale} Effort {a.effort}/3.", 200)
                if txt:
                    a.rationale = txt
                    ctx.llm_used = True
        top = ctx.actions[0].title if ctx.actions else "none"
        ctx.log(self.name, f"Evaluated candidate actions by simulation and ranked {len(ctx.actions)}. Top recommendation: {top}.")
        return ctx
