import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Dashboard } from '@/pages/Dashboard'
import { Conversations } from '@/pages/Conversations'
import { Settings } from '@/pages/Settings'
import { PageLayout } from '@/components/layout/PageLayout'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30000,
      refetchOnWindowFocus: false,
    },
  },
})

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <PageLayout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/conversations" element={<Conversations />} />
            <Route path="/conversations/:id" element={<Conversations />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </PageLayout>
      </Router>
    </QueryClientProvider>
  )
}

export default App
