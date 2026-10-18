from __future__ import annotations
from ..models import Context, Risk


class Agent:
    """Every agent reads/writes the shared Context (a blackboard) and logs what it did."""
    name = "Agent"

    def run(self, ctx: Context, llm=None) -> Context:   # pragma: no cover
        raise NotImplementedError


def new_risk(ctx: Context, row, category: str, rule: str, title: str, desc: str, base: float, evidence: dict) -> Risk:
    r = Risk(risk_id=f"R{len(ctx.risks) + 1:03d}", task_id=row["task_id"], task_name=row["name"], owner=row["owner"],
             category=category, rule=rule, title=title, description=desc,
             base_prob=float(min(max(base, 0.05), 0.97)), evidence=evidence)
    ctx.risks.append(r)
    return r
