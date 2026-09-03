import { useState } from 'react'
import { motion } from 'framer-motion'
import { Search, Calendar, X } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { fetchConversations, fetchConversation, searchConversations, Conversation } from '@/lib/api'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { formatTime, formatDuration, formatDate } from '@/lib/utils'
import { ConversationCard } from '@/components/conversations/ConversationCard'

export function Conversations() {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedDate, setSelectedDate] = useState<string>('')
  const [selectedConv, setSelectedConv] = useState<Conversation | null>(null)

  const { data: conversations, isLoading } = useQuery({
    queryKey: ['conversations', selectedDate],
    queryFn: () => fetchConversations(selectedDate || undefined, 200),
  })

  const { data: searchResults, isLoading: searchLoading } = useQuery({
    queryKey: ['search', searchQuery],
    queryFn: () => searchConversations(searchQuery),
    enabled: searchQuery.length > 2,
  })

  const displayConversations = searchQuery.length > 2 ? searchResults : conversations

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold">Journal</h1>
          <p className="text-muted-foreground">All your conversations in one place</p>
        </div>

        <div className="flex gap-2">
          <div className="relative flex-1 md:w-80">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search conversations..."
              className="w-full rounded-lg border border-input bg-background py-2 pl-10 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-3 top-1/2 -translate-y-1/2"
              >
                <X className="h-4 w-4 text-muted-foreground hover:text-foreground" />
              </button>
            )}
          </div>

          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
      </div>

      {/* Conversations List */}
      {isLoading || searchLoading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="h-40 animate-pulse rounded-lg bg-muted/20" />
          ))}
        </div>
      ) : displayConversations?.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <Calendar className="h-12 w-12 text-muted-foreground/50" />
            <p className="mt-4 text-lg font-medium">No conversations found</p>
            <p className="text-muted-foreground">
              {searchQuery ? 'Try a different search term' : 'No entries for this date'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <motion.div
          className="grid gap-4 md:grid-cols-2 lg:grid-cols-3"
          initial="hidden"
          animate="visible"
          variants={{
            visible: { transition: { staggerChildren: 0.05 } },
          }}
        >
          {displayConversations?.map((conv) => (
            <ConversationCard
              key={conv.conversation_id}
              conversation={conv}
              onClick={async () => setSelectedConv(await fetchConversation(conv.conversation_id))}
            />
          ))}
        </motion.div>
      )}

      {/* Detail Modal */}
      <Dialog open={!!selectedConv} onOpenChange={() => setSelectedConv(null)}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
          {selectedConv && (
            <>
              <DialogHeader>
                <DialogTitle>
                  {formatDate(selectedConv.date)} at {formatTime(selectedConv.start_time)}
                </DialogTitle>
              </DialogHeader>

              <div className="space-y-4">
                {/* Meta */}
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">{formatDuration(selectedConv.duration_seconds)}</Badge>
                  {selectedConv.participants?.map((p) => (
                    <Badge key={p} variant="secondary">{p}</Badge>
                  ))}
                  {selectedConv.languages?.map((l) => (
                    <Badge key={l}>{l}</Badge>
                  ))}
                  {selectedConv.is_shivangi_conversation && (
                    <Badge variant="shivangi">♥ Shivangi</Badge>
                  )}
                </div>

                {/* Summary */}
                {selectedConv.summary && (
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground">Summary</h4>
                    <p className="mt-1">{selectedConv.summary}</p>
                  </div>
                )}

                {/* Transcript */}
                {(selectedConv.cleaned_transcript || selectedConv.transcript) && (
                  <div>
                    <h4 className="mb-2 text-sm font-medium text-muted-foreground">Cleaned Transcript</h4>
                    <pre className="whitespace-pre-wrap rounded-lg bg-muted/30 p-4 font-mono text-sm">
                      {selectedConv.cleaned_transcript || selectedConv.transcript}
                    </pre>
                  </div>
                )}
                {selectedConv.audio_url && (
                  <audio className="w-full" controls preload="metadata" src={selectedConv.audio_url} />
                )}
                {(selectedConv.raw_transcript || selectedConv.transcript) && (
                  <details>
                    <summary className="cursor-pointer text-sm font-medium text-muted-foreground">Raw Transcript</summary>
                    <pre className="mt-2 whitespace-pre-wrap rounded-lg bg-muted/30 p-4 font-mono text-sm">
                      {selectedConv.raw_transcript || selectedConv.transcript}
                    </pre>
                  </details>
                )}
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
