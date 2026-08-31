export const APP_NAME = 'Voice Journal'
export const APP_VERSION = '2.0.0'

export const NAV_ITEMS = [
  { path: '/', label: 'Dashboard', icon: 'Home' },
  { path: '/conversations', label: 'Journal', icon: 'BookOpen' },
  { path: '/settings', label: 'Settings', icon: 'Settings' },
] as const

export const QUALITY_LABELS: Record<string, string> = {
  good: '😊 Good',
  tense: '😔 Tense',
  neutral: '😐 Neutral',
}

export const LANGUAGE_LABELS: Record<string, string> = {
  hi: 'Hindi',
  en: 'English',
  'hi-en': 'Hinglish',
}

export const REFRESH_INTERVALS = {
  stats: 30000, // 30s
  conversations: 30000, // 30s
  weekly: 60000, // 1min
  backlog: 60000, // 1min
  live: 2000, // 2s (SSE)
} as const

export const API_CACHE_CONFIG = {
  staleTime: 30000,
  gcTime: 300000, // 5 minutes
  retry: 1,
  refetchOnWindowFocus: false,
} as const
