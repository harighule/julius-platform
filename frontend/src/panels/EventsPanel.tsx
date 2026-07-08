import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { events } from '../lib/api'

interface BusEvent {
  id: string | number
  event_type: string
  source: string
  data: unknown
  timestamp: string
}

export function EventsPanel() {
  const qc = useQueryClient()
  const { data: eventsData } = useQuery({ queryKey: ['events'], queryFn: () => events.recent(200), refetchInterval: 5000 })
  const { data: statsRaw } = useQuery({ queryKey: ['event-stats'], queryFn: events.stats, refetchInterval: 10000 })
  const stats = statsRaw as { total_events?: number; event_types?: Record<string, number> } | undefined

  const [showPublish, setShowPublish] = useState(false)
  const [form, setForm] = useState({ event_type: 'custom', source: 'julius-ui', data: '{}' })
  const [filterType, setFilterType] = useState('')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<BusEvent | null>(null)

  const publishMut = useMutation({
    mutationFn: () => {
      let parsed: Record<string, unknown> = {}
      try {
        parsed = JSON.parse(form.data) as Record<string, unknown>
      } catch {
        void 0
      }
      return events.publish(form.event_type, form.source, parsed)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['events'] }); qc.invalidateQueries({ queryKey: ['event-stats'] }); setShowPublish(false); setForm({ event_type: 'custom', source: 'julius-ui', data: '{}' }) },
  })

  const allEvts = (eventsData as { events?: BusEvent[] } | undefined)?.events ?? []
  const types = stats?.event_types ?? {}

  const filtered = allEvts.filter((e: BusEvent) => {
    if (filterType && e.event_type !== filterType) return false
    if (search) {
      const s = search.toLowerCase()
      const str = `${e.event_type} ${e.source} ${JSON.stringify(e.data)}`.toLowerCase()
      if (!str.includes(s)) return false
    }
    return true
  })

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold tracking-wide">Event Bus</h1>
        <button onClick={() => setShowPublish(!showPublish)}
          className="text-xs bg-julius-accent/20 text-julius-accent px-3 py-1.5 rounded hover:bg-julius-accent/30">
          {showPublish ? 'Cancel' : '+ Publish Event'}
        </button>
      </div>

      {showPublish && (
        <div className="bg-julius-surface border border-julius-border rounded-xl p-4 space-y-3">
          <h3 className="text-sm font-semibold">Publish New Event</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[10px] text-julius-muted uppercase mb-1">Event Type</label>
              <select value={form.event_type} onChange={e => setForm(f => ({ ...f, event_type: e.target.value }))}
                className="w-full bg-julius-bg border border-julius-border rounded px-2 py-1.5 text-xs text-julius-text">
                <option value="custom">custom</option>
                <option value="scan_complete">scan_complete</option>
                <option value="exploit_result">exploit_result</option>
                <option value="behavioral_alert">behavioral_alert</option>
                <option value="identity_match">identity_match</option>
                <option value="system_event">system_event</option>
              </select>
            </div>
            <div>
              <label className="block text-[10px] text-julius-muted uppercase mb-1">Source</label>
              <input value={form.source} onChange={e => setForm(f => ({ ...f, source: e.target.value }))}
                className="w-full bg-julius-bg border border-julius-border rounded px-2 py-1.5 text-xs text-julius-text focus:outline-none" />
            </div>
          </div>
          <div>
            <label className="block text-[10px] text-julius-muted uppercase mb-1">Payload (JSON)</label>
            <textarea value={form.data} onChange={e => setForm(f => ({ ...f, data: e.target.value }))} rows={3}
              className="w-full bg-julius-bg border border-julius-border rounded px-2 py-1.5 text-xs font-mono text-julius-text focus:outline-none" />
          </div>
          <button onClick={() => publishMut.mutate()} disabled={publishMut.isPending}
            className="bg-julius-accent hover:bg-julius-accent/90 disabled:opacity-40 text-white px-4 py-1.5 rounded text-xs">
            Publish
          </button>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-julius-surface border border-julius-border rounded-xl p-4 text-center">
          <div className="text-[10px] text-julius-muted uppercase mb-1">Total Events</div>
          <div className="text-2xl font-bold font-mono text-julius-accent">{stats?.total_events ?? 0}</div>
        </div>
        <div className="bg-julius-surface border border-julius-border rounded-xl p-4 text-center">
          <div className="text-[10px] text-julius-muted uppercase mb-1">Event Types</div>
          <div className="text-2xl font-bold font-mono text-julius-green">{Object.keys(types).length}</div>
        </div>
        <div className="bg-julius-surface border border-julius-border rounded-xl p-4 text-center col-span-2">
          <div className="text-[10px] text-julius-muted uppercase mb-2">Type Distribution</div>
          <div className="flex flex-wrap gap-2 justify-center">
            {Object.entries(types).map(([t, c]) => (
              <button key={t} onClick={() => setFilterType(filterType === t ? '' : t)}
                className={`text-[10px] border rounded px-2 py-0.5 transition-colors ${filterType === t ? 'bg-julius-accent/20 border-julius-accent text-julius-accent' : 'bg-julius-bg border-julius-border'}`}>
                <span className="text-julius-accent">{t}</span>: <span className="font-mono">{c as number}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex gap-3">
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search events..."
          className="flex-1 bg-julius-surface border border-julius-border rounded-lg px-3 py-2 text-xs text-julius-text focus:outline-none" />
        {(filterType || search) && (
          <button onClick={() => { setFilterType(''); setSearch('') }} className="text-xs text-julius-muted hover:text-julius-text px-2">Clear</button>
        )}
      </div>

      {/* Event stream + detail */}
      <div className="flex gap-6">
        <div className={`bg-julius-surface border border-julius-border rounded-xl p-4 ${selected ? 'flex-1' : 'w-full'}`}>
          <h3 className="text-sm font-semibold mb-3">Live Event Stream ({filtered.length})</h3>
          <div className="space-y-1 max-h-[500px] overflow-y-auto">
            {filtered.map((e: BusEvent) => (
              <div key={e.id} onClick={() => setSelected(e)}
                className={`flex items-center gap-4 text-xs py-2 border-b border-julius-border/20 px-2 rounded cursor-pointer transition-colors ${selected?.id === e.id ? 'bg-julius-accent/10' : 'hover:bg-julius-surface2'}`}>
                <span className="text-[10px] font-mono text-julius-muted w-16 shrink-0">{String(e.id).split('_').pop()}</span>
                <span className="text-julius-accent font-mono w-36 truncate shrink-0">{e.event_type}</span>
                <span className="text-julius-muted w-28 truncate shrink-0">{e.source}</span>
                <span className="text-julius-text truncate flex-1">{typeof e.data === 'object' ? JSON.stringify(e.data).slice(0, 80) : String(e.data)}</span>
                <span className="text-[10px] text-julius-muted font-mono shrink-0">{new Date(e.timestamp).toLocaleTimeString()}</span>
              </div>
            ))}
            {filtered.length === 0 && <div className="text-xs text-julius-muted text-center py-8">No events match.</div>}
          </div>
        </div>

        {/* Detail panel */}
        {selected && (
          <div className="w-80 shrink-0 bg-julius-surface border border-julius-border rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold">Event Detail</h3>
              <button onClick={() => setSelected(null)} className="text-julius-muted hover:text-julius-text text-sm">✕</button>
            </div>
            <div className="space-y-3 text-xs">
              <Row label="ID" value={String(selected.id)} />
              <Row label="Type" value={selected.event_type} />
              <Row label="Source" value={selected.source} />
              <Row label="Time" value={new Date(selected.timestamp).toLocaleString()} />
              <div>
                <div className="text-[10px] text-julius-muted uppercase mb-1">Payload</div>
                <pre className="bg-julius-bg border border-julius-border rounded p-2 text-[10px] font-mono text-julius-text overflow-auto max-h-60 whitespace-pre-wrap">
                  {typeof selected.data === 'object' ? JSON.stringify(selected.data, null, 2) : String(selected.data)}
                </pre>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex justify-between border-b border-julius-border/20 pb-1">
      <span className="text-julius-muted">{label}</span>
      <span className="font-mono text-julius-text truncate ml-2">{String(value)}</span>
    </div>
  )
}
