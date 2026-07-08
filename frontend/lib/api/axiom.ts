/**
 * frontend/lib/api/axiom.ts
 *
 * Type-safe client for the AXIOM compression engine and
 * the unified intelligence pipeline.
 *
 * Usage:
 *   import { axiomApi, intelApi } from '@/lib/api/axiom'
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// ── Generic fetch helper ────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(`[${res.status}] ${path} — ${detail}`)
  }
  return res.json() as Promise<T>
}

// ── Types ───────────────────────────────────────────────────────────────────

export interface AxiomStatus {
  module: string
  state: string
  version: string
  capabilities: string[]
  pipeline_stages: number
  lossless_guarantee: boolean
}

export interface CompressionResult {
  original_params: number
  post_gauge_params: number | null
  post_null_params: number | null
  post_tt_params: number | null
  entropy_coding_ratio: number
  total_compression_ratio: number
  verified_lossless: boolean | null
  max_output_difference: number | null
  compression_modes_applied: string[]
}

export interface CompressionRequest {
  model_architecture?: 'mini_transformer' | 'custom'
  d_model?: number
  n_heads?: number
  verify_lossless?: boolean
  verbose?: boolean
}

export interface ScanFinding {
  scan_index: number
  target: string | null
  feature_rank: number
  null_dimension: number
  anomaly_score: number
  severity: 'critical' | 'high' | 'medium' | 'low'
  open_ports: number
  vulnerabilities: number
  axiom_flags: (string | null)[]
}

export interface PipelineResult {
  target: string | null
  depth: string
  axiom_findings: ScanFinding[]
  causal_graph: Record<string, unknown>
  causal_inferences: unknown[]
  summary: {
    total_targets_analysed: number
    severity_breakdown: Record<string, number>
    causal_paths_found: number
    osint_indicators: number
    pipeline_stages_completed: number
    recommendation: string
  }
}

export interface IntelAnalysisRequest {
  scan_results?: Record<string, unknown>[]
  osint_data?: Record<string, unknown>
  target?: string
  depth?: 'standard' | 'deep'
}

// ── AXIOM API ───────────────────────────────────────────────────────────────

export const axiomApi = {
  /** Health + capability summary */
  status: () =>
    apiFetch<AxiomStatus>('/api/axiom/status'),

  /** Full pipeline stage descriptions */
  capabilities: () =>
    apiFetch<unknown>('/api/axiom/capabilities'),

  /** Run compression on a named architecture */
  compress: (req: CompressionRequest = {}) =>
    apiFetch<CompressionResult>('/api/axiom/compress', {
      method: 'POST',
      body: JSON.stringify(req),
    }),

  /** Upload a .pt/.pth checkpoint for compression */
  compressUpload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return apiFetch<unknown>('/api/axiom/compress/upload', {
      method: 'POST',
      headers: {},        // let browser set multipart boundary
      body: form,
    })
  },

  /** Run live demo (mini transformer, fast) */
  demo: () =>
    apiFetch<CompressionResult & { demo: boolean; model: string }>('/api/axiom/demo', {
      method: 'POST',
    }),

  /** Static compression capability report */
  report: () =>
    apiFetch<unknown>('/api/axiom/report'),

  /**
   * Feed scanner/osint data through AXIOM algebraic analysis.
   * Usually you want intelApi.analyse() instead (runs both stages).
   */
  analysePipeline: (req: IntelAnalysisRequest) =>
    apiFetch<unknown>('/api/axiom/analyse/pipeline', {
      method: 'POST',
      body: JSON.stringify(req),
    }),
}

// ── Intelligence Pipeline API ───────────────────────────────────────────────

export const intelApi = {
  /** Full pipeline: scanner + osint → AXIOM → causal functor */
  analyse: (req: IntelAnalysisRequest) =>
    apiFetch<PipelineResult>('/api/intel/analyse', {
      method: 'POST',
      body: JSON.stringify(req),
    }),

  /** Pipeline health */
  status: () =>
    apiFetch<unknown>('/api/intel/status'),
}