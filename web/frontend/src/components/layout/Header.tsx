import { Menu, AudioLines } from 'lucide-react'
import { useLocation } from 'react-router-dom'
import { ThemeToggle } from '@/components/settings/ThemeToggle'
import { MuteButton } from '@/components/dashboard/MuteButton'

export function Header({ onMenuClick }: { onMenuClick: () => void }) {
  const { pathname } = useLocation()
  const title = pathname.startsWith('/conversations') ? 'Your journal' : pathname === '/settings' ? 'Settings' : 'Voice Journal'
  return <header className="sticky top-0 z-30 border-b border-border bg-background/95 backdrop-blur-md">
    <div className="flex min-h-20 items-center justify-between gap-3 px-4 md:px-8">
      <div className="flex items-center gap-3">
        <button onClick={onMenuClick} aria-label="Toggle navigation" className="rounded-lg p-2 md:hidden"><Menu className="h-5 w-5" /></button>
        <AudioLines className="hidden h-5 w-5 text-primary sm:block" />
        <p className="text-sm font-semibold tracking-wide">{title}</p>
      </div>
      <div className="flex items-center gap-2"><ThemeToggle /><MuteButton /></div>
    </div>
  </header>
}
