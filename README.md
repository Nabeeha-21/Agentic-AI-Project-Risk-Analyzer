# PROJEX — Agentic AI Project Risk Analyzer

Professional Training I · Sathyabama Institute of Science and Technology · CSE

An **AI Orchestrator** coordinates seven specialised agents (Risk, Dependency, Resource, Root Cause, Impact,
Simulation, Recommendation) that analyse project tasks, deadlines, dependencies, resources and progress, produce a
**Project Health Score**, explain *why* risks occur and *how* they affect the project, and let you test **what-if** changes
in a **React dashboard** (Health Score, Risk Heatmap, Gantt, Dependency Graph, Trends & Insights, Workload View, What-If Simulator).
It follows the architecture slide of your presentation box for box.

---

## 1. Setup

You need **Python 3.10+** (`python --version`). **Node.js is NOT needed** — the React dashboard is already built (`frontend/dist`).

### Windows
```bat
cd PROJEX
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python server.py
```
### macOS / Linux
```bash
cd PROJEX
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py
```
Open **http://localhost:8000** — the demo project is analysed automatically. Stop with `Ctrl+C`.

(If PowerShell blocks `activate`: `Set-ExecutionPolicy -Scope Process Bypass`.)

**No API key is needed.** By default PROJEX runs in *rule-based mode*: detection, prediction, simulation, ranking and
explanations all work; the explanations are templates built from computed evidence.

### Optional: LLM-written explanations
1. `copy .env.example .env` (Windows) / `cp .env.example .env`
2. Put **one** key in `.env`: `ANTHROPIC_API_KEY=...` (Claude) **or** `GOOGLE_API_KEY=...` + `PROJEX_LLM_PROVIDER=gemini` (also `pip install google-genai`).
3. Restart `python server.py`, tick **“LLM explanations”** in the dashboard header, press **Run analysis**.

The LLM only *writes* the explanation from evidence lines the code computed, so it cannot invent facts. If the key is
missing or a call fails, PROJEX falls back to rule-based text automatically.

### Optional: edit the React code
Only if you want to change the UI (needs Node 18+):
```bash
cd frontend
npm install
npm run build        # rebuilds frontend/dist   (or: npm run dev  to rebuild on every save)
```
Source is in `frontend/src` (`App.jsx`, `panels.jsx`, `charts.jsx`).

### Tests / evaluation / command line
```bash
pytest -q                 # 18 tests
python evaluate.py        # numbers for your Results slide
python run_cli.py --demo --report reports/report.md     # no browser needed
```

---

## 2. Using the dashboard

| Header control | What it does |
|---|---|
| **Data → Demo project** | Built-in “ShopEasy v2” project with planted risks (dates are generated around today) |
| **Data → Upload CSV files** | Choose `tasks.csv` (+ optional `resources.csv`, `issues.csv`, `git_activity.csv`). Sample files are linked right there; formats in `data/sample/README.txt` |
| **Data → Watched folder** | Reads the CSVs in `data/live/` (seeded with the demo on first run). Tick **Live monitoring** and edit a CSV in Excel — the dashboard re-analyses within ~3 s |
| **As of** | The analysis date. Move it forward and re-run to see the Trends tab build up (time passes, progress doesn’t → health falls) |
| **LLM explanations** | Use Claude/Gemini to write explanations (needs a key) |
| **⬇ Report** | Markdown risk report of the last analysis |

| Tab | Slide item |
|---|---|
| Overview | Health Score gauge, KPI cards, **Risk Heatmap** (likelihood × impact), insights, top risks, deadline forecast |
| Gantt | **Gantt chart** with progress, projected finish, overrun, critical path, today line |
| Dependency graph | **Dependency graph** with critical path highlighted |
| Workload | **Workload view**: load vs capacity per person, remaining work, their tasks |
| Risks & root cause | Ranked risks → root cause, contributing factors, **evidence**, **impact on the project** |
| What-If simulator | Custom scenarios (delay, add people, reassign, cut scope, scope creep, drop task, remove dependency) + standard scenarios |
| Recommendations | Ranked actions, each one **simulated** (chance of meeting the deadline before → after) |
| Trends & monitoring | **Trends & insights**: health / on-time / risk history, forecast, what changed since last run |
| Agents | Architecture, per-agent activity log and timings |

---

## 3. How the code maps to your architecture slide

```
Input layer ─▶ Processing layer ─▶ AI Orchestrator ─▶ Specialised AI agents ─▶ Intelligence layer ─▶ Dashboard
 (CSV files)    (clean/validate/      (orchestrator.py)   Risk · Dependency · Resource ·    (levels, health score,   (React)
                 feature extraction)                       Root Cause · Impact ·             predictions & trends,
                                                           Simulation · Recommendation       recommendations)
        ▲                                   Continuous monitoring & feedback (monitoring.py)                  │
        └───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

| Slide box | Code |
|---|---|
| Input layer: tasks, deadlines, dependencies, resources, progress | `projex/data_collection.py` (`load_csvs`; optional issues & git activity as extra signals) |
| Processing: data cleaning, validation, feature extraction | `data_collection.prepare()` (cleaning + validation warnings) and `processing.py` (graph, schedule, critical path) |
| **AI Orchestrator** | `projex/orchestrator.py` — runs everything in order over a shared `Context` “blackboard”, times each step, isolates failures |
| Risk Agent | `agents/risk_agent.py` — overdue, behind pace, late start, insufficient time, critical issues, issue backlog, stalled |
| Dependency Agent | `agents/dependency_agent.py` — started before prerequisites, cascading delays, bottlenecks, circular dependencies |
| Resource Agent | `agents/resource_agent.py` — overload vs per-person capacity, key-person dependency, unassigned work |
| Root Cause Agent | `agents/root_cause.py` — evidence from data + cause (rules or LLM) |
| Impact Agent | `agents/impact_agent.py` — “if this slips 5 more days…” → tasks pushed back, finish date, chance of meeting the deadline |
| Simulation Agent | `agents/simulation_agent.py` + `whatif.py` — standard scenarios; custom ones from the dashboard |
| Recommendation Agent | `agents/recommendation_agent.py` — candidate actions, each simulated and ranked by benefit ÷ effort |
| Risk levels & prioritisation / Predictions / **Project Health Score** | `projex/intelligence.py` |
| Trends & insights, continuous monitoring | `projex/monitoring.py` (SQLite history, diffs, trend forecast), `projex/insights.py` |
| Dashboard | `frontend/` (React) served by `server.py` (standard-library HTTP API, no extra packages) |

**Project Health Score** (0–100) = 30 % Schedule (chance of meeting the deadline + progress vs plan) + 20 % Risk exposure +
20 % Dependencies + 15 % Resources + 15 % Quality. Labels: ≥75 Healthy · 55–74 Watch · 35–54 At risk · <35 Critical.

**Risk score** = probability × impact × 100. Probability = ½ rule-based likelihood + ½ ML “will this task finish late?”
(logistic regression). Impact = downstream tasks, priority, critical path, projected slip.

---

## 4. Honest notes (say these in your viva)

* The ML model is trained on **synthetic history** (`intelligence.py → synthetic_history`) because no real project
  history was available. AUC ≈ 0.72 is a sanity check, not a real-world accuracy claim. To make it real, replace that
  function with a CSV of past tasks (same feature columns + a `late` 0/1 column).
* The what-if engine assumes work is divisible, an extra person adds ~60 % productivity, and each task above a person’s capacity adds 25 % to duration (all in `config.py`).
* Monte-Carlo uses a triangular distribution (0.85× / 1× / 1.5×+ of remaining work), wider for tasks with open critical bugs.
* Evaluated on a **demo project with planted risks**, not a real company project. Future scope (also in your abstract): Jira/GitHub API integration, learning from the organisation’s own history, automated optimisation, resource levelling.

## 5. Updating your slides

* **Results and Discussion** (currently empty): run `python server.py`, take screenshots of Overview, Gantt, Dependency graph, Workload, Risks, What-If result and Trends; add the numbers from `python evaluate.py`
  (e.g. *5/5 planted risks detected; chance of meeting the deadline 12 % → 21 % after rebalancing Ravi's workload; Health Score 32 → …*).
* **Module slide** can name the agents and files from the table above.
* Add one line to the Abstract/Conclusion: the Health Score is a weighted composite of five sub-scores, and the recommendations are validated by simulation.

## 6. Folder layout
```
PROJEX/
├── server.py              API + serves the dashboard   (python server.py)
├── run_cli.py             command-line version (+ --watch)
├── evaluate.py            numbers for the Results slide
├── projex/                orchestrator, processing, intelligence, monitoring, insights, whatif, graph, llm, serialize
│   └── agents/            risk, dependency, resource, root_cause, impact, simulation, recommendation
├── frontend/              React source (src/) + prebuilt dist/
├── data/sample/           sample CSVs (tasks, resources, issues, git_activity)
└── tests/                 18 tests
```
