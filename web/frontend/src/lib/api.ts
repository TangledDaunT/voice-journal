const API_BASE = '/api'

export interface Conversation {
  turns?: { start_ts: string; end_ts: string; text: string; speaker: string; status: string }[]
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
  review_flags?: string[]
  full_audio_url?: string | null
  original_audio_url?: string | null
  engine?: string
  status?: string
  segment_id?: string | null
  audio_url?: string | null
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
  invalid_segments?: number
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

// Mute API
export const muteApi = {
  getStatus: () => apiJson<{ muted: boolean }>('/mute/status'),

  toggle: () =>
    apiJson<{ muted: boolean }>('/mute', { method: 'POST' }),
}

export async function fetchStorageStatus(): Promise<{ available: boolean; error?: string }> {
  const response = await fetch(`${API_BASE}/storage`)
  const data = await response.json()
  if (!response.ok && response.status !== 503) throw new Error('Storage status unavailable')
  return data
}

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init)
  const data = await response.json()
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`)
  return data
}

export interface RuntimeStatus {
  capture: { vad_worker_alive?: boolean; capture_worker_alive?: boolean; capture_stalled?: boolean; input_overflows?: number; capture_queue_depth?: number; vad_queue_depth?: number; input_card?: string; input_jack_control?: string; selected_device?: string; device_error?: string; fresh?: boolean; stream_active?: boolean; muted?: boolean; captured_chunks?: number; input_rms_db?: number; vad_segments_detected?: number; segments_staged?: number; last_audio_at?: string }
  processing: { status?: string; engine?: string; last_error?: string; last_success_at?: string; last_latency_seconds?: number }
  usage: { requests: number; audio_seconds: number; billed_seconds: number }
  speakers?: { enabled: number; excluded_sources: number }
  enrolled_only?: boolean
  groq_configured: boolean
  quarantined_files: number
}
export const fetchRuntime = () => apiJson<RuntimeStatus>('/runtime')
export const dataApi = {
  csvUrl: `${API_BASE}/data/export.csv`,
  zipUrl: `${API_BASE}/data/export.zip`,
  templateUrl: `${API_BASE}/data/template.csv`,
  importCsv: (file: File) => { const body = new FormData(); body.append('file', file); return apiJson<{ imported: number; duplicates: number }>('/data/import', { method: 'POST', body }) },
  clear: (confirmation: string) => apiJson<{ cleared: boolean }>('/data/clear', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ confirmation }) }),
  testGroq: () => apiJson<{ ok: boolean; configured: boolean; status?: number }>('/groq/test', { method: 'POST' }),
}

export interface SpeakerProfile {
  id: string
  name: string
  enabled: boolean
  model: string
  recorded_seconds: number
  voiced_seconds: number
  updated_at: string
  quality: { self_consistency?: number; prototype_count?: number; accuracy_verified?: boolean }
}
export interface EnrollmentState {
  id?: string
  name?: string
  status: 'idle' | 'queued' | 'recording' | 'analyzing' | 'complete' | 'error' | 'cancelled'
  seconds_recorded?: number
  input_rms_db?: number
  error?: string
  profile?: { name: string; id: string }
}
export interface SpeakerStatus {
  profiles: SpeakerProfile[]
  model_installed: boolean
  enrolled_only: boolean
  enrollment: EnrollmentState
  similarity_threshold: number
  similarity_margin: number
}
export const speakerApi = {
  list: () => apiJson<SpeakerStatus>('/speakers'),
  enroll: (name: string) => apiJson<EnrollmentState>('/speakers/enroll', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) }),
  progress: () => apiJson<EnrollmentState>('/speakers/enrollment'),
  cancel: () => apiJson<{ cancelled: boolean }>('/speakers/enrollment/cancel', { method: 'POST' }),
  setEnabled: (id: string, enabled: boolean) => apiJson<{ enabled: boolean }>(`/speakers/${encodeURIComponent(id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }) }),
}

export const microphoneApi = {
  listen: (enabled: boolean) => apiJson<{ listening: boolean }>('/microphone/listen', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }) }),
  audio: (after: string, signal: AbortSignal) => fetch(`${API_BASE}/microphone/audio?after=${encodeURIComponent(after)}`, { cache: 'no-store', signal }),
}
