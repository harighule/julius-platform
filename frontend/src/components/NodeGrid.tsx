import { useState } from 'react'
import type { NodeMetric } from '../api/guardian'

interface Props {
  nodes: NodeMetric[]
  loading?: boolean
}

const STATUS_CONFIG = {
  healthy: { color: 'text-julius-green', bg: 'bg-julius-green/10', border: 'border-julius-green/30', dot: 'bg-julius-green', glow: '0 0 8px rgba(0,255,136,0.5)', label: 'HEALTHY' },
  warning: { color: 'text-julius-amber', bg: 'bg-julius-amber/10', border: 'border-julius-amber/30', dot: 'bg-julius-amber', glow: '0 0 8px rgba(255,170,0,0.5)', label: 'WARNING' },
  critical: { color: 'text-julius-red', bg: 'bg-julius-red/10', border: 'border-julius-red/30', dot: 'bg-julius-red', glow: '0 0 8px rgba(255,51,85,0.5)', label: 'CRITICAL' },
}

function fmtUptime(s: number) {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return `${h}h ${m}m`
}

function fmtBytes(bps?: number) {
  if (!bps) return '—'
  if (bps >= 1e9) return `${(bps / 1e9).toFixed(1)} Gbps`
  if (bps >= 1e6) return `${(bps / 1e6).toFixed(1)} Mbps`
  return `${(bps / 1e3).toFixed(0)} Kbps`
}

function NodeCard({ node, onClick, selected }: { node: NodeMetric; onClick: () => void; selected: boolean }) {
  const status = STATUS_CONFIG[node.health_status] ?? STATUS_CONFIG.warning
  const m = node.latest_metric

  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-3 border transition-all duration-200 hover:border-julius-accent/40 hover:bg-julius-surface2 group relative ${
        selected
          ? 'border-julius-accent/60 bg-julius-accent/5'
          : `border-julius-border ${status.bg}`
      }`}
    >
      {/* status glow bar */}
      <div className={`absolute left-0 top-0 bottom-0 w-0.5 ${status.dot}`} style={{ boxShadow: status.glow }} />

      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className={`w-1.5 h-1.5 rounded-full ${status.dot} animate-pulse`} />
          <span className="font-mono text-[10px] font-black tracking-wider text-julius-text truncate max-w-[90px]">
            {node.node_id.split('_').slice(-2).join('_')}
          </span>
        </div>
        <span className={`text-[8px] font-black tracking-[0.2em] px-1.5 py-0.5 border ${status.color} ${status.border} ${status.bg}`}>
          {status.label}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[9px] font-mono">
        <div className="text-julius-muted">LATENCY</div>
        <div className={`font-bold text-right ${m.latency_avg_ms > 200 ? 'text-julius-red' : m.latency_avg_ms > 100 ? 'text-julius-amber' : 'text-julius-green'}`}>
          {m.latency_avg_ms?.toFixed(0) ?? '—'}ms
        </div>

        <div className="text-julius-muted">UPTIME</div>
        <div className="text-julius-accent font-bold text-right">{fmtUptime(m.uptime_seconds)}</div>

        <div className="text-julius-muted">QUEUE</div>
        <div className={`font-bold text-right ${m.queue_size > 100 ? 'text-julius-red' : 'text-julius-text'}`}>
          {m.queue_size ?? 0}
        </div>

        <div className="text-julius-muted">BW</div>
        <div className="text-julius-text font-bold text-right">{fmtBytes(m.bandwidth_bps)}</div>
      </div>

      {selected && (
        <div className="mt-2 pt-2 border-t border-julius-border text-[9px] font-mono text-julius-muted">
          <div className="flex justify-between">
            <span>PACKETS</span>
            <span className="text-julius-text">{m.packets_processed?.toLocaleString() ?? '—'}</span>
          </div>
        </div>
      )}
    </button>
  )
}

export function NodeGrid({ nodes, loading }: Props) {
  const [selected, setSelected] = useState<string | null>(null)

  if (loading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-28 bg-julius-surface2 border border-julius-border animate-pulse" />
        ))}
      </div>
    )
  }

  if (!nodes?.length) {
    return (
      <div className="flex items-center justify-center h-32 text-julius-muted font-mono text-xs tracking-widest">
        NO_NODES_DETECTED
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2">
      {nodes.map(n => (
        <NodeCard
          key={n.node_id}
          node={n}
          selected={selected === n.node_id}
          onClick={() => setSelected(prev => prev === n.node_id ? null : n.node_id)}
        />
      ))}
    </div>
  )
}
