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

  // ── Company Lookup States ──────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<'market' | 'company-lookup'>('market')
  const [lookupQuery, setLookupQuery] = useState('')
  const [lookupLoading, setLookupLoading] = useState(false)
  const [lookupResult, setLookupResult] = useState<any>(null)
  const [lookupHistory, setLookupHistory] = useState<any[]>([])
  const [lookupError, setLookupError] = useState('')

  const fetchLookupHistory = useCallback(async () => {
    try {
      const res = await axios.get('/api/intelligence/company-lookup/history')
      if (res.data.success) {
        setLookupHistory(res.data.records || [])
      }
    } catch {
      // silent fail
    }
  }, [])

  useEffect(() => {
    if (activeTab === 'company-lookup') {
      fetchLookupHistory()
    }
  }, [activeTab, fetchLookupHistory])

  const handleCompanyLookup = async () => {
    if (!lookupQuery.trim()) return
    setLookupLoading(true)
    setLookupError('')
    setLookupResult(null)
    try {
      const res = await axios.post('/api/intelligence/company-lookup', {
        company_name: lookupQuery.trim(),
        country: 'India',
        save: true
      })
      if (res.data.success) {
        setLookupResult(res.data.result)
        fetchLookupHistory()
      } else {
        setLookupError('Failed to lookup company details.')
      }
    } catch (e: any) {
      setLookupError(e.response?.data?.detail || e.message || 'Lookup failed.')
    } finally {
      setLookupLoading(false)
    }
  }

  const handleDeleteLookup = async (id: string) => {
    try {
      await axios.delete(`/api/intelligence/company-lookup/${id}`)
      fetchLookupHistory()
      if (lookupResult?.id === id) {
        setLookupResult(null)
      }
    } catch (e: any) {
      // silent
    }
  }

  // ── Deep-Dive AI States ───────────────────────────────────────────────────
  const [activeDeepDive, setActiveDeepDive] = useState<string | null>(null)
  const [deepDiveData, setDeepDiveData] = useState<{ title: string; explanation: string; engine: string } | null>(null)
  const [loadingDeepDive, setLoadingDeepDive] = useState(false)

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

      {/* ── MARKET INTELLIGENCE TAB ────────────────────────────────────── */}
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

      {/* ── Sliding AI Deep-Dive Brief Drawer ───────────────────────────── */}
      {activeDeepDive && (
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
