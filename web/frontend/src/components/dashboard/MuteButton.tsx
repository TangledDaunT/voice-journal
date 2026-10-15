import { useEffect, useState } from 'react'
import { Mic, MicOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { muteApi } from '@/lib/api'

export function MuteButton() {
  const [muted, setMuted] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    // Fetch initial mute status
    muteApi.getStatus()
      .then(data => setMuted(data.muted))
      .catch(() => setMuted(false))
  }, [])

  const handleToggle = async () => {
    setLoading(true)
    try {
      const result = await muteApi.toggle()
      setMuted(result.muted)
    } catch (error) {
      console.error('Failed to toggle mute:', error)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Button
      variant="outline"
      size="icon"
      onClick={handleToggle}
      disabled={loading}
      className={muted ? 'bg-destructive/10 text-destructive border-destructive/30' : ''}
      title={muted ? 'Unmute microphone' : 'Mute microphone'}
    >
      {muted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
      <span className="sr-only">{muted ? 'Muted' : 'Listening'}</span>
    </Button>
  )
}

export function MuteStatus() {
  const [muted, setMuted] = useState(false)

  useEffect(() => {
    muteApi.getStatus()
      .then(data => setMuted(data.muted))
      .catch(() => setMuted(false))
  }, [])

  return (
    <div className="flex items-center gap-2">
      <div
        className={`h-2.5 w-2.5 rounded-full transition-colors ${
          muted ? 'bg-destructive' : 'bg-accent'
        }`}
      />
      <span className="text-sm font-medium text-muted-foreground">
        {muted ? 'Muted' : 'Listening'}
      </span>
    </div>
  )
}