"""Module 1 & 2 - Project data collection and preprocessing.

Accepts three CSV files (only tasks is mandatory):
  tasks.csv        task_id,name,owner,start_date,due_date,est_days,progress[,status,dependencies,priority,component]
  issues.csv       issue_id,task_id,severity,status[,title,opened_date]
  git_activity.csv task_id,commits_14d,last_commit_date
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
import re
import pandas as pd

from . import config

REQUIRED_TASK_COLS = ["task_id", "name", "owner", "start_date", "due_date", "est_days", "progress"]
DONE_WORDS = {"done", "completed", "complete", "closed", "finished"}
PROGRESS_WORDS = {"in progress", "in_progress", "inprogress", "active", "started", "ongoing", "wip"}
CLOSED_ISSUE = {"closed", "resolved", "done", "fixed"}


@dataclass
class ProjectData:
    tasks: pd.DataFrame
    issues: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["issue_id", "task_id", "severity", "status"]))
    git: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["task_id", "commits_14d", "last_commit_date"]))
    resources: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["name", "role", "capacity"]))
    name: str = "Project"


def load_csvs(tasks, issues=None, git=None, resources=None, name: str = "Project") -> ProjectData:
    """`tasks`, `issues`, `git` may be file paths or file-like objects (e.g. Streamlit uploads)."""
    t = pd.read_csv(tasks, dtype=str).fillna("")
    missing = [c for c in REQUIRED_TASK_COLS if c not in [x.strip().lower() for x in t.columns]]
    t.columns = [c.strip().lower() for c in t.columns]
    if missing:
        raise ValueError(f"tasks file is missing required column(s): {', '.join(missing)}")
    i = pd.read_csv(issues, dtype=str).fillna("") if issues is not None else None
    g = pd.read_csv(git, dtype=str).fillna("") if git is not None else None
    r = pd.read_csv(resources, dtype=str).fillna("") if resources is not None else None
    pd_ = ProjectData(tasks=t, name=name)
    if r is not None:
        r.columns = [c.strip().lower() for c in r.columns]
        pd_.resources = r
    if i is not None:
        i.columns = [c.strip().lower() for c in i.columns]
        pd_.issues = i
    if g is not None:
        g.columns = [c.strip().lower() for c in g.columns]
        pd_.git = g
    return pd_


def compute_owner_load(df: pd.DataFrame, as_of: date) -> pd.Series:
    """Number of concurrently active tasks per owner (in progress, or starting within 7 days)."""
    horizon = pd.Timestamp(as_of) + pd.Timedelta(days=7)
    active = (~df["is_done"]) & ((df["progress"] > 0) | (df["start_date"] <= horizon))
    return active.groupby(df["owner"]).sum()


def prepare(project: ProjectData, as_of: date) -> tuple[pd.DataFrame, list[str]]:
    """Clean the raw tables and add every derived column the agents need. Returns (tasks_df, warnings)."""
    warnings: list[str] = []
    df = project.tasks.copy()
    for c in ["status", "dependencies", "priority", "component"]:
        if c not in df.columns:
            df[c] = ""
    for c in ["task_id", "name", "owner", "status", "dependencies", "priority", "component"]:
        df[c] = df[c].astype(str).str.strip()

    if df["task_id"].duplicated().any():
        dups = df.loc[df["task_id"].duplicated(), "task_id"].tolist()
        warnings.append(f"Duplicate task_id values dropped (kept first): {dups}")
        df = df.drop_duplicates("task_id", keep="first")

    for c in ["start_date", "due_date"]:
        df[c] = pd.to_datetime(df[c], errors="coerce").dt.normalize()
    bad = df[df["start_date"].isna() | df["due_date"].isna()]
    if len(bad):
        warnings.append(f"Tasks with unreadable dates dropped: {bad['task_id'].tolist()}")
        df = df.drop(bad.index)
    swapped = df["due_date"] < df["start_date"]
    if swapped.any():
        warnings.append(f"due_date earlier than start_date for: {df.loc[swapped, 'task_id'].tolist()} (dates swapped)")
        df.loc[swapped, ["start_date", "due_date"]] = df.loc[swapped, ["due_date", "start_date"]].values

    df["est_days"] = pd.to_numeric(df["est_days"], errors="coerce").fillna(1.0).clip(lower=0.5)
    df["progress"] = pd.to_numeric(df["progress"].str.replace("%", "", regex=False), errors="coerce").fillna(0).clip(0, 100)
    df["owner"] = df["owner"].replace("", "Unassigned")
    df["priority"] = df["priority"].replace("", "Medium").str.title()

    status = df["status"].str.lower()
    df["is_done"] = (df["progress"] >= 100) | status.isin(DONE_WORDS)
    df.loc[df["is_done"], "progress"] = 100.0
    df["status"] = "Not started"
    df.loc[(df["progress"] > 0) | status.isin(PROGRESS_WORDS), "status"] = "In progress"
    df.loc[df["is_done"], "status"] = "Done"
    df["in_progress"] = df["status"] == "In progress"

    # dependencies -> list of valid ids
    ids = set(df["task_id"])
    dep_lists = []
    for tid, raw in zip(df["task_id"], df["dependencies"]):
        deps = [d.strip() for d in re.split(r"[;,|]", raw) if d.strip()]
        unknown = [d for d in deps if d not in ids]
        if unknown:
            warnings.append(f"{tid} lists unknown dependencies {unknown} (ignored)")
        dep_lists.append([d for d in deps if d in ids and d != tid])
    df["deps"] = dep_lists
    df = df.set_index("task_id", drop=False)

    ts = pd.Timestamp(as_of)
    df["planned_days"] = ((df["due_date"] - df["start_date"]).dt.days).clip(lower=1)
    elapsed = ((ts - df["start_date"]).dt.days).clip(lower=0)
    elapsed = elapsed.where(elapsed < df["planned_days"], df["planned_days"])
    df["expected_progress"] = 100.0 * elapsed / df["planned_days"]
    df.loc[df["is_done"], "expected_progress"] = 100.0
    df["progress_gap"] = (df["expected_progress"] - df["progress"]).where(~df["is_done"], 0.0)
    df["days_to_due"] = (df["due_date"] - ts).dt.days
    df["days_overdue"] = (-df["days_to_due"]).clip(lower=0).where(~df["is_done"], 0)
    df["remaining_days"] = df["est_days"] * (1 - df["progress"] / 100.0)

    # priority weight
    df["priority_weight"] = df["priority"].str.lower().map(config.PRIORITY_WEIGHT).fillna(1.0)

    # issues
    df["open_issues"] = 0
    df["open_critical"] = 0
    iss = project.issues.copy()
    if len(iss):
        iss["status"] = iss["status"].astype(str).str.lower().str.strip()
        iss["severity"] = iss["severity"].astype(str).str.lower().str.strip()
        iss = iss[~iss["status"].isin(CLOSED_ISSUE)]
        total = iss.groupby("task_id").size()
        crit = iss[iss["severity"].isin(["critical", "high", "blocker", "major"])].groupby("task_id").size()
        df["open_issues"] = df["task_id"].map(total).fillna(0).astype(int)
        df["open_critical"] = df["task_id"].map(crit).fillna(0).astype(int)
        df.attrs["open_issue_ids"] = {t: g["issue_id"].tolist() for t, g in iss.groupby("task_id")}
    else:
        df.attrs["open_issue_ids"] = {}

    # git activity
    df["commits_14d"] = 0
    df["days_since_commit"] = 0.0
    df["has_git_data"] = False
    g = project.git.copy()
    if len(g):
        g["commits_14d"] = pd.to_numeric(g["commits_14d"], errors="coerce").fillna(0)
        g["last_commit_date"] = pd.to_datetime(g["last_commit_date"], errors="coerce")
        g = g.drop_duplicates("task_id", keep="last").set_index("task_id")
        df["commits_14d"] = df["task_id"].map(g["commits_14d"]).fillna(0).astype(int)
        last = df["task_id"].map(g["last_commit_date"])
        df["has_git_data"] = last.notna()
        df["days_since_commit"] = (ts - last).dt.days.fillna(0).clip(lower=0)

    # resources (team): capacity = how many concurrent tasks a person can comfortably handle
    cap, role = {}, {}
    res = project.resources
    if len(res) and "name" in res.columns:
        for _, rr in res.iterrows():
            nm = str(rr["name"]).strip()
            c = pd.to_numeric(rr.get("capacity", ""), errors="coerce")
            cap[nm] = float(c) if pd.notna(c) and c > 0 else float(config.OWNER_CAPACITY)
            role[nm] = str(rr.get("role", "")).strip()
        unknown = sorted(set(df["owner"]) - set(cap) - {"Unassigned"})
        if unknown:
            warnings.append(f"Task owners missing from resources file (default capacity {config.OWNER_CAPACITY} used): {unknown}")
    df["owner_capacity"] = df["owner"].map(cap).fillna(float(config.OWNER_CAPACITY))
    df["owner_role"] = df["owner"].map(role).fillna("")
    load = compute_owner_load(df, as_of)
    df["owner_load"] = df["owner"].map(load).fillna(0).astype(int)
    return df, warnings
