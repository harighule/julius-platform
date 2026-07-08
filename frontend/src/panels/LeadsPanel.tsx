import { useState, useCallback } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { leads } from '../lib/api'

/* ── Types ───────────────────────────────────────────────────────────── */
interface Lead {
  id: string
  company_name: string
  legal_entity?: string
  city?: string
  state?: string
  full_address?: string
  contact_number?: string
  email?: string
  gstin?: string
  revenue?: string
  products?: string
  source?: string
  query?: string
  created_at?: string
}

interface SearchResponse {
  success: boolean
  count: number
  query: string
  leads: Lead[]
}

interface ListResponse {
  success: boolean
  count: number
  leads: Lead[]
}

/* ── Helpers ─────────────────────────────────────────────────────────── */
function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function Badge({ text, color }: { text: string; color: string }) {
  return (
    <span
      className="inline-block rounded px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest"
      style={{ background: color + '22', color }}
    >
      {text}
    </span>
  )
}

/* ── Main Component ──────────────────────────────────────────────────── */
export function LeadsPanel() {
  const [query, setQuery] = useState('rambutan buyers India')
  const [cityFilter, setCityFilter] = useState('')
  const [stateFilter, setStateFilter] = useState('')
  const [maxResults, setMaxResults] = useState(10)
  const [activeLeads, setActiveLeads] = useState<Lead[]>([])
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [notification, setNotification] = useState<string | null>(null)
  const [csvLoading, setCsvLoading] = useState(false)
  const [jsonLoading, setJsonLoading] = useState(false)

  const notify = (msg: string) => {
    setNotification(msg)
    setTimeout(() => setNotification(null), 3500)
  }

  /* search mutation */
  const searchMut = useMutation({
    mutationFn: () =>
      leads.search({
        query,
        city: cityFilter || undefined,
        state: stateFilter || undefined,
        max_results: maxResults,
        save: true,
      }) as Promise<SearchResponse>,
    onSuccess: (data) => {
      setActiveLeads(data.leads || [])
      notify(`✅ Found ${data.count} leads for "${data.query}"`)
    },
    onError: (e: unknown) => notify(`❌ Search failed: ${e instanceof Error ? e.message : String(e)}`),
  })

  /* list stored leads */
  const { data: storedData, refetch: refetchList } = useQuery({
    queryKey: ['leads-list'],
    queryFn: () =>
      leads.list({ limit: 50, city: cityFilter || undefined }) as Promise<ListResponse>,
    refetchOnWindowFocus: false,
  })

  /* delete lead */
  const deleteMut = useMutation({
    mutationFn: (id: string) => leads.deleteLead(id) as Promise<unknown>,
    onSuccess: () => {
      notify('🗑️ Lead deleted')
      refetchList()
    },
  })

  /* stats */
  const { data: statsData } = useQuery({
    queryKey: ['leads-stats'],
    queryFn: () => leads.stats() as Promise<{ total_leads: number; cities: { city: string; n: number }[] }>,
  })

  /* CSV download */
  const handleCsvDownload = useCallback(async () => {
    setCsvLoading(true)
    try {
      const blob = await leads.exportCsv(cityFilter || undefined)
      triggerDownload(blob, 'julius_b2b_leads.csv')
      notify('📥 CSV downloaded!')
    } catch {
      notify('❌ CSV export failed')
    } finally {
      setCsvLoading(false)
    }
  }, [cityFilter])

  /* JSON download */
  const handleJsonDownload = useCallback(async () => {
    setJsonLoading(true)
    try {
      const blob = await leads.exportJson(cityFilter || undefined)
      triggerDownload(blob, 'julius_b2b_leads.json')
      notify('📥 JSON downloaded!')
    } catch {
      notify('❌ JSON export failed')
    } finally {
      setJsonLoading(false)
    }
  }, [cityFilter])

  /* display leads — prefer search results, fall back to stored */
  const displayLeads: Lead[] =
    activeLeads.length > 0
      ? activeLeads
      : (storedData?.leads || [])

  return (
    <div className="relative flex flex-col h-full overflow-hidden bg-julius-bg text-julius-text">

      {/* ── Notification toast ──────────────────────────────────────── */}
      {notification && (
        <div
          className="absolute top-4 left-1/2 -translate-x-1/2 z-50 rounded-lg border border-julius-accent/40
                      bg-julius-surface2 px-6 py-3 text-xs font-semibold text-julius-accent shadow-xl
                      animate-pulse"
        >
          {notification}
        </div>
      )}

      {/* ── Header ──────────────────────────────────────────────────── */}
      <div className="shrink-0 border-b border-julius-border bg-julius-surface px-6 py-5">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-black tracking-[0.15em] text-julius-accent" style={{ fontFamily: 'monospace' }}>
              🏢 B2B LEADS INTELLIGENCE
            </h1>
            <p className="mt-0.5 text-[10px] uppercase tracking-widest text-julius-muted">
              Find · Enrich · Export Business Contacts
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Stats chips */}
            {statsData && (
              <div className="flex gap-2">
                <div className="rounded-lg border border-julius-border bg-julius-surface2 px-3 py-1.5 text-center">
                  <div className="text-lg font-black text-julius-accent">{statsData.total_leads}</div>
                  <div className="text-[8px] uppercase tracking-widest text-julius-muted">Total Leads</div>
                </div>
                <div className="rounded-lg border border-julius-border bg-julius-surface2 px-3 py-1.5 text-center">
                  <div className="text-lg font-black text-green-400">{displayLeads.length}</div>
                  <div className="text-[8px] uppercase tracking-widest text-julius-muted">Showing</div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ── Search Form ──────────────────────────────────────────── */}
        <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-5">
          <div className="col-span-2 lg:col-span-2">
            <label className="mb-1 block text-[9px] uppercase tracking-widest text-julius-muted">Search Query</label>
            <input
              id="leads-query-input"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && searchMut.mutate()}
              placeholder="e.g. rambutan buyers India"
              className="w-full rounded border border-julius-border bg-julius-bg px-3 py-2 text-xs
                         font-mono text-julius-text placeholder:text-julius-muted
                         focus:border-julius-accent/60 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-[9px] uppercase tracking-widest text-julius-muted">City</label>
            <input
              id="leads-city-input"
              value={cityFilter}
              onChange={e => setCityFilter(e.target.value)}
              placeholder="Mumbai, Delhi…"
              className="w-full rounded border border-julius-border bg-julius-bg px-3 py-2 text-xs
                         font-mono text-julius-text placeholder:text-julius-muted
                         focus:border-julius-accent/60 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-[9px] uppercase tracking-widest text-julius-muted">State</label>
            <input
              id="leads-state-input"
              value={stateFilter}
              onChange={e => setStateFilter(e.target.value)}
              placeholder="Maharashtra…"
              className="w-full rounded border border-julius-border bg-julius-bg px-3 py-2 text-xs
                         font-mono text-julius-text placeholder:text-julius-muted
                         focus:border-julius-accent/60 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-[9px] uppercase tracking-widest text-julius-muted">Max Results</label>
            <select
              id="leads-max-results"
              value={maxResults}
              onChange={e => setMaxResults(Number(e.target.value))}
              className="w-full rounded border border-julius-border bg-julius-bg px-3 py-2 text-xs
                         text-julius-text focus:border-julius-accent/60 focus:outline-none"
            >
              {[5, 10, 20, 50].map(n => (
                <option key={n} value={n}>{n} results</option>
              ))}
            </select>
          </div>
        </div>

        {/* ── Action Buttons ───────────────────────────────────────── */}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            id="leads-search-btn"
            onClick={() => searchMut.mutate()}
            disabled={!query || searchMut.isPending}
            className="flex items-center gap-2 rounded bg-julius-accent px-5 py-2 text-xs font-bold
                       uppercase tracking-widest text-white shadow-lg shadow-julius-accent/20
                       transition-all hover:brightness-110 disabled:opacity-40 active:scale-95"
          >
            {searchMut.isPending ? (
              <span className="animate-spin">⟳</span>
            ) : (
              '🔍'
            )}
            {searchMut.isPending ? 'Searching…' : 'Search Leads'}
          </button>

          <button
            id="leads-refresh-btn"
            onClick={() => refetchList()}
            className="rounded border border-julius-border bg-julius-surface2 px-4 py-2 text-xs
                       font-bold uppercase tracking-widest text-julius-muted
                       transition-all hover:border-julius-accent/40 hover:text-julius-text"
          >
            ↻ Refresh
          </button>

          {/* Divider */}
          <div className="h-6 w-px bg-julius-border mx-1" />

          {/* Download buttons */}
          <button
            id="leads-download-csv-btn"
            onClick={handleCsvDownload}
            disabled={csvLoading}
            className="flex items-center gap-1.5 rounded border border-green-500/40 bg-green-500/10 px-4 py-2
                       text-xs font-bold uppercase tracking-widest text-green-400
                       transition-all hover:bg-green-500/20 disabled:opacity-40"
          >
            {csvLoading ? <span className="animate-spin text-xs">⟳</span> : '⬇'}
            Download CSV
          </button>

          <button
            id="leads-download-json-btn"
            onClick={handleJsonDownload}
            disabled={jsonLoading}
            className="flex items-center gap-1.5 rounded border border-blue-500/40 bg-blue-500/10 px-4 py-2
                       text-xs font-bold uppercase tracking-widest text-blue-400
                       transition-all hover:bg-blue-500/20 disabled:opacity-40"
          >
            {jsonLoading ? <span className="animate-spin text-xs">⟳</span> : '⬇'}
            Download JSON
          </button>
        </div>
      </div>

      {/* ── Results Table ────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {displayLeads.length === 0 && !searchMut.isPending && (
          <div className="flex flex-col items-center justify-center py-24 text-julius-muted">
            <div className="text-5xl mb-4">🏢</div>
            <p className="text-sm font-bold">No leads found</p>
            <p className="text-[10px] mt-1">Enter a query above and click Search Leads</p>
          </div>
        )}

        {searchMut.isPending && (
          <div className="flex flex-col items-center justify-center py-24 text-julius-muted">
            <div className="animate-spin text-4xl mb-4">⟳</div>
            <p className="text-sm font-bold text-julius-accent">Scanning intelligence sources…</p>
            <p className="text-[10px] mt-1">Querying B2B directories and open data sources</p>
          </div>
        )}

        {displayLeads.length > 0 && !searchMut.isPending && (
          <div className="space-y-3">
            {/* Table header */}
            <div className="grid text-[9px] font-bold uppercase tracking-widest text-julius-muted pb-1"
                 style={{ gridTemplateColumns: '2fr 1fr 1fr 1.5fr 1.5fr 1.2fr 0.8fr auto' }}>
              <span className="pl-2">Company</span>
              <span>City / State</span>
              <span>Entity Type</span>
              <span>Contact</span>
              <span>Email</span>
              <span>GSTIN / CIN</span>
              <span>Revenue</span>
              <span></span>
            </div>

            {displayLeads.map((lead, idx) => (
              <div key={lead.id || idx}>
                {/* Row */}
                <div
                  className={`grid items-center rounded-lg border px-3 py-3 cursor-pointer transition-all
                    ${expandedId === lead.id
                      ? 'border-julius-accent/50 bg-julius-accent/5'
                      : 'border-julius-border bg-julius-surface hover:border-julius-accent/30 hover:bg-julius-surface2'
                    }`}
                  style={{ gridTemplateColumns: '2fr 1fr 1fr 1.5fr 1.5fr 1.2fr 0.8fr auto' }}
                  onClick={() => setExpandedId(expandedId === lead.id ? null : lead.id)}
                >
                  {/* Company */}
                  <div>
                    <div className="font-bold text-xs text-julius-text leading-tight">{lead.company_name}</div>
                    {lead.products && (
                      <div className="text-[9px] text-julius-muted mt-0.5 truncate max-w-[180px]">
                        {lead.products}
                      </div>
                    )}
                  </div>

                  {/* City/State */}
                  <div>
                    <div className="text-xs text-julius-text">{lead.city || '—'}</div>
                    <div className="text-[9px] text-julius-muted">{lead.state || ''}</div>
                  </div>

                  {/* Entity */}
                  <div>
                    <Badge
                      text={lead.legal_entity || 'Unknown'}
                      color={
                        (lead.legal_entity || '').includes('Private') ? '#00d4ff'
                        : (lead.legal_entity || '').includes('LLP') ? '#a78bfa'
                        : '#94a3b8'
                      }
                    />
                  </div>

                  {/* Contact */}
                  <div className="text-[10px] font-mono text-julius-text truncate">
                    {lead.contact_number || '—'}
                  </div>

                  {/* Email */}
                  <div className="text-[10px] font-mono text-julius-accent truncate">
                    {lead.email
                      ? lead.email.split(',')[0].trim()
                      : '—'}
                  </div>

                  {/* GSTIN */}
                  <div className="text-[9px] font-mono text-yellow-400 truncate">
                    {lead.gstin || '—'}
                  </div>

                  {/* Revenue */}
                  <div className="text-[9px] text-green-400">{lead.revenue || '—'}</div>

                  {/* Expand */}
                  <div className="flex items-center gap-1 ml-2">
                    <span className={`text-julius-muted text-[10px] transition-transform ${expandedId === lead.id ? 'rotate-90' : ''}`}>▶</span>
                    <button
                      id={`lead-delete-${lead.id}`}
                      onClick={e => { e.stopPropagation(); deleteMut.mutate(lead.id) }}
                      className="text-julius-muted hover:text-red-400 text-[10px] ml-1 transition-colors"
                      title="Delete lead"
                    >
                      ✕
                    </button>
                  </div>
                </div>

                {/* Expanded detail */}
                {expandedId === lead.id && (
                  <div className="mt-1 rounded-b-lg border border-t-0 border-julius-accent/30
                                  bg-julius-accent/5 px-5 py-4 grid grid-cols-2 gap-4 lg:grid-cols-3">
                    <DetailField label="Full Address" value={lead.full_address} />
                    <DetailField label="All Contact Numbers" value={lead.contact_number} />
                    <DetailField label="All Emails" value={lead.email} />
                    <DetailField label="GSTIN / CIN / LLPIN" value={lead.gstin} highlight />
                    <DetailField label="Revenue (Est.)" value={lead.revenue} highlight />
                    <DetailField label="Products Dealt In" value={lead.products} />
                    <DetailField label="Legal Entity" value={lead.legal_entity} />
                    <DetailField label="Source" value={lead.source} />
                    <DetailField label="Collected At" value={lead.created_at?.slice(0, 19).replace('T', ' ')} />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Footer ───────────────────────────────────────────────────── */}
      {displayLeads.length > 0 && (
        <div className="shrink-0 border-t border-julius-border bg-julius-surface px-6 py-3 flex items-center justify-between">
          <span className="text-[10px] text-julius-muted">
            Showing <span className="text-julius-text font-bold">{displayLeads.length}</span> leads
            {cityFilter ? ` · City: ${cityFilter}` : ''}
          </span>
          <div className="flex gap-2">
            <button
              id="leads-footer-csv-btn"
              onClick={handleCsvDownload}
              disabled={csvLoading}
              className="flex items-center gap-1.5 rounded border border-green-500/40 bg-green-500/10 px-3 py-1.5
                         text-[10px] font-bold uppercase tracking-wider text-green-400
                         transition-all hover:bg-green-500/20 disabled:opacity-40"
            >
              ⬇ CSV
            </button>
            <button
              id="leads-footer-json-btn"
              onClick={handleJsonDownload}
              disabled={jsonLoading}
              className="flex items-center gap-1.5 rounded border border-blue-500/40 bg-blue-500/10 px-3 py-1.5
                         text-[10px] font-bold uppercase tracking-wider text-blue-400
                         transition-all hover:bg-blue-500/20 disabled:opacity-40"
            >
              ⬇ JSON
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/* ── Detail field sub-component ─────────────────────────────────────── */
function DetailField({ label, value, highlight }: { label: string; value?: string | null; highlight?: boolean }) {
  return (
    <div>
      <div className="text-[8px] uppercase tracking-widest text-julius-muted mb-0.5">{label}</div>
      <div className={`text-xs font-mono break-words ${highlight ? 'text-yellow-300 font-bold' : 'text-julius-text'}`}>
        {value || <span className="text-julius-muted italic">Not available</span>}
      </div>
    </div>
  )
}
