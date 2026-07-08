import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'

type JobStatus =
  | 'running'
  | 'stopping'
  | 'stopped'
  | 'completed'
  | 'completed_partial'
  | 'failed'

interface SourceCounts {
  github?: number
  gitlab?: number
  npm?: number
  pypi?: number
  govuk?: number
  companies_house?: number
  gdelt?: number
  wikidata?: number
  opencorporates?: number
  hackertarget?: number
  ipinfo?: number
  shodan?: number
  whois?: number
  [source: string]: number | undefined
}

interface CollectionJobStatus {
  job_id: string
  status: JobStatus
  // The backend may return either a "STRATUM collector" shape or a minimal "active_jobs" shape.
  target_profiles?: number
  collected_profiles?: number
  stored_profiles?: number
  deduplicated_profiles?: number
  progress_percent?: number
  source_breakdown?: SourceCounts
  recent_errors?: string[]
  started_at?: string
  updated_at?: string
  completed_at?: string | null
  stop_requested?: boolean
  target_reached?: boolean
  // Minimal job status fields (active_jobs)
  progress?: number
  total?: number
  collected?: number
  sources?: Record<string, number>
}

interface ValidationReport {
  profiles_checked: number
  valid_profiles: number
  invalid_profiles: number
  validation_rate: number
  total_errors: number
  total_warnings: number
  synthetic_detected: number
}

interface ExportData {
  job_id: string
  export_timestamp: string
  profiles: any[]
  statistics: {
    total_profiles: number
    verified_people: number
    verified_organizations: number
    verification_rate: number
    source_distribution: SourceCounts
    duplicate_rate: number
    average_signal_strength: number
  }
  quality_report: ValidationReport
}

const JOB_KEY = 'julius_signal_collection_job'
const API_BASE = '/api/signals'

function isTerminal(status?: string) {
  return ['completed', 'completed_partial', 'failed', 'error', 'stopped'].includes(status || '')
}

function normalizeJob(raw?: CollectionJobStatus | null) {
  if (!raw) return null
  const collected = raw.collected_profiles ?? raw.collected ?? 0
  const target = raw.target_profiles ?? raw.total ?? 0
  const progress =
    raw.progress_percent ??
    (target > 0 ? Math.min(100, Math.round((Number(raw.progress ?? collected) / target) * 100)) : 0)
  return {
    ...raw,
    collected_profiles: collected,
    target_profiles: target,
    stored_profiles: raw.stored_profiles ?? collected,
    deduplicated_profiles: raw.deduplicated_profiles ?? collected,
    progress_percent: progress,
    source_breakdown: raw.source_breakdown ?? raw.sources ?? {},
  }
}

async function readApiError(res: Response, fallback: string) {
  try {
    const body = await res.json()
    if (typeof body?.detail === 'string') return body.detail
    if (Array.isArray(body?.detail)) return body.detail.map((d: { msg?: string }) => d.msg).join(', ')
  } catch {
    /* ignore */
  }
  return fallback
}

class HttpError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function SourceCard({ label, value, accent }: { label: string; value: number | undefined; accent: string }) {
  return (
    <div className="rounded-xl border border-julius-border bg-julius-surface p-4">
      <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">{label}</div>
      <div className="mt-2 text-2xl font-bold font-mono" style={{ color: accent }}>
        {(value || 0).toLocaleString()}
      </div>
    </div>
  )
}

export function SignalCollectionPanel() {
  const [jobId, setJobId] = useState(() => localStorage.getItem(JOB_KEY) || '')
  const [targetProfiles, setTargetProfiles] = useState('100000')
  const [message, setMessage] = useState('')
  const [exportData, setExportData] = useState<ExportData | null>(null)
  const [showValidation, setShowValidation] = useState(false)
  const [haltStatusPolling, setHaltStatusPolling] = useState(false)
  const [lastStatus, setLastStatus] = useState<JobStatus | ''>('')
  const failedPollAttemptsRef = useRef(0)

  useEffect(() => {
    failedPollAttemptsRef.current = 0
    setHaltStatusPolling(false)
    setLastStatus('')
  }, [jobId])

  useEffect(() => {
    if (jobId) {
      localStorage.setItem(JOB_KEY, jobId)
    } else {
      localStorage.removeItem(JOB_KEY)
    }
  }, [jobId])

  // Fetch job status
  const isRunning =
    !!jobId && !haltStatusPolling && !['completed', 'failed', 'error'].includes(lastStatus || '')

  const statusQuery = useQuery({
    queryKey: ['signal-status', jobId],
    queryFn: async () => {
      if (failedPollAttemptsRef.current >= 10) {
        setHaltStatusPolling(true)
        throw new Error('Status polling stopped after 10 attempts')
      }

      const res = await fetch(`/api/signals/status/${jobId}`)
      if (res.status === 404) throw new HttpError(404, `Job ${jobId} not found (404)`)
      if (!res.ok) throw new HttpError(res.status, await readApiError(res, `Failed to fetch status (${res.status})`))
      failedPollAttemptsRef.current = 0
      const data = (await res.json()) as CollectionJobStatus
      return normalizeJob(data) as CollectionJobStatus
    },
    enabled: !!jobId && isRunning, // Only poll when running
    refetchInterval: isRunning ? 3000 : false, // Stop when done
    retry: false, // Don't retry on 404
  })

  useEffect(() => {
    if (!statusQuery.data?.status) return
    setLastStatus(statusQuery.data.status)
  }, [statusQuery.data?.status])

  useEffect(() => {
    if (!statusQuery.error) return

    if (statusQuery.error instanceof HttpError && statusQuery.error.status === 404) {
      setHaltStatusPolling(true)
      setMessage(`✗ Status check failed: ${statusQuery.error.message}. Polling stopped.`)
      setJobId('')
      return
    }

    failedPollAttemptsRef.current += 1
    if (failedPollAttemptsRef.current >= 10) {
      setHaltStatusPolling(true)
      setMessage('✗ Status polling stopped after 10 attempts.')
    }
  }, [statusQuery.error])

  // Start collection
  const startMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${API_BASE}/collect/uk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_profiles: Math.max(1, Number(targetProfiles) || 100000) }),
      })
      if (!res.ok) throw new Error(await readApiError(res, 'Failed to start collection'))
      return res.json() as Promise<{ job_id: string; status: string; message?: string }>
    },
    onSuccess: (data) => {
      setHaltStatusPolling(false)
      failedPollAttemptsRef.current = 0
      setLastStatus('')
      setExportData(null)
      setJobId(data.job_id)
      setMessage(data.message ? `✓ ${data.message}` : `✓ Collection job ${data.job_id} started`)
    },
    onError: (error) => {
      setMessage(`✗ ${error instanceof Error ? error.message : 'Failed to start collection'}`)
    },
  })

  // Stop collection
  const stopMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${API_BASE}/stop/${jobId}`, { method: 'POST' })
      if (!res.ok) throw new Error('Failed to stop collection')
      return res.json()
    },
    onSuccess: () => {
      setMessage('✓ Stop request sent')
    },
    onError: (error) => {
      setMessage(`✗ ${error instanceof Error ? error.message : 'Failed to stop'}`)
    },
  })

  // Export collection
  const exportMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${API_BASE}/export/${jobId}`)
      if (!res.ok) throw new Error(await readApiError(res, 'Failed to export'))
      const data = (await res.json()) as ExportData
      setExportData(data)
      return data
    },
    onSuccess: (data) => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${jobId || 'uk-signals'}-export.json`
      link.click()
      URL.revokeObjectURL(url)
      setMessage(`✓ Exported ${data.statistics.total_profiles.toLocaleString()} profiles`)
    },
    onError: (error) => {
      setMessage(`✗ ${error instanceof Error ? error.message : 'Export failed'}`)
    },
  })

  const job = normalizeJob(statusQuery.data)
  const active = job && !isTerminal(job.status)

  useEffect(() => {
    if (!job || !isTerminal(job.status)) return
    if ((job.collected_profiles || 0) === 0) {
      setMessage('✗ Job completed with 0 profiles. Click Start Collection to run a new job.')
    }
  }, [job?.status, job?.collected_profiles])
  const rawSources = job?.source_breakdown ?? (job?.sources as SourceCounts | undefined) ?? {}
  const sourceCounts: SourceCounts = {
    github: rawSources.github,
    gitlab: rawSources.gitlab,
    npm: rawSources.npm,
    pypi: rawSources.pypi,
    govuk: rawSources.govuk,
    gdelt: rawSources.gdelt,
    companies_house: rawSources.companies_house,
    // UK collector uses spending_context / openstreetmap keys
    ...(rawSources as Record<string, number | undefined>),
  }
  const stats = exportData?.statistics

  const sourcesList = Object.entries(sourceCounts)
    .filter(([, v]) => (v ?? 0) > 0)
    .sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0))

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-7xl space-y-6">
        {/* Header */}
        <div
          className="overflow-hidden rounded-3xl border border-julius-border"
          style={{
            background:
              'radial-gradient(circle at top left, rgba(0,212,255,0.14), transparent 32%), linear-gradient(135deg, rgba(10,16,30,0.98), rgba(18,25,42,0.96))',
          }}
        >
          <div className="grid gap-6 p-6 lg:grid-cols-[1.25fr_0.95fr]">
            <div className="space-y-4">
              <div className="inline-flex rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-300">
                ⚡ Public Signal Collection (STRATUM)
              </div>
              <div>
                <h1 className="text-3xl font-black tracking-[0.08em] text-julius-text">Global Signal Intelligence</h1>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-julius-muted">
                  Production-grade STRATUM collection from 100,000+ real Global's entities. Profiles include entity resolution, 
                  behavioral intelligence, signal enrichment, and verification. All data from public sources only.
                </p>
              </div>
              <div className="rounded-2xl border border-green-400/20 bg-green-400/8 p-4 text-sm text-green-100">
                <div className="text-[10px] uppercase tracking-[0.28em] text-green-300">✓ Public Data Only</div>
                <div className="mt-2">
                  Safe mode enabled: GitHub, GitLab, npm, PyPI, GOV.UK, Companies House, GDELT, Wikidata, OpenCorporates.
                  No network scanning. No private data. All signals publicly verifiable.
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-julius-border bg-black/20 p-5 backdrop-blur">
              <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">Launch Controls</div>
              <div className="mt-4 grid gap-4">
                <label className="block">
                  <div className="mb-1 text-[10px] uppercase tracking-[0.24em] text-julius-muted">Target Profiles</div>
                  <input
                    type="number"
                    value={targetProfiles}
                    onChange={(e) => setTargetProfiles(e.target.value)}
                    className="w-full rounded-xl border border-julius-border bg-julius-bg px-3 py-2 text-sm text-julius-text outline-none"
                  />
                </label>

                <div className="flex flex-wrap gap-3">
                  <button
                    onClick={() => startMutation.mutate()}
                    disabled={startMutation.isPending || Boolean(active)}
                    className="rounded-xl bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Start Collection
                  </button>
                  <button
                    onClick={() => stopMutation.mutate()}
                    disabled={!jobId || stopMutation.isPending || !active}
                    className="rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 py-2 text-sm font-semibold text-amber-300 transition hover:bg-amber-500/15 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Stop
                  </button>
                  <button
                    onClick={() => exportMutation.mutate()}
                    disabled={!jobId || exportMutation.isPending}
                    className="rounded-xl border border-julius-border bg-julius-surface px-4 py-2 text-sm font-semibold text-julius-text transition hover:bg-julius-surface2 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Export + Report
                  </button>
                  <button
                    onClick={() => setShowValidation(!showValidation)}
                    className="rounded-xl border border-julius-border bg-julius-surface px-4 py-2 text-sm font-semibold text-julius-text transition hover:bg-julius-surface2"
                  >
                    {showValidation ? 'Hide' : 'Show'} Quality
                  </button>
                  <button
                    onClick={() => {
                      setJobId('')
                      setHaltStatusPolling(false)
                      setLastStatus('')
                      setExportData(null)
                      setMessage('✓ Cleared stale job. Start a new collection.')
                    }}
                    className="rounded-xl border border-red-400/30 bg-red-500/10 px-4 py-2 text-sm font-semibold text-red-300 transition hover:bg-red-500/15"
                  >
                    Clear Job
                  </button>
                </div>
                {message && <div className="text-xs text-cyan-300 font-mono">{message}</div>}
              </div>
            </div>
          </div>
        </div>

        {/* Status Cards */}
        <div className="grid gap-4 md:grid-cols-4">
          <div className="rounded-xl border border-julius-border bg-julius-surface p-4">
            <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">Job Status</div>
            <div className="mt-2 text-xl font-bold text-julius-text">{job?.status || 'Idle'}</div>
            <div className="mt-1 font-mono text-[11px] text-cyan-300">{job?.job_id || 'No active job'}</div>
          </div>
          <div className="rounded-xl border border-julius-border bg-julius-surface p-4">
            <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">Collected</div>
            <div className="mt-2 text-xl font-bold text-julius-text">
              {(job?.collected_profiles || 0).toLocaleString()}
            </div>
            <div className="mt-1 text-xs text-julius-muted">
              Target: {(job?.target_profiles || Number(targetProfiles) || 0).toLocaleString()}
            </div>
          </div>
          <div className="rounded-xl border border-julius-border bg-julius-surface p-4">
            <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">Unique</div>
            <div className="mt-2 text-xl font-bold text-green-400">
              {(job?.stored_profiles || 0).toLocaleString()}
            </div>
            <div className="mt-1 text-xs text-julius-muted">
              After dedup: {(job?.deduplicated_profiles || 0).toLocaleString()}
            </div>
          </div>
          <div className="rounded-xl border border-julius-border bg-julius-surface p-4">
            <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">Progress</div>
            <div className="mt-2 text-xl font-bold text-cyan-400">{job?.progress_percent ?? 0}%</div>
            <div className="mt-1 text-xs text-julius-muted">
              {job?.target_reached
                ? '✓ Target reached'
                : isTerminal(job?.status)
                  ? 'Finished'
                  : 'In progress...'}
            </div>
          </div>
        </div>

        {/* Quality Metrics */}
        {showValidation && stats && (
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-julius-border bg-julius-surface p-5">
              <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">🎯 Quality Report</div>
              <div className="mt-4 space-y-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-julius-muted">Total Profiles:</span>
                  <span className="font-bold text-julius-text">{stats.total_profiles.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-julius-muted">Verified People:</span>
                  <span className="font-bold text-green-400">{stats.verified_people.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-julius-muted">Verified Organizations:</span>
                  <span className="font-bold text-green-400">{stats.verified_organizations.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-julius-muted">Verification Rate:</span>
                  <span className="font-bold text-green-400">{stats.verification_rate.toFixed(1)}%</span>
                </div>
                <div className="flex justify-between border-t border-julius-border pt-3">
                  <span className="text-julius-muted">Duplicate Rate:</span>
                  <span className="font-bold text-amber-400">{stats.duplicate_rate.toFixed(1)}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-julius-muted">Avg Signal Strength:</span>
                  <span className="font-bold text-cyan-400">{stats.average_signal_strength.toFixed(0)}/100</span>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-julius-border bg-julius-surface p-5">
              <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">📊 Source Distribution</div>
              <div className="mt-4 space-y-2">
                {sourcesList.slice(0, 8).map(([source, count]) => (
                  <div key={source} className="flex justify-between">
                    <span className="text-xs text-julius-muted capitalize">{source}:</span>
                    <span className="font-mono text-xs text-cyan-300">{(count || 0).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Progress & Details */}
        <div className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="rounded-2xl border border-julius-border bg-julius-surface p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">Collection Progress</div>
                <div className="mt-1 text-lg font-semibold text-julius-text">
                  {job?.progress_percent ?? 0}% complete
                </div>
              </div>
              <div className="text-right text-xs text-julius-muted">
                <div>Started {job?.started_at ? new Date(job.started_at).toLocaleString() : '-'}</div>
                <div>Updated {job?.updated_at ? new Date(job.updated_at).toLocaleString() : '-'}</div>
              </div>
            </div>
            <div className="mt-4 h-4 overflow-hidden rounded-full bg-julius-bg">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${job?.progress_percent ?? 0}%`,
                  background: 'linear-gradient(90deg, #06b6d4 0%, #22c55e 100%)',
                }}
              />
            </div>

            <div className="mt-6 grid gap-4 sm:grid-cols-4">
              <SourceCard label="GitHub" value={sourceCounts.github} accent="#22c55e" />
              <SourceCard label="GitLab" value={sourceCounts.gitlab} accent="#fc6d26" />
              <SourceCard label="npm" value={sourceCounts.npm} accent="#cb3837" />
              <SourceCard label="PyPI" value={sourceCounts.pypi} accent="#3775a9" />
            </div>

            <div className="mt-4 grid gap-4 sm:grid-cols-4">
              <SourceCard label="GOV.UK" value={sourceCounts.govuk} accent="#0078d4" />
              <SourceCard label="Spending" value={(rawSources as Record<string, number>).spending_context} accent="#8b5cf6" />
              <SourceCard label="GDELT" value={sourceCounts.gdelt} accent="#f59e0b" />
              <SourceCard label="OpenStreetMap" value={(rawSources as Record<string, number>).openstreetmap} accent="#10b981" />
            </div>
          </div>

          <div className="rounded-2xl border border-julius-border bg-julius-surface p-5">
            <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">Recent Errors</div>
            <div className="mt-4 space-y-2 max-h-64 overflow-y-auto">
              {(job?.recent_errors || []).slice(0, 10).map((error, index) => (
                <div key={`${index}-${error}`} className="rounded-lg border border-red-500/20 bg-red-500/8 p-2 text-xs text-red-200 font-mono">
                  {error}
                </div>
              ))}
              {!job?.recent_errors?.length && (
                <div className="rounded-lg border border-dashed border-julius-border p-3 text-xs text-julius-muted">
                  No errors recorded ✓
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Info Box */}
        <div className="rounded-2xl border border-julius-border bg-julius-surface p-5">
          <div className="text-[10px] uppercase tracking-[0.28em] text-julius-muted">ℹ️ About STRATUM Collection</div>
          <div className="mt-3 grid gap-4 text-xs text-julius-muted leading-relaxed lg:grid-cols-3">
            <div>
              <div className="font-semibold text-julius-text mb-1">Entity Resolution</div>
              Canonical keys, cross-source matching, alias resolution, deduplication, confidence scoring.
            </div>
            <div>
              <div className="font-semibold text-julius-text mb-1">Signal Enrichment</div>
              Public social activity, digital patterns, spending context, source diversity, entity trust, behavioral patterns.
            </div>
            <div>
              <div className="font-semibold text-julius-text mb-1">Quality Validation</div>
              Schema validation, score ranges, provenance tracking, synthetic data detection, null density checks.
            </div>
          </div>
        </div>

        {statusQuery.error && (
          <div className="rounded-xl border border-red-500/20 bg-red-500/8 p-4 text-sm text-red-200">
            ✗ {statusQuery.error instanceof Error ? statusQuery.error.message : 'Unable to load job status'}
          </div>
        )}
      </div>
    </div>
  )
}

