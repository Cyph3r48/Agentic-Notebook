import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { AnimatePresence } from 'framer-motion'

import { useAuthStore } from './store/authStore'
import { Layout } from './components/Layout'
import { Login } from './pages/Login'
import { Dashboard } from './pages/Dashboard'
import { Documents } from './pages/Documents'
import { Chat } from './pages/Chat'
import { Settings } from './pages/Settings'
import { Analytics } from './pages/Analytics'

// Create React Query client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 5 * 60 * 1000, // 5 minutes
    },
  },
})

function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuthStore()
  
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  
  return children
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <div className="min-h-screen bg-dark-base">
          {/* Animated background gradient */}
          <div className="fixed inset-0 overflow-hidden pointer-events-none">
            <div className="absolute -top-1/2 -left-1/2 w-full h-full bg-gradient-to-br from-blue-500/10 via-purple-500/5 to-transparent blur-3xl animate-float" />
            <div className="absolute -bottom-1/2 -right-1/2 w-full h-full bg-gradient-to-tl from-light-blue-500/10 via-purple-500/5 to-transparent blur-3xl animate-float" style={{ animationDelay: '1s' }} />
          </div>
          
          {/* Main content */}
          <div className="relative z-10">
            <AnimatePresence mode="wait">
              <Routes>
                <Route path="/login" element={<Login />} />
                
                <Route
                  path="/*"
                  element={
                    <ProtectedRoute>
                      <Layout>
                        <Routes>
                          <Route path="/" element={<Dashboard />} />
                          <Route path="/documents" element={<Documents />} />
                          <Route path="/chat" element={<Chat />} />
                          <Route path="/chat/:conversationId" element={<Chat />} />
                          <Route path="/analytics" element={<Analytics />} />
                          <Route path="/settings" element={<Settings />} />
                          <Route path="*" element={<Navigate to="/" replace />} />
                        </Routes>
                      </Layout>
                    </ProtectedRoute>
                  }
                />
              </Routes>
            </AnimatePresence>
          </div>
          
          {/* Toast notifications */}
          <Toaster 
            position="top-right"
            theme="dark"
            toastOptions={{
              style: {
                background: 'rgba(15, 20, 25, 0.95)',
                backdropFilter: 'blur(20px)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                color: '#fff',
              },
            }}
          />
        </div>
      </Router>
    </QueryClientProvider>
  )
}

export default App
