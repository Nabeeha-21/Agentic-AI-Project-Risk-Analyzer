#!/usr/bin/env python3
"""PROJEX server - JSON API + the React dashboard (no extra dependencies, standard library only).

    python server.py                 # http://localhost:8000
    python server.py --port 9000 --data-dir data/live

Endpoints
  GET  /api/config            capabilities (LLM, data folder)
  POST /api/analyze           run the AI Orchestrator  {source: demo|folder|upload, as_of, use_llm, record, *_csv}
  POST /api/whatif            simulate a custom scenario against the last analysis
  GET  /api/history           stored analysis runs (Trends & Insights)
  GET  /api/report            Markdown risk report of the last analysis
  GET  /api/signature         change-detector for the watched folder (continuous monitoring)
  GET  /api/sample/<file>.csv sample CSV templates
"""
import argparse
import io
import json
import mimetypes
import os
import shutil
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from projex import config
from projex.data_collection import ProjectData, load_csvs
from projex.graph import build_graph
from projex.llm import LLMClient
from projex.monitoring import history
from projex.orchestrator import AIOrchestrator
from projex.report import build_markdown_report
from projex.sample_data import build_resources, build_sample, write_sample_csvs
from projex.serialize import _j, context_to_dict, mc_to_dict
from projex.whatif import describe, monte_carlo, simulate

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "frontend", "dist")
CSV_FILES = ["tasks.csv", "issues.csv", "git_activity.csv", "resources.csv"]

STATE = {"ctx": None, "lock": threading.Lock(), "data_dir": os.path.join(ROOT, "data", "live")}


def ensure_live_folder():
    d = STATE["data_dir"]
    if not os.path.exists(os.path.join(d, "tasks.csv")):
        write_sample_csvs(d)                       # first run: seed the watched folder with the demo project


def folder_signature() -> str:
    d = STATE["data_dir"]
    return "|".join(f"{f}:{os.path.getmtime(os.path.join(d, f)):.3f}" for f in CSV_FILES if os.path.exists(os.path.join(d, f)))


def load_project(body: dict) -> ProjectData:
    source = body.get("source", "demo")
    if source == "demo":
        t, i, g = build_sample(date.today())
        return ProjectData(tasks=t.astype(str), issues=i, git=g.astype(str), resources=build_resources().astype(str), name="ShopEasy v2 (demo)")
    if source == "folder":
        ensure_live_folder()
        d = STATE["data_dir"]
        pick = lambda f: os.path.join(d, f) if os.path.exists(os.path.join(d, f)) else None
        return load_csvs(pick("tasks.csv"), pick("issues.csv"), pick("git_activity.csv"), pick("resources.csv"),
                         name=f"Folder: {os.path.basename(d)}")
    if source == "upload":
        if not body.get("tasks_csv"):
            raise ValueError("Upload at least a tasks.csv file.")
        wrap = lambda k: io.StringIO(body[k]) if body.get(k) else None
        return load_csvs(wrap("tasks_csv"), wrap("issues_csv"), wrap("git_csv"), wrap("resources_csv"), name="Uploaded project")
    raise ValueError(f"Unknown source: {source}")


def analyze(body: dict) -> dict:
    as_of = date.fromisoformat(body["as_of"]) if body.get("as_of") else date.today()
    llm = LLMClient() if body.get("use_llm") else None
    project = load_project(body)
    ctx = AIOrchestrator(llm=llm, record=bool(body.get("record", True))).run(project, as_of)
    with STATE["lock"]:
        STATE["ctx"] = ctx
    out = context_to_dict(ctx, history(ctx.project_name))
    out["llm"] = {"requested": bool(llm), "available": bool(llm and llm.available), "error": (llm.error if llm and not llm.available else None)}
    return out


def whatif(body: dict) -> dict:
    ctx = STATE["ctx"]
    if ctx is None:
        raise ValueError("Run an analysis first.")
    scenario = body.get("scenario") or []
    if not scenario:
        raise ValueError("Scenario is empty.")
    sim = simulate(ctx.tasks, ctx.as_of, scenario)
    mc1 = monte_carlo(ctx.tasks, ctx.graph, ctx.as_of, n=1500)
    mc2 = monte_carlo(sim["tasks_after"], build_graph(sim["tasks_after"]), ctx.as_of, n=1500)
    return _j({
        "scenario_text": sim["scenario_text"], "baseline_finish": sim["baseline"].project_finish,
        "new_finish": sim["scenario"].project_finish, "project_shift_days": sim["project_shift_days"],
        "deadline_slip_before": sim["deadline_slip_before"], "deadline_slip_after": sim["deadline_slip_after"],
        "on_time_before": mc1["on_time_prob"], "on_time_after": mc2["on_time_prob"],
        "p80_before": mc1["p80"], "p80_after": mc2["p80"],
        "changed_tasks": sim["changed_tasks"], "mc_before": mc_to_dict(mc1), "mc_after": mc_to_dict(mc2),
    })


class Handler(BaseHTTPRequestHandler):
    server_version = "PROJEX/1.0"

    def log_message(self, fmt, *args):
        pass                                           # keep the console quiet

    # ---- helpers
    def _send(self, code: int, payload, ctype="application/json"):
        data = payload if isinstance(payload, (bytes, bytearray)) else (
            payload.encode("utf-8") if isinstance(payload, str) else json.dumps(payload).encode("utf-8"))
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") or ctype == "application/json" else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _static(self, path: str):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        full = os.path.normpath(os.path.join(DIST, rel))
        if not full.startswith(DIST) or not os.path.isfile(full):
            full = os.path.join(DIST, "index.html")
        if not os.path.isfile(full):
            return self._send(200, "<h2>PROJEX API is running.</h2><p>The dashboard is not built yet: run "
                                   "<code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code>, then refresh.</p>", "text/html")
        with open(full, "rb") as f:
            self._send(200, f.read(), mimetypes.guess_type(full)[0] or "application/octet-stream")

    # ---- routes
    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/config":
                llm = LLMClient()
                return self._send(200, {"llm_available": llm.available, "llm_provider": llm.provider, "llm_error": llm.error,
                                        "data_dir": os.path.relpath(STATE["data_dir"], ROOT), "today": date.today().isoformat(),
                                        "model": config.ANTHROPIC_MODEL if llm.provider == "anthropic" else config.GEMINI_MODEL})
            if path == "/api/signature":
                ensure_live_folder()
                return self._send(200, {"signature": folder_signature()})
            if path == "/api/history":
                ctx = STATE["ctx"]
                return self._send(200, _j(history(ctx.project_name).to_dict(orient="records")) if ctx else [])
            if path == "/api/report":
                ctx = STATE["ctx"]
                if not ctx:
                    return self._send(404, {"error": "Run an analysis first."})
                return self._send(200, build_markdown_report(ctx), "text/markdown")
            if path.startswith("/api/sample/"):
                name = path.rsplit("/", 1)[1]
                t, i, g = build_sample(date.today())
                frames = {"tasks.csv": t, "issues.csv": i, "git_activity.csv": g, "resources.csv": build_resources()}
                if name not in frames:
                    return self._send(404, {"error": "unknown sample file"})
                self.send_response(200)
                data = frames[name].to_csv(index=False).encode()
                self.send_header("Content-Type", "text/csv")
                self.send_header("Content-Disposition", f'attachment; filename="{name}"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                return self.wfile.write(data)
            if path.startswith("/api/"):
                return self._send(404, {"error": "not found"})
            return self._static(path)
        except Exception as e:
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self._body()
            if path == "/api/analyze":
                return self._send(200, analyze(body))
            if path == "/api/whatif":
                return self._send(200, whatif(body))
            self._send(404, {"error": "not found"})
        except ValueError as e:
            self._send(400, {"error": str(e)})
        except Exception as e:
            self._send(500, {"error": f"{type(e).__name__}: {e}"})


def make_server(port: int = 8000, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="PROJEX server")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--data-dir", default=STATE["data_dir"], help="folder watched for continuous monitoring (tasks.csv, issues.csv, git_activity.csv, resources.csv)")
    a = ap.parse_args()
    STATE["data_dir"] = os.path.abspath(a.data_dir)
    ensure_live_folder()
    print(f"PROJEX running on http://{a.host}:{a.port}   (watching {STATE['data_dir']})  - Ctrl+C to stop")
    if not os.path.isdir(DIST):
        print("Note: frontend/dist not found - API only. Build the dashboard (see README).")
    try:
        make_server(a.port, a.host).serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
