import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { Globe3D } from '../components/Globe3D'
import { GlobeNewsPanel } from '../components/GlobeNewsPanel'
import { MonitorLiveTV } from '../components/MonitorLiveTV'
import { MonitorKeywords } from '../components/MonitorKeywords'
import { MonitorNewsTicker } from '../components/MonitorNewsTicker'
import { MonitorMap2D } from '../components/MonitorMap2D'
import {
  MONITOR_LAYERS,
  fetchMonitorFeeds,
  fetchMonitorNews,
  getStaticLayerEvents,
  type MonitorEvent,
  type MonitorLayer,
  type NewsArticle,
} from '../lib/monitorData'
import { type GlobeEvent } from '../lib/globeData'

const API = "";
const VIEW_PRESETS = [
  { key: 'global', label: 'GLOBAL' },
  { key: 'americas', label: 'AMERICAS' },
  { key: 'europe', label: 'EUROPE' },
  { key: 'mena', label: 'MENA' },
  { key: 'asia', label: 'ASIA' },
  { key: 'africa', label: 'AFRICA' },
] as const

export function MonitorPanel() {
  const [layers, setLayers] = useState<MonitorLayer[]>(MONITOR_LAYERS)
  const [events, setEvents] = useState<MonitorEvent[]>([])
  const [selectedEvent, setSelectedEvent] = useState<GlobeEvent | null>(null)
  const [newsOpen, setNewsOpen] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [tvOpen, setTvOpen] = useState(true)
  const [monitorOpen, setMonitorOpen] = useState(false)
  const [crtFx, setCrtFx] = useState(false)
  const [time, setTime] = useState(new Date())
  const [newsArticles, setNewsArticles] = useState<NewsArticle[]>([])
  const [mapMode, setMapMode] = useState<'globe' | 'flat'>('globe')
  const [activeView, setActiveView] = useState('global')
  const [loading, setLoading] = useState(true)

  // REAL APEX Monitor Intelligence - NO FAKE API
  const [apexMonitor, setApexMonitor] = useState<any>(null)
  const [apexMonitorRunning, setApexMonitorRunning] = useState(false)

  const runRealApexMonitor = async () => {
    setApexMonitorRunning(true)
    try {
      // Get REAL causal strength for global events -> threat
      const causalRes = await fetch(`${API}/api/causal/global_events/threat`)
      const causalData = await causalRes.json()

      // Get REAL system status
      const statusRes = await fetch(`${API}/api/status`)
      const statusData = await statusRes.json()

      // Get REAL threat assessment
      const threatRes = await fetch(`${API}/api/threat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ threat_type: 'global_monitor' })
      })
      const threatData = await threatRes.json()

      // Calculate statistics from actual events
      const criticalCount = events.filter(e => e.severity === 'critical').length
      const highCount = events.filter(e => e.severity === 'high').length
      const uniqueSources = new Set(events.map(e => e.source || 'unknown')).size
      const uniqueCountries = new Set(events.filter(e => e.country).map(e => e.country)).size

      setApexMonitor({
        causal_analysis: {
          global_events_to_threat_strength: causalData.strength,
          interpretation: causalData.interpretation
        },
        system_status: statusData,
        threat_assessment: threatData,
        monitor_statistics: {
          total_events: events.length,
          critical_events: criticalCount,
          high_risk_events: highCount,
          unique_sources: uniqueSources,
          countries_affected: uniqueCountries,
          active_layers: layers.filter(l => l.enabled).length,
          active_view: activeView
        },
        recommendation: causalData.strength > 0.7 
          ? "HIGH THREAT: Global events show strong correlation with security risks - Increase alert level"
          : causalData.strength > 0.4
          ? "MEDIUM THREAT: Monitor global events closely"
          : "LOW THREAT: Continue standard monitoring",
        timestamp: new Date().toISOString()
      })
    } catch (error) {
      console.error('APEX monitor analysis failed:', error)
      setApexMonitor({ error: 'Backend not running. Start: python backend/julius_api_real.py' })
    } finally {
      setApexMonitorRunning(false)
    }
  }

  const geoChangeRef = useRef<(c: { lat: number; lng: number } | null) => void>(() => {})
  const handleGeoChange = useCallback((c: { lat: number; lng: number } | null) => {
    geoChangeRef.current(c)
  }, [])

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  const loadData = useCallback(async () => {
    setLoading(true)
    const { events: fetched } = await fetchMonitorFeeds()
    const enabledKeys = new Set(layers.filter(l => l.enabled).map(l => l.key))
    const staticEvents: MonitorEvent[] = []
    for (const key of ['base', 'nuclear', 'hotspot']) {
      if (enabledKeys.has(key)) {
        staticEvents.push(...getStaticLayerEvents(key))
      }
    }
    setEvents([...fetched, ...staticEvents])
    setLoading(false)
  }, [layers])

  useEffect(() => {
    const boot = window.setTimeout(() => { void loadData() }, 0)
    const interval = setInterval(() => void loadData(), 3 * 60 * 1000)
    return () => { clearTimeout(boot); clearInterval(interval) }
  }, [loadData])

  useEffect(() => {
    const fetchNews = async () => {
      const articles = await fetchMonitorNews('', 'world breaking news security cyber')
      setNewsArticles(articles)
    }
    const boot = window.setTimeout(() => { void fetchNews() }, 0)
    const interval = setInterval(() => void fetchNews(), 5 * 60 * 1000)
    return () => { clearTimeout(boot); clearInterval(interval) }
  }, [])

  const enabledLayerKeys = useMemo(
    () => new Set(layers.filter(l => l.enabled).map(l => l.key)),
    [layers]
  )

  const visibleEvents: GlobeEvent[] = useMemo(() =>
    events
      .filter(e => enabledLayerKeys.has(e.category))
      .map(e => ({
        id: e.id,
        category: e.category,
        title: e.title,
        description: e.description,
        lat: e.lat,
        lng: e.lng,
        severity: e.severity === 'info' ? 'low' as const : e.severity,
        timestamp: e.timestamp,
        source: e.source,
        country: e.country,
      })),
    [events, enabledLayerKeys]
  )

  const toggleLayer = (key: string) => {
    setLayers(prev => prev.map(l => l.key === key ? { ...l, enabled: !l.enabled } : l))
  }

  const handleEventClick = (ev: GlobeEvent) => {
    setSelectedEvent(ev)
    setNewsOpen(true)
  }

  const handleCloseNews = () => {
    setNewsOpen(false)
    setTimeout(() => setSelectedEvent(null), 350)
  }

  const eventCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const e of events) {
      counts[e.category] = (counts[e.category] || 0) + 1
    }
    return counts
  }, [events])

  const zuluTime = time.toISOString().split('T')[1].substring(0, 8)
  const totalEvents = events.length
  const criticalCount = events.filter(e => e.severity === 'critical').length

  return (
    <div className={`relative w-full h-full bg-black overflow-hidden font-mono ${crtFx ? 'monitor-crt-fx' : ''}`}>

      {/* Full-screen Map */}
      <div className="absolute inset-0 z-0">
        {mapMode === 'globe' ? (
          <Globe3D
            className="w-full h-full"
            onGeoChange={handleGeoChange}
            events={visibleEvents}
            onEventClick={handleEventClick}
          />
        ) : (
          <MonitorMap2D
            className="w-full h-full"
            events={visibleEvents}
            onEventClick={handleEventClick}
            activeView={activeView}
          />
        )}
      </div>

      {/* Top HUD Bar */}
      <div className="absolute top-0 left-0 right-0 z-20 flex items-center justify-between px-4 py-2 bg-gradient-to-b from-black/85 via-black/50 to-transparent pointer-events-none">
        <div className="flex items-center gap-3 pointer-events-auto">
          <button className="w-7 h-7 flex flex-col justify-center gap-1 group" onClick={() => setSidebarOpen(o => !o)}>
            <span className="block h-[2px] w-5 bg-julius-accent shadow-[0_0_8px_var(--color-julius-accent)] group-hover:bg-white transition-colors" />
            <span className="block h-[2px] w-5 bg-julius-accent shadow-[0_0_8px_var(--color-julius-accent)] group-hover:bg-white transition-colors" />
            <span className="block h-[2px] w-5 bg-julius-accent shadow-[0_0_8px_var(--color-julius-accent)] group-hover:bg-white transition-colors" />
          </button>
          <span className="text-white text-[12px] font-black tracking-[0.3em] font-display glow-cyan">JULIUS_MONITOR</span>
          <span className="text-julius-accent text-[9px] tracking-[0.3em] border border-julius-accent/30 bg-julius-accent/5 px-2 py-0.5 font-bold">GLOBAL_INTEL</span>
          {loading && <span className="text-[8px] text-julius-amber/60 tracking-wider animate-pulse">SYNCING...</span>}
        </div>
        <div className="flex items-center gap-3 text-[9px] font-black tracking-[0.2em] font-mono pointer-events-none">
          <span className="text-julius-red bg-julius-red/10 border border-julius-red/25 px-2 py-0.5 rounded shadow-[0_0_10px_var(--color-julius-red-dim)]">CONFLICTS: {eventCounts.conflict || 0}</span>
          <span className="text-julius-amber bg-julius-amber/10 border border-julius-amber/25 px-2 py-0.5 rounded">FIRES: {eventCounts.fire || 0}</span>
          <span className="text-julius-accent bg-julius-accent/10 border border-julius-accent/25 px-2 py-0.5 rounded glow-cyan">CYBER: {eventCounts.cyber || 0}</span>
          <span className="text-yellow-400 bg-yellow-400/10 border border-yellow-400/25 px-2 py-0.5 rounded">HAZARDS: {eventCounts.natural || 0}</span>
        </div>
        <div className="flex items-center gap-4 text-[10px] tracking-widest text-julius-accent pointer-events-auto">
          {criticalCount > 0 && (
            <span className="px-2 py-0.5 rounded font-mono font-bold text-julius-red bg-julius-red/20 border border-julius-red/40 glow-red animate-pulse">
              ⚠️ CRITICAL: {criticalCount}
            </span>
          )}
          <span className="text-white font-black tracking-widest">ZULU {zuluTime}</span>
          <button onClick={() => setMapMode(m => m === 'globe' ? 'flat' : 'globe')}
            className="px-2 py-0.5 border border-julius-border text-[8px] font-bold tracking-wider hover:border-julius-accent transition-colors uppercase">
            {mapMode === 'globe' ? '🌍 Globe' : '🗺️ Flat'}
          </button>
          <button onClick={() => setMonitorOpen(o => !o)}
            className={`px-2 py-0.5 border text-[8px] font-bold tracking-wider transition-colors uppercase ${monitorOpen ? 'border-julius-accent text-julius-accent bg-julius-accent/10' : 'border-julius-border text-julius-muted hover:border-julius-accent'}`}>
            📡 MONITOR
          </button>
        </div>
      </div>

      {/* REAL APEX Global Monitor Intelligence - NO FAKE API */}
      <div className="absolute top-16 right-4 z-30 w-80">
        <div className="bg-black/90 border border-cyan-900/60 rounded-xl p-3 backdrop-blur-sm">
          <div className="flex items-center justify-between mb-2">
            <div>
              <div className="text-[10px] font-bold tracking-widest text-cyan-400">🔗 APEX GLOBAL INTEL</div>
              <div className="text-[9px] text-julius-muted">REAL causal threat analysis</div>
            </div>
            <span className="text-[9px] px-2 py-0.5 rounded bg-cyan-900/30 text-cyan-400 border border-cyan-800/50">REAL DATA</span>
          </div>
          <button onClick={runRealApexMonitor} disabled={apexMonitorRunning || loading}
            className="w-full py-1.5 text-[10px] font-mono rounded mb-2 disabled:opacity-40 transition-all"
            style={{ background: '#001414', border: '1px solid #06b6d444', color: '#06b6d4' }}>
            {apexMonitorRunning ? '⚙️ ANALYSING GLOBAL EVENTS...' : `🚀 ANALYSE ${totalEvents} EVENTS`}
          </button>
          
          {apexMonitor && !apexMonitor.error && (
            <div className="space-y-2">
              {/* Causal Analysis */}
              <div className="bg-black/60 rounded p-2">
                <div className="text-[8px] text-cyan-400 uppercase tracking-wider mb-1">Causal Analysis</div>
                <div className="text-[9px]"><span className="text-julius-muted">Events → Threat:</span> <span className="text-green-400 font-mono">{(apexMonitor.causal_analysis?.global_events_to_threat_strength * 100).toFixed(0)}%</span></div>
                <div className="text-[8px] text-julius-muted">{apexMonitor.causal_analysis?.interpretation}</div>
              </div>

              {/* Statistics */}
              <div className="bg-black/60 rounded p-2">
                <div className="text-[8px] text-yellow-400 uppercase tracking-wider mb-1">Live Statistics</div>
                <div className="grid grid-cols-2 gap-1 text-[9px]">
                  <div><span className="text-julius-muted">Total Events:</span> <span className="text-white">{apexMonitor.monitor_statistics?.total_events || 0}</span></div>
                  <div><span className="text-julius-muted">Critical:</span> <span className="text-red-400">{apexMonitor.monitor_statistics?.critical_events || 0}</span></div>
                  <div><span className="text-julius-muted">Sources:</span> <span className="text-cyan-400">{apexMonitor.monitor_statistics?.unique_sources || 0}</span></div>
                  <div><span className="text-julius-muted">Countries:</span> <span className="text-green-400">{apexMonitor.monitor_statistics?.countries_affected || 0}</span></div>
                </div>
              </div>

              {/* Recommendation */}
              <div className="bg-black/60 rounded p-2">
                <div className="text-[8px] text-red-400 uppercase tracking-wider mb-1">Recommendation</div>
                <div className="text-[9px] text-yellow-300 leading-tight">{apexMonitor.recommendation}</div>
              </div>

              <div className="text-[7px] text-julius-muted text-right">Real-time from APEX backend | {new Date(apexMonitor.timestamp).toLocaleTimeString()}</div>
            </div>
          )}
          
          {apexMonitor?.error && (
            <div className="bg-red-900/20 text-red-400 p-2 rounded text-[9px]">{apexMonitor.error}</div>
          )}
        </div>
      </div>

      {/* Left Sidebar */}
      <div className={`absolute top-12 left-0 z-20 h-[calc(100%-7rem)] transition-all duration-300 ease-in-out ${sidebarOpen ? 'w-56' : 'w-0 overflow-hidden'}`}>
        <div className="h-full bg-julius-bg/85 backdrop-blur-md border-r border-julius-border flex flex-col py-3 w-56">
          <div className="px-4 mb-3">
            <p className="text-[9px] text-julius-accent/70 tracking-[0.4em] font-black uppercase font-display px-1 border-l-2 border-julius-accent">Intelligence Layers</p>
          </div>
          <div className="flex-1 overflow-y-auto space-y-0.5 px-2">
            {layers.map(layer => {
              const count = eventCounts[layer.key] || 0
              return (
                <button key={layer.key} onClick={() => toggleLayer(layer.key)}
                  className={`w-full flex items-center gap-3 px-3 py-2 rounded-none text-left transition-all duration-200 group ${layer.enabled ? 'bg-julius-accent/10 border-l-2' : 'bg-transparent border border-transparent hover:bg-julius-surface'}`}
                  style={layer.enabled ? { borderLeftColor: layer.color } : {}}>
                  <span className="text-sm leading-none">{layer.emoji}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className={`text-[10px] font-bold tracking-wide ${layer.enabled ? 'text-white' : 'text-julius-muted'}`}>{layer.label}</span>
                      {count > 0 && (
                        <span className="text-[8px] font-bold px-1.5 py-0.5 rounded-full"
                          style={{ background: layer.color + '22', color: layer.color, border: `1px solid ${layer.color}44` }}>
                          {count}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className={`w-6 h-3 rounded-full transition-colors flex items-center shrink-0 ${layer.enabled ? '' : 'bg-blue-950/60 border border-blue-800/40'}`}
                    style={layer.enabled ? { background: layer.color + 'aa', border: `1px solid ${layer.color}` } : {}}>
                    <div className={`w-2.5 h-2.5 rounded-full bg-white transition-transform mx-0.5 ${layer.enabled ? 'translate-x-2.5' : 'translate-x-0'}`} />
                  </div>
                </button>
              )
            })}
          </div>
          <div className="px-3 pt-3 border-t border-julius-border">
            <p className="text-[8px] text-julius-muted tracking-[0.3em] font-bold uppercase mb-2 px-1">VIEW PRESETS</p>
            <div className="grid grid-cols-3 gap-1">
              {VIEW_PRESETS.map(v => (
                <button key={v.key} onClick={() => setActiveView(v.key)}
                  className={`text-[7px] font-bold tracking-wider py-1 border transition-colors ${activeView === v.key ? 'border-julius-accent text-julius-accent bg-julius-accent/10' : 'border-julius-border text-julius-muted hover:text-white'}`}>
                  {v.label}
                </button>
              ))}
            </div>
          </div>
          <div className="px-4 pt-3 border-t border-julius-border space-y-1.5 text-[9px] text-julius-muted font-black tracking-[0.2em] uppercase mt-2">
            <div className="flex justify-between"><span>TOTAL_EVENTS</span><span className="text-white">{totalEvents}</span></div>
            <div className="flex justify-between"><span>SOURCES</span><span className="text-white">{new Set(events.map(e => e.source || 'unknown')).size}</span></div>
            <div className="flex justify-between"><span>COUNTRIES</span><span className="text-white">{new Set(events.filter(e => e.country).map(e => e.country)).size}</span></div>
            <div className="flex items-center justify-between mt-2">
              <span>CRT_FX</span>
              <div className={`w-8 h-4 rounded-full p-0.5 cursor-pointer flex items-center transition-colors ${crtFx ? 'bg-cyan-600' : 'bg-blue-900/60 border border-blue-700'}`}
                onClick={() => setCrtFx(v => !v)}>
                <div className={`w-3 h-3 rounded-full bg-white transition-transform ${crtFx ? 'translate-x-4' : 'translate-x-0'}`} />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* News Panel */}
      <div className={`absolute top-0 right-0 z-30 h-full transition-all duration-300 ease-in-out ${newsOpen ? 'w-[380px] opacity-100' : 'w-0 opacity-0 overflow-hidden'}`}
        style={{ transitionProperty: 'width, opacity' }}>
        <GlobeNewsPanel event={selectedEvent} onClose={handleCloseNews} />
      </div>

      {/* Monitor Keywords Panel */}
      {monitorOpen && !newsOpen && (
        <div className="absolute top-12 right-3 z-20 w-80 max-h-[60vh] bg-julius-bg/90 backdrop-blur-md border border-julius-border flex flex-col overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 border-b border-julius-border bg-julius-surface/50">
            <span className="text-[9px] text-julius-accent font-black tracking-[0.3em] font-display">KEYWORD_MONITOR</span>
            <button onClick={() => setMonitorOpen(false)} className="text-julius-muted hover:text-white text-xs">✕</button>
          </div>
          <MonitorKeywords news={newsArticles} />
        </div>
      )}

      {/* Live TV Panel */}
      {!newsOpen && (
        <div className={`absolute z-20 transition-all duration-300 ${tvOpen ? 'bottom-[72px] right-3 w-[380px]' : 'bottom-[72px] right-3 w-auto'}`}>
          {tvOpen ? (
            <MonitorLiveTV />
          ) : (
            <button onClick={() => setTvOpen(true)}
              className="flex items-center gap-2 px-3 py-2 bg-julius-bg/80 backdrop-blur border border-julius-border hover:border-julius-accent transition-colors">
              <div className="w-1.5 h-1.5 bg-julius-red rounded-full animate-pulse shadow-[0_0_5px_var(--color-julius-red)]" />
              <span className="text-[9px] text-julius-red font-black tracking-[0.3em] uppercase">LIVE_TV</span>
            </button>
          )}
        </div>
      )}

      {/* News Ticker */}
      <div className="absolute bottom-8 left-0 right-0 z-20 pointer-events-auto">
        <MonitorNewsTicker />
      </div>

      {/* Bottom Bar */}
      <div className="absolute bottom-0 left-0 right-0 z-20 flex items-center justify-between px-6 py-2 bg-julius-bg/95 border-t border-julius-border pointer-events-none">
        <GeoDisplay onGeoChangeRef={geoChangeRef} />
        <div className="flex items-center gap-4">
          {layers.filter(l => l.enabled).map(layer => (
            <div key={layer.key} className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: layer.color, boxShadow: `0 0 5px ${layer.color}` }} />
              <span className="text-[8px] font-black tracking-[0.15em] uppercase" style={{ color: layer.color }}>{layer.label}</span>
            </div>
          ))}
        </div>
        <div className="text-[9px] text-julius-muted font-black tracking-[0.2em] text-right uppercase">
          <div>WGS-84 // OSINT_GRID</div>
          <div>JULIUS · GDELT · USGS · FIRMS</div>
        </div>
      </div>

      {/* Hint text */}
      {!newsOpen && visibleEvents.length > 0 && (
        <div className="absolute bottom-16 left-1/2 -translate-x-1/2 z-10 pointer-events-none">
          <div className="text-[9px] text-blue-500/30 tracking-[0.3em] font-bold animate-pulse">CLICK A MARKER TO OPEN LIVE INTELLIGENCE FEED</div>
        </div>
      )}

      {/* CRT Effect */}
      <style dangerouslySetInnerHTML={{ __html: `
        .monitor-crt-fx::before {
          content: " ";
          display: block;
          position: absolute;
          top: 0; left: 0; bottom: 0; right: 0;
          background: linear-gradient(rgba(18,16,16,0) 50%, rgba(0,0,0,0.22) 50%),
                      linear-gradient(90deg, rgba(255,0,0,0.05), rgba(0,255,0,0.02), rgba(0,0,255,0.05));
          z-index: 50;
          background-size: 100% 2px, 3px 100%;
          pointer-events: none;
        }
      `}} />
    </div>
  )
}

// Geo Coordinate HUD
function GeoDisplay({ onGeoChangeRef }: { onGeoChangeRef: React.MutableRefObject<(c: { lat: number; lng: number } | null) => void> }) {
  const [geo, setGeo] = useState<{ lat: number; lng: number } | null>(null)
  useEffect(() => { onGeoChangeRef.current = setGeo }, [onGeoChangeRef])
  const fmt = (v: number, isLat: boolean) => {
    const dir = isLat ? (v >= 0 ? 'N' : 'S') : (v >= 0 ? 'E' : 'W')
    const abs = Math.abs(v)
    const deg = Math.floor(abs)
    const min = Math.floor((abs - deg) * 60)
    const sec = (((abs - deg) * 60) - min) * 60
    return `${deg}°${min}'${sec.toFixed(1)}"${dir}`
  }
  return (
    <div className="text-[10px] font-black font-mono tracking-widest">
      {geo && !isNaN(geo.lat) ? (
        <div className="text-julius-accent">
          <span>{fmt(geo.lat, true)}</span>
          <span className="mx-2 text-julius-border">/</span>
          <span>{fmt(geo.lng, false)}</span>
          <span className="ml-3 text-julius-muted text-[9px] tracking-normal">[{geo.lat.toFixed(4)}, {geo.lng.toFixed(4)}]</span>
        </div>
      ) : (
        <div className="text-julius-muted italic text-[9px] tracking-[0.2em] uppercase">Awaiting_Geo_Lock...</div>
      )}
    </div>
  )
}