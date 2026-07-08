import { useEffect, useState, useRef } from 'react'

interface HistoryItem {
  timestamp: string
  command: string
  output?: string
  error?: string
  exit_code?: number
  duration_ms?: number
  cwd?: string
  success?: boolean
  backend?: string
}

interface TerminalStatus {
  backend?: string
  distro?: string
}

export function TerminalPanel() {
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [status, setStatus] = useState<TerminalStatus | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const fetchHistory = async () => {
    try {
      const res = await fetch('/api/terminal/history')
      if (res.ok) {
        const data = await res.json()
        setHistory(data)
      }
      
      const statusRes = await fetch('/api/terminal/status')
      if (statusRes.ok) setStatus(await statusRes.json())
    } catch (e) {
      console.error('Failed to fetch terminal history', e)
    }
  }

  useEffect(() => {
    const boot = window.setTimeout(() => {
      void fetchHistory()
    }, 0)
    const interval = setInterval(() => void fetchHistory(), 2000)
    return () => {
      clearTimeout(boot)
      clearInterval(interval)
    }
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history])

  return (
    <div className="flex flex-col h-full bg-black text-gray-300 font-mono p-4 overflow-hidden relative">
      <div className="flex items-center justify-between border-b border-gray-800 pb-2 mb-4 shrink-0">
        <div className="flex items-center gap-3">
          <div className="text-julius-accent font-bold tracking-widest text-lg px-2">JULIUS TERMINAL</div>
          {status && (
            <div className="text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-400">
              Backend: {status.backend} {status.distro ? `(${status.distro})` : ''}
            </div>
          )}
        </div>
        <div className="flex gap-2">
          <div className="w-3 h-3 rounded-full bg-red-500/20 border border-red-500/50"></div>
          <div className="w-3 h-3 rounded-full bg-yellow-500/20 border border-yellow-500/50"></div>
          <div className="w-3 h-3 rounded-full bg-green-500/20 border border-green-500/50"></div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto space-y-6 pb-20 scrollbar-thin scrollbar-thumb-gray-700 scrollbar-track-transparent">
        <div className="text-gray-500 mb-6 text-sm">
          Welcome to JULIUS Secure Terminal Integration.<br/>
          Commands executed via the AI Chatbot are displayed here in real-time.
        </div>

        {history.map((item, i) => (
          <div key={i} className="flex flex-col gap-1 text-sm">
            <div className="flex items-center gap-2 text-blue-400">
              <span className="text-green-500">julius@sec-ops</span>
              <span className="text-gray-500">[{new Date(item.timestamp).toLocaleTimeString()}]</span>
              <span className="text-gray-400">{item.cwd || '~'}</span>
              <span className="text-white">$</span>
              <span className="text-white ml-2">{item.command.split('\n')[0]} {item.command.includes('\n') ? '...' : ''}</span>
            </div>
            
            {item.exit_code === undefined ? (
              <div className="mt-2 pl-4 py-2 border-l-2 border-yellow-500/50 bg-gray-900/50 whitespace-pre-wrap font-mono text-xs overflow-x-auto">
                <div className="text-yellow-500/80 animate-pulse mb-2 text-[10px] tracking-wider uppercase">
                  [ System Execution Context Active ]
                </div>
                {item.output && <div className="text-gray-300">{item.output}</div>}
                <div className="inline-block w-2 h-3 bg-gray-400 animate-ping ml-1 mt-1"></div>
              </div>
            ) : (
              <div className={`mt-2 pl-4 py-2 border-l-2 ${item.success ? 'border-gray-700' : 'border-red-500/50'} bg-gray-900/30 whitespace-pre-wrap font-mono text-xs overflow-x-auto`}>
                {item.output && <div className="text-gray-300">{item.output}</div>}
                {item.error && <div className="text-red-400 mt-2">{item.error}</div>}
                <div className="mt-2 text-gray-600 text-[10px]">
                  Exit: {item.exit_code} • {(item.duration_ms || 0) / 1000}s
                </div>
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      
      {/* Decorative scanline overlay */}
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%),linear-gradient(90deg,rgba(255,0,0,0.06),rgba(0,255,0,0.02),rgba(0,0,255,0.06))] bg-[length:100%_4px,3px_100%] z-50 opacity-20"></div>
    </div>
  )
}
