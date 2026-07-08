import {
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Area, AreaChart, ReferenceLine,
} from 'recharts'
import type { RevenueTrendPoint } from '../api/guardian'

interface Props {
  data: RevenueTrendPoint[]
  loading?: boolean
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-julius-surface border border-julius-border px-3 py-2 text-[11px] font-mono shadow-xl">
      <div className="text-julius-muted mb-1 tracking-widest">{label}</div>
      <div className="text-julius-green font-bold">
        ${payload[0]?.value?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </div>
      {payload[1] && (
        <div className="text-julius-accent mt-0.5">
          {payload[1].value} txns
        </div>
      )}
    </div>
  )
}

export function RevenueChart({ data, loading }: Props) {
  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <div className="flex gap-1">
          {[0, 1, 2].map(i => (
            <div key={i} className="w-1 h-6 bg-julius-accent/40 animate-pulse rounded" style={{ animationDelay: `${i * 150}ms` }} />
          ))}
        </div>
      </div>
    )
  }

  if (!data?.length) {
    return (
      <div className="flex items-center justify-center h-48 text-julius-muted font-mono text-xs tracking-widest">
        NO_REVENUE_DATA
      </div>
    )
  }

  const avg = data.reduce((s, d) => s + d.revenue, 0) / data.length

  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="revenueGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#00ff88" stopOpacity={0.18} />
            <stop offset="95%" stopColor="#00ff88" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="2 4" stroke="#1a1d2e" vertical={false} />
        <XAxis
          dataKey="date"
          tickFormatter={(v: string) => v.slice(5)}
          tick={{ fill: '#5a6278', fontSize: 9, fontFamily: 'JetBrains Mono', fontWeight: 700 }}
          tickLine={false}
          axisLine={{ stroke: '#1a1d2e' }}
          interval="preserveStartEnd"
        />
        <YAxis
          tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
          tick={{ fill: '#5a6278', fontSize: 9, fontFamily: 'JetBrains Mono', fontWeight: 700 }}
          tickLine={false}
          axisLine={false}
          width={44}
        />
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine
          y={avg}
          stroke="#ffaa00"
          strokeDasharray="4 4"
          strokeOpacity={0.4}
        />
        <Area
          type="monotone"
          dataKey="revenue"
          stroke="#00ff88"
          strokeWidth={2}
          fill="url(#revenueGrad)"
          dot={false}
          activeDot={{ r: 4, fill: '#00ff88', stroke: '#0a0a0f', strokeWidth: 2 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
