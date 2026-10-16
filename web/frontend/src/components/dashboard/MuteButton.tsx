import { useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Mic, MicOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { muteApi } from '@/lib/api'

export function MuteButton() {
  const client = useQueryClient()
  const status = useQuery({ queryKey: ['mute'], queryFn: muteApi.getStatus, refetchInterval: 3000 })
  const toggle = useMutation({ mutationFn: muteApi.toggle, onSuccess: data => { client.setQueryData(['mute'], data); client.invalidateQueries({ queryKey: ['runtime'] }) } })
  const act = toggle.mutate
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.shiftKey && event.code === 'KeyM') { event.preventDefault(); act() }
    }
    window.addEventListener('keydown', listener)
    return () => window.removeEventListener('keydown', listener)
  }, [act])
  const muted = status.data?.muted
  return <div>
    <Button variant={muted ? 'destructive' : 'default'} disabled={status.isLoading || status.isError || toggle.isPending} onClick={() => toggle.mutate()} className="gap-2 rounded-xl" title="Ctrl+Shift+M">
      {muted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
      {status.isError ? 'Mic unavailable' : muted ? 'Unmute' : 'Mute microphone'}
    </Button>
    {toggle.isError && <p role="alert" className="text-xs text-destructive">Mute failed. Try again.</p>}
  </div>
}

export function MuteStatus() {
  const state = useQuery({ queryKey: ['mute'], queryFn: muteApi.getStatus, refetchInterval: 3000 })
  return <span className="text-sm text-muted-foreground">{state.isError ? 'Mic status unavailable' : state.data?.muted === true ? 'Muted' : state.data?.muted === false ? 'Unmuted' : 'Checking microphone…'}</span>
}
