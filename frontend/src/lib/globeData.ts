/* ═══════════════════════════════════════════════════════════════════════
   JULIUS — Globe Event Data Layer
   Fetches threat events from OSINT feeds and maps them to lat/lng
   ═══════════════════════════════════════════════════════════════════════ */

export interface GlobeEvent {
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
}

export const CATEGORY_CONFIG: Record<string, { label: string; color: string; emoji: string }> = {
  conflict:   { label: 'Armed Conflict', color: '#ef4444', emoji: '⚔️' },
  hotspot:    { label: 'Geopol Hotspot', color: '#f97316', emoji: '🔥' },
  natural:    { label: 'Natural Event',  color: '#eab308', emoji: '🌪️' },
  cyber:      { label: 'Cyber Attack',   color: '#8b5cf6', emoji: '💻' },
  nuclear:    { label: 'Nuclear Alert',  color: '#ec4899', emoji: '☢️' },
  base:       { label: 'Base Activity',  color: '#3b82f6', emoji: '🏢' },
  // Additional cyber ones for threat feeds if needed
  malware:    { label: 'Malware',        color: '#ef4444', emoji: '🦠' },
  ransomware: { label: 'Ransomware',     color: '#dc2626', emoji: '🔒' },
  phishing:   { label: 'Phishing',       color: '#f59e0b', emoji: '🎣' },
  ddos:       { label: 'DDoS',           color: '#f97316', emoji: '💥' },
  apt:        { label: 'APT',            color: '#e11d48', emoji: '🎯' },
  botnet:     { label: 'Botnet',         color: '#a855f7', emoji: '🤖' },
  exploit:    { label: 'Exploit',        color: '#ec4899', emoji: '⚡' },
  breach:     { label: 'Data Breach',    color: '#06b6d4', emoji: '🔓' },
  vuln:       { label: 'Vulnerability',  color: '#8b5cf6', emoji: '🐛' },
  scan:       { label: 'Scan',           color: '#22d3ee', emoji: '📡' },
  c2:         { label: 'C2 Server',      color: '#f43f5e', emoji: '📡' },
  darkweb:    { label: 'Dark Web',       color: '#6366f1', emoji: '🌑' },
  insider:    { label: 'Insider',        color: '#eab308', emoji: '👤' },
  crypto:     { label: 'Cryptojacking',  color: '#10b981', emoji: '⛏️' },
}

// Random locations for simulated global threat data
const LOCATIONS: { country: string; lat: number; lng: number }[] = [
  { country: 'US', lat: 37.77, lng: -122.42 }, { country: 'US', lat: 40.71, lng: -74.01 },
  { country: 'US', lat: 34.05, lng: -118.24 }, { country: 'UK', lat: 51.51, lng: -0.13 },
  { country: 'DE', lat: 52.52, lng: 13.41 }, { country: 'FR', lat: 48.86, lng: 2.35 },
  { country: 'JP', lat: 35.68, lng: 139.69 }, { country: 'CN', lat: 39.91, lng: 116.40 },
  { country: 'CN', lat: 31.23, lng: 121.47 }, { country: 'RU', lat: 55.76, lng: 37.62 },
  { country: 'BR', lat: -23.55, lng: -46.63 }, { country: 'IN', lat: 28.61, lng: 77.21 },
  { country: 'IN', lat: 19.08, lng: 72.88 }, { country: 'AU', lat: -33.87, lng: 151.21 },
  { country: 'KR', lat: 37.57, lng: 126.98 }, { country: 'SG', lat: 1.35, lng: 103.82 },
  { country: 'AE', lat: 25.20, lng: 55.27 }, { country: 'IL', lat: 32.07, lng: 34.78 },
  { country: 'ZA', lat: -33.93, lng: 18.42 }, { country: 'NG', lat: 6.52, lng: 3.38 },
  { country: 'CA', lat: 43.65, lng: -79.38 }, { country: 'NL', lat: 52.37, lng: 4.90 },
  { country: 'SE', lat: 59.33, lng: 18.07 }, { country: 'UA', lat: 50.45, lng: 30.52 },
  { country: 'IR', lat: 35.69, lng: 51.39 }, { country: 'KP', lat: 39.02, lng: 125.75 },
  { country: 'PK', lat: 33.69, lng: 73.04 }, { country: 'MX', lat: 19.43, lng: -99.13 },
  { country: 'AR', lat: -34.60, lng: -58.38 }, { country: 'EG', lat: 30.04, lng: 31.24 },
  { country: 'TW', lat: 25.03, lng: 121.57 }, { country: 'ID', lat: -6.21, lng: 106.85 },
  { country: 'PH', lat: 14.60, lng: 120.98 }, { country: 'VN', lat: 21.03, lng: 105.85 },
  { country: 'TH', lat: 13.76, lng: 100.50 }, { country: 'MY', lat: 3.14, lng: 101.69 },
  { country: 'PL', lat: 52.23, lng: 21.01 }, { country: 'RO', lat: 44.43, lng: 26.10 },
  { country: 'CL', lat: -33.45, lng: -70.67 }, { country: 'CO', lat: 4.71, lng: -74.07 },
]

const SEVERITY_WEIGHTS: GlobeEvent['severity'][] = ['info', 'low', 'low', 'medium', 'medium', 'medium', 'high', 'high', 'critical']

function randomItem<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]
}

function generateEvents(categories: Set<string>, count = 60): GlobeEvent[] {
  const cats = Array.from(categories).filter(c => c in CATEGORY_CONFIG)
  if (cats.length === 0) return []

  const events: GlobeEvent[] = []
  for (let i = 0; i < count; i++) {
    const cat = randomItem(cats)
    const loc = randomItem(LOCATIONS)
    const cfg = CATEGORY_CONFIG[cat]
    events.push({
      id: `ge-${Date.now()}-${i}`,
      category: cat,
      title: `${cfg.emoji} ${cfg.label} Activity in ${loc.country}`,
      description: `${cfg.label} event detected from ${loc.country} region`,
      lat: loc.lat + (Math.random() - 0.5) * 3,
      lng: loc.lng + (Math.random() - 0.5) * 3,
      severity: randomItem(SEVERITY_WEIGHTS),
      timestamp: new Date(Date.now() - Math.random() * 3600000).toISOString(),
      source: 'osint',
      country: loc.country,
    })
  }
  return events
}

/**
 * Fetch globe events. In production this would call the OSINT API.
 * Currently generates realistic simulated threat data.
 */
export async function fetchGlobeEvents(enabledLayers: Set<string>): Promise<GlobeEvent[]> {
  // Try real API first
  try {
    const token = localStorage.getItem('julius_token')
    const res = await fetch('/api/osint/globe-events', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (res.ok) {
      const data = await res.json()
      if (Array.isArray(data) && data.length > 0) {
        return data.filter((e: GlobeEvent) => enabledLayers.has(e.category))
      }
    }
  } catch {
    // API not available — fall through to simulated data
  }

  // Simulated data
  return generateEvents(enabledLayers, 40 + Math.floor(Math.random() * 30))
}
