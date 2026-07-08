import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getTransactions } from '../api/guardian'
import type { Transaction } from '../api/guardian'

const PAGE_SIZE = 20

const STATUS_STYLE: Record<string, string> = {
  confirmed:  'text-julius-green border-julius-green/30 bg-julius-green/10',
  pending:    'text-julius-amber border-julius-amber/30 bg-julius-amber/10',
  failed:     'text-julius-red   border-julius-red/30   bg-julius-red/10',
  processing: 'text-julius-accent border-julius-accent/30 bg-julius-accent/10',
}

function fmtBytes(b: number) {
  if (b >= 1e9) return `${(b / 1e9).toFixed(2)} GB`
  if (b >= 1e6) return `${(b / 1e6).toFixed(2)} MB`
  if (b >= 1e3) return `${(b / 1e3).toFixed(1)} KB`
  return `${b} B`
}

function fmtTime(ts: string) {
  try {
    return new Date(ts).toLocaleString(undefined, {
      month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    })
  } catch { return ts }
}

export function TransactionsTable() {
  const [page, setPage] = useState(1)
  const [nodeFilter, setNodeFilter] = useState('')
  const [debouncedFilter, setDebouncedFilter] = useState('')

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['guardian-txns', page, debouncedFilter],
    queryFn: () => getTransactions(page, PAGE_SIZE, debouncedFilter || undefined),
    refetchInterval: 30_000,
    placeholderData: (prev) => prev,
  })

  const handleFilterChange = (v: string) => {
    setNodeFilter(v)
    clearTimeout((handleFilterChange as any)._t)
    ;(handleFilterChange as any)._t = setTimeout(() => {
      setDebouncedFilter(v)
      setPage(1)
    }, 400)
  }

  const txns: Transaction[] = data?.transactions ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="flex flex-col gap-3">
      {/* Filter bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-julius-muted text-[10px] font-mono">▶</span>
          <input
            id="txn-node-filter"
            type="text"
            placeholder="FILTER_BY_NODE_ID..."
            value={nodeFilter}
            onChange={e => handleFilterChange(e.target.value)}
            className="w-full pl-6 pr-3 py-1.5 bg-julius-surface border border-julius-border text-julius-text text-[11px] font-mono tracking-wider placeholder:text-julius-muted/50 focus:outline-none focus:border-julius-accent/60 transition-colors"
          />
        </div>
        <div className="text-[9px] font-mono text-julius-muted tracking-widest">
          {total.toLocaleString()} RECORDS
        </div>
        {isFetching && (
          <div className="flex gap-0.5">
            {[0, 1, 2].map(i => (
              <div key={i} className="w-0.5 h-3 bg-julius-accent animate-pulse" style={{ animationDelay: `${i * 100}ms` }} />
            ))}
          </div>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto border border-julius-border">
        <table className="w-full text-[10px] font-mono">
          <thead>
            <tr className="border-b border-julius-border bg-julius-surface2">
              {['TIMESTAMP', 'NODE_ID', 'BYTES_ROUTED', 'COMMISSION', 'STATUS'].map(h => (
                <th key={h} className="text-left px-3 py-2 text-[8px] font-black tracking-[0.2em] text-julius-muted border-r border-julius-border last:border-0">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? Array.from({ length: 8 }).map((_, i) => (
                  <tr key={`skel-${i}`} className="border-b border-julius-border/50">
                    {[1, 2, 3, 4, 5].map(j => (
                      <td key={j} className="px-3 py-2">
                        <div className="h-3 bg-julius-surface2 animate-pulse rounded" style={{ width: `${50 + j * 10}%` }} />
                      </td>
                    ))}
                  </tr>
                ))
              : txns.length > 0
                ? txns.map((txn) => (
                    <tr
                      key={txn.transaction_id}
                      className="border-b border-julius-border/40 hover:bg-julius-surface2 transition-colors group"
                    >
                      <td className="px-3 py-2 text-julius-muted whitespace-nowrap">
                        {fmtTime(txn.timestamp)}
                      </td>
                      <td className="px-3 py-2 text-julius-accent font-bold truncate max-w-[120px]" title={txn.node_id}>
                        {txn.node_id}
                      </td>
                      <td className="px-3 py-2 text-julius-text">
                        {fmtBytes(txn.bytes_routed ?? 0)}
                      </td>
                      <td className="px-3 py-2 text-julius-green font-bold">
                        ${(txn.commission ?? 0).toFixed(4)}
                      </td>
                      <td className="px-3 py-2">
                        <span className={`px-1.5 py-0.5 border text-[8px] font-black tracking-[0.2em] ${STATUS_STYLE[txn.status ?? ''] ?? 'text-julius-muted border-julius-border'}`}>
                          {(txn.status ?? 'unknown').toUpperCase()}
                        </span>
                      </td>
                    </tr>
                  ))
                : [
                    <tr key="empty">
                      <td colSpan={5} className="px-3 py-8 text-center text-julius-muted tracking-widest">
                        NO_TRANSACTIONS_FOUND
                      </td>
                    </tr>,
                  ]
            }
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between text-[9px] font-mono text-julius-muted">
        <span>PAGE {page} / {totalPages}</span>
        <div className="flex gap-2">
          <button
            id="txn-prev-page"
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="px-3 py-1 border border-julius-border hover:border-julius-accent/60 hover:text-julius-accent disabled:opacity-30 disabled:cursor-not-allowed transition-colors tracking-widest"
          >
            ◀ PREV
          </button>
          <button
            id="txn-next-page"
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="px-3 py-1 border border-julius-border hover:border-julius-accent/60 hover:text-julius-accent disabled:opacity-30 disabled:cursor-not-allowed transition-colors tracking-widest"
          >
            NEXT ▶
          </button>
        </div>
      </div>
    </div>
  )
}
