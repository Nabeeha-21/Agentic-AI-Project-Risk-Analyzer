"""Built-in demo project ("ShopEasy v2" e-commerce platform) with deliberately planted risks.

Dates are generated relative to `as_of` so the demo always looks 'live'.
Planted risks (so you can check detection accuracy):
  T07  Payment gateway: overdue, 40% done, blocks many tasks         -> schedule / bottleneck
  T10  Cart service: started before its blocker T07 is finished      -> dependency
  T12  Order service: stalled, no commits for 15 days                -> technical / stalled
  T15  Search: several open critical bugs                            -> quality / technical
  Ravi: 5 concurrent tasks (capacity is 3)                           -> resource
Run:  python -m projex.sample_data   (writes CSVs into data/sample/)
"""
from __future__ import annotations
from datetime import date, timedelta
import os
import pandas as pd

# id, name, owner, start_off, due_off, est_days, progress, deps, priority, component
_TASKS = [
    ("T01", "Requirements & scope", "Anita", -60, -45, 10, 100, "", "High", "Planning"),
    ("T02", "System design", "Karthik", -45, -30, 12, 100, "T01", "High", "Design"),
    ("T03", "Database schema", "Meena", -40, -28, 8, 100, "T02", "Medium", "Backend"),
    ("T04", "UI/UX wireframes", "Divya", -42, -25, 10, 100, "T01", "Medium", "Frontend"),
    ("T05", "Auth & user service", "Ravi", -28, -10, 12, 100, "T03", "High", "Backend"),
    ("T06", "Product catalog API", "Meena", -28, -8, 13, 100, "T03", "High", "Backend"),
    ("T07", "Payment gateway integration", "Ravi", -25, -5, 14, 40, "T05", "Critical", "Backend"),
    ("T08", "Frontend component library", "Divya", -26, -6, 12, 100, "T04", "Medium", "Frontend"),
    ("T09", "Product listing pages", "Divya", -15, 3, 10, 70, "T06;T08", "Medium", "Frontend"),
    ("T10", "Shopping cart service", "Ravi", -10, 6, 9, 35, "T05;T07", "High", "Backend"),
    ("T11", "Checkout flow UI", "Divya", -5, 10, 8, 15, "T09;T10", "High", "Frontend"),
    ("T12", "Order management service", "Ravi", -8, 8, 10, 30, "T03;T07", "High", "Backend"),
    ("T13", "Inventory sync", "Suresh", -12, 4, 8, 60, "T06", "Medium", "Backend"),
    ("T14", "Notification service", "Ravi", 0, 12, 7, 0, "T12", "Medium", "Backend"),
    ("T15", "Search & recommendations", "Karthik", -14, 5, 12, 55, "T06", "High", "Backend"),
    ("T16", "Admin dashboard", "Anita", -4, 14, 9, 25, "T05;T06", "Medium", "Frontend"),
    ("T17", "Security hardening", "Suresh", 2, 16, 6, 0, "T07;T10", "High", "Security"),
    ("T18", "Performance optimisation", "Karthik", 5, 18, 6, 0, "T15;T13", "Medium", "Backend"),
    ("T19", "Integration testing", "Meena", 8, 22, 8, 0, "T11;T12;T14", "High", "QA"),
    ("T20", "User acceptance testing", "Anita", 30, 41, 5, 0, "T19;T16", "High", "QA"),
    ("T21", "Documentation", "Divya", 10, 28, 6, 0, "T09", "Medium", "Docs"),
    ("T22", "CI/CD pipeline", "Suresh", -10, 10, 7, 40, "T05", "Medium", "DevOps"),
    ("T23", "Staging deployment", "Suresh", 18, 24, 3, 0, "T22;T18;T17", "Medium", "DevOps"),
    ("T24", "Go-live & handover", "Anita", 41, 44, 3, 0, "T20;T23", "Critical", "Release"),
    ("T25", "Coupons & discounts", "Ravi", -3, 14, 8, 10, "T05", "Medium", "Backend"),
]

# issue_id, task_id, severity, status, title
_ISSUES = [
    ("I-001", "T15", "Critical", "Open", "Search returns wrong results for multi-word queries"),
    ("I-002", "T15", "Critical", "Open", "Index rebuild crashes on large catalogue"),
    ("I-003", "T15", "High", "Open", "Recommendation latency > 5s"),
    ("I-004", "T15", "Medium", "Open", "Stale cache after product update"),
    ("I-005", "T15", "Medium", "Open", "Typo tolerance disabled"),
    ("I-006", "T07", "High", "Open", "Gateway sandbox returns intermittent 502"),
    ("I-007", "T10", "High", "Open", "Cart totals wrong when coupons applied"),
    ("I-008", "T10", "Medium", "Open", "Cart not persisted across sessions"),
    ("I-009", "T09", "Low", "Open", "Image lazy-loading flicker"),
    ("I-010", "T12", "Medium", "Closed", "Order status enum mismatch"),
    ("I-011", "T13", "Medium", "Open", "Sync job skips deleted products"),
    ("I-012", "T22", "Low", "Open", "Pipeline cache misses on Windows runner"),
]

# task_id, commits_14d, last_commit_offset
_GIT = [
    ("T07", 12, -1), ("T09", 20, -1), ("T10", 5, -3), ("T11", 6, -1), ("T12", 0, -15),
    ("T13", 9, -2), ("T15", 14, -1), ("T16", 4, -2), ("T22", 7, -3), ("T25", 2, -6),
]


_RESOURCES = [("Anita", "Project Manager / QA", 4), ("Karthik", "Tech Lead", 3), ("Meena", "Backend Developer", 3),
              ("Divya", "Frontend Developer", 3), ("Ravi", "Backend Developer", 3), ("Suresh", "DevOps Engineer", 3)]


def build_sample(as_of: date | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """`as_of` is the ANCHOR date the demo is built around (default: today)."""
    as_of = as_of or date.today()
    d = lambda off: (as_of + timedelta(days=off)).isoformat()
    tasks = pd.DataFrame(
        [(t, n, o, d(s), d(e), est, pr, dep, pri, comp) for t, n, o, s, e, est, pr, dep, pri, comp in _TASKS],
        columns=["task_id", "name", "owner", "start_date", "due_date", "est_days", "progress", "dependencies", "priority", "component"],
    )
    issues = pd.DataFrame(_ISSUES, columns=["issue_id", "task_id", "severity", "status", "title"])
    git = pd.DataFrame([(t, c, d(off)) for t, c, off in _GIT], columns=["task_id", "commits_14d", "last_commit_date"])
    return tasks, issues, git


PLANTED_RISKS = {  # used by the tests / evaluation to measure detection recall
    ("T07", "overdue"), ("T10", "dependency_violation"), ("T12", "stalled"),
    ("T15", "critical_issues"), ("T07", "owner_overload"),
}


def build_resources() -> pd.DataFrame:
    return pd.DataFrame(_RESOURCES, columns=["name", "role", "capacity"])


def write_sample_csvs(folder: str, as_of: date | None = None) -> None:
    os.makedirs(folder, exist_ok=True)
    tasks, issues, git = build_sample(as_of)
    tasks.to_csv(os.path.join(folder, "tasks.csv"), index=False)
    issues.to_csv(os.path.join(folder, "issues.csv"), index=False)
    git.to_csv(os.path.join(folder, "git_activity.csv"), index=False)
    build_resources().to_csv(os.path.join(folder, "resources.csv"), index=False)


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sample")
    write_sample_csvs(out)
    print("Sample CSVs written to", out)
