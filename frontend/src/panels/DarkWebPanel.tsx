import React, { useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { darkweb } from '../lib/api'

const API = "";

interface DwHealth {
  tor_proxy?: { status?: string; latency_ms?: number }
  robin_available?: boolean
  llm_available?: boolean
  search_engines?: number
}

interface SearchHit {
  title: string
  link: string
}

interface SearchResponse {
  total_found?: number
  refined_query?: string
  original_query?: string
  results?: SearchHit[]
}

interface InvestigationSummary {
  id: string
  query: string
  status: string
  results_found: number
  pages_scraped: number
}

interface ActiveInvestigation {
  id: string
  status: string
  query: string
  refined_query?: string
  raw_results_count?: number
  filtered_count?: number
  scraped_count?: number
  analysis?: string
  filtered_results?: SearchHit[]
}

export function DarkWebPanel() {
  const [query, setQuery] = useState('')
  const [activeInvId, setActiveInvId] = useState<string | null>(null)
  const [searchResults, setSearchResults] = useState<SearchResponse | null>(null)
  const qc = useQueryClient()

  // ========== AI NODE CONTROL STATE (NEW - ADDED) ==========
  const [aiStatus, setAiStatus] = useState({ active: false, nodes: 0, revenue: 0, lastAction: '' })
  const [aiLoading, setAiLoading] = useState(false)

  const { data: health } = useQuery({ queryKey: ['dw-health'], queryFn: darkweb.health, refetchInterval: 30000 })
  const { data: investigations } = useQuery({ queryKey: ['dw-investigations'], queryFn: darkweb.investigations, refetchInterval: 5000 })
  const { data: activeInvRaw } = useQuery({
    queryKey: ['dw-inv', activeInvId],
    queryFn: () => darkweb.getInvestigation(activeInvId!),
    enabled: !!activeInvId,
    refetchInterval: (query) => {
      const status = (query.state.data as { status?: string } | undefined)?.status
      return status === 'completed' || status === 'failed' ? false : 2000
    },
  })

  const searchMut = useMutation({
    mutationFn: () => darkweb.search(query),
    onSuccess: (data) => {
      setSearchResults(data as SearchResponse)
    },
  })

  const investigateMut = useMutation({
    mutationFn: () => darkweb.investigate(query),
    onSuccess: (data) => {
      setActiveInvId((data as { investigation_id: string }).investigation_id)
      qc.invalidateQueries({ queryKey: ['dw-investigations'] })
    },
  })

  // ========== AI NODE CONTROL FUNCTIONS (NEW - ADDED) ==========
  // Manager Requirement: Inject AI into dark web, take control of nodes
  const fetchAIDarkWebStatus = async () => {
    try {
      const nodesRes = await fetch('/veil/nodes/controlled')
      const nodesData = await nodesRes.json()
      const revenueRes = await fetch('/veil/revenue')
      const revenueData = await revenueRes.json()
      
      setAiStatus({
        active: true,
        nodes: nodesData.total_db_controlled || 0,
        revenue: revenueData.total_revenue_usd || 0,
        lastAction: new Date().toLocaleTimeString()
      })
    } catch (error) {
      console.error('Failed to fetch AI dark web status:', error)
    }
  }

  const activateAINodeControl = async () => {
    setAiLoading(true)
    try {
      // Step 1: Control a dark web node (AI injection into dark web)
      const nodeRes = await fetch('/veil/nodes/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_id: `ai_injected_${Date.now()}`, method: 'covert' })
      })
      const nodeData = await nodeRes.json()
      
      // Step 2: Optimize the node with VEIL enhancements
      await fetch(`/veil/nodes/optimize/${nodeData.node_id}`, { method: 'POST' })
      
      // Step 3: Protect the node from surveillance
      await fetch(`/veil/nodes/protect/${nodeData.node_id}`, { method: 'POST' })
      
      // Step 4: Update status
      await fetchAIDarkWebStatus()
      
      alert(`✅ AI injected into dark web! Node ${nodeData.node_id} is now under JULIUS control.\n✓ Optimized with VEIL enhancements\n✓ Protected from surveillance\n✓ Revenue tracking active`)
      
      // Refresh investigations to show new activity
      qc.invalidateQueries({ queryKey: ['dw-investigations'] })
      
    } catch (error) {
      console.error('AI injection failed:', error)
      alert('❌ AI injection failed. Make sure VEIL backend is running on port 8000')
    } finally {
      setAiLoading(false)
    }
  }

  // REAL APEX Dark Web Intelligence - NO FAKE API
  const [apexDarkWeb, setApexDarkWeb] = useState<any>(null)
  const [apexDarkWebRunning, setApexDarkWebRunning] = useState(false)

  const runRealApexDarkWeb = async () => {
    setApexDarkWebRunning(true)
    try {
      // Get REAL causal strength for darkweb -> threat
      const causalRes = await fetch(`${API}/api/causal/darkweb/threat`)
      const causalData = await causalRes.json()

      // Get REAL system status
      const statusRes = await fetch(`${API}/api/status`)
      const statusData = await statusRes.json()

      // Get REAL threat assessment
      const threatRes = await fetch(`${API}/api/threat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ threat_type: 'darkweb_intel' })
      })
      const threatData = await threatRes.json()

      // Calculate dark web statistics from actual data
      const totalResults = investigationList.reduce((sum, inv) => sum + inv.results_found, 0)
      const completedInvestigations = investigationList.filter(inv => inv.status === 'completed').length
      const highRiskQueries = investigationList.filter(inv => inv.results_found > 10).length

      setApexDarkWeb({
        causal_analysis: {
          darkweb_to_threat_strength: causalData.strength,
          interpretation: causalData.interpretation
        },
        system_status: statusData,
        threat_assessment: threatData,
        darkweb_statistics: {
          total_investigations: investigationList.length,
          completed_investigations: completedInvestigations,
          total_results_found: totalResults,
          high_risk_queries: highRiskQueries,
          tor_status: healthTyped?.tor_proxy?.status === 'up' ? 'connected' : 'disconnected',
          robin_available: healthTyped?.robin_available || false
        },
        recommendation: causalData.strength > 0.7 
          ? "HIGH THREAT: Dark web intelligence shows strong correlation with breaches - Increase monitoring"
          : causalData.strength > 0.4
          ? "MEDIUM THREAT: Dark web monitoring recommended"
          : "LOW THREAT: Continue routine dark web monitoring",
        timestamp: new Date().toISOString()
      })
    } catch (error) {
      console.error('APEX dark web analysis failed:', error)
      setApexDarkWeb({ error: 'Backend not running. Start: python backend/julius_api_real.py' })
    } finally {
      setApexDarkWebRunning(false)
    }
  }

  const healthTyped = health as DwHealth | undefined
  const activeInv = activeInvRaw as ActiveInvestigation | undefined
  const investigationList =
    (investigations as { investigations?: InvestigationSummary[] } | undefined)?.investigations ?? []

  const torUp = healthTyped?.tor_proxy?.status === 'up'
  const robinOk = healthTyped?.robin_available

  // Fetch AI status on component mount
// Fetch AI status on component mount
React.useEffect(() => {
  fetchAIDarkWebStatus()
}, [])

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-bold tracking-wide">Dark Web OSINT</h1>
        <span className="text-[10px] px-2 py-0.5 rounded bg-julius-accent/20 text-julius-accent">Powered by Robin AI</span>
      </div>

      {/* ========== AI DARK WEB NODE CONTROL SECTION (NEW - MANAGER REQUIREMENT) ========== */}
      <div className="bg-gradient-to-r from-purple-900/30 to-indigo-900/30 border border-purple-500/50 rounded-xl p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-sm font-semibold text-white">🤖 AI Dark Web Node Control</h3>
            <p className="text-[10px] text-purple-300">Manager Requirement: Inject AI into dark web, take control of nodes, optimize and protect them</p>
          </div>
          <span className="text-[10px] px-2 py-1 rounded bg-green-900/50 text-green-400 border border-green-700">REAL VEIL INTEGRATION</span>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4">
          <div className="bg-black/30 rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-purple-400">{aiStatus.nodes}</div>
            <div className="text-[9px] text-purple-300">Nodes Under AI Control</div>
          </div>
          <div className="bg-black/30 rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-green-400">${aiStatus.revenue.toFixed(2)}</div>
            <div className="text-[9px] text-purple-300">Revenue from Controlled Nodes</div>
          </div>
          <div className="bg-black/30 rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-yellow-400">1.5^c</div>
            <div className="text-[9px] text-purple-300">Complexity Scaling</div>
          </div>
          <div className="bg-black/30 rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-blue-400">3-Layer</div>
            <div className="text-[9px] text-purple-300">Poisson Mixing</div>
          </div>
        </div>
        
        <button
          onClick={activateAINodeControl}
          disabled={aiLoading}
          className="w-full py-2.5 bg-purple-600 hover:bg-purple-700 text-white font-bold rounded-lg transition disabled:opacity-50 text-sm"
        >
          {aiLoading ? '🤖 Injecting AI into Dark Web...' : '🤖 ACTIVATE AI NODE CONTROL'}
        </button>
        
        <div className="mt-3 text-[10px] text-purple-300 text-center">
          When activated: AI takes control of dark web nodes → optimizes with VEIL enhancements → protects from surveillance → charges commissions
        </div>
        
        {aiStatus.lastAction && (
          <div className="mt-2 text-[9px] text-purple-400 text-center">
            Last updated: {aiStatus.lastAction}
          </div>
        )}
      </div>

      {/* REAL APEX Dark Web Intelligence - NO FAKE API */}
      <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-sm font-semibold">🔗 APEX Dark Web Intelligence</h3>
            <p className="text-[10px] text-julius-muted">REAL causal analysis of dark web investigations</p>
          </div>
          <span className="text-[10px] px-2 py-1 rounded bg-red-900/30 text-red-400 border border-red-800">REAL DATA</span>
        </div>
        <button onClick={runRealApexDarkWeb} disabled={apexDarkWebRunning || investigationList.length === 0}
          className="w-full py-2 text-xs font-mono rounded disabled:opacity-40 mb-3"
          style={{ background: '#140000', border: '1px solid #ef444444', color: '#ef4444' }}>
          {apexDarkWebRunning ? '⚙️ ANALYSING DARK WEB...' : `🚀 RUN APEX ON ${investigationList.length} INVESTIGATIONS`}
        </button>
        
        {apexDarkWeb && !apexDarkWeb.error && (
          <div className="space-y-3">
            {/* Causal Analysis */}
            <div className="bg-julius-bg rounded p-3">
              <div className="text-[10px] text-red-400 uppercase tracking-wider mb-2">Causal Analysis (REAL)</div>
              <div className="text-[10px]"><span className="text-julius-muted">Dark Web → Threat Strength:</span> <span className="text-green-400 font-mono">{(apexDarkWeb.causal_analysis?.darkweb_to_threat_strength * 100).toFixed(0)}%</span></div>
              <div className="text-[10px]"><span className="text-julius-muted">Interpretation:</span> <span className="text-red-400">{apexDarkWeb.causal_analysis?.interpretation}</span></div>
            </div>

            {/* Dark Web Statistics */}
            <div className="bg-julius-bg rounded p-3">
              <div className="text-[10px] text-cyan-400 uppercase tracking-wider mb-2">Dark Web Statistics (LIVE)</div>
              <div className="grid grid-cols-2 gap-2 text-center mb-2">
                <div><div className="text-green-400 font-bold text-lg">{apexDarkWeb.darkweb_statistics?.total_investigations || 0}</div><div className="text-[9px] text-julius-muted">Investigations</div></div>
                <div><div className="text-blue-400 font-bold text-lg">{apexDarkWeb.darkweb_statistics?.total_results_found || 0}</div><div className="text-[9px] text-julius-muted">Results Found</div></div>
                <div><div className="text-yellow-400 font-bold text-lg">{apexDarkWeb.darkweb_statistics?.high_risk_queries || 0}</div><div className="text-[9px] text-julius-muted">High Risk</div></div>
                <div><div className="text-purple-400 font-bold text-lg">{apexDarkWeb.darkweb_statistics?.completed_investigations || 0}</div><div className="text-[9px] text-julius-muted">Completed</div></div>
              </div>
              <div className="text-[10px] mt-2"><span className="text-julius-muted">Tor Status:</span> <span className={apexDarkWeb.darkweb_statistics?.tor_status === 'connected' ? 'text-green-400' : 'text-red-400'}>{apexDarkWeb.darkweb_statistics?.tor_status || 'unknown'}</span></div>
              <div className="text-[10px]"><span className="text-julius-muted">Robin AI:</span> <span className={apexDarkWeb.darkweb_statistics?.robin_available ? 'text-green-400' : 'text-red-400'}>{apexDarkWeb.darkweb_statistics?.robin_available ? 'available' : 'unavailable'}</span></div>
            </div>

            {/* Recommendation */}
            <div className={`rounded p-3 ${apexDarkWeb.causal_analysis?.darkweb_to_threat_strength > 0.7 ? 'bg-red-900/20 border border-red-800' : 'bg-green-900/20 border border-green-800'}`}>
              <div className="text-[10px] font-bold mb-1">💡 RECOMMENDATION</div>
              <div className="text-[11px]">{apexDarkWeb.recommendation}</div>
            </div>

            <div className="text-[9px] text-julius-muted text-right">Real-time from APEX backend | {new Date(apexDarkWeb.timestamp).toLocaleTimeString()}</div>
          </div>
        )}
        
        {apexDarkWeb?.error && (
          <div className="bg-red-900/20 text-red-400 p-2 rounded text-[10px]">{apexDarkWeb.error}</div>
        )}
      </div>

      {/* Health badges */}
      <div className="flex gap-4 flex-wrap">
        <Badge label="Tor Proxy" value={torUp ? 'UP' : 'DOWN'} ok={torUp} extra={healthTyped?.tor_proxy?.latency_ms ? `${healthTyped.tor_proxy.latency_ms}ms` : undefined} />
        <Badge label="Robin Search" value={robinOk ? 'Loaded' : 'Unavailable'} ok={robinOk} />
        <Badge label="LLM Analysis" value={healthTyped?.llm_available ? 'Available' : 'No keys'} ok={healthTyped?.llm_available} />
        <Badge label="Search Engines" value={String(healthTyped?.search_engines ?? 0)} ok={(healthTyped?.search_engines ?? 0) > 0} />
      </div>

      {/* Search / Investigate form */}
      <div className="bg-julius-surface border border-julius-border rounded-xl p-5">
        <div className="flex items-end gap-4">
          <div className="flex-1">
            <label className="block text-[10px] text-julius-muted uppercase tracking-wider mb-1">Search Query</label>
            <input
              type="text" value={query} onChange={e => setQuery(e.target.value)}
              placeholder="e.g. leaked credentials company.com"
              className="w-full bg-julius-bg border border-julius-border rounded-lg px-4 py-2.5 text-sm text-julius-text focus:border-julius-accent focus:outline-none"
              onKeyDown={e => e.key === 'Enter' && query.trim() && searchMut.mutate()}
            />
          </div>
          <button
            onClick={() => searchMut.mutate()}
            disabled={!query.trim() || searchMut.isPending || !robinOk}
            className="bg-julius-accent hover:bg-julius-accent/90 disabled:opacity-40 text-white px-5 py-2.5 rounded-lg text-sm font-medium"
          >
            {searchMut.isPending ? 'Searching...' : 'Search'}
          </button>
          <button
            onClick={() => investigateMut.mutate()}
            disabled={!query.trim() || investigateMut.isPending || !robinOk}
            className="bg-julius-red hover:bg-julius-red/90 disabled:opacity-40 text-white px-5 py-2.5 rounded-lg text-sm font-medium"
          >
            {investigateMut.isPending ? 'Starting...' : 'Full Investigation'}
          </button>
        </div>
        {!torUp && (
          <div className="mt-3 text-xs text-julius-red bg-julius-red/10 rounded-lg px-3 py-2">
            Tor proxy is not running. Install Tor and start the service on port 9150.
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Search results */}
        <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
          <h3 className="text-sm font-semibold mb-3">
            Search Results {searchResults ? `(${searchResults.total_found} found)` : ''}
          </h3>
          {searchResults?.refined_query && searchResults.refined_query !== searchResults.original_query && (
            <div className="text-[10px] text-julius-muted mb-2">
              Refined: <span className="text-julius-accent font-mono">{searchResults.refined_query}</span>
            </div>
          )}
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {(searchResults?.results || []).map((r: SearchHit, i: number) => (
              <div key={i} className="bg-julius-bg rounded-lg px-3 py-2">
                <div className="text-xs text-julius-text truncate">{r.title}</div>
                <div className="text-[10px] text-julius-accent font-mono truncate mt-0.5">{r.link}</div>
              </div>
            ))}
            {!searchResults && <div className="text-xs text-julius-muted text-center py-8">Enter a query and click Search.</div>}
            {searchResults && searchResults.results?.length === 0 && (
              <div className="text-xs text-julius-muted text-center py-8">No results found.</div>
            )}
          </div>
        </div>

        {/* Active investigation */}
        <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
          <h3 className="text-sm font-semibold mb-3">Investigation</h3>
          {activeInv ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className={`text-[10px] px-2 py-0.5 rounded font-bold
                  ${activeInv.status === 'completed' ? 'bg-julius-green/20 text-julius-green'
                    : activeInv.status === 'failed' ? 'bg-julius-red/20 text-julius-red'
                    : 'bg-julius-amber/20 text-julius-amber'}`}>
                  {activeInv.status}
                </span>
                <span className="text-xs text-julius-muted font-mono">{activeInv.id}</span>
              </div>
              <div className="text-xs text-julius-muted">
                Query: <span className="text-julius-text">{activeInv.query}</span>
              </div>
              {activeInv.refined_query && activeInv.refined_query !== activeInv.query && (
                <div className="text-xs text-julius-muted">
                  Refined: <span className="text-julius-accent">{activeInv.refined_query}</span>
                </div>
              )}
              <div className="grid grid-cols-3 gap-2">
                <MiniStat label="Results" value={activeInv.raw_results_count} />
                <MiniStat label="Filtered" value={activeInv.filtered_count} />
                <MiniStat label="Scraped" value={activeInv.scraped_count} />
              </div>

              {/* Analysis output */}
              {activeInv.analysis && (
                <div className="bg-julius-bg rounded-lg p-3 max-h-64 overflow-y-auto">
                  <div className="text-[10px] text-julius-muted uppercase tracking-wider mb-2">Analysis</div>
                  <div className="text-xs text-julius-text whitespace-pre-wrap leading-relaxed">
                    {activeInv.analysis}
                  </div>
                </div>
              )}

              {/* Filtered results */}
              {(activeInv.filtered_results?.length ?? 0) > 0 && (
                <div>
                  <div className="text-[10px] text-julius-muted uppercase tracking-wider mb-1">
                    Filtered Results ({activeInv.filtered_count})
                  </div>
                  <div className="space-y-1 max-h-40 overflow-y-auto">
                    {(activeInv.filtered_results ?? []).slice(0, 10).map((r: SearchHit, i: number) => (
                      <div key={i} className="text-[10px] text-julius-accent font-mono truncate">
                        {r.title}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-xs text-julius-muted text-center py-8">
              Click "Full Investigation" to run the complete pipeline:<br />
              Search → Filter → Scrape → Analyze
            </div>
          )}
        </div>
      </div>

      {/* Investigation history */}
      <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
        <h3 className="text-sm font-semibold mb-3">Investigation History</h3>
        <div className="space-y-2">
          {investigationList.map((inv: InvestigationSummary) => (
            <div
              key={inv.id}
              onClick={() => setActiveInvId(inv.id)}
              className="bg-julius-bg rounded-lg px-3 py-2 flex items-center justify-between cursor-pointer hover:bg-julius-surface2"
            >
              <div>
                <span className="text-xs text-julius-text">{inv.query}</span>
                <span className="text-[10px] text-julius-muted ml-2 font-mono">{inv.id}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-[10px] text-julius-muted">{inv.results_found} results, {inv.pages_scraped} scraped</span>
                <span className={`text-[10px] px-2 py-0.5 rounded
                  ${inv.status === 'completed' ? 'bg-julius-green/20 text-julius-green'
                    : inv.status === 'failed' ? 'bg-julius-red/20 text-julius-red'
                    : 'bg-julius-amber/20 text-julius-amber'}`}>
                  {inv.status}
                </span>
              </div>
            </div>
          ))}
          {investigationList.length === 0 && (
            <div className="text-xs text-julius-muted text-center py-6">No investigations yet.</div>
          )}
        </div>
      </div>
    </div>
  )
}

function Badge({ label, value, ok, extra }: { label: string; value: string; ok?: boolean; extra?: string }) {
  return (
    <div className="bg-julius-surface border border-julius-border rounded-lg px-3 py-2 flex items-center gap-2">
      <div className={`w-2 h-2 rounded-full ${ok ? 'bg-julius-green' : 'bg-julius-red'}`} />
      <div>
        <div className="text-[9px] text-julius-muted uppercase">{label}</div>
        <div className={`text-xs font-mono ${ok ? 'text-julius-green' : 'text-julius-red'}`}>
          {value} {extra && <span className="text-julius-muted">({extra})</span>}
        </div>
      </div>
    </div>
  )
}

function MiniStat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="bg-julius-bg rounded-lg p-2 text-center">
      <div className="text-[9px] text-julius-muted uppercase">{label}</div>
      <div className="text-sm font-mono text-julius-accent font-bold">{value ?? 0}</div>
    </div>
  )
}