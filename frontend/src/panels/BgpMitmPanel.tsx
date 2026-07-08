import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'

const BASE = '' // Vite proxies /api → backend

type Result = { loading: boolean; data: any; error: string | null }

function errMessage(e: unknown) {
  return e instanceof Error ? e.message : 'Request failed'
}

function hdr() {
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  const t = localStorage.getItem('julius_token')
  if (t) h['Authorization'] = `Bearer ${t}`
  return h
}

async function post<T = unknown>(url: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${url}`, { method: 'POST', headers: hdr(), body: JSON.stringify(body) })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return (await r.json()) as T
}

async function get<T = unknown>(url: string): Promise<T> {
  const r = await fetch(`${BASE}${url}`, { headers: hdr() })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return (await r.json()) as T
}

function InfoCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="bg-julius-surface border border-julius-border rounded-xl p-4 space-y-2">
      <div className="text-xs font-semibold text-julius-text">{title}</div>
      {children}
    </div>
  )
}

function ResultBox({ result }: { result: Result }) {
  if (result.loading) return <div className="text-[10px] text-julius-muted">Running...</div>
  if (result.error) return <div className="text-[10px] text-julius-red">{result.error}</div>
  if (!result.data) return null
  return (
    <pre className="text-[10px] font-mono bg-julius-bg border border-julius-border rounded p-3 max-h-72 overflow-auto">
      {JSON.stringify(result.data, null, 2)}
    </pre>
  )
}

export function BgpMitmPanel() {
  const [ipRange, setIpRange] = useState('192.168.1.0/24')
  const [target, setTarget] = useState('192.168.1.50')
  const [gateway, setGateway] = useState('192.168.1.1')
  const [interfaceName, setInterfaceName] = useState('eth0')
  const [timeout, setTimeout] = useState<number | ''>('')
  const [result, setResult] = useState<Result>({ loading: false, data: null, error: null })

  // ---- Wallet Query ----
  const { data: walletData, refetch: refetchWallet } = useQuery<{ address: string }>({
    queryKey: ['bgp-wallet'],
    queryFn: () => get('/api/bgp-mitm/wallet'),
    refetchInterval: 30000,
    retry: false,
  })

  // ---- Gateway ----
  const gatewayMut = useMutation({
    mutationFn: () => get('/api/bgp-mitm/gateway'),
    onMutate: () => setResult({ loading: true, data: null, error: null }),
    onSuccess: (data) => setResult({ loading: false, data, error: null }),
    onError: (e: unknown) => setResult({ loading: false, data: null, error: errMessage(e) }),
  })

  // ---- Scan ----
  const scanMut = useMutation({
    mutationFn: () => post('/api/bgp-mitm/scan', { ip_range: ipRange }),
    onMutate: () => setResult({ loading: true, data: null, error: null }),
    onSuccess: (data) => setResult({ loading: false, data, error: null }),
    onError: (e: unknown) => setResult({ loading: false, data: null, error: errMessage(e) }),
  })

  // ---- ARP Spoof ----
  const spoofMut = useMutation({
    mutationFn: () => post('/api/bgp-mitm/spoof', { target, gateway, interface: interfaceName }),
    onMutate: () => setResult({ loading: true, data: null, error: null }),
    onSuccess: (data) => setResult({ loading: false, data, error: null }),
    onError: (e: unknown) => setResult({ loading: false, data: null, error: errMessage(e) }),
  })

  // ---- Sniff ----
  const sniffMut = useMutation({
    mutationFn: () =>
      post('/api/bgp-mitm/sniff', {
        interface: interfaceName,
        timeout: timeout === '' ? undefined : timeout,
      }),
    onMutate: () => setResult({ loading: true, data: null, error: null }),
    onSuccess: (data) => setResult({ loading: false, data, error: null }),
    onError: (e: unknown) => setResult({ loading: false, data: null, error: errMessage(e) }),
  })

  // ---- Modify ----
  const modifyMut = useMutation({
    mutationFn: () => post('/api/bgp-mitm/modify', { interface: interfaceName, timeout: undefined }),
    onMutate: () => setResult({ loading: true, data: null, error: null }),
    onSuccess: (data) => setResult({ loading: false, data, error: null }),
    onError: (e: unknown) => setResult({ loading: false, data: null, error: errMessage(e) }),
  })

  // ---- BGP Simulate ----
  const bgpSimMut = useMutation({
    mutationFn: () => get('/api/bgp-mitm/simulate-bgp'),
    onMutate: () => setResult({ loading: true, data: null, error: null }),
    onSuccess: (data) => setResult({ loading: false, data, error: null }),
    onError: (e: unknown) => setResult({ loading: false, data: null, error: errMessage(e) }),
  })

  // ---- Full Attack ----
  const attackMut = useMutation({
    mutationFn: () => post('/api/bgp-mitm/attack', { target, gateway, interface: interfaceName }),
    onMutate: () => setResult({ loading: true, data: null, error: null }),
    onSuccess: (data) => setResult({ loading: false, data, error: null }),
    onError: (e: unknown) => setResult({ loading: false, data: null, error: errMessage(e) }),
  })

  // ---- Stop all ----
  const stopMut = useMutation({
    mutationFn: () => post('/api/bgp-mitm/stop', {}),
    onMutate: () => setResult({ loading: true, data: null, error: null }),
    onSuccess: (data) => setResult({ loading: false, data, error: null }),
    onError: (e: unknown) => setResult({ loading: false, data: null, error: errMessage(e) }),
  })

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">
      <h1 className="text-xl font-bold tracking-wide">BGP MITM</h1>
      <div className="text-[10px] text-julius-muted">
        Controls Julius BGP MITM routes from your backend. Use your own lab network.
      </div>

      {/* Wallet Card */}
      <InfoCard title="💰 Wallet">
        <div className="text-xs font-mono text-julius-green break-all">
          {walletData?.address || 'Loading wallet...'}
        </div>
        <button
          className="text-[10px] text-julius-accent underline"
          onClick={() => refetchWallet()}
        >
          Refresh
        </button>
      </InfoCard>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <InfoCard title="Inputs">
          <div className="space-y-3">
            <div>
              <label className="block text-[10px] text-julius-muted mb-1">Interface</label>
              <input
                value={interfaceName}
                onChange={(e) => setInterfaceName(e.target.value)}
                className="w-full bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs font-mono text-julius-text focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-[10px] text-julius-muted mb-1">IP Range (scan)</label>
              <input
                value={ipRange}
                onChange={(e) => setIpRange(e.target.value)}
                className="w-full bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs font-mono text-julius-text focus:outline-none"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] text-julius-muted mb-1">Target</label>
                <input
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  className="w-full bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs font-mono text-julius-text focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-[10px] text-julius-muted mb-1">Gateway</label>
                <input
                  value={gateway}
                  onChange={(e) => setGateway(e.target.value)}
                  className="w-full bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs font-mono text-julius-text focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label className="block text-[10px] text-julius-muted mb-1">Sniff timeout (seconds, optional)</label>
              <input
                value={timeout}
                onChange={(e) => {
                  const v = e.target.value
                  if (v === '') setTimeout('')
                  else setTimeout(Number(v))
                }}
                placeholder="e.g. 30"
                className="w-full bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs font-mono text-julius-text focus:outline-none"
              />
            </div>
          </div>
        </InfoCard>

        <InfoCard title="Actions">
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <button
                className="text-xs bg-julius-accent text-white px-4 py-2 rounded disabled:opacity-40"
                onClick={() => gatewayMut.mutate()}
                disabled={gatewayMut.isPending}
              >
                {gatewayMut.isPending ? 'Getting...' : 'Get Gateway'}
              </button>

              <button
                className="text-xs bg-julius-accent text-white px-4 py-2 rounded disabled:opacity-40"
                onClick={() => scanMut.mutate()}
                disabled={scanMut.isPending}
              >
                {scanMut.isPending ? 'Scanning...' : 'Scan'}
              </button>

              <button
                className="text-xs bg-julius-accent/30 text-white px-4 py-2 rounded disabled:opacity-40 border border-julius-accent/50"
                onClick={() => spoofMut.mutate()}
                disabled={spoofMut.isPending}
              >
                {spoofMut.isPending ? 'Spoofing...' : 'ARP Spoof'}
              </button>
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                className="text-xs bg-julius-accent/30 text-white px-4 py-2 rounded disabled:opacity-40 border border-julius-accent/50"
                onClick={() => sniffMut.mutate()}
                disabled={sniffMut.isPending}
              >
                {sniffMut.isPending ? 'Sniffing...' : 'Sniff'}
              </button>
              <button
                className="text-xs bg-julius-accent/30 text-white px-4 py-2 rounded disabled:opacity-40 border border-julius-accent/50"
                onClick={() => modifyMut.mutate()}
                disabled={modifyMut.isPending}
              >
                {modifyMut.isPending ? 'Modifying...' : 'Modify'}
              </button>
              <button
                className="text-xs bg-julius-accent/30 text-white px-4 py-2 rounded disabled:opacity-40 border border-julius-accent/50"
                onClick={() => bgpSimMut.mutate()}
                disabled={bgpSimMut.isPending}
              >
                {bgpSimMut.isPending ? 'Running...' : 'Simulate BGP'}
              </button>
            </div>

            <div className="flex gap-2">
              <button
                className="flex-1 text-xs bg-julius-red text-white px-4 py-2 rounded disabled:opacity-40"
                onClick={() => attackMut.mutate()}
                disabled={attackMut.isPending}
              >
                {attackMut.isPending ? 'Starting full attack...' : 'Full Attack'}
              </button>
              <button
                className="text-xs bg-julius-muted/30 text-white px-4 py-2 rounded border border-julius-muted/50 disabled:opacity-40"
                onClick={() => stopMut.mutate()}
                disabled={stopMut.isPending}
              >
                {stopMut.isPending ? 'Stopping...' : 'Stop All'}
              </button>
            </div>
          </div>
        </InfoCard>
      </div>

      <InfoCard title="Backend Response">
        <ResultBox result={result} />
      </InfoCard>
    </div>
  )
}