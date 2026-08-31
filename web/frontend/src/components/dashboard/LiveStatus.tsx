import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { subscribeToLiveUpdates } from '@/lib/api'
import { cn } from '@/lib/utils'

type ConnectionStatus = 'connected' | 'reconnecting' | 'disconnected'

export function LiveStatus() {
  const [status, setStatus] = useState<ConnectionStatus>('connected')
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  useEffect(() => {
    const unsubscribe = subscribeToLiveUpdates(
      (data) => {
        if (data.type === 'heartbeat' || data.type === 'connected') {
          setStatus('connected')
          setLastUpdate(new Date())
        }
      },
      () => {
        setStatus('reconnecting')
        // Try to reconnect after 5s
        setTimeout(() => setStatus('connected'), 5000)
      }
    )

    return unsubscribe
  }, [])

  return (
    <div className="flex items-center gap-2">
      <motion.div
        animate={{
          scale: status === 'connected' ? [1, 1.15, 1] : 1,
          opacity: status === 'connected' ? 1 : 0.5,
        }}
        transition={{
          scale: { repeat: Infinity, duration: 2, ease: 'easeInOut' },
        }}
        className={cn(
          'h-2.5 w-2.5 rounded-full',
          status === 'connected' && 'bg-accent',
          status === 'reconnecting' && 'bg-secondary',
          status === 'disconnected' && 'bg-muted'
        )}
      />
      <span className="text-sm font-medium text-muted-foreground">
        {status === 'connected' && 'Live'}
        {status === 'reconnecting' && 'Reconnecting...'}
        {status === 'disconnected' && 'Offline'}
      </span>
    </div>
  )
}
