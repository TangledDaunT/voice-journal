import { motion } from 'framer-motion'
import { Clock, Users } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Conversation } from '@/lib/api'
import { formatTime, formatDuration } from '@/lib/utils'

interface ConversationCardProps {
  conversation: Conversation
  onClick: () => void
}

export function ConversationCard({ conversation, onClick }: ConversationCardProps) {
  return (
    <motion.div
      variants={{ hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0 } }}
      whileHover={{ y: -4, transition: { duration: 0.15 } }}
      whileTap={{ scale: 0.98 }}
    >
      <Card
        onClick={onClick}
        className="cursor-pointer overflow-hidden transition-all hover:border-primary/30 hover:shadow-md"
      >
        <CardContent className="p-4">
          {/* Time Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Clock className="h-3.5 w-3.5" />
              <span>{formatTime(conversation.start_time)}</span>
              <span className="text-xs">•</span>
              <span>{formatDuration(conversation.duration_seconds)}</span>
            </div>
            {conversation.is_shivangi_conversation && (
              <Badge variant="shivangi" className="text-xs">♥</Badge>
            )}
          </div>

          {/* Summary Preview */}
          <p className="mt-3 text-sm line-clamp-2">
            {conversation.summary || 'No summary available'}
          </p>

          {/* Footer: Participants and Languages */}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {/* Participants */}
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Users className="h-3 w-3" />
              <span>{conversation.participants?.join(', ') || 'Unknown'}</span>
            </div>

            <div className="flex-1" />

            {/* Language Tags */}
            {conversation.languages?.slice(0, 2).map((lang) => (
              <Badge key={lang} variant="outline" className="text-xs px-2 py-0.5">
                {lang}
              </Badge>
            ))}

            {/* Quality Badge */}
            {conversation.quality && conversation.quality !== 'not_applicable' && (
              <Badge variant={conversation.quality === 'good' ? 'quality_good' : 'quality_tense'} className="text-xs">
                {conversation.quality}
              </Badge>
            )}
          </div>
        </CardContent>
      </Card>
    </motion.div>
  )
}
