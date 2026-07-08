import { useState } from 'react'
import type { ReactNode } from 'react'
import { useMutation } from '@tanstack/react-query'
import { live, scanner, lan } from '../lib/api'

type ToolResult = { loading: boolean; data: unknown; error: string | null }

function errMessage(e: unknown) {
  return e instanceof Error ? e.message : 'Request failed'
}

export function ToolsPanel() {
  const [ipInput, setIpInput] = useState('')
  const [dnsInput, setDnsInput] = useState('')
  const [portIp, setPortIp] = useState('')
  const [portNum, setPortNum] = useState('80')

  const [ipResult, setIpResult] = useState<ToolResult>({ loading: false, data: null, error: null })
  const [dnsResult, setDnsResult] = useState<ToolResult>({ loading: false, data: null, error: null })
  const [portResult, setPortResult] = useState<ToolResult>({ loading: false, data: null, error: null })
  const [cveResult, setCveResult] = useState<ToolResult>({ loading: false, data: null, error: null })

  const ipMut = useMutation({
    mutationFn: (ip: string) => live.ipLookup(ip),
    onMutate: () => setIpResult({ loading: true, data: null, error: null }),
    onSuccess: (data) => setIpResult({ loading: false, data, error: null }),
    onError: (e: unknown) => setIpResult({ loading: false, data: null, error: errMessage(e) }),
  })

  const dnsMut = useMutation({
    mutationFn: (domain: string) => live.dnsLookup(domain),
    onMutate: () => setDnsResult({ loading: true, data: null, error: null }),
    onSuccess: (data) => setDnsResult({ loading: false, data, error: null }),
    onError: (e: unknown) => setDnsResult({ loading: false, data: null, error: errMessage(e) }),
  })

  const portMut = useMutation({
    mutationFn: () => scanner.checkPort(portIp, parseInt(portNum)),
    onMutate: () => setPortResult({ loading: true, data: null, error: null }),
    onSuccess: (data) => setPortResult({ loading: false, data, error: null }),
    onError: (e: unknown) => setPortResult({ loading: false, data: null, error: errMessage(e) }),
  })

  const cveMut = useMutation({
    mutationFn: () => live.latestCves(),
    onMutate: () => setCveResult({ loading: true, data: null, error: null }),
    onSuccess: (data) => setCveResult({ loading: false, data, error: null }),
    onError: (e: unknown) => setCveResult({ loading: false, data: null, error: errMessage(e) }),
  })

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">
      <h1 className="text-xl font-bold tracking-wide">Security Tools</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* IP Lookup */}
        <ToolCard title="IP Lookup" description="Geolocation, ISP, and threat intelligence">
          <div className="flex gap-2">
            <input value={ipInput} onChange={e => setIpInput(e.target.value)} placeholder="8.8.8.8"
              onKeyDown={e => e.key === 'Enter' && ipInput && ipMut.mutate(ipInput)}
              className="flex-1 bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs font-mono text-julius-text focus:outline-none" />
            <button onClick={() => ipMut.mutate(ipInput)} disabled={!ipInput || ipMut.isPending}
              className="text-xs bg-julius-accent text-white px-4 py-2 rounded disabled:opacity-40">Lookup</button>
          </div>
          <ResultView result={ipResult} render={(data) => {
            const d = data as Record<string, unknown>
            const intel = (d.intel as Record<string, unknown> | undefined) || {}
            const geo = (intel.geolocation as Record<string, unknown> | undefined) || {}
            const info = (intel.ipinfo as Record<string, unknown> | undefined) || {}
            const isLAN = String(intel.network_type ?? '') === 'Private LAN'
            const openPorts = intel.open_ports
            const portStr = Array.isArray(openPorts) ? (openPorts as unknown[]).map(String).join(', ') : ''
            return (
              <div className="space-y-1 text-[10px]">
                <Row label="IP" value={String(d.ip ?? '')} />
                <Row label="Network" value={String(intel.network_type ?? '-')} />
                {isLAN && intel.host_alive !== undefined ? (
                  <Row
                    label="Status"
                    value={(intel.host_alive === true || intel.host_alive === 'true' || intel.host_alive === 1)
                      ? `Online (${String(intel.latency_ms ?? '?')}ms)`
                      : 'Offline / Firewall'}
                  />
                ) : null}
                {intel.hostname != null && String(intel.hostname) !== '' ? <Row label="Hostname" value={String(intel.hostname)} /> : null}
                {intel.mac_address != null && String(intel.mac_address) !== '' ? <Row label="MAC" value={String(intel.mac_address)} /> : null}
                {intel.device_vendor != null && String(intel.device_vendor) !== '' ? <Row label="Vendor" value={String(intel.device_vendor)} /> : null}
                <Row label="Country" value={String(geo.country ?? info.country ?? '-')} />
                {!isLAN && <Row label="City" value={`${String(geo.city ?? info.city ?? '-')}, ${String(geo.regionName ?? info.region ?? '')}`} />}
                <Row label="ISP/Org" value={String(geo.isp ?? info.org ?? '-')} />
                {!isLAN && geo.org != null && String(geo.org) !== '' ? <Row label="Org" value={String(geo.org)} /> : null}
                {!isLAN && geo.proxy !== undefined ? (
                  <Row
                    label="Proxy/VPN"
                    value={(geo.proxy === true || geo.proxy === 'true' || geo.proxy === 1) ? 'Yes' : 'No'}
                  />
                ) : null}
                {portStr && (
                  <Row label="Open Ports" value={portStr} />
                )}
                {isLAN && !portStr && (intel.host_alive === true || intel.host_alive === 'true' || intel.host_alive === 1) ? (
                  <Row label="Open Ports" value="None (firewall blocking)" />
                ) : null}
              </div>
            )
          }} />
        </ToolCard>

        {/* DNS Lookup */}
        <ToolCard title="DNS Lookup" description="Resolve domain names to IP addresses">
          <div className="flex gap-2">
            <input value={dnsInput} onChange={e => setDnsInput(e.target.value)} placeholder="google.com"
              onKeyDown={e => e.key === 'Enter' && dnsInput && dnsMut.mutate(dnsInput)}
              className="flex-1 bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs font-mono text-julius-text focus:outline-none" />
            <button onClick={() => dnsMut.mutate(dnsInput)} disabled={!dnsInput || dnsMut.isPending}
              className="text-xs bg-julius-accent text-white px-4 py-2 rounded disabled:opacity-40">Resolve</button>
          </div>
          <ResultView result={dnsResult} render={(data) => {
            const d = data as Record<string, unknown>
            const dns = (d.dns as Record<string, unknown> | undefined) || {}
            const aRecords = dns.a_records
            const aStr = Array.isArray(aRecords) ? (aRecords as unknown[]).map(String).join(', ') : ''
            return (
              <div className="space-y-1 text-[10px]">
                <Row label="Domain" value={String(d.domain ?? '')} />
                <Row label="Resolved" value={dns.resolved ? 'Yes' : 'No'} />
                {aStr ? <Row label="A Records" value={aStr} /> : null}
                {dns.reverse_dns != null && String(dns.reverse_dns) !== '' ? <Row label="Reverse DNS" value={String(dns.reverse_dns)} /> : null}
                {dns.error != null && String(dns.error) !== '' ? <Row label="Error" value={String(dns.error)} /> : null}
              </div>
            )
          }} />
        </ToolCard>

        {/* Port Check */}
        <ToolCard title="Port Check" description="Test if a TCP port is open on a target">
          <div className="flex gap-2">
            <input value={portIp} onChange={e => setPortIp(e.target.value)} placeholder="192.168.1.1"
              className="flex-1 bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs font-mono text-julius-text focus:outline-none" />
            <input value={portNum} onChange={e => setPortNum(e.target.value)} placeholder="80" type="number"
              className="w-20 bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs font-mono text-julius-text focus:outline-none" />
            <button onClick={() => portMut.mutate()} disabled={!portIp || !portNum || portMut.isPending}
              className="text-xs bg-julius-accent text-white px-4 py-2 rounded disabled:opacity-40">Check</button>
          </div>
          <ResultView result={portResult} render={(data) => {
            const d = data as Record<string, unknown>
            return (
              <div className="space-y-1 text-[10px]">
                <Row label="Target" value={`${String(d.ip ?? d.target ?? '')}:${String(d.port ?? '')}`} />
                <Row label="Status" value={String(d.status ?? '')} />
                {d.service != null && String(d.service) !== '' ? <Row label="Service" value={String(d.service)} /> : null}
                {d.banner != null && String(d.banner) !== '' ? <Row label="Banner" value={String(d.banner)} /> : null}
                {d.authorized_via != null && String(d.authorized_via) !== '' ? <Row label="Auth" value={String(d.authorized_via)} /> : null}
              </div>
            )
          }} />
        </ToolCard>

        {/* CVE Search */}
        <ToolCard title="Latest CVEs" description="Recent vulnerabilities from NIST NVD">
          <button onClick={() => cveMut.mutate()} disabled={cveMut.isPending}
            className="text-xs bg-julius-accent text-white px-4 py-2 rounded disabled:opacity-40 w-full">
            {cveMut.isPending ? 'Fetching...' : 'Fetch Latest CVEs'}
          </button>
          <ResultView result={cveResult} render={(raw) => {
            const d = raw as { total_results?: number; cves?: Array<Record<string, unknown>> }
            const cves = d.cves || []
            return (
              <div className="space-y-2 max-h-80 overflow-y-auto">
                <div className="text-[10px] text-julius-muted">{d.total_results} total in NVD</div>
                {cves.map((cve: Record<string, unknown>) => (
                  <div key={String(cve.id)} className="bg-julius-bg rounded-lg px-3 py-2">
                    <div className="flex items-center gap-2">
                      {cve.cvss_score != null && (
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${cve.severity === 'critical' ? 'bg-julius-red/20 text-julius-red' : cve.severity === 'high' ? 'bg-julius-amber/20 text-julius-amber' : 'bg-julius-accent/20 text-julius-accent'}`}>
                          {String(cve.cvss_score)}
                        </span>
                      )}
                      <span className="text-[10px] font-mono text-julius-accent">{String(cve.id)}</span>
                    </div>
                    <div className="text-[10px] text-julius-text mt-1">{String(cve.description ?? '').slice(0, 150)}...</div>
                  </div>
                ))}
              </div>
            )
          }} />
        </ToolCard>
      </div>

      {/* LAN Target Recon */}
      <LanReconSection />
    </div>
  )
}

interface ReconPayload {
  netbios_info?: { hostname?: string; domain?: string; mac?: string }
  os_info?: { os?: string; ttl?: string | number }
  smb_shares?: {
    accessible?: boolean
    shares?: Array<{ name: string; type?: string; remark?: string }>
    error?: string
  }
  users?: { users?: Array<{ name: string }>; error?: string }
  services?: { services?: Array<{ display_name?: string; name?: string }>; total?: number; error?: string }
  network_info?: { adapters?: Array<{ description?: string }>; error?: string }
  smb_security?: { null_session?: boolean; vulnerabilities?: string[] }
}

interface BrowsePayload {
  path?: string
  files?: Array<{ type?: string; name?: string; size?: string | number }>
  error?: string
}

interface MkdirResult {
  success?: boolean
  method?: string
  error?: string
}

type ExecStreamState = { success: boolean; output?: string; error?: string }

function LanReconSection() {
  const [target, setTarget] = useState('')
  const [creds, setCreds] = useState({ username: '', password: '' })
  const [reconData, setReconData] = useState<ReconPayload | null>(null)
  const [activeTab, setActiveTab] = useState('overview')
  const [browseData, setBrowseData] = useState<BrowsePayload | null>(null)
  const [mkdirPath, setMkdirPath] = useState('')
  const [mkdirResult, setMkdirResult] = useState<MkdirResult | null>(null)
  const [execCmd, setExecCmd] = useState('')
  const [execResult, setExecResult] = useState<ExecStreamState | null>(null)

  const reconMut = useMutation({
    mutationFn: () => lan.recon(target, creds.username || undefined, creds.password || undefined),
    onSuccess: (data) => { setReconData(data as ReconPayload); setActiveTab('overview') },
  })

  const browseMut = useMutation({
    mutationFn: (args: { share: string; path?: string }) => lan.browse(target, args.share, args.path, creds.username || undefined, creds.password || undefined),
    onSuccess: (data) => setBrowseData(data as BrowsePayload),
  })

  const mkdirMut = useMutation({
    mutationFn: () => lan.mkdir(target, mkdirPath, creds.username || undefined, creds.password || undefined),
    onSuccess: (data) => setMkdirResult(data as MkdirResult),
  })

  const [isExecuting, setIsExecuting] = useState(false)

  const handleExecStream = async () => {
    setExecResult({ success: true, output: '' })
    setIsExecuting(true)
    try {
      await lan.execStream(
        target,
        execCmd,
        (chunk) => {
          setExecResult((prev: ExecStreamState | null) => ({
            success: true,
            output: (prev?.output || '') + chunk
          }))
        },
        creds.username || undefined,
        creds.password || undefined
      )
    } catch (e: unknown) {
      setExecResult({ success: false, error: errMessage(e) })
    } finally {
      setIsExecuting(false)
    }
  }

  const tabs = ['overview', 'shares', 'security', 'actions'] as const

  return (
    <div className="bg-julius-surface border border-julius-border rounded-xl p-5 space-y-4">
      <div>
        <h2 className="text-sm font-bold text-julius-text">LAN Target Reconnaissance</h2>
        <p className="text-[10px] text-julius-muted">Deep scan a device on your network — NetBIOS, SMB shares, OS detection, users, security audit</p>
      </div>

      <div className="flex gap-3 flex-wrap">
        <input value={target} onChange={e => setTarget(e.target.value)} placeholder="Target IP (e.g. 192.168.1.7)"
          className="flex-1 min-w-[180px] bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs font-mono text-julius-text focus:outline-none" />
        <input value={creds.username} onChange={e => setCreds(c => ({ ...c, username: e.target.value }))} placeholder="Username (optional)"
          className="w-32 bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs text-julius-text focus:outline-none" />
        <input value={creds.password} onChange={e => setCreds(c => ({ ...c, password: e.target.value }))} placeholder="Password" type="password"
          className="w-32 bg-julius-bg border border-julius-border rounded px-3 py-2 text-xs text-julius-text focus:outline-none" />
        <button onClick={() => reconMut.mutate()} disabled={!target || reconMut.isPending}
          className="text-xs bg-julius-red text-white px-5 py-2 rounded disabled:opacity-40 font-semibold">
          {reconMut.isPending ? 'Scanning...' : 'Full Recon'}
        </button>
      </div>

      {reconData && (
        <>
          {/* Tabs */}
          <div className="flex gap-1 bg-julius-bg rounded-lg p-1">
            {tabs.map(t => (
              <button key={t} onClick={() => setActiveTab(t)}
                className={`flex-1 text-[10px] py-1.5 rounded transition-colors capitalize ${activeTab === t ? 'bg-julius-accent/20 text-julius-accent font-semibold' : 'text-julius-muted hover:text-julius-text'}`}>
                {t}
              </button>
            ))}
          </div>

          {activeTab === 'overview' && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              <InfoCard title="NetBIOS">
                <KV label="Hostname" value={reconData.netbios_info?.hostname} />
                <KV label="Domain/Group" value={reconData.netbios_info?.domain} />
                <KV label="MAC" value={reconData.netbios_info?.mac} />
              </InfoCard>
              <InfoCard title="OS Detection">
                <KV label="OS" value={reconData.os_info?.os} />
                <KV label="TTL" value={reconData.os_info?.ttl} />
              </InfoCard>
              <InfoCard title="SMB Shares">
                <KV label="Accessible" value={reconData.smb_shares?.accessible ? 'Yes' : 'No'} />
                <KV label="Count" value={reconData.smb_shares?.shares?.length ?? 0} />
                {reconData.smb_shares?.shares?.map((s, i: number) => (
                  <div key={i} className="text-[10px] text-julius-accent font-mono">\\{target}\{s.name}</div>
                ))}
                {reconData.smb_shares?.error && <div className="text-[10px] text-julius-red">{reconData.smb_shares.error}</div>}
              </InfoCard>
              <InfoCard title="Users">
                {reconData.users?.users?.length ? reconData.users.users.map((u, i: number) => (
                  <div key={i} className="text-[10px] text-julius-text font-mono">{u.name}</div>
                )) : <div className="text-[10px] text-julius-muted">{reconData.users?.error || 'Access denied'}</div>}
              </InfoCard>
              <InfoCard title="Services">
                <KV label="Running" value={reconData.services?.total ?? '?'} />
                {reconData.services?.services?.slice(0, 8).map((s, i: number) => (
                  <div key={i} className="text-[10px] text-julius-muted truncate">{s.display_name || s.name}</div>
                ))}
                {reconData.services?.error && <div className="text-[10px] text-julius-red">{reconData.services.error}</div>}
              </InfoCard>
              <InfoCard title="Network">
                {reconData.network_info?.adapters?.map((a, i: number) => (
                  <div key={i} className="text-[10px] text-julius-muted truncate">{a.description}</div>
                ))}
                {reconData.network_info?.error && <div className="text-[10px] text-julius-red">{reconData.network_info.error}</div>}
              </InfoCard>
            </div>
          )}

          {activeTab === 'shares' && (
            <div className="space-y-3">
              {reconData.smb_shares?.shares?.length ? reconData.smb_shares.shares.map((s, i: number) => (
                <div key={i} className="bg-julius-bg rounded-lg p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-julius-accent">\\{target}\{s.name}</span>
                    <button onClick={() => browseMut.mutate({ share: s.name })} disabled={browseMut.isPending}
                      className="text-[10px] bg-julius-accent/20 text-julius-accent px-2 py-1 rounded hover:bg-julius-accent/30">Browse</button>
                  </div>
                  {s.type && <div className="text-[10px] text-julius-muted mt-1">Type: {s.type} {s.remark ? `— ${s.remark}` : ''}</div>}
                </div>
              )) : <div className="text-xs text-julius-muted text-center py-4">{reconData.smb_shares?.error || 'No shares found'}</div>}

              {browseData && (
                <div className="bg-julius-bg rounded-lg p-3">
                  <div className="text-[10px] text-julius-muted mb-2 font-mono">{browseData.path}</div>
                  {browseData.files?.map((f, i: number) => (
                    <div key={i} className="flex gap-3 text-[10px] py-0.5">
                      <span>{f.type === 'dir' ? '📁' : '📄'}</span>
                      <span className={f.type === 'dir' ? 'text-julius-accent' : 'text-julius-text'}>{f.name}</span>
                      <span className="text-julius-muted ml-auto">{f.size || '-'}</span>
                    </div>
                  ))}
                  {browseData.error && <div className="text-[10px] text-julius-red">{browseData.error}</div>}
                </div>
              )}
            </div>
          )}

          {activeTab === 'security' && (
            <div className="space-y-3">
              <InfoCard title="SMB Security Audit">
                <KV label="Null Session" value={reconData.smb_security?.null_session ? 'ALLOWED (vulnerable)' : 'Blocked'} />
                {reconData.smb_security?.vulnerabilities?.map((v: string, i: number) => (
                  <div key={i} className="text-[10px] text-julius-red mt-1">⚠ {v}</div>
                ))}
                {!reconData.smb_security?.vulnerabilities?.length && (
                  <div className="text-[10px] text-julius-green mt-1">✓ No SMB vulnerabilities detected</div>
                )}
              </InfoCard>
            </div>
          )}

          {activeTab === 'actions' && (
            <div className="space-y-4">
              {/* Create folder */}
              <div className="bg-julius-bg rounded-lg p-3 space-y-2">
                <div className="text-xs font-semibold text-julius-text">Create Remote Folder</div>
                <div className="flex gap-2">
                  <input value={mkdirPath} onChange={e => setMkdirPath(e.target.value)}
                    placeholder="C:\Users\Public\Desktop\MyFolder"
                    className="flex-1 bg-julius-surface border border-julius-border rounded px-2 py-1.5 text-xs font-mono text-julius-text focus:outline-none" />
                  <button onClick={() => mkdirMut.mutate()} disabled={!mkdirPath || mkdirMut.isPending}
                    className="text-[10px] bg-julius-accent text-white px-3 py-1.5 rounded disabled:opacity-40">Create</button>
                </div>
                {mkdirResult && (
                  <div className={`text-[10px] ${mkdirResult.success ? 'text-julius-green' : 'text-julius-red'}`}>
                    {mkdirResult.success ? `Created via ${mkdirResult.method}` : mkdirResult.error}
                  </div>
                )}
              </div>
              {/* Execute command */}
              <div className="bg-julius-bg rounded-lg p-3 space-y-2">
                <div className="text-xs font-semibold text-julius-text">Execute Remote Command</div>
                <div className="flex gap-2">
                  <input value={execCmd} onChange={e => setExecCmd(e.target.value)}
                    placeholder="hostname"
                    className="flex-1 bg-julius-surface border border-julius-border rounded px-2 py-1.5 text-xs font-mono text-julius-text focus:outline-none" />
                  <button onClick={handleExecStream} disabled={!execCmd || isExecuting}
                    className="text-[10px] bg-julius-red text-white px-3 py-1.5 rounded disabled:opacity-40">
                    {isExecuting ? 'Executing...' : 'Execute'}
                  </button>
                </div>
                {execResult && (
                  <pre className="text-[10px] font-mono p-2 bg-julius-surface rounded max-h-40 overflow-auto text-julius-text">
                    {execResult.success ? execResult.output : execResult.error}
                    {isExecuting && <span className="animate-pulse">_</span>}
                  </pre>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function InfoCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-julius-bg border border-julius-border rounded-lg p-3">
      <div className="text-[10px] text-julius-muted uppercase tracking-wider mb-2 font-semibold">{title}</div>
      <div className="space-y-0.5">{children}</div>
    </div>
  )
}

function KV({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between text-[10px] py-0.5">
      <span className="text-julius-muted">{label}</span>
      <span className="font-mono text-julius-text">{value ?? '-'}</span>
    </div>
  )
}

function ToolCard({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <div className="bg-julius-surface border border-julius-border rounded-xl p-5 space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-julius-text">{title}</h3>
        <p className="text-[10px] text-julius-muted">{description}</p>
      </div>
      {children}
    </div>
  )
}

function ResultView({ result, render }: { result: ToolResult; render: (data: Record<string, unknown>) => ReactNode }) {
  if (result.loading) return <div className="text-xs text-julius-muted text-center py-3">Loading...</div>
  if (result.error) return <div className="text-xs text-julius-red bg-julius-red/10 rounded p-2">{result.error}</div>
  if (!result.data) return null
  return <div className="bg-julius-bg border border-julius-border rounded-lg p-3">{render(result.data as Record<string, unknown>)}</div>
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between py-0.5">
      <span className="text-julius-muted">{label}</span>
      <span className="font-mono text-julius-text text-right ml-2 truncate max-w-[60%]">{value}</span>
    </div>
  )
}
