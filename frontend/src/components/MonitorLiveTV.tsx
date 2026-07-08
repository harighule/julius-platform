import { useState, useRef, useEffect } from 'react'

interface Channel {
  id: string
  name: string
  videoId?: string
  channelId?: string
  region: string
}

const DEFAULT_CHANNELS: Channel[] = [
  { id: 'bloomberg', name: 'Bloomberg', channelId: 'UC7UFcUbAd8oyCBWCogVpJ6g', region: 'NA' },
  { id: 'sky', name: 'Sky News', channelId: 'UC9Ou4N1-d9yH4L_u983d98g', region: 'EU' },
  { id: 'france24', name: 'France 24', channelId: 'UCQruz7qrPBbqL52T2P96t-Q', region: 'EU' },
  { id: 'dw', name: 'DW News', channelId: 'UCknLrEdhRCp3S2H3N_4867A', region: 'EU' },
  { id: 'aljazeera', name: 'Al Jazeera', channelId: 'UCNye-wNBqNL5ZzHSJj3l8Bg', region: 'ME' },
  { id: 'euronews', name: 'Euronews', channelId: 'UCSrZ37JIu3AdGlUgt18F8FQ', region: 'EU' },
  { id: 'nhk', name: 'NHK World', channelId: 'UC1oD41b1M69XU5679_q8oGg', region: 'AS' },
  { id: 'abc-au', name: 'ABC News AU', channelId: 'UCrizSjHscQ9g0M6e0N2NdfA', region: 'OC' },
  { id: 'ndtv', name: 'NDTV', channelId: 'UCZFMm1FwguBY-g_TX_1VJ2g', region: 'AS' },
]

const getEmbedUrl = (ch: Channel, muted: boolean) => {
  const base = ch.channelId
    ? `https://www.youtube.com/embed/live_stream?channel=${ch.channelId}`
    : `https://www.youtube.com/embed/${ch.videoId}`
  return `${base}&autoplay=1&mute=${muted ? 1 : 0}&controls=0&rel=0&modestbranding=1&playsinline=1`
}

const REGION_LABELS: Record<string, string> = {
  NA: 'Americas', EU: 'Europe', ME: 'Middle East', AS: 'Asia', AF: 'Africa', OC: 'Oceania'
}

export function MonitorLiveTV() {
  const [active, setActive] = useState<Channel>(DEFAULT_CHANNELS[0])
  const [expanded, setExpanded] = useState(true)
  const [muted, setMuted] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Scroll active channel into view
  useEffect(() => {
    const el = scrollRef.current?.querySelector(`[data-channel="${active.id}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' })
  }, [active.id])

  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        className="flex items-center gap-2 px-3 py-2 bg-julius-bg/80 backdrop-blur border border-julius-border hover:border-julius-accent transition-colors"
      >
        <div className="w-1.5 h-1.5 bg-julius-red rounded-full animate-pulse shadow-[0_0_5px_var(--color-julius-red)]" />
        <span className="text-[9px] text-julius-red font-black tracking-[0.3em] uppercase">LIVE_TV</span>
      </button>
    )
  }

  return (
    <div className="flex flex-col bg-julius-bg/95 backdrop-blur-md border border-julius-border rounded overflow-hidden" style={{ width: '100%' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-julius-border bg-julius-surface/50">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 bg-julius-red rounded-full animate-pulse shadow-[0_0_5px_var(--color-julius-red)]" />
          <span className="text-[9px] text-julius-red font-black tracking-[0.3em] uppercase font-display">LIVE_BROADCAST</span>
          <span className="text-[8px] text-julius-muted tracking-wider">{active.name}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setMuted(m => !m)}
            className="w-5 h-5 flex items-center justify-center text-julius-muted hover:text-julius-accent text-[10px] transition-colors"
            title={muted ? 'Unmute' : 'Mute'}
          >
            {muted ? '🔇' : '🔊'}
          </button>
          <button
            onClick={() => setExpanded(false)}
            className="w-5 h-5 flex items-center justify-center text-julius-muted hover:text-white text-xs"
          >✕</button>
        </div>
      </div>

      {/* Video embed */}
      <div className="relative w-full" style={{ paddingBottom: '56.25%' }}>
        <iframe
          className="absolute inset-0 w-full h-full"
          src={getEmbedUrl(active, muted)}
          allow="autoplay; encrypted-media"
          allowFullScreen
          style={{ border: 'none' }}
        />
      </div>

      {/* Channel strip */}
      <div ref={scrollRef} className="flex items-center gap-0.5 px-1 py-1 overflow-x-auto scrollbar-hide bg-julius-surface/30">
        {DEFAULT_CHANNELS.map(ch => (
          <button
            key={ch.id}
            data-channel={ch.id}
            onClick={() => setActive(ch)}
            className={`shrink-0 px-2 py-1 text-[8px] font-bold tracking-wider uppercase transition-all border
              ${active.id === ch.id
                ? 'bg-julius-accent/15 text-julius-accent border-julius-accent/40'
                : 'bg-transparent text-julius-muted border-transparent hover:text-white hover:bg-julius-surface2'
              }`}
          >
            <span className="text-[7px] opacity-60 mr-1">{REGION_LABELS[ch.region] || ch.region}</span>
            {ch.name}
          </button>
        ))}
      </div>
    </div>
  )
}
