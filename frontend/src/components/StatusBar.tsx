import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { live, system } from '../lib/api'
import { ReportControls } from './ReportControls'

type HealthPayload = { status?: string; version?: string }
type SystemPayload = {
  cpu_percent?: number
  memory_percent?: number
  net_mb_sent?: number
  net_mb_recv?: number
  connections_established?: number
  hostname?: string
}

type LiveDashPayload = {
  system?: SystemPayload
  stats?: Record<string, number | undefined>
}

export function StatusBar() {
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: system.health, refetchInterval: 15000, retry: 1 })
  const { data: dash } = useQuery({ queryKey: ['live-dash-bar'], queryFn: live.dashboard, refetchInterval: 5000, retry: 1 })

  const healthTyped = health as HealthPayload | undefined
  const dashTyped = dash as LiveDashPayload | undefined
  const sys: SystemPayload = dashTyped?.system ?? {}
  const stats = dashTyped?.stats ?? {}

  return (
    <div className="h-10 bg-julius-surface border-b border-julius-border flex items-center px-5 gap-6 shrink-0 overflow-x-auto relative">
      <div className="absolute bottom-0 left-0 w-full h-[1px] bg-julius-accent/20"></div>
      <div className="flex items-center gap-2">
        <div className={`w-1.5 h-1.5 rounded-full ${healthTyped?.status === 'healthy' ? 'bg-julius-green shadow-[0_0_8px_var(--color-julius-green)]' : 'bg-julius-red shadow-[0_0_8px_var(--color-julius-red)]'} animate-pulse`} />
        <span className="text-[11px] text-julius-accent font-black tracking-[0.2em] font-display glow-cyan">SYS_INF</span>
      </div>
      <Sep />
      <div className="flex gap-4 items-center">
        <Pill label="CPU" value={`${Math.round(Number(sys.cpu_percent ?? 0))}%`} color={Number(sys.cpu_percent ?? 0) > 80 ? 'text-julius-red glow-red' : 'text-julius-green glow-green'} />
        <Pill label="RAM" value={`${Math.round(Number(sys.memory_percent ?? 0))}%`} color={Number(sys.memory_percent ?? 0) > 80 ? 'text-julius-red glow-red' : 'text-julius-green glow-green'} />
      </div>
      <Sep />
      <div className="flex gap-4 items-center">
        <Pill label="SCANS" value={stats.total_scans ?? 0} />
        <Pill label="VULNS" value={stats.total_vulnerabilities ?? 0} color="text-julius-red glow-red" />
        <Pill label="EVENTS" value={stats.total_events ?? 0} />
      </div>
      <Sep />
      <div className="flex gap-4 items-center">
        <Pill label="TRAFFIC" value={`↑${sys.net_mb_sent ?? 0} ↓${sys.net_mb_recv ?? 0}`} />
        <Pill label="CONNS" value={sys.connections_established ?? 0} color="text-julius-accent glow-cyan" />
      </div>
      <div className="ml-auto flex items-center gap-3">
        <ReportControls />
        <div className="text-[9px] text-julius-muted font-mono uppercase tracking-widest hidden md:block">
          {sys.hostname} <span className="text-julius-border mx-1">|</span> {healthTyped?.status?.toUpperCase()} <span className="text-julius-border mx-1">|</span> v{healthTyped?.version || '1.0.0'}
        </div>
      </div>
    </div>
  )
}

function Pill({ label, value, color }: { label: string; value: ReactNode; color?: string }) {
  return (
    <span className="text-[9px] text-julius-muted whitespace-nowrap uppercase tracking-tighter">
      {label} <span className={`font-mono font-bold ml-1 ${color || 'text-julius-text'}`}>{value}</span>
    </span>
  )
}

function Sep() {
  return <div className="w-[1px] h-3 bg-julius-border shrink-0" />
}
