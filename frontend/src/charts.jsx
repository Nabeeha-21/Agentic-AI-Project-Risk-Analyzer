import React, { useMemo, useState } from "react";

export const LEVEL_COLOR = { Critical: "#d9363e", High: "#f08c2e", Medium: "#e8b923", Low: "#3fa65b" };
export const NONE_COLOR = "#9aa7b5";
const HEALTH_COLOR = { Healthy: "#3fa65b", Watch: "#e8b923", "At risk": "#f08c2e", Critical: "#d9363e" };
export const levelColor = (l) => LEVEL_COLOR[l] || NONE_COLOR;
export const pct = (x, d = 0) => `${(x * 100).toFixed(d)}%`;
const DAY = 86400000;
const toDay = (s) => Math.round(new Date(s + "T00:00:00Z").getTime() / DAY);
const fmtDay = (d) => new Date(d * DAY).toISOString().slice(5, 10);

/* ------------------------------------------------------------------ Health score gauge */
export function HealthGauge({ health }) {
  const color = HEALTH_COLOR[health.label] || NONE_COLOR;
  return (
    <div>
      <svg viewBox="0 0 220 130" width="100%" style={{ maxWidth: 300, display: "block", margin: "0 auto" }}>
        <path d="M 20 110 A 90 90 0 0 1 200 110" fill="none" stroke="#e6ebf2" strokeWidth="18" strokeLinecap="round" pathLength="100" />
        <path d="M 20 110 A 90 90 0 0 1 200 110" fill="none" stroke={color} strokeWidth="18" strokeLinecap="round" pathLength="100"
              strokeDasharray={`${Math.max(health.score, 0.5)} 100`} />
        <text x="110" y="92" textAnchor="middle" fontSize="40" fontWeight="800" fill="#1c2733">{Math.round(health.score)}</text>
        <text x="110" y="112" textAnchor="middle" fontSize="13" fontWeight="700" fill={color}>{health.label.toUpperCase()}</text>
        <text x="20" y="127" fontSize="10" fill="#6b7a8c">0</text>
        <text x="200" y="127" fontSize="10" fill="#6b7a8c" textAnchor="end">100</text>
      </svg>
      <div style={{ marginTop: 10 }}>
        {health.components.map((c) => (
          <div key={c.name} style={{ marginBottom: 7 }}>
            <div className="row between" style={{ fontSize: 12 }}>
              <span>{c.name} <span className="muted">({Math.round(c.weight * 100)}%)</span></span>
              <b>{Math.round(c.score)}</b>
            </div>
            <div className="bar"><span style={{ width: `${c.score}%`, background: c.score >= 75 ? "#3fa65b" : c.score >= 55 ? "#e8b923" : c.score >= 35 ? "#f08c2e" : "#d9363e" }} /></div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ Risk heatmap (likelihood x impact) */
export function RiskHeatmap({ risks, onSelect }) {
  const cells = useMemo(() => {
    const grid = Array.from({ length: 5 }, () => Array.from({ length: 5 }, () => []));
    risks.forEach((r) => {
      const xi = Math.min(4, Math.floor(r.probability * 5));
      const yi = Math.min(4, Math.floor(r.impact * 5));
      grid[yi][xi].push(r);
    });
    return grid;
  }, [risks]);
  const zone = (xi, yi) => {
    const s = xi + yi;
    return s >= 7 ? "#f4b3b6" : s >= 5 ? "#f9d3a8" : s >= 3 ? "#fbefb0" : "#d4ecd9";
  };
  return (
    <div>
      <div className="heat">
        {[4, 3, 2, 1, 0].map((yi) => (
          <React.Fragment key={yi}>
            <div className="axis" style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}>{yi === 2 ? "IMPACT →" : ""}</div>
            {[0, 1, 2, 3, 4].map((xi) => {
              const rs = cells[yi][xi];
              return (
                <div key={xi} className="cell" style={{ background: zone(xi, yi) }}
                     title={rs.map((r) => `${r.id} ${r.task_id}: ${r.title}`).join("\n") || "no risks"}>
                  {rs.slice(0, 4).map((r) => (
                    <span key={r.id} className="chip" onClick={() => onSelect && onSelect(r.id)}>{r.id.replace("R0", "R")}</span>
                  ))}
                  {rs.length > 4 && <span className="chip">+{rs.length - 4}</span>}
                </div>
              );
            })}
          </React.Fragment>
        ))}
        <div />
        {["0–20%", "20–40%", "40–60%", "60–80%", "80–100%"].map((t) => <div key={t} className="axis">{t}</div>)}
      </div>
      <div className="sub" style={{ textAlign: "center" }}>LIKELIHOOD →  (click a risk chip to open it)</div>
    </div>
  );
}

/* ------------------------------------------------------------------ Gantt chart */
export function Gantt({ tasks, asOf, showDone, onSelect }) {
  const rows = useMemo(() => tasks.filter((t) => showDone || !t.is_done).sort((a, b) => a.start.localeCompare(b.start) || a.id.localeCompare(b.id)), [tasks, showDone]);
  if (!rows.length) return <div className="empty">No tasks to show.</div>;
  const LEFT = 230, RIGHT = 30, TOP = 34, RH = 28;
  const W = 1200, plotW = W - LEFT - RIGHT, H = TOP + rows.length * RH + 20;
  const today = toDay(asOf);
  const starts = rows.map((r) => toDay(r.start));
  const ends = rows.map((r) => Math.max(toDay(r.due), r.projected_finish ? toDay(r.projected_finish) : 0));
  const min = Math.min(...starts, today) - 2, max = Math.max(...ends, today) + 3;
  const x = (d) => LEFT + ((d - min) / (max - min)) * plotW;
  const ticks = [];
  for (let d = Math.ceil(min / 7) * 7; d <= max; d += 7) ticks.push(d);
  return (
    <div className="scroll-x">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ minWidth: 900 }}>
        {ticks.map((d) => (
          <g key={d}>
            <line x1={x(d)} x2={x(d)} y1={TOP - 6} y2={H - 14} stroke="#e8edf4" />
            <text x={x(d)} y={TOP - 12} fontSize="10" textAnchor="middle" fill="#6b7a8c">{fmtDay(d)}</text>
          </g>
        ))}
        {rows.map((t, i) => {
          const y = TOP + i * RH;
          const s = toDay(t.start), e = toDay(t.due);
          const color = t.is_done ? "#b4bfcc" : levelColor(t.level);
          const w = Math.max(x(e) - x(s), 4);
          const pf = t.projected_finish ? toDay(t.projected_finish) : null;
          return (
            <g key={t.id} style={{ cursor: "pointer" }} onClick={() => onSelect && onSelect(t)}>
              {i % 2 === 0 && <rect x="0" y={y - 2} width={W} height={RH} fill="#f8fafc" />}
              {t.on_critical_path && <rect x="0" y={y - 2} width="4" height={RH} fill="#d9363e" />}
              <text x="10" y={y + 15} fontSize="11" fill="#1c2733" fontWeight={t.on_critical_path ? 700 : 400}>
                {t.id} {t.name.length > 28 ? t.name.slice(0, 27) + "…" : t.name}
              </text>
              <rect x={x(s)} y={y + 3} width={w} height={14} rx="4" fill={color} opacity="0.25" stroke={color} />
              <rect x={x(s)} y={y + 3} width={(w * t.progress) / 100} height={14} rx="4" fill={color} />
              {pf !== null && pf > e && <rect x={x(e)} y={y + 8} width={x(pf) - x(e)} height={4} fill="#d9363e" opacity="0.7" />}
              {pf !== null && <path d={`M ${x(pf)} ${y + 1} l 5 9 l -5 9 l -5 -9 z`} fill="#1c2733" />}
              <title>{`${t.id} ${t.name}\nOwner: ${t.owner}\nProgress ${t.progress}% (expected ${t.expected_progress}%)\nDue ${t.due}${pf !== null ? `\nProjected finish ${t.projected_finish} (slip ${t.slip} d)` : ""}`}</title>
            </g>
          );
        })}
        <line x1={x(today)} x2={x(today)} y1={TOP - 8} y2={H - 12} stroke="#2f6fb3" strokeWidth="2" strokeDasharray="5 4" />
        <text x={x(today)} y={H - 2} fontSize="10" textAnchor="middle" fill="#2f6fb3" fontWeight="700">today</text>
      </svg>
      <div className="legend">
        {Object.entries(LEVEL_COLOR).map(([k, c]) => <span key={k}><i style={{ background: c }} />{k} risk</span>)}
        <span><i style={{ background: "#b4bfcc" }} />Done / no risk</span>
        <span><i style={{ background: "#1c2733", transform: "rotate(45deg)" }} />Projected finish</span>
        <span><i style={{ background: "#d9363e", height: 4, verticalAlign: 3 }} />Projected overrun</span>
        <span><i style={{ background: "#d9363e", width: 4 }} />Critical path</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ Dependency graph */
export function DependencyGraph({ tasks, edges, criticalEdges, onSelect, selected }) {
  const layout = useMemo(() => {
    const byId = Object.fromEntries(tasks.map((t) => [t.id, t]));
    const layer = {};
    const depth = (id, seen = new Set()) => {
      if (layer[id] !== undefined) return layer[id];
      if (seen.has(id)) return 0;
      seen.add(id);
      const deps = (byId[id].deps || []).filter((d) => byId[d]);
      layer[id] = deps.length ? 1 + Math.max(...deps.map((d) => depth(d, seen))) : 0;
      return layer[id];
    };
    tasks.forEach((t) => depth(t.id));
    const L = Math.max(...Object.values(layer)) + 1;
    const cols = Array.from({ length: L }, () => []);
    tasks.forEach((t) => cols[layer[t.id]].push(t.id));
    const pos = {};
    cols.forEach((c, ci) => {
      c.sort((a, b) => {
        const bary = (id) => {
          const ds = (byId[id].deps || []).filter((d) => pos[d] !== undefined);
          return ds.length ? ds.reduce((s, d) => s + pos[d], 0) / ds.length : 1e6;
        };
        return bary(a) - bary(b) || a.localeCompare(b);
      });
      c.forEach((id, i) => { pos[id] = i; });
    });
    const NW = 142, NH = 44, GX = 58, GY = 14;
    const maxRows = Math.max(...cols.map((c) => c.length));
    const nodes = {};
    cols.forEach((c, ci) => {
      const offset = ((maxRows - c.length) * (NH + GY)) / 2;
      c.forEach((id, i) => { nodes[id] = { x: 20 + ci * (NW + GX), y: 20 + offset + i * (NH + GY) }; });
    });
    return { nodes, NW, NH, W: 40 + L * (NW + GX), H: 40 + maxRows * (NH + GY) };
  }, [tasks]);
  const crit = new Set(criticalEdges.map((e) => `${e.from}>${e.to}`));
  const byId = Object.fromEntries(tasks.map((t) => [t.id, t]));
  const { nodes, NW, NH, W, H } = layout;
  return (
    <div className="scroll-x">
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H}>
        <defs>
          <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="#8795a8" /></marker>
          <marker id="arrc" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="#d9363e" /></marker>
        </defs>
        {edges.map((e, i) => {
          const a = nodes[e.from], b = nodes[e.to];
          if (!a || !b) return null;
          const c = crit.has(`${e.from}>${e.to}`);
          const x1 = a.x + NW, y1 = a.y + NH / 2, x2 = b.x, y2 = b.y + NH / 2, mx = (x1 + x2) / 2;
          const dim = selected && selected !== e.from && selected !== e.to;
          return <path key={i} d={`M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2 - 2} ${y2}`} fill="none" stroke={c ? "#d9363e" : "#a9b4c3"}
                       strokeWidth={c ? 2.6 : 1.3} opacity={dim ? 0.15 : 1} markerEnd={`url(#${c ? "arrc" : "arr"})`} />;
        })}
        {tasks.map((t) => {
          const n = nodes[t.id];
          const color = t.is_done ? "#b4bfcc" : levelColor(t.level);
          return (
            <g key={t.id} transform={`translate(${n.x},${n.y})`} style={{ cursor: "pointer" }} onClick={() => onSelect(t.id)}>
              <rect width={NW} height={NH} rx="8" fill={t.is_done ? "#eef1f5" : "#fff"} stroke={t.on_critical_path ? "#d9363e" : color} strokeWidth={selected === t.id ? 3.5 : t.on_critical_path ? 2.2 : 1.4} />
              <rect width="6" height={NH} rx="3" fill={color} />
              <text x="14" y="17" fontSize="11" fontWeight="700" fill="#1c2733">{t.id} · {Math.round(t.progress)}%</text>
              <text x="14" y="33" fontSize="10" fill="#4b5a6c">{t.name.length > 21 ? t.name.slice(0, 20) + "…" : t.name}</text>
              <title>{`${t.id} ${t.name}\nOwner ${t.owner}\nBlocks ${t.downstream} task(s)`}</title>
            </g>
          );
        })}
      </svg>
      <div className="legend">
        <span><i style={{ background: "#d9363e" }} />Critical path</span>
        {Object.entries(LEVEL_COLOR).map(([k, c]) => <span key={k}><i style={{ background: c }} />{k}</span>)}
        <span><i style={{ background: "#b4bfcc" }} />Done / no risk</span>
        <span>Arrows point from a prerequisite to the task that waits for it. Click a node to highlight its links.</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ Workload view */
export function WorkloadView({ workload }) {
  const maxLoad = Math.max(...workload.map((w) => Math.max(w.load, w.capacity)), 1);
  return (
    <div className="grid g2">
      {workload.map((w) => (
        <div className="card" key={w.owner} style={w.overloaded ? { borderColor: "#d9363e" } : null}>
          <div className="row between">
            <div><h3 style={{ marginBottom: 0 }}>{w.owner}</h3><div className="muted" style={{ fontSize: 12 }}>{w.role || "Team member"}</div></div>
            <div style={{ textAlign: "right" }}>
              <b style={{ fontSize: 22 }} className={w.overloaded ? "bad" : ""}>{w.load}</b><span className="muted"> / {w.capacity} tasks</span>
              {w.overloaded && <div className="bad" style={{ fontSize: 11, fontWeight: 700 }}>OVERLOADED</div>}
            </div>
          </div>
          <div style={{ position: "relative", margin: "12px 0 4px" }}>
            <div className="bar" style={{ height: 12 }}><span style={{ width: `${(w.load / maxLoad) * 100}%`, background: w.overloaded ? "#d9363e" : "#2f6fb3" }} /></div>
            <div title={`capacity ${w.capacity}`} style={{ position: "absolute", left: `${(w.capacity / maxLoad) * 100}%`, top: -3, height: 18, width: 2, background: "#1c2733" }} />
          </div>
          <div className="sub" style={{ marginTop: 0 }}>Remaining work: <b>{w.remaining_days}</b> person-days · black line = comfortable capacity</div>
          <div style={{ marginTop: 10 }}>
            {w.tasks.length === 0 && <span className="muted">No open tasks.</span>}
            {w.tasks.map((t) => (
              <span key={t.id} className={`chip ${t.level || ""}`} title={`${t.name} (${t.status}, ${Math.round(t.progress)}%)`}>
                {t.on_critical_path ? "★ " : ""}{t.id} {t.name.length > 18 ? t.name.slice(0, 17) + "…" : t.name}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ Line chart (trends) */
export function LineChart({ title, labels, series, yMin = 0, yMax = 100, fmt = (v) => v.toFixed(0), forecast }) {
  const W = 460, H = 210, L = 42, R = 14, T = 16, B = 34;
  const n = Math.max(labels.length + (forecast !== undefined ? 1 : 0), 2);
  const x = (i) => L + (i / (n - 1)) * (W - L - R);
  const y = (v) => T + (1 - (v - yMin) / (yMax - yMin || 1)) * (H - T - B);
  const grid = [0, 0.25, 0.5, 0.75, 1].map((f) => yMin + f * (yMax - yMin));
  return (
    <div>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{title}</div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%">
        {grid.map((g) => (
          <g key={g}><line x1={L} x2={W - R} y1={y(g)} y2={y(g)} stroke="#e8edf4" /><text x={L - 6} y={y(g) + 3} fontSize="10" textAnchor="end" fill="#6b7a8c">{fmt(g)}</text></g>
        ))}
        {labels.map((lb, i) => <text key={i} x={x(i)} y={H - 16} fontSize="10" textAnchor="middle" fill="#6b7a8c">{lb}</text>)}
        {forecast !== undefined && <text x={x(labels.length)} y={H - 16} fontSize="10" textAnchor="middle" fill="#6b7a8c">next</text>}
        {series.map((s) => (
          <g key={s.name}>
            <polyline fill="none" stroke={s.color} strokeWidth="2.5" points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ")} />
            {s.values.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r="4" fill={s.color}><title>{`${s.name}: ${fmt(v)}`}</title></circle>)}
            {forecast !== undefined && s.forecastable && s.values.length > 0 && (
              <g>
                <line x1={x(s.values.length - 1)} y1={y(s.values[s.values.length - 1])} x2={x(labels.length)} y2={y(forecast)} stroke={s.color} strokeDasharray="5 4" strokeWidth="2" />
                <circle cx={x(labels.length)} cy={y(forecast)} r="4" fill="#fff" stroke={s.color} strokeWidth="2"><title>{`forecast: ${fmt(forecast)}`}</title></circle>
              </g>
            )}
          </g>
        ))}
      </svg>
    </div>
  );
}

/* ------------------------------------------------------------------ Monte-Carlo histogram */
export function Histogram({ before, after, asOf }) {
  const W = 460, H = 220, L = 14, R = 14, T = 14, B = 34;
  const bins = before.histogram;
  const all = [...bins, ...(after ? after.histogram : [])];
  const lo = Math.min(...all.map((b) => b.x0), before.deadline_offset), hi = Math.max(...all.map((b) => b.x1), before.deadline_offset);
  const maxC = Math.max(...all.map((b) => b.count), 1);
  const x = (v) => L + ((v - lo) / (hi - lo || 1)) * (W - L - R);
  const y = (c) => T + (1 - c / maxC) * (H - T - B);
  const base = toDay(asOf);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => lo + f * (hi - lo));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%">
      {bins.map((b, i) => <rect key={i} x={x(b.x0)} y={y(b.count)} width={Math.max(x(b.x1) - x(b.x0) - 1, 1)} height={H - B - y(b.count)} fill={after ? "#9bb7d8" : "#4c78a8"} />)}
      {after && after.histogram.map((b, i) => <rect key={i} x={x(b.x0)} y={y(b.count)} width={Math.max(x(b.x1) - x(b.x0) - 1, 1)} height={H - B - y(b.count)} fill="#f08c2e" opacity="0.55" />)}
      <line x1={x(before.deadline_offset)} x2={x(before.deadline_offset)} y1={T} y2={H - B} stroke="#d9363e" strokeWidth="3" />
      <text x={x(before.deadline_offset) + (before.deadline_offset > (lo + hi) / 2 ? -6 : 6)} y={T + 9} fontSize="10" fill="#d9363e" fontWeight="700" textAnchor={before.deadline_offset > (lo + hi) / 2 ? "end" : "start"}>deadline</text>
      <line x1={L} x2={W - R} y1={H - B} y2={H - B} stroke="#9aa7b5" />
      {ticks.map((t) => <text key={t} x={x(t)} y={H - 18} fontSize="10" textAnchor="middle" fill="#6b7a8c">{fmtDay(base + Math.round(t))}</text>)}
      <text x={W / 2} y={H - 4} fontSize="10" textAnchor="middle" fill="#6b7a8c">simulated project finish date</text>
    </svg>
  );
}
