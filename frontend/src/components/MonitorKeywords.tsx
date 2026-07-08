import { useState, useEffect, useRef, useCallback } from 'react'
import { MONITOR_TAG_COLORS, type MonitorKeyword, type NewsArticle } from '../lib/monitorData'

interface Props {
  news: NewsArticle[]
}

function generateId(): string {
  return `mk-${Date.now()}-${Math.random().toString(36).substring(2, 8)}`
}

const STORAGE_KEY = 'julius_monitor_keywords'

function loadKeywords(): MonitorKeyword[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch {
    void 0
  }
  return []
}

function saveKeywords(keywords: MonitorKeyword[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(keywords))
}

export function MonitorKeywords({ news }: Props) {
  const [keywords, setKeywords] = useState<MonitorKeyword[]>(loadKeywords)
  const [inputVal, setInputVal] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => saveKeywords(keywords), [keywords])

  const addKeyword = useCallback(() => {
    const val = inputVal.trim()
    if (!val) return
    const kws = val.split(',').map(k => k.trim().toLowerCase()).filter(Boolean)
    if (kws.length === 0) return
    const color = MONITOR_TAG_COLORS[keywords.length % MONITOR_TAG_COLORS.length]
    setKeywords(prev => [...prev, { id: generateId(), keywords: kws, color }])
    setInputVal('')
    inputRef.current?.focus()
  }, [inputVal, keywords.length])

  const removeKeyword = (id: string) => {
    setKeywords(prev => prev.filter(k => k.id !== id))
  }

  // Find matching news
  const matchedNews: (NewsArticle & { matchColor: string })[] = []
  const seenUrls = new Set<string>()

  for (const article of news) {
    for (const monitor of keywords) {
      const searchText = `${article.title} ${article.source}`.toLowerCase()
      const matched = monitor.keywords.some(kw => {
        try {
          const escaped = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
          return new RegExp(`\\b${escaped}\\b`, 'i').test(searchText)
        } catch {
          return searchText.includes(kw)
        }
      })
      if (matched && !seenUrls.has(article.url)) {
        seenUrls.add(article.url)
        matchedNews.push({ ...article, matchColor: monitor.color })
      }
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Input */}
      <div className="flex items-center gap-1.5 px-3 py-2 border-b border-julius-border">
        <input
          ref={inputRef}
          type="text"
          value={inputVal}
          onChange={e => setInputVal(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && addKeyword()}
          placeholder="Add keywords (comma separated)..."
          className="flex-1 bg-julius-bg/60 border border-julius-border px-2 py-1 text-[10px] text-julius-text placeholder:text-julius-muted/50 outline-none focus:border-julius-accent/50 transition-colors"
        />
        <button
          onClick={addKeyword}
          className="px-2 py-1 text-[9px] font-bold tracking-wider bg-julius-accent/10 text-julius-accent border border-julius-accent/30 hover:bg-julius-accent/20 transition-colors"
        >
          ADD
        </button>
      </div>

      {/* Tags */}
      {keywords.length > 0 && (
        <div className="flex flex-wrap gap-1 px-3 py-1.5 border-b border-julius-border/50">
          {keywords.map(k => (
            <span
              key={k.id}
              className="inline-flex items-center gap-1 px-2 py-0.5 text-[9px] font-bold rounded-sm"
              style={{ background: k.color + '22', color: k.color, border: `1px solid ${k.color}44` }}
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: k.color }} />
              {k.keywords.join(', ')}
              <button
                onClick={() => removeKeyword(k.id)}
                className="ml-0.5 opacity-60 hover:opacity-100"
              >×</button>
            </span>
          ))}
        </div>
      )}

      {/* Results */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5">
        {keywords.length === 0 ? (
          <div className="text-[10px] text-julius-muted/50 py-4 text-center">
            Add keywords to monitor news feeds
          </div>
        ) : matchedNews.length === 0 ? (
          <div className="text-[10px] text-julius-muted/50 py-4 text-center">
            No matches found in {news.length} articles
          </div>
        ) : (
          <>
            <div className="text-[9px] text-julius-muted mb-1">
              {matchedNews.length} match{matchedNews.length !== 1 ? 'es' : ''}
            </div>
            {matchedNews.slice(0, 15).map((article, i) => (
              <a
                key={`${article.url}-${i}`}
                href={article.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block py-1.5 hover:bg-julius-surface/50 transition-colors border-l-2 pl-2 -ml-1"
                style={{ borderLeftColor: article.matchColor }}
              >
                <div className="text-[8px] text-julius-muted tracking-wider uppercase">{article.source}</div>
                <div className="text-[10px] text-julius-text leading-snug line-clamp-2">{article.title}</div>
              </a>
            ))}
          </>
        )}
      </div>
    </div>
  )
}
