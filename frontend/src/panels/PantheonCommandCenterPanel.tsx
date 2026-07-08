import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../auth/useAuth'
import { PantheonAccessPolicySection } from '../components/PantheonAccessPolicySection'
import { pantheon } from '../lib/api'

interface PantheonModuleRow {
  module_id: string
  name: string
  tier: string
  status: string
  feature_flag: string
}

interface PantheonEventRow {
  event_id: string
  event_type: string
  module: string
  entity_id: string
  timestamp: string
  actor_username?: string | null
  client_ip?: string | null
}

interface ModuleHealthProbe {
  status: 'ok' | 'degraded' | 'unknown'
  latency_ms: number
  detail: string
}

interface ModuleHealthRow {
  module_id: string
  name: string
  tier: string
  contract_status: string
  feature_flag: string
  enabled: boolean
  health: 'live' | 'standby' | 'planned'
  probe: ModuleHealthProbe
}

function healthChipClass(health: ModuleHealthRow['health']) {
  if (health === 'live') return 'border-emerald-500/40 text-emerald-300/95 bg-emerald-950/30'
  if (health === 'standby') return 'border-amber-500/40 text-amber-200/95 bg-amber-950/25'
  return 'border-julius-border text-julius-muted bg-julius-bg/80'
}

export function PantheonCommandCenterPanel() {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)
  const modules = useQuery({
    queryKey: ['pantheon-modules'],
    queryFn: pantheon.modules,
    refetchInterval: 30000,
  })

  const moduleHealth = useQuery({
    queryKey: ['pantheon-module-health'],
    queryFn: pantheon.modulesHealth,
    refetchInterval: 45000,
  })

  const conditionRegistry = useQuery({
    queryKey: ['pantheon-condition-registry'],
    queryFn: pantheon.conditionRegistry,
    refetchInterval: 120000,
  })

  const taxonReceipts = useQuery({
    queryKey: ['pantheon-taxon-receipts'],
    queryFn: () => pantheon.taxonReceipts(15),
    refetchInterval: 60000,
  })

  const events = useQuery({
    queryKey: ['pantheon-events'],
    queryFn: () => pantheon.events(25),
    refetchInterval: 5000,
  })

  const eventIdsForIntegrity = useMemo(
    () =>
      (events.data as { items?: PantheonEventRow[] } | undefined)?.items
        ?.map((e) => e.event_id)
        .filter(Boolean)
        .slice(0, 25) ?? [],
    [events.data],
  )

  const integrityBatch = useQuery({
    queryKey: ['pantheon-events-integrity-batch', eventIdsForIntegrity.join('|')],
    queryFn: () => pantheon.verifyEventsIntegrity(eventIdsForIntegrity),
    enabled: eventIdsForIntegrity.length > 0 && !events.isLoading,
    staleTime: 15000,
    refetchInterval: 20000,
  })

  const integrityByEventId = useMemo(() => {
    const rows =
      (
        integrityBatch.data as
          | { items?: { event_id?: string; integrity_valid?: boolean; reason?: string }[] }
          | undefined
      )?.items ?? []
    const m = new Map<string, 'ok' | 'bad' | 'missing'>()
    for (const r of rows) {
      const id = r.event_id
      if (!id) continue
      if (r.reason === 'not_found') m.set(id, 'missing')
      else if (r.integrity_valid === true) m.set(id, 'ok')
      else m.set(id, 'bad')
    }
    return m
  }, [integrityBatch.data])

  const eventDetailQuery = useQuery({
    queryKey: ['pantheon-event-detail', selectedEventId],
    queryFn: () => pantheon.eventById(selectedEventId as string),
    enabled: Boolean(selectedEventId),
  })

  useEffect(() => {
    if (!selectedEventId) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelectedEventId(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selectedEventId])

  const audit = useQuery({
    queryKey: ['pantheon-audit-verify'],
    queryFn: pantheon.verifyAudit,
    refetchInterval: 15000,
  })
  const root = useQuery({
    queryKey: ['pantheon-audit-root-latest'],
    queryFn: pantheon.latestAuditRoot,
    refetchInterval: 15000,
  })

  const auditRecent = useQuery({
    queryKey: ['pantheon-audit-recent'],
    queryFn: () => pantheon.auditRecent(12),
    refetchInterval: 20000,
  })

  const accessPolicy = useQuery({
    queryKey: ['pantheon-access-policy'],
    queryFn: pantheon.accessPolicy,
    refetchInterval: 60000,
  })

  const savePolicyMutation = useMutation({
    mutationFn: ({
      policyKey,
      body,
    }: {
      policyKey: string
      body: { min_role: string; enabled: boolean; description: string }
    }) => pantheon.updateAccessPolicy(policyKey, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['pantheon-access-policy'] })
    },
  })

  const canEditAccessPolicy = Boolean(
    user && ['admin', 'superadmin'].includes(String(user.role).toLowerCase()),
  )

  const policySectionStatus = accessPolicy.isError
    ? 'error'
    : accessPolicy.isLoading
      ? 'pending'
      : 'success'
  const policyItemsForSection = !accessPolicy.isError
    ? ((accessPolicy.data as { items?: { policy_key: string; min_role: string; enabled: boolean; description?: string | null }[] } | undefined)
        ?.items ?? [])
    : []
  const policyErrorMessage =
    accessPolicy.error instanceof Error ? accessPolicy.error.message : 'Could not load access policy.'

  const items = (modules.data as { items?: PantheonModuleRow[] } | undefined)?.items ?? []
  const recentEvents = (events.data as { items?: PantheonEventRow[] } | undefined)?.items ?? []
  const auditStatus = audit.data as { valid?: boolean; records?: number } | undefined
  const auditTail =
    (auditRecent.data as { items?: { seq?: number; event_type?: string; entity_id?: string; record_hash?: string }[] } | undefined)
      ?.items ?? []
  const rootData = root.data as { latest?: { root_hash?: string } } | undefined
  const healthPayload = moduleHealth.data as
    | {
        summary?: {
          live?: number
          standby?: number
          planned?: number
          total?: number
          probe_ok?: number
          probe_degraded?: number
          probe_unknown?: number
        }
        modules?: ModuleHealthRow[]
      }
    | undefined
  const healthModules = healthPayload?.modules ?? []
  const healthSummary = healthPayload?.summary

  const registryItems =
    (conditionRegistry.data as { items?: { code: string; title: string; implemented?: boolean }[] } | undefined)
      ?.items ?? []

  const taxReceiptRows =
    (taxonReceipts.data as { items?: { payment_id?: string; receipt_hash?: string; tax_amount?: number }[] } | undefined)
      ?.items ?? []

  const sampleConditionRun = useQuery({
    queryKey: ['pantheon-sample-conditions'],
    queryFn: () =>
      pantheon.evaluateConditions({
        payment: {
          payment_id: 'sample-001',
          amount: 1500,
          risk_score: 0.35,
          beneficiary_id: 'beneficiary-1',
        },
        conditions: [
          { code: 'MAX_AMOUNT', config: { threshold: 2500 } },
          { code: 'RISK_SCORE', config: { max_score: 0.6 } },
          { code: 'BENEFICIARY_ALLOWLIST', config: { allowlist: ['beneficiary-1', 'beneficiary-2'] } },
        ],
      }),
    enabled: false,
  })

  const sampleTaxRun = useQuery({
    queryKey: ['pantheon-sample-taxon'],
    queryFn: () =>
      pantheon.computeTax({
        payment_id: 'sample-001',
        payment_type: 'VENDOR_PAYMENT',
        gross_amount: 10000,
        category_code: 'CONTRACTOR',
      }),
    enabled: false,
  })

  const sampleDryRun = useQuery({
    queryKey: ['pantheon-conditions-dry-run'],
    queryFn: () =>
      pantheon.conditionsDryRun({
        code: 'MIN_PAYMENT',
        payment: { amount: 250, gross_amount: 250 },
        config: { minimum: 100 },
      }),
    enabled: false,
  })

  const canDryRunConditions = Boolean(
    user && ['admin', 'superadmin', 'auditor'].includes(String(user.role).toLowerCase()),
  )

  return (
    <div className="p-6 space-y-6 text-julius-text">
      <div>
        <h1 className="text-xl font-bold tracking-wide">PANTHEON Command Center</h1>
        <p className="text-sm text-julius-muted mt-1">
          Control plane: module registry, live health probes, NEXUS dry-run, event stream, PRISM chain (including TAXON
          receipt mirrors), and DB-backed access policy.
        </p>
      </div>

      <section className="border border-julius-border bg-julius-surface rounded" data-testid="pantheon-module-health-section">
        <div className="px-4 py-3 border-b border-julius-border flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm font-semibold">Module health (PR-4)</span>
          {moduleHealth.isLoading ? (
            <span className="text-xs text-julius-muted">Loading…</span>
          ) : null}
          {moduleHealth.isError ? (
            <span className="text-xs text-red-400/90">Health unavailable</span>
          ) : null}
          {healthSummary != null ? (
            <span className="text-xs text-julius-muted font-mono">
              flags: live {healthSummary.live ?? 0} · standby {healthSummary.standby ?? 0} · planned{' '}
              {healthSummary.planned ?? 0} / {healthSummary.total ?? 0}
              {' · '}
              probes: ok {healthSummary.probe_ok ?? 0} · deg {healthSummary.probe_degraded ?? 0} · unk{' '}
              {healthSummary.probe_unknown ?? 0}
            </span>
          ) : null}
        </div>
        {healthModules.length > 0 ? (
          <div className="max-h-[140px] overflow-auto p-3 flex flex-wrap gap-1.5">
            {healthModules.map((m: ModuleHealthRow) => (
              <span
                key={m.module_id}
                title={`${m.feature_flag} · ${m.contract_status}\n${m.probe?.detail ?? ''}`}
                className={`text-[10px] px-2 py-0.5 rounded border font-mono ${healthChipClass(m.health)} ${
                  m.probe?.status === 'degraded' ? 'ring-1 ring-red-500/35' : ''
                }`}
              >
                {m.name}: {m.health}
                {m.probe ? ` · ${m.probe.status}` : ''}
              </span>
            ))}
          </div>
        ) : null}
      </section>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="border border-julius-border bg-julius-surface rounded p-4">
          <div className="text-xs uppercase tracking-wider text-julius-muted">Modules</div>
          <div className="text-2xl font-bold mt-2">{items.length}</div>
        </div>
        <div className="border border-julius-border bg-julius-surface rounded p-4">
          <div className="text-xs uppercase tracking-wider text-julius-muted">Recent Events</div>
          <div className="text-2xl font-bold mt-2">{recentEvents.length}</div>
        </div>
        <div className="border border-julius-border bg-julius-surface rounded p-4">
          <div className="text-xs uppercase tracking-wider text-julius-muted">Audit Chain</div>
          <div className="text-2xl font-bold mt-2">
            {auditStatus?.valid ? 'Valid' : 'Pending'}
          </div>
          <div className="text-[11px] mt-2 text-julius-muted">
            Records: {auditStatus?.records != null ? String(auditStatus.records) : '—'} · root:{' '}
            {rootData?.latest?.root_hash ? `${String(rootData.latest.root_hash).slice(0, 16)}...` : 'n/a'}
          </div>
          {auditRecent.isError ? (
            <div className="text-[10px] mt-2 text-julius-muted">Recent entries need auditor (or higher).</div>
          ) : auditTail.length > 0 ? (
            <ul className="text-[10px] font-mono mt-2 space-y-0.5 text-julius-muted max-h-[72px] overflow-hidden">
              {auditTail.slice(0, 6).map((r) => (
                <li key={`${r.seq}-${r.record_hash ?? ''}`} className="truncate" title={r.event_type}>
                  {r.event_type ?? '?'} · {r.entity_id ?? '?'} ·{' '}
                  {r.record_hash ? `${String(r.record_hash).slice(0, 10)}…` : '—'}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </section>

      <section className="border border-julius-border bg-julius-surface rounded p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm font-semibold">NEXUS condition registry</div>
          {canDryRunConditions ? (
            <button
              type="button"
              className="text-xs px-2 py-1 rounded border border-julius-border hover:border-julius-accent text-julius-muted"
              onClick={() => void sampleDryRun.refetch()}
            >
              Dry-run MIN_PAYMENT
            </button>
          ) : null}
        </div>
        {conditionRegistry.isError ? (
          <div className="text-xs text-julius-muted">Registry unavailable.</div>
        ) : conditionRegistry.isLoading ? (
          <div className="text-xs text-julius-muted">Loading registry…</div>
        ) : (
          <ul className="text-xs space-y-1 font-mono text-julius-muted max-h-[120px] overflow-auto">
            {registryItems.map((c) => (
              <li key={c.code}>
                <span className="text-julius-text">{c.code}</span>
                {' — '}
                <span className="text-julius-muted">{c.title}</span>
              </li>
            ))}
          </ul>
        )}
        {sampleDryRun.data != null ? (
          <pre className="text-[11px] bg-black/30 p-3 rounded overflow-auto text-julius-muted">
            {JSON.stringify(sampleDryRun.data, null, 2)}
          </pre>
        ) : null}
      </section>

      <section className="border border-julius-border bg-julius-surface rounded p-4 space-y-2">
        <div className="text-sm font-semibold">TAXON receipts</div>
        <p className="text-[11px] text-julius-muted">
          New computes append <span className="font-mono text-julius-text/80">taxon.receipt.mirror</span> to the PRISM
          audit chain (idempotent replays do not duplicate).
        </p>
        {taxonReceipts.isError ? (
          <div className="text-xs text-julius-muted">Receipts unavailable.</div>
        ) : taxonReceipts.isLoading ? (
          <div className="text-xs text-julius-muted">Loading receipts…</div>
        ) : taxReceiptRows.length === 0 ? (
          <div className="text-xs text-julius-muted">No tax computations recorded yet.</div>
        ) : (
          <ul className="text-[11px] font-mono space-y-1 max-h-[100px] overflow-auto text-julius-muted">
            {taxReceiptRows.map((r) => (
              <li key={String(r.payment_id) + String(r.receipt_hash)}>
                {r.payment_id ?? '?'} · tax {String(r.tax_amount ?? '—')} ·{' '}
                <span className="text-julius-text/80">{r.receipt_hash ? `${String(r.receipt_hash).slice(0, 12)}…` : '—'}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="border border-julius-border bg-julius-surface rounded p-4 space-y-3">
        <div className="text-sm font-semibold">Phase 2 Sandbox (NEXUS + TAXON)</div>
        <div className="flex flex-wrap gap-3">
          <button
            className="px-3 py-2 text-sm rounded border border-julius-border hover:border-julius-accent"
            onClick={() => pantheon.snapshotAudit().then(() => root.refetch())}
          >
            Snapshot Audit Root
          </button>
          <button
            className="px-3 py-2 text-sm rounded border border-julius-border hover:border-julius-accent"
            onClick={() => sampleConditionRun.refetch()}
          >
            Run Condition Evaluation
          </button>
          <button
            className="px-3 py-2 text-sm rounded border border-julius-border hover:border-julius-accent"
            onClick={() => sampleTaxRun.refetch()}
          >
            Run Tax Compute
          </button>
        </div>
        {sampleConditionRun.data != null ? (
          <pre className="text-xs bg-black/30 p-3 rounded overflow-auto">{JSON.stringify(sampleConditionRun.data, null, 2)}</pre>
        ) : null}
        {sampleTaxRun.data != null ? (
          <pre className="text-xs bg-black/30 p-3 rounded overflow-auto">{JSON.stringify(sampleTaxRun.data, null, 2)}</pre>
        ) : null}
      </section>

      <section className="border border-julius-border bg-julius-surface rounded">
        <div className="px-4 py-3 border-b border-julius-border text-sm font-semibold">Module Registry</div>
        <div className="max-h-[320px] overflow-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-julius-muted">
              <tr>
                <th className="px-4 py-2">Module</th>
                <th className="px-4 py-2">Tier</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Feature Flag</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item: PantheonModuleRow) => (
                <tr key={item.module_id} className="border-t border-julius-border">
                  <td className="px-4 py-2">{item.name}</td>
                  <td className="px-4 py-2 uppercase">{item.tier}</td>
                  <td className="px-4 py-2 uppercase">{item.status}</td>
                  <td className="px-4 py-2 font-mono text-xs">{item.feature_flag}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="space-y-2">
        <PantheonAccessPolicySection
          policies={policyItemsForSection}
          status={policySectionStatus}
          errorMessage={policyErrorMessage}
          canEdit={canEditAccessPolicy}
          onSavePolicy={
            canEditAccessPolicy
              ? async (policyKey, body) => {
                  await savePolicyMutation.mutateAsync({ policyKey, body })
                }
              : undefined
          }
          savingPolicyKey={
            savePolicyMutation.isPending && savePolicyMutation.variables
              ? savePolicyMutation.variables.policyKey
              : null
          }
        />
        {savePolicyMutation.isError ? (
          <div className="text-xs text-red-400/90 px-1" data-testid="pantheon-policy-save-error">
            {savePolicyMutation.error instanceof Error
              ? savePolicyMutation.error.message
              : 'Policy update failed'}
          </div>
        ) : null}
      </div>

      <section className="border border-julius-border bg-julius-surface rounded">
        <div className="px-4 py-3 border-b border-julius-border flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm font-semibold">Recent Event Timeline</span>
          <span className="text-[10px] text-julius-muted font-mono">
            integrity: batch · top {Math.min(25, recentEvents.length)} rows · click row for detail
          </span>
        </div>
        <div className="max-h-[260px] overflow-auto divide-y divide-julius-border">
          {recentEvents.length === 0 && (
            <div className="px-4 py-3 text-sm text-julius-muted">No events published yet.</div>
          )}
          {recentEvents.map((event: PantheonEventRow) => {
            const ig = integrityByEventId.get(event.event_id)
            const igLabel =
              ig === 'ok'
                ? 'SHA row OK'
                : ig === 'bad'
                  ? 'hash mismatch or empty'
                  : ig === 'missing'
                    ? 'not found'
                    : integrityBatch.isFetching
                      ? '…'
                      : '—'
            return (
              <div
                key={event.event_id}
                role="button"
                tabIndex={0}
                className="px-4 py-3 flex gap-3 items-start cursor-pointer hover:bg-black/15 border-l-2 border-transparent hover:border-julius-accent/25 outline-none focus-visible:ring-1 focus-visible:ring-julius-accent/40"
                onClick={() => setSelectedEventId(event.event_id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    setSelectedEventId(event.event_id)
                  }
                }}
              >
                <div
                  className="mt-0.5 shrink-0 w-7 text-center text-xs font-mono pointer-events-none"
                  title={igLabel}
                  aria-label={igLabel}
                >
                  {ig === 'ok' ? (
                    <span className="text-emerald-400/95">✓</span>
                  ) : ig === 'bad' ? (
                    <span className="text-amber-400/95">!</span>
                  ) : ig === 'missing' ? (
                    <span className="text-julius-muted">?</span>
                  ) : integrityBatch.isFetching ? (
                    <span className="text-julius-muted animate-pulse">…</span>
                  ) : (
                    <span className="text-julius-muted">·</span>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold">{event.event_type}</div>
                  <div className="text-xs text-julius-muted mt-1">
                    {event.module} · {event.entity_id} · {event.timestamp}
                    {event.actor_username != null && event.actor_username !== '' ? (
                      <> · actor: {event.actor_username}</>
                    ) : null}
                    {event.client_ip != null && event.client_ip !== '' ? <> · {event.client_ip}</> : null}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {selectedEventId ? (
        <div
          className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center bg-black/55 p-3 sm:p-6"
          onClick={() => setSelectedEventId(null)}
          role="presentation"
        >
          <div
            className="w-full max-w-2xl max-h-[88vh] flex flex-col rounded border border-julius-border bg-julius-surface shadow-xl"
            onClick={(e) => e.stopPropagation()}
            data-testid="pantheon-event-detail-drawer"
          >
            <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-julius-border shrink-0">
              <div className="min-w-0">
                <div className="text-sm font-semibold truncate">Event detail</div>
                <div className="text-[11px] font-mono text-julius-muted truncate">{selectedEventId}</div>
              </div>
              <button
                type="button"
                className="shrink-0 px-2 py-1 text-xs rounded border border-julius-border hover:border-julius-accent text-julius-muted"
                onClick={() => setSelectedEventId(null)}
              >
                Close
              </button>
            </div>
            <div className="overflow-auto flex-1 p-4">
              {eventDetailQuery.isLoading ? (
                <div className="text-sm text-julius-muted">Loading…</div>
              ) : eventDetailQuery.isError ? (
                <div className="text-sm text-red-400/90">
                  {eventDetailQuery.error instanceof Error
                    ? eventDetailQuery.error.message
                    : 'Could not load event.'}
                </div>
              ) : (
                <pre className="text-[11px] font-mono text-julius-muted whitespace-pre-wrap break-all">
                  {JSON.stringify(
                    (eventDetailQuery.data as { event?: Record<string, unknown> } | undefined)?.event ?? {},
                    null,
                    2,
                  )}
                </pre>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

