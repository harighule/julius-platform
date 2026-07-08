import { useCallback, useState } from 'react'

export interface PantheonPolicyRow {
  policy_key: string
  min_role: string
  enabled: boolean
  description?: string | null
}

const ROLE_OPTIONS = ['read_only', 'user', 'operator', 'auditor', 'admin', 'superadmin'] as const

function policyRowTestId(policyKey: string) {
  return `pantheon-policy-row-${encodeURIComponent(policyKey)}`
}

function PolicyRowEditor({
  row,
  canEdit,
  onSave,
  busy,
}: {
  row: PantheonPolicyRow
  canEdit: boolean
  onSave: (policyKey: string, body: { min_role: string; enabled: boolean; description: string }) => Promise<void>
  busy: boolean
}) {
  const [minRole, setMinRole] = useState(row.min_role)
  const [enabled, setEnabled] = useState(row.enabled)
  const [description, setDescription] = useState(row.description ?? '')

  const handleSave = useCallback(async () => {
    await onSave(row.policy_key, {
      min_role: minRole,
      enabled,
      description,
    })
  }, [row.policy_key, minRole, enabled, description, onSave])

  if (!canEdit) {
    return (
      <tr data-testid={policyRowTestId(row.policy_key)} className="border-t border-julius-border">
        <td className="px-4 py-2 font-mono">{row.policy_key}</td>
        <td className="px-4 py-2 uppercase">{row.min_role}</td>
        <td className="px-4 py-2">{row.enabled ? 'yes' : 'no'}</td>
        <td className="px-4 py-2 text-julius-muted max-w-[200px] truncate" title={row.description ?? ''}>
          {row.description ?? '—'}
        </td>
      </tr>
    )
  }

  return (
    <tr data-testid={policyRowTestId(row.policy_key)} className="border-t border-julius-border">
      <td className="px-4 py-2 font-mono align-top">{row.policy_key}</td>
      <td className="px-4 py-2 align-top">
        <select
          value={minRole}
          onChange={e => setMinRole(e.target.value)}
          className="bg-julius-bg border border-julius-border rounded px-2 py-1 text-xs uppercase max-w-[140px]"
          aria-label={`Min role for ${row.policy_key}`}
        >
          {ROLE_OPTIONS.map(r => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </td>
      <td className="px-4 py-2 align-top">
        <label className="flex items-center gap-1 cursor-pointer">
          <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />
          <span className="text-julius-muted">on</span>
        </label>
      </td>
      <td className="px-4 py-2 align-top">
        <input
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder="Note"
          className="w-full max-w-[180px] bg-julius-bg border border-julius-border rounded px-2 py-1 text-xs"
        />
      </td>
      <td className="px-4 py-2 align-top">
        <button
          type="button"
          disabled={busy}
          onClick={() => void handleSave()}
          className="text-xs bg-julius-accent text-white px-2 py-1 rounded disabled:opacity-40"
        >
          Save
        </button>
      </td>
    </tr>
  )
}

export interface PantheonAccessPolicySectionProps {
  policies: PantheonPolicyRow[]
  status: 'pending' | 'error' | 'success'
  errorMessage?: string | null
  canEdit: boolean
  onSavePolicy?: (policyKey: string, body: { min_role: string; enabled: boolean; description: string }) => Promise<void>
  savingPolicyKey?: string | null
}

export function PantheonAccessPolicySection({
  policies,
  status,
  errorMessage,
  canEdit,
  onSavePolicy,
  savingPolicyKey,
}: PantheonAccessPolicySectionProps) {
  return (
    <section className="border border-julius-border bg-julius-surface rounded" data-testid="pantheon-policy-section">
      <div className="px-4 py-3 border-b border-julius-border text-sm font-semibold">Access policy (database)</div>
      <div className="max-h-[280px] overflow-auto">
        {status === 'pending' ? (
          <div className="px-4 py-3 text-sm text-julius-muted" data-testid="pantheon-policy-loading">
            Loading access policy…
          </div>
        ) : null}
        {status === 'error' ? (
          <div className="px-4 py-3 text-sm text-red-400/90" data-testid="pantheon-policy-error">
            {errorMessage ?? 'Could not load access policy.'}
          </div>
        ) : null}
        {status === 'success' && policies.length === 0 ? (
          <div className="px-4 py-3 text-sm text-julius-muted" data-testid="pantheon-policy-empty">
            No policy rows.
          </div>
        ) : null}
        {status === 'success' && policies.length > 0 ? (
          <table className="w-full text-xs" data-testid="pantheon-policy-table">
            <thead className="text-left text-julius-muted">
              <tr>
                <th className="px-4 py-2">Policy key</th>
                <th className="px-4 py-2">Min role</th>
                <th className="px-4 py-2">On</th>
                <th className="px-4 py-2">Description</th>
                {canEdit ? <th className="px-4 py-2">Actions</th> : null}
              </tr>
            </thead>
            <tbody>
              {policies.map(p => (
                <PolicyRowEditor
                  key={`${p.policy_key}|${p.min_role}|${p.enabled}|${p.description ?? ''}`}
                  row={p}
                  canEdit={canEdit && Boolean(onSavePolicy)}
                  onSave={onSavePolicy ?? (async () => {})}
                  busy={savingPolicyKey === p.policy_key}
                />
              ))}
            </tbody>
          </table>
        ) : null}
      </div>
      {!canEdit && status === 'success' && policies.length > 0 ? (
        <div className="px-4 py-2 text-[11px] text-julius-muted border-t border-julius-border">
          Policy edits require an admin or superadmin account.
        </div>
      ) : null}
    </section>
  )
}
