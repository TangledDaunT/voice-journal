import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Dashboard } from '@/pages/Dashboard'
import { Conversations } from '@/pages/Conversations'
import { Settings } from '@/pages/Settings'
import Calibration from '@/pages/Calibration'
import AudioTestPage from '@/pages/AudioTest'
import { PageLayout } from '@/components/layout/PageLayout'
import { ErrorBoundary } from '@/components/ErrorBoundary'

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
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <Router>
          <PageLayout>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/conversations" element={<Conversations />} />
              <Route path="/conversations/:id" element={<Conversations />} />
              <Route path="/calibration" element={<Calibration />} />
              <Route path="/audio-test" element={<AudioTestPage />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </PageLayout>
        </Router>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}

export default App
