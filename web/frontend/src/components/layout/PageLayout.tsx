import { useQuery } from '@tanstack/react-query'
import { fetchStorageStatus } from '@/lib/api'
import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { Header } from './Header'
import { Sidebar } from './Sidebar'
import { MobileNav } from './MobileNav'
import { Footer } from './Footer'

interface PageLayoutProps {
  children: React.ReactNode
}

export function PageLayout({ children }: PageLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const location = useLocation()
  const storage = useQuery({ queryKey: ['storage'], queryFn: fetchStorageStatus, refetchInterval: 10000 })

  return (
    <div className="min-h-screen bg-background">
      {/* Desktop Sidebar */}
      <Sidebar isOpen={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />

      {/* Main Content */}
      <div
        className={cn(
          'transition-all duration-300',
          sidebarOpen ? 'md:ml-64' : 'md:ml-20'
        )}
      >
        <Header onMenuClick={() => setSidebarOpen(!sidebarOpen)} />

        {(storage.isError || storage.data?.available === false) && (
          <div role="alert" className="bg-destructive p-4 font-semibold text-destructive-foreground">
            {storage.data?.error || 'Storage status unavailable. Check the journal drive.'}
          </div>
        )}
        <main className="min-h-[calc(100vh-8rem)] p-4 md:p-6 lg:p-8 pb-20 md:pb-8">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
          >
            {children}
          </motion.div>
        </main>

        <Footer />
      </div>

      {/* Mobile Bottom Navigation */}
      <MobileNav />
    </div>
  )
}
