import { Outlet, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAuth } from '../hooks/useAuth'

export const Layout = () => {
  const { logout, user } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <motion.aside
        initial={{ x: -100, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        className="w-64 glass-card border-r-0 border-t-0 border-b-0 border-l-0 flex flex-col"
      >
        {/* Logo */}
        <div className="p-6 border-b border-glass-border">
          <h1 className="text-xl font-display font-bold text-gradient">
            Structured Intelligence
          </h1>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-2">
          <NavLink to="/" icon="📊">Dashboard</NavLink>
          <NavLink to="/documents" icon="📄">Documents</NavLink>
          <NavLink to="/chat" icon="💬">Chat</NavLink>
          <NavLink to="/analytics" icon="📈">Analytics</NavLink>
          <NavLink to="/settings" icon="⚙️">Settings</NavLink>
        </nav>

        {/* User section */}
        <div className="p-4 border-t border-glass-border">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white font-medium">
              {user?.username?.[0]?.toUpperCase() || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{user?.username || 'User'}</p>
              <p className="text-xs text-gray-500 truncate">{user?.email || ''}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="w-full py-2 px-4 rounded-lg glass-button text-sm"
          >
            Logout
          </button>
        </div>
      </motion.aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}

// Simple NavLink component
const NavLink = ({ to, icon, children }) => {
  const navigate = useNavigate()
  const isActive = window.location.pathname === to

  return (
    <button
      onClick={() => navigate(to)}
      className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 ${
        isActive
          ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
          : 'text-gray-400 hover:bg-glass-hover hover:text-white'
      }`}
    >
      <span>{icon}</span>
      <span className="font-medium">{children}</span>
    </button>
  )
}
