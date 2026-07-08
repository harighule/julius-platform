import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getAlerts, closeAlert } from '../api/guardian'
import type { Alert } from '../api/guardian'

const SEVERITY_CONFIG = {
  low:      { color: 'text-julius-accent',  border: 'border-julius-accent/30',  bg: 'bg-julius-accent/5',  bar: 'bg-julius-accent',  label: 'LOW' },
  medium:   { color: 'text-julius-amber',   border: 'border-julius-amber/30',   bg: 'bg-julius-amber/5',   bar: 'bg-julius-amber',   label: 'MED' },
  high:     { color: 'text-orange-400',     border: 'border-orange-400/30',     bg: 'bg-orange-400/5',     bar: 'bg-orange-400',     label: 'HIGH' },
  critical: { color: 'text-julius-red',     border: 'border-julius-red/30',     bg: 'bg-julius-red/5',     bar: 'bg-julius-red',     label: 'CRIT' },
}

const STATUS_CONFIG: Record<Alert['status'], { label: string; color: string }> = {
  open:           { label: 'OPEN',        color: 'text-julius-red' },
  investigating:  { label: 'INVESTIG.',   color: 'text-julius-amber' },
  mitigated:      { label: 'MITIGATED',   color: 'text-julius-green' },
  false_positive: { label: 'FALSE_POS',   color: 'text-julius-muted' },
}

function fmtAge(ts: string | undefined | null) {
  if (!ts) return '?'
  const d = new Date(ts)
  if (isNaN(d.getTime())) return '?'
  const secs = Math.floor((Date.now() - d.getTime()) / 1000)
  if (secs < 0) return 'just now'
  if (secs < 60) return `${secs}s ago`
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  return `${Math.floor(secs / 3600)}h ago`
}

interface Props {
  isAdmin?: boolean
}

export function AlertList({ isAdmin }: Props) {
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['guardian-alerts'],
    queryFn: getAlerts,
    refetchInterval: 30_000,
  })

  const { mutate: close, isPending: closing } = useMutation({
    mutationFn: closeAlert,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['guardian-alerts'] }),
  })

  const alerts: Alert[] = data?.alerts ?? []
  const activeAlerts = alerts.filter(a => a.status === 'open' || a.status === 'investigating')

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-16 bg-julius-surface2 border border-julius-border animate-pulse" />
        ))}
      </div>
    )
  }

  if (!alerts.length) {
    return (
      <div className="flex flex-col items-center justify-center h-32 gap-2">
        <div className="text-julius-green text-xl">✓</div>
        <div className="text-julius-muted text-[10px] font-mono tracking-widest">NO_ACTIVE_ALERTS</div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Summary row */}
      <div className="flex items-center gap-3 px-1 mb-1">
        <span className="text-[8px] font-black tracking-[0.3em] text-julius-muted font-mono">ALERTS_24H</span>
        <span className="text-julius-red font-black font-mono text-xs">{activeAlerts.length} ACTIVE</span>
        <span className="text-julius-muted font-mono text-[9px]">/ {alerts.length} TOTAL</span>
      </div>

      {/* Alert rows */}
      {alerts.map(alert => {
        const sev  = SEVERITY_CONFIG[alert.severity] ?? SEVERITY_CONFIG.medium
        const stat = STATUS_CONFIG[alert.status]   ?? STATUS_CONFIG.open

        return (
          <div
            key={alert.alert_id}
            className={`relative border ${sev.border} ${sev.bg} p-3 transition-all duration-200 hover:border-opacity-60 group`}
          >
            {/* left severity bar */}
            <div className={`absolute left-0 top-0 bottom-0 w-0.5 ${sev.bar}`} />

            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`text-[8px] font-black tracking-[0.2em] px-1.5 py-0.5 border ${sev.color} ${sev.border}`}>
                    {sev.label}
                  </span>
                  <span className={`text-[9px] font-bold font-mono ${stat.color}`}>
                    {stat.label}
                  </span>
                  <span className="text-[8px] text-julius-muted font-mono ml-auto">
                    {fmtAge(alert.created_at)}
                  </span>
                </div>
                <div className="text-[11px] font-bold text-julius-text truncate">
                  {alert.title}
                </div>
                <div className="text-[9px] text-julius-muted mt-0.5 line-clamp-2 font-mono">
                  {alert.description}
                </div>
                {alert.node_id && (
                  <div className="text-[9px] text-julius-accent font-mono mt-1">
                    NODE: {alert.node_id}
                  </div>
                )}
              </div>

              {/* Actions */}
              {isAdmin && alert.status === 'open' && (
                <button
                  id={`close-alert-${alert.alert_id}`}
                  onClick={() => close(alert.alert_id)}
                  disabled={closing}
                  className="shrink-0 px-2 py-1 text-[8px] font-black tracking-[0.2em] border border-julius-border text-julius-muted hover:border-julius-red/60 hover:text-julius-red transition-colors disabled:opacity-40"
                >
                  ✕ CLOSE
                </button>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
