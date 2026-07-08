import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { system, network, auth } from '../lib/api'

type Tab = 'system' | 'network' | 'users'

interface AllowRangeRow {
  cidr: string
  label: string
  added_by?: string
}

interface UserRow {
  id: string | number
  username: string
  email?: string
  role: string
  totp_enabled?: boolean
  last_login?: string
}

type HealthPayload = {
  version?: string
  status?: string
  uptime_seconds?: number
  details?: Record<string, string>
}

type NetInfoPayload = {
  service?: string
  version?: string
  authorization?: { total_ranges?: number }
  constraints?: { security?: string[] }
}

export function SettingsPanel() {
  const [tab, setTab] = useState<Tab>('system')
  const qc = useQueryClient()
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: system.health, refetchInterval: 15000 })
  const { data: netInfo } = useQuery({ queryKey: ['net-info'], queryFn: network.info })
  const { data: allowlist } = useQuery({ queryKey: ['allowlist'], queryFn: network.allowlist })
  const { data: usersData } = useQuery({ queryKey: ['users'], queryFn: () => auth.status().then(() => fetch('/api/auth/users', { headers: { Authorization: `Bearer ${localStorage.getItem('julius_token')}` } }).then(r => r.json())), enabled: tab === 'users' })

  const [newCidr, setNewCidr] = useState('')
  const [newLabel, setNewLabel] = useState('')

  const addRangeMut = useMutation({
    mutationFn: () => fetch('/api/network/allowlist/add', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cidr: newCidr, label: newLabel }) }).then(r => r.json()),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['allowlist'] }); qc.invalidateQueries({ queryKey: ['net-info'] }); setNewCidr(''); setNewLabel('') },
  })

  const removeRangeMut = useMutation({
    mutationFn: (cidr: string) => fetch('/api/network/allowlist/remove', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cidr }) }).then(r => r.json()),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['allowlist'] }); qc.invalidateQueries({ queryKey: ['net-info'] }) },
  })

  const healthTyped = health as HealthPayload | undefined
  const netTyped = netInfo as NetInfoPayload | undefined

  const ranges = (allowlist as { authorized_ranges?: AllowRangeRow[] } | undefined)?.authorized_ranges ?? []
  const users: UserRow[] = Array.isArray(usersData) ? (usersData as UserRow[]) : []

  const tabs: { id: Tab; label: string }[] = [
    { id: 'system', label: 'System' },
    { id: 'network', label: 'Network' },
    { id: 'users', label: 'Users' },
  ]

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">
      <h1 className="text-xl font-bold tracking-wide">Settings & Diagnostics</h1>

      {/* Tab bar */}
      <div className="flex gap-1 bg-julius-surface border border-julius-border rounded-lg p-1">
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex-1 text-xs py-2 rounded-md transition-colors ${tab === t.id ? 'bg-julius-accent/20 text-julius-accent font-semibold' : 'text-julius-muted hover:text-julius-text'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'system' && (
        <>
          <div className="bg-julius-surface border border-julius-border rounded-xl p-5">
            <h3 className="text-sm font-semibold mb-4">System Information</h3>
            <div className="grid grid-cols-2 gap-x-8 gap-y-2">
              <Row label="Platform" value="JULIUS" />
              <Row label="Version" value={healthTyped?.version || '-'} />
              <Row label="Status" value={healthTyped?.status === 'healthy' ? 'OPERATIONAL' : 'DEGRADED'} color={healthTyped?.status === 'healthy' ? 'text-julius-green' : 'text-julius-red'} />
              <Row label="Uptime" value={healthTyped?.uptime_seconds ? `${Math.round(healthTyped.uptime_seconds)}s` : '-'} />
            </div>
          </div>
          <div className="bg-julius-surface border border-julius-border rounded-xl p-5">
            <h3 className="text-sm font-semibold mb-4">Subsystem Health</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {Object.entries(healthTyped?.details || {}).map(([k, v]) => (
                <div key={k} className="bg-julius-bg border border-julius-border rounded-lg p-3 text-center">
                  <div className="text-[10px] text-julius-muted uppercase tracking-wider mb-1">{k.replace(/_/g, ' ')}</div>
                  <div className={`text-xs font-mono ${v === 'operational' ? 'text-julius-green' : 'text-julius-red'}`}>{v as string}</div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {tab === 'network' && (
        <>
          <div className="bg-julius-surface border border-julius-border rounded-xl p-5">
            <h3 className="text-sm font-semibold mb-4">Network Monitor</h3>
            <div className="space-y-2">
              <Row label="Service" value={netTyped?.service || '-'} />
              <Row label="Version" value={netTyped?.version || '-'} />
              <Row label="Authorized Ranges" value={String(netTyped?.authorization?.total_ranges ?? 0)} />
            </div>
          </div>
          <div className="bg-julius-surface border border-julius-border rounded-xl p-5">
            <h3 className="text-sm font-semibold mb-4">Allowlist Management</h3>
            <div className="flex gap-3 mb-4">
              <input value={newCidr} onChange={e => setNewCidr(e.target.value)} placeholder="CIDR (e.g., 10.0.0.0/8)" className="flex-1 bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs text-julius-text focus:outline-none" />
              <input value={newLabel} onChange={e => setNewLabel(e.target.value)} placeholder="Label" className="flex-1 bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs text-julius-text focus:outline-none" />
              <button onClick={() => addRangeMut.mutate()} disabled={!newCidr || !newLabel}
                className="text-xs bg-julius-accent text-white px-4 py-2 rounded disabled:opacity-40">Add</button>
            </div>
            <div className="space-y-1">
              {ranges.map((r: AllowRangeRow, i: number) => (
                <div key={i} className="flex items-center gap-3 text-xs py-2 border-b border-julius-border/20 group">
                  <span className="w-2 h-2 bg-julius-green rounded-full" />
                  <span className="font-mono text-julius-accent flex-1">{r.cidr}</span>
                  <span className="text-julius-muted">{r.label}</span>
                  <span className="text-[10px] text-julius-muted">{r.added_by}</span>
                  <button onClick={() => removeRangeMut.mutate(r.cidr)} className="opacity-0 group-hover:opacity-100 text-julius-muted hover:text-julius-red text-xs">✕</button>
                </div>
              ))}
            </div>
          </div>
          {netTyped?.constraints?.security && (
            <div className="bg-julius-surface border border-julius-border rounded-xl p-5">
              <h3 className="text-sm font-semibold mb-4">Security Controls</h3>
              <div className="space-y-1">
                {netTyped.constraints.security.map((s: string, i: number) => (
                  <div key={i} className="flex items-center gap-2 text-xs text-julius-muted py-0.5">
                    <span className="text-julius-green">✓</span><span>{s}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {tab === 'users' && (
        <div className="bg-julius-surface border border-julius-border rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-4">User Management</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-julius-muted text-left border-b border-julius-border">
                  <th className="pb-2 px-2">ID</th>
                  <th className="pb-2 px-2">Username</th>
                  <th className="pb-2 px-2">Email</th>
                  <th className="pb-2 px-2">Role</th>
                  <th className="pb-2 px-2">MFA</th>
                  <th className="pb-2 px-2">Last Login</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u: UserRow) => (
                  <tr key={u.id} className="border-b border-julius-border/30 hover:bg-julius-surface2">
                    <td className="py-2 px-2 font-mono text-julius-muted">{u.id}</td>
                    <td className="py-2 px-2 text-julius-text font-semibold">{u.username}</td>
                    <td className="py-2 px-2 text-julius-muted font-mono">{u.email || '-'}</td>
                    <td className="py-2 px-2"><span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${u.role === 'admin' ? 'bg-julius-accent/20 text-julius-accent' : 'bg-julius-surface2 text-julius-muted'}`}>{u.role}</span></td>
                    <td className="py-2 px-2"><span className={u.totp_enabled ? 'text-julius-green' : 'text-julius-muted'}>{u.totp_enabled ? 'Enabled' : 'Off'}</span></td>
                    <td className="py-2 px-2 text-julius-muted font-mono text-[10px]">{u.last_login ? new Date(u.last_login).toLocaleString() : 'Never'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {users.length === 0 && <div className="text-xs text-julius-muted text-center py-6">No users found.</div>}
          </div>
        </div>
      )}
    </div>
  )
}

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-julius-border/20">
      <span className="text-xs text-julius-muted">{label}</span>
      <span className={`text-xs font-mono ${color || 'text-julius-text'}`}>{value}</span>
    </div>
  )
}
