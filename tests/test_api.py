"""API smoke tests (standard-library server). Run with:  pytest -q"""
import json
import os
import tempfile
import threading
import urllib.error
import urllib.request

import projex.config as config

config.DB_PATH = os.path.join(tempfile.mkdtemp(), "api_test.db")
import server  # noqa: E402

PORT = 8791
_srv = server.make_server(PORT)
threading.Thread(target=_srv.serve_forever, daemon=True).start()


def call(path, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def test_analyze_returns_everything_the_dashboard_needs():
    r = call("/api/analyze", {"source": "demo"})
    for key in ["project", "health", "tasks", "edges", "risks", "workload", "actions", "scenarios", "insights", "monte_carlo", "trace"]:
        assert key in r
    assert 0 <= r["health"]["score"] <= 100 and r["risks"] and r["tasks"]


def test_whatif_endpoint():
    call("/api/analyze", {"source": "demo", "record": False})
    w = call("/api/whatif", {"scenario": [{"type": "add_resource", "task_id": "T07", "count": 1}]})
    assert w["on_time_after"] >= w["on_time_before"]


def test_upload_requires_tasks_file():
    try:
        call("/api/analyze", {"source": "upload"})
        assert False, "should have failed"
    except urllib.error.HTTPError as e:
        assert e.code == 400
