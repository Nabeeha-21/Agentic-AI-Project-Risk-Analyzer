"""AI Orchestrator - coordinates every layer and agent and manages the flow of information between them.

    Input layer  -> Processing layer -> [Risk, Dependency, Resource agents] -> Intelligence layer
                 -> [Root Cause, Impact, Simulation, Recommendation agents] -> Insights -> Continuous Monitoring
                          ^------------------------- feedback loop (re-run on new data) --------------------------+

One failing agent never kills the run: the orchestrator logs the error and carries on with what it has.
"""
from __future__ import annotations
import time
from datetime import date
from typing import Optional

from .agents.dependency_agent import DependencyAgent
from .agents.impact_agent import ImpactAgent
from .agents.recommendation_agent import RecommendationAgent
from .agents.resource_agent import ResourceAgent
from .agents.risk_agent import RiskAgent
from .agents.root_cause import RootCauseAgent
from .agents.simulation_agent import SimulationAgent
from .data_collection import ProjectData, prepare
from .insights import build_insights
from .intelligence import IntelligenceLayer
from .llm import LLMClient
from .models import Context
from .monitoring import ContinuousMonitoring
from .processing import ProcessingLayer


class AIOrchestrator:
    def __init__(self, llm: Optional[LLMClient] = None, db_path: Optional[str] = None, record: bool = True):
        self.llm = llm
        self.steps = [ProcessingLayer(), RiskAgent(), DependencyAgent(), ResourceAgent(), IntelligenceLayer(),
                      RootCauseAgent(), ImpactAgent(), SimulationAgent(), RecommendationAgent(),
                      ContinuousMonitoring(db_path=db_path, record=record)]

    def run(self, project: ProjectData, as_of: Optional[date] = None) -> Context:
        ctx = Context(as_of=as_of or date.today(), project_name=project.name, raw=project)
        t0 = time.perf_counter()
        ctx.tasks, ctx.warnings = prepare(project, ctx.as_of)                         # Input layer + cleaning/validation
        ctx.log("AI Orchestrator", f"Received {len(project.tasks)} tasks, {len(project.resources)} team members, "
                                   f"{len(project.issues)} issues, {len(project.git)} git records; dispatching to "
                                   f"{len(self.steps)} layers/agents.")
        for step in self.steps:
            t = time.perf_counter()
            try:
                ctx = step.run(ctx, self.llm)
            except Exception as e:                                                    # isolate failures
                ctx.log("AI Orchestrator", f"{step.name} failed ({type(e).__name__}: {e}); continuing without it.")
                ctx.warnings.append(f"{step.name} failed: {e}")
                if step.name == "Processing Layer":
                    raise                                                              # nothing works without it
            ctx.timings[step.name] = round(time.perf_counter() - t, 3)
        # insights need the trend, so they are produced last
        ctx.insights = build_insights(ctx)
        ctx.timings["total"] = round(time.perf_counter() - t0, 3)
        ctx.log("AI Orchestrator", f"Analysis complete in {ctx.timings['total']}s. Health score {ctx.health.get('score')} ({ctx.health.get('label')}).")
        return ctx


ProjexPipeline = AIOrchestrator          # backwards-compatible name
