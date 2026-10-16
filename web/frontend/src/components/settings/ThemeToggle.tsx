import { Moon, Sun } from 'lucide-react'
import { useTheme } from '@/lib/theme'

export function ThemeToggle() {
  const { dark, setTheme } = useTheme()
  return <button onClick={() => setTheme(dark ? 'light' : 'dark')} aria-label={dark ? 'Use light mode' : 'Use dark mode'} className="rounded-xl border border-border p-2.5 hover:bg-muted/10">
    {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
  </button>
}
