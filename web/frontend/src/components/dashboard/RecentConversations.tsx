import { motion } from 'framer-motion'
import { ChevronRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Conversation } from '@/lib/api'
import { formatTime, formatDuration } from '@/lib/utils'

interface RecentConversationsProps {
  conversations: Conversation[]
  isLoading?: boolean
}

export function RecentConversations({ conversations, isLoading }: RecentConversationsProps) {
  const navigate = useNavigate()

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Recent Conversations</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-20 animate-pulse rounded-lg bg-muted/20" />
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (conversations.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Recent Conversations</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <p className="text-muted-foreground">No conversations yet today.</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Start speaking to create your first entry!
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Recent Conversations</CardTitle>
        <button
          onClick={() => navigate('/conversations')}
          className="flex items-center gap-1 text-sm text-primary hover:underline"
        >
          View all
          <ChevronRight className="h-4 w-4" />
        </button>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {conversations.slice(0, 5).map((conv, index) => (
            <motion.div
              key={conv.conversation_id}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.05 }}
              onClick={() => navigate(`/conversations/${conv.conversation_id}`)}
              className="flex cursor-pointer items-center justify-between rounded-lg border border-transparent p-3 transition-all hover:border-border hover:bg-muted/5"
            >
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">
                    {formatTime(conv.start_time)} - {formatTime(conv.end_time)}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    ({formatDuration(conv.duration_seconds)})
                  </span>
                </div>
                <p className="mt-1 text-sm text-muted-foreground line-clamp-1">
                  {conv.summary || 'No summary'}
                </p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {conv.is_shivangi_conversation && (
                    <Badge variant="shivangi">♥ Shivangi</Badge>
                  )}
                  {conv.quality && conv.quality !== 'not_applicable' && (
                    <Badge variant={conv.quality === 'good' ? 'quality_good' : 'quality_tense'}>
                      {conv.quality}
                    </Badge>
                  )}
                  {conv.languages?.map((lang) => (
                    <Badge key={lang} variant="outline">
                      {lang}
                    </Badge>
                  ))}
                </div>
              </div>
              <ChevronRight className="h-5 w-5 text-muted-foreground" />
            </motion.div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
