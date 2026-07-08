import { useState } from 'react'

interface Channel {
  name: string
  videoId?: string
  channelId?: string
  logo: string
}

const LIVE_CHANNELS: Channel[] = [
  { name: 'Sky News',        channelId: 'UC9Ou4N1-d9yH4L_u983d98g', logo: '🛡️' },
  { name: 'Al Jazeera',      channelId: 'UCNye-wNBqNL5ZzHSJj3l8Bg', logo: '🟢' },
  { name: 'France 24',       channelId: 'UCQruz7qrPBbqL52T2P96t-Q', logo: '🔵' },
  { name: 'DW News',         channelId: 'UCknLrEdhRCp3S2H3N_4867A', logo: '🟡' },
]

const getEmbedUrl = (ch: Channel, controls = true) => {
  const base = ch.channelId
    ? `https://www.youtube.com/embed/live_stream?channel=${ch.channelId}`
    : `https://www.youtube.com/embed/${ch.videoId}`
  return `${base}&autoplay=1&mute=1&rel=0&modestbranding=1${controls ? '' : '&controls=0'}`
}

export function LiveTVPanel() {
  const [expanded, setExpanded] = useState(true)
  const [focusedIdx, setFocusedIdx] = useState<number | null>(null)

  return (
    <div className="flex flex-col bg-julius-bg/95 backdrop-blur-xl border-l border-julius-border overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded(v => !v)}
        className="flex items-center justify-between px-3 py-2 border-b border-julius-border hover:bg-julius-surface transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 bg-julius-red rounded-full animate-pulse shadow-[0_0_5px_var(--color-julius-red)]" />
          <span className="text-[10px] font-black tracking-[0.3em] text-julius-red font-display">LIVE_INTEL_TV</span>
          <span className="text-[9px] text-julius-muted font-mono uppercase bg-julius-border/20 px-1">4_SIGHOSTS</span>
        </div>
        <span className="text-julius-accent text-xs">{expanded ? '▾' : '▸'}</span>
      </button>

      {expanded && (
        <div className="flex-1 flex flex-col">
          {/* If a channel is focused, show it large */}
          {focusedIdx !== null ? (
            <div className="flex flex-col flex-1">
              <div className="flex items-center justify-between px-3 py-1.5 bg-julius-red/5 border-b border-julius-red/20">
                <div className="flex items-center gap-2">
                  <span>{LIVE_CHANNELS[focusedIdx].logo}</span>
                  <span className="text-[10px] text-white font-black font-display uppercase tracking-widest">{LIVE_CHANNELS[focusedIdx].name}</span>
                  <span className="text-[8px] text-julius-red font-black tracking-[0.4em] uppercase animate-pulse">● LIVE_SIGNAL</span>
                </div>
                <button
                  onClick={() => setFocusedIdx(null)}
                  className="text-[9px] text-julius-accent hover:text-white transition-colors tracking-widest font-black uppercase font-mono"
                >
                  [Exit_Focus]
                </button>
              </div>
              <div className="flex-1 bg-black">
                <iframe
                  src={getEmbedUrl(LIVE_CHANNELS[focusedIdx], true)}
                  className="w-full h-full"
                  style={{ minHeight: '200px', border: 'none' }}
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                  title={LIVE_CHANNELS[focusedIdx].name}
                />
              </div>
            </div>
          ) : (
            /* 2x2 grid of all 4 channels */
            <div className="grid grid-cols-2 gap-px bg-julius-border flex-1">
              {LIVE_CHANNELS.map((ch, i) => (
                <div key={i} className="relative bg-julius-bg/80 group flex flex-col">
                  <div className="flex items-center justify-between px-2 py-1 bg-julius-bg/10 backdrop-blur-sm border-b border-julius-border/20">
                    <div className="flex items-center gap-2">
                      <span className="text-xs">{ch.logo}</span>
                      <span className="text-[9px] text-julius-accent font-black uppercase tracking-tighter truncate font-mono">{ch.name}</span>
                    </div>
                    <button
                      onClick={() => setFocusedIdx(i)}
                      className="text-[8px] text-julius-accent hover:text-white opacity-0 group-hover:opacity-100 transition-all font-black"
                    >
                      [+]
                    </button>
                  </div>
                  <div className="flex-1 min-h-[80px]">
                    <iframe
                      src={getEmbedUrl(ch, false)}
                      className="w-full h-full"
                      style={{ border: 'none', minHeight: '80px' }}
                      allow="accelerometer; autoplay; encrypted-media"
                      title={ch.name}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
