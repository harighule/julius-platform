/**
 * JULIUS Intelligence Engine — Production UI v3
 * Uses Tailwind v4 julius-* tokens, real-time polling, full 8-category display.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'

// ─── Types ────────────────────────────────────────────────────────────────────
interface Company { symbol: string; name: string; sector: string }

interface PurchaseIntent {
  score: number; percent: number; confidence: string
  timeframe: string; narrative: string
  factors: {
    google_trend: number; news_sentiment: number; revenue_growth: number
    analyst_rating: number; prophet_forecast?: number
    fred_demand?: number; gdelt_tone?: number
  }
}
interface EnterpriseBuying {
  score: number; confidence: string
  inferred_signals: string[]
  raw_signals: { job_postings: number; github_stars: number; github_forks: number; news_sentiment: number; pe_ratio: number; sec_signals?: number }
}
interface ConsumerDemandCategory { demand_index: number; '3m_forecast': string; trend_score: number; sentiment_score: number }
interface ConsumerDemand { categories: Record<string, ConsumerDemandCategory>; most_demand: string }
interface RevenueMomentum {
  score: number; direction: string; confidence: string
  revenue_ttm: string; revenue_growth: string; earnings_growth: string
  profit_margin: string; volume_avg: string; price_4w_return: string
}
interface SupplyChain { risk_score: number; status: string; forecast: string; risk_flags: string[]; news_sentiment: number }
interface CorporateExpansion {
  expansion_score: number; confidence: string; likely_actions: string[]
  timeframe: string; job_posting_count: number; free_cash_flow: string; employee_count: string
}
interface AiAdoption {
  adoption_score: number; ai_spend_estimate: string; gpu_demand: string
  cloud_migration: string; open_source_activity: string; ai_hiring_signal: string
  github_stars: number; github_forks: number
}
interface Contact { address: string; phone: string; website: string; email: string; domain: string; employees: string; hq_country: string }
interface MacroSignals { vix: number; gold: number; oil: number; eurusd: number; risk_regime: string }
interface RedditSentiment { mention_volume: number; sentiment: number; hype_signal: string }
interface RevenueForecast { trend: string; forecast_6m_pct: string; confidence: string; rsquared: number }

// ─── Enriched Signal Types ────────────────────────────────────────────────────
interface FredSeries { latest: number; previous: number; change_pct: number; date: string; series_id: string }
interface NewsapiData { sentiment: number; article_count: number; top_headlines: string[]; source: string }
interface GdeltData { tone: number; article_count: number; top_themes: string[]; top_headlines: string[]; source: string }
interface SecEdgarData {
  detected_signals: Record<string, { keyword: string; filing_count: number }>
  signal_count: number; source: string
}
interface BlsSector { technology?: number; industrials?: number; consumer_discretionary?: number; healthcare?: number }
interface EnrichedSignals {
  fred_macro?: Record<string, FredSeries>
  fred_demand_signal?: number
  newsapi?: NewsapiData
  gdelt?: GdeltData
  sec_edgar?: SecEdgarData
  bls_sector?: BlsSector
  worldbank_demand?: number
}

interface Report {
  company: string; symbol: string; sector: string; timestamp: string; contact: Contact
  macro_signals: MacroSignals; reddit_sentiment: RedditSentiment; revenue_forecast: RevenueForecast
  purchase_intent: PurchaseIntent; enterprise_buying: EnterpriseBuying; consumer_demand: ConsumerDemand
  revenue_momentum: RevenueMomentum; supply_chain: SupplyChain; corporate_expansion: CorporateExpansion
  ai_adoption: AiAdoption
  enriched_signals?: EnrichedSignals
}
interface SectorData { score: number; signal: string; momentum: string; etf: string; '1m_return': string }
interface DbStats { total_stored_reports: number; unique_companies: number; latest_report_at: string | null }
interface LookupRecord {
  id: number; company_name: string; full_address: string; city: string; state: string
  contact_number: string; email: string; revenue: string; gstin: string
  legal_entity: string; looked_up_at: string
}

// ─── Helpers ─────────────────────────────────────────────────────────────────
const pctStr = (v: number) => `${(v * 100).toFixed(1)}%`

const scoreColor = (v: number): string =>
  v > 0.65 ? 'text-julius-green' : v > 0.42 ? 'text-julius-accent' : 'text-julius-red'

const scoreBg = (v: number): string =>
  v > 0.65 ? 'bg-julius-green' : v > 0.42 ? 'bg-julius-accent' : 'bg-julius-red'

const signalTextColor = (s: string): string => {
  if (['overweight', 'positive', 'healthy', 'rising', 'active', 'strong', 'high'].includes(s)) return 'text-julius-green'
  if (['underweight', 'negative', 'critical', 'falling', 'weak'].includes(s)) return 'text-julius-red'
  return 'text-julius-amber'
}

// ─── Sub-components ───────────────────────────────────────────────────────────
function ScoreBar({ value, label }: { value: number; label: string }) {
  const clr = scoreBg(value)
  const w = `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`
  return (
    <div className="mb-2">
      {label && (
        <div className="flex justify-between text-[10px] mb-1 text-julius-muted">
          <span>{label}</span>
          <span className={`font-bold ${scoreColor(value)}`}>{pctStr(value)}</span>
        </div>
      )}
      <div className="w-full rounded-full h-1 bg-julius-border">
        <div className={`h-1 rounded-full transition-all duration-700 ${clr} opacity-80`} style={{ width: w }} />
      </div>
    </div>
  )
}

function Badge({ text, type = 'neutral' }: { text: string; type?: 'good' | 'bad' | 'neutral' | 'accent' }) {
  const cls = type === 'good' ? 'border-julius-green/40 text-julius-green bg-julius-green/5'
    : type === 'bad' ? 'border-julius-red/40 text-julius-red bg-julius-red/5'
    : type === 'accent' ? 'border-julius-accent/40 text-julius-accent bg-julius-accent/5'
    : 'border-julius-border text-julius-muted bg-julius-surface2'
  return <span className={`text-[10px] px-2 py-0.5 rounded-full border mr-1 mb-1 inline-block ${cls}`}>{text}</span>
}

function Card({ title, icon, children, accent = false, onClick }: { title: string; icon: string; children: React.ReactNode; accent?: boolean; onClick?: () => void }) {
  return (
    <div
      onClick={onClick}
      className={`rounded-xl p-4 border transition-all duration-300 relative group ${onClick ? 'cursor-pointer hover:border-julius-accent/60 hover:bg-julius-surface2/30' : 'border-julius-border bg-julius-surface'} ${accent ? 'border-julius-accent/20 bg-julius-surface' : 'border-julius-border bg-julius-surface'}`}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-base">{icon}</span>
          <h3 className="font-display text-[10px] tracking-widest uppercase text-julius-accent">{title}</h3>
        </div>
        {onClick && (
          <span className="text-[9px] text-julius-accent/50 group-hover:text-julius-accent transition-all uppercase tracking-widest font-bold">
            Deep-Dive ⚡
          </span>
        )}
      </div>
      {children}
    </div>
  )
}

function StatBox({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div className="rounded-lg p-2 bg-julius-surface2 border border-julius-border">
      <div className={`text-xs font-bold truncate ${good === true ? 'text-julius-green' : good === false ? 'text-julius-red' : 'text-julius-accent'}`}>{value}</div>
      <div className="text-[10px] text-julius-muted mt-0.5 truncate">{label}</div>
    </div>
  )
}

function Spinner() {
  return (
    <div className="flex items-center justify-center gap-2 py-20">
      {[0, 1, 2].map(i => (
        <div key={i} className="w-2 h-2 rounded-full bg-julius-accent animate-bounce"
          style={{ animationDelay: `${i * 0.15}s` }} />
      ))}
    </div>
  )
}

function PulsingDot({ color = 'bg-julius-green' }: { color?: string }) {
  return (
    <span className="relative flex h-2 w-2">
      <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${color} opacity-75`} />
      <span className={`relative inline-flex rounded-full h-2 w-2 ${color}`} />
    </span>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function IntelligencePage() {
  const [companies, setCompanies]   = useState<Company[]>([])
  const [search, setSearch]         = useState('')
  const [selected, setSelected]     = useState<Company | null>(null)
  const [report, setReport]         = useState<Report | null>(null)
  const [sectors, setSectors]       = useState<Record<string, SectorData>>({})
  const [loading, setLoading]       = useState(false)
  const [liveUpdating, setLiveUpdating] = useState(false)
  const [error, setError]           = useState('')
  const [dbStats, setDbStats]       = useState<DbStats | null>(null)
  const [showDrop, setShowDrop]     = useState(false)
  const [lastUpdated, setLastUpdated] = useState<string>('')
  const [autoRefresh, setAutoRefresh] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Tab State ─────────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<'market' | 'company-lookup'>('market')

  // ── Deep-Dive AI States ───────────────────────────────────────────────────
  const [activeDeepDive, setActiveDeepDive] = useState<string | null>(null)
  const [deepDiveData, setDeepDiveData] = useState<{ title: string; explanation: string; engine: string } | null>(null)
  const [loadingDeepDive, setLoadingDeepDive] = useState(false)

  // ── Company Lookup States ─────────────────────────────────────────────────
  const [lookupQuery, setLookupQuery] = useState('')
  const [lookupResult, setLookupResult] = useState<LookupRecord | null>(null)
  const [lookupLoading, setLookupLoading] = useState(false)
  const [lookupError, setLookupError] = useState('')
  const [lookupHistory, setLookupHistory] = useState<LookupRecord[]>([])

  const fetchLookupHistory = useCallback(async () => {
    try {
      const r = await axios.get<{ records: LookupRecord[] }>('/api/intelligence/company-lookup/history')
      setLookupHistory(Array.isArray(r.data.records) ? r.data.records : [])
    } catch { /* ignore */ }
  }, [])

  const handleCompanyLookup = async () => {
    if (!lookupQuery.trim()) return
    setLookupLoading(true)
    setLookupError('')
    setLookupResult(null)
    try {
      const r = await axios.post<LookupRecord>('/api/intelligence/company-lookup', { query: lookupQuery })
      setLookupResult(r.data)
      fetchLookupHistory()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setLookupError(msg || 'Lookup failed — check backend connection.')
    } finally {
      setLookupLoading(false)
    }
  }

  const handleDeleteLookup = async (id: number) => {
    try {
      await axios.delete(`/api/intelligence/company-lookup/${id}`)
      fetchLookupHistory()
      if (lookupResult?.id === id) setLookupResult(null)
    } catch { /* ignore */ }
  }

  useEffect(() => { fetchLookupHistory() }, [fetchLookupHistory])

  const handleOpenDeepDive = async (category: string) => {
    if (!selected) return
    setActiveDeepDive(category)
    setLoadingDeepDive(true)
    setDeepDiveData(null)
    try {
      const res = await axios.get<{ title: string; explanation: string; engine: string }>(
        `/api/intelligence/explain/${selected.symbol}/${category}`
      )
      setDeepDiveData(res.data)
    } catch {
      setDeepDiveData({
        title: "OSINT Detailed Explanation",
        explanation: "Could not retrieve detailed AI breakdown. Check if the backend server is reachable.",
        engine: "Fallback Reporter"
      })
    } finally {
      setLoadingDeepDive(false)
    }
  }

  // ── Bootstrap ─────────────────────────────────────────────────────────────
  useEffect(() => {
    axios.get<{ companies: Company[] }>('/api/intelligence/companies')
      .then(r => setCompanies(r.data.companies))
      .catch(() => setError('Could not load company list — check backend'))

    axios.get<DbStats>('/api/intelligence/stats')
      .then(r => setDbStats(r.data))
      .catch(() => {})
  }, [])

  // ── Auto-refresh loop (every 60s when enabled) ────────────────────────────
  useEffect(() => {
    if (autoRefresh && selected) {
      intervalRef.current = setInterval(() => fetchReport(selected, true), 60_000)
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [autoRefresh, selected]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Filtered dropdown ─────────────────────────────────────────────────────
  const filtered = companies.filter(c =>
    c.name.toLowerCase().includes(search.toLowerCase()) ||
    c.symbol.toLowerCase().includes(search.toUpperCase())
  ).slice(0, 10)

  // ── Fetch report ──────────────────────────────────────────────────────────
  const fetchReport = useCallback(async (company: Company, silent = false) => {
    if (!silent) setLoading(true)
    else setLiveUpdating(true)
    setError('')
    try {
      const [reportRes, sectorRes] = await Promise.all([
        axios.get<{ reports: Report[]; sector_rotation: Record<string, SectorData> }>(
          `/api/intelligence/report?symbol=${company.symbol}`
        ),
        axios.get<{ sector_rotation: Record<string, SectorData> }>('/api/intelligence/sector-rotation')
      ])
      if (reportRes.data.reports.length === 0) {
        setError(`No data available for ${company.symbol}`)
        return
      }
      setReport(reportRes.data.reports[0])
      setSectors(reportRes.data.sector_rotation || sectorRes.data.sector_rotation || {})
      setLastUpdated(new Date().toLocaleTimeString())
      // Refresh stats
      axios.get<DbStats>('/api/intelligence/stats').then(r => setDbStats(r.data)).catch(() => {})
    } catch (e: unknown) {
      const msg = axios.isAxiosError(e) && e.response?.data?.detail
        ? e.response.data.detail
        : 'Analysis request failed — is the backend running?'
      setError(msg)
    } finally {
      setLoading(false)
      setLiveUpdating(false)
    }
  }, [])

  const handleAnalyse = () => {
    if (selected) {
      fetchReport(selected)
    } else if (search.trim()) {
      const query = search.trim()
      const dummyCompany: Company = {
        symbol: query,
        name: query,
        sector: 'Global Brand'
      }
      fetchReport(dummyCompany)
    }
  }

  const handleRefreshDb = async () => {
    try {
      await axios.post('/api/intelligence/refresh?limit=50')
      setError('')
    } catch { setError('Refresh trigger failed') }
  }

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen p-5 bg-julius-bg text-julius-text font-mono">

      {/* ── HEADER ─────────────────────────────────────────────────────── */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between mb-6 gap-3">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-display text-xl font-black tracking-widest text-julius-accent glow-cyan">
              ◈ INTELLIGENCE ENGINE
            </h1>
            {liveUpdating && activeTab === 'market' && (
              <div className="flex items-center gap-1.5 text-[10px] text-julius-green">
                <PulsingDot />
                <span>LIVE</span>
              </div>
            )}
          </div>
          <p className="text-[10px] text-julius-muted mt-1 tracking-wider">
            REAL-TIME COMMERCIAL INTELLIGENCE · 8-CATEGORY PREDICTION MATRIX · S&P 500
          </p>
        </div>

        {/* Stats bar */}
        <div className="flex flex-wrap items-center gap-3 text-[10px] text-julius-muted">
          {dbStats && activeTab === 'market' && (
            <>
              <span className="flex items-center gap-1">
                <PulsingDot color="bg-julius-accent" />
                {dbStats.total_stored_reports.toLocaleString()} cached reports
              </span>
              <span>🏢 {dbStats.unique_companies} companies</span>
              {lastUpdated && <span className="text-julius-green">↻ {lastUpdated}</span>}
            </>
          )}
          {activeTab === 'market' && (
            <>
              <button
                onClick={() => setAutoRefresh(v => !v)}
                className={`px-2.5 py-1 rounded border text-[10px] transition-all ${autoRefresh ? 'border-julius-green/50 text-julius-green bg-julius-green/5' : 'border-julius-border text-julius-muted hover:border-julius-accent/50'}`}
              >
                {autoRefresh ? '⏸ Auto-Refresh ON' : '▶ Auto-Refresh'}
              </button>
              <button
                onClick={handleRefreshDb}
                className="px-2.5 py-1 rounded border border-julius-border text-julius-muted hover:border-julius-accent/50 hover:text-julius-accent text-[10px] transition-all"
              >
                ⟳ Refresh DB
              </button>
            </>
          )}
        </div>
      </div>

      {/* ── TAB BAR ─────────────────────────────────────────────────────── */}
      <div className="flex gap-4 mb-6 border-b border-julius-border pb-3">
        <button
          onClick={() => setActiveTab('market')}
          className={`pb-2 px-1 text-sm font-bold tracking-wider uppercase transition-all border-b-2 ${
            activeTab === 'market'
              ? 'border-julius-accent text-julius-accent'
              : 'border-transparent text-julius-muted hover:text-julius-text'
          }`}
        >
          ◈ Market Intelligence
        </button>
        <button
          onClick={() => setActiveTab('company-lookup')}
          className={`pb-2 px-1 text-sm font-bold tracking-wider uppercase transition-all border-b-2 ${
            activeTab === 'company-lookup'
              ? 'border-julius-accent text-julius-accent'
              : 'border-transparent text-julius-muted hover:text-julius-text'
          }`}
        >
          🏢 Live Company OSINT Lookup
        </button>
      </div>

      {activeTab === 'market' && (
        <>
          {/* ── SEARCH ─────────────────────────────────────────────────────── */}
      <div className="flex gap-3 mb-5 max-w-2xl">
        <div className="relative flex-1">
          <input
            id="intel-search"
            type="text"
            placeholder="Search company or ticker — AAPL, Tesla, NVDA..."
            value={search}
            onChange={e => { setSearch(e.target.value); setShowDrop(true) }}
            onFocus={() => setShowDrop(true)}
            onBlur={() => setTimeout(() => setShowDrop(false), 160)}
            className="w-full px-4 py-3 rounded-lg text-sm bg-julius-surface border border-julius-border text-julius-text outline-none focus:border-julius-accent/60 transition-all placeholder:text-julius-muted"
          />
          {selected && search && (
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-julius-accent font-bold">
              {selected.symbol}
            </span>
          )}
          {showDrop && search && filtered.length > 0 && (
            <div className="absolute z-50 w-full mt-1 rounded-lg overflow-hidden bg-julius-surface border border-julius-border shadow-2xl">
              {filtered.map(c => (
                <button
                  key={c.symbol}
                  onMouseDown={() => { setSelected(c); setSearch(`${c.name} (${c.symbol})`); setShowDrop(false) }}
                  className="w-full flex justify-between items-center px-4 py-2.5 text-xs text-left border-b border-julius-border hover:bg-julius-surface2 transition-all"
                >
                  <div>
                    <span className="text-julius-text font-medium">{c.name}</span>
                    <span className="text-[10px] text-julius-muted ml-2">{c.sector}</span>
                  </div>
                  <span className="font-bold text-julius-accent text-[11px]">{c.symbol}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <button
          id="intel-analyse-btn"
          onClick={handleAnalyse}
          disabled={loading || !search.trim()}
          className="px-6 py-3 rounded-lg font-bold text-sm bg-julius-accent text-black hover:opacity-90 disabled:opacity-40 transition-all min-w-[120px]"
        >
          {loading ? '⟳ Scanning…' : '⚡ Analyse'}
        </button>
      </div>

      {/* ── ERROR ──────────────────────────────────────────────────────── */}
      {error && (
        <div className="mb-4 px-4 py-3 rounded-lg text-xs border border-julius-red/40 bg-julius-red/5 text-julius-red">
          ⚠ {error}
        </div>
      )}

      {loading && <Spinner />}

      {/* ── REPORT ─────────────────────────────────────────────────────── */}
      {report && !loading && (
        <div className="space-y-5">

          {/* Company header */}
          <div className="rounded-xl border border-julius-border bg-julius-surface p-5 flex flex-col lg:flex-row lg:items-start justify-between gap-5">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <span className="font-display text-2xl font-black text-julius-accent glow-cyan">{report.symbol}</span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-julius-surface2 border border-julius-border text-julius-muted">{report.sector}</span>
                {autoRefresh && <span className="flex items-center gap-1 text-[10px] text-julius-green"><PulsingDot /> LIVE</span>}
              </div>
              <h2 className="text-base font-bold text-julius-text">{report.company}</h2>
              <p className="text-[10px] text-julius-muted mt-1">
                Last analysed: {new Date(report.timestamp).toLocaleString()} · Source: public market data
              </p>
            </div>

            {/* Corporate contact */}
            {report.contact && (
              <div className="rounded-lg p-4 bg-julius-surface2 border border-julius-border min-w-[260px]">
                <div className="text-[10px] font-bold text-julius-accent mb-2 tracking-widest">◈ CORPORATE CONTACT</div>
                <div className="space-y-1 text-[11px] text-julius-muted">
                  <div className="flex gap-2"><span>📍</span><span className="break-all">{report.contact.address || 'N/A'}</span></div>
                  <div className="flex gap-2"><span>📞</span><span>{report.contact.phone || 'N/A'}</span></div>
                  <div className="flex gap-2">
                    <span>🌐</span>
                    {report.contact.website && report.contact.website !== 'N/A'
                      ? <a href={report.contact.website} target="_blank" rel="noreferrer" className="text-julius-accent hover:underline">{report.contact.domain}</a>
                      : <span>N/A</span>
                    }
                  </div>
                  <div className="flex gap-2"><span>✉</span><span>{report.contact.email || 'N/A'}</span></div>
                  <div className="flex gap-2"><span>👥</span><span>{report.contact.employees || 'N/A'} employees · {report.contact.hq_country || 'N/A'}</span></div>
                </div>
              </div>
            )}

            {/* Macro & Social Indicators */}
            {report.macro_signals && report.reddit_sentiment && (
              <div className="rounded-lg p-4 bg-julius-surface2 border border-julius-border min-w-[260px] flex-1 lg:max-w-[340px]">
                <div className="text-[10px] font-bold text-julius-accent mb-2 tracking-widest">◈ MACRO & SOCIAL TRACKER</div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] text-julius-muted">
                  <div>VIX Index: <span className="text-julius-text font-bold">{report.macro_signals?.vix?.toFixed(1) || 'N/A'}</span></div>
                  <div>Gold Spot: <span className="text-julius-text font-bold">${report.macro_signals?.gold?.toFixed(0) || 'N/A'}</span></div>
                  <div>Crude Oil: <span className="text-julius-text font-bold">${report.macro_signals?.oil?.toFixed(1) || 'N/A'}</span></div>
                  <div>EUR/USD: <span className="text-julius-text font-bold">{report.macro_signals?.eurusd?.toFixed(3) || 'N/A'}</span></div>
                  <div className="col-span-2 border-t border-julius-border/40 my-1"></div>
                  <div>Reddit Posts: <span className="text-julius-text font-bold">{report.reddit_sentiment?.mention_volume ?? 0}</span></div>
                  <div>Sentiment: <span className={`font-bold ${report.reddit_sentiment?.sentiment > 0.05 ? 'text-julius-green' : report.reddit_sentiment?.sentiment < -0.05 ? 'text-julius-red' : 'text-julius-text'}`}>{report.reddit_sentiment?.sentiment?.toFixed(2) ?? '0.00'}</span></div>
                  <div className="col-span-2">
                    Regime: <span className={`font-bold uppercase ${report.macro_signals?.risk_regime === 'risk-on' ? 'text-julius-green' : 'text-julius-red'}`}>{report.macro_signals?.risk_regime || 'N/A'}</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* 8-Category Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">

            {/* 1 — Purchase Intent */}
            <Card title="Purchase Intent Forecast" icon="🎯" accent onClick={() => handleOpenDeepDive('purchase_intent')}>
              <div className={`text-4xl font-black mb-1 font-display ${scoreColor(report.purchase_intent.score)}`}>
                {report.purchase_intent.percent}%
              </div>
              <div className="flex flex-wrap mb-3">
                <Badge text={report.purchase_intent?.confidence?.toUpperCase() || 'UNKNOWN'} type={report.purchase_intent?.score > 0.65 ? 'good' : report.purchase_intent?.score > 0.42 ? 'accent' : 'bad'} />
                <Badge text={`⏱ ${report.purchase_intent.timeframe}`} type="neutral" />
              </div>
              <p className="text-[11px] text-julius-muted leading-relaxed mb-3">{report.purchase_intent.narrative}</p>
              <ScoreBar value={report.purchase_intent.factors.google_trend} label="Google Trend Signal" />
              <ScoreBar value={Math.max(0, (report.purchase_intent.factors.news_sentiment + 1) / 2)} label="NewsAPI Sentiment" />
              <ScoreBar value={Math.min(1, report.purchase_intent.factors.revenue_growth * 3 + 0.3)} label="Revenue Growth Signal" />
              <ScoreBar value={report.purchase_intent.factors.analyst_rating} label="Analyst Consensus" />
              {report.purchase_intent.factors.fred_demand != null && (
                <ScoreBar value={report.purchase_intent.factors.fred_demand} label="FRED Macro Demand" />
              )}
              {report.purchase_intent.factors.gdelt_tone != null && (
                <ScoreBar value={Math.max(0, (report.purchase_intent.factors.gdelt_tone + 1) / 2)} label="GDELT Geopolitical Tone" />
              )}
            </Card>

            {/* 2 — Enterprise Buying Signals */}
            <Card title="Enterprise Buying Signals" icon="🏢" onClick={() => handleOpenDeepDive('enterprise_buying')}>
              <div className={`text-4xl font-black mb-1 font-display ${scoreColor(report.enterprise_buying.score)}`}>
                {pctStr(report.enterprise_buying.score)}
              </div>
              <div className="flex flex-wrap mb-3">
                <Badge text={report.enterprise_buying?.confidence?.toUpperCase() || 'UNKNOWN'} type={report.enterprise_buying?.score > 0.6 ? 'good' : 'neutral'} />
              </div>
              <div className="space-y-1 mb-3">
                {report.enterprise_buying.inferred_signals.map((s, i) => (
                  <div key={i} className="text-[11px] flex items-start gap-2">
                    <span className="text-julius-accent mt-0.5">›</span>
                    <span className="text-julius-muted">{s}</span>
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-3 gap-2">
                <StatBox label="Job Posts" value={report.enterprise_buying.raw_signals.job_postings.toLocaleString()} />
                <StatBox label="GH Stars" value={report.enterprise_buying.raw_signals.github_stars.toLocaleString()} />
                <StatBox label="GH Forks" value={report.enterprise_buying.raw_signals.github_forks.toLocaleString()} />
              </div>
            </Card>

            {/* 3 — Consumer Category Demand */}
            <Card title="Consumer Category Demand" icon="📊" onClick={() => handleOpenDeepDive('consumer_demand')}>
              <div className="text-[11px] text-julius-muted mb-3">
                Highest demand: <span className="text-julius-green font-bold">{report.consumer_demand.most_demand}</span>
              </div>
              <div className="space-y-1 max-h-52 overflow-y-auto pr-1">
                {Object.entries(report.consumer_demand.categories).map(([cat, d]) => (
                  <div key={cat}>
                    <div className="flex justify-between text-[10px] mb-0.5">
                      <span className="text-julius-text capitalize">{cat}</span>
                      <span className={`font-bold ${signalTextColor(d['3m_forecast'])}`}>{d['3m_forecast']}</span>
                    </div>
                    <ScoreBar value={d.demand_index} label="" />
                  </div>
                ))}
              </div>
            </Card>

            {/* 4 — Revenue Momentum */}
            <Card title="Revenue Momentum" icon="📈" onClick={() => handleOpenDeepDive('revenue_momentum')}>
              <div className="flex items-baseline gap-3 mb-3">
                <span className={`text-2xl font-black font-display uppercase ${scoreColor(report.revenue_momentum.score)}`}>
                  {report.revenue_momentum.direction}
                </span>
                <Badge text={report.revenue_momentum?.confidence?.toUpperCase() || 'UNKNOWN'} type={report.revenue_momentum?.score > 0.6 ? 'good' : 'neutral'} />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <StatBox label="Revenue TTM" value={report.revenue_momentum.revenue_ttm} />
                <StatBox label="4W Return" value={report.revenue_momentum.price_4w_return} good={report.revenue_momentum.price_4w_return.startsWith('-') ? false : true} />
                <StatBox label="Rev Growth" value={report.revenue_momentum.revenue_growth} good={parseFloat(report.revenue_momentum.revenue_growth) > 0 ? true : false} />
                <StatBox label="EPS Growth" value={report.revenue_momentum.earnings_growth} good={parseFloat(report.revenue_momentum.earnings_growth) > 0 ? true : false} />
                <StatBox label="Margin" value={report.revenue_momentum.profit_margin} />
                <StatBox label="Avg Volume" value={report.revenue_momentum.volume_avg} />
              </div>

              {report.revenue_forecast && (
                <div className="mt-3 pt-3 border-t border-julius-border/40 text-[10px] text-julius-muted space-y-1">
                  <div className="font-bold text-julius-accent uppercase tracking-wider">6-Month Trend Forecast</div>
                  <div className="flex justify-between">
                    <span>Forecast 6M Change:</span>
                    <span className={`font-bold ${report.revenue_forecast.trend === 'upward' ? 'text-julius-green' : report.revenue_forecast.trend === 'downward' ? 'text-julius-red' : 'text-julius-text'}`}>
                      {report.revenue_forecast.forecast_6m_pct} ({report.revenue_forecast.trend})
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Model Confidence (R²):</span>
                    <span className="font-bold text-julius-text">{report.revenue_forecast?.confidence?.toUpperCase() || 'UNKNOWN'} ({report.revenue_forecast?.rsquared ?? 0.0})</span>
                  </div>
                </div>
              )}
            </Card>

            {/* 5 — Supply Chain */}
            <Card title="Supply Chain Intelligence" icon="⛓️" onClick={() => handleOpenDeepDive('supply_chain')}>
              <div className={`text-2xl font-black font-display mb-2 ${signalTextColor(report.supply_chain.status)}`}>
                {report.supply_chain?.status?.toUpperCase()?.replace(/_/g, ' ') || 'UNKNOWN'}
              </div>
              <ScoreBar value={report.supply_chain.risk_score} label="Risk Score" />
              <div className="mt-2 space-y-1">
                {report.supply_chain.risk_flags.map((f, i) => (
                  <div key={i} className="text-[11px] flex items-start gap-2">
                    <span className={report.supply_chain.risk_score > 0.55 ? 'text-julius-red' : 'text-julius-amber'}>⚑</span>
                    <span className="text-julius-muted">{f}</span>
                  </div>
                ))}
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <StatBox label="News Sentiment" value={report.supply_chain.news_sentiment.toFixed(3)} good={report.supply_chain.news_sentiment > 0 ? true : false} />
                <StatBox label="Forecast" value={report.supply_chain.forecast} good={report.supply_chain.forecast === 'stable' ? true : false} />
              </div>
            </Card>

            {/* 6 — Corporate Expansion */}
            <Card title="Corporate Expansion Score" icon="🌍" onClick={() => handleOpenDeepDive('corporate_expansion')}>
              <div className={`text-4xl font-black mb-1 font-display ${scoreColor(report.corporate_expansion.expansion_score)}`}>
                {pctStr(report.corporate_expansion.expansion_score)}
              </div>
              <div className="flex flex-wrap mb-3">
                <Badge text={report.corporate_expansion?.confidence?.toUpperCase() || 'UNKNOWN'} type={report.corporate_expansion?.expansion_score > 0.65 ? 'good' : 'neutral'} />
                <Badge text={`⏱ ${report.corporate_expansion.timeframe}`} />
              </div>
              <div className="space-y-1 mb-3">
                {report.corporate_expansion.likely_actions.map((a, i) => (
                  <div key={i} className="text-[11px] flex items-start gap-2">
                    <span className="text-julius-green">✓</span>
                    <span className="text-julius-muted">{a}</span>
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-2">
                <StatBox label="Job Posts" value={report.corporate_expansion.job_posting_count.toLocaleString()} />
                <StatBox label="Free Cash Flow" value={report.corporate_expansion.free_cash_flow} />
              </div>
            </Card>

            {/* 7 — AI Adoption */}
            <Card title="AI Adoption Intelligence" icon="🤖" onClick={() => handleOpenDeepDive('ai_adoption')}>
              <div className={`text-4xl font-black mb-1 font-display ${scoreColor(report.ai_adoption.adoption_score)}`}>
                {pctStr(report.ai_adoption.adoption_score)}
              </div>
              <ScoreBar value={report.ai_adoption.adoption_score} label="Adoption Score" />
              <div className="grid grid-cols-2 gap-2 mt-2">
                <StatBox label="AI Spend Est." value={report.ai_adoption.ai_spend_estimate} />
                <StatBox label="GPU Demand" value={report.ai_adoption?.gpu_demand?.toUpperCase() || 'UNKNOWN'} good={report.ai_adoption?.gpu_demand === 'high' ? true : undefined} />
                <StatBox label="Cloud Migration" value={report.ai_adoption.cloud_migration} />
                <StatBox label="AI Hiring" value={report.ai_adoption.ai_hiring_signal} good={report.ai_adoption.ai_hiring_signal === 'strong' ? true : undefined} />
                <StatBox label="GitHub Stars" value={report.ai_adoption.github_stars.toLocaleString()} />
                <StatBox label="GitHub Forks" value={report.ai_adoption.github_forks.toLocaleString()} />
              </div>
            </Card>

            {/* 8 — Sector Rotation (wide) */}
            {Object.keys(sectors).length > 0 && (
              <div className="md:col-span-2 xl:col-span-3">
                <Card title="Sector Rotation Signals — Live ETF Momentum" icon="🔄">
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-2">
                    {Object.entries(sectors).map(([sector, d]) => (
                      <div
                        key={sector}
                        className="rounded-lg px-3 py-2.5 border border-julius-border bg-julius-surface2 flex flex-col gap-1"
                      >
                        <div className="text-[11px] font-bold text-julius-text truncate">{sector}</div>
                        <div className={`text-xs font-black uppercase ${signalTextColor(d.signal)}`}>{d.signal}</div>
                        <div className="text-[10px] text-julius-muted">{d.etf} · {d['1m_return']}</div>
                        <div className="w-full h-0.5 rounded-full bg-julius-border mt-1">
                          <div
                            className={`h-0.5 rounded-full ${d.signal === 'overweight' ? 'bg-julius-green' : d.signal === 'underweight' ? 'bg-julius-red' : 'bg-julius-amber'}`}
                            style={{ width: `${Math.round(d.score * 100)}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              </div>
            )}

            {/* ── ENRICHED SIGNALS SECTION ─────────────────────────────────── */}
            {report.enriched_signals && Object.keys(report.enriched_signals).length > 0 && (
              <div className="md:col-span-2 xl:col-span-3">
                <div className="text-[10px] font-bold text-julius-accent tracking-widest uppercase mb-3 flex items-center gap-2">
                  <span className="opacity-60">━━━━</span>
                  ◈ EXTENDED INTELLIGENCE LAYER — FRED · GDELT · SEC EDGAR · BLS · WORLD BANK
                  <span className="opacity-60">━━━━</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">

                  {/* FRED Macro Dashboard */}
                  {report.enriched_signals.fred_macro && (
                    <Card title="FRED Macro Dashboard" icon="🏛️">
                      <div className="flex items-center gap-2 mb-3">
                        <div className={`text-2xl font-black font-display ${
                          (report.enriched_signals.fred_demand_signal ?? 0.5) > 0.65 ? 'text-julius-green'
                          : (report.enriched_signals.fred_demand_signal ?? 0.5) > 0.42 ? 'text-julius-accent'
                          : 'text-julius-red'
                        }`}>
                          {(((report.enriched_signals.fred_demand_signal ?? 0.5)) * 100).toFixed(1)}%
                        </div>
                        <div className="text-[10px] text-julius-muted">Consumer Demand Index</div>
                      </div>
                      <ScoreBar value={report.enriched_signals.fred_demand_signal ?? 0.5} label="Overall FRED Demand Signal" />
                      <div className="space-y-1.5 mt-2">
                        {Object.entries(report.enriched_signals.fred_macro).slice(0, 6).map(([key, val]) => (
                          <div key={key} className="flex justify-between items-center text-[10px]">
                            <span className="text-julius-muted capitalize">{key.replace(/_/g, ' ')}</span>
                            <div className="flex items-center gap-2">
                              <span className="text-julius-text font-bold">{val?.latest ?? 'N/A'}</span>
                              {val?.change_pct != null && (
                                <span className={`font-bold ${
                                  val.change_pct > 0 ? 'text-julius-green' : val.change_pct < 0 ? 'text-julius-red' : 'text-julius-muted'
                                }`}>
                                  {val.change_pct > 0 ? '▲' : '▼'} {Math.abs(val.change_pct).toFixed(2)}%
                                </span>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                      <div className="mt-2 text-[9px] text-julius-muted border-t border-julius-border/40 pt-2">Source: Federal Reserve Economic Data (FRED)</div>
                    </Card>
                  )}

                  {/* GDELT Geopolitical Signals */}
                  {report.enriched_signals.gdelt && (
                    <Card title="GDELT Geopolitical Events" icon="🌐">
                      <div className="flex items-center gap-3 mb-3">
                        <div className={`text-2xl font-black font-display ${
                          (report.enriched_signals.gdelt.tone ?? 0) > 0.1 ? 'text-julius-green'
                          : (report.enriched_signals.gdelt.tone ?? 0) < -0.1 ? 'text-julius-red'
                          : 'text-julius-accent'
                        }`}>
                          {(report.enriched_signals.gdelt.tone ?? 0) > 0.1 ? '↑ Positive' :
                           (report.enriched_signals.gdelt.tone ?? 0) < -0.1 ? '↓ Negative' : '→ Neutral'}
                        </div>
                        <Badge
                          text={`${report.enriched_signals.gdelt.article_count} articles`}
                          type="neutral"
                        />
                      </div>
                      <ScoreBar
                        value={Math.max(0, ((report.enriched_signals.gdelt.tone ?? 0) + 1) / 2)}
                        label="Geopolitical Tone Score"
                      />
                      {report.enriched_signals.gdelt.top_themes.length > 0 && (
                        <div className="mt-2">
                          <div className="text-[10px] text-julius-muted mb-1">Top Event Themes:</div>
                          <div className="flex flex-wrap gap-1">
                            {report.enriched_signals.gdelt.top_themes.slice(0, 5).map((theme, i) => (
                              <Badge key={i} text={theme.replace(/_/g, ' ').toLowerCase()} type="neutral" />
                            ))}
                          </div>
                        </div>
                      )}
                      {report.enriched_signals.gdelt.top_headlines.length > 0 && (
                        <div className="mt-2 space-y-1">
                          {report.enriched_signals.gdelt.top_headlines.map((h, i) => (
                            <div key={i} className="text-[10px] text-julius-muted flex gap-1">
                              <span className="text-julius-accent">›</span>
                              <span className="line-clamp-1">{h}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      <div className="mt-2 text-[9px] text-julius-muted border-t border-julius-border/40 pt-2">Source: GDELT Global Knowledge Graph — 65+ languages</div>
                    </Card>
                  )}

                  {/* SEC EDGAR Filing Evidence */}
                  {report.enriched_signals.sec_edgar && (
                    <Card title="SEC EDGAR Filing Evidence" icon="📋">
                      <div className="flex items-center gap-3 mb-3">
                        <div className={`text-2xl font-black font-display ${
                          (report.enriched_signals.sec_edgar.signal_count ?? 0) >= 3 ? 'text-julius-green'
                          : (report.enriched_signals.sec_edgar.signal_count ?? 0) >= 1 ? 'text-julius-accent'
                          : 'text-julius-muted'
                        }`}>
                          {report.enriched_signals.sec_edgar.signal_count ?? 0}
                        </div>
                        <div className="text-[10px] text-julius-muted">Confirmed Buying Signals<br/>from 10-K / 8-K Filings</div>
                      </div>
                      {Object.keys(report.enriched_signals.sec_edgar.detected_signals ?? {}).length > 0 ? (
                        <div className="space-y-2">
                          {Object.entries(report.enriched_signals.sec_edgar.detected_signals).map(([sig, info]) => (
                            <div key={sig} className="rounded-lg p-2 bg-julius-surface2 border border-julius-green/20">
                              <div className="flex justify-between items-center">
                                <span className="text-[10px] font-bold text-julius-green capitalize">{sig.replace(/_/g, ' ')}</span>
                                <Badge text={`${info.filing_count} filings`} type="good" />
                              </div>
                              <div className="text-[9px] text-julius-muted mt-0.5">Keyword: "{info.keyword}"</div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-[11px] text-julius-muted text-center py-4">No confirmed SEC filing signals found</div>
                      )}
                      <div className="mt-2 text-[9px] text-julius-muted border-t border-julius-border/40 pt-2">Source: SEC EDGAR Full-Text Search — 10-K, 8-K</div>
                    </Card>
                  )}

                  {/* BLS Sector Employment */}
                  {report.enriched_signals.bls_sector && Object.keys(report.enriched_signals.bls_sector).length > 0 && (
                    <Card title="BLS Sector Employment" icon="👷">
                      <div className="text-[11px] text-julius-muted mb-3">US Labor Bureau hiring momentum by sector</div>
                      <div className="space-y-2">
                        {Object.entries(report.enriched_signals.bls_sector).map(([sector, score]) => (
                          <div key={sector}>
                            <ScoreBar
                              value={score as number}
                              label={`${sector.replace(/_/g, ' ')} sector`}
                            />
                          </div>
                        ))}
                      </div>
                      <div className="mt-3 grid grid-cols-2 gap-2">
                        {Object.entries(report.enriched_signals.bls_sector).map(([sector, score]) => (
                          <StatBox
                            key={sector}
                            label={sector.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                            value={(score as number) > 0.6 ? '↑ Expanding' : (score as number) < 0.4 ? '↓ Contracting' : '→ Stable'}
                            good={(score as number) > 0.6 ? true : (score as number) < 0.4 ? false : undefined}
                          />
                        ))}
                      </div>
                      <div className="mt-2 text-[9px] text-julius-muted border-t border-julius-border/40 pt-2">Source: US Bureau of Labor Statistics API</div>
                    </Card>
                  )}

                  {/* World Bank Country Demand */}
                  {report.enriched_signals.worldbank_demand != null && (
                    <Card title="World Bank Demand Index" icon="🌍">
                      <div className="flex items-center gap-3 mb-3">
                        <div className={`text-3xl font-black font-display ${
                          report.enriched_signals.worldbank_demand > 0.65 ? 'text-julius-green'
                          : report.enriched_signals.worldbank_demand > 0.42 ? 'text-julius-accent'
                          : 'text-julius-red'
                        }`}>
                          {(report.enriched_signals.worldbank_demand * 100).toFixed(1)}%
                        </div>
                        <div className="text-[10px] text-julius-muted">
                          Consumer Demand Index<br/>
                          <span className="text-julius-accent font-bold">{report.contact?.hq_country || 'Global'}</span>
                        </div>
                      </div>
                      <ScoreBar value={report.enriched_signals.worldbank_demand} label="Country Demand Score" />
                      <div className="mt-3 text-[10px] text-julius-muted space-y-1">
                        <div>Composite of: GDP per capita · Internet penetration · Inflation rate</div>
                        <div className="flex gap-2 mt-2">
                          <Badge
                            text={report.enriched_signals.worldbank_demand > 0.65 ? 'High Demand Market' :
                                  report.enriched_signals.worldbank_demand > 0.42 ? 'Moderate Market' : 'Emerging Market'}
                            type={report.enriched_signals.worldbank_demand > 0.65 ? 'good' :
                                  report.enriched_signals.worldbank_demand > 0.42 ? 'accent' : 'neutral'}
                          />
                        </div>
                      </div>
                      <div className="mt-2 text-[9px] text-julius-muted border-t border-julius-border/40 pt-2">Source: World Bank Data360 WDI Database</div>
                    </Card>
                  )}

                  {/* NewsAPI Headlines */}
                  {report.enriched_signals.newsapi && report.enriched_signals.newsapi.article_count > 0 && (
                    <Card title="NewsAPI Live Headlines" icon="📰">
                      <div className="flex items-center gap-3 mb-3">
                        <div className={`text-2xl font-black font-display ${
                          (report.enriched_signals.newsapi.sentiment ?? 0) > 0.05 ? 'text-julius-green'
                          : (report.enriched_signals.newsapi.sentiment ?? 0) < -0.05 ? 'text-julius-red'
                          : 'text-julius-accent'
                        }`}>
                          {((report.enriched_signals.newsapi.sentiment ?? 0) >= 0 ? '+' : '')}{(report.enriched_signals.newsapi.sentiment ?? 0).toFixed(3)}
                        </div>
                        <div className="text-[10px] text-julius-muted">
                          Sentiment Score<br/>
                          <span className="text-julius-text font-bold">{report.enriched_signals.newsapi.article_count}</span> articles analysed
                        </div>
                      </div>
                      <ScoreBar
                        value={Math.max(0, ((report.enriched_signals.newsapi.sentiment ?? 0) + 1) / 2)}
                        label="Aggregate News Sentiment"
                      />
                      {report.enriched_signals.newsapi.top_headlines.length > 0 && (
                        <div className="mt-2 space-y-1.5">
                          <div className="text-[10px] text-julius-muted mb-1">Top Headlines:</div>
                          {report.enriched_signals.newsapi.top_headlines.map((h, i) => (
                            <div key={i} className="text-[10px] text-julius-muted flex gap-1">
                              <span className="text-julius-accent font-bold">{i + 1}.</span>
                              <span className="line-clamp-2">{h}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      <div className="mt-2 text-[9px] text-julius-muted border-t border-julius-border/40 pt-2">Source: NewsAPI.org — Authenticated, 24h cached</div>
                    </Card>
                  )}

                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Empty state ─────────────────────────────────────────────────── */}
      {!report && !loading && (
        <div className="text-center py-24">
          <div className="text-6xl mb-5 text-julius-accent opacity-20 font-display">◈</div>
          <div className="font-display text-lg tracking-widest text-julius-muted">SELECT A COMPANY TO BEGIN</div>
          <p className="text-[11px] text-julius-muted mt-2">
            8-category intelligence · purchase intent · AI signals · sector rotation · corporate contacts
          </p>
          <div className="flex flex-wrap justify-center gap-2 mt-5">
            {['AAPL', 'MSFT', 'NVDA', 'TSLA', 'GOOGL', 'AMZN', 'META'].map(sym => (
              <button
                key={sym}
                onClick={() => {
                  const c = companies.find(co => co.symbol === sym)
                  if (c) { setSelected(c); setSearch(`${c.name} (${c.symbol})`) }
                }}
                className="px-3 py-1.5 rounded border border-julius-border text-julius-muted text-xs hover:border-julius-accent/50 hover:text-julius-accent transition-all"
              >
                {sym}
              </button>
            ))}
          </div>
        </div>
      )}
        </>
      )}

      {/* ── LIVE COMPANY OSINT LOOKUP TAB ─────────────────────────────────── */}
      {activeTab === 'company-lookup' && (
        <div className="space-y-6">
          <div className="rounded-xl border border-julius-border bg-julius-surface p-5">
            <h2 className="text-sm font-bold text-julius-accent uppercase tracking-widest mb-3">🔍 Live Company Signal Extraction</h2>
            <div className="flex flex-col md:flex-row gap-3">
              <input
                id="lookup-query-input"
                type="text"
                placeholder="Enter company name (e.g. TCS, Anusaya Fresh, Rakesh Fruit)..."
                value={lookupQuery}
                onChange={e => setLookupQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleCompanyLookup()}
                className="flex-1 px-4 py-3 rounded-lg text-sm bg-julius-bg border border-julius-border text-julius-text outline-none focus:border-julius-accent/60 transition-all placeholder:text-julius-muted"
              />
              <button
                id="lookup-search-btn"
                onClick={handleCompanyLookup}
                disabled={lookupLoading || !lookupQuery.trim()}
                className="px-6 py-3 rounded-lg font-bold text-sm bg-julius-accent text-black hover:opacity-90 disabled:opacity-40 transition-all min-w-[150px]"
              >
                {lookupLoading ? '⟳ Extracting...' : '⚡ Search & Extract'}
              </button>
            </div>
            {lookupError && (
              <div className="mt-3 px-4 py-2 rounded border border-julius-red/30 bg-julius-red/5 text-julius-red text-xs">⚠ {lookupError}</div>
            )}
          </div>

          {lookupLoading && <Spinner />}

          {lookupResult && !lookupLoading && (
            <div className="rounded-xl border border-julius-accent/40 bg-julius-accent/5 p-6 space-y-4">
              <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-julius-border pb-4 gap-3">
                <div>
                  <span className="text-xs px-2 py-0.5 rounded bg-julius-accent/20 text-julius-accent font-bold uppercase tracking-wider">{lookupResult.legal_entity || 'Business'}</span>
                  <h2 className="text-xl font-black text-julius-text mt-1">{lookupResult.company_name}</h2>
                </div>
                <div className="flex gap-2">
                  <a href="/api/intelligence/company-lookup/export/csv" target="_blank" className="px-3.5 py-2 text-xs font-bold border border-green-500/40 text-green-400 bg-green-500/10 hover:bg-green-500/20 rounded uppercase tracking-wider">📥 CSV</a>
                  <a href="/api/intelligence/company-lookup/export/json" target="_blank" className="px-3.5 py-2 text-xs font-bold border border-blue-500/40 text-blue-400 bg-blue-500/10 hover:bg-blue-500/20 rounded uppercase tracking-wider">📥 JSON</a>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {[
                  { label: 'Legal Entity', value: lookupResult.legal_entity || '—', color: 'text-julius-accent' },
                  { label: 'GSTIN / CIN', value: lookupResult.gstin || '—', color: 'text-yellow-300 font-mono' },
                  { label: 'Contact Number', value: lookupResult.contact_number || '—', color: 'text-julius-text font-mono' },
                  { label: 'Email', value: lookupResult.email || '—', color: 'text-julius-accent font-mono' },
                  { label: 'Revenue', value: lookupResult.revenue || '—', color: 'text-green-400 font-bold' },
                  { label: 'City / State', value: `${lookupResult.city || '—'}${lookupResult.state ? ', ' + lookupResult.state : ''}`, color: 'text-julius-text' },
                ].map(f => (
                  <div key={f.label}>
                    <div className="text-[9px] uppercase tracking-widest text-julius-muted">{f.label}</div>
                    <div className={`text-sm mt-1 ${f.color}`}>{f.value}</div>
                  </div>
                ))}
                <div className="col-span-1 md:col-span-2">
                  <div className="text-[9px] uppercase tracking-widest text-julius-muted">Full Address</div>
                  <div className="text-xs text-julius-text mt-1 bg-julius-surface/40 p-2.5 rounded border border-julius-border">{lookupResult.full_address || '—'}</div>
                </div>
              </div>
            </div>
          )}

          <div className="rounded-xl border border-julius-border bg-julius-surface p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-bold text-julius-text uppercase tracking-wider">📜 Cached Profiles</h3>
              <div className="flex gap-2">
                <a href="/api/intelligence/company-lookup/export/csv" target="_blank" className="px-2.5 py-1 text-[10px] font-bold border border-green-500/40 text-green-400 bg-green-500/5 hover:bg-green-500/10 rounded uppercase">📥 CSV</a>
                <a href="/api/intelligence/company-lookup/export/json" target="_blank" className="px-2.5 py-1 text-[10px] font-bold border border-blue-500/40 text-blue-400 bg-blue-500/5 hover:bg-blue-500/10 rounded uppercase">📥 JSON</a>
              </div>
            </div>
            {lookupHistory.length === 0 ? (
              <div className="text-center py-10 text-xs text-julius-muted italic">No history yet. Search a company above.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-[11px]">
                  <thead>
                    <tr className="border-b border-julius-border/60 text-julius-muted uppercase text-[9px] tracking-wider">
                      <th className="py-2 px-3">Company</th><th className="py-2">Entity</th><th className="py-2">City</th>
                      <th className="py-2">Contact</th><th className="py-2">GSTIN</th><th className="py-2">Revenue</th><th className="py-2 text-center">Del</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-julius-border/30">
                    {lookupHistory.map(rec => (
                      <tr key={rec.id} onClick={() => setLookupResult(rec)} className={`cursor-pointer hover:bg-julius-surface2 transition-all ${lookupResult?.id === rec.id ? 'bg-julius-accent/5' : ''}`}>
                        <td className="py-2.5 px-3 font-bold text-julius-text">{rec.company_name}</td>
                        <td className="py-2.5 text-julius-accent">{rec.legal_entity || '—'}</td>
                        <td className="py-2.5">{rec.city || '—'}</td>
                        <td className="py-2.5 font-mono text-[10px]">{rec.contact_number || rec.email || '—'}</td>
                        <td className="py-2.5 font-mono text-yellow-300">{rec.gstin || '—'}</td>
                        <td className="py-2.5 text-green-400 font-bold">{rec.revenue || '—'}</td>
                        <td className="py-2.5 text-center" onClick={e => e.stopPropagation()}>
                          <button onClick={() => handleDeleteLookup(rec.id)} className="text-julius-muted hover:text-red-400 font-bold px-2">✕</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Sliding AI Deep-Dive Brief Drawer ───────────────────────────── */}
      {activeDeepDive && activeTab === 'market' && (
        <div className="fixed inset-0 z-50 flex items-center justify-end bg-black/70 backdrop-blur-xs transition-opacity duration-300">
          <div className="w-full max-w-xl h-full border-l border-julius-border bg-julius-surface p-6 flex flex-col shadow-2xl relative animate-slide-in">
            <button
              onClick={() => setActiveDeepDive(null)}
              className="absolute top-4 right-4 text-julius-muted hover:text-julius-red text-xl transition-all"
            >
              ✕
            </button>
            <div className="flex items-center gap-2 mb-6 border-b border-julius-border pb-4">
              <span className="text-julius-accent text-xl">◈</span>
              <div>
                <h2 className="font-display text-xs font-bold tracking-widest text-julius-accent uppercase">
                  {deepDiveData?.title || activeDeepDive.replace('_', ' ').toUpperCase()}
                </h2>
                <div className="text-[9px] text-julius-muted mt-1 uppercase tracking-wider">
                  Powered by: <span className="text-julius-green font-bold">{deepDiveData?.engine || 'Analyzing...'}</span>
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto pr-2 space-y-4 text-xs leading-relaxed text-julius-text scrollbar-thin">
              {loadingDeepDive ? (
                <div className="flex flex-col items-center justify-center py-20 gap-3">
                  <Spinner />
                  <div className="text-[10px] text-julius-muted uppercase tracking-widest animate-pulse">Running OSINT AI Inference...</div>
                </div>
              ) : (
                <div className="markdown-brief whitespace-pre-line text-julius-text">
                  {deepDiveData?.explanation}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
