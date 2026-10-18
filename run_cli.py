#!/usr/bin/env python3
"""Command-line PROJEX.  Examples:
    python run_cli.py --demo
    python run_cli.py --tasks data/sample/tasks.csv --issues data/sample/issues.csv --git data/sample/git_activity.csv --report reports/report.md
    python run_cli.py --demo --use-llm          # needs ANTHROPIC_API_KEY (or GOOGLE_API_KEY with PROJEX_LLM_PROVIDER=gemini)
    python run_cli.py --tasks my/tasks.csv --watch 30   # re-analyse every time the CSV files change (continuous monitoring)
"""
import argparse
import os
import time
from datetime import date, datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from projex.data_collection import ProjectData, load_csvs
from projex.llm import LLMClient
from projex.orchestrator import AIOrchestrator
from projex.report import build_markdown_report
from projex.sample_data import build_resources, build_sample


def load(args) -> ProjectData:
    if args.demo:
        t, i, g = build_sample(args.as_of)
        return ProjectData(tasks=t.astype(str), issues=i, git=g.astype(str), resources=build_resources().astype(str), name="ShopEasy v2 (demo)")
    if not args.tasks:
        raise SystemExit("Give --tasks FILE or use --demo")
    return load_csvs(args.tasks, args.issues, args.git, args.resources, name=args.name)


def show(ctx):
    s = ctx.summary
    print(f"\n=== PROJEX - {ctx.project_name} ({ctx.as_of}) ===")
    print(f"HEALTH SCORE {ctx.health['score']}/100 ({ctx.health['label']})")
    print(f"Progress {s['overall_progress']}% (expected {s['expected_progress']}%) | deadline {s['deadline']} | "
          f"projected {s['projected_finish']} ({s['deadline_slip_days']:+} d) | on-time chance {ctx.monte_carlo['on_time_prob'] * 100:.0f}%")
    print("\nTOP RISKS")
    for r in ctx.risks[:8]:
        print(f"  {r.risk_id} [{r.level:8s} {r.score:5.1f}] {r.task_id} {r.title}\n        why: {r.root_cause}")
    print("\nRECOMMENDED ACTIONS")
    for a in ctx.actions[:6]:
        print(f"  {a.action_id} {a.title} (effort {a.effort})\n        {a.rationale}")
    ch = ctx.changes
    if ch and not ch["first_run"]:
        print(f"\nCHANGES: new={ch['new']} resolved={ch['resolved']} escalated={ch['escalated']} improved={ch['improved']}")


def main():
    ap = argparse.ArgumentParser(description="PROJEX - Agentic AI Project Risk Analyzer")
    ap.add_argument("--demo", action="store_true", help="use the built-in demo project")
    ap.add_argument("--tasks"); ap.add_argument("--issues"); ap.add_argument("--git"); ap.add_argument("--resources")
    ap.add_argument("--name", default="My Project")
    ap.add_argument("--as-of", type=date.fromisoformat, default=None, help="analysis date YYYY-MM-DD (default today)")
    ap.add_argument("--use-llm", action="store_true", help="let the LLM write explanations (needs an API key)")
    ap.add_argument("--report", help="write a Markdown report to this path")
    ap.add_argument("--watch", type=int, default=0, help="re-run every N seconds when input files change")
    ap.add_argument("--no-record", action="store_true", help="do not store this run in the monitoring database")
    args = ap.parse_args()

    llm = LLMClient() if args.use_llm else None
    if llm and not llm.available:
        print(f"[LLM unavailable: {llm.error}] continuing with rule-based explanations")
    pipe = AIOrchestrator(llm=llm, record=not args.no_record)

    def run_once():
        ctx = pipe.run(load(args), args.as_of)
        show(ctx)
        if args.report:
            os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
            open(args.report, "w", encoding="utf-8").write(build_markdown_report(ctx))
            print(f"\nReport written to {args.report}")

    run_once()
    if args.watch and not args.demo:
        files = [f for f in (args.tasks, args.issues, args.git, args.resources) if f]
        stamp = lambda: tuple(os.path.getmtime(f) for f in files)
        last = stamp()
        print(f"\nWatching {files} every {args.watch}s - Ctrl+C to stop")
        while True:
            time.sleep(args.watch)
            if stamp() != last:
                last = stamp()
                print(f"\n[{datetime.now():%H:%M:%S}] change detected - re-analysing")
                run_once()


if __name__ == "__main__":
    main()
