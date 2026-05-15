import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import Connectors from './pages/Connectors'
import ConnectorDetail from './pages/ConnectorDetail'
import Findings from './pages/Findings'
import Rules from './pages/Rules'
import Identities from './pages/Identities'
import IdentityDetail from './pages/IdentityDetail'
import Settings from './pages/Settings'
import ThirdPartyApps from './pages/ThirdPartyApps'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10_000),
      staleTime: 20_000,
      gcTime: 5 * 60 * 1000,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="connectors" element={<Connectors />} />
            <Route path="connectors/:id" element={<ConnectorDetail />} />
            <Route path="findings" element={<Findings />} />
            <Route path="rules" element={<Rules />} />
            <Route path="identities" element={<Identities />} />
            <Route path="identities/:platform" element={<IdentityDetail />} />
            <Route path="third-party-apps" element={<ThirdPartyApps />} />
            <Route path="settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
