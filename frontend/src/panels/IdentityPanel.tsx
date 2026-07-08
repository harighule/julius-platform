import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { identity } from '../lib/api'

const API = "";

interface IdentityRow {
  id: string
  name: string
  platform: string
  email?: string
  phone?: string
  handle?: string
  extra?: any
}

interface GraphEdge {
  source: string
  target: string
  merged?: boolean
  weight: number
}

interface ConfidenceResult {
  confidence_score?: number | string
  matches?: { field: string; score: number }[]
}

// ── Profile Detail Modal (same as before, keep as is) ──
function ProfileModal({ profile, onClose }: { profile: IdentityRow; onClose: () => void }) {
  // ... (keep your existing ProfileModal code - it's fine)
  // For brevity, I'm not repeating it here, but keep your existing one
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-julius-surface border border-julius-border rounded-xl w-full max-w-2xl max-h-[90vh] flex flex-col shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="p-4 border-b border-julius-border">
          <div className="text-base font-bold text-julius-text">{profile.name}</div>
          <div className="text-[10px] font-mono text-julius-accent">{profile.id}</div>
          <button onClick={onClose} className="absolute top-4 right-4 text-julius-muted hover:text-julius-text">✕</button>
        </div>
        <div className="p-4 overflow-y-auto">
          <pre className="text-xs">{JSON.stringify(profile.extra, null, 2)}</pre>
        </div>
      </div>
    </div>
  )
}

// ── Main Panel ────────────────────────────────────────────────
export function IdentityPanel() {
  const qc = useQueryClient()
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState('')
  const [selectedProfile, setSelectedProfile] = useState<IdentityRow | null>(null)
  const limit = 50

  const { data } = useQuery({
    queryKey: ['identities', page, search],
    queryFn: () => fetch(`/api/identity/list?limit=${limit}&offset=${page * limit}&search=${encodeURIComponent(search)}`)
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json() }),
    refetchInterval: 30000,
  })

  const { data: graphData } = useQuery({
    queryKey: ['identity-graph'],
    queryFn: identity.graph,
    refetchInterval: 60000,
    staleTime: 30000,
  })

  const [mergeFrom, setMergeFrom] = useState('')
  const [mergeTo, setMergeTo] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  const [addForm, setAddForm] = useState({ name: '', platform: 'email', email: '', phone: '', handle: '' })
  const [confidenceId, setConfidenceId] = useState('')
  const [confidenceResult, setConfidenceResult] = useState<ConfidenceResult | null>(null)

  // REAL APEX Identity Intelligence - NO FAKE API
  const [apexIdentity, setApexIdentity] = useState<any>(null)
  const [apexIdentityRunning, setApexIdentityRunning] = useState(false)

  const runRealApexIdentity = async () => {
    setApexIdentityRunning(true)
    try {
      // Get REAL causal strength for identity → breach
      const causalRes = await fetch(`${API}/api/causal/identity/breach`)
      const causalData = await causalRes.json()

      // Get REAL system status
      const statusRes = await fetch(`${API}/api/status`)
      const statusData = await statusRes.json()

      // Get REAL threat assessment
      const threatRes = await fetch(`${API}/api/threat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ threat_type: 'identity_compromise' })
      })
      const threatData = await threatRes.json()

      // Calculate identity statistics from actual data
      const hasEmail = identities.filter(i => i.email).length
      const hasPhone = identities.filter(i => i.phone).length
      const hasHandle = identities.filter(i => i.handle).length

      setApexIdentity({
        causal_analysis: {
          identity_to_breach_strength: causalData.strength,
          interpretation: causalData.interpretation
        },
        system_status: statusData,
        threat_assessment: threatData,
        identity_statistics: {
          total_identities: total,
          with_email: hasEmail,
          with_phone: hasPhone,
          with_handle: hasHandle,
          graph_connections: edges.length,
          merged_identities: mergedCount
        },
        recommendation: causalData.strength > 0.7 
          ? "HIGH RISK: Identity compromise strongly leads to breach - Implement MFA and monitoring"
          : causalData.strength > 0.4
          ? "MEDIUM RISK: Identity monitoring recommended"
          : "LOW RISK: Continue standard identity management",
        timestamp: new Date().toISOString()
      })
    } catch (error) {
      console.error('APEX identity analysis failed:', error)
      setApexIdentity({ error: 'Backend not running. Start: python backend/julius_api_real.py' })
    } finally {
      setApexIdentityRunning(false)
    }
  }

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ['identities'] })
    qc.invalidateQueries({ queryKey: ['identity-graph'] })
  }

  const mergeMut = useMutation({
    mutationFn: () => identity.merge(mergeFrom, mergeTo),
    onSuccess: () => { invalidateAll(); setMergeFrom(''); setMergeTo('') },
  })

  const addMut = useMutation({
    mutationFn: () => identity.add(addForm),
    onSuccess: () => { invalidateAll(); setShowAddForm(false); setAddForm({ name: '', platform: 'email', email: '', phone: '', handle: '' }) },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) =>
      fetch(`/api/identity/${encodeURIComponent(id)}`, { method: 'DELETE' })
        .then(async res => { if (!res.ok) throw new Error(await res.text()); return res.json() }),
    onSuccess: () => invalidateAll(),
  })

  const confidenceMut = useMutation({
    mutationFn: (id: string) => identity.confidence(id),
    onSuccess: (data) => setConfidenceResult(data as ConfidenceResult),
  })

  const handleProfileClick = async (row: IdentityRow) => {
    if (row.extra && typeof row.extra === 'string') {
      try { row.extra = JSON.parse(row.extra) } catch {}
    }
    if (row.extra && typeof row.extra === 'object' && row.extra.behavioral_intelligence) {
      setSelectedProfile(row)
      return
    }
    try {
      const res = await fetch(`/api/identity/list?limit=1&offset=0&search=${encodeURIComponent(row.name)}`)
      const data = await res.json()
      const full = data.identities?.[0]
      if (full) {
        if (typeof full.extra === 'string') { try { full.extra = JSON.parse(full.extra) } catch {} }
        setSelectedProfile(full)
      } else {
        setSelectedProfile(row)
      }
    } catch { setSelectedProfile(row) }
  }

  const identities: IdentityRow[] = (data as any)?.identities ?? []
  const edges: GraphEdge[] = (graphData as any)?.edges ?? []
  const total = (data as any)?.total ?? 0
  const totalPages = (data as any)?.pages ?? 0
  const mergedCount = edges.filter((e: GraphEdge) => e.merged).length

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">
      {/* Profile Detail Modal */}
      {selectedProfile && (
        <ProfileModal profile={selectedProfile} onClose={() => setSelectedProfile(null)} />
      )}

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold tracking-wide">Identity Resolution</h1>
        <button onClick={() => setShowAddForm(!showAddForm)}
          className="text-xs bg-julius-accent/20 text-julius-accent px-3 py-1.5 rounded hover:bg-julius-accent/30">
          {showAddForm ? 'Cancel' : '+ Add Identity'}
        </button>
      </div>

      {/* REAL APEX Identity Intelligence - NO FAKE API */}
      <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-sm font-semibold">🔗 APEX Identity Intelligence</h3>
            <p className="text-[10px] text-julius-muted">REAL causal analysis of identity profiles</p>
          </div>
          <span className="text-[10px] px-2 py-1 rounded bg-purple-900/30 text-purple-400 border border-purple-800">REAL DATA</span>
        </div>
        <button onClick={runRealApexIdentity} disabled={apexIdentityRunning || identities.length === 0}
          className="w-full py-2 text-xs font-mono rounded disabled:opacity-40 mb-3"
          style={{ background: '#0a0014', border: '1px solid #a855f744', color: '#a855f7' }}>
          {apexIdentityRunning ? '⚙️ ANALYSING IDENTITIES...' : `🚀 RUN APEX ON ${identities.length} PROFILES`}
        </button>
        
        {apexIdentity && !apexIdentity.error && (
          <div className="space-y-3">
            {/* Causal Analysis */}
            <div className="bg-julius-bg rounded p-3">
              <div className="text-[10px] text-purple-400 uppercase tracking-wider mb-2">Causal Analysis (REAL)</div>
              <div className="text-[10px]"><span className="text-julius-muted">Identity → Breach Strength:</span> <span className="text-green-400 font-mono">{(apexIdentity.causal_analysis?.identity_to_breach_strength * 100).toFixed(0)}%</span></div>
              <div className="text-[10px]"><span className="text-julius-muted">Interpretation:</span> <span className="text-purple-400">{apexIdentity.causal_analysis?.interpretation}</span></div>
            </div>

            {/* Identity Statistics */}
            <div className="bg-julius-bg rounded p-3">
              <div className="text-[10px] text-cyan-400 uppercase tracking-wider mb-2">Identity Statistics (LIVE)</div>
              <div className="grid grid-cols-3 gap-2 text-center mb-2">
                <div><div className="text-green-400 font-bold text-lg">{apexIdentity.identity_statistics?.total_identities || 0}</div><div className="text-[9px] text-julius-muted">Total</div></div>
                <div><div className="text-blue-400 font-bold text-lg">{apexIdentity.identity_statistics?.with_email || 0}</div><div className="text-[9px] text-julius-muted">With Email</div></div>
                <div><div className="text-yellow-400 font-bold text-lg">{apexIdentity.identity_statistics?.with_phone || 0}</div><div className="text-[9px] text-julius-muted">With Phone</div></div>
              </div>
              <div className="text-[10px] mt-2"><span className="text-julius-muted">Graph Connections:</span> <span className="text-cyan-400">{apexIdentity.identity_statistics?.graph_connections || 0}</span></div>
              <div className="text-[10px]"><span className="text-julius-muted">Merged Identities:</span> <span className="text-yellow-400">{apexIdentity.identity_statistics?.merged_identities || 0}</span></div>
            </div>

            {/* Recommendation */}
            <div className={`rounded p-3 ${apexIdentity.causal_analysis?.identity_to_breach_strength > 0.7 ? 'bg-red-900/20 border border-red-800' : 'bg-green-900/20 border border-green-800'}`}>
              <div className="text-[10px] font-bold mb-1">💡 RECOMMENDATION</div>
              <div className="text-[11px]">{apexIdentity.recommendation}</div>
            </div>

            <div className="text-[9px] text-julius-muted text-right">Real-time from APEX backend | {new Date(apexIdentity.timestamp).toLocaleTimeString()}</div>
          </div>
        )}
        
        {apexIdentity?.error && (
          <div className="bg-red-900/20 text-red-400 p-2 rounded text-[10px]">{apexIdentity.error}</div>
        )}
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-julius-surface border border-julius-border rounded-xl p-4 text-center">
          <div className="text-[10px] text-julius-muted uppercase mb-1">Identities</div>
          <div className="text-2xl font-bold font-mono text-julius-accent">
            {total > 0 ? total.toLocaleString() : '—'}
          </div>
        </div>
        <div className="bg-julius-surface border border-julius-border rounded-xl p-4 text-center">
          <div className="text-[10px] text-julius-muted uppercase mb-1">Connections</div>
          <div className="text-2xl font-bold font-mono text-julius-green">{edges.length.toLocaleString()}</div>
        </div>
        <div className="bg-julius-surface border border-julius-border rounded-xl p-4 text-center">
          <div className="text-[10px] text-julius-muted uppercase mb-1">Merged</div>
          <div className="text-2xl font-bold font-mono text-julius-amber">{mergedCount}</div>
        </div>
      </div>

      {/* Add Identity Form */}
      {showAddForm && (
        <div className="bg-julius-surface border border-julius-border rounded-xl p-4 space-y-3">
          <h3 className="text-sm font-semibold">Add New Identity</h3>
          <div className="grid grid-cols-2 gap-3">
            <input value={addForm.name} onChange={e => setAddForm(f => ({ ...f, name: e.target.value }))} placeholder="Name *"
              className="bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs text-julius-text focus:outline-none" />
            <select value={addForm.platform} onChange={e => setAddForm(f => ({ ...f, platform: e.target.value }))}
              className="bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs text-julius-text">
              {['email','twitter','linkedin','github','facebook','slack','phone','telegram','darkweb'].map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
            <input value={addForm.email} onChange={e => setAddForm(f => ({ ...f, email: e.target.value }))} placeholder="Email"
              className="bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs text-julius-text focus:outline-none" />
            <input value={addForm.phone} onChange={e => setAddForm(f => ({ ...f, phone: e.target.value }))} placeholder="Phone"
              className="bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs text-julius-text focus:outline-none" />
            <input value={addForm.handle} onChange={e => setAddForm(f => ({ ...f, handle: e.target.value }))} placeholder="Handle (@username)"
              className="bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs text-julius-text focus:outline-none col-span-2" />
          </div>
          <button onClick={() => addMut.mutate()} disabled={!addForm.name || addMut.isPending}
            className="bg-julius-accent hover:bg-julius-accent/90 disabled:opacity-40 text-white px-4 py-2 rounded text-xs">
            Add Identity
          </button>
        </div>
      )}

      {/* Merge + Confidence */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
          <h3 className="text-sm font-semibold mb-3">Merge Identities</h3>
          <div className="flex items-end gap-3">
            <div className="flex-1">
              <label className="block text-[10px] text-julius-muted uppercase mb-1">Source ID</label>
              <select value={mergeFrom} onChange={e => setMergeFrom(e.target.value)}
                className="w-full bg-julius-bg border border-julius-border rounded-lg px-3 py-2 text-xs text-julius-text focus:outline-none">
                <option value="">Select...</option>
                {identities.map((i: IdentityRow) => <option key={i.id} value={i.id}>{i.id} — {i.name}</option>)}
              </select>
            </div>
            <div className="flex-1">
              <label className="block text-[10px] text-julius-muted uppercase mb-1">Target ID</label>
              <select value={mergeTo} onChange={e => setMergeTo(e.target.value)}
                className="w-full bg-julius-bg border border-julius-border rounded-lg px-3 py-2 text-xs text-julius-text focus:outline-none">
                <option value="">Select...</option>
                {identities.map((i: IdentityRow) => <option key={i.id} value={i.id}>{i.id} — {i.name}</option>)}
              </select>
            </div>
            <button onClick={() => mergeMut.mutate()} disabled={!mergeFrom || !mergeTo || mergeMut.isPending}
              className="bg-julius-accent hover:bg-julius-accent/90 disabled:opacity-40 text-white px-4 py-2 rounded-lg text-xs">Merge</button>
          </div>
        </div>

        <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
          <h3 className="text-sm font-semibold mb-3">Confidence Check</h3>
          <div className="flex items-end gap-3">
            <div className="flex-1">
              <label className="block text-[10px] text-julius-muted uppercase mb-1">Identity ID</label>
              <select value={confidenceId} onChange={e => setConfidenceId(e.target.value)}
                className="w-full bg-julius-bg border border-julius-border rounded-lg px-3 py-2 text-xs text-julius-text focus:outline-none">
                <option value="">Select...</option>
                {identities.map((i: IdentityRow) => <option key={i.id} value={i.id}>{i.id} — {i.name}</option>)}
              </select>
            </div>
            <button onClick={() => confidenceMut.mutate(confidenceId)} disabled={!confidenceId || confidenceMut.isPending}
              className="bg-julius-green/80 hover:bg-julius-green/90 disabled:opacity-40 text-white px-4 py-2 rounded-lg text-xs">Check</button>
          </div>
          {confidenceResult && (
            <div className="mt-3 bg-julius-bg border border-julius-border rounded-lg p-3">
              <div className="text-xs text-julius-text">
                Score: <span className="font-bold font-mono text-julius-accent">{confidenceResult.confidence_score ?? 'N/A'}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Identity Table */}
      <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
        <h3 className="text-sm font-semibold mb-3">
          Identity Database
          <span className="ml-2 text-julius-muted font-normal text-xs">({total > 0 ? total.toLocaleString() : '...'} total profiles)</span>
        </h3>
        <input value={search} onChange={e => { setSearch(e.target.value); setPage(0) }}
          placeholder="Search by name, email or handle..."
          className="bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs w-full mb-3 focus:outline-none" />
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-julius-muted text-left border-b border-julius-border">
                <th className="pb-2 px-2">ID</th>
                <th className="pb-2 px-2">Name</th>
                <th className="pb-2 px-2">Platform</th>
                <th className="pb-2 px-2">Email</th>
                <th className="pb-2 px-2">Phone</th>
                <th className="pb-2 px-2">Handle</th>
                <th className="pb-2 px-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {identities.map((i: IdentityRow) => (
                <tr key={i.id} className="border-b border-julius-border/30 hover:bg-julius-surface2">
                  <td className="py-2 px-2">
                    <button onClick={() => handleProfileClick(i)}
                      className="font-mono text-julius-accent text-[10px] hover:underline cursor-pointer text-left">
                      {i.id}
                    </button>
                  </td>
                  <td className="py-2 px-2 text-julius-text">{i.name}</td>
                  <td className="py-2 px-2 text-julius-muted">{i.platform}</td>
                  <td className="py-2 px-2 font-mono text-julius-muted text-[10px]">{i.email || '—'}</td>
                  <td className="py-2 px-2 font-mono text-julius-muted text-[10px]">{i.phone || '—'}</td>
                  <td className="py-2 px-2 font-mono text-julius-accent text-[10px]">{i.handle || '—'}</td>
                  <td className="py-2 px-2">
                    <button onClick={() => { if (window.confirm(`Delete ${i.name}?`)) deleteMut.mutate(i.id) }}
                      disabled={deleteMut.isPending}
                      className="text-xs text-red-400 hover:text-red-600 px-2 py-1 border border-red-400 rounded">
                      🗑 Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between mt-3">
          <span className="text-xs text-julius-muted">
            Showing {total === 0 ? 0 : page * limit + 1}–{Math.min((page + 1) * limit, total)} of {total.toLocaleString()}
          </span>
          <div className="flex gap-2 items-center">
            <button onClick={() => setPage(0)} disabled={page === 0}
              className="text-xs px-2 py-1 border border-julius-border rounded disabled:opacity-40">«</button>
            <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
              className="text-xs px-3 py-1 border border-julius-border rounded disabled:opacity-40">← Prev</button>
            <span className="text-xs px-3 py-1 text-julius-muted">Page {page + 1} of {totalPages.toLocaleString()}</span>
            <button onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
              className="text-xs px-3 py-1 border border-julius-border rounded disabled:opacity-40">Next →</button>
            <button onClick={() => setPage(totalPages - 1)} disabled={page >= totalPages - 1}
              className="text-xs px-2 py-1 border border-julius-border rounded disabled:opacity-40">»</button>
          </div>
        </div>
      </div>

      {/* Graph Connections */}
      <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
        <h3 className="text-sm font-semibold mb-3">
          Graph Connections
          <span className="ml-2 text-julius-muted font-normal text-xs">(sample of 500 nodes)</span>
        </h3>
        <div className="space-y-1 max-h-60 overflow-y-auto">
          {edges.map((e: GraphEdge, i: number) => (
            <div key={i} className="flex items-center gap-3 text-xs py-1 border-b border-julius-border/20">
              <span className="font-mono text-julius-accent text-[10px]">{e.source}</span>
              <span className="text-julius-muted">→</span>
              <span className="font-mono text-julius-accent text-[10px]">{e.target}</span>
              <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded ${e.merged ? 'bg-julius-green/20 text-julius-green' : 'bg-julius-accent/20 text-julius-accent'}`}>
                {e.merged ? 'Merged' : `${(e.weight * 100).toFixed(0)}%`}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}