import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { insights } from '../lib/api'

interface WorkflowRow {
  id: string | number
  name: string
  description?: string
  trigger_type: string
  is_active: boolean
}

type AnalyticsPayload = {
  severity_counts?: Record<string, number>
  vuln_by_service?: Record<string, unknown>
  scan_coverage?: Record<string, unknown>
  scan_types?: Record<string, number>
  event_breakdown?: Record<string, unknown>
  alert_severity?: Record<string, number>
  alert_types?: Record<string, number>
  behavioral?: { total_alerts?: number; active_patterns?: number }
  overview?: Record<string, number>
  total_vulns?: number
  total_events?: number
}

type DashboardPayload = { stats?: Record<string, number> }

export function InsightsPanel() {
  const { data: analytics, isLoading } = useQuery({ queryKey: ['analytics'], queryFn: insights.analytics, refetchInterval: 15000 })
  const { data: dashboard } = useQuery({ queryKey: ['insights-dash'], queryFn: insights.dashboard, refetchInterval: 15000 })
  const { data: workflowsData } = useQuery({ queryKey: ['workflows'], queryFn: insights.workflows, refetchInterval: 15000 })

  const a = analytics as AnalyticsPayload | undefined
  const dsh = dashboard as DashboardPayload | undefined

  const sevCounts = a?.severity_counts || {}
  const vulnBySvc = a?.vuln_by_service || {}
  const scanCoverage = a?.scan_coverage || {}
  const scanTypes = a?.scan_types || {}
  const eventBreakdown = a?.event_breakdown || {}
  const alertSev = a?.alert_severity || {}
  const alertTypes = a?.alert_types || {}
  const behavioral = a?.behavioral || {}
  const workflows = (workflowsData as { workflows?: WorkflowRow[] } | undefined)?.workflows ?? []
  const overview = a?.overview || dsh?.stats || {}

  if (isLoading) return <div className="flex items-center justify-center h-full"><span className="text-julius-muted text-sm">Loading analytics...</span></div>

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">
      <h1 className="text-xl font-bold tracking-wide">Analytics & Insights</h1>

      {/* Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <Card label="Scans" value={overview.total_scans ?? 0} color="text-julius-accent" />
        <Card label="Vulnerabilities" value={a?.total_vulns ?? 0} color="text-julius-red" />
        <Card label="Events" value={a?.total_events ?? 0} color="text-julius-green" />
        <Card label="Alerts" value={behavioral.total_alerts ?? 0} color="text-julius-amber" />
        <Card label="Patterns" value={behavioral.active_patterns ?? 0} color="text-julius-accent" />
        <Card label="Workflows" value={workflows.length} color="text-julius-text" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Vulnerability severity */}
        <div className="bg-julius-surface border border-julius-border rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-4">Vulnerability Severity</h3>
          {Object.keys(sevCounts).length > 0 ? (
            <div className="space-y-3">
              {Object.entries(sevCounts as Record<string, number>).sort(([a], [b]) => sevOrder(a) - sevOrder(b)).map(([sev, count]) => {
                const total = a?.total_vulns || 1
                return (
                  <div key={sev} className="flex items-center gap-3">
                    <span className={`text-[10px] px-2 py-0.5 rounded font-bold w-16 text-center ${sevBadge(sev)}`}>{sev}</span>
                    <div className="flex-1 h-3 bg-julius-bg rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${sevBar(sev)}`} style={{ width: `${(count / total) * 100}%` }} />
                    </div>
                    <span className="text-xs font-mono text-julius-text w-8 text-right">{count}</span>
                  </div>
                )
              })}
            </div>
          ) : <Empty text="No vulnerabilities found yet. Run a scan." />}
        </div>

        {/* Vulnerabilities by service */}
        <div className="bg-julius-surface border border-julius-border rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-4">Vulnerabilities by Service</h3>
          {Object.keys(vulnBySvc).length > 0 ? (
            <div className="space-y-2">
              {Object.entries(vulnBySvc as Record<string, number>).sort(([, a], [, b]) => b - a).map(([svc, count]) => (
                <div key={svc} className="flex items-center gap-3">
                  <span className="text-[10px] font-mono text-julius-accent w-24 truncate">{svc}</span>
                  <div className="flex-1 h-2 bg-julius-bg rounded-full overflow-hidden">
                    <div className="h-full bg-julius-red rounded-full" style={{ width: `${(count / Math.max(...Object.values(vulnBySvc as Record<string, number>))) * 100}%` }} />
                  </div>
                  <span className="text-[10px] font-mono text-julius-muted w-6 text-right">{count}</span>
                </div>
              ))}
            </div>
          ) : <Empty text="No vulnerability data yet." />}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Event distribution */}
        <div className="bg-julius-surface border border-julius-border rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-4">Event Type Distribution</h3>
          {Object.keys(eventBreakdown).length > 0 ? (
            <div className="space-y-2">
              {Object.entries(eventBreakdown as Record<string, number>).sort(([, a], [, b]) => b - a).slice(0, 12).map(([type, count]) => (
                <div key={type} className="flex items-center gap-3">
                  <span className="text-[10px] font-mono text-julius-accent w-36 truncate">{type}</span>
                  <div className="flex-1 h-2 bg-julius-bg rounded-full overflow-hidden">
                    <div className="h-full bg-julius-accent rounded-full" style={{ width: `${(count / Math.max(...Object.values(eventBreakdown as Record<string, number>), 1)) * 100}%` }} />
                  </div>
                  <span className="text-[10px] font-mono text-julius-muted w-8 text-right">{count}</span>
                </div>
              ))}
            </div>
          ) : <Empty text="No events yet." />}
        </div>

        {/* Alert breakdown */}
        <div className="bg-julius-surface border border-julius-border rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-4">Alert Analysis</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <h4 className="text-[10px] text-julius-muted uppercase mb-2">By Severity</h4>
              {Object.keys(alertSev).length > 0 ? (
                <div className="space-y-1">
                  {Object.entries(alertSev as Record<string, number>).sort(([a], [b]) => sevOrder(a) - sevOrder(b)).map(([sev, count]) => (
                    <div key={sev} className="flex items-center justify-between text-xs py-0.5">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${sevBadge(sev)}`}>{sev}</span>
                      <span className="font-mono text-julius-text">{count}</span>
                    </div>
                  ))}
                </div>
              ) : <Empty text="No alerts" />}
            </div>
            <div>
              <h4 className="text-[10px] text-julius-muted uppercase mb-2">By Type</h4>
              {Object.keys(alertTypes).length > 0 ? (
                <div className="space-y-1">
                  {Object.entries(alertTypes as Record<string, number>).sort(([, a], [, b]) => b - a).map(([type, count]) => (
                    <div key={type} className="flex items-center justify-between text-[10px] py-0.5">
                      <span className="text-julius-muted truncate max-w-[70%]">{type}</span>
                      <span className="font-mono text-julius-accent">{count}</span>
                    </div>
                  ))}
                </div>
              ) : <Empty text="No alerts" />}
            </div>
          </div>
        </div>
      </div>

      {/* Scan coverage */}
      <div className="bg-julius-surface border border-julius-border rounded-xl p-5">
        <h3 className="text-sm font-semibold mb-4">Scan Coverage</h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4">
          <Mini label="Total Scans" value={Number((scanCoverage as Record<string, number>).total_scans ?? 0)} />
          <Mini label="Completed" value={Number((scanCoverage as Record<string, number>).completed ?? 0)} />
          <Mini label="Running" value={Number((scanCoverage as Record<string, number>).running ?? 0)} />
          <Mini label="Unique Targets" value={Number((scanCoverage as Record<string, number>).unique_targets ?? 0)} />
          <Mini label="Open Ports Found" value={Number((scanCoverage as Record<string, number>).total_open_ports ?? 0)} />
        </div>
        {Object.keys(scanTypes).length > 0 && (
          <div>
            <h4 className="text-[10px] text-julius-muted uppercase mb-2">Scan Types</h4>
            <div className="flex flex-wrap gap-2">
              {Object.entries(scanTypes as Record<string, number>).map(([type, count]) => (
                <span key={type} className="text-[10px] bg-julius-bg border border-julius-border rounded px-2 py-1">
                  <span className="text-julius-accent">{type}</span>: <span className="font-mono text-julius-text">{count}</span>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Workflows */}
      <div className="bg-julius-surface border border-julius-border rounded-xl p-5">
        <h3 className="text-sm font-semibold mb-4">Workflows ({workflows.length})</h3>
        {workflows.length > 0 ? (
          <div className="space-y-2">
            {workflows.map((w: WorkflowRow) => (
              <div key={w.id} className="bg-julius-bg rounded-lg px-4 py-3 flex items-center justify-between">
                <div>
                  <div className="text-xs font-semibold text-julius-text">{w.name}</div>
                  <div className="text-[10px] text-julius-muted">{w.description || 'No description'}</div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[10px] text-julius-muted font-mono">{w.trigger_type}</span>
                  <span className={`text-[10px] px-2 py-0.5 rounded ${w.is_active ? 'bg-julius-green/20 text-julius-green' : 'bg-julius-muted/20 text-julius-muted'}`}>
                    {w.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : <Empty text="No workflows yet. Create one from the chat: 'investigate 192.168.1.1'" />}
      </div>
    </div>
  )
}

function Card({ label, value, color }: { label: string; value: number | string; color: string }) {
  return (
    <div className="bg-julius-surface border border-julius-border rounded-xl p-4 text-center">
      <div className="text-[10px] text-julius-muted uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-2xl font-bold font-mono ${color}`}>{value}</div>
    </div>
  )
}

function Mini({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="bg-julius-bg border border-julius-border rounded-lg p-3 text-center">
      <div className="text-[9px] text-julius-muted uppercase tracking-wider">{label}</div>
      <div className="text-lg font-bold font-mono text-julius-accent">{value}</div>
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return <div className="text-xs text-julius-muted text-center py-6">{text}</div>
}

function sevOrder(s: string): number {
  return { critical: 0, high: 1, medium: 2, low: 3, info: 4 }[s] ?? 5
}

function sevBadge(s: string): string {
  if (s === 'critical') return 'bg-julius-red/20 text-julius-red'
  if (s === 'high') return 'bg-julius-amber/20 text-julius-amber'
  if (s === 'medium') return 'bg-yellow-600/20 text-yellow-500'
  return 'bg-julius-accent/20 text-julius-accent'
}

function sevBar(s: string): string {
  if (s === 'critical') return 'bg-julius-red'
  if (s === 'high') return 'bg-julius-amber'
  if (s === 'medium') return 'bg-yellow-500'
  return 'bg-julius-accent'
}
