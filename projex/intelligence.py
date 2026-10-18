"""Intelligence Layer - risk levels & prioritisation, predictions, Project Health Score.

* Probability  = 1/2 rule-based likelihood + 1/2 ML 'will this task finish late?' (logistic regression)
* Impact       = downstream tasks, priority, critical path, projected slip (dependency graph)
* Score        = probability x impact x 100  -> level Critical / High / Medium / Low
* Forecast     = Monte-Carlo simulation of the project finish date -> probability of meeting the deadline
* Health score = weighted blend of schedule, exposure, dependency, resource and quality sub-scores (0-100)

The ML model is trained on SYNTHETIC history (see synthetic_history) - replace it with real past-project data to make
it a real predictor.
"""
from __future__ import annotations
from functools import lru_cache
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import config
from .graph import downstream_tasks
from .models import Context

FEATURES = ["progress_gap", "days_to_due", "remaining_ratio", "owner_load", "open_critical",
            "open_issues", "days_since_commit", "downstream", "incomplete_deps", "priority_weight"]
FEATURE_LABELS = {
    "progress_gap": "progress behind plan", "days_to_due": "little time left before the due date",
    "remaining_ratio": "remaining work is large relative to time left", "owner_load": "owner is overloaded",
    "open_critical": "open critical issues", "open_issues": "open issues", "days_since_commit": "no recent commits",
    "downstream": "many tasks depend on it", "incomplete_deps": "unfinished prerequisites", "priority_weight": "high priority",
}
HEALTH_WEIGHTS = {"Schedule": 0.30, "Risk exposure": 0.20, "Dependencies": 0.20, "Resources": 0.15, "Quality": 0.15}


def synthetic_history(n: int = 4000, seed: int = 42) -> pd.DataFrame:
    """Simulated past tasks. Lateness follows plausible project-management logic plus noise."""
    rng = np.random.default_rng(seed)
    d = pd.DataFrame({
        "progress_gap": np.clip(rng.normal(8, 14, n), -10, 70),
        "days_to_due": rng.integers(-10, 30, n).astype(float),
        "remaining_ratio": np.clip(rng.gamma(2.0, 0.5, n), 0, 5),
        "owner_load": rng.integers(1, 8, n).astype(float),
        "open_critical": rng.poisson(0.6, n).astype(float),
        "open_issues": rng.poisson(1.5, n).astype(float),
        "days_since_commit": np.clip(rng.exponential(3.5, n), 0, 30),
        "downstream": rng.poisson(2.0, n).astype(float),
        "incomplete_deps": rng.poisson(0.7, n).astype(float),
        "priority_weight": rng.choice([0.5, 1.0, 1.5, 2.0], n),
    })
    z = (-3.0 + 0.055 * d.progress_gap + 0.85 * np.clip(d.remaining_ratio - 0.8, 0, 4)
         + 0.30 * np.clip(d.owner_load - 3, 0, 5) + 0.35 * d.open_critical + 0.05 * d.open_issues
         + 0.07 * np.clip(d.days_since_commit - 5, 0, 25) + 0.40 * d.incomplete_deps
         - 0.03 * d.days_to_due + 0.05 * d.downstream + rng.normal(0, 0.6, n))
    d["late"] = (rng.random(n) < 1 / (1 + np.exp(-z))).astype(int)
    return d


@lru_cache(maxsize=1)
def get_model():
    hist = synthetic_history()
    Xtr, Xte, ytr, yte = train_test_split(hist[FEATURES], hist["late"], test_size=0.25, random_state=1, stratify=hist["late"])
    pipe = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    pipe.fit(Xtr, ytr)
    auc = float(roc_auc_score(yte, pipe.predict_proba(Xte)[:, 1]))
    return pipe, {"auc": round(auc, 3), "train_rows": int(len(Xtr)), "test_rows": int(len(Xte)),
                  "late_rate": round(float(hist["late"].mean()), 3), "data": "synthetic"}


def task_features(df: pd.DataFrame, G) -> pd.DataFrame:
    X = pd.DataFrame(index=df.index)
    X["progress_gap"] = df["progress_gap"]
    X["days_to_due"] = df["days_to_due"].astype(float)
    X["remaining_ratio"] = (df["remaining_days"] / df["days_to_due"].clip(lower=1)).clip(0, 5)
    X["owner_load"] = (df["owner_load"] - df["owner_capacity"] + config.OWNER_CAPACITY).astype(float)
    X["open_critical"] = df["open_critical"].astype(float)
    X["open_issues"] = df["open_issues"].astype(float)
    X["days_since_commit"] = df["days_since_commit"].astype(float)
    X["downstream"] = [float(len(downstream_tasks(G, t))) for t in df["task_id"]]
    X["incomplete_deps"] = [float(sum(not df.loc[d, "is_done"] for d in deps)) for deps in df["deps"]]
    X["priority_weight"] = df["priority_weight"]
    return X[FEATURES]


def level_for(score: float) -> str:
    for name, cut in config.LEVEL_THRESHOLDS:
        if score >= cut:
            return name
    return "Low"


def health_label(score: float) -> str:
    return "Healthy" if score >= 75 else "Watch" if score >= 55 else "At risk" if score >= 35 else "Critical"


def compute_health(ctx: Context) -> dict:
    s, mc = ctx.summary, ctx.monte_carlo
    by_cat: dict[str, float] = {}
    for r in ctx.risks:
        by_cat[r.category] = by_cat.get(r.category, 0.0) + r.score
    decay = lambda total, k: 100.0 / (1.0 + total / k)
    gap = max(0.0, s["expected_progress"] - s["overall_progress"])
    comp = {
        "Schedule": 100 * (0.6 * mc["on_time_prob"] + 0.4 * float(np.clip(1 - gap / 25.0, 0, 1))),
        "Risk exposure": decay(sum(by_cat.values()), 250),
        "Dependencies": decay(by_cat.get("Dependency", 0), 100),
        "Resources": decay(by_cat.get("Resource", 0), 80),
        "Quality": decay(by_cat.get("Technical", 0) + by_cat.get("Quality", 0), 80),
    }
    score = sum(HEALTH_WEIGHTS[k] * v for k, v in comp.items())
    return {"score": round(score, 1), "label": health_label(score),
            "components": [{"name": k, "score": round(v, 1), "weight": HEALTH_WEIGHTS[k]} for k, v in comp.items()]}


class IntelligenceLayer:
    name = "Intelligence Layer"

    def run(self, ctx: Context, llm=None) -> Context:
        df, G, sched = ctx.tasks, ctx.graph, ctx.schedule
        model, info = get_model()
        ctx.model_info = info
        X = task_features(df, G)
        proba = np.where(df["is_done"].values, 0.0, model.predict_proba(X)[:, 1])
        ctx.task_late_prob = dict(zip(df["task_id"], proba.round(3)))

        scaler, lr = model.steps[0][1], model.steps[1][1]
        contrib = scaler.transform(X) * lr.coef_[0]
        for i, tid in enumerate(df["task_id"]):
            top = np.argsort(contrib[i])[::-1][:3]
            ctx.task_drivers[tid] = [FEATURE_LABELS[FEATURES[j]] for j in top if contrib[i][j] > 0.15]

        on_cp = set(sched.critical_path)
        for r in ctx.risks:
            row = df.loc[r.task_id]
            n_down = len(downstream_tasks(G, r.task_id))
            slip = max(sched.slip.get(r.task_id, 0.0), 0.0)
            impact = (0.20 + 0.10 * n_down + 0.15 * (row["priority_weight"] - 1.0)
                      + (0.20 if r.task_id in on_cp else 0.0) + 0.25 * min(slip / 10.0, 1.0))
            r.impact = float(np.clip(impact, 0.05, 1.0))
            r.ml_prob = float(ctx.task_late_prob.get(r.task_id, 0.0))
            r.probability = float(np.clip(0.5 * r.base_prob + 0.5 * r.ml_prob, 0.02, 0.99))
            r.score = round(100 * r.probability * r.impact, 1)
            r.level = level_for(r.score)
        ctx.risks.sort(key=lambda r: r.score, reverse=True)
        for i, r in enumerate(ctx.risks, 1):
            r.risk_id = f"R{i:03d}"

        from .whatif import monte_carlo
        ctx.monte_carlo = monte_carlo(df, G, ctx.as_of, n=config.MC_RUNS)
        ctx.health = compute_health(ctx)
        lv = pd.Series([r.level for r in ctx.risks]).value_counts().to_dict()
        ctx.log(self.name, f"Prioritised {len(ctx.risks)} risks {lv}. Late-probability model AUC {info['auc']} ({info['data']} history). "
                           f"Chance of meeting the deadline {ctx.monte_carlo['on_time_prob'] * 100:.0f}%. "
                           f"Project Health Score {ctx.health['score']} ({ctx.health['label']}).")
        return ctx
