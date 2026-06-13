const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${path}: ${res.status} – ${txt}`);
  }
  return res.json();
}

const qs = (params) =>
  new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== '' && v != null)
  ).toString();

export const api = {
  // ── Logs ──────────────────────────────────────────────────────────────
  getLogs: (p = {}) => req(`/api/logs?${qs(p)}`),

  // ── Stats ─────────────────────────────────────────────────────────────
  getStats: (start, end) => req(`/api/stats?${qs({ start, end })}`),
  getServices: () => req('/api/services'),

  // ── Patterns ──────────────────────────────────────────────────────────
  getPatterns: (p = {}) => req(`/api/patterns?${qs(p)}`),
  getPatternSeries: (p = {}) => req(`/api/patterns/timeseries?${qs(p)}`),
  getPatternSamples: (clusterId, p = {}) => req(`/api/patterns/${clusterId}/samples?${qs(p)}`),

  // ── Drain config ──────────────────────────────────────────────────────
  getDrainConfig: () => req('/api/drain/config'),
  updateDrainConfig: (cfg) => req('/api/drain/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  }),

  // ── Mask presets ──────────────────────────────────────────────────────
  getMaskPresets: () => req('/api/masks/presets'),
  getActiveMasks: () => req('/api/masks/active'),
  updateActiveMasks: (ids) => req('/api/masks/active', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ active_ids: ids }),
  }),
  resetMasks: () => req('/api/masks/reset', { method: 'POST' }),
};
