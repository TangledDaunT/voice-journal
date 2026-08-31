import { NavLink } from 'react-router-dom'
import { Home, BookOpen, Settings, ChevronLeft, ChevronRight, Mic, Sliders } from 'lucide-react'
import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'

interface SidebarProps {
  isOpen: boolean
  onToggle: () => void
}

const navItems = [
  { path: '/', label: 'Dashboard', icon: Home },
  { path: '/conversations', label: 'Journal', icon: BookOpen },
  { path: '/calibration', label: 'Calibration', icon: Sliders },
  { path: '/settings', label: 'Settings', icon: Settings },
]

export function Sidebar({ isOpen, onToggle }: SidebarProps) {
  return (
    <motion.aside
      initial={false}
      animate={{ width: isOpen ? 256 : 80 }}
      transition={{ duration: 0.2 }}
      className={cn(
        'fixed left-0 top-0 z-40 hidden h-screen border-r border-border/50 bg-card md:block',
        'flex-col'
      )}
    >
      {/* Logo */}
      <div className="flex h-16 items-center justify-between border-b border-border/50 px-4">
        <motion.div
          initial={false}
          animate={{ opacity: isOpen ? 1 : 0 }}
          transition={{ duration: 0.15 }}
          className="flex items-center gap-2"
        >
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-secondary">
            <Mic className="h-5 w-5 text-primary-foreground" />
          </div>
          {isOpen && (
            <span className="font-display text-lg font-semibold">Voice Journal</span>
          )}
        </motion.div>

        <button
          onClick={onToggle}
          className="absolute -right-3 top-5 flex h-6 w-6 items-center justify-center rounded-full border border-border bg-card shadow-sm hover:bg-muted/10"
        >
          {isOpen ? (
            <ChevronLeft className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-3">
        {navItems.map((item) => {
          const Icon = item.icon
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:bg-muted/10 hover:text-foreground'
                )
              }
            >
              <Icon className="h-5 w-5 flex-shrink-0" />
              {isOpen && <span>{item.label}</span>}
            </NavLink>
          )
        })}
      </nav>

      {/* Bottom section */}
      <div className="border-t border-border/50 p-4">
        {isOpen ? (
          <div className="text-xs text-muted-foreground">
            <p>v2.0.0 • Batch Mode</p>
            <p className="mt-1">© 2024 Voice Journal</p>
          </div>
        ) : (
          <div className="text-center text-[10px] text-muted-foreground">v2</div>
        )}
      </div>
    </motion.aside>
  )
}
