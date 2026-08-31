import { useEffect, useState } from 'react'
import { subscribeToLiveUpdates } from '@/lib/api'
import { useQueryClient } from '@tanstack/react-query'
import { Conversation, Stats } from '@/lib/api'

type LiveStatus = 'connected' | 'reconnecting' | 'disconnected'

export function useLiveUpdates() {
  const [status, setStatus] = useState<LiveStatus>('connected')
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const queryClient = useQueryClient()

  useEffect(() => {
    const unsubscribe = subscribeToLiveUpdates(
      (data) => {
        setLastUpdate(new Date())

        if (data.type === 'new_conversation' && data.conversation) {
          // Invalidate conversations query to refetch
          queryClient.invalidateQueries({ queryKey: ['conversations'] })
          queryClient.invalidateQueries({ queryKey: ['stats'] })
          queryClient.invalidateQueries({ queryKey: ['weekly'] })
          queryClient.invalidateQueries({ queryKey: ['shivangi'] })
        }
      },
      () => {
        setStatus('reconnecting')
        setTimeout(() => setStatus('connected'), 5000)
      }
    )

    return unsubscribe
  }, [queryClient])

  return { status, lastUpdate }
}
