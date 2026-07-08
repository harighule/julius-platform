import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { scanner } from '../lib/api'

const API = "";

interface PortCheckResult {
  status?: string
}

interface ScanRow {
  id: string | number
  target: string
  scan_type: string
  status: string
  results?: { open_ports?: unknown[] }
}

interface VulnRow {
  id: string | number
  severity: string
  title: string
  host: string
  port: string | number
  service: string
  cve_id?: string
}

export function ScannerPanel() {
  const [target, setTarget] = useState('')
  const [scanType, setScanType] = useState('quick')
  const [qpIp, setQpIp] = useState('')
  const [qpPort, setQpPort] = useState('80')
  const [qpResult, setQpResult] = useState<PortCheckResult | null>(null)
  
  // REAL AXIOM AI Integration - NO RANDOM DATA
  const [axiomResult, setAxiomResult] = useState<any>(null)
  const [axiomRunning, setAxiomRunning] = useState(false)

  const runRealAxiomAnalysis = async (target: string) => {
    setAxiomRunning(true)
    try {
      // Call REAL AXIOM backend
      const axiomRes = await fetch(`${API}/api/axiom/real`)
      const axiomData = await axiomRes.json()
      
      // Call REAL causal analysis
      const causalRes = await fetch(`${API}/api/causal/vulnerability/breach`)
      const causalData = await causalRes.json()
      
      // Call REAL scan
      const scanRes = await fetch(`${API}/api/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target })
      })
      const scanData = await scanRes.json()
      
      setAxiomResult({
        compression_ratio: axiomData.compression_ratio,
        lossless: axiomData.lossless,
        causal_strength: causalData.strength,
        open_ports: scanData.open_ports,
        risk_assessment: scanData.risk_assessment,
        recommendations: scanData.recommendations,
        timestamp: new Date().toISOString()
      })
    } catch (error) {
      console.error('AXIOM analysis failed:', error)
      setAxiomResult({ error: 'Backend not running. Start: python backend/julius_api_real.py' })
    } finally {
      setAxiomRunning(false)
    }
  }

  const qc = useQueryClient()

  const { data: scans } = useQuery({ queryKey: ['scans'], queryFn: () => scanner.list(), refetchInterval: 5000 })
  const { data: vulns } = useQuery({ queryKey: ['vulns'], queryFn: () => scanner.vulnerabilities(), refetchInterval: 10000 })

  const scanMut = useMutation({
    mutationFn: () => scanner.scan(target, scanType),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['scans'] }); setTarget('') },
  })

  const portCheckMut = useMutation({
    mutationFn: () => scanner.checkPort(qpIp, parseInt(qpPort)),
    onSuccess: (data) => setQpResult(data as PortCheckResult),
  })

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">
      <h1 className="text-xl font-bold tracking-wide">Network Scanner</h1>

      {/* Scan form */}
      <div className="bg-julius-surface border border-julius-border rounded-xl p-5">
        <div className="flex items-end gap-4">
          <div className="flex-1">
            <label className="block text-[10px] text-julius-muted uppercase tracking-wider mb-1">Target IP / Host</label>
            <input
              type="text" value={target} onChange={e => setTarget(e.target.value)}
              placeholder="192.168.1.1 or scanme.nmap.org"
              className="w-full bg-julius-bg border border-julius-border rounded-lg px-4 py-2.5 text-sm font-mono text-julius-text focus:border-julius-accent focus:outline-none"
            />
          </div>
          <div className="w-40">
            <label className="block text-[10px] text-julius-muted uppercase tracking-wider mb-1">Scan Type</label>
            <select value={scanType} onChange={e => setScanType(e.target.value)}
              className="w-full bg-julius-bg border border-julius-border rounded-lg px-3 py-2.5 text-sm text-julius-text focus:border-julius-accent focus:outline-none">
              <option value="quick">Quick (15 ports)</option>
              <option value="full">Full (28 ports)</option>
              <option value="stealth">Stealth (10 ports)</option>
            </select>
          </div>
          <button
            onClick={() => scanMut.mutate()}
            disabled={!target || scanMut.isPending}
            className="bg-julius-accent hover:bg-julius-accent/90 disabled:opacity-40 text-white px-6 py-2.5 rounded-lg text-sm font-medium"
          >
            {scanMut.isPending ? 'Scanning...' : 'Start Scan'}
          </button>
        </div>
      </div>

      {/* Quick port check */}
      <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
        <h3 className="text-xs font-semibold mb-3">Quick Port Check</h3>
        <div className="flex items-center gap-3">
          <input value={qpIp} onChange={e => setQpIp(e.target.value)} placeholder="IP address"
            className="flex-1 bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs font-mono text-julius-text focus:outline-none" />
          <input value={qpPort} onChange={e => setQpPort(e.target.value)} placeholder="Port" type="number"
            className="w-20 bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs font-mono text-julius-text focus:outline-none" />
          <button onClick={() => portCheckMut.mutate()} disabled={!qpIp || portCheckMut.isPending}
            className="text-xs bg-julius-accent text-white px-4 py-2 rounded disabled:opacity-40">Check</button>
          {qpResult && (
            <span className={`text-xs font-mono px-2 py-1 rounded ${qpResult.status === 'open' ? 'bg-julius-green/20 text-julius-green' : 'bg-julius-red/20 text-julius-red'}`}>
              {qpResult.status?.toUpperCase()}
            </span>
          )}
        </div>
      </div>

      {/* REAL AXIOM AI Analysis - NO RANDOM DATA */}
      <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-sm font-semibold">🤖 AXIOM � CSIE � APEX Analysis</h3>
            <p className="text-[10px] text-julius-muted">AI-powered threat intelligence pipeline (REAL DATA)</p>
          </div>
          <span className="text-[10px] px-2 py-1 rounded bg-green-900/30 text-green-400 border border-green-800">ACTIVE</span>
        </div>
        <div className="flex gap-2 mb-3">
          <input value={target} onChange={e => setTarget(e.target.value)} placeholder="Target IP for AI analysis"
            className="flex-1 bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs font-mono text-julius-text focus:outline-none" />
          <button onClick={() => runRealAxiomAnalysis(target)} disabled={!target || axiomRunning}
            className="text-xs px-4 py-2 rounded disabled:opacity-40 font-mono"
            style={{ background: '#001a00', border: '1px solid #00ff9d44', color: '#00ff9d' }}>
            {axiomRunning ? '⚙️ ANALYSING...' : '🚀 RUN AI PIPELINE'}
          </button>
        </div>
        {axiomResult && !axiomResult.error && (
          <div className="bg-julius-bg rounded p-3 text-[10px] font-mono space-y-1">
            <div><span className="text-julius-muted">AXIOM Compression:</span> <span className="text-green-400">{axiomResult.compression_ratio?.toFixed(1)}x</span></div>
            <div><span className="text-julius-muted">Lossless:</span> <span className="text-green-400">{axiomResult.lossless ? '✓ VERIFIED' : '✗'}</span></div>
            <div><span className="text-julius-muted">Causal Strength (vuln→breach):</span> <span className="text-purple-400">{(axiomResult.causal_strength * 100).toFixed(0)}%</span></div>
            <div><span className="text-julius-muted">Open Ports:</span> <span className="text-blue-400">{axiomResult.open_ports?.join(', ') || 'None'}</span></div>
            {axiomResult.risk_assessment && Object.entries(axiomResult.risk_assessment).map(([port, data]: [string, any]) => (
              <div key={port}>Port {port}: <span className={data.risk === 'HIGH' ? 'text-red-400' : 'text-yellow-400'}>{data.risk} risk ({(data.exploit_probability * 100).toFixed(0)}% exploit)</span></div>
            ))}
            {axiomResult.recommendations?.length > 0 && (
              <div className="mt-2 pt-2 border-t border-julius-border">
                <span className="text-julius-muted">Recommendation:</span> <span className="text-green-400">{axiomResult.recommendations[0]}</span>
              </div>
            )}
            <div className="text-julius-muted text-[9px] mt-2">Real-time from AXIOM backend</div>
          </div>
        )}
        {axiomResult?.error && (
          <div className="bg-red-900/20 text-red-400 p-2 rounded text-[10px]">{axiomResult.error}</div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Scan history */}
        <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
          <h3 className="text-sm font-semibold mb-3">Scan History</h3>
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {((scans as { scans?: ScanRow[] } | undefined)?.scans ?? []).map((s: ScanRow) => (
              <div key={s.id} className="bg-julius-bg rounded-lg px-3 py-2 flex items-center justify-between">
                <div>
                  <div className="text-xs font-mono text-julius-accent">{s.target}</div>
                  <div className="text-[10px] text-julius-muted">{s.scan_type} | {s.id}</div>
                </div>
                <div className="text-right">
                  <span className={`text-[10px] px-2 py-0.5 rounded ${s.status === 'completed' ? 'bg-julius-green/20 text-julius-green' : s.status === 'running' ? 'bg-julius-amber/20 text-julius-amber' : 'bg-julius-red/20 text-julius-red'}`}>
                    {s.status}
                  </span>
                  {s.results?.open_ports && (
                    <div className="text-[10px] text-julius-muted mt-0.5">{s.results.open_ports.length} open ports</div>
                  )}
                </div>
              </div>
            ))}
            {(((scans as { scans?: ScanRow[] } | undefined)?.scans ?? []).length === 0) && (
              <div className="text-xs text-julius-muted text-center py-8">No scans yet. Enter a target above.</div>
            )}
          </div>
        </div>

        {/* Vulnerabilities */}
        <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
          <h3 className="text-sm font-semibold mb-3">Vulnerabilities</h3>
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {((vulns as { vulnerabilities?: VulnRow[] } | undefined)?.vulnerabilities ?? []).map((v: VulnRow) => (
              <div key={v.id} className="bg-julius-bg rounded-lg px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold
                    ${v.severity === 'critical' ? 'bg-julius-red/20 text-julius-red'
                      : v.severity === 'high' ? 'bg-julius-amber/20 text-julius-amber'
                      : v.severity === 'medium' ? 'bg-yellow-600/20 text-yellow-500'
                      : 'bg-julius-accent/20 text-julius-accent'}`}>
                    {v.severity}
                  </span>
                  <span className="text-xs text-julius-text">{v.title}</span>
                </div>
                <div className="text-[10px] text-julius-muted mt-1 font-mono">
                  {v.host}:{v.port} ({v.service}) {v.cve_id && `| ${v.cve_id}`}
                </div>
              </div>
            ))}
            {(((vulns as { vulnerabilities?: VulnRow[] } | undefined)?.vulnerabilities ?? []).length === 0) && (
              <div className="text-xs text-julius-muted text-center py-8">No vulnerabilities detected yet.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}





// import { useState } from 'react'
// import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
// import { scanner } from '../lib/api'

// interface PortCheckResult {
//   status?: string
// }

// interface ScanRow {
//   id: string | number
//   target: string
//   scan_type: string
//   status: string
//   results?: { open_ports?: unknown[] }
// }

// interface VulnRow {
//   id: string | number
//   severity: string
//   title: string
//   host: string
//   port: string | number
//   service: string
//   cve_id?: string
// }

// export function ScannerPanel() {
//   const [target, setTarget] = useState('')
//   const [scanType, setScanType] = useState('quick')
//   const [qpIp, setQpIp] = useState('')
//   const [qpPort, setQpPort] = useState('80')
//   const [qpResult, setQpResult] = useState<PortCheckResult | null>(null)
//   // -- AXIOM AI Integration ----------------------------------------------
//   const [axiomResult, setAxiomResult] = useState<unknown>(null)
//   const [axiomRunning, setAxiomRunning] = useState(false)

//   const runAxiomAnalysis = async (target: string) => {
//     setAxiomRunning(true)
//     try {
//       const r = await fetch('http://localhost:8001/api/intel/analyse', {
//         method: 'POST',
//         headers: { 'Content-Type': 'application/json' },
//         body: JSON.stringify({
//           scan_results: [{ target, ports: [80,443,22,3306,8080].slice(0, Math.floor(Math.random()*4)+2), vulnerabilities: [], services: {}, risk_score: parseFloat((Math.random()*10).toFixed(1)), open_ports_count: Math.floor(Math.random()*8)+1 }],
//           osint_data: { emails: [], domains: [target], ips: [target], phones: [], usernames: [] },
//           target, depth: 'standard'
//         })
//       })
//       setAxiomResult(await r.json())
//     } finally {
//       setAxiomRunning(false)
//     }
//   }
//   const qc = useQueryClient()

//   const { data: scans } = useQuery({ queryKey: ['scans'], queryFn: () => scanner.list(), refetchInterval: 5000 })
//   const { data: vulns } = useQuery({ queryKey: ['vulns'], queryFn: () => scanner.vulnerabilities(), refetchInterval: 10000 })

//   const scanMut = useMutation({
//     mutationFn: () => scanner.scan(target, scanType),
//     onSuccess: () => { qc.invalidateQueries({ queryKey: ['scans'] }); setTarget('') },
//   })

//   const portCheckMut = useMutation({
//     mutationFn: () => scanner.checkPort(qpIp, parseInt(qpPort)),
//     onSuccess: (data) => setQpResult(data as PortCheckResult),
//   })

//   return (
//     <div className="p-6 space-y-6 overflow-y-auto h-full">
//       <h1 className="text-xl font-bold tracking-wide">Network Scanner</h1>

//       {/* Scan form */}
//       <div className="bg-julius-surface border border-julius-border rounded-xl p-5">
//         <div className="flex items-end gap-4">
//           <div className="flex-1">
//             <label className="block text-[10px] text-julius-muted uppercase tracking-wider mb-1">Target IP / Host</label>
//             <input
//               type="text" value={target} onChange={e => setTarget(e.target.value)}
//               placeholder="192.168.1.1"
//               className="w-full bg-julius-bg border border-julius-border rounded-lg px-4 py-2.5 text-sm font-mono text-julius-text focus:border-julius-accent focus:outline-none"
//             />
//           </div>
//           <div className="w-40">
//             <label className="block text-[10px] text-julius-muted uppercase tracking-wider mb-1">Scan Type</label>
//             <select value={scanType} onChange={e => setScanType(e.target.value)}
//               className="w-full bg-julius-bg border border-julius-border rounded-lg px-3 py-2.5 text-sm text-julius-text focus:border-julius-accent focus:outline-none">
//               <option value="quick">Quick (15 ports)</option>
//               <option value="full">Full (28 ports)</option>
//               <option value="stealth">Stealth (10 ports)</option>
//             </select>
//           </div>
//           <button
//             onClick={() => scanMut.mutate()}
//             disabled={!target || scanMut.isPending}
//             className="bg-julius-accent hover:bg-julius-accent/90 disabled:opacity-40 text-white px-6 py-2.5 rounded-lg text-sm font-medium"
//           >
//             {scanMut.isPending ? 'Scanning...' : 'Start Scan'}
//           </button>
//         </div>
//       </div>

//       {/* Quick port check */}
//       <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
//         <h3 className="text-xs font-semibold mb-3">Quick Port Check</h3>
//         <div className="flex items-center gap-3">
//           <input value={qpIp} onChange={e => setQpIp(e.target.value)} placeholder="IP address"
//             className="flex-1 bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs font-mono text-julius-text focus:outline-none" />
//           <input value={qpPort} onChange={e => setQpPort(e.target.value)} placeholder="Port" type="number"
//             className="w-20 bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs font-mono text-julius-text focus:outline-none" />
//           <button onClick={() => portCheckMut.mutate()} disabled={!qpIp || portCheckMut.isPending}
//             className="text-xs bg-julius-accent text-white px-4 py-2 rounded disabled:opacity-40">Check</button>
//           {qpResult && (
//             <span className={`text-xs font-mono px-2 py-1 rounded ${qpResult.status === 'open' ? 'bg-julius-green/20 text-julius-green' : 'bg-julius-red/20 text-julius-red'}`}>
//               {qpResult.status?.toUpperCase()}
//             </span>
//           )}
//         </div>
//       </div>

//       {/* AXIOM AI Analysis */}
//       <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
//         <div className="flex items-center justify-between mb-3">
//           <div>
//             <h3 className="text-sm font-semibold">AXIOM � CSIE � APEX Analysis</h3>
//             <p className="text-[10px] text-julius-muted">AI-powered threat intelligence pipeline</p>
//           </div>
//           <span className="text-[10px] px-2 py-1 rounded bg-green-900/30 text-green-400 border border-green-800">ACTIVE</span>
//         </div>
//         <div className="flex gap-2 mb-3">
//           <input value={target} onChange={e => setTarget(e.target.value)} placeholder="Target IP for AI analysis"
//             className="flex-1 bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs font-mono text-julius-text focus:outline-none" />
//           <button onClick={() => runAxiomAnalysis(target)} disabled={!target || axiomRunning}
//             className="text-xs px-4 py-2 rounded disabled:opacity-40 font-mono"
//             style={{ background: '#001a00', border: '1px solid #00ff9d44', color: '#00ff9d' }}>
//             {axiomRunning ? '? ANALYSING...' : '? RUN AI PIPELINE'}
//           </button>
//         </div>
//         {axiomResult && (
//           <div className="bg-julius-bg rounded p-3 text-[10px] font-mono space-y-1 max-h-48 overflow-y-auto">
//             {Object.entries(axiomResult as Record<string, unknown>).map(([k, v]) => (
//               <div key={k}><span className="text-julius-muted">{k}:</span> <span className="text-green-400">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span></div>
//             ))}
//           </div>
//         )}
//       </div>
//       <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
//         {/* Scan history */}
//         <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
//           <h3 className="text-sm font-semibold mb-3">Scan History</h3>
//           <div className="space-y-2 max-h-80 overflow-y-auto">
//             {((scans as { scans?: ScanRow[] } | undefined)?.scans ?? []).map((s: ScanRow) => (
//               <div key={s.id} className="bg-julius-bg rounded-lg px-3 py-2 flex items-center justify-between">
//                 <div>
//                   <div className="text-xs font-mono text-julius-accent">{s.target}</div>
//                   <div className="text-[10px] text-julius-muted">{s.scan_type} | {s.id}</div>
//                 </div>
//                 <div className="text-right">
//                   <span className={`text-[10px] px-2 py-0.5 rounded ${s.status === 'completed' ? 'bg-julius-green/20 text-julius-green' : s.status === 'running' ? 'bg-julius-amber/20 text-julius-amber' : 'bg-julius-red/20 text-julius-red'}`}>
//                     {s.status}
//                   </span>
//                   {s.results?.open_ports && (
//                     <div className="text-[10px] text-julius-muted mt-0.5">{s.results.open_ports.length} open ports</div>
//                   )}
//                 </div>
//               </div>
//             ))}
//             {(((scans as { scans?: ScanRow[] } | undefined)?.scans ?? []).length === 0) && (
//               <div className="text-xs text-julius-muted text-center py-8">No scans yet. Enter a target above.</div>
//             )}
//           </div>
//         </div>

//         {/* Vulnerabilities */}
//         <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
//           <h3 className="text-sm font-semibold mb-3">Vulnerabilities</h3>
//           <div className="space-y-2 max-h-80 overflow-y-auto">
//             {((vulns as { vulnerabilities?: VulnRow[] } | undefined)?.vulnerabilities ?? []).map((v: VulnRow) => (
//               <div key={v.id} className="bg-julius-bg rounded-lg px-3 py-2">
//                 <div className="flex items-center gap-2">
//                   <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold
//                     ${v.severity === 'critical' ? 'bg-julius-red/20 text-julius-red'
//                       : v.severity === 'high' ? 'bg-julius-amber/20 text-julius-amber'
//                       : v.severity === 'medium' ? 'bg-yellow-600/20 text-yellow-500'
//                       : 'bg-julius-accent/20 text-julius-accent'}`}>
//                     {v.severity}
//                   </span>
//                   <span className="text-xs text-julius-text">{v.title}</span>
//                 </div>
//                 <div className="text-[10px] text-julius-muted mt-1 font-mono">
//                   {v.host}:{v.port} ({v.service}) {v.cve_id && `| ${v.cve_id}`}
//                 </div>
//               </div>
//             ))}
//             {(((vulns as { vulnerabilities?: VulnRow[] } | undefined)?.vulnerabilities ?? []).length === 0) && (
//               <div className="text-xs text-julius-muted text-center py-8">No vulnerabilities detected yet.</div>
//             )}
//           </div>
//         </div>
//       </div>
//     </div>
//   )
// }
