import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { ActionsPanel, AgentsPanel, DependencyPanel, GanttPanel, Overview, RisksPanel, TrendsPanel, WhatIfPanel, WorkloadPanel } from "./panels";

const readFile = (file) => new Promise((resolve, reject) => {
  const r = new FileReader();
  r.onload = () => resolve(r.result);
  r.onerror = () => reject(new Error("Could not read " + file.name));
  r.readAsText(file);
});

export default function App() {
  const [cfg, setCfg] = useState(null);
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("overview");
  const [source, setSource] = useState("demo");
  const [asOf, setAsOf] = useState("");
  const [useLlm, setUseLlm] = useState(false);
  const [live, setLive] = useState(false);
  const [files, setFiles] = useState({});
  const [selectedRisk, setSelectedRisk] = useState(null);
  const [scenario, setScenario] = useState([]);
  const sig = useRef(null);

  const run = useCallback(async (overrides = {}) => {
    setBusy(true); setError("");
    try {
      const body = { source, as_of: asOf || undefined, use_llm: useLlm, record: true, ...overrides };
      if (body.source === "upload") {
        if (!files.tasks) throw new Error("Choose a tasks.csv file first (issues, git activity and resources are optional).");
        body.tasks_csv = await readFile(files.tasks);
        if (files.issues) body.issues_csv = await readFile(files.issues);
        if (files.git) body.git_csv = await readFile(files.git);
        if (files.resources) body.resources_csv = await readFile(files.resources);
      }
      const res = await api.analyze(body);
      setData(res);
      if (res.llm && res.llm.requested && !res.llm.available) setError(`LLM unavailable (${res.llm.error}) – using rule-based explanations.`);
    } catch (e) { setError(e.message); }
    setBusy(false);
  }, [source, asOf, useLlm, files]);

  // first load: read config, run the demo analysis
  useEffect(() => {
    api.config().then((c) => { setCfg(c); setAsOf(c.today); }).catch(() => {});
  }, []);
  useEffect(() => { if (cfg && !data && !busy) run({ as_of: cfg.today }); /* eslint-disable-next-line */ }, [cfg]);

  // continuous monitoring: poll the watched folder, re-analyse when a CSV changes
  useEffect(() => {
    if (!(live && source === "folder")) { sig.current = null; return undefined; }
    const id = setInterval(async () => {
      try {
        const { signature } = await api.signature();
        if (sig.current === null) { sig.current = signature; return; }
        if (signature !== sig.current) { sig.current = signature; run(); }
      } catch (e) { /* server restarting */ }
    }, 3000);
    return () => clearInterval(id);
  }, [live, source, run]);

  const openRisk = (id) => { setSelectedRisk(id); setTab("risks"); };
  const simulate = (sc) => { setScenario(sc); setTab("whatif"); };
  const nBad = data ? data.risks.filter((r) => r.level === "Critical" || r.level === "High").length : 0;
  const TABS = [["overview", "Overview"], ["gantt", "Gantt"], ["deps", "Dependency graph"], ["workload", "Workload"], ["risks", "Risks & root cause"],
    ["whatif", "What-If simulator"], ["actions", "Recommendations"], ["trends", "Trends & monitoring"], ["agents", "Agents"]];

  return (
    <div>
      <div className="header">
        <div className="logo">PROJEX<small>Agentic AI Project Risk Analyzer</small></div>
        {data && <div style={{ fontSize: 13 }}><b>{data.project.name}</b><div style={{ opacity: .8, fontSize: 12 }}>{data.project.tasks} tasks · deadline {data.project.deadline}</div></div>}
        <div className="spacer" />
        <div className="ctl">Data
          <select value={source} onChange={(e) => { setSource(e.target.value); setLive(false); }}>
            <option value="demo">Demo project</option><option value="folder">Watched folder ({cfg ? cfg.data_dir : "data/live"})</option><option value="upload">Upload CSV files</option>
          </select></div>
        <div className="ctl">As of <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} /></div>
        <label className="ctl" title={cfg && !cfg.llm_available ? `LLM unavailable: ${cfg.llm_error}` : "Let the LLM write explanations"}>
          <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} /> LLM explanations</label>
        <label className="ctl" title="Only for the watched folder: re-analyse automatically when you edit the CSV files">
          <input type="checkbox" disabled={source !== "folder"} checked={live} onChange={(e) => setLive(e.target.checked)} /> Live monitoring</label>
        <button className="btn" disabled={busy} onClick={() => run()}>{busy ? "Analysing…" : "▶ Run analysis"}</button>
        <a className="btn secondary small" href="/api/report" download="projex_risk_report.md" style={{ textDecoration: "none" }}>⬇ Report</a>
        {source === "upload" && (
          <div className="upload">
            {[["tasks", "tasks.csv *"], ["issues", "issues.csv"], ["git", "git_activity.csv"], ["resources", "resources.csv"]].map(([k, label]) => (
              <label key={k}>{label}: <input type="file" accept=".csv" onChange={(e) => setFiles({ ...files, [k]: e.target.files[0] })} /></label>))}
            <span>Samples: {["tasks", "issues", "git_activity", "resources"].map((f) => <a key={f} href={`/api/sample/${f}.csv`} style={{ marginRight: 8 }}>{f}.csv</a>)}</span>
          </div>
        )}
      </div>
      <div className="tabs">
        {TABS.map(([k, l]) => (
          <button key={k} className={`tab ${tab === k ? "active" : ""}`} onClick={() => setTab(k)}>
            {l}{k === "risks" && nBad > 0 && <span className="count">{nBad}</span>}</button>))}
      </div>
      <div className="main">
        {error && <div className={`banner ${error.startsWith("LLM") ? "warn" : "error"}`}>{error}</div>}
        {busy && !data && <div className="empty">Agents are analysing the project…</div>}
        {data && (
          <>
            {tab === "overview" && <Overview data={data} onOpenRisk={openRisk} />}
            {tab === "gantt" && <GanttPanel data={data} />}
            {tab === "deps" && <DependencyPanel data={data} />}
            {tab === "workload" && <WorkloadPanel data={data} />}
            {tab === "risks" && <RisksPanel data={data} selectedId={selectedRisk} setSelectedId={setSelectedRisk} />}
            {tab === "whatif" && <WhatIfPanel data={data} scenario={scenario} setScenario={setScenario} />}
            {tab === "actions" && <ActionsPanel data={data} onSimulate={simulate} />}
            {tab === "trends" && <TrendsPanel data={data} />}
            {tab === "agents" && <AgentsPanel data={data} />}
          </>
        )}
        <div className="footer-note">PROJEX · Professional Training I · Sathyabama Institute of Science and Technology · CSE</div>
      </div>
    </div>
  );
}
