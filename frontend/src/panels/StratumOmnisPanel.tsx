import { useQuery } from '@tanstack/react-query'
import { stratum } from '../lib/api'

type Layer = {
  layer_id: string
  title: string
  primary_technology: string
  function: string
  implementation_status: string
  safety_mode: string
  implementation_notes: string
}

type SignalSource = {
  source_id: string
  name: string
  category: string
  collection_mechanism: string
  implementation_status: string
  safety_mode: string
  notes: string
}

type BlueprintPayload = {
  mode: string
  source_documents: string[]
  doc_alignment: {
    strategy: string
    guardrails: string[]
  }
  layers: Layer[]
  signal_sources: SignalSource[]
  next_build_targets: string[]
}

type RuntimePayload = {
  stats: {
    total_identities: number
    total_events: number
    stratum_profiles: number
    source_breakdown: Record<string, number>
    implemented_signal_sources: number
    stubbed_signal_sources: number
  }
  runtime: {
    active_layers: string[]
    recent_jobs: Array<{
      job_id: string
      status: string
      collected_profiles: number
      source_counts?: Record<string, number>
      updated_at?: string
    }>
    latest_profiles: Array<{
      stratum_id?: string
      identity_anchors?: { handle?: string; platform?: string }
      metadata?: { source?: string; collection_date?: string }
    }>
  }
}

type FeatureStorePayload = {
  summary: {
    avg_activity_score: number
    avg_risk_numeric: number
  }
  features: Array<{
    stratum_id: string
    handle: string
    platform: string
    source: string
    feature_vector: {
      activity_score: number
      contribution_score: number
      followers: number
      public_repos: number
      risk_numeric: number
    }
  }>
}

type OraclePayload = {
  predictions: Array<{
    stratum_id: string
    handle: string
    platform: string
    predictions: {
      ['24h']: { action: string; confidence: number; domain: string }
    }
  }>
}

type CsiePayload = {
  classifications: Array<{
    stratum_id: string
    semantic_objects: string[]
    morphisms: string[]
  }>
}

type StreamProcessingPayload = {
  synthetic_stream_count: number
  source_counts: Record<string, number>
  synthetic_event_types: Record<string, number>
}

type IdentityResolutionPayload = {
  unique_identity_anchors: number
  platform_distribution: Record<string, number>
  resolved_identities: Array<{
    anchor: string
    count: number
    resolution_confidence: number
  }>
}

type ModelHubPayload = {
  registry: Array<{
    model_id: string
    family: string
    status: string
    records: number
  }>
}

function statusTone(status: string) {
  if (status === 'implemented') return 'text-emerald-300 bg-emerald-500/10 border-emerald-500/20'
  if (status === 'partial') return 'text-cyan-300 bg-cyan-500/10 border-cyan-500/20'
  if (status === 'scaffolded') return 'text-amber-300 bg-amber-500/10 border-amber-500/20'
  return 'text-red-300 bg-red-500/10 border-red-500/20'
}

export function StratumOmnisPanel() {
  const { data: blueprintData, isLoading: blueprintLoading, error: blueprintError } = useQuery({
    queryKey: ['stratum-blueprint'],
    queryFn: stratum.blueprint,
    staleTime: 60000,
  })
  const { data: runtimeData } = useQuery({
    queryKey: ['stratum-runtime'],
    queryFn: stratum.runtime,
    refetchInterval: 15000,
    staleTime: 10000,
  })
  const { data: featureData } = useQuery({
    queryKey: ['stratum-feature-store'],
    queryFn: () => stratum.featureStore(12),
    refetchInterval: 20000,
    staleTime: 15000,
  })
  const { data: oracleData } = useQuery({
    queryKey: ['stratum-oracle'],
    queryFn: () => stratum.oracle(8),
    refetchInterval: 20000,
    staleTime: 15000,
  })
  const { data: csieData } = useQuery({
    queryKey: ['stratum-csie'],
    queryFn: () => stratum.csie(8),
    refetchInterval: 20000,
    staleTime: 15000,
  })
  const { data: streamData } = useQuery({
    queryKey: ['stratum-stream-processing'],
    queryFn: () => stratum.streamProcessing(40),
    refetchInterval: 20000,
    staleTime: 15000,
  })
  const { data: identityData } = useQuery({
    queryKey: ['stratum-identity-resolution'],
    queryFn: () => stratum.identityResolution(80),
    refetchInterval: 20000,
    staleTime: 15000,
  })
  const { data: modelHubData } = useQuery({
    queryKey: ['stratum-model-hub'],
    queryFn: stratum.modelHub,
    refetchInterval: 20000,
    staleTime: 15000,
  })

  const blueprint = blueprintData as BlueprintPayload | undefined
  const runtime = runtimeData as RuntimePayload | undefined
  const featureStore = featureData as FeatureStorePayload | undefined
  const oracle = oracleData as OraclePayload | undefined
  const csie = csieData as CsiePayload | undefined
  const streamProcessing = streamData as StreamProcessingPayload | undefined
  const identityResolution = identityData as IdentityResolutionPayload | undefined
  const modelHub = modelHubData as ModelHubPayload | undefined

  if (blueprintLoading) {
    return <div className="flex h-full items-center justify-center text-sm text-julius-muted">Loading STRATUM blueprint...</div>
  }

  if (blueprintError || !blueprint) {
    return <div className="flex h-full items-center justify-center text-sm text-red-300">Unable to load STRATUM blueprint.</div>
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <section
          className="rounded-[28px] border border-julius-border p-6"
          style={{
            background:
              'radial-gradient(circle at 0% 0%, rgba(245,158,11,0.18), transparent 28%), radial-gradient(circle at 100% 0%, rgba(34,197,94,0.14), transparent 24%), linear-gradient(135deg, rgba(16,21,35,0.98), rgba(10,14,26,0.98))',
          }}
        >
          <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
            <div className="space-y-4">
              <div className="inline-flex rounded-full border border-amber-400/20 bg-amber-400/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.28em] text-amber-300">
                STRATUM OMNIS Alignment
              </div>
              <div>
                <h1 className="text-3xl font-black tracking-[0.08em] text-julius-text">Architecture Blueprint</h1>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-julius-muted">
                  JULIUS now follows the document architecture as a safe scaffold: same layer boundaries, same signal
                  taxonomy, and explicit status for what is implemented, partial, scaffolded, or intentionally disabled.
                </p>
              </div>
              <div className="rounded-2xl border border-julius-border bg-black/20 p-4">
                <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">Source Documents</div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {blueprint.source_documents.map((doc) => (
                    <span key={doc} className="rounded-full border border-julius-border bg-julius-bg px-3 py-1 text-xs text-julius-text">
                      {doc}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-julius-border bg-black/20 p-5">
              <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">Runtime Snapshot</div>
              <div className="mt-4 grid grid-cols-2 gap-4">
                <MetricCard label="STRATUM Profiles" value={runtime?.stats.stratum_profiles ?? 0} accent="text-cyan-300" />
                <MetricCard label="Events" value={runtime?.stats.total_events ?? 0} accent="text-emerald-300" />
                <MetricCard label="Live Sources" value={runtime?.stats.implemented_signal_sources ?? 0} accent="text-amber-300" />
                <MetricCard label="Stubbed Sources" value={runtime?.stats.stubbed_signal_sources ?? 0} accent="text-red-300" />
              </div>
              <div className="mt-4 rounded-2xl border border-julius-border bg-julius-bg p-4">
                <div className="text-[10px] uppercase tracking-[0.24em] text-julius-muted">Strategy</div>
                <div className="mt-2 text-sm text-julius-text">{blueprint.doc_alignment.strategy}</div>
                <div className="mt-3 space-y-2 text-sm text-julius-muted">
                  {blueprint.doc_alignment.guardrails.map((item) => (
                    <div key={item}>{item}</div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-julius-border bg-julius-surface p-5">
            <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">Nine Layers</div>
            <div className="mt-4 space-y-3">
              {blueprint.layers.map((layer) => (
                <div key={layer.layer_id} className="rounded-2xl border border-julius-border bg-julius-bg p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-xs font-semibold tracking-[0.12em] text-julius-accent">
                        {layer.layer_id} {layer.title}
                      </div>
                      <div className="mt-1 text-sm text-julius-text">{layer.function}</div>
                    </div>
                    <span className={`rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] ${statusTone(layer.implementation_status)}`}>
                      {layer.implementation_status}
                    </span>
                  </div>
                  <div className="mt-3 text-xs text-julius-muted">{layer.primary_technology}</div>
                  <div className="mt-2 text-xs leading-5 text-julius-muted">{layer.implementation_notes}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-julius-border bg-julius-surface p-5">
            <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">Signal Sources</div>
            <div className="mt-4 space-y-3">
              {blueprint.signal_sources.map((source) => (
                <div key={source.source_id} className="rounded-2xl border border-julius-border bg-julius-bg p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-julius-text">{source.name}</div>
                      <div className="mt-1 text-[11px] uppercase tracking-[0.2em] text-julius-muted">{source.category}</div>
                    </div>
                    <span className={`rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] ${statusTone(source.implementation_status)}`}>
                      {source.implementation_status}
                    </span>
                  </div>
                  <div className="mt-3 text-xs text-julius-muted">{source.collection_mechanism}</div>
                  <div className="mt-2 text-xs leading-5 text-julius-muted">{source.notes}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="grid gap-4 lg:grid-cols-[1fr_1fr]">
          <div className="rounded-2xl border border-julius-border bg-julius-surface p-5">
            <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">Recent Collection Jobs</div>
            <div className="mt-4 space-y-3">
              {(runtime?.runtime.recent_jobs ?? []).map((job) => (
                <div key={job.job_id} className="rounded-2xl border border-julius-border bg-julius-bg p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-mono text-xs text-julius-accent">{job.job_id}</div>
                    <span className="rounded-full border border-julius-border px-3 py-1 text-[10px] uppercase tracking-[0.2em] text-julius-text">
                      {job.status}
                    </span>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-3 text-xs text-julius-muted">
                    <div>Profiles: {job.collected_profiles.toLocaleString()}</div>
                    <div>Updated: {job.updated_at ? new Date(job.updated_at).toLocaleString() : '-'}</div>
                  </div>
                </div>
              ))}
              {!(runtime?.runtime.recent_jobs ?? []).length && (
                <div className="rounded-2xl border border-dashed border-julius-border p-4 text-sm text-julius-muted">
                  No STRATUM jobs captured yet.
                </div>
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-julius-border bg-julius-surface p-5">
            <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">Next Build Targets</div>
            <div className="mt-4 space-y-3">
              {blueprint.next_build_targets.map((item) => (
                <div key={item} className="rounded-2xl border border-julius-border bg-julius-bg p-4 text-sm leading-6 text-julius-text">
                  {item}
                </div>
              ))}
              <div className="rounded-2xl border border-cyan-500/20 bg-cyan-500/8 p-4">
                <div className="text-[10px] uppercase tracking-[0.24em] text-cyan-300">Active Layer Set</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {(runtime?.runtime.active_layers ?? []).map((id) => (
                    <span key={id} className="rounded-full border border-cyan-500/20 bg-cyan-500/10 px-3 py-1 text-xs text-cyan-200">
                      {id}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-4 lg:grid-cols-3">
          <div className="rounded-2xl border border-julius-border bg-julius-surface p-5">
            <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">Feature Store</div>
            <div className="mt-4 grid gap-3 grid-cols-2">
              <MetricCard
                label="Avg Activity"
                value={Math.round(featureStore?.summary.avg_activity_score ?? 0)}
                accent="text-cyan-300"
              />
              <MetricCard
                label="Avg Risk"
                value={Math.round(featureStore?.summary.avg_risk_numeric ?? 0)}
                accent="text-amber-300"
              />
            </div>
            <div className="mt-4 space-y-2">
              {(featureStore?.features ?? []).slice(0, 4).map((row) => (
                <div key={row.stratum_id} className="rounded-2xl border border-julius-border bg-julius-bg p-3">
                  <div className="font-mono text-xs text-julius-accent">{row.handle}</div>
                  <div className="mt-1 text-[11px] text-julius-muted">
                    {row.platform} · activity {row.feature_vector.activity_score} · risk {row.feature_vector.risk_numeric}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-julius-border bg-julius-surface p-5">
            <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">ORACLE Preview</div>
            <div className="mt-4 space-y-3">
              {(oracle?.predictions ?? []).slice(0, 4).map((row) => (
                <div key={row.stratum_id} className="rounded-2xl border border-julius-border bg-julius-bg p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-mono text-xs text-julius-accent">{row.handle}</div>
                    <div className="text-[10px] uppercase tracking-[0.2em] text-julius-muted">{row.predictions['24h'].domain}</div>
                  </div>
                  <div className="mt-2 text-sm text-julius-text">{row.predictions['24h'].action}</div>
                  <div className="mt-1 text-[11px] text-julius-muted">
                    Confidence {(row.predictions['24h'].confidence * 100).toFixed(0)}%
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-julius-border bg-julius-surface p-5">
            <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">CSIE Semantics</div>
            <div className="mt-4 space-y-3">
              {(csie?.classifications ?? []).slice(0, 4).map((row) => (
                <div key={row.stratum_id} className="rounded-2xl border border-julius-border bg-julius-bg p-3">
                  <div className="font-mono text-xs text-julius-accent">{row.stratum_id}</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {row.semantic_objects.map((item) => (
                      <span key={item} className="rounded-full border border-cyan-500/20 bg-cyan-500/10 px-2 py-1 text-[10px] text-cyan-200">
                        {item}
                      </span>
                    ))}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {row.morphisms.map((item) => (
                      <span key={item} className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-200">
                        {item}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="grid gap-4 lg:grid-cols-3">
          <div className="rounded-2xl border border-julius-border bg-julius-surface p-5">
            <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">Stream Processing</div>
            <div className="mt-4 grid gap-3 grid-cols-2">
              <MetricCard
                label="Stream Events"
                value={streamProcessing?.synthetic_stream_count ?? 0}
                accent="text-cyan-300"
              />
              <MetricCard
                label="Source Buckets"
                value={Object.keys(streamProcessing?.source_counts ?? {}).length}
                accent="text-emerald-300"
              />
            </div>
            <div className="mt-4 space-y-2">
              {Object.entries(streamProcessing?.synthetic_event_types ?? {}).slice(0, 4).map(([eventType, count]) => (
                <div key={eventType} className="rounded-2xl border border-julius-border bg-julius-bg p-3 text-sm text-julius-text">
                  <div className="font-mono text-xs text-julius-accent">{eventType}</div>
                  <div className="mt-1 text-[11px] text-julius-muted">{count} normalized events</div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-julius-border bg-julius-surface p-5">
            <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">Identity Resolution</div>
            <div className="mt-4 grid gap-3 grid-cols-2">
              <MetricCard
                label="Anchors"
                value={identityResolution?.unique_identity_anchors ?? 0}
                accent="text-amber-300"
              />
              <MetricCard
                label="Platforms"
                value={Object.keys(identityResolution?.platform_distribution ?? {}).length}
                accent="text-cyan-300"
              />
            </div>
            <div className="mt-4 space-y-2">
              {(identityResolution?.resolved_identities ?? []).slice(0, 4).map((row) => (
                <div key={row.anchor} className="rounded-2xl border border-julius-border bg-julius-bg p-3">
                  <div className="font-mono text-xs text-julius-accent">{row.anchor}</div>
                  <div className="mt-1 text-[11px] text-julius-muted">
                    {row.count} profile(s) · confidence {(row.resolution_confidence * 100).toFixed(0)}%
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-julius-border bg-julius-surface p-5">
            <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">Model Hub Registry</div>
            <div className="mt-4 space-y-3">
              {(modelHub?.registry ?? []).map((model) => (
                <div key={model.model_id} className="rounded-2xl border border-julius-border bg-julius-bg p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-mono text-xs text-julius-accent">{model.model_id}</div>
                    <div className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-emerald-200">
                      {model.status}
                    </div>
                  </div>
                  <div className="mt-1 text-[11px] text-julius-muted">
                    {model.family} · {model.records} records
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

function MetricCard({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <div className="rounded-2xl border border-julius-border bg-julius-bg p-4">
      <div className="text-[10px] uppercase tracking-[0.24em] text-julius-muted">{label}</div>
      <div className={`mt-2 text-2xl font-bold font-mono ${accent}`}>{value.toLocaleString()}</div>
    </div>
  )
}
