"""Continuous Monitoring & Feedback - stores every analysis in SQLite, detects what changed since the last run,
and computes the health trend / forecast ("Predictions & Trends")."""
from __future__ import annotations
import hashlib
import json
import os
import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd

from . import config
from .models import Context

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
  run_id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT, ts TEXT, as_of TEXT, fingerprint TEXT,
  overall_progress REAL, n_risks INTEGER, n_critical INTEGER, n_high INTEGER,
  deadline_slip REAL, on_time_prob REAL, total_score REAL, health REAL);
CREATE TABLE IF NOT EXISTS risk_scores(
  run_id INTEGER, key TEXT, task_id TEXT, rule TEXT, category TEXT, title TEXT, score REAL, level TEXT);
"""


def connect(path: str | None = None) -> sqlite3.Connection:
    path = path or config.DB_PATH
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def history(project: str, path: str | None = None) -> pd.DataFrame:
    conn = connect(path)
    try:
        return pd.read_sql_query("SELECT * FROM runs WHERE project=? ORDER BY run_id", conn, params=(project,))
    finally:
        conn.close()


def compute_trend(hist: pd.DataFrame) -> dict:
    h = hist["health"].dropna().tail(6).tolist()
    if len(h) < 2:
        return {"runs": len(h), "label": "Not enough data", "slope": 0.0, "forecast": h[-1] if h else 0.0}
    slope = float(np.polyfit(range(len(h)), h, 1)[0])
    return {"runs": len(h), "slope": round(slope, 2), "forecast": round(float(np.clip(h[-1] + slope, 0, 100)), 1),
            "label": "Improving" if slope > 1 else "Declining" if slope < -1 else "Stable"}


class ContinuousMonitoring:
    name = "Continuous Monitoring"

    def __init__(self, db_path: str | None = None, record: bool = True):
        self.db_path, self.record = db_path, record

    def run(self, ctx: Context, llm=None) -> Context:
        conn = connect(self.db_path)
        try:
            prev = conn.execute("SELECT run_id, fingerprint FROM runs WHERE project=? ORDER BY run_id DESC LIMIT 1", (ctx.project_name,)).fetchone()
            prev_scores = {}
            if prev:
                for k, score, level in conn.execute("SELECT key, score, level FROM risk_scores WHERE run_id=?", (prev[0],)):
                    prev_scores[k] = (score, level)
            cur = {r.key: (r.score, r.level) for r in ctx.risks}
            new = sorted(k for k in cur if k not in prev_scores)
            resolved = sorted(k for k in prev_scores if k not in cur)
            esc = sorted(k for k in cur if k in prev_scores and cur[k][0] - prev_scores[k][0] >= 10)
            imp = sorted(k for k in cur if k in prev_scores and prev_scores[k][0] - cur[k][0] >= 10)
            fp = hashlib.sha1(json.dumps(sorted((k, round(v[0], 1)) for k, v in cur.items()) +
                                         [round(ctx.schedule.deadline_slip, 1), ctx.health.get("score")]).encode()).hexdigest()
            unchanged = bool(prev and prev[1] == fp)
            ctx.changes = {"first_run": prev is None, "unchanged": unchanged, "new": new, "resolved": resolved,
                           "escalated": esc, "improved": imp}
            if self.record and not unchanged:
                lv = pd.Series([r.level for r in ctx.risks]).value_counts().to_dict() if ctx.risks else {}
                c = conn.execute(
                    "INSERT INTO runs(project, ts, as_of, fingerprint, overall_progress, n_risks, n_critical, n_high, deadline_slip, on_time_prob, total_score, health) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (ctx.project_name, datetime.now().isoformat(timespec="seconds"), ctx.as_of.isoformat(), fp,
                     ctx.summary.get("overall_progress"), len(ctx.risks), lv.get("Critical", 0), lv.get("High", 0),
                     float(ctx.schedule.deadline_slip), float(ctx.monte_carlo.get("on_time_prob", 0)),
                     float(sum(r.score for r in ctx.risks)), float(ctx.health.get("score", 0))))
                rid = c.lastrowid
                conn.executemany("INSERT INTO risk_scores VALUES (?,?,?,?,?,?,?,?)",
                                 [(rid, r.key, r.task_id, r.rule, r.category, r.title, r.score, r.level) for r in ctx.risks])
                conn.commit()
            hist = pd.read_sql_query("SELECT * FROM runs WHERE project=? ORDER BY run_id", conn, params=(ctx.project_name,))
        finally:
            conn.close()
        ctx.trend = compute_trend(hist)
        ch = ctx.changes
        if ch["first_run"]:
            ctx.log(self.name, "First analysis stored as the monitoring baseline.")
        elif ch["unchanged"]:
            ctx.log(self.name, "No change since the previous analysis.")
        else:
            ctx.log(self.name, f"Since last run: {len(new)} new, {len(resolved)} resolved, {len(esc)} escalated, {len(imp)} improved risk(s). "
                               f"Health trend: {ctx.trend['label'].lower()}.")
        return ctx
