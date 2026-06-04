import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ApiError } from './api/client'
import { AuthProvider } from './context/AuthContext'
import { ProtectedRoute } from './components/ProtectedRoute'
import Layout from './components/layout/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Connectors from './pages/Connectors'
import ConnectorDetail from './pages/ConnectorDetail'
import Findings from './pages/Findings'
import Rules from './pages/Rules'
import Identities from './pages/Identities'
import IdentityDetail from './pages/IdentityDetail'
import Settings from './pages/Settings'
import ThirdPartyApps from './pages/ThirdPartyApps'
import Compliance from './pages/Compliance'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        // Never retry on auth failures — they won't recover.
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) return false
        return failureCount < 2
      },
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10_000),
      staleTime: 20_000,
      gcTime: 5 * 60 * 1000,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            {/* Public */}
            <Route path="/login" element={<Login />} />

            {/* Protected — all app routes require authentication */}
            <Route element={<ProtectedRoute />}>
              <Route element={<Layout />}>
                <Route index element={<Dashboard />} />
                <Route path="connectors" element={<Connectors />} />
                <Route path="connectors/:id" element={<ConnectorDetail />} />
                <Route path="findings" element={<Findings />} />
                <Route path="rules" element={<Rules />} />
                <Route path="identities" element={<Identities />} />
                <Route path="identities/:platform" element={<IdentityDetail />} />
                <Route path="third-party-apps" element={<ThirdPartyApps />} />
                <Route path="compliance" element={<Compliance />} />
                <Route path="settings" element={<Settings />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
