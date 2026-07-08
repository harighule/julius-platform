import type { NetworkMetrics } from '../api/guardian'

interface HealthProps {
  data?: {
    breakdown: { healthy: number; warning: number; critical: number }
    total_nodes: number
    nodes: Array<{
      node_id: string
      health_status: string
      latency_avg_ms: number
      queue_size: number
      uptime_seconds: number
      timestamp: string
    }>
  }
  network?: NetworkMetrics
  loading?: boolean
}

function HealthOrb({ status }: { status: 'healthy' | 'warning' | 'critical' }) {
  const cfg = {
    healthy:  { color: '#00ff88', label: 'HEALTHY',  shadow: '0 0 24px rgba(0,255,136,0.6)' },
    warning:  { color: '#ffaa00', label: 'WARNING',  shadow: '0 0 24px rgba(255,170,0,0.6)' },
    critical: { color: '#ff3355', label: 'CRITICAL', shadow: '0 0 24px rgba(255,51,85,0.6)' },
  }[status]

  return (
    <div className="flex flex-col items-center gap-2">
      <div
        className="w-14 h-14 rounded-full border-2 flex items-center justify-center animate-pulse"
        style={{ borderColor: cfg.color, boxShadow: cfg.shadow, background: cfg.color + '18' }}
      >
        <div className="w-6 h-6 rounded-full" style={{ background: cfg.color, boxShadow: cfg.shadow }} />
      </div>
      <span className="text-[10px] font-black tracking-[0.3em] font-mono" style={{ color: cfg.color }}>
        {cfg.label}
      </span>
    </div>
  )
}

function Stat({ label, value, accent }: { label: string; value: string | number; accent?: string }) {
  return (
    <div className="border border-julius-border bg-julius-surface2/50 px-3 py-2 flex flex-col gap-0.5">
      <div className="text-[8px] font-black tracking-[0.25em] text-julius-muted font-mono">{label}</div>
      <div className={`text-sm font-black font-mono ${accent ?? 'text-julius-text'}`}>{value}</div>
    </div>
  )
}

function Bar({ label, count, total, color }: { label: string; count: number; total: number; color: string }) {
  const pct = total ? Math.round((count / total) * 100) : 0
  return (
    <div className="flex items-center gap-2 text-[9px] font-mono">
      <span className="w-14 text-julius-muted tracking-widest">{label}</span>
      <div className="flex-1 h-1.5 bg-julius-border rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all duration-700" style={{ width: `${pct}%`, background: color, boxShadow: `0 0 6px ${color}` }} />
      </div>
      <span className="w-6 text-right font-bold" style={{ color }}>{count}</span>
    </div>
  )
}

function fmtBw(bps: number) {
  if (bps >= 1e9) return `${(bps / 1e9).toFixed(2)} Gbps`
  if (bps >= 1e6) return `${(bps / 1e6).toFixed(2)} Mbps`
  return `${(bps / 1e3).toFixed(0)} Kbps`
}

export function NetworkHealth({ data, network, loading }: HealthProps) {
  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-8 bg-julius-surface2 border border-julius-border animate-pulse" />
        ))}
      </div>
    )
  }

  const breakdown = data?.breakdown ?? { healthy: 0, warning: 0, critical: 0 }
  const total = data?.total_nodes ?? 0
  const overallStatus: 'healthy' | 'warning' | 'critical' =
    breakdown.critical > 0 ? 'critical' : breakdown.warning > 0 ? 'warning' : 'healthy'

  return (
    <div className="space-y-4">
      {/* Overall orb + stats */}
      <div className="flex items-center gap-6">
        <HealthOrb status={overallStatus} />
        <div className="flex-1 grid grid-cols-2 gap-2">
          <Stat label="TOTAL_NODES" value={total} />
          <Stat label="ACTIVE_NODES" value={
            (() => {
              const fromBreakdown = breakdown.healthy + breakdown.warning
              const fromNetwork = network?.active_nodes ?? 0
              // Prefer breakdown count when network metric says 0 but breakdown disagrees
              return fromNetwork > 0 ? fromNetwork : fromBreakdown
            })()
          } accent="text-julius-accent" />
          <Stat label="AVG_LATENCY" value={network?.average_latency_ms != null ? `${network.average_latency_ms.toFixed(1)}ms` : '—'} accent="text-julius-amber" />
          <Stat label="BANDWIDTH" value={network?.total_bandwidth_bps != null ? fmtBw(network.total_bandwidth_bps) : '—'} accent="text-julius-green" />
        </div>
      </div>

      {/* Breakdown bars */}
      <div className="border border-julius-border bg-julius-surface2/30 px-3 py-3 space-y-2">
        <div className="text-[8px] font-black tracking-[0.3em] text-julius-muted font-mono mb-2">NODE_BREAKDOWN</div>
        <Bar label="HEALTHY" count={breakdown.healthy}  total={total} color="#00ff88" />
        <Bar label="WARNING" count={breakdown.warning}  total={total} color="#ffaa00" />
        <Bar label="CRITICAL" count={breakdown.critical} total={total} color="#ff3355" />
      </div>

      {/* Network throughput extras */}
      {network && (
        <div className="grid grid-cols-2 gap-2">
          <Stat label="TOTAL_QUEUE" value={network.total_queue_size.toLocaleString()} />
          <Stat label="PKTS_PROCESSED" value={network.total_packets_processed.toLocaleString()} accent="text-julius-accent" />
        </div>
      )}
    </div>
  )
}
