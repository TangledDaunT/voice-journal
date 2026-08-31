import { FileCode2, Settings2, Home, BookOpen } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'

const routeLabels: Record<string, string> = {
  '/': 'Dashboard',
  '/conversations': 'Journal',
  '/settings': 'Settings',
}

const routeIcons: Record<string, React.ElementType> = {
  '/': Home,
  '/conversations': BookOpen,
  '/settings': Settings2,
}

export function Breadcrumbs() {
  const location = useLocation()
  const path = location.pathname
  const Icon = routeIcons[path] || FileCode2
  const label = routeLabels[path] || 'Page'

  return (
    <nav className="flex items-center gap-2 text-sm text-muted-foreground">
      <Link
        to="/"
        className="flex items-center gap-1 hover:text-foreground transition-colors"
      >
        <Home className="h-3.5 w-3.5" />
        <span className="hidden md:inline">Home</span>
      </Link>
      {path !== '/' && (
        <>
          <span className="text-muted-foreground/50">/</span>
          <div className="flex items-center gap-1 text-foreground">
            <Icon className="h-3.5 w-3.5" />
            <span className="hidden md:inline">{label}</span>
          </div>
        </>
      )}
    </nav>
  )
}
