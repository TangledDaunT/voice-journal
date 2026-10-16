import { useRef, useState } from 'react'
import { MicrophoneStudio } from '@/components/settings/MicrophoneStudio'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Cloud, Download, Upload, Trash2, Palette, Mic, CheckCircle2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useTheme } from '@/lib/theme'
import { dataApi, fetchRuntime } from '@/lib/api'

export function Settings() {
  const { theme, setTheme } = useTheme()
  const client = useQueryClient()
  const upload = useRef<HTMLInputElement>(null)
  const [confirmation, setConfirmation] = useState('')
  const [clearOpen, setClearOpen] = useState(false)
  const [notice, setNotice] = useState('')
  const runtime = useQuery({ queryKey: ['runtime'], queryFn: fetchRuntime })
  const imported = useMutation({ mutationFn: dataApi.importCsv, onSuccess: data => {
    setNotice(`Imported ${data.imported} entries; ${data.duplicates} duplicates skipped.`)
    client.invalidateQueries()
    if (upload.current) upload.current.value = ''
  } })
  const clear = useMutation({ mutationFn: dataApi.clear, onSuccess: () => {
    setClearOpen(false); setConfirmation(''); setNotice('User data cleared. The database and its schema are preserved.')
    client.resetQueries()
  } })
  const test = useMutation({ mutationFn: dataApi.testGroq })
  const error = imported.error || clear.error || test.error
  return <div className="mx-auto max-w-4xl space-y-6">
    <div className="mb-8"><p className="eyebrow">Make it yours</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">Settings</h1><p className="mt-2 text-muted-foreground">Control appearance, transcription, and your personal archive.</p></div>
    {notice && <p role="status" className="flex items-center gap-2 rounded-xl border border-accent/30 bg-accent/10 p-4 text-sm"><CheckCircle2 className="h-4 w-4" />{notice}</p>}
    {error && <p role="alert" className="rounded-xl bg-destructive/10 p-4 text-sm text-destructive">{error.message}</p>}
    <Card><CardHeader><CardTitle className="flex items-center gap-2"><Palette className="h-5 w-5 text-primary" />Appearance</CardTitle><CardDescription>Your choice applies across the dashboard and stays saved in this browser.</CardDescription></CardHeader><CardContent><div className="grid grid-cols-3 gap-3">{(['system', 'light', 'dark'] as const).map(value => <button key={value} aria-pressed={theme === value} onClick={() => setTheme(value)} className={`rounded-xl border px-3 py-4 text-sm font-medium capitalize transition ${theme === value ? 'border-primary bg-primary/10 text-primary ring-1 ring-primary' : 'border-border hover:bg-muted/10'}`}>{value === 'system' ? 'Match system' : `${value} mode`}</button>)}</div></CardContent></Card>
    <Card><CardHeader><CardTitle className="flex items-center gap-2"><Cloud className="h-5 w-5 text-primary" />Transcription</CardTitle><CardDescription>Groq is primary. Local Whisper is used only when cloud transcription is unavailable.</CardDescription></CardHeader><CardContent className="space-y-4"><div className="flex flex-wrap items-center justify-between gap-4"><div><p className="font-medium">Groq connection</p><p className="mt-1 text-sm text-muted-foreground">Key {runtime.data ? runtime.data.groq_configured ? 'configured' : 'not configured' : 'status unavailable'} · whisper-large-v3</p></div><Button variant="outline" onClick={() => test.mutate()} disabled={test.isPending}>{test.isPending ? 'Testing…' : 'Test connection'}</Button></div>{test.data && <p role="status" className={test.data.ok ? 'text-accent' : 'text-destructive'}>{test.data.ok ? 'Connection successful.' : `Connection failed (${test.data.status || 'unavailable'}).`}</p>}<p className="rounded-xl bg-muted/10 p-4 text-sm text-muted-foreground">Speech clips are transcribed throughout the day, including on battery. Local fallback waits for AC power. Enable Zero Data Retention in your Groq console Data Controls; this dashboard cannot confirm that setting.</p></CardContent></Card>
    <Card><CardHeader><CardTitle className="flex items-center gap-2"><Mic className="h-5 w-5 text-primary" />Microphone & calibration</CardTitle><CardDescription>Check your input levels or open voice calibration.</CardDescription></CardHeader><CardContent className="flex gap-3"><Button asChild variant="outline"><Link to="/audio-test">Test microphone</Link></Button><Button asChild variant="outline"><Link to="/calibration">Open calibration</Link></Button></CardContent></Card>
    <MicrophoneStudio />
    <Card><CardHeader><CardTitle>Your data</CardTitle><CardDescription>Export before deleting. CSV entries are organized by date and local time in Asia/Kolkata.</CardDescription></CardHeader><CardContent className="space-y-5"><div className="grid gap-3 sm:grid-cols-2"><Button asChild variant="outline" className="justify-start gap-2"><a href={dataApi.csvUrl}><Download className="h-4 w-4" />Export journal CSV</a></Button><Button asChild variant="outline" className="justify-start gap-2"><a href={dataApi.zipUrl}><Download className="h-4 w-4" />Export archive with audio</a></Button></div><div className="rounded-xl border border-dashed border-border p-5"><p className="font-medium">Import dated CSV</p><p className="mt-2 text-sm text-muted-foreground">Required columns: date, start_time, end_time, text. Use YYYY-MM-DD and HH:MM:SS. Optional: language, speaker, engine. Imported notes are labeled and have no attached recording.</p><div className="mt-4 flex flex-wrap items-center gap-3"><input ref={upload} aria-label="Choose journal CSV" type="file" accept=".csv,text/csv" className="max-w-full text-sm" disabled={imported.isPending} onChange={event => { const file = event.target.files?.[0]; if (file) imported.mutate(file) }} /><a className="text-sm text-primary underline" href={dataApi.templateUrl}>Download blank template</a></div>{imported.isPending && <p className="mt-2 text-sm">Importing…</p>}<Upload className="sr-only" /></div><div className="flex flex-wrap items-center justify-between gap-4 border-t border-border pt-5"><div><p className="font-medium">Clear all user data</p><p className="mt-1 text-sm text-muted-foreground">Removes notes, recordings, imports, exports, and backups. Keeps the database file and schema.</p></div><Button variant="destructive" onClick={() => setClearOpen(true)} className="gap-2"><Trash2 className="h-4 w-4" />Clear data</Button></div></CardContent></Card>
    <Dialog open={clearOpen} onOpenChange={setClearOpen}><DialogContent><DialogHeader><DialogTitle>Permanently clear your journal?</DialogTitle></DialogHeader><p className="text-sm text-muted-foreground">Download an export first. This deletes all stored user data, including audio and saved backups. New audio can be captured again immediately afterward. The SQLite file and tables remain.</p><label className="text-sm font-medium" htmlFor="clear-confirmation">Type DELETE ALL USER DATA</label><input id="clear-confirmation" className="rounded-lg border border-input bg-background p-3" value={confirmation} onChange={event => setConfirmation(event.target.value)} autoComplete="off" /><Button variant="destructive" disabled={confirmation !== 'DELETE ALL USER DATA' || clear.isPending} onClick={() => clear.mutate(confirmation)}>{clear.isPending ? 'Clearing…' : 'Permanently clear user data'}</Button>{clear.error && <p role="alert" className="text-sm text-destructive">{clear.error.message}</p>}</DialogContent></Dialog>
  </div>
}
