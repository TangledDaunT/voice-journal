import { lazy, Suspense } from 'react'
import { ThemeProvider } from '@/lib/theme'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PageLayout } from '@/components/layout/PageLayout'
import { ErrorBoundary } from '@/components/ErrorBoundary'

const Dashboard = lazy(() => import('@/pages/Dashboard').then(module => ({ default: module.Dashboard })))
const Conversations = lazy(() => import('@/pages/Conversations').then(module => ({ default: module.Conversations })))
const Settings = lazy(() => import('@/pages/Settings').then(module => ({ default: module.Settings })))
const Calibration = lazy(() => import('@/pages/Calibration'))
const AudioTestPage = lazy(() => import('@/pages/AudioTest'))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

function App() {
  return (
    <ThemeProvider><ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <Router>
          <PageLayout>
            <Suspense fallback={<p className="p-8 text-muted-foreground">Loading…</p>}><Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/conversations" element={<Conversations />} />
              <Route path="/conversations/:id" element={<Conversations />} />
              <Route path="/calibration" element={<Calibration />} />
              <Route path="/audio-test" element={<AudioTestPage />} />
              <Route path="/settings" element={<Settings />} />
            </Routes></Suspense>
          </PageLayout>
        </Router>
      </QueryClientProvider>
    </ErrorBoundary></ThemeProvider>
  )
}

export default App
