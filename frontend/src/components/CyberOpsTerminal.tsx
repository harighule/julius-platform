import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { chat } from '../lib/api';
import './CyberOpsTerminal.css';

interface Msg { id: string; role: 'user' | 'assistant'; content: string; ts: string; loading?: boolean; intent?: string; engine?: string; }
interface LogLine { id: string; msg: string; level: 'info' | 'warn' | 'err' | 'ok'; ts: string; }
interface ProcItem { id: string; name: string; state: 'running' | 'success' | 'failed' | 'pending'; }

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));
const rand = (a: number, b: number) => Math.floor(Math.random() * (b - a + 1)) + a;
const pick = <T,>(arr: T[]): T => arr[Math.floor(Math.random() * arr.length)];

const codeSnippets = [
  `import socket, ssl, struct\nfrom cryptography.fernet import Fernet\n\ndef establish_tunnel(host, port):\n    ctx = ssl.create_default_context()\n    sock = socket.create_connection((host, port))\n    secure = ctx.wrap_socket(sock, server_hostname=host)\n    key = Fernet.generate_key()\n    cipher = Fernet(key)\n    return secure, cipher`,
  `async function probeEndpoints(targets) {\n  const results = [];\n  for (const t of targets) {\n    const res = await fetch(t.url, {\n      method: 'OPTIONS',\n      headers: { 'X-Probe': crypto.randomUUID() }\n    });\n    results.push({ target: t.id, status: res.status,\n      headers: Object.fromEntries(res.headers) });\n  }\n  return results;\n}`,
  `#!/usr/bin/env python3\n# CVE-2024-XXXX Exploit Module\nimport subprocess, hashlib\n\ndef inject_payload(target_ip, payload):\n    h = hashlib.sha256(payload).hexdigest()[:16]\n    packet = struct.pack('!HH', 0x1337, len(payload))\n    packet += payload.encode()\n    sock.sendto(packet, (target_ip, 4444))\n    return f'[+] Payload {h} delivered'`,
  `# AutoGen Agent Initialization\nfrom autogen import AssistantAgent, UserProxyAgent\n\nbrain2 = AssistantAgent(\n    name="CyberStrike",\n    system_message="Analyze network topology..."\n)\nproxy = UserProxyAgent(\n    name="Julius_Core",\n    code_execution_config={"work_dir": "/ops"}\n)\nproxy.initiate_chat(brain2, message=cmd)`,
  `nmap -sV -sC --script=vuln -T4 -oX scan.xml $TARGET\nhydra -L users.txt -P pass.txt ssh://$TARGET\nsqlmap -u "$URL" --batch --dbs --random-agent\nnikto -h $TARGET -output report.html -Format html\ngobuster dir -u $URL -w /wordlists/common.txt`,
  `def lateral_move(session, target):\n    creds = session.dump_credentials()\n    for cred in creds:\n        try:\n            new_session = exploit(\n                target=target,\n                username=cred.user,\n                token=cred.ntlm_hash,\n                method='pass-the-hash'\n            )\n            if new_session.active:\n                return new_session\n        except AccessDenied:\n            continue\n    raise NoValidCredentials()`,
  `// Robin AI — Tor OSINT Module\nconst torClient = new TorController({\n  socksPort: 9150,\n  controlPort: 9051,\n  circuitRotation: 30000\n});\nawait torClient.connect();\nconst identity = await torClient.newCircuit();\nconsole.log('[OSINT] New identity:', identity.exitNode);`,
  `class MemoryLayer:\n    """JULIUS 4-Layer Cognitive Memory"""\n    def __init__(self):\n        self.episodic = EpisodicStore()\n        self.semantic = SemanticGraph()\n        self.procedural = ProcedureCache()\n        self.working = WorkingMemory(capacity=128)\n\n    async def recall(self, query, context):\n        relevance = self.semantic.search(query)\n        procedures = self.procedural.match(context)\n        return self.working.synthesize(relevance, procedures)`
];

interface CommandProfile {
  label: string
  phases: string[]
  nodes: string[]
  nodeStates: string[]
  vulns: number
  packets: number
}

const commandProfiles: Record<string, CommandProfile> = {
  scan: {
    label: 'Network Scan',
    phases: ['Initializing scan engine', 'Resolving DNS targets', 'SYN probe on 65535 ports', 'Service fingerprinting', 'OS detection via TCP/IP stack', 'Vulnerability correlation', 'Generating scan report'],
    nodes: ['Gateway 10.0.0.1', 'Firewall 10.0.0.2', 'Server 192.168.1.10', 'DB 192.168.1.20', 'API 192.168.1.30'],
    nodeStates: ['active', 'active', 'breached', 'breached', 'active'],
    vulns: 7, packets: 24580
  },
  exploit: {
    label: 'Exploit Execution',
    phases: ['Loading exploit module', 'Compiling payload', 'Encoding shellcode', 'Establishing reverse handler', 'Injecting payload', 'Escalating privileges', 'Establishing persistence'],
    nodes: ['Attacker', 'Target 10.0.2.15', 'Kernel', 'Root Shell', 'C2 Server'],
    nodeStates: ['active', 'breached', 'breached', 'breached', 'active'],
    vulns: 3, packets: 8920
  },
  recon: {
    label: 'OSINT Reconnaissance',
    phases: ['Activating Robin AI', 'Routing through Tor', 'Scraping public records', 'Cross-referencing databases', 'Analyzing social graph', 'Compiling intelligence', 'Encrypting findings'],
    nodes: ['Robin AI', 'Tor Entry', 'Relay Node', 'Exit Node', 'Target Domain'],
    nodeStates: ['active', 'active', 'active', 'active', 'breached'],
    vulns: 0, packets: 15340
  },
  bruteforce: {
    label: 'Credential Attack',
    phases: ['Loading wordlist (14M entries)', 'Spawning 32 threads', 'Testing SSH authentication', 'Rate limit detected — throttling', 'Rotating source IPs', 'Match found — validating', 'Session established'],
    nodes: ['Hydra Engine', 'Proxy Pool', 'SSH Target', 'Auth Service', 'Session Mgr'],
    nodeStates: ['active', 'active', 'blocked', 'breached', 'breached'],
    vulns: 1, packets: 198400
  },
  defend: {
    label: 'Defense Protocol',
    phases: ['Analyzing threat vectors', 'Deploying WAF rules', 'Updating IDS signatures', 'Patching CVE entries', 'Rotating API keys', 'Hardening firewall policies', 'Defense grid active'],
    nodes: ['Perimeter', 'WAF', 'IDS/IPS', 'Endpoint', 'SIEM'],
    nodeStates: ['active', 'active', 'active', 'active', 'active'],
    vulns: 0, packets: 5600
  },
  default: {
    label: 'System Command',
    phases: ['Parsing command', 'Loading modules', 'Brain-2 analysis', 'Executing subroutines', 'Validating output', 'Compiling results', 'Task complete'],
    nodes: ['CLI Parser', 'Brain-1', 'Brain-2', 'Executor', 'Output'],
    nodeStates: ['active', 'active', 'breached', 'active', 'active'],
    vulns: 2, packets: 3200
  }
};

function detectCommand(cmd: string) {
  const c = cmd.toLowerCase();
  if (c.includes('scan') || c.includes('nmap') || c.includes('recon') || c.includes('discover')) return 'scan';
  if (c.includes('exploit') || c.includes('attack') || c.includes('inject') || c.includes('payload')) return 'exploit';
  if (c.includes('osint') || c.includes('robin') || c.includes('tor') || c.includes('intel')) return 'recon';
  if (c.includes('brute') || c.includes('hydra') || c.includes('crack') || c.includes('password')) return 'bruteforce';
  if (c.includes('defend') || c.includes('patch') || c.includes('harden') || c.includes('firewall')) return 'defend';
  return 'default';
}

const EXECUTION_INTENTS = [
  'network_scan', 'port_check', 'vulnerability_scan', 'run_exploit', 'add_pattern',
  'identity_merge', 'darkweb_investigate', 'investigate',
  'remote_command', 'store_credentials', 'install_package', 'linux_command'
];

interface Props {
  onClose: () => void;
}

export function CyberOpsTerminal({ onClose }: Props) {
  const navigate = useNavigate();
  const location = useLocation();

  const [sysTime, setSysTime] = useState('');
  const [netStatus, setNetStatus] = useState<'live' | 'warn'>('warn');
  
  const [msgs, setMsgs] = useState<Msg[]>([
    { id: 'start', role: 'assistant', content: 'Cyber Operations Terminal initialized. All subsystems nominal.\nBrain-2 (AutoGen) linked. CyberStrike module on standby.\nAwaiting command input...', ts: new Date().toISOString() }
  ]);
  const [input, setInput] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState(0);

  const [processes, setProcesses] = useState<ProcItem[]>([]);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [codeStream, setCodeStream] = useState('');
  const [glitchActive, setGlitchActive] = useState(false);
  const [accessFlash, setAccessFlash] = useState<{ label: string, status: 'granted' | 'denied' } | null>(null);

  const [networkNodes, setNetworkNodes] = useState<string[]>(['Core Router', 'Firewall Alpha', 'DMZ Server', 'Internal Net', 'Database Cluster']);
  const [networkStates, setNetworkStates] = useState<string[]>(['active', 'active', 'pending', 'pending', 'pending']);
  
  const [metrics, setMetrics] = useState({ packets: 0, vulns: 0, latency: 1, threads: 1 });

  const chatEndRef = useRef<HTMLDivElement>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const procEndRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Clock
  useEffect(() => {
    const iv = setInterval(() => {
      setSysTime(new Date().toTimeString().split(' ')[0]);
    }, 1000);
    return () => clearInterval(iv);
  }, []);

  // Matrix Rain
  useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const ctx = c.getContext('2d');
    if (!ctx) return;

    let cols: number;
    let drops: number[];

    const resize = () => {
      if (!c.parentElement) return;
      c.width = c.parentElement.offsetWidth;
      c.height = c.parentElement.offsetHeight;
      cols = Math.floor(c.width / 14);
      drops = Array(cols).fill(1);
    };
    resize();
    window.addEventListener('resize', resize);

    const chars = 'アイウエオカキクケコ0123456789ABCDEF{}[]<>/\\|=+-*&^%$#@!';
    const iv = setInterval(() => {
      ctx.fillStyle = 'rgba(10,10,15,0.1)';
      ctx.fillRect(0, 0, c.width, c.height);
      ctx.fillStyle = '#00ff88';
      ctx.font = '12px "JetBrains Mono"';
      for (let i = 0; i < cols; i++) {
        const ch = chars[Math.floor(Math.random() * chars.length)];
        ctx.fillText(ch, i * 14, drops[i] * 14);
        if (drops[i] * 14 > c.height && Math.random() > 0.97) drops[i] = 0;
        drops[i]++;
      }
    }, 50);

    return () => {
      clearInterval(iv);
      window.removeEventListener('resize', resize);
    };
  }, []);

  // Auto-scrolls
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs]);
  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [logs]);
  useEffect(() => { procEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [processes]);

  const addLog = useCallback((msg: string, level: 'info' | 'warn' | 'err' | 'ok' = 'info') => {
    setLogs(p => [...p, { id: `l-${Date.now()}-${Math.random()}`, msg, level, ts: new Date().toTimeString().split(' ')[0] }]);
  }, []);

  // Boot Sequence
  useEffect(() => {
    const bootMsgs: [string, 'info'|'warn'|'err'|'ok'][] = [
      ['Kernel modules loaded', 'info'],
      ['Brain-1 classifier online', 'info'],
      ['Brain-2 (AutoGen) connected', 'ok'],
      ['CyberStrike MCP bridge: standby', 'warn'],
      ['Robin AI Tor module: ready', 'info'],
      ['4-layer cognitive memory initialized', 'ok'],
      ['JULIUS Cyber Ops Terminal ready', 'ok']
    ];
    let isMounted = true;
    (async () => {
      for (const [msg, lvl] of bootMsgs) {
        if (!isMounted) break;
        addLog(msg, lvl);
        await sleep(200);
      }
    })();
    return () => { isMounted = false; };
  }, [addLog]);

  const executeCommand = async () => {
    const v = input.trim();
    if (!v || isRunning) return;
    setIsRunning(true);
    setInput('');
    setNetStatus('live');
    setProgress(0);
    setProcesses([]);

    // Add user message to UI immediately
    const userMsgId = `u-${Date.now()}`;
    setMsgs(p => [...p, { id: userMsgId, role: 'user', content: v, ts: new Date().toISOString() }]);
    
    // Add loading AI message
    const loadMsgId = `l-${Date.now()}`;
    setMsgs(p => [...p, { id: loadMsgId, role: 'assistant', content: '', ts: new Date().toISOString(), loading: true }]);

    const type = detectCommand(v);
    const profile = commandProfiles[type];
    
    addLog(`Command received: ${v}`, 'info');
    addLog(`Routing to module: ${profile.label}`, 'info');
    await sleep(400);

    // Fire off backend APi concurrently
    // We don't await chat.send() yet. Let the cinematic phases play out at least partially 
    // to hide latency, then we wait for chat.send() if it hasn't finished.
    const startTime = Date.now();
    let backendResult: unknown = null;
    let backendErr: unknown = null;
    
    const apiPromise = chat.send(v).then(res => backendResult = res).catch(err => backendErr = err);

    for (let i = 0; i < profile.phases.length; i++) {
      const phase = profile.phases[i];
      const pct = Math.round(((i + 1) / profile.phases.length) * 100);

      const procId = `p-${Date.now()}-${i}`;
      setProcesses(p => [...p, { id: procId, name: phase, state: 'running' }]);
      addLog(phase, 'info');
      setProgress(pct);

      const snippet = pick(codeSnippets);
      // Simulate typing code stream
      setCodeStream('');
      for (let j = 0; j < snippet.length; j += 4) {
        setCodeStream(snippet.substring(0, j + 4));
        await sleep(30); 
      }

      if (i === Math.floor(profile.phases.length / 2)) {
        setNetworkNodes(profile.nodes);
        setNetworkStates(profile.nodeStates);
        addLog('Network topology mapped', 'ok');
      }

      if (Math.random() > 0.7) {
        addLog(pick([
          'Anomalous traffic pattern detected',
          'Encrypted channel established',
          'Firewall rule bypassed',
          'Memory injection successful',
          'TLS handshake intercepted',
          'Credential hash extracted',
          'Port 443 — service verified',
          'Polymorphic evasion engaged',
          'Sandbox detection — clean',
          'Anti-forensics module loaded'
        ]), 'warn');
      }

      await sleep(rand(300, 700));

      setProcesses(p => p.map(proc => proc.id === procId ? { ...proc, state: 'success' } : proc));
    }

    // Await API if it's still running
    addLog('Awaiting backend confirmation...', 'warn');
    try {
      if (!backendResult && !backendErr) await apiPromise;
    } catch {
      void 0
    }

    type ChatSendPayload = {
      id?: string
      timestamp?: string
      message?: string
      intent?: { category?: string }
      engine?: string
    }
    const br = backendResult as ChatSendPayload | null
    const errMsg = backendErr instanceof Error ? backendErr.message : String(backendErr ?? 'error')
    const isSuccess = !backendErr && !br?.intent?.category?.includes('error');
    const intentCat = br?.intent?.category || 'unknown';
    const isExecution = EXECUTION_INTENTS.includes(intentCat);
    
    const status = isSuccess ? 'granted' : 'denied';
    const flashLabel = isExecution 
      ? (isSuccess ? 'COMMAND EXECUTED' : 'EXECUTION FAILED')
      : (isSuccess ? 'ACCESS GRANTED' : 'ACCESS DENIED');

    // Update metrics
    setMetrics({ packets: profile.packets, vulns: profile.vulns, latency: Date.now() - startTime, threads: rand(4, 64) });

    // Glitch & Flash
    setGlitchActive(true);
    setAccessFlash({ label: flashLabel, status });
    setTimeout(() => setGlitchActive(false), 450);
    setTimeout(() => setAccessFlash(null), 1800);
    
    addLog(`Operation complete — ${flashLabel}`, status === 'granted' ? 'ok' : 'err');
    await sleep(800);

    // Finalize Chat
    const finalText = backendErr ? `Error: ${errMsg}` : (br?.message || 'Operation confirmed.');
    setMsgs(p => [
      ...p.filter(m => !m.loading),
      {
        id: br?.id || `r-${Date.now()}`,
        role: 'assistant',
        content: finalText,
        ts: br?.timestamp || new Date().toISOString(),
        intent: br?.intent?.category,
        engine: br?.engine
      }
    ]);

    addLog('JULIUS ready for next command', 'ok');

    if (br?.intent?.category === 'linux_command' && location.pathname !== '/terminal') {
       navigate('/terminal');
    }

    setProgress(0);
    setNetStatus('warn');
    setIsRunning(false);
  };

  return (
    <div className={`cyber-ops-terminal-container ${glitchActive ? 'cyber-glitch-active' : ''}`}>
      <div className="cyber-app">
        {/* TOP BAR */}
        <div className="cyber-topbar">
          <div className="cyber-logo">JULIUS</div>
          <div style={{ fontSize: '10px', color: 'var(--cyb-text-dim)', letterSpacing: '2px' }}>CYBER OPS TERMINAL v3.1</div>
          <div className="cyber-status-cluster">
            <span><span className="cyber-status-dot live"></span>CORE ONLINE</span>
            <span><span className="cyber-status-dot live"></span>BRAIN-2 LINKED</span>
            <span><span className={`cyber-status-dot ${netStatus}`}></span>{netStatus === 'live' ? 'NET ACTIVE' : 'NET STANDBY'}</span>
          </div>
          <div className="cyber-sys-time">{sysTime}</div>
          <button onClick={onClose} className="cyber-close-btn ml-4">EXIT</button>
        </div>

        {/* MAIN: CHAT */}
        <div className="cyber-main-panel">
          <div className="cyber-panel-header"><span className="cyber-indicator"></span>COMMAND INTERFACE</div>
          <div className="cyber-exec-progress"><div className="cyber-exec-progress-fill" style={{ width: `${progress}%` }}></div></div>
          
          <div className="cyber-chat-messages">
            {msgs.map((m) => (
              <div key={m.id} className={`cyber-msg ${m.role}`}>
                <span className="cyber-prefix">{m.role === 'user' ? 'OPERATOR ▸' : 'JULIUS ▸'}</span>
                {m.loading ? (
                   <span className="flex gap-1 mt-1">
                     <span className="w-1.5 h-1.5 bg-[var(--cyb-green)] rounded-full animate-bounce" />
                     <span className="w-1.5 h-1.5 bg-[var(--cyb-green)] rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                     <span className="w-1.5 h-1.5 bg-[var(--cyb-green)] rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                   </span>
                ) : m.content}
                {(m.engine || m.intent) && (
                  <div className="mt-2 text-[9px] text-[var(--cyb-text-dim)] font-mono flex gap-2 border-t border-[var(--cyb-border)] pt-1">
                    {m.intent && <span>I:[{m.intent}]</span>}
                    {m.engine && <span>E:[{m.engine}]</span>}
                  </div>
                )}
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>

          <div className="cyber-chat-input-wrap">
            <textarea 
              className="cyber-chat-input" 
              placeholder="Enter command :: e.g. scan target 192.168.1.0/24" 
              spellCheck="false" 
              autoComplete="off"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  executeCommand();
                }
              }}
              disabled={isRunning}
              rows={1}
            />
            <button className="cyber-send-btn" onClick={executeCommand} disabled={isRunning || !input.trim()}>
              {isRunning ? '◼ BUSY' : 'EXEC ▸'}
            </button>
          </div>
        </div>

        {/* SIDE: CODE + PROCESSES */}
        <div className="cyber-side-panel">
          <div className="cyber-panel-header"><span className="cyber-indicator"></span>CODE INJECTION STREAM</div>
          <div className="cyber-code-stream">
            <canvas ref={canvasRef} className="cyber-matrix-canvas"></canvas>
            <pre>
              {codeStream}
              {codeStream && <span className="cyber-cursor-blink"></span>}
            </pre>
          </div>
          
          <div className="cyber-panel-header mt-auto" style={{ borderTop: '1px solid var(--cyb-border)' }}>
            <span className="cyber-indicator" style={{ background: 'var(--cyb-amber)', boxShadow: '0 0 8px var(--cyb-amber)' }}></span>
            ACTIVE PROCESSES
          </div>
          <div className="cyber-process-list">
            {processes.map(p => (
              <div key={p.id} className={`cyber-proc-item ${p.state}`}>
                {p.state === 'running' ? <div className="cyber-proc-spinner"></div> : 
                 p.state === 'success' ? <span className="cyber-proc-icon">✓</span> : 
                 p.state === 'failed' ? <span className="cyber-proc-icon">✗</span> : <span className="cyber-proc-icon">◦</span>}
                <span>{p.name}</span>
              </div>
            ))}
            <div ref={procEndRef} />
          </div>
        </div>

        {/* BOTTOM */}
        <div className="cyber-bottom-panel">
          <div className="cyber-bottom-section">
            <div className="cyber-panel-header"><span className="cyber-indicator" style={{ background: 'var(--cyb-purple)', boxShadow: '0 0 8px var(--cyb-purple)' }}></span>NETWORK TOPOLOGY</div>
            <div className="cyber-network-viz">
              {networkNodes.map((n, i) => {
                const state = networkStates[i] || 'pending';
                const pct = state === 'breached' ? 100 : state === 'active' ? rand(40, 80) : rand(5, 20);
                const color = state === 'breached' ? 'var(--cyb-green)' : state === 'blocked' ? 'var(--cyb-red)' : 'var(--cyb-cyan)';
                return (
                  <div key={i} className={`cyber-net-node ${state}`}>
                    <span style={{ fontFamily: 'var(--cyb-font-display)', fontSize: '9px', letterSpacing: '1px', minWidth: '20px' }}>
                      0{i + 1}
                    </span>
                    {n}
                    <div className="cyber-net-bar">
                      <div className="cyber-net-bar-fill" style={{ width: `${pct}%`, background: color }}></div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          
          <div className="cyber-bottom-section">
            <div className="cyber-panel-header"><span className="cyber-indicator" style={{ background: 'var(--cyb-green)', boxShadow: '0 0 8px var(--cyb-green)' }}></span>SYSTEM LOG</div>
            <div className="cyber-log-stream">
              {logs.map((l) => (
                <div key={l.id} className="cyber-log-line">
                  <span className="cyb-ts">{l.ts}</span>
                  <span className={`cyb-lvl ${l.level}`}>{l.level.toUpperCase()}</span>
                  {l.msg}
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          </div>
          
          <div className="cyber-bottom-section">
            <div className="cyber-panel-header"><span className="cyber-indicator" style={{ background: 'var(--cyb-amber)', boxShadow: '0 0 8px var(--cyb-amber)' }}></span>METRICS</div>
            <div className="cyber-metrics-grid">
              <div className="cyber-metric-card"><div className="cyber-metric-val" style={{ color: 'var(--cyb-cyan)' }}>{metrics.packets.toLocaleString()}</div><div className="cyber-metric-label">Packets</div></div>
              <div className="cyber-metric-card"><div className="cyber-metric-val" style={{ color: 'var(--cyb-green)' }}>{metrics.vulns.toLocaleString()}</div><div className="cyber-metric-label">Vulns Found</div></div>
              <div className="cyber-metric-card"><div className="cyber-metric-val" style={{ color: 'var(--cyb-amber)' }}>{metrics.latency}ms</div><div className="cyber-metric-label">Latency</div></div>
              <div className="cyber-metric-card"><div className="cyber-metric-val" style={{ color: 'var(--cyb-purple)' }}>{metrics.threads.toLocaleString()}</div><div className="cyber-metric-label">Threads</div></div>
            </div>
          </div>
        </div>
      </div>

      {accessFlash && (
        <div className="cyber-access-overlay show">
          <div className={`cyber-access-badge ${accessFlash.status}`}>
            {accessFlash.label}
          </div>
        </div>
      )}
    </div>
  );
}
