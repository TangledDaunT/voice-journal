import { useQuery } from '@tanstack/react-query'
import { Activity, Cloud, AlertTriangle } from 'lucide-react'
import { fetchBacklog, fetchRuntime } from '@/lib/api'
import { Card, CardContent } from '@/components/ui/card'

const labels: Record<string, string> = { enrollment_required: 'Enroll a voice in Calibration to enable transcription', calibrating: 'Recording a voice calibration sample', verifying_speaker: 'Checking for an enrolled voice before upload', background_skipped: 'Unknown or uncertain voice skipped', speaker_model_unavailable: 'Speaker model unavailable · uploads blocked', uploading: 'Uploading speech to Groq', transcribing: 'Transcribing locally', saved: 'Latest note saved', waiting_for_speech: 'Ready for speech', local_waiting_for_ac: 'Groq unavailable · local fallback waiting for AC', error: 'Processing needs attention' }
export function BacklogInfo() {
  const runtime = useQuery({ queryKey: ['runtime'], queryFn: fetchRuntime, refetchInterval: 2000 })
  const backlog = useQuery({ queryKey: ['backlog'], queryFn: fetchBacklog, refetchInterval: 3000 })
  const state = runtime.data
  const capture = state?.capture
  const workerFailed = capture?.vad_worker_alive === false || capture?.capture_worker_alive === false || capture?.capture_stalled === true
  const listening = capture?.fresh && capture.stream_active && !capture.muted && !capture.device_error && !workerFailed
  return <Card className="overflow-hidden border-primary/20">
    <CardContent className="p-5 md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex gap-3"><div className={`rounded-xl p-3 ${listening ? 'bg-accent/10 text-accent' : 'bg-muted/10 text-muted-foreground'}`}><Activity className="h-5 w-5" /></div>
          <div><p className="font-semibold">{runtime.isError ? 'Live status unavailable' : !capture?.fresh ? 'Capture status unavailable' : workerFailed ? 'Speech capture stalled · recovery needed' : capture.device_error ? capture.device_error : capture.muted ? 'Microphone muted' : listening ? 'Listening to your room' : 'Microphone stream inactive'}</p>
            <p className="mt-1 text-sm text-muted-foreground">{labels[state?.processing.status || ''] || 'Checking transcription…'}</p></div></div>
        <div className="flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary"><Cloud className="h-3.5 w-3.5" />Groq first · local fallback</div>
      </div>
      {state?.enrolled_only && <div className="mt-4 rounded-xl bg-primary/5 p-3 text-sm"><span className="font-medium">Enrolled voices only</span><span className="text-muted-foreground"> · {state.speakers?.enabled ?? 0} enabled · {state.speakers?.excluded_sources ?? 0} source clips excluded</span><a href="/calibration" className="ml-3 text-primary underline">Calibrate voices</a></div>}
      <div className="mt-6 grid grid-cols-2 gap-5 border-t border-border pt-5 md:grid-cols-4">
        <div><p className="metric-label">Input level</p><p className="mt-1 font-medium">{capture?.fresh && capture.input_rms_db !== undefined ? `${capture.input_rms_db.toFixed(0)} dBFS` : '—'}</p><div className="mt-2 h-1.5 rounded-full bg-muted/10"><div className="h-full rounded-full bg-accent transition-all" style={{ width: `${capture?.fresh ? Math.min(100, Math.max(0, (capture.input_rms_db ?? -100) + 80)) : 0}%` }} /></div></div>
        <div><p className="metric-label">Speech captured</p><p className="mt-1 font-medium">{capture?.fresh ? `${capture.vad_segments_detected ?? 0} segments` : '—'}</p></div>
        <div><p className="metric-label">Processing queue</p><p className="mt-1 font-medium">{backlog.isError ? 'Unavailable' : backlog.data ? `${backlog.data.segments_pending} segments` : '—'}</p></div>
        <div><p className="metric-label">Groq today</p><p className="mt-1 font-medium">{state ? `${state.usage.requests} requests` : '—'}</p></div>
      </div>
      {(state?.processing.last_error || backlog.data?.invalid_segments || state?.quarantined_files) ? <p role="status" className="mt-4 flex items-center gap-2 text-sm text-destructive"><AlertTriangle className="h-4 w-4 shrink-0" />{state?.processing.last_error || `${backlog.data?.invalid_segments || state?.quarantined_files} damaged old queue items need review; no audio has been invented.`}</p> : null}
      {state?.processing.last_success_at && <p className="mt-4 text-xs text-muted-foreground">Last saved {new Date(state.processing.last_success_at).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' })}{state.processing.last_latency_seconds !== undefined ? ` · processed in ${state.processing.last_latency_seconds}s` : ''}. Updates arrive after short speech clips.</p>}
    </CardContent>
  </Card>
}
