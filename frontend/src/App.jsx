import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import {
  Search, RefreshCw, Activity, Terminal, Layers,
  Settings, Database, Zap, AlertTriangle, Info,
  Bug, Play, X, RotateCcw, ChevronDown, Clock,
  FileText,
} from 'lucide-react';
import { api } from './api';
import './App.css';

// ─── Constants ────────────────────────────────────────────────────────────────

const SEV_COLOR = {
  ERROR: '#EF4444',
  WARN:  '#F5A623',
  WARNING: '#F5A623',
  INFO:  '#22C55E',
  DEBUG: '#A78BFA',
  TRACE: '#38BDF8',
};
const SEV_ICON = {
  ERROR: <AlertTriangle size={11}/>,
  WARN:  <Zap size={11}/>,
  WARNING: <Zap size={11}/>,
  INFO:  <Info size={11}/>,
  DEBUG: <Bug size={11}/>,
  TRACE: <ChevronDown size={11}/>,
};
const DORIS_BLUE = '#1B4AEF';
const DORIS_ACCENT = '#4D7CFE';

const PRESETS = [
  { label: '15m', minutes: 15 },
  { label: '1h',  minutes: 60 },
  { label: '6h',  minutes: 360 },
  { label: '24h', minutes: 1440 },
  { label: '48h', minutes: 2880 },
];

const isoNow   = () => new Date().toISOString();
const isoMinus = (m) => new Date(Date.now() - m * 60000).toISOString();

// ─── Small shared components ──────────────────────────────────────────────────

function SevBadge({ sev }) {
  const color = SEV_COLOR[sev] || '#7A96C2';
  return (
    <span className="sev-badge" style={{ '--sev-color': color }}>
      {SEV_ICON[sev]} {sev}
    </span>
  );
}

function Spinner() { return <span className="spinner" />; }

function StatCard({ label, value, sub, accent }) {
  return (
    <div className="stat-card" style={{ '--accent': accent || DORIS_BLUE }}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value?.toLocaleString() ?? '–'}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

function TimeRangeBar({ start, end, onStart, onEnd, onPreset, loading, onRefresh }) {
  return (
    <div className="time-bar">
      <div style={{ display: 'flex', gap: 4 }}>
        {PRESETS.map(p => (
          <button key={p.label} className="preset-btn" onClick={() => onPreset(p.minutes)}>
            {p.label}
          </button>
        ))}
      </div>
      <div className="time-inputs">
        <Clock size={13} />
        <input type="datetime-local" className="time-input"
          value={start ? start.slice(0, 16) : ''}
          onChange={e => onStart(e.target.value ? e.target.value + ':00Z' : '')} />
        <span className="time-sep">→</span>
        <input type="datetime-local" className="time-input"
          value={end ? end.slice(0, 16) : ''}
          onChange={e => onEnd(e.target.value ? e.target.value + ':00Z' : '')} />
      </div>
      <button className={`refresh-btn ${loading ? 'spinning' : ''}`}
        onClick={onRefresh} title="Refresh">
        <RefreshCw size={14} />
      </button>
    </div>
  );
}

// ─── Template renderer: highlights <MASK_TOKENS> in amber ─────────────────────

function TemplateText({ template }) {
  // Split on anything that looks like <TOKEN> or <TOKEN_NAME> patterns
  const parts = template.split(/(<[A-Z_0-9]+>|\?<QUERY>|Bearer <TOKEN>|"<USER_AGENT>")/g);
  return (
    <span className="pattern-template">
      {parts.map((p, i) =>
        /^(<[A-Z_0-9]+>|\?<QUERY>|Bearer <TOKEN>|"<USER_AGENT>")$/.test(p)
          ? <span key={i} className="mask-token">{p}</span>
          : p
      )}
    </span>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Overview Tab
// ═══════════════════════════════════════════════════════════════════════════════

function OverviewTab({ start, end }) {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setStats(await api.getStats(start, end)); }
    catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [start, end]);

  useEffect(() => { load(); }, [load]);

  const sevData = stats
    ? Object.entries(stats.by_severity).map(([s, c]) => ({ sev: s, count: c }))
    : [];

  const serviceData = stats ? stats.by_service.slice(0, 8) : [];

  return (
    <div className="tab-content">
      {loading && <div className="loading-bar" />}
      {stats && (
        <>
          <div className="stat-grid">
            <StatCard label="Total Logs"  value={stats.total}                          accent={DORIS_BLUE} />
            <StatCard label="ERROR"       value={stats.by_severity.ERROR || 0}         accent="#EF4444" />
            <StatCard label="WARN"        value={stats.by_severity.WARN || stats.by_severity.WARNING || 0} accent="#F5A623" />
            <StatCard label="INFO"        value={stats.by_severity.INFO || 0}          accent="#22C55E" />
          </div>

          {/* Hourly sparkline */}
          {stats.hourly?.length > 0 && (
            <div className="chart-card">
              <h3>Log Volume – Last 24 Hours</h3>
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={stats.hourly} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1E3A6E" />
                  <XAxis dataKey="ts"
                    tickFormatter={v => v.slice(11, 16)}
                    tick={{ fill: '#3A5580', fontFamily: 'JetBrains Mono', fontSize: 10 }}
                    interval="preserveStartEnd" />
                  <YAxis tick={{ fill: '#3A5580', fontFamily: 'JetBrains Mono', fontSize: 10 }} />
                  <Tooltip
                    labelFormatter={v => v.replace('T', ' ').slice(0, 16)}
                    contentStyle={{ background: '#0F2043', border: '1px solid #1E3A6E', borderRadius: 6 }} />
                  <Bar dataKey="count" fill={DORIS_BLUE} radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          <div className="chart-row">
            <div className="chart-card">
              <h3>By Severity</h3>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={sevData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1E3A6E" />
                  <XAxis dataKey="sev" tick={{ fill: '#7A96C2', fontFamily: 'JetBrains Mono', fontSize: 11 }} />
                  <YAxis tick={{ fill: '#7A96C2', fontFamily: 'JetBrains Mono', fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: '#0F2043', border: '1px solid #1E3A6E', borderRadius: 6 }} />
                  <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                    {sevData.map(d => (
                      <Cell key={d.sev} fill={SEV_COLOR[d.sev] || DORIS_ACCENT} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="chart-card">
              <h3>By Service</h3>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={serviceData} layout="vertical"
                  margin={{ top: 4, right: 20, left: 100, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1E3A6E" />
                  <XAxis type="number" tick={{ fill: '#7A96C2', fontFamily: 'JetBrains Mono', fontSize: 10 }} />
                  <YAxis dataKey="service" type="category"
                    tick={{ fill: '#7A96C2', fontFamily: 'JetBrains Mono', fontSize: 10 }} width={96} />
                  <Tooltip contentStyle={{ background: '#0F2043', border: '1px solid #1E3A6E', borderRadius: 6 }} />
                  <Bar dataKey="count" fill={DORIS_ACCENT} radius={[0, 3, 3, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="info-box">
            <strong>OTel Native Schema</strong> — Logs stored in{' '}
            <code style={{ fontFamily: 'JetBrains Mono', color: '#F5A623' }}>otel.otel_logs</code> via
            Apache Doris 4.0 Stream Load. Full-text search powered by{' '}
            <strong>MATCH_ANY</strong> on the <code style={{ fontFamily: 'JetBrains Mono', color: '#F5A623' }}>Body</code>{' '}
            column inverted index. Pattern analysis is on-demand via Drain3 — no pattern data is stored.
          </div>
        </>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// LogsTab — standalone component
//
// Paste this function into your App.jsx replacing the existing LogsTab.
//
// Requires these imports to already exist at the top of App.jsx:
//   import React, { useState, useEffect, useCallback, useRef } from 'react';
//   import { Search } from 'lucide-react';
//   import { api } from './api';
//
// Requires these constants defined earlier in App.jsx:
//   SEV_COLOR  — { ERROR: '#EF4444', WARN: '#F5A623', INFO: '#22C55E', ... }
//   SevBadge   — component that renders a severity pill
// ═══════════════════════════════════════════════════════════════════════════════

function LogsTab({ start, end }) {

  // ── State ───────────────────────────────────────────────────────────────────
  const [logs,     setLogs]     = useState([]);
  const [total,    setTotal]    = useState(0);
  const [loading,  setLoading]  = useState(false);
  const [q,        setQ]        = useState('');
  const [qMode,    setQMode]    = useState('MATCH_ANY');
  const [severity, setSeverity] = useState('');
  const [service,  setService]  = useState('');
  const [services, setServices] = useState([]);
  const [expanded, setExpanded] = useState(null);
  const [offset,   setOffset]   = useState(0);
  const LIMIT = 100;

  // ── Refs ────────────────────────────────────────────────────────────────────
  // WHY REFS: useCallback captures state values at creation time (stale closure).
  // If we put q/severity/service in the useCallback dependency array, a new
  // function reference is created on every keystroke — causing useEffect to
  // re-fire in a loop, and the Enter-key handler always reads the OLD value.
  //
  // Fix: refs are mutable and always return the current value, so fetch()
  // never reads a stale q, severity, or service — even when called synchronously
  // inside an event handler before React has processed the state update.
  const qRef        = useRef('');   // mirrors q state, always current
  const qModeRef    = useRef('MATCH_ANY'); // mirrors qMode state, always current
  const severityRef = useRef('');   // mirrors severity state
  const serviceRef  = useRef('');   // mirrors service state
  const debounceRef = useRef(null); // setTimeout handle for typing debounce

  // ── Load services dropdown on mount ────────────────────────────────────────
  useEffect(() => {
    api.getServices()
      .then(d => setServices(d.services))
      .catch(() => {});
  }, []);

  // ── Core fetch function ─────────────────────────────────────────────────────
  // Reads filter values from refs (always current), not from state (may be stale).
  // Accepts newOffset directly so pagination never races with a setOffset call.
  // Only re-created when the time range (start/end) changes from the TimeRangeBar.
  const fetch = useCallback(async (newOffset = 0) => {
    setOffset(newOffset);
    setLoading(true);
    setExpanded(null); // collapse any open row when results change
    try {
      const d = await api.getLogs({
        q:        qRef.current,        // ← always the latest typed value
        q_mode:   qModeRef.current,    // ← search operator mode
        severity: severityRef.current, // ← always the latest selected value
        service:  serviceRef.current,  // ← always the latest selected value
        start,
        end,
        limit:  LIMIT,
        offset: newOffset,
      });
      setLogs(d.logs);
      setTotal(d.total);
    } catch (e) {
      console.error('LogsTab fetch error:', e);
    } finally {
      setLoading(false);
    }
  }, [start, end]); // ← only these two can change externally

  // ── Fetch on mount + whenever time range changes ────────────────────────────
  useEffect(() => { fetch(0); }, [fetch]);

  // ── Search input: debounce typing (300ms), instant on Enter ────────────────
  const handleQueryChange = (e) => {
    const val = e.target.value;
    setQ(val);
    qRef.current = val;              // update ref immediately — before re-render
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetch(0), 300);
  };

  const handleQueryKeyDown = (e) => {
    if (e.key === 'Enter') {
      clearTimeout(debounceRef.current); // cancel pending debounce
      fetch(0);                          // fire immediately with ref value
    }
  };

  const handleClearSearch = () => {
    qRef.current = '';
    setQ('');
    clearTimeout(debounceRef.current);
    fetch(0);
  };

  // ── Dropdown handlers ───────────────────────────────────────────────────────
  const handleQModeChange = (e) => {
    qModeRef.current = e.target.value;
    setQMode(e.target.value);
    fetch(0);
  };

  const handleSeverityChange = (e) => {
    severityRef.current = e.target.value;
    setSeverity(e.target.value);
    fetch(0);
  };

  const handleServiceChange = (e) => {
    serviceRef.current = e.target.value;
    setService(e.target.value);
    fetch(0);
  };

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="tab-content logs-tab">

      {/* Top loading bar */}
      {loading && <div className="loading-bar" />}

      {/* Filter bar */}
      <div className="filter-bar">

        {/* Full-text search */}
        <div className="search-wrap">
          <Search size={13} />
          <input
            className="search-input"
            placeholder="Search log body… (type to filter, Enter to search)"
            value={q}
            onChange={handleQueryChange}
            onKeyDown={handleQueryKeyDown}
          />
          {/* Clear button — only visible when there is a query */}
          {q && (
            <button
              onClick={handleClearSearch}
              title="Clear search"
              style={{
                background: 'none',
                border: 'none',
                color: '#3A5580',
                cursor: 'pointer',
                padding: '0 4px',
                fontSize: 14,
                lineHeight: 1,
              }}
            >
              ✕
            </button>
          )}
        </div>

        {/* Search operator mode dropdown */}
        <select
          className="filter-select"
          value={qMode}
          onChange={handleQModeChange}
          title="Search Mode"
        >
          <option value="MATCH_ANY">Any Match</option>
          <option value="MATCH_ALL">All Match</option>
          <option value="MATCH_PHRASE">Phrase Match</option>
          <option value="MATCH_PHRASE_PREFIX">Phrase Prefix</option>
          <option value="MATCH_PHRASE_EDGE">Phrase Edge</option>
          <option value="MATCH_REGEXP">Regex Match</option>
        </select>

        {/* Severity dropdown */}
        <select
          className="filter-select"
          value={severity}
          onChange={handleSeverityChange}
        >
          <option value="">All severity</option>
          {['ERROR', 'WARN', 'INFO', 'DEBUG', 'TRACE'].map(s => (
            <option key={s}>{s}</option>
          ))}
        </select>

        {/* Service dropdown */}
        <select
          className="filter-select"
          value={service}
          onChange={handleServiceChange}
        >
          <option value="">All services</option>
          {services.map(s => <option key={s}>{s}</option>)}
        </select>

        {/* Result count */}
        <span className="row-count">{total.toLocaleString()} rows</span>
      </div>

      {/* Log table */}
      <div className="log-table-wrap">
        <table className="log-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Severity</th>
              <th>Service</th>
              <th>Body</th>
              <th>TraceId</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log, i) => (
              <React.Fragment key={i}>

                {/* Collapsed row */}
                <tr
                  className={`log-row ${expanded === i ? 'expanded' : ''}`}
                  style={{ '--sev-color': SEV_COLOR[log.severity_text] || '#7A96C2' }}
                  onClick={() => setExpanded(expanded === i ? null : i)}
                >
                  <td className="cell-ts">
                    {String(log.timestamp).slice(0, 19).replace('T', ' ')}
                  </td>
                  <td><SevBadge sev={log.severity_text} /></td>
                  <td className="cell-svc">{log.service_name}</td>
                  <td className="cell-body">{log.body}</td>
                  <td className="cell-trace">
                    {log.trace_id && log.trace_id !== '0'.repeat(32)
                      ? log.trace_id.slice(0, 16) + '…'
                      : '—'}
                  </td>
                </tr>

                {/* Expanded detail row */}
                {expanded === i && (
                  <tr className="expand-row">
                    <td colSpan={5}>
                      <div className="expand-detail">

                        <div>
                          <span className="label">Body:</span>
                          <span className="expand-body">{log.body}</span>
                        </div>

                        <div>
                          <span className="label">Service:</span>{' '}
                          {log.service_name}
                          {log.service_instance_id && (
                            <span style={{ color: '#3A5580' }}>
                              {' '}· {log.service_instance_id}
                            </span>
                          )}
                        </div>

                        <div>
                          <span className="label">Severity:</span>{' '}
                          {log.severity_text} ({log.severity_number})
                        </div>

                        {log.scope_name && (
                          <div>
                            <span className="label">Scope:</span>{' '}
                            {log.scope_name}
                            {log.scope_version && ` v${log.scope_version}`}
                          </div>
                        )}

                        {log.trace_id && log.trace_id !== '0'.repeat(32) && (
                          <div>
                            <span className="label">TraceId:</span>{' '}
                            {log.trace_id}
                          </div>
                        )}

                        {log.span_id && log.span_id !== '0'.repeat(16) && (
                          <div>
                            <span className="label">SpanId:</span>{' '}
                            {log.span_id}
                          </div>
                        )}

                        {log.log_attributes && (
                          <div>
                            <span className="label">Attributes:</span>
                            <span style={{ fontFamily: 'JetBrains Mono', fontSize: 11 }}>
                              {typeof log.log_attributes === 'string'
                                ? log.log_attributes
                                : JSON.stringify(log.log_attributes, null, 2)}
                            </span>
                          </div>
                        )}

                      </div>
                    </td>
                  </tr>
                )}

              </React.Fragment>
            ))}

            {/* Empty state */}
            {!loading && logs.length === 0 && (
              <tr>
                <td colSpan={5} className="empty-row">
                  No logs found for this filter
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="pagination">
        <button
          disabled={offset === 0}
          onClick={() => fetch(Math.max(0, offset - LIMIT))}
        >
          ← Prev
        </button>
        <span>
          Page {Math.floor(offset / LIMIT) + 1} of{' '}
          {Math.max(1, Math.ceil(total / LIMIT))}
        </span>
        <button
          disabled={offset + LIMIT >= total}
          onClick={() => fetch(offset + LIMIT)}
        >
          Next →
        </button>
      </div>

    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Patterns Tab
// ═══════════════════════════════════════════════════════════════════════════════

function PatternsTab({ start, end }) {
  const [patterns, setPatterns]   = useState([]);
  const [meta, setMeta]           = useState(null);
  const [loading, setLoading]     = useState(false);
  const [selected, setSelected]   = useState(null);
  const [series, setSeries]       = useState([]);
  const [seriesLoading, setSeriesLoading] = useState(false);
  const [bucket, setBucket]       = useState('1h');
  const [minCount, setMinCount]   = useState(2);
  const [service, setService]     = useState('');
  const [severity, setSeverity]   = useState('');
  const [services, setServices]   = useState([]);
  const [activeMasks, setActiveMasks] = useState([]);
  const [samples, setSamples]             = useState([]);
  const [samplesLoading, setSamplesLoading] = useState(false);
  const [totalMatched, setTotalMatched]   = useState(0);
  const [expandedSample, setExpandedSample] = useState(null);

  useEffect(() => {
    api.getServices().then(d => setServices(d.services)).catch(() => {});
    api.getActiveMasks().then(d => setActiveMasks(d.active_ids)).catch(() => {});
  }, []);

  const analyse = useCallback(async () => {
    setLoading(true);
    setSelected(null); setSeries([]);
    try {
      const d = await api.getPatterns({ start, end, service, severity, min_count: minCount });
      setPatterns(d.patterns);
      setMeta({ logs_analysed: d.logs_analysed, active_masks: d.active_masks });
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [start, end, service, severity, minCount]);

  const loadSeries = useCallback(async (cid) => {
    setSeriesLoading(true);
    try {
      const d = await api.getPatternSeries({ cluster_id: cid, start, end, service, bucket });
      setSeries(d.series);
    } catch (e) { console.error(e); }
    finally { setSeriesLoading(false); }
  }, [start, end, service, bucket]);

  const loadSamples = useCallback(async (cid) => {
    setSamplesLoading(true);
    setSamples([]); setTotalMatched(0); setExpandedSample(null);
    try {
      const d = await api.getPatternSamples(cid, { start, end, service, severity, sample_size: 10 });
      setSamples(d.samples);
      setTotalMatched(d.total_matched);
    } catch (e) { console.error(e); }
    finally { setSamplesLoading(false); }
  }, [start, end, service, severity]);

  const selectPattern = (p) => {
    if (selected?.cluster_id === p.cluster_id) {
      setSelected(null); setSeries([]); setSamples([]); setTotalMatched(0);
    } else {
      setSelected(p);
      loadSeries(p.cluster_id);
      loadSamples(p.cluster_id);
    }
  };

  useEffect(() => {
    if (selected) loadSeries(selected.cluster_id);
  }, [bucket, selected, loadSeries]);

  const maxCount = patterns[0]?.count || 1;

  return (
    <div className="tab-content">
      {loading && <div className="loading-bar" />}

      {/* Controls */}
      <div className="pattern-controls">
        <select className="filter-select" value={service} onChange={e => setService(e.target.value)}>
          <option value="">All services</option>
          {services.map(s => <option key={s}>{s}</option>)}
        </select>
        <select className="filter-select" value={severity} onChange={e => setSeverity(e.target.value)}>
          <option value="">All severity</option>
          {['ERROR', 'WARN', 'INFO', 'DEBUG'].map(s => <option key={s}>{s}</option>)}
        </select>
        <label>
          Min count
          <input type="number" className="num-input" min={1} max={9999}
            value={minCount} onChange={e => setMinCount(Number(e.target.value))} />
        </label>
        <button className="pattern-analyse-btn" onClick={analyse} disabled={loading}>
          {loading ? <Spinner /> : <Play size={13} />}
          {loading ? 'Analysing…' : 'Analyse Patterns'}
        </button>
        {patterns.length > 0 && (
          <span className="row-count">{patterns.length} clusters</span>
        )}
      </div>

      {/* Active masks summary */}
      {activeMasks.length > 0 && (
        <div className="info-box">
          <strong>Active masking:</strong>{' '}
          {activeMasks.join(' · ')}{' '}
          — Mask tokens appear highlighted in <span style={{ color: '#F5A623', fontWeight: 600 }}>amber</span> within templates.
          Configure in the <strong>Settings</strong> tab.
        </div>
      )}

      {/* Meta row */}
      {meta && (
        <div className="pattern-meta">
          <span>Logs analysed: <span className="meta-highlight">{meta.logs_analysed.toLocaleString()}</span></span>
          <span>·</span>
          <span>Clusters found: <span className="meta-highlight">{patterns.length}</span></span>
          <span>·</span>
          <span>Active masks: <span className="meta-highlight">{meta.active_masks?.length ?? 0}</span></span>
        </div>
      )}

      {/* No patterns yet */}
      {!meta && patterns.length === 0 && (
        <div className="info-box">
          Click <strong>Analyse Patterns</strong> to run Drain3 log clustering on the selected time window.
          Patterns are detected on-demand from <code style={{ fontFamily: 'JetBrains Mono', color: '#F5A623' }}>otel.otel_logs</code> and are not stored.
        </div>
      )}

      {/* Layout */}
      <div className={`pattern-layout ${selected ? 'with-detail' : ''}`}>
        <div className="pattern-list">
          {patterns.map(p => (
            <div key={p.cluster_id}
              className={`pattern-row ${selected?.cluster_id === p.cluster_id ? 'active' : ''}`}
              onClick={() => selectPattern(p)}>
              <div className="pattern-header">
                <span className="pattern-cid">#{p.cluster_id}</span>
                <span className="pattern-count">{p.count.toLocaleString()} hits</span>
              </div>
              {/* Template with mask token highlighting */}
              <TemplateText template={p.template} />
              <div className="pattern-bar-wrap">
                <div className="pattern-bar" style={{ width: `${(p.count / maxCount) * 100}%` }} />
              </div>
              {p.mask_tokens?.length > 0 && (
                <div className="pattern-mask-tags">
                  {p.mask_tokens.map(t => (
                    <span key={t} className="mask-tag">{t}</span>
                  ))}
                </div>
              )}
            </div>
          ))}
          {meta && patterns.length === 0 && (
            <div className="empty-msg">No patterns found. Lower min count or broaden the time range.</div>
          )}
        </div>

        {/* Detail panel */}
        {selected && (
          <div className="pattern-detail">
            <div className="detail-header">
              <div>
                <h3>Cluster #{selected.cluster_id}</h3>
                <TemplateText template={selected.template} />
                {selected.mask_tokens?.length > 0 && (
                  <div className="pattern-mask-tags" style={{ marginTop: 8 }}>
                    {selected.mask_tokens.map(t => (
                      <span key={t} className="mask-tag">{t}</span>
                    ))}
                  </div>
                )}
              </div>
              <button className="icon-btn" onClick={() => { setSelected(null); setSeries([]); }}>
                <X size={14} />
              </button>
            </div>

            <div className="bucket-select">
              {['5m', '15m', '1h', '6h', '1d'].map(b => (
                <button key={b}
                  className={`preset-btn ${bucket === b ? 'active' : ''}`}
                  onClick={() => setBucket(b)}>{b}</button>
              ))}
            </div>

            {seriesLoading && (
              <div style={{ textAlign: 'center', padding: 20 }}><Spinner /></div>
            )}
            {!seriesLoading && series.length > 0 && (
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={series} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1E3A6E" />
                  <XAxis dataKey="ts"
                    tickFormatter={v => v.slice(11, 16)}
                    tick={{ fill: '#3A5580', fontFamily: 'JetBrains Mono', fontSize: 10 }} />
                  <YAxis tick={{ fill: '#3A5580', fontFamily: 'JetBrains Mono', fontSize: 10 }} />
                  <Tooltip
                    labelFormatter={v => v.replace('T', ' ').slice(0, 19)}
                    contentStyle={{ background: '#0F2043', border: '1px solid #1E3A6E', borderRadius: 6 }} />
                  <Line type="monotone" dataKey="count"
                    stroke={DORIS_ACCENT} strokeWidth={2} dot={false}
                    activeDot={{ r: 4, fill: DORIS_ACCENT }} />
                </LineChart>
              </ResponsiveContainer>
            )}
            {!seriesLoading && series.length === 0 && (
              <div className="empty-msg">No time-series data for this pattern.</div>
            )}

            {/* ── Sample Matched Logs ─────────────────────────────── */}
            <div className="samples-section">
              <div className="samples-header">
                <div className="samples-title">
                  <FileText size={14} />
                  <span>Matched Log Samples</span>
                  {totalMatched > 0 && (
                    <span className="samples-count">
                      showing {samples.length} of {totalMatched.toLocaleString()} matched
                    </span>
                  )}
                </div>
              </div>

              {samplesLoading && (
                <div style={{ textAlign: 'center', padding: 20 }}><Spinner /></div>
              )}

              {!samplesLoading && samples.length > 0 && (
                <div className="samples-list">
                  {samples.map((s, i) => (
                    <div key={i}
                      className={`sample-row ${expandedSample === i ? 'expanded' : ''}`}
                      onClick={() => setExpandedSample(expandedSample === i ? null : i)}>
                      <div className="sample-meta">
                        <span className="sample-ts">
                          {String(s.timestamp).slice(0, 19).replace('T', ' ')}
                        </span>
                        <SevBadge sev={s.severity_text} />
                        <span className="sample-svc">{s.service_name}</span>
                      </div>
                      <div className={`sample-body ${expandedSample === i ? 'full' : ''}`}>
                        {s.body}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {!samplesLoading && samples.length === 0 && !loading && selected && (
                <div className="empty-msg">No matching log samples found.</div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Settings Tab
// ═══════════════════════════════════════════════════════════════════════════════

const CATEGORY_ORDER = ['Network', 'Identity', 'Web', 'System', 'Security'];

function SettingsTab() {
  const [presets, setPresets]       = useState([]);
  const [activeIds, setActiveIds]   = useState([]);
  const [simTh, setSimTh]           = useState(0.4);
  const [depth, setDepth]           = useState(4);
  const [saving, setSaving]         = useState(false);
  const [saveMsg, setSaveMsg]       = useState('');

  const load = async () => {
    const [p, a, cfg] = await Promise.all([
      api.getMaskPresets(),
      api.getActiveMasks(),
      api.getDrainConfig(),
    ]);
    setPresets(p.presets);
    setActiveIds(a.active_ids);
    setSimTh(cfg.sim_th);
    setDepth(cfg.depth);
  };
  useEffect(() => { load(); }, []);

  const togglePreset = (id) => {
    setActiveIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const saveMasks = async () => {
    setSaving(true); setSaveMsg('');
    try {
      await api.updateActiveMasks(activeIds);
      setSaveMsg('✓ Active masks updated. Next pattern analysis will use these rules.');
    } catch (e) { setSaveMsg('✗ ' + e.message); }
    finally { setSaving(false); }
  };

  const resetMasks = async () => {
    setSaving(true); setSaveMsg('');
    try {
      const d = await api.resetMasks();
      setActiveIds(d.active_ids);
      setSaveMsg('✓ Masks reset to defaults.');
    } catch (e) { setSaveMsg('✗ ' + e.message); }
    finally { setSaving(false); }
  };

  const saveDrainConfig = async () => {
    setSaving(true); setSaveMsg('');
    try {
      await api.updateDrainConfig({ sim_th: simTh, depth });
      setSaveMsg('✓ Drain3 config saved. Next analysis will use the new settings.');
    } catch (e) { setSaveMsg('✗ ' + e.message); }
    finally { setSaving(false); }
  };

  const byCategory = CATEGORY_ORDER.map(cat => ({
    cat,
    items: presets.filter(p => p.category === cat),
  })).filter(g => g.items.length > 0);

  return (
    <div className="tab-content settings-tab">

      {/* ── Mask Presets ──────────────────────────────────────────────── */}
      <div className="settings-section">
        <h2><Layers size={16} /> Masking Presets</h2>
        <p className="settings-desc">
          Select which pre-written masking rules Drain3 applies before clustering.
          Checked rules replace matching values with named tokens (e.g.{' '}
          <em>&lt;IP_ADDRESS&gt;</em>) so high-cardinality fields don't fragment your clusters.
          These tokens remain visible in detected pattern templates — shown in{' '}
          <span style={{ color: '#F5A623', fontWeight: 600 }}>amber</span> in the Patterns tab.
          Masking rules are pre-defined; no custom regex input is needed.
        </p>

        {byCategory.map(({ cat, items }) => (
          <div key={cat} className="mask-category">
            <div className="mask-category-label">{cat}</div>
            <div className="mask-presets-grid">
              {items.map(preset => {
                const isActive = activeIds.includes(preset.id);
                return (
                  <div key={preset.id}
                    className={`mask-preset-card ${isActive ? 'active' : ''}`}
                    onClick={() => togglePreset(preset.id)}>
                    <div className="preset-checkbox">
                      {isActive && <span className="preset-check">✓</span>}
                    </div>
                    <div className="preset-info">
                      <div className="preset-label">{preset.label}</div>
                      <div className="preset-desc">{preset.description}</div>
                      <div className="preset-token">→ {preset.token}</div>
                      <div className="preset-examples">
                        {preset.examples.slice(0, 2).map(ex => (
                          <span key={ex} className="preset-example">{ex}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}

        <div className="mask-action-row">
          <button className="btn-primary" onClick={saveMasks} disabled={saving}>
            {saving ? <Spinner /> : null} Save Mask Selection
          </button>
          <button className="btn-ghost" onClick={resetMasks} disabled={saving}>
            <RotateCcw size={13} /> Reset to defaults
          </button>
          <span className="mask-active-count">
            <span>{activeIds.length}</span> of {presets.length} active
          </span>
        </div>
      </div>

      {/* ── Drain3 Config ─────────────────────────────────────────────── */}
      <div className="settings-section">
        <h2><Database size={16} /> Drain3 Algorithm Parameters</h2>
        <p className="settings-desc">
          Drain3 builds an in-memory prefix tree over log tokens. These settings apply
          the next time you click <em>Analyse Patterns</em>. Changes are not retroactive.
        </p>

        <div className="slider-row">
          <div className="slider-label">
            Similarity Threshold
            <span className="slider-value">{simTh.toFixed(2)}</span>
          </div>
          <input type="range" className="range-input"
            min={0.1} max={1.0} step={0.05} value={simTh}
            onChange={e => setSimTh(Number(e.target.value))} />
          <div className="range-labels">
            <span>← coarse grouping (0.1)</span>
            <span>fine grouping (1.0) →</span>
          </div>
        </div>

        <div className="slider-row">
          <div className="slider-label">
            Tree Depth
            <span className="slider-value">{depth}</span>
          </div>
          <input type="range" className="range-input"
            min={2} max={10} step={1} value={depth}
            onChange={e => setDepth(Number(e.target.value))} />
          <div className="range-labels"><span>2</span><span>10</span></div>
        </div>

        <button className="btn-primary" onClick={saveDrainConfig} disabled={saving}>
          {saving ? <Spinner /> : null} Save Drain3 Config
        </button>
      </div>

      {saveMsg && (
        <div className={`save-msg ${saveMsg.startsWith('✓') ? 'ok' : 'err'}`}>
          {saveMsg}
        </div>
      )}

      {/* ── Schema reference ──────────────────────────────────────────── */}
      <div className="settings-section">
        <h2><Info size={16} /> OTel Native Schema Reference</h2>
        <p className="settings-desc">
          Logs are stored in <em>otel.otel_logs</em> (Apache Doris 4.x) by the OTel Collector
          via Stream Load. This backend is <em>read-only</em> — it queries but never writes.
        </p>
        <div style={{ fontFamily: 'JetBrains Mono', fontSize: 12, color: '#7A96C2',
          background: '#091325', padding: 16, borderRadius: 8, lineHeight: 2,
          border: '1px solid #1E3A6E', overflowX: 'auto' }}>
          {[
            ['timestamp',             'DATETIME(6)',   'Log event time · DUPLICATE KEY · partition column'],
            ['service_name',          'VARCHAR(200)',  'service.name from OTLP resource attributes · DUPLICATE KEY'],
            ['service_instance_id',   'VARCHAR(200)',  'service.instance.id from OTLP resource attributes'],
            ['trace_id',              'VARCHAR(200)',  '128-bit W3C trace identifier (hex string)'],
            ['span_id',               'STRING',        '64-bit W3C span identifier (hex string)'],
            ['severity_number',       'INT',           'OTLP numeric severity: 9=INFO 13=WARN 17=ERROR 21=FATAL'],
            ['severity_text',         'STRING',        'Human severity label: INFO / WARN / ERROR / DEBUG'],
            ['body',                  'STRING',        'Raw log line – unicode inverted index + phrase support'],
            ['resource_attributes',   'VARIANT',       'All OTLP resource attributes as JSON (inverted indexed)'],
            ['log_attributes',        'VARIANT',       'Parsed log fields as JSON: http.method, status_code…'],
            ['scope_name',            'STRING',        'Instrumentation scope name (e.g. logscope.simulator)'],
            ['scope_version',         'STRING',        'Instrumentation scope version (e.g. 1.0.0)'],
          ].map(([col, type, desc]) => (
            <div key={col} style={{ display: 'grid', gridTemplateColumns: '200px 130px 1fr', gap: 8 }}>
              <span style={{ color: '#4D7CFE' }}>{col}</span>
              <span style={{ color: '#F5A623' }}>{type}</span>
              <span style={{ color: '#3A5580' }}>-- {desc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Root App
// ═══════════════════════════════════════════════════════════════════════════════

const TABS = [
  { id: 'overview',  label: 'Overview',  icon: <Activity size={14} /> },
  { id: 'logs',      label: 'Logs',      icon: <Terminal size={14} /> },
  { id: 'patterns',  label: 'Patterns',  icon: <Layers   size={14} /> },
  { id: 'settings',  label: 'Settings',  icon: <Settings size={14} /> },
];

export default function App() {
  const [tab, setTab]     = useState('overview');
  const [start, setStart] = useState(isoMinus(1440));
  const [end, setEnd]     = useState(isoNow());
  const refreshRef        = useRef(0);
  const [loading]         = useState(false);

  const handlePreset = (m) => { setStart(isoMinus(m)); setEnd(isoNow()); };
  const handleRefresh = () => { setEnd(isoNow()); refreshRef.current += 1; };

  return (
    <div className="app">
      <header className="header">
        <div className="header-brand">
          <div className="brand-icon">LS</div>
          <span className="brand-name">LogScope</span>
          <span className="brand-tag">OTel · Doris 4.x</span>
        </div>

        <nav className="header-nav">
          {TABS.map(t => (
            <button key={t.id}
              className={`nav-btn ${tab === t.id ? 'active' : ''}`}
              onClick={() => setTab(t.id)}>
              {t.icon} {t.label}
            </button>
          ))}
        </nav>

        <div className="header-right">
          <div className="live-badge">
            <span className="live-dot" />
            Live · Doris 4.0
          </div>
        </div>
      </header>

      {tab !== 'settings' && (
        <TimeRangeBar
          start={start} end={end}
          onStart={setStart} onEnd={setEnd}
          onPreset={handlePreset}
          loading={loading}
          onRefresh={handleRefresh}
        />
      )}

      <main className="main">
        {tab === 'overview' && <OverviewTab start={start} end={end} key={`ov-${refreshRef.current}`} />}
        {tab === 'logs'     && <LogsTab     start={start} end={end} key={`lg-${refreshRef.current}`} />}
        {tab === 'patterns' && <PatternsTab start={start} end={end} key={`pt-${refreshRef.current}`} />}
        {tab === 'settings' && <SettingsTab />}
      </main>
    </div>
  );
}
