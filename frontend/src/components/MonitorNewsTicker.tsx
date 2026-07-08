import { useState, useEffect, useRef } from 'react'
import { fetchGlobalHeadlines, type NewsArticle } from '../lib/monitorData'

export function MonitorNewsTicker() {
  const [headlines, setHeadlines] = useState<NewsArticle[]>([])
  const tickerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchGlobalHeadlines().then(setHeadlines)
    const interval = setInterval(() => {
      fetchGlobalHeadlines().then(setHeadlines)
    }, 5 * 60 * 1000) // Refresh every 5 minutes
    return () => clearInterval(interval)
  }, [])

  if (headlines.length === 0) {
    return (
      <div className="w-full h-7 bg-julius-bg/90 border-t border-julius-border flex items-center px-4">
        <span className="text-[9px] text-julius-muted/40 tracking-[0.2em] uppercase animate-pulse">
          Loading global intelligence feed...
        </span>
      </div>
    )
  }

  // Duplicate for seamless scroll
  const displayHeadlines = [...headlines, ...headlines]

  return (
    <div className="w-full h-7 bg-julius-bg/90 border-t border-julius-border flex items-center overflow-hidden relative">
      {/* Ticker label */}
      <div className="shrink-0 flex items-center gap-2 px-3 border-r border-julius-border h-full bg-julius-red/10 z-10">
        <div className="w-1.5 h-1.5 bg-julius-red rounded-full animate-pulse" />
        <span className="text-[8px] text-julius-red font-black tracking-[0.3em] uppercase font-display">INTEL_FEED</span>
      </div>

      {/* Scrolling content */}
      <div className="flex-1 overflow-hidden relative">
        <div className="absolute inset-y-0 left-0 w-8 bg-gradient-to-r from-julius-bg/90 to-transparent z-10 pointer-events-none" />
        <div className="absolute inset-y-0 right-0 w-8 bg-gradient-to-l from-julius-bg/90 to-transparent z-10 pointer-events-none" />
        <div
          ref={tickerRef}
          className="flex items-center gap-8 whitespace-nowrap animate-ticker h-full"
          style={{
            animation: `tickerScroll ${headlines.length * 6}s linear infinite`,
          }}
        >
          {displayHeadlines.map((article, i) => (
            <a
              key={`${article.url}-${i}`}
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-[10px] hover:text-julius-accent transition-colors shrink-0"
            >
              <span className="text-julius-accent/60">▸</span>
              <span className="text-julius-text/80 font-medium">{article.title}</span>
              <span className="text-julius-muted text-[8px]">{article.source}</span>
            </a>
          ))}
        </div>
      </div>

      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes tickerScroll {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        .animate-ticker { will-change: transform; }
      `}} />
    </div>
  )
}
