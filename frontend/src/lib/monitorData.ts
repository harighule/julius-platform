/* ═══════════════════════════════════════════════════════════════════════
   JULIUS — Monitor Data Layer
   Static geo data, layer config, fetch helpers for the Monitor tab
   ═══════════════════════════════════════════════════════════════════════ */

export interface MonitorEvent {
  id: string
  category: string
  title: string
  description: string
  lat: number
  lng: number
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info'
  timestamp: string
  source?: string
  country?: string
  url?: string
  brightness?: number
}

export interface MonitorLayer {
  key: string
  label: string
  color: string
  emoji: string
  enabled: boolean
}

export interface LiveChannel {
  id: string
  name: string
  videoId: string
  region: string
}

export interface MonitorKeyword {
  id: string
  keywords: string[]
  color: string
}

export interface NewsArticle {
  title: string
  url: string
  source: string
  image: string
  timestamp: string
  language: string
  source_country: string
}

// ─── Layer Configuration ─────────────────────────────────────────────────────
export const MONITOR_LAYERS: MonitorLayer[] = [
  { key: 'conflict',  label: 'Armed Conflicts',  color: '#ef4444', emoji: '⚔️',  enabled: true },
  { key: 'cyber',     label: 'Cyber Threats',     color: '#8b5cf6', emoji: '💻',  enabled: true },
  { key: 'natural',   label: 'Natural Events',    color: '#eab308', emoji: '🌪️', enabled: true },
  { key: 'fire',      label: 'Satellite Fires',   color: '#f97316', emoji: '🔥',  enabled: true },
  { key: 'base',      label: 'Military Bases',    color: '#3b82f6', emoji: '🏢',  enabled: false },
  { key: 'nuclear',   label: 'Nuclear Sites',     color: '#ec4899', emoji: '☢️',  enabled: false },
  { key: 'hotspot',   label: 'Hotspot Zones',     color: '#f59e0b', emoji: '⚠️', enabled: true },
]

export const CATEGORY_COLORS: Record<string, string> = {
  conflict: '#ef4444',
  cyber: '#8b5cf6',
  natural: '#eab308',
  fire: '#f97316',
  base: '#3b82f6',
  nuclear: '#ec4899',
  hotspot: '#f59e0b',
  malware: '#ef4444',
  ransomware: '#dc2626',
  phishing: '#f59e0b',
  ddos: '#f97316',
  apt: '#e11d48',
  botnet: '#a855f7',
}

export const MONITOR_TAG_COLORS = [
  '#06b6d4', '#8b5cf6', '#f97316', '#ec4899', '#10b981',
  '#f59e0b', '#ef4444', '#3b82f6', '#6366f1', '#14b8a6',
]

// ─── Static Geo Data — Military Bases (curated from worldmonitor) ────────────
export const MILITARY_BASES: { id: string; name: string; lat: number; lng: number; country: string; type: string }[] = [
  { id: 'mb-1', name: 'Camp Humphreys', lat: 36.96, lng: 127.03, country: 'US', type: 'Army' },
  { id: 'mb-2', name: 'Ramstein Air Base', lat: 49.44, lng: 7.60, country: 'US', type: 'Air Force' },
  { id: 'mb-3', name: 'Yokota Air Base', lat: 35.75, lng: 139.35, country: 'US', type: 'Air Force' },
  { id: 'mb-4', name: 'Diego Garcia', lat: -7.32, lng: 72.42, country: 'US', type: 'Naval' },
  { id: 'mb-5', name: 'Al Udeid Air Base', lat: 25.12, lng: 51.31, country: 'US', type: 'Air Force' },
  { id: 'mb-6', name: 'Guantanamo Bay', lat: 19.90, lng: -75.14, country: 'US', type: 'Naval' },
  { id: 'mb-7', name: 'Thule Air Base', lat: 76.53, lng: -68.70, country: 'US', type: 'Space Force' },
  { id: 'mb-8', name: 'RAF Lakenheath', lat: 52.41, lng: 0.56, country: 'US', type: 'Air Force' },
  { id: 'mb-9', name: 'Kadena Air Base', lat: 26.36, lng: 127.77, country: 'US', type: 'Air Force' },
  { id: 'mb-10', name: 'Naval Station Rota', lat: 36.64, lng: -6.35, country: 'US', type: 'Naval' },
  { id: 'mb-11', name: 'Kaliningrad Base', lat: 54.71, lng: 20.51, country: 'RU', type: 'Naval' },
  { id: 'mb-12', name: 'Tartus Naval Base', lat: 34.89, lng: 35.89, country: 'RU', type: 'Naval' },
  { id: 'mb-13', name: 'Khmeimim Air Base', lat: 35.41, lng: 35.95, country: 'RU', type: 'Air Force' },
  { id: 'mb-14', name: 'Djibouti Base', lat: 11.55, lng: 43.15, country: 'CN', type: 'Naval' },
  { id: 'mb-15', name: 'Pine Gap', lat: -23.80, lng: 133.74, country: 'US', type: 'Intelligence' },
]

// ─── Static Geo Data — Nuclear Sites ─────────────────────────────────────────
export const NUCLEAR_SITES: { id: string; name: string; lat: number; lng: number; country: string; type: string; status: string }[] = [
  { id: 'ns-1', name: 'Natanz Enrichment', lat: 33.72, lng: 51.72, country: 'IR', type: 'Enrichment', status: 'Active' },
  { id: 'ns-2', name: 'Yongbyon Complex', lat: 39.80, lng: 125.75, country: 'KP', type: 'Reactor', status: 'Active' },
  { id: 'ns-3', name: 'Dimona', lat: 31.00, lng: 35.15, country: 'IL', type: 'Reactor', status: 'Active' },
  { id: 'ns-4', name: 'Zaporizhzhia NPP', lat: 47.51, lng: 34.59, country: 'UA', type: 'Power', status: 'Occupied' },
  { id: 'ns-5', name: 'La Hague', lat: 49.68, lng: -1.88, country: 'FR', type: 'Reprocessing', status: 'Active' },
  { id: 'ns-6', name: 'Sellafield', lat: 54.42, lng: -3.50, country: 'GB', type: 'Reprocessing', status: 'Decommissioning' },
  { id: 'ns-7', name: 'Bushehr NPP', lat: 28.83, lng: 50.89, country: 'IR', type: 'Power', status: 'Active' },
  { id: 'ns-8', name: 'Kudankulam NPP', lat: 8.17, lng: 77.71, country: 'IN', type: 'Power', status: 'Active' },
  { id: 'ns-9', name: 'Barakah NPP', lat: 23.96, lng: 52.26, country: 'AE', type: 'Power', status: 'Active' },
  { id: 'ns-10', name: 'Chernobyl (Exclusion Zone)', lat: 51.39, lng: 30.10, country: 'UA', type: 'Decommissioned', status: 'Monitored' },
]

// ─── Intel Hotspot Zones ─────────────────────────────────────────────────────
export const HOTSPOT_ZONES: { id: string; name: string; lat: number; lng: number; severity: string; description: string }[] = [
  { id: 'hz-1', name: 'Taiwan Strait', lat: 24.0, lng: 119.5, severity: 'critical', description: 'Ongoing military tensions between PRC and Taiwan' },
  { id: 'hz-2', name: 'Ukraine Front', lat: 48.5, lng: 37.5, severity: 'critical', description: 'Active conflict zone in eastern Ukraine' },
  { id: 'hz-3', name: 'Gaza Strip', lat: 31.4, lng: 34.4, severity: 'critical', description: 'Active conflict zone' },
  { id: 'hz-4', name: 'South China Sea', lat: 12.0, lng: 114.0, severity: 'high', description: 'Territorial disputes and military buildup' },
  { id: 'hz-5', name: 'Korean DMZ', lat: 37.95, lng: 126.98, severity: 'high', description: 'Persistent nuclear threat and military confrontation' },
  { id: 'hz-6', name: 'Strait of Hormuz', lat: 26.56, lng: 56.25, severity: 'high', description: 'Critical oil transit chokepoint' },
  { id: 'hz-7', name: 'Horn of Africa', lat: 5.0, lng: 46.0, severity: 'high', description: 'Piracy, terrorism, and regional instability' },
  { id: 'hz-8', name: 'Sahel Region', lat: 14.5, lng: 1.0, severity: 'high', description: 'Jihadist insurgency and political instability' },
  { id: 'hz-9', name: 'Kashmir', lat: 34.5, lng: 76.5, severity: 'medium', description: 'India-Pakistan disputed territory' },
  { id: 'hz-10', name: 'Red Sea / Yemen', lat: 14.7, lng: 42.5, severity: 'critical', description: 'Houthi attacks on shipping lanes' },
]

// ─── Data Fetch Helpers ──────────────────────────────────────────────────────

function getAuthHeaders(): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  const t = localStorage.getItem('julius_token')
  if (t) h['Authorization'] = `Bearer ${t}`
  return h
}

export async function fetchMonitorFeeds(): Promise<{
  events: MonitorEvent[]
  counts: Record<string, number>
}> {
  try {
    const res = await fetch('/api/globe/monitor-feeds', { headers: getAuthHeaders() })
    if (res.ok) {
      const data = await res.json()
      if (data.status === 'ok') {
        return { events: data.events || [], counts: data.counts || {} }
      }
    }
  } catch {
    void 0
  }
  // Fallback: return empty
  return { events: [], counts: {} }
}

export async function fetchMonitorNews(country: string, topic: string): Promise<NewsArticle[]> {
  try {
    const params = new URLSearchParams()
    if (country) params.set('country', country)
    if (topic) params.set('topic', topic)
    const res = await fetch(`/api/globe/news?${params}`, { headers: getAuthHeaders() })
    if (res.ok) {
      const data = await res.json()
      return data.articles || []
    }
  } catch {
    void 0
  }
  return []
}

export async function fetchLiveChannels(): Promise<LiveChannel[]> {
  try {
    const res = await fetch('/api/globe/live-channels', { headers: getAuthHeaders() })
    if (res.ok) {
      const data = await res.json()
      return data.channels || []
    }
  } catch {
    void 0
  }
  return []
}

export async function fetchGlobalHeadlines(): Promise<NewsArticle[]> {
  try {
    const res = await fetch('/api/globe/news?topic=breaking+news+world&limit=20', { headers: getAuthHeaders() })
    if (res.ok) {
      const data = await res.json()
      return data.articles || []
    }
  } catch {
    void 0
  }
  return []
}

// ─── Static data helpers ─────────────────────────────────────────────────────

export function getStaticLayerEvents(layerKey: string): MonitorEvent[] {
  if (layerKey === 'base') {
    return MILITARY_BASES.map(b => ({
      id: b.id,
      category: 'base',
      title: `${b.type} — ${b.name}`,
      description: `${b.country} ${b.type} installation`,
      lat: b.lat,
      lng: b.lng,
      severity: 'info' as const,
      timestamp: '',
      source: 'Static Intel',
      country: b.country,
    }))
  }
  if (layerKey === 'nuclear') {
    return NUCLEAR_SITES.map(n => ({
      id: n.id,
      category: 'nuclear',
      title: `☢️ ${n.name}`,
      description: `${n.type} — ${n.status}`,
      lat: n.lat,
      lng: n.lng,
      severity: n.status === 'Occupied' ? 'critical' as const : 'high' as const,
      timestamp: '',
      source: 'IAEA',
      country: n.country,
    }))
  }
  if (layerKey === 'hotspot') {
    return HOTSPOT_ZONES.map(h => ({
      id: h.id,
      category: 'hotspot',
      title: `⚠️ ${h.name}`,
      description: h.description,
      lat: h.lat,
      lng: h.lng,
      severity: h.severity as 'critical' | 'high' | 'medium' | 'low',
      timestamp: '',
      source: 'JULIUS Intel',
      country: '',
    }))
  }
  return []
}
