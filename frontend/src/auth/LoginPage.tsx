import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from './useAuth'

export function LoginPage() {
  const { login, isAuthenticated } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/', { replace: true })
    }
  }, [isAuthenticated, navigate])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
      navigate('/', { replace: true })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-julius-bg">
      <div className="w-full max-w-sm">
        <div className="bg-julius-surface border border-julius-border rounded-xl p-8 shadow-2xl">
          <div className="text-center mb-8">
            <div className="text-4xl font-bold tracking-wider text-julius-accent mb-1">JULIUS</div>
            <div className="text-xs tracking-[0.3em] text-julius-muted uppercase">Security Operations Platform</div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-xs text-julius-muted uppercase tracking-wider mb-1.5">Username</label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                className="w-full bg-julius-bg border border-julius-border rounded-lg px-4 py-2.5 text-sm text-julius-text focus:border-julius-accent focus:outline-none transition-colors"
                placeholder="admin"
                autoFocus
              />
            </div>
            <div>
              <label className="block text-xs text-julius-muted uppercase tracking-wider mb-1.5">Password</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full bg-julius-bg border border-julius-border rounded-lg px-4 py-2.5 text-sm text-julius-text focus:border-julius-accent focus:outline-none transition-colors"
                placeholder="********"
              />
            </div>

            {error && (
              <div className="text-julius-red text-xs text-center py-2 bg-julius-red/10 rounded-lg">{error}</div>
            )}

            <button
              type="submit"
              disabled={loading || !username || !password}
              className="w-full bg-julius-accent hover:bg-julius-accent/90 disabled:opacity-50 text-white py-2.5 rounded-lg text-sm font-medium tracking-wide transition-colors"
            >
              {loading ? 'Authenticating...' : 'ACCESS SYSTEM'}
            </button>
          </form>

          <div className="mt-6 text-center text-[10px] text-julius-muted">
            Default: admin / Admin@1234
          </div>
        </div>
      </div>
    </div>
  )
}
