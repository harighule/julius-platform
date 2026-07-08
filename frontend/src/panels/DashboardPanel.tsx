import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { live, behavioral } from '../lib/api'
import { Globe3D } from '../components/Globe3D'
import { GlobeNewsPanel } from '../components/GlobeNewsPanel'
import { GlobalNewsTicker } from '../components/GlobalNewsTicker'
import { LiveTVPanel } from '../components/LiveTVPanel'
import { useState, useEffect, useRef, useCallback } from 'react'
import { fetchGlobeEvents, type GlobeEvent, CATEGORY_CONFIG } from '../lib/globeData'

// ─── Layer definitions ────────────────────────────────────────────────────────
const ALL_LAYERS = ['conflict', 'hotspot', 'base', 'nuclear', 'natural', 'cyber'] as const
type LayerKey = typeof ALL_LAYERS[number]

const DEFAULT_ENABLED: Set<LayerKey> = new Set(['conflict', 'hotspot', 'natural', 'cyber', 'nuclear', 'base'])

type LiveDashboardPayload = {
  stats?: Record<string, number | undefined>
  recent_vulns?: unknown[]
}

export function DashboardPanel() {
  const { data } = useQuery({ queryKey: ['live-dashboard'], queryFn: live.dashboard, refetchInterval: 5000 })
  const { data: behavData } = useQuery({ queryKey: ['dash-behav'], queryFn: behavioral.stats, refetchInterval: 15000 })

  const dash = data as LiveDashboardPayload | undefined
  const behavStats = behavData as { active_patterns?: number } | undefined

  const [time, setTime] = useState(new Date())
  const [enabledLayers, setEnabledLayers] = useState<Set<LayerKey>>(DEFAULT_ENABLED)
  const [globeEvents, setGlobeEvents] = useState<GlobeEvent[]>([])
  const [selectedEvent, setSelectedEvent] = useState<GlobeEvent | null>(null)
  const [newsOpen, setNewsOpen] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [tvOpen, setTvOpen] = useState(true)
  const [crtFx, setCrtFx] = useState(false)

  const geoChangeRef = useRef<(c: { lat: number; lng: number } | null) => void>(() => {})
  const handleGeoChange = useCallback((c: { lat: number; lng: number } | null) => {
    geoChangeRef.current(c)
  }, [])

  // Clock
  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  // Fetch globe events on layer change
  useEffect(() => {
    fetchGlobeEvents(enabledLayers as Set<string>).then(setGlobeEvents)
  }, [enabledLayers])

  // Refresh every 3 minutes
  useEffect(() => {
    const interval = setInterval(() => {
      fetchGlobeEvents(enabledLayers as Set<string>).then(setGlobeEvents)
    }, 3 * 60 * 1000)
    return () => clearInterval(interval)
  }, [enabledLayers])

  const stats = dash?.stats ?? {}
  const realVulns = Array.isArray(dash?.recent_vulns) ? dash.recent_vulns : []
  const zuluTime = time.toISOString().split('T')[1].substring(0, 8)

  const toggleLayer = (layer: LayerKey) => {
    setEnabledLayers(prev => {
      const next = new Set(prev)
      if (next.has(layer)) next.delete(layer)
      else next.add(layer)
      return next
    })
  }

  const handleEventClick = (ev: GlobeEvent) => {
    setSelectedEvent(ev)
    setNewsOpen(true)
  }

  const handleCloseNews = () => {
    setNewsOpen(false)
    // Small delay so panel slides out before clearing data
    setTimeout(() => setSelectedEvent(null), 350)
  }

  const eventsByCategory = ALL_LAYERS.reduce((acc, k) => {
    acc[k] = globeEvents.filter(e => e.category === k).length
    return acc
  }, {} as Record<string, number>)

  return (
    <div className={`relative w-full h-full bg-black overflow-hidden font-mono ${crtFx ? 'crt-scanlines' : ''}`}>

      {/* ─── Full-screen Globe ─────────────────────────────────── */}
      <div className="absolute inset-0 z-0">
        <Globe3D
          className="w-full h-full"
          onGeoChange={handleGeoChange}
          events={globeEvents}
          onEventClick={handleEventClick}
        />
      </div>

      {/* ─── Top Bar ───────────────────────────────────────────── */}
      <div className="absolute top-0 left-0 right-0 z-20 flex items-center justify-between px-4 py-2 bg-gradient-to-b from-black/80 via-black/40 to-transparent pointer-events-none">
        <div className="flex items-center gap-3">
          <button
            className="pointer-events-auto w-7 h-7 flex flex-col justify-center gap-1 group"
            onClick={() => setSidebarOpen(o => !o)}
          >
            <span className="block h-[2px] w-5 bg-julius-accent shadow-[0_0_8px_var(--color-julius-accent)] group-hover:bg-white transition-colors" />
            <span className="block h-[2px] w-5 bg-julius-accent shadow-[0_0_8px_var(--color-julius-accent)] group-hover:bg-white transition-colors" />
            <span className="block h-[2px] w-5 bg-julius-accent shadow-[0_0_8px_var(--color-julius-accent)] group-hover:bg-white transition-colors" />
          </button>
          <span className="text-white text-[12px] font-black tracking-[0.3em] font-display glow-cyan">PANOPTICON_HUD</span>
          <span className="text-julius-accent text-[9px] tracking-[0.3em] border border-julius-accent/30 bg-julius-accent/5 px-2 py-0.5 font-bold">OSINT_FEED</span>
          <Link
            to="/guardian"
            className="pointer-events-auto flex items-center gap-1.5 px-3 py-1 rounded border border-julius-accent/50 bg-julius-accent/10 text-julius-accent hover:bg-julius-accent hover:text-black hover:shadow-[0_0_15px_var(--color-julius-accent)] font-bold text-[9px] tracking-[0.25em] transition-all"
          >
            <span>🛡️</span> GUARDIAN_DASHBOARD
          </Link>
        </div>

        <div className="flex items-center gap-3 text-[9px] font-black tracking-[0.2em] font-mono">
          <span className="text-julius-red bg-julius-red/10 border border-julius-red/25 px-2 py-0.5 rounded shadow-[0_0_10px_var(--color-julius-red-dim)]">
            CONFLICTS: {(eventsByCategory.conflict || 0) + (eventsByCategory.hotspot || 0)}
          </span>
          <span className="text-julius-amber bg-julius-amber/10 border border-julius-amber/25 px-2 py-0.5 rounded">
            HAZARDS: {eventsByCategory.natural || 0}
          </span>
          <span className="text-julius-accent bg-julius-accent/10 border border-julius-accent/25 px-2 py-0.5 rounded glow-cyan">
            CYBER_OPS: {eventsByCategory.cyber || 0}
          </span>
        </div>

        <div className="flex items-center gap-4 text-[10px] tracking-widest text-julius-accent pointer-events-none">
          <span className={`px-2 py-0.5 rounded font-mono font-bold ${realVulns.length > 0 ? 'text-julius-red bg-julius-red/20 border border-julius-red/40 glow-red' : 'text-julius-green bg-julius-green/10 border border-julius-green/30 glow-green'}`}>
            {realVulns.length > 0 ? `VULNS_DETECTED: ${realVulns.length}` : 'VULNS: 0'}
          </span>
          <span className="text-white font-black tracking-widest">ZULU {zuluTime}</span>
        </div>
      </div>

      {/* ─── Left sidebar — Layer toggles ──────────────────────── */}
      <div
        className={`absolute top-12 left-0 z-20 h-[calc(100%-6rem)] transition-all duration-300 ease-in-out ${sidebarOpen ? 'w-52' : 'w-0 overflow-hidden'}`}
      >
        <div className="h-full bg-julius-bg/85 backdrop-blur-md border-r border-julius-border flex flex-col py-4 w-52">
          <div className="px-4 mb-4">
            <p className="text-[9px] text-julius-accent/70 tracking-[0.4em] font-black uppercase font-display px-1 border-l-2 border-julius-accent">Intelligence Layers</p>
          </div>

          <div className="flex-1 overflow-y-auto space-y-1 px-2">
            {ALL_LAYERS.map(layer => {
              const cfg = CATEGORY_CONFIG[layer]
              const active = enabledLayers.has(layer)
              const count = eventsByCategory[layer] || 0
              return (
                <button
                  key={layer}
                  onClick={() => toggleLayer(layer)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-none text-left transition-all duration-200 group
                    ${active
                      ? 'bg-julius-accent/10 border-l-2 border-julius-accent'
                      : 'bg-transparent border border-transparent hover:bg-julius-surface'
                    }`}
                >
                  <span className="text-base leading-none">{cfg.emoji}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className={`text-[11px] font-bold tracking-wide ${active ? 'text-white' : 'text-blue-400/60'}`}>
                        {cfg.label}
                      </span>
                      {count > 0 && (
                        <span
                          className="text-[9px] font-bold px-1.5 py-0.5 rounded-full"
                          style={{ background: cfg.color + '22', color: cfg.color, border: `1px solid ${cfg.color}44` }}
                        >
                          {count}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className={`w-6 h-3 rounded-full transition-colors flex items-center shrink-0
                    ${active ? '' : 'bg-blue-950/60 border border-blue-800/40'}`}
                    style={active ? { background: cfg.color + 'aa', border: `1px solid ${cfg.color}` } : {}}
                  >
                    <div className={`w-2.5 h-2.5 rounded-full bg-white transition-transform mx-0.5
                      ${active ? 'translate-x-2.5' : 'translate-x-0'}`} />
                  </div>
                </button>
              )
            })}
          </div>

          <div className="px-4 pt-4 border-t border-julius-border space-y-2 text-[9px] text-julius-muted font-black tracking-[0.2em] uppercase">
            <div className="flex justify-between">
              <span>EVENTS</span>
              <span className="text-white">{stats.total_events ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span>PATTERNS</span>
              <span className="text-white">{behavStats?.active_patterns ?? 0}</span>
            </div>
            <div className="flex items-center justify-between mt-3">
              <span>CRT FX</span>
              <div
                className={`w-8 h-4 rounded-full p-0.5 cursor-pointer flex items-center transition-colors
                  ${crtFx ? 'bg-cyan-600' : 'bg-blue-900/60 border border-blue-700'}`}
                onClick={() => setCrtFx(v => !v)}
              >
                <div className={`w-3 h-3 rounded-full bg-white transition-transform ${crtFx ? 'translate-x-4' : 'translate-x-0'}`} />
              </div>
            </div>
          </div>

          <div className="px-3 pt-3 mt-auto border-t border-julius-border">
            <Link
              to="/guardian"
              className="w-full flex items-center justify-center gap-2 py-2 px-3 border border-julius-accent/40 bg-julius-accent/5 text-julius-accent hover:bg-julius-accent hover:text-black font-bold text-[9px] tracking-[0.2em] transition-all uppercase rounded animate-pulse"
            >
              <span>🛡️</span> GUARDIAN DASHBOARD
            </Link>
          </div>
        </div>
      </div>

      {/* ─── News Panel — slides in from right on event click ──── */}
      <div
        className={`absolute top-0 right-0 z-30 h-full
          transition-all duration-300 ease-in-out
          ${newsOpen ? 'w-[380px] opacity-100' : 'w-0 opacity-0 overflow-hidden'}`}
        style={{ transitionProperty: 'width, opacity' }}
      >
        <GlobeNewsPanel event={selectedEvent} onClose={handleCloseNews} />
      </div>

      {/* ─── Live TV Panel (bottom-right) ──────────────────────── */}
      {!newsOpen && (
        <div className={`absolute z-25 transition-all duration-300
          ${tvOpen ? 'bottom-[72px] right-3 w-[340px] h-[300px]' : 'bottom-[72px] right-3 w-[120px] h-auto'}`}
        >
          {tvOpen ? (
            <div className="w-full h-full rounded-lg overflow-hidden border border-blue-900/30 shadow-2xl">
              <LiveTVPanel />
              <button
                onClick={() => setTvOpen(false)}
                className="absolute top-1 right-1 w-5 h-5 flex items-center justify-center rounded bg-black/60 text-blue-400 hover:text-white text-xs z-10"
              >✕</button>
            </div>
          ) : (
            <button
              onClick={() => setTvOpen(true)}
              className="flex items-center gap-2 px-3 py-2 rounded-none bg-julius-bg/80 backdrop-blur border border-julius-border hover:border-julius-accent transition-colors pointer-events-auto"
            >
              <div className="w-1.5 h-1.5 bg-julius-red rounded-full animate-pulse shadow-[0_0_5px_var(--color-julius-red)]" />
              <span className="text-[9px] text-julius-red font-black tracking-[0.3em] uppercase">Live_TV_Signal</span>
            </button>
          )}
        </div>
      )}

      {/* ─── Global news ticker (always on) ────────────────── */}
      <div className="absolute bottom-8 left-0 right-0 z-20 pointer-events-auto">
        <GlobalNewsTicker />
      </div>

      {/* ─── Bottom legend bar ─────────────────────────────────── */}
      <div className="absolute bottom-0 left-0 right-0 z-20 flex items-center justify-between px-6 py-2 bg-julius-bg/90 border-t border-julius-border pointer-events-none">
        <GeoDisplay onGeoChangeRef={geoChangeRef} />

        <div className="flex items-center gap-5">
          {ALL_LAYERS.filter(l => enabledLayers.has(l)).map(layer => {
            const cfg = CATEGORY_CONFIG[layer]
            return (
              <div key={layer} className="flex items-center gap-2">
                <span className="w-1 h-1 bg-white" style={{ background: cfg.color, boxShadow: `0 0 5px ${cfg.color}` }} />
                <span className="text-[9px] font-black tracking-[0.2em] uppercase" style={{ color: cfg.color }}>{cfg.label}</span>
              </div>
            )
          })}
        </div>

        <div className="text-[9px] text-julius-muted font-black tracking-[0.2em] text-right uppercase">
          <div>WGS-84 // GLOBAL_COORD</div>
          <div>GDELT // REAL_TIME_INTEL</div>
        </div>
      </div>

      {/* ─── Hint text when nothing selected ─────────────────── */}
      {!newsOpen && globeEvents.length > 0 && (
        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-10 pointer-events-none">
          <div className="text-[9px] text-blue-500/40 tracking-[0.3em] font-bold animate-pulse">
            CLICK A MARKER TO OPEN LIVE NEWS FEED
          </div>
        </div>
      )}

      <style dangerouslySetInnerHTML={{ __html: `
        .crt-scanlines::before {
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
        .scrollbar-thin::-webkit-scrollbar { width: 3px; }
        .scrollbar-thin::-webkit-scrollbar-track { background: transparent; }
        .scrollbar-thin::-webkit-scrollbar-thumb { background: rgba(59,130,246,0.3); border-radius: 2px; }
        .line-clamp-3 {
          display: -webkit-box;
          -webkit-line-clamp: 3;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }
      `}} />
    </div>
  )
}

// ─── Geo coord HUD ────────────────────────────────────────────────────────────
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
        <div className="text-julius-muted italic text-[9px] tracking-[0.2em] uppercase">Awaiting_Geo_Loc...</div>
      )}
    </div>
  )
}
