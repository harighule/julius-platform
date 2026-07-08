import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  getRevenueSummary,
  getRevenueTrend,
  getNodeMetrics,
  getNetworkHealth,
  getNetworkMetrics,
} from '../api/guardian'
import { RevenueChart } from '../components/RevenueChart'
import { NodeGrid } from '../components/NodeGrid'
import { NetworkHealth } from '../components/NetworkHealth'
import { TransactionsTable } from '../components/TransactionsTable'
import { AlertList } from '../components/AlertList'

// ─── helper sub-components ────────────────────────────────────────────────────

function Section({
  id,
  title,
  badge,
  children,
  className = '',
}: {
  id?: string
  title: string
  badge?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <div id={id} className={`bg-julius-surface border border-julius-border flex flex-col ${className}`}>
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-julius-border bg-julius-surface2/60">
        <div className="w-1 h-4 bg-julius-accent shadow-[0_0_6px_var(--color-julius-accent)]" />
        <span className="font-display text-[10px] font-black tracking-[0.3em] text-julius-accent">{title}</span>
        {badge}
        <div className="ml-auto flex gap-1">
          <div className="w-1.5 h-1.5 rounded-full bg-julius-border" />
          <div className="w-1.5 h-1.5 rounded-full bg-julius-green/50" />
        </div>
      </div>
      <div className="p-4 flex-1 overflow-auto">{children}</div>
    </div>
  )
}

function KpiCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string
  value: string | number
  sub?: string
  accent?: string
}) {
  return (
    <div className="bg-julius-surface border border-julius-border px-4 py-3 hover:border-julius-accent/40 transition-colors group">
      <div className="text-[8px] font-black tracking-[0.3em] text-julius-muted font-mono mb-1">{label}</div>
      <div className={`text-xl font-black font-display ${accent ?? 'text-julius-text'} group-hover:text-white transition-colors`}>
        {value}
      </div>
      {sub && <div className="text-[9px] text-julius-muted font-mono mt-0.5">{sub}</div>}
    </div>
  )
}

function Ticker({ lastRefresh }: { lastRefresh: Date }) {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])
  const secsAgo = Math.floor((now.getTime() - lastRefresh.getTime()) / 1000)
  const nextIn   = Math.max(0, 30 - secsAgo)

  return (
    <span className="text-[8px] font-mono text-julius-muted tracking-widest">
      REFRESH IN {nextIn}s
    </span>
  )
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────

export function GuardianDashboard() {
  const REFETCH_MS = 30_000

  const [lastRefresh, setLastRefresh] = useState(new Date())
  const [isAdmin] = useState(() => {
    try { return JSON.parse(localStorage.getItem('julius_user') ?? '{}').role === 'admin' }
    catch { return false }
  })

  const summaryQ = useQuery({
    queryKey: ['guardian-revenue-summary'],
    queryFn: getRevenueSummary,
    refetchInterval: REFETCH_MS,
  })

  const trendQ = useQuery({
    queryKey: ['guardian-revenue-trend'],
    queryFn: getRevenueTrend,
    refetchInterval: REFETCH_MS,
  })

  const nodesQ = useQuery({
    queryKey: ['guardian-node-metrics'],
    queryFn: getNodeMetrics,
    refetchInterval: REFETCH_MS,
  })

  const healthQ = useQuery({
    queryKey: ['guardian-network-health'],
    queryFn: getNetworkHealth,
    refetchInterval: REFETCH_MS,
  })

  const networkQ = useQuery({
    queryKey: ['guardian-network-metrics'],
    queryFn: getNetworkMetrics,
    refetchInterval: REFETCH_MS,
  })

  // Track last successful refresh
  useEffect(() => {
    if (!summaryQ.isFetching && !trendQ.isFetching && !nodesQ.isFetching) {
      setLastRefresh(new Date())
    }
  }, [summaryQ.isFetching, trendQ.isFetching, nodesQ.isFetching])

  const s = summaryQ.data
  const nodes = nodesQ.data?.nodes ?? []
  const criticalAlerts = healthQ.data?.breakdown?.critical ?? 0

  return (
    <div className="h-full overflow-y-auto bg-julius-bg p-4 space-y-4">

      {/* ── Top bar ─────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-base font-black tracking-[0.4em] text-julius-accent glow-cyan">
            GUARDIAN_DASHBOARD
          </h1>
          <p className="text-[9px] text-julius-muted font-mono tracking-widest mt-0.5">
            NETWORK REVENUE · NODE STATUS · TRANSACTION AUDIT · HEALTH MONITOR
          </p>
        </div>
        <div className="flex items-center gap-4">
          <Ticker lastRefresh={lastRefresh} />
          {criticalAlerts > 0 && (
            <div className="flex items-center gap-1.5 px-2 py-1 border border-julius-red/40 bg-julius-red/10 animate-pulse">
              <div className="w-1.5 h-1.5 rounded-full bg-julius-red" />
              <span className="text-[8px] font-black tracking-widest text-julius-red font-mono">
                {criticalAlerts} CRITICAL
              </span>
            </div>
          )}
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-julius-green animate-pulse" />
            <span className="text-[8px] font-mono text-julius-green tracking-widest">LIVE</span>
          </div>
        </div>
      </div>

      {/* ── KPI row ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
        <KpiCard
          label="TOTAL_REVENUE"
          value={s ? `$${s.total_revenue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '…'}
          accent="text-julius-green"
        />
        <KpiCard
          label="TODAY"
          value={s ? `$${s.revenue_today.toFixed(2)}` : '…'}
          accent="text-julius-green"
        />
        <KpiCard
          label="THIS_WEEK"
          value={s ? `$${s.revenue_this_week.toFixed(2)}` : '…'}
          accent="text-julius-amber"
        />
        <KpiCard
          label="THIS_MONTH"
          value={s ? `$${s.revenue_this_month.toFixed(2)}` : '…'}
          accent="text-julius-amber"
        />
        <KpiCard
          label="AVG_DAILY"
          value={s ? `$${s.average_daily_revenue.toFixed(2)}` : '…'}
        />
        <KpiCard
          label="TOTAL_NODES"
          value={s?.node_count ?? '…'}
          accent="text-julius-accent"
        />
        <KpiCard
          label="ACTIVE_NODES"
          value={s?.active_nodes ?? '…'}
          accent="text-julius-accent"
          sub={s ? `${Math.round((s.active_nodes / s.node_count) * 100)}% online` : undefined}
        />
      </div>

      {/* ── Revenue chart + Network health ──────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Section id="guardian-revenue" title="REVENUE_TREND_30D" className="lg:col-span-2">
          <RevenueChart
            data={trendQ.data ?? []}
            loading={trendQ.isLoading}
          />
        </Section>

        <Section id="guardian-network-health" title="NETWORK_HEALTH">
          <NetworkHealth
            data={healthQ.data}
            network={networkQ.data}
            loading={healthQ.isLoading && networkQ.isLoading}
          />
        </Section>
      </div>

      {/* ── Node grid ───────────────────────────────────────────────── */}
      <Section
        id="guardian-nodes"
        title="NODE_STATUS_GRID"
        badge={
          nodes.length > 0 && (
            <span className="text-[8px] font-mono text-julius-muted ml-1 tracking-widest">
              [{nodes.length} NODES]
            </span>
          )
        }
      >
        <NodeGrid nodes={nodes} loading={nodesQ.isLoading} />
      </Section>

      {/* ── Transactions + Alerts ───────────────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Section id="guardian-transactions" title="TRANSACTION_LEDGER" className="xl:col-span-2">
          <TransactionsTable />
        </Section>

        <Section
          id="guardian-alerts"
          title="DETECTOR_ALERTS"
          badge={
            criticalAlerts > 0 && (
              <span className="ml-1 text-[8px] font-black tracking-widest text-julius-red animate-pulse">
                ● {criticalAlerts} CRIT
              </span>
            )
          }
        >
          <AlertList isAdmin={isAdmin} />
        </Section>
      </div>

    </div>
  )
}
