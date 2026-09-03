const API_BASE = '/api'

export interface Conversation {
  id: number
  conversation_id: number
  date: string
  start_time: string
  end_time: string
  duration_seconds: number
  participants: string[]
  source_type: string
  is_shivangi_conversation: boolean
  quality: string
  languages: string[]
  summary: string | null
  transcript?: string
  raw_transcript?: string
  cleaned_transcript?: string
}

export interface Stats {
  date: string
  total_conversations: number
  with_shivangi: number
  self_talk: number
  media_flagged: number
  last_updated: string
  status: string
}

export interface WeeklyData {
  date: string
  total: number
  with_shivangi: number
  live: number
  avg_duration: number
}

export interface ShivangiStats {
  total_conversations: number
  total_duration_minutes: number
  avg_duration_seconds: number
  good_count: number
  tense_count: number
}

export interface BacklogStatus {
  total_queued_hours: number
  segments_pending: number
  overflow_threshold: number
}

export async function fetchStats(): Promise<Stats> {
  const res = await fetch(`${API_BASE}/stats`)
  if (!res.ok) throw new Error('Failed to fetch stats')
  return res.json()
}

export async function fetchConversations(date?: string, limit = 50): Promise<Conversation[]> {
  const params = new URLSearchParams()
  if (date) params.set('date', date)
  if (limit) params.set('limit', String(limit))

  const res = await fetch(`${API_BASE}/conversations?${params}`)
  if (!res.ok) throw new Error('Failed to fetch conversations')
  return res.json()
}

export async function fetchConversation(id: number): Promise<Conversation> {
  const res = await fetch(`${API_BASE}/conversation/${id}`)
  if (!res.ok) throw new Error('Failed to fetch conversation')
  return res.json()
}

export async function searchConversations(query: string): Promise<Conversation[]> {
  const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`)
  if (!res.ok) throw new Error('Failed to search conversations')
  return res.json()
}

export async function fetchWeeklySummary(): Promise<WeeklyData[]> {
  const res = await fetch(`${API_BASE}/weekly_summary`)
  if (!res.ok) throw new Error('Failed to fetch weekly summary')
  return res.json()
}

export async function fetchShivangiStats(days = 30): Promise<ShivangiStats> {
  const res = await fetch(`${API_BASE}/shivangi_stats?days=${days}`)
  if (!res.ok) throw new Error('Failed to fetch Shivangi stats')
  return res.json()
}

export async function fetchBacklog(): Promise<BacklogStatus> {
  const res = await fetch(`${API_BASE}/backlog`)
  if (!res.ok) throw new Error('Failed to fetch backlog')
  return res.json()
}

export async function fetchQualityDistribution(): Promise<{ quality: string; count: number }[]> {
  const res = await fetch(`${API_BASE}/quality_distribution`)
  if (!res.ok) throw new Error('Failed to fetch quality distribution')
  return res.json()
}

export function subscribeToLiveUpdates(
  onMessage: (data: { type: string; conversation?: Conversation; stats?: Partial<Stats> }) => void,
  onError?: (error: Error) => void
): () => void {
  const eventSource = new EventSource(`${API_BASE}/stream`)

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      onMessage(data)
    } catch (e) {
      console.error('Failed to parse SSE message', e)
    }
  }

  eventSource.onerror = () => {
    onError?.(new Error('Live update connection failed'))
  }

  return () => {
    eventSource.close()
  }
}

// Calibration API
export const calibrationApi = {
  getStatus: () => fetch(`${API_BASE}/calibration/status`).then(r => r.json()),

  getAudioDevices: () => fetch(`${API_BASE}/calibration/audio_devices`).then(r => r.json()),

  setAudioDevice: (deviceIndex: number) =>
    fetch(`${API_BASE}/calibration/set_device`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_index: deviceIndex })
    }).then(r => r.json()),

  recordSilentBaseline: () =>
    fetch(`${API_BASE}/calibration/start_silent`, { method: 'POST' }).then(r => r.json()),

  recordVoiceSample: (name: string) =>
    fetch(`${API_BASE}/calibration/start_voice`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    }).then(r => r.json()),

  testLevels: () =>
    fetch(`${API_BASE}/calibration/test_levels`, { method: 'POST' }).then(r => r.json()),

  apply: () =>
    fetch(`${API_BASE}/calibration/apply`, { method: 'POST' }).then(r => r.json()),
}
