"""Shared data structures. The `Context` object is the 'blackboard' every agent reads from and writes to."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional
import pandas as pd


@dataclass
class Risk:
    risk_id: str
    task_id: str
    task_name: str
    owner: str
    category: str            # Schedule | Resource | Technical | Dependency | Quality
    rule: str                # machine-readable rule name, e.g. "overdue"
    title: str
    description: str
    base_prob: float         # rule-based likelihood 0..1
    evidence: dict[str, Any] = field(default_factory=dict)
    # filled by the prediction agent
    ml_prob: float = 0.0
    probability: float = 0.0
    impact: float = 0.0
    score: float = 0.0
    level: str = "Low"
    # filled by the root-cause agent
    evidence_lines: list[str] = field(default_factory=list)
    root_cause: str = ""
    contributing_factors: list[str] = field(default_factory=list)
    explained_by: str = "rules"   # "rules" or "llm"
    # filled by the impact agent
    impact_info: dict[str, Any] = field(default_factory=dict)
    impact_text: str = ""

    @property
    def key(self) -> str:
        return f"{self.task_id}:{self.rule}"


@dataclass
class Action:
    action_id: str
    title: str
    description: str
    effort: int                      # 1 (easy) .. 3 (hard)
    scenario: list[dict]             # what-if scenario that models this action ([] = process action)
    risk_keys: list[str] = field(default_factory=list)
    target_task: str = ""
    project_days_saved: Optional[float] = None
    on_time_before: Optional[float] = None
    on_time_after: Optional[float] = None
    p80_days_saved: Optional[float] = None
    target_slip_before: Optional[float] = None
    target_slip_after: Optional[float] = None
    priority_score: float = 0.0
    rationale: str = ""


@dataclass
class Context:
    as_of: date
    project_name: str = "Project"
    raw: Any = None                              # ProjectData
    tasks: Optional[pd.DataFrame] = None         # enriched tasks table
    graph: Any = None                            # networkx.DiGraph
    schedule: Any = None                         # baseline ScheduleResult
    summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)
    task_late_prob: dict[str, float] = field(default_factory=dict)
    task_drivers: dict[str, list[str]] = field(default_factory=dict)
    model_info: dict[str, Any] = field(default_factory=dict)
    monte_carlo: dict[str, Any] = field(default_factory=dict)
    actions: list[Action] = field(default_factory=list)
    changes: dict[str, Any] = field(default_factory=dict)
    trace: list[dict] = field(default_factory=list)   # agent activity log
    llm_used: bool = False
    health: dict[str, Any] = field(default_factory=dict)
    insights: list[dict] = field(default_factory=list)
    scenarios: list[dict] = field(default_factory=list)
    trend: dict[str, Any] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)

    def log(self, agent: str, message: str) -> None:
        self.trace.append({"agent": agent, "message": message})
