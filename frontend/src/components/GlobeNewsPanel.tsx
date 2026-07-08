import { useState, useEffect, useRef } from 'react'
import { type GlobeEvent, CATEGORY_CONFIG } from '../lib/globeData'

interface Article {
  title: string
  url: string
  source: string
  image: string
  timestamp: string
  source_country: string
}

interface Props {
  event: GlobeEvent | null
  onClose: () => void
}

export function GlobeNewsPanel({ event, onClose }: Props) {
  const [articles, setArticles] = useState<Article[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [clockMs, setClockMs] = useState(() => Date.now())
  const abortRef = useRef<AbortController | null>(null)
  const tickerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const id = window.setInterval(() => setClockMs(Date.now()), 60_000)
    return () => clearInterval(id)
  }, [])

  // Fetch news from GDELT when event changes
  useEffect(() => {
    if (!event) {
      queueMicrotask(() => setArticles([]))
      return
    }

    const boot = window.setTimeout(() => {
      abortRef.current?.abort()
      abortRef.current = new AbortController()
      setLoading(true)
      setError('')
      setArticles([])

      const params = new URLSearchParams()
      if (event.country) params.set('country', event.country)
      if (event.title) params.set('topic', event.title)
      params.set('limit', '15')

      const token = localStorage.getItem('julius_token')
      const headers: Record<string, string> = {}
      if (token) headers['Authorization'] = `Bearer ${token}`

      fetch(`/api/globe/news?${params}`, { headers, signal: abortRef.current.signal })
        .then(r => r.json())
        .then(data => {
          if (data.status === 'ok') setArticles(data.articles || [])
          else setError(data.status === 'timeout' ? 'Feed timed out — retrying...' : 'No coverage found')
        })
        .catch(err => { if (err.name !== 'AbortError') setError('Feed unavailable') })
        .finally(() => setLoading(false))
    }, 0)

    return () => {
      clearTimeout(boot)
      abortRef.current?.abort()
    }
  }, [event])

  if (!event) return null

  const cfg = CATEGORY_CONFIG[event.category]
  const sevColors: Record<string, string> = {
    critical: '#ef4444', high: '#f97316', medium: '#eab308', low: '#22c55e'
  }
  const sevCol = sevColors[event.severity]

  const timeAgo = (iso: string) => {
    if (!iso) return ''
    try {
      const ms = clockMs - new Date(iso).getTime()
      const h = Math.floor(ms / 3600000)
      if (h < 1) return `${Math.max(1, Math.floor(ms / 60000))}m ago`
      if (h < 24) return `${h}h ago`
      return `${Math.floor(h / 24)}d ago`
    } catch { return '' }
  }

  return (
    <div className="flex flex-col h-full bg-julius-bg/95 backdrop-blur-xl border-l border-julius-border overflow-hidden relative">
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-julius-accent/5 pointer-events-none"></div>

      {/* ── Header with event info ──────────────────────────────── */}
      <div className="shrink-0 px-4 py-3" style={{ borderBottom: `1px solid ${cfg.color}25`, background: `${cfg.color}08` }}>
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-2.5 min-w-0">
            <span className="text-lg leading-none mt-0.5">{cfg.emoji}</span>
            <div className="min-w-0">
              <h2 className="text-white font-black text-[13px] leading-tight truncate font-display uppercase tracking-widest glow-cyan">{event.title}</h2>
              <div className="flex items-center gap-2 mt-2">
                {event.country && <span className="text-[10px] text-julius-accent font-bold uppercase tracking-widest">LOC:: {event.country}</span>}
                <span className="text-[9px] font-black px-1.5 py-0.5 rounded uppercase tracking-widest"
                  style={{ background: sevCol + '22', color: sevCol, border: `1px solid ${sevCol}40` }}>
                  {event.severity}
                </span>
              </div>
            </div>
          </div>
          <button onClick={onClose} className="text-julius-muted hover:text-julius-red text-xl leading-none transition-colors ml-2">×</button>
        </div>
      </div>

      {/* ── Breaking news ticker (horizontal scroll) ──────────── */}
      {articles.length > 0 && (
        <div className="shrink-0 overflow-hidden border-b border-julius-red/20 bg-julius-red/5">
          <div className="flex items-center">
            <span className="shrink-0 bg-julius-red text-white text-[9px] font-black tracking-[0.3em] px-3 py-2 uppercase font-display shadow-[0_0_10px_var(--color-julius-red-dim)]">
              CRITICAL_SIGNAL
            </span>
            <div className="overflow-hidden flex-1">
              <div
                ref={tickerRef}
                className="flex whitespace-nowrap animate-ticker"
              >
                {/* Duplicate for seamless loop */}
                {[...articles, ...articles].map((a, i) => (
                  <a
                    key={i}
                    href={a.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-3 px-5 py-2 text-[10px] text-julius-text hover:text-julius-accent transition-colors font-mono uppercase tracking-widest"
                  >
                    <span className="text-julius-red">//</span>
                    <span className="font-bold">{a.title}</span>
                    <span className="text-julius-muted text-[8px] border border-julius-muted/20 px-1">{a.source}</span>
                  </a>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── LIVE FEED label ──────────────────────────────────────── */}
      <div className="shrink-0 px-4 py-2 flex items-center justify-between border-b border-julius-border bg-julius-surface">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 bg-julius-red rounded-full animate-pulse shadow-[0_0_5px_var(--color-julius-red)]" />
            <span className="text-[10px] font-black tracking-[0.3em] text-julius-red font-display">SIGNAL_INTEL</span>
          </span>
          {!loading && articles.length > 0 && (
            <span className="text-[9px] text-julius-muted font-mono uppercase bg-julius-border/20 px-1">{articles.length} SOURCES</span>
          )}
        </div>
        <span className="text-[8px] text-julius-muted font-mono uppercase tracking-widest">GDELT_RELAY // 15M</span>
      </div>

      {/* ── News articles list ──────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto min-h-0 news-scroll">

        {loading && (
          <div className="flex flex-col items-center justify-center h-52 gap-4">
            <div className="relative w-10 h-10">
              <div className="absolute inset-0 border-2 border-julius-accent/10 rounded-full" />
              <div className="absolute inset-0 border-2 border-t-julius-accent rounded-full animate-spin shadow-[0_0_10px_var(--color-julius-accent)]" />
            </div>
            <span className="text-[10px] text-julius-accent font-black tracking-[0.4em] uppercase font-display animate-pulse">Scanning_Feeds...</span>
          </div>
        )}

        {!loading && error && (
          <div className="m-3 p-3 rounded border border-orange-500/20 bg-orange-500/5">
            <p className="text-[10px] text-orange-400">{error}</p>
            <p className="text-[8px] text-blue-600/40 mt-1">GDELT may be throttling — try another event</p>
          </div>
        )}

        {!loading && !error && articles.length === 0 && (
          <div className="flex flex-col items-center justify-center h-40 gap-2">
            <span className="text-3xl opacity-20">📰</span>
            <span className="text-[9px] text-blue-700/40 tracking-widest">NO COVERAGE FOUND</span>
          </div>
        )}

        {!loading && articles.map((article, i) => (
          <a
            key={i}
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="block border-b border-julius-border hover:bg-julius-accent/5 transition-colors group"
          >
            {/* Card with optional image */}
            {article.image && i < 3 ? (
              // Top 3 articles get a hero image
              <div className="relative">
                <div className="w-full h-32 overflow-hidden bg-blue-950/30">
                  <img
                    src={article.image}
                    alt=""
                    className="w-full h-full object-cover opacity-70 group-hover:opacity-90 transition-opacity"
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                  />
                </div>
                <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/90 via-black/60 to-transparent px-4 pt-8 pb-3">
                  <p className="text-[12px] text-white font-bold leading-snug line-clamp-2">{article.title}</p>
                  <div className="flex items-center gap-2 mt-1.5">
                    <span className="text-[9px] text-blue-300/70 font-mono">{article.source}</span>
                    {article.timestamp && <span className="text-[9px] text-blue-500/40">{timeAgo(article.timestamp)}</span>}
                  </div>
                </div>
              </div>
            ) : (
              // Text-only card for remaining articles
              <div className="flex gap-3 px-4 py-3">
                {article.image && (
                  <div className="w-16 h-16 shrink-0 rounded overflow-hidden bg-blue-950/30">
                    <img
                      src={article.image}
                      alt=""
                      className="w-full h-full object-cover opacity-70 group-hover:opacity-90 transition-opacity"
                      onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                    />
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] text-white/85 leading-snug font-medium group-hover:text-white transition-colors line-clamp-3">
                    {article.title}
                  </p>
                  <div className="flex items-center gap-2 mt-1.5">
                    <span className="text-[9px] text-blue-400/60 font-mono">{article.source}</span>
                    {article.timestamp && <span className="text-[9px] text-blue-600/40">{timeAgo(article.timestamp)}</span>}
                    <span className="ml-auto text-[8px] font-bold opacity-0 group-hover:opacity-100 transition-opacity"
                      style={{ color: cfg.color }}>
                      READ ↗
                    </span>
                  </div>
                </div>
              </div>
            )}
          </a>
        ))}

        {/* Footer */}
        {articles.length > 0 && (
          <div className="px-4 py-4 text-center border-t border-blue-900/15">
            <p className="text-[8px] text-blue-800/30 tracking-[0.3em]">
              POWERED BY GDELT PROJECT — SCANNING 250K+ SOURCES
            </p>
          </div>
        )}
      </div>

      {/* Inline styles */}
      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes ticker {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        .animate-ticker {
          animation: ticker 45s linear infinite;
        }
        .animate-ticker:hover {
          animation-play-state: paused;
        }
        .news-scroll::-webkit-scrollbar { width: 2px; }
        .news-scroll::-webkit-scrollbar-track { background: transparent; }
        .news-scroll::-webkit-scrollbar-thumb { background: rgba(59,130,246,0.2); border-radius: 1px; }
        .line-clamp-2 {
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }
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
