import { useEffect } from 'react'

type KeyboardShortcut = {
  key: string
  ctrl?: boolean
  meta?: boolean
  shift?: boolean
  alt?: boolean
  action: () => void
  description?: string
}

export function useKeyboardShortcuts(shortcuts: KeyboardShortcut[]) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      for (const shortcut of shortcuts) {
        const ctrlMatch = shortcut.ctrl ? e.ctrlKey : !e.ctrlKey
        const metaMatch = shortcut.meta ? e.metaKey : !e.metaKey
        const shiftMatch = shortcut.shift ? e.shiftKey : !e.shiftKey
        const altMatch = shortcut.alt ? e.altKey : !e.altKey
        const keyMatch = e.key.toLowerCase() === shortcut.key.toLowerCase()

        if (ctrlMatch && metaMatch && shiftMatch && altMatch && keyMatch) {
          e.preventDefault()
          shortcut.action()
          return
        }
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [shortcuts])
}

export const DEFAULT_SHORTCUTS: KeyboardShortcut[] = [
  { key: '/', ctrl: true, action: () => console.log('Search'), description: 'Search' },
  { key: 'k', meta: true, action: () => console.log('Command palette'), description: 'Command palette' },
  { key: 'Escape', action: () => console.log('Close'), description: 'Close dialog' },
]

export function KeyboardShortcutsHelp() {
  return (
    <div className="space-y-2 text-sm">
      {DEFAULT_SHORTCUTS.map((s, i) => (
        <div key={i} className="flex items-center justify-between">
          <span>{s.description}</span>
          <kbd className="rounded bg-muted px-2 py-1 text-xs">
            {s.ctrl ? 'Ctrl+' : ''}
            {s.meta ? 'Cmd+' : ''}
            {s.shift ? 'Shift+' : ''}
            {s.key}
          </kbd>
        </div>
      ))}
    </div>
  )
}
