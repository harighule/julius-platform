import { Link, useLocation } from 'react-router-dom'

interface Props {
  onLogout: () => void
  username?: string
  role?: string
}

const NAV = [
  { path: '/', icon: 'D', label: 'Dashboard' },
  { path: '/guardian', icon: '🛡', label: 'Guardian' },
  { path: '/scanner', icon: 'N', label: 'Scanner' },
  { path: '/exploits', icon: 'X', label: 'Exploits' },
  { path: '/behavioral', icon: 'B', label: 'Behavioral' },
  { path: '/monitor', icon: 'M', label: 'Monitor' },
  { path: '/identity', icon: 'I', label: 'Identity' },
  { path: '/darkweb', icon: 'W', label: 'Dark Web' },
  { path: '/threat-feeds', icon: 'T', label: 'Threat Feeds' },
  { path: '/signals', icon: 'S', label: 'Signals' },
  { path: '/stratum', icon: 'O', label: 'Stratum' },
  { path: '/events', icon: 'E', label: 'Events' },
  { path: '/files', icon: 'F', label: 'Files' },
  { path: '/insights', icon: 'R', label: 'Insights' },
  { path: '/tools', icon: 'U', label: 'Tools' },
  { path: '/terminal', icon: 'C', label: 'Terminal' },
  { path: '/pantheon', icon: 'P', label: 'Pantheon' },
  { path: '/settings', icon: 'G', label: 'Settings' },
  { path: '/chat', icon: 'A', label: 'AI Chat' },
  { path: '/ai-systems', icon: 'K', label: 'AI Systems' },
  { path: '/veil', icon: 'V', label: 'Veil' },
  { path: '/intelligence', icon: '◈', label: 'Intelligence' },
  { path: '/leads', icon: '🏢', label: 'B2B Leads' },
  { path: '/bgp-mitm', icon: '⚡', label: 'BGP MITM' },
]


export function Sidebar({ onLogout, username, role }: Props) {
  const location = useLocation()

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/'
    return location.pathname.startsWith(path)
  }

  return (
    <div className="h-full w-56 shrink-0 border-r border-julius-border bg-julius-surface flex flex-col">
      <div className="relative overflow-hidden border-b border-julius-border bg-julius-surface2/50 px-5 py-6">
        <div className="absolute left-0 top-0 h-full w-1 bg-julius-accent shadow-[0_0_10px_rgba(0,212,255,0.5)]"></div>
        <div className="font-display text-xl font-black tracking-[0.2em] text-julius-accent glow-cyan">JULIUS</div>
        <div className="mt-1 font-mono text-[8px] uppercase tracking-[0.3em] text-julius-muted">
          Terminal Interface v3.1
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto py-4 scrollbar-hide">
        {NAV.map((item) => {
          const active = isActive(item.path)
          const isEmoji = item.icon.length > 1
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`group relative flex w-full items-center gap-3 px-5 py-3 text-[11px] transition-all ${
                active
                  ? 'bg-julius-accent/10 text-julius-accent'
                  : 'text-julius-muted hover:bg-julius-surface2 hover:text-julius-text'
              }`}
            >
              {active && (
                <div className="absolute left-0 top-1/2 h-2/3 w-1 -translate-y-1/2 bg-julius-accent shadow-[0_0_8px_var(--color-julius-accent)]" />
              )}
              <span
                className={`flex h-6 w-6 items-center justify-center rounded-full border text-[11px] font-bold transition-transform group-hover:scale-110 ${
                  active
                    ? 'border-julius-accent/40 bg-julius-accent/10 glow-cyan'
                    : 'border-julius-border bg-julius-bg'
                } ${isEmoji ? 'text-[13px]' : ''}`}
              >
                {item.icon}
              </span>
              <span className="font-bold uppercase tracking-wider">{item.label}</span>
            </Link>
          )
        })}
      </nav>

      <div className="border-t border-julius-border p-4">
        <div className="mb-3 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-julius-accent/20 text-xs font-bold text-julius-accent">
            {username?.[0]?.toUpperCase() || '?'}
          </div>
          <div>
            <div className="text-xs font-medium text-julius-text">{username || 'User'}</div>
            <div className="text-[10px] capitalize text-julius-muted">{role || 'Operator'}</div>
          </div>
        </div>
        <button
          onClick={onLogout}
          className="w-full rounded border border-julius-border py-1.5 text-xs text-julius-muted transition-colors hover:border-julius-red/50 hover:text-julius-red"
        >
          Sign Out
        </button>
      </div>
    </div>
  )
}
