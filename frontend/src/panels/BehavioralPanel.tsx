import { useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { behavioral } from '../lib/api'

const API = "";

interface BehaviorPattern {
  id: number
  name: string
  pattern_type: string
  description?: string
  severity: string
  rules?: unknown
  is_active?: boolean
}

interface BehaviorAlert {
  id: number
  alert_type: string
  severity: string
  message: string
  created_at: string
}

export function BehavioralPanel() {
  const qc = useQueryClient()
  const { data: patternsData } = useQuery({ queryKey: ['patterns'], queryFn: behavioral.patterns, refetchInterval: 10000 })
  const { data: alertsData } = useQuery({ queryKey: ['alerts'], queryFn: () => behavioral.alerts(30), refetchInterval: 5000 })
  const { data: stats } = useQuery({ queryKey: ['behav-stats'], queryFn: behavioral.stats, refetchInterval: 10000 })

  const patterns = (patternsData as { patterns?: BehaviorPattern[] } | undefined)?.patterns ?? []
  const alerts = (alertsData as { alerts?: BehaviorAlert[] } | undefined)?.alerts ?? []
  const statsTyped = stats as { severity_distribution?: Record<string, number>; active_patterns?: number; total_alerts?: number } | undefined
  const dist = statsTyped?.severity_distribution ?? {}

  const [showPatternForm, setShowPatternForm] = useState(false)
  const [editingPattern, setEditingPattern] = useState<BehaviorPattern | null>(null)
  const [pForm, setPForm] = useState({ name: '', pattern_type: 'behavioral', description: '', severity: 'medium', rules: '{}' })

  const [showAlertForm, setShowAlertForm] = useState(false)
  const [aForm, setAForm] = useState({ alert_type: '', severity: 'medium', message: '', pattern_id: '' })
  const [confirmDelete, setConfirmDelete] = useState<{ type: string; id: number } | null>(null)

  const invalidateAll = () => { qc.invalidateQueries({ queryKey: ['patterns'] }); qc.invalidateQueries({ queryKey: ['alerts'] }); qc.invalidateQueries({ queryKey: ['behav-stats'] }) }

  const addPatternMut = useMutation({ mutationFn: behavioral.addPattern, onSuccess: () => { invalidateAll(); setShowPatternForm(false); resetPForm() } })
  const updatePatternMut = useMutation({
    mutationFn: (vars: { id: number; data: Record<string, unknown> }) => behavioral.updatePattern(vars.id, vars.data),
    onSuccess: () => { invalidateAll(); setEditingPattern(null); resetPForm() },
  })
  const deletePatternMut = useMutation({
    mutationFn: (id: number) => behavioral.deletePattern(id),
    onSuccess: () => { invalidateAll(); setConfirmDelete(null) },
  })
  const addAlertMut = useMutation({
    mutationFn: (data: Record<string, unknown>) => behavioral.addAlert(data),
    onSuccess: () => { invalidateAll(); setShowAlertForm(false); resetAForm() },
  })
  const deleteAlertMut = useMutation({
    mutationFn: (id: number) => behavioral.deleteAlert(id),
    onSuccess: () => { invalidateAll(); setConfirmDelete(null) },
  })

  // REAL APEX/CSIE Behavioral Analysis - NO FAKE API
  const [apexResult, setApexResult] = useState<any>(null)
  const [apexRunning, setApexRunning] = useState(false)
  const runRealApexBehavioral = async () => {
    setApexRunning(true)
    try {
      // Get REAL causal strength from backend
      const causalRes = await fetch(`${API}/api/causal/behavior/breach`)
      const causalData = await causalRes.json()

      // Get REAL system status
      const statusRes = await fetch(`${API}/api/status`)
      const statusData = await statusRes.json()

      // Get REAL threat analysis based on alert patterns
      const threatRes = await fetch(`${API}/api/threat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ threat_type: 'behavioral_anomaly' })
      })
      const threatData = await threatRes.json()

      // Calculate behavioral risk from actual alerts
      const criticalCount = alerts.filter(a => a.severity === 'critical').length
      const highCount = alerts.filter(a => a.severity === 'high').length
      
      setApexResult({
        causal_analysis: {
          behavioral_to_breach_strength: causalData.strength,
          interpretation: causalData.interpretation
        },
        system_status: statusData,
        threat_assessment: threatData,
        alert_statistics: {
          critical: criticalCount,
          high: highCount,
          medium: alerts.filter(a => a.severity === 'medium').length,
          low: alerts.filter(a => a.severity === 'low').length,
          total: alerts.length
        },
        recommendation: criticalCount > 0 ? "IMMEDIATE ACTION REQUIRED: Critical behavioral anomalies detected" 
                      : highCount > 0 ? "High risk behavioral patterns - Investigate immediately"
                      : "Normal behavioral patterns - Continue monitoring",
        timestamp: new Date().toISOString()
      })
    } catch (error) {
      console.error('APEX behavioral analysis failed:', error)
      setApexResult({ error: 'Backend not running. Start: python backend/julius_api_real.py' })
    } finally {
      setApexRunning(false)
    }
  }

  const resetPForm = () => setPForm({ name: '', pattern_type: 'behavioral', description: '', severity: 'medium', rules: '{}' })
  const resetAForm = () => setAForm({ alert_type: '', severity: 'medium', message: '', pattern_id: '' })

  const startEdit = (p: BehaviorPattern) => {
    setEditingPattern(p)
    setPForm({
      name: p.name,
      pattern_type: p.pattern_type,
      description: p.description || '',
      severity: p.severity,
      rules: typeof p.rules === 'object' && p.rules !== null ? JSON.stringify(p.rules) : String(p.rules ?? '{}'),
    })
    setShowPatternForm(true)
  }

  const submitPattern = () => {
    let rules: Record<string, unknown> = {}
    try {
      rules = JSON.parse(pForm.rules) as Record<string, unknown>
    } catch {
      void 0
    }
    const data: Record<string, unknown> = { ...pForm, rules }
    if (editingPattern) {
      updatePatternMut.mutate({ id: editingPattern.id, data })
    } else {
      addPatternMut.mutate(data)
    }
  }

  const submitAlert = () => {
    const data = { ...aForm, pattern_id: aForm.pattern_id ? Number(aForm.pattern_id) : null }
    addAlertMut.mutate(data)
  }

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">
      <h1 className="text-xl font-bold tracking-wide">Behavioral Analytics</h1>
      
      {/* REAL APEX/CSIE Behavioral Intelligence - NO FAKE API */}
      <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-sm font-semibold">🔗 APEX � CSIE Behavioral Intelligence</h3>
            <p className="text-[10px] text-julius-muted">REAL causal analysis of behavioral patterns</p>
          </div>
          <span className="text-[10px] px-2 py-1 rounded bg-purple-900/30 text-purple-400 border border-purple-800">REAL DATA</span>
        </div>
        <button onClick={runRealApexBehavioral} disabled={apexRunning}
          className="w-full py-2 text-xs font-mono rounded disabled:opacity-40 mb-3"
          style={{ background: '#0a0014', border: '1px solid #a855f744', color: '#a855f7' }}>
          {apexRunning ? '⚙️ ANALYSING BEHAVIOR...' : '🚀 RUN APEX BEHAVIORAL ANALYSIS'}
        </button>
        
        {apexResult && !apexResult.error && (
          <div className="space-y-3">
            {/* Causal Analysis */}
            <div className="bg-julius-bg rounded p-3">
              <div className="text-[10px] text-purple-400 uppercase tracking-wider mb-2">Causal Analysis (REAL)</div>
              <div className="text-[10px]"><span className="text-julius-muted">Behavior → Breach Strength:</span> <span className="text-green-400 font-mono">{(apexResult.causal_analysis?.behavioral_to_breach_strength * 100).toFixed(0)}%</span></div>
              <div className="text-[10px]"><span className="text-julius-muted">Interpretation:</span> <span className="text-purple-400">{apexResult.causal_analysis?.interpretation}</span></div>
            </div>

            {/* Alert Statistics */}
            <div className="bg-julius-bg rounded p-3">
              <div className="text-[10px] text-yellow-400 uppercase tracking-wider mb-2">Alert Statistics (LIVE)</div>
              <div className="grid grid-cols-4 gap-2 text-center">
                <div><div className="text-red-400 font-bold text-lg">{apexResult.alert_statistics?.critical || 0}</div><div className="text-[9px] text-julius-muted">Critical</div></div>
                <div><div className="text-orange-400 font-bold text-lg">{apexResult.alert_statistics?.high || 0}</div><div className="text-[9px] text-julius-muted">High</div></div>
                <div><div className="text-yellow-400 font-bold text-lg">{apexResult.alert_statistics?.medium || 0}</div><div className="text-[9px] text-julius-muted">Medium</div></div>
                <div><div className="text-green-400 font-bold text-lg">{apexResult.alert_statistics?.low || 0}</div><div className="text-[9px] text-julius-muted">Low</div></div>
              </div>
            </div>

            {/* Recommendation */}
            <div className={`rounded p-3 ${apexResult.alert_statistics?.critical > 0 ? 'bg-red-900/20 border border-red-800' : apexResult.alert_statistics?.high > 0 ? 'bg-orange-900/20 border border-orange-800' : 'bg-green-900/20 border border-green-800'}`}>
              <div className="text-[10px] font-bold mb-1">💡 RECOMMENDATION</div>
              <div className="text-[11px]">{apexResult.recommendation}</div>
            </div>

            {/* Threat Assessment */}
            <div className="bg-julius-bg rounded p-3">
              <div className="text-[10px] text-red-400 uppercase tracking-wider mb-2">Threat Assessment</div>
              <div className="text-[10px]"><span className="text-julius-muted">Risk Level:</span> <span className="font-bold" style={{ color: apexResult.threat_assessment?.risk_level === 'CRITICAL' ? '#ff3b3b' : '#ff8c00' }}>{apexResult.threat_assessment?.risk_level || 'MEDIUM'}</span></div>
              <div className="text-[10px]"><span className="text-julius-muted">Action:</span> <span className="text-yellow-400">{apexResult.threat_assessment?.recommended_action || 'Monitor'}</span></div>
            </div>

            <div className="text-[9px] text-julius-muted text-right">Real-time from AXIOM/APEX backend | {new Date(apexResult.timestamp).toLocaleTimeString()}</div>
          </div>
        )}
        
        {apexResult?.error && (
          <div className="bg-red-900/20 text-red-400 p-2 rounded text-[10px]">{apexResult.error}</div>
        )}
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Active Patterns" value={statsTyped?.active_patterns ?? 0} color="text-julius-accent" />
        <StatCard label="Total Alerts" value={statsTyped?.total_alerts ?? 0} color="text-julius-amber" />
        <StatCard label="Critical" value={dist.critical ?? 0} color="text-julius-red" />
        <StatCard label="High" value={dist.high ?? 0} color="text-julius-amber" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Patterns */}
        <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold">Detection Patterns</h3>
            <button onClick={() => { resetPForm(); setEditingPattern(null); setShowPatternForm(!showPatternForm) }}
              className="text-[10px] bg-julius-accent/20 text-julius-accent px-2 py-1 rounded hover:bg-julius-accent/30">
              {showPatternForm ? 'Cancel' : '+ New Pattern'}
            </button>
          </div>

          {showPatternForm && (
            <div className="bg-julius-bg border border-julius-border rounded-lg p-3 mb-3 space-y-2">
              <input value={pForm.name} onChange={e => setPForm(f => ({ ...f, name: e.target.value }))} placeholder="Pattern name" className="w-full bg-julius-surface border border-julius-border rounded px-2 py-1.5 text-xs text-julius-text focus:outline-none" />
              <div className="flex gap-2">
                <select value={pForm.pattern_type} onChange={e => setPForm(f => ({ ...f, pattern_type: e.target.value }))} className="flex-1 bg-julius-surface border border-julius-border rounded px-2 py-1.5 text-xs text-julius-text">
                  <option value="network">Network</option><option value="auth">Auth</option><option value="behavioral">Behavioral</option>
                </select>
                <select value={pForm.severity} onChange={e => setPForm(f => ({ ...f, severity: e.target.value }))} className="flex-1 bg-julius-surface border border-julius-border rounded px-2 py-1.5 text-xs text-julius-text">
                  <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option>
                </select>
              </div>
              <textarea value={pForm.description} onChange={e => setPForm(f => ({ ...f, description: e.target.value }))} placeholder="Description" rows={2} className="w-full bg-julius-surface border border-julius-border rounded px-2 py-1.5 text-xs text-julius-text focus:outline-none" />
              <input value={pForm.rules} onChange={e => setPForm(f => ({ ...f, rules: e.target.value }))} placeholder='Rules JSON: {"threshold": 10}' className="w-full bg-julius-surface border border-julius-border rounded px-2 py-1.5 text-xs font-mono text-julius-text focus:outline-none" />
              <button onClick={submitPattern} disabled={!pForm.name || addPatternMut.isPending || updatePatternMut.isPending}
                className="w-full bg-julius-accent hover:bg-julius-accent/90 disabled:opacity-40 text-white py-1.5 rounded text-xs">
                {editingPattern ? 'Update' : 'Create'} Pattern
              </button>
            </div>
          )}

          <div className="space-y-2">
            {patterns.map((p: BehaviorPattern) => (
              <div key={p.id} className="bg-julius-bg rounded-lg px-3 py-2.5 group">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${p.severity === 'critical' ? 'bg-julius-red/20 text-julius-red' : p.severity === 'high' ? 'bg-julius-amber/20 text-julius-amber' : 'bg-julius-accent/20 text-julius-accent'}`}>{p.severity}</span>
                  <span className="text-xs font-semibold text-julius-text">{p.name}</span>
                  <span className={`ml-auto text-[10px] ${p.is_active ? 'text-julius-green' : 'text-julius-muted'}`}>{p.is_active ? 'Active' : 'Inactive'}</span>
                  <button onClick={() => startEdit(p)} className="opacity-0 group-hover:opacity-100 text-julius-muted hover:text-julius-accent text-xs">✏️</button>
                  <button onClick={() => setConfirmDelete({ type: 'pattern', id: p.id })} className="opacity-0 group-hover:opacity-100 text-julius-muted hover:text-julius-red text-xs">🗑️</button>
                </div>
                <div className="text-[10px] text-julius-muted">{p.description}</div>
                <div className="text-[10px] text-julius-muted mt-1 font-mono">Type: {p.pattern_type}</div>
              </div>
            ))}
            {patterns.length === 0 && <div className="text-xs text-julius-muted text-center py-6">No patterns configured.</div>}
          </div>
        </div>

        {/* Alerts */}
        <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold">Recent Alerts</h3>
            <button onClick={() => { resetAForm(); setShowAlertForm(!showAlertForm) }}
              className="text-[10px] bg-julius-amber/20 text-julius-amber px-2 py-1 rounded hover:bg-julius-amber/30">
              {showAlertForm ? 'Cancel' : '+ New Alert'}
            </button>
          </div>

          {showAlertForm && (
            <div className="bg-julius-bg border border-julius-border rounded-lg p-3 mb-3 space-y-2">
              <input value={aForm.alert_type} onChange={e => setAForm(f => ({ ...f, alert_type: e.target.value }))} placeholder="Alert type" className="w-full bg-julius-surface border border-julius-border rounded px-2 py-1.5 text-xs text-julius-text focus:outline-none" />
              <select value={aForm.severity} onChange={e => setAForm(f => ({ ...f, severity: e.target.value }))} className="w-full bg-julius-surface border border-julius-border rounded px-2 py-1.5 text-xs text-julius-text">
                <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option>
              </select>
              <input value={aForm.message} onChange={e => setAForm(f => ({ ...f, message: e.target.value }))} placeholder="Alert message" className="w-full bg-julius-surface border border-julius-border rounded px-2 py-1.5 text-xs text-julius-text focus:outline-none" />
              <select value={aForm.pattern_id} onChange={e => setAForm(f => ({ ...f, pattern_id: e.target.value }))} className="w-full bg-julius-surface border border-julius-border rounded px-2 py-1.5 text-xs text-julius-text">
                <option value="">No pattern</option>
                {patterns.map((p: BehaviorPattern) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <button onClick={submitAlert} disabled={!aForm.alert_type || !aForm.message || addAlertMut.isPending}
                className="w-full bg-julius-amber hover:bg-julius-amber/90 disabled:opacity-40 text-white py-1.5 rounded text-xs">
                Create Alert
              </button>
            </div>
          )}

          <div className="space-y-2 max-h-96 overflow-y-auto">
            {alerts.map((a: BehaviorAlert) => (
              <div key={a.id} className="bg-julius-bg rounded-lg px-3 py-2 group">
                <div className="flex items-center gap-2">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${a.severity === 'critical' ? 'bg-julius-red/20 text-julius-red' : a.severity === 'high' ? 'bg-julius-amber/20 text-julius-amber' : 'bg-julius-accent/20 text-julius-accent'}`}>{a.severity}</span>
                  <span className="text-xs text-julius-text truncate flex-1">{a.message}</span>
                  <button onClick={() => setConfirmDelete({ type: 'alert', id: a.id })} className="opacity-0 group-hover:opacity-100 text-julius-muted hover:text-julius-red text-xs shrink-0">🗑️</button>
                </div>
                <div className="text-[10px] text-julius-muted mt-1 font-mono">{a.alert_type} | {new Date(a.created_at).toLocaleString()}</div>
              </div>
            ))}
            {alerts.length === 0 && <div className="text-xs text-julius-muted text-center py-6">No alerts recorded.</div>}
          </div>
        </div>
      </div>

      {/* Delete confirmation modal */}
      {confirmDelete && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center" onClick={() => setConfirmDelete(null)}>
          <div className="bg-julius-surface border border-julius-border rounded-xl p-6 max-w-sm" onClick={e => e.stopPropagation()}>
            <h3 className="text-sm font-bold mb-2">Confirm Delete</h3>
            <p className="text-xs text-julius-muted mb-4">Are you sure you want to delete this {confirmDelete.type}? This cannot be undone.</p>
            <div className="flex gap-2">
              <button onClick={() => setConfirmDelete(null)} className="flex-1 text-xs py-2 rounded border border-julius-border hover:bg-julius-surface2">Cancel</button>
              <button onClick={() => confirmDelete.type === 'pattern' ? deletePatternMut.mutate(confirmDelete.id) : deleteAlertMut.mutate(confirmDelete.id)}
                className="flex-1 text-xs py-2 rounded bg-julius-red text-white hover:bg-julius-red/90">Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: ReactNode; color: string }) {
  return (
    <div className="bg-julius-surface border border-julius-border rounded-xl p-4 text-center">
      <div className="text-[10px] text-julius-muted uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-2xl font-bold font-mono ${color}`}>{value}</div>
    </div>
  )
}