import { useState, useRef, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  tool_calls?: { name: string; args: string }[]
}

export function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: `Hello! I am JULIUS AI — your autonomous security intelligence assistant.

I have access to all platform modules:
- Scanner — scan targets, check ports
- Exploits — run security assessments
- Behavioral — check patterns and alerts
- Identity — resolve and track identities
- Dark Web — search .onion sites via Tor
- Events — monitor live event stream
- Tools — IP lookup, DNS, CVE check

What would you like me to investigate?`,
      timestamp: new Date().toISOString(),
    }
  ])
  const [input, setInput] = useState('')
  const [sessionId] = useState(() => `session_${Date.now()}`)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const chatMut = useMutation({
    mutationFn: async (message: string) => {
      const history = messages.slice(-10).map(m => ({
        role: m.role,
        content: m.content,
      }))

      const res = await fetch('/api/chat/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          session_id: sessionId,
          conversation_history: history,
        }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err?.detail || `Server error ${res.status}`)
      }

      return res.json()
    },
    onSuccess: (data: any) => {
      const reply =
        data?.message ||
        data?.response ||
        data?.content ||
        data?.reply ||
        'No response received.'
      const toolCalls = data?.tool_calls || []
      setMessages(prev => [
        ...prev,
        {
          id: `msg_${Date.now()}`,
          role: 'assistant',
          content: reply,
          timestamp: new Date().toISOString(),
          tool_calls: toolCalls,
        },
      ])
    },
    onError: (error: any) => {
      setMessages(prev => [
        ...prev,
        {
          id: `err_${Date.now()}`,
          role: 'assistant',
          content: `Error: ${error?.message || 'Failed to get response. Make sure OPENAI_API_KEY is set in your .env file.'}`,
          timestamp: new Date().toISOString(),
        },
      ])
    },
  })

  const sendMessage = () => {
    const text = input.trim()
    if (!text || chatMut.isPending) return
    setMessages(prev => [
      ...prev,
      {
        id: `user_${Date.now()}`,
        role: 'user',
        content: text,
        timestamp: new Date().toISOString(),
      },
    ])
    setInput('')
    chatMut.mutate(text)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const quickCommands = [
    'Scan 127.0.0.1',
    'Check behavioral alerts',
    'Search dark web: cybersecurity threats',
    'Get system stats',
    'List vulnerabilities',
    'IP lookup 8.8.8.8',
  ]

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-julius-border bg-julius-surface">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🤖</span>
          <div>
            <h1 className="text-sm font-bold tracking-wide">JULIUS AI</h1>
            <p className="text-[10px] text-julius-muted">
              Powered by AutoGen + Cognitive Memory
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div
            className={`w-2 h-2 rounded-full ${
              chatMut.isPending
                ? 'bg-yellow-400 animate-pulse'
                : 'bg-green-400'
            }`}
          />
          <span className="text-[10px] text-julius-muted">
            {chatMut.isPending ? 'Thinking...' : 'Ready'}
          </span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.map(msg => (
          <div
            key={msg.id}
            className={`flex gap-3 ${
              msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'
            }`}
          >
            {/* Avatar */}
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-sm flex-shrink-0 ${
                msg.role === 'user'
                  ? 'bg-blue-500 text-white'
                  : 'bg-julius-surface2 border border-julius-border'
              }`}
            >
              {msg.role === 'user' ? '👤' : '🤖'}
            </div>

            {/* Bubble */}
            <div
              className={`max-w-[75%] flex flex-col gap-1 ${
                msg.role === 'user' ? 'items-end' : 'items-start'
              }`}
            >
              <div
                className={`rounded-xl px-4 py-3 text-xs leading-relaxed whitespace-pre-wrap ${
                  msg.role === 'user'
                    ? 'bg-blue-500 text-white rounded-tr-none'
                    : 'bg-julius-surface border border-julius-border text-julius-text rounded-tl-none'
                }`}
              >
                {msg.content}
              </div>

              {/* Tool calls */}
              {msg.tool_calls && msg.tool_calls.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {msg.tool_calls.map((tc, i) => (
                    <span
                      key={i}
                      className="text-[9px] bg-julius-surface2 border border-julius-border text-julius-muted px-2 py-0.5 rounded-full"
                    >
                      🔧 {tc.name}
                    </span>
                  ))}
                </div>
              )}

              <span className="text-[9px] text-julius-muted px-1">
                {new Date(msg.timestamp).toLocaleTimeString()}
              </span>
            </div>
          </div>
        ))}

        {/* Thinking indicator */}
        {chatMut.isPending && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-julius-surface2 border border-julius-border flex items-center justify-center text-sm">
              🤖
            </div>
            <div className="bg-julius-surface border border-julius-border rounded-xl rounded-tl-none px-4 py-3">
              <div className="flex gap-1 items-center">
                <div
                  className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-bounce"
                  style={{ animationDelay: '0ms' }}
                />
                <div
                  className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-bounce"
                  style={{ animationDelay: '150ms' }}
                />
                <div
                  className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-bounce"
                  style={{ animationDelay: '300ms' }}
                />
                <span className="text-[10px] text-julius-muted ml-2">
                  JULIUS is thinking...
                </span>
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Quick commands */}
      <div className="px-6 py-2 border-t border-julius-border">
        <div className="flex gap-2 overflow-x-auto pb-1">
          {quickCommands.map((cmd, i) => (
            <button
              key={i}
              onClick={() => setInput(cmd)}
              className="text-[10px] whitespace-nowrap bg-julius-surface border border-julius-border text-julius-muted hover:text-julius-text px-3 py-1 rounded-full transition-colors flex-shrink-0"
            >
              {cmd}
            </button>
          ))}
        </div>
      </div>

      {/* Input */}
      <div className="px-6 py-4 border-t border-julius-border bg-julius-surface">
        <div className="flex gap-3 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask JULIUS anything... (Enter to send, Shift+Enter for new line)"
            rows={2}
            className="flex-1 bg-julius-bg border border-julius-border rounded-xl px-4 py-3 text-xs text-julius-text placeholder:text-julius-muted focus:outline-none focus:border-blue-400 resize-none"
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || chatMut.isPending}
            className="bg-blue-500 text-white px-4 py-3 rounded-xl text-sm font-semibold disabled:opacity-40 hover:opacity-90 transition-opacity flex-shrink-0"
          >
            {chatMut.isPending ? '...' : '➤'}
          </button>
        </div>
        <p className="text-[9px] text-julius-muted mt-2 text-center">
          JULIUS AI has access to all platform modules — scanner, exploits,
          identity, dark web, behavioral analysis
        </p>
      </div>
    </div>
  )
}
