import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from './useAuth'
import { Sidebar } from '../components/Sidebar'
import { StatusBar } from '../components/StatusBar'
import { ChatOverlay } from '../components/ChatOverlay'

export function ProtectedRoute() {
  const { user, loading, isAuthenticated, logout } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen bg-julius-bg flex items-center justify-center">
        <div className="flex gap-2">
          {[0, 1, 2].map(i => (
            <span key={i} className="w-2 h-2 bg-julius-accent rounded-full animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
          ))}
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return (
    <div className="h-screen flex flex-col bg-julius-bg overflow-hidden">
      <StatusBar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar onLogout={logout} username={user?.username} role={user?.role} />
        <main className="flex-1 overflow-auto min-w-0">
          <Outlet />
        </main>
      </div>
      <ChatOverlay />
    </div>
  )
}
