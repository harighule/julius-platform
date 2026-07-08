/**
 * guardian.ts — API client for /api/guardian/* endpoints.
 * Automatically injects the stored JWT as a Bearer token.
 */

const BASE = '/api/guardian'

function authHeaders(): HeadersInit {
  const token = localStorage.getItem('julius_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...authHeaders(), ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`[${res.status}] ${text}`)
  }
  return res.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// Revenue
// ---------------------------------------------------------------------------

export interface RevenueSummary {
  total_revenue: number
  revenue_today: number
  revenue_this_week: number
  revenue_this_month: number
  average_daily_revenue: number
  node_count: number
  active_nodes: number
}

export interface RevenueTrendPoint {
  date: string
  revenue: number
  transactions: number
}

export interface NodeRevenue {
  node_id: string
  partner_id: string
  total_bytes: number
  total_commission: number
  revenue_share_pct: number
  payout_amount: number
}

export const getRevenueSummary = () =>
  apiFetch<RevenueSummary>('/revenue/summary')

export const getRevenueTrend = () =>
  apiFetch<RevenueTrendPoint[]>('/revenue/trend')

export const getNodeRevenue = () =>
  apiFetch<{ nodes: NodeRevenue[]; total_nodes: number }>('/revenue/nodes')

// ---------------------------------------------------------------------------
// Node metrics
// ---------------------------------------------------------------------------

export interface NodeMetric {
  node_id: string
  health_status: 'healthy' | 'warning' | 'critical'
  latest_metric: {
    timestamp: string
    latency_avg_ms: number
    queue_size: number
    uptime_seconds: number
    bandwidth_bps?: number
    packets_processed?: number
  }
}

export interface NetworkMetrics {
  timestamp: string
  total_nodes: number
  active_nodes: number
  total_bandwidth_bps: number
  average_latency_ms: number
  total_queue_size: number
  total_packets_processed: number
  health_breakdown: { healthy: number; warning: number; critical: number }
}

export const getNodeMetrics = () =>
  apiFetch<{ nodes: NodeMetric[]; count: number }>('/metrics/nodes')

export const getNetworkHealth = () =>
  apiFetch<{
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
  }>('/metrics/health')

export const getNetworkMetrics = () =>
  apiFetch<NetworkMetrics>('/metrics/network')

// ---------------------------------------------------------------------------
// Transactions
// ---------------------------------------------------------------------------

export interface Transaction {
  transaction_id: string
  node_id: string
  timestamp: string
  bytes_routed: number
  commission: number
  status: string
  partner_id?: string
}

export const getTransactions = (page = 1, size = 20, node_id?: string) => {
  const params = new URLSearchParams({ page: String(page), page_size: String(size) })
  if (node_id) params.set('node_id', node_id)
  return apiFetch<{ transactions: Transaction[]; total: number; page: number; page_size: number }>(
    `/transactions?${params}`
  )
}

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------

export interface Alert {
  alert_id: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  status: 'open' | 'investigating' | 'mitigated' | 'false_positive'
  title: string
  description: string
  node_id?: string
  created_at: string
  updated_at?: string
}

export const getAlerts = () =>
  apiFetch<{ alerts: Alert[]; count: number }>('/detector/alerts')

export const closeAlert = (alertId: string) =>
  apiFetch<{ success: boolean }>(`/detector/alerts/${alertId}/close`, { method: 'POST' })
