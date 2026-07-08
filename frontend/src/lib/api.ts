/* ═══════════════════════════════════════════════════════════════════════
   JULIUS — Unified API Client
   All backend calls go through Vite proxy: /api → localhost:8000
   ═══════════════════════════════════════════════════════════════════════ */

const BASE = ''  // Vite proxies /api to backend

export interface AuthLoginResponse {
  requires_mfa?: boolean
  token: string
  user: Record<string, unknown>
}

interface ApiValidationError {
  loc?: string | string[]
  msg?: string
  type?: string
}

function hdr() {
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  const t = localStorage.getItem('julius_token')
  if (t) h['Authorization'] = `Bearer ${t}`
  return h
}

async function get<T = unknown>(url: string): Promise<T> {
  const r = await fetch(`${BASE}${url}`, { headers: hdr() })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return (await r.json()) as T
}

async function post<T = unknown>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${url}`, { method: 'POST', headers: hdr(), body: body != null ? JSON.stringify(body) : undefined })
  if (!r.ok) {
    // Log detailed 422 body for easier debugging
    if (r.status === 422) {
      try {
        const errBody = await r.json()
        console.error('API 422 Unprocessable Entity:', url, errBody)
        if (errBody && Array.isArray(errBody.detail)) {
          console.error('API 422 validation errors:')
          errBody.detail.forEach((err: ApiValidationError) => {
            console.error(`Field: ${Array.isArray(err.loc) ? err.loc.join('.') : err.loc} — msg: ${err.msg} — type: ${err.type}`)
          })
        }
      } catch {
        try {
          const text = await r.text()
          console.error('API 422 Unprocessable Entity (text):', url, text)
        } catch {
          console.error('API 422 Unprocessable Entity and failed to parse body', url)
        }
      }
    }
    throw new Error(`${r.status} ${r.statusText}`)
  }
  return (await r.json()) as T
}

async function put<T = unknown>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${url}`, { method: 'PUT', headers: hdr(), body: body != null ? JSON.stringify(body) : undefined })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return (await r.json()) as T
}

async function del<T = unknown>(url: string): Promise<T> {
  const r = await fetch(`${BASE}${url}`, { method: 'DELETE', headers: hdr() })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return (await r.json()) as T
}

async function download(url: string): Promise<Blob> {
  const r = await fetch(`${BASE}${url}`, { headers: hdr() })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return await r.blob()
}

/* ── Auth ──────────────────────────────────────────────────────────── */
export const auth = {
  login: (username: string, password: string) => post<AuthLoginResponse>('/api/auth/login', { username, password }),
  me: () => get<Record<string, unknown>>('/api/auth/me'),
  status: () => get<Record<string, unknown>>('/api/auth/me'),
  verify: () => get<Record<string, unknown>>('/api/auth/me'),
  register: (data: Record<string, unknown>) => post('/api/auth/register', data),
  logout: () => post('/api/auth/logout'),
  users: () => get('/api/auth/users'),
}

/* ── Chat ──────────────────────────────────────────────────────────── */
export const chat = {
  send: (message: string, session_id = 'default') => post('/api/chat/message', { message, session_id }),
  history: (session_id = 'default') => get(`/api/chat/history/${session_id}`),
}

/* ── Scanner ───────────────────────────────────────────────────────── */
export const scanner = {
  scan: (target: string, portsOrScanType?: string | number[], mode?: string) => {
    const payload: Record<string, unknown> = { target }

    // Determine if second arg is ports (array or comma-separated numbers) or a scan type
    if (Array.isArray(portsOrScanType)) {
      payload.ports = portsOrScanType
    } else if (typeof portsOrScanType === 'string') {
      const s = portsOrScanType.trim()
      if (/^[0-9,\s]+$/.test(s)) {
        payload.ports = s.split(',').map(p => parseInt(p.trim(), 10)).filter(n => !Number.isNaN(n))
      } else {
        payload.scan_type = s
      }
    }

    // If explicit mode provided, override scan_type
    if (mode) payload.scan_type = mode

    return post('/api/scanner/scan', payload)
  },
  list: () => get('/api/scanner/scans'),
  checkPort: (ip: string, port: number) => post('/api/scanner/check-port', { ip, port }),
  vulns: () => get('/api/scanner/vulnerabilities'),
  vulnerabilities: () => get('/api/scanner/vulnerabilities'),
}

/* ── Exploit ───────────────────────────────────────────────────────── */
export const exploit = {
  modules: () => get('/api/exploit/modules'),
  run: (target: string, module_id: string, port?: number, options?: Record<string, unknown>) => {
    const payload: Record<string, unknown> = { target, exploit_type: module_id }
    if (port != null) payload.port = Number(port)
    if (options) payload.options = options
    return post('/api/exploit/run', payload)
  },
  history: () => get('/api/exploit/history'),
}

/* ── Behavioral ────────────────────────────────────────────────────── */
export const behavioral = {
  stats: () => get('/api/behavioral/stats'),
  patterns: () => get('/api/behavioral/patterns'),
  alerts: (limit = 50) => get(`/api/behavioral/alerts?limit=${limit}`),
  addPattern: (data: Record<string, unknown>) => post('/api/behavioral/patterns', data),
  updatePattern: (id: number, data: Record<string, unknown>) => put(`/api/behavioral/patterns/${id}`, data),
  deletePattern: (id: number) => del(`/api/behavioral/patterns/${id}`),
  addAlert: (data: Record<string, unknown>) => post('/api/behavioral/alerts', data),
  deleteAlert: (id: number) => del(`/api/behavioral/alerts/${id}`),
  acknowledge: (id: string) => put(`/api/behavioral/alerts/${id}/acknowledge`),
}

/* ── Identity ──────────────────────────────────────────────────────── */
export const identity = {
  list: () => get('/api/identity/list'),
  graph: () => get('/api/identity/graph'),
  add: (data: Record<string, unknown>) => post('/api/identity', data),
  merge: (from: string, to: string) => post('/api/identity/merge', { source_id: from, target_id: to }),
  confidence: (id: string) => get(`/api/identity/${id}/confidence`),
}

/* ── Events ────────────────────────────────────────────────────────── */
export const events = {
  recent: (limit = 100) => get(`/api/events/recent?limit=${limit}`),
  stats: () => get('/api/events/stats'),
  publish: (event_type: string, source: string, data: Record<string, unknown>) =>
    post('/api/events/publish', { event_type, source, data }),
}

/* ── Files ─────────────────────────────────────────────────────────── */
export const files = {
  list: (path = '.') => get(`/api/files/list?path=${encodeURIComponent(path)}`),
  read: (path: string) => get(`/api/files/read?path=${encodeURIComponent(path)}`),
  operate: (op: string, path: string, content?: string, force?: boolean) =>
    post('/api/files/operate', { operation: op, path, content, force }),
  sandboxInfo: () => get('/api/files/sandbox'),
}

/* ── Dark Web ──────────────────────────────────────────────────────── */
export const darkweb = {
  health: () => get('/api/darkweb/health'),
  search: (query: string) => post('/api/darkweb/search', { query }),
  investigate: (query: string) => post('/api/darkweb/investigate', { query }),
  investigations: () => get('/api/darkweb/investigations'),
  getInvestigation: (id: string) => get(`/api/darkweb/investigations/${id}`),
}

/* ── Insights / Workflows ──────────────────────────────────────────── */
export const insights = {
  analytics: () => get('/api/insights/analytics'),
  dashboard: () => get('/api/insights/dashboard'),
  workflows: () => get('/api/workflows/'),
}

/* ── OSINT / Threat Feeds ──────────────────────────────────────────── */
export const osint = {
  threatFeeds: () => get('/api/osint/feeds'),
  lookup: (ip: string) => get(`/api/osint/lookup/${ip}`),
  startUkCollection: (payload?: {
    target_profiles?: number
    github_queries?: string[]
    allowlisted_domains?: string[]
    hostsearch_zones?: string[]
    gitlab_queries?: string[]
    npm_queries?: string[]
    pypi_packages?: string[]
    govuk_queries?: string[]
    spending_queries?: string[]
    gdelt_queries?: string[]
    osm_queries?: string[]
    max_github_pages?: number
    max_github_enrichments?: number
    max_hostsearch_results_per_zone?: number
    max_ipinfo_lookups?: number
    max_gitlab_results_per_query?: number
    max_npm_results_per_query?: number
    max_pypi_package_lookups?: number
    max_govuk_results_per_query?: number
    max_spending_results_per_query?: number
    max_gdelt_results_per_query?: number
    max_osm_results_per_query?: number
  }) => post('/api/osint/collect/uk', payload ?? {}),
  stopUkCollection: (jobId: string) => post(`/api/osint/collect/uk/stop/${encodeURIComponent(jobId)}`),
  ukCollectionStatus: (jobId: string) => get(`/api/osint/collect/status/${encodeURIComponent(jobId)}`),
  exportUkCollection: (jobId: string) => download(`/api/osint/collect/export/${encodeURIComponent(jobId)}`),
}

/* STRATUM OMNIS */
export const stratum = {
  blueprint: () => get('/api/stratum/blueprint'),
  runtime: () => get('/api/stratum/runtime'),
  featureStore: (limit = 25) => get(`/api/stratum/feature-store?limit=${limit}`),
  streamProcessing: (limit = 50) => get(`/api/stratum/stream-processing?limit=${limit}`),
  identityResolution: (limit = 100) => get(`/api/stratum/identity-resolution?limit=${limit}`),
  modelHub: () => get('/api/stratum/model-hub'),
  oracle: (limit = 10) => get(`/api/stratum/oracle?limit=${limit}`),
  csie: (limit = 10) => get(`/api/stratum/csie?limit=${limit}`),
}

/* ── Live Data ─────────────────────────────────────────────────────── */
export const live = {
  dashboard: () => get('/api/live/dashboard'),
  metrics: () => get('/api/live/metrics'),
  connections: () => get('/api/live/connections'),
  processes: () => get('/api/live/processes'),
  ipLookup: (ip: string) => get(`/api/live/ip/${ip}`),
  dnsLookup: (domain: string) => get(`/api/live/dns/${domain}`),
  latestCves: () => get('/api/live/cves'),
  arp: () => get('/api/live/arp'),
}

/* ── System / Status ───────────────────────────────────────────────── */
export const system = {
  health: () => get('/api/status/health'),
  stats: () => get('/api/status/stats'),
}

/* ── Network ───────────────────────────────────────────────────────── */
export const network = {
  info: () => get('/api/network/info'),
  allowlist: () => get('/api/network/allowlist'),
  addAllowlist: (cidr: string) => post('/api/network/allowlist', { cidr }),
  check: (ip: string, port: number) => get(`/api/network/check/${ip}/${port}`),
}

/* ── LAN ───────────────────────────────────────────────────────────── */
export const lan = {
  recon: (target: string, username?: string, password?: string) =>
    post('/api/lan/recon', { target, username, password }),
  browse: (target: string, share: string, path?: string, username?: string, password?: string) =>
    post('/api/lan/browse', { target, share, path, username, password }),
  mkdir: (target: string, path: string, username?: string, password?: string) =>
    post('/api/lan/mkdir', { target, path, username, password }),
  exec: (target: string, command: string, username?: string, password?: string) =>
    post('/api/lan/exec', { target, command, username, password }),
  execStream: async (target: string, command: string, onChunk: (text: string) => void, username?: string, password?: string) => {
    const res = await fetch(BASE + '/api/lan/exec-stream', {
      method: 'POST',
      headers: hdr(),
      body: JSON.stringify({ target, command, username, password })
    })
    if (!res.body) throw new Error('No streaming response body')
    const reader = res.body.getReader()
    const dec = new TextDecoder()
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      onChunk(dec.decode(value, { stream: true }))
    }
  },
}

/* ── Settings ──────────────────────────────────────────────────────── */
export const settings = {
  get: () => get('/api/settings'),
  update: (data: Record<string, unknown>) => put('/api/settings', data),
}

/* ── Terminal (Linux Shell) ────────────────────────────────────────── */
export const terminal = {
  execute: (command: string, timeout = 30) => post('/api/terminal/execute', { command, timeout }),
  status: () => get('/api/terminal/status'),
  sysinfo: () => get('/api/terminal/sysinfo'),
  history: () => get('/api/terminal/history'),
  install: (packages: string) => post('/api/terminal/install', { packages }),
}

/* ── Monitor ───────────────────────────────────────────────────────── */
export const monitor = {
  feeds: () => get('/api/globe/monitor-feeds'),
  conflicts: () => get('/api/globe/conflicts'),
  fires: () => get('/api/globe/fires'),
  news: (country: string, topic: string) => get(`/api/globe/news?country=${country}&topic=${topic}`),
  liveChannels: () => get('/api/globe/live-channels'),
}

/* ── Reports ─────────────────────────────────────────────────────────────── */
export const reports = {
  generateFull: () => post('/api/reports/full/generate'),
  downloadDocx: (reportId: string) => download(`/api/reports/full/${reportId}/docx`),
  downloadPdf: (reportId: string) => download(`/api/reports/full/${reportId}/pdf`),
}

/* ── Intelligence (World Monitor Total Conversion) ─────────────────── */
export const intelligence = {
  maritime: {
    signals: () => get('/api/intelligence/maritime/signals'),
  },
  aviation: {
    military: () => get('/api/intelligence/aviation/military'),
  },
  satellites: {
    tle: () => get('/api/intelligence/satellites/tle'),
  },
  gdelt: {
    tensions: () => get('/api/intelligence/gdelt/tensions'),
  },
  infrastructure: {
    cables: () => get('/api/intelligence/infrastructure/cables'),
  },
  cii: {
    scores: () => get('/api/intelligence/cii/scores'),
  },
}

/* ── Pantheon Control Plane ───────────────────────────────────────── */
export const pantheon = {
  modules: () => get('/api/v1/pantheon/modules'),
  modulesHealth: () => get('/api/v1/pantheon/modules/health'),
  moduleDetail: (moduleId: string) => get(`/api/v1/pantheon/modules/${moduleId}`),
  registryStatus: () => get('/api/v1/pantheon/registry/status'),
  events: (
    limit = 25,
    filters?: { module?: string; eventType?: string; entityId?: string },
  ) => {
    const q = new URLSearchParams({ limit: String(limit) })
    if (filters?.module) q.set('module', filters.module)
    if (filters?.eventType) q.set('event_type', filters.eventType)
    if (filters?.entityId) q.set('entity_id', filters.entityId)
    return get(`/api/v1/pantheon/events?${q.toString()}`)
  },
  eventIntegrity: (eventId: string) =>
    get(`/api/v1/pantheon/events/${encodeURIComponent(eventId)}/integrity`),
  verifyEventsIntegrity: (eventIds: string[]) =>
    post('/api/v1/pantheon/events/verify-integrity', {
      event_ids: eventIds.slice(0, 50),
    }),
  eventById: (eventId: string) => get(`/api/v1/pantheon/events/${encodeURIComponent(eventId)}`),
  publishEvent: (payload: Record<string, unknown>) => post('/api/v1/pantheon/events', payload),
  appendAudit: (payload: Record<string, unknown>) => post('/api/v1/pantheon/audit/append', payload),
  verifyAudit: () => get('/api/v1/pantheon/audit/verify'),
  auditRecent: (limit = 20, eventType?: string) =>
    get(
      `/api/v1/pantheon/audit/recent?limit=${limit}${eventType ? `&event_type=${encodeURIComponent(eventType)}` : ''}`,
    ),
  snapshotAudit: () => post('/api/v1/pantheon/audit/snapshot'),
  latestAuditRoot: () => get('/api/v1/pantheon/audit/root/latest'),
  conditionRegistry: () => get('/api/v1/pantheon/conditions/registry'),
  evaluateConditions: (payload: Record<string, unknown>) => post('/api/v1/pantheon/conditions/evaluate', payload),
  conditionsDryRun: (payload: Record<string, unknown>) => post('/api/v1/pantheon/conditions/dry-run', payload),
  computeTax: (payload: Record<string, unknown>) => post('/api/v1/pantheon/taxon/compute', payload),
  taxonReceipts: (limit = 25) => get(`/api/v1/pantheon/taxon/receipts?limit=${limit}`),
  accessPolicy: () => get('/api/v1/pantheon/access-policy'),
  updateAccessPolicy: (policyKey: string, body: Record<string, unknown>) =>
    put(`/api/v1/pantheon/access-policy/${encodeURIComponent(policyKey)}`, body),
}
