import { useState, useEffect, useRef } from 'react'

interface TickerArticle {
  title: string
  url: string
  source: string
}

function mapTickerArticles(raw: unknown): TickerArticle[] {
  if (!Array.isArray(raw)) return []
  return raw.map((a: unknown) => {
    const o = a as Record<string, unknown>
    return {
      title: String(o.title ?? ''),
      url: String(o.url ?? ''),
      source: String(o.source ?? ''),
    }
  })
}

/**
 * Always-on global news ticker — fetches top headlines from GDELT
 * and scrolls them horizontally, WorldMonitor-style.
 */
export function GlobalNewsTicker() {
  const [articles, setArticles] = useState<TickerArticle[]>([])
  const fetchedRef = useRef(false)

  useEffect(() => {
    if (fetchedRef.current) return
    fetchedRef.current = true

    const token = localStorage.getItem('julius_token')
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`

    // Fetch general global news — broad query
    const params = new URLSearchParams({
      country: 'world',
      topic: 'conflict military attack',
      limit: '20',
    })

    fetch(`/api/globe/news?${params}`, { headers })
      .then(r => r.json())
      .then(data => {
        if (data.status === 'ok' && data.articles?.length) {
          setArticles(mapTickerArticles(data.articles))
        }
      })
      .catch(() => {})
  }, [])

  // Refresh every 5 minutes
  useEffect(() => {
    const interval = setInterval(() => {
      const token = localStorage.getItem('julius_token')
      const headers: Record<string, string> = {}
      if (token) headers['Authorization'] = `Bearer ${token}`
      const params = new URLSearchParams({
        country: 'world',
        topic: 'conflict military attack',
        limit: '20',
      })
      fetch(`/api/globe/news?${params}`, { headers })
        .then(r => r.json())
        .then(data => {
          if (data.status === 'ok' && data.articles?.length) {
            setArticles(mapTickerArticles(data.articles))
          }
        })
        .catch(() => {})
    }, 5 * 60_000)
    return () => clearInterval(interval)
  }, [])

  if (articles.length === 0) return null

  return (
    <div className="w-full overflow-hidden bg-julius-bg/80 backdrop-blur-sm border-t border-julius-border flex items-center">
      <span className="shrink-0 bg-julius-red text-white text-[9px] font-black tracking-[0.2em] px-4 py-1.5 uppercase font-display shadow-[0_0_10px_var(--color-julius-red-dim)]">
        LIVE_INTEL_STREAM
      </span>
      <div className="overflow-hidden flex-1">
        <div className="flex whitespace-nowrap global-ticker">
          {[...articles, ...articles].map((a, i) => (
            <a
              key={i}
              href={a.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-6 py-1 text-[10px] text-julius-text hover:text-julius-accent transition-colors font-mono uppercase tracking-wider"
            >
              <span className="text-julius-red">//</span>
              <span>{a.title}</span>
              <span className="text-julius-muted text-[8px] ml-1">[{a.source}]</span>
            </a>
          ))}
        </div>
      </div>

      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes globalTicker { 0%{transform:translateX(0)} 100%{transform:translateX(-50%)} }
        .global-ticker { animation: globalTicker 60s linear infinite; }
        .global-ticker:hover { animation-play-state: paused; }
      `}} />
    </div>
  )
}
