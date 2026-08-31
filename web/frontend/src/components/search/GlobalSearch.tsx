import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Search, X, Loader2 } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useConversations, useSearchConversations } from '@/hooks/useConversations'
import { useDebounce } from '@/hooks/useDebounce'
import { formatTime, formatDate, formatDuration } from '@/lib/utils'
import { Conversation } from '@/lib/api'
import { useNavigate } from 'react-router-dom'

export function GlobalSearch() {
  const [query, setQuery] = useState('')
  const [isOpen, setIsOpen] = useState(false)
  const debouncedQuery = useDebounce(query, 300)
  const navigate = useNavigate()

  const { data: results, isLoading } = useSearchConversations(debouncedQuery)

  const handleSelect = (conv: Conversation) => {
    setIsOpen(false)
    setQuery('')
    navigate(`/conversations/${conv.conversation_id}`)
  }

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="flex items-center gap-2 rounded-lg border border-input bg-background/50 px-3 py-1.5 text-sm text-muted-foreground hover:bg-background w-64"
      >
        <Search className="h-4 w-4" />
        <span>Search conversations...</span>
        <kbd className="ml-auto text-xs bg-muted px-1.5 py-0.5 rounded hidden md:inline-block">⌘K</kbd>
      </button>

      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Search Conversations</DialogTitle>
          </DialogHeader>

          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Type to search..."
              className="w-full rounded-lg border border-input bg-background py-2 pl-10 pr-10 focus:outline-none focus:ring-2 focus:ring-ring"
              autoFocus
            />
            {query && (
              <button
                onClick={() => setQuery('')}
                className="absolute right-3 top-1/2 -translate-y-1/2"
              >
                <X className="h-4 w-4 text-muted-foreground" />
              </button>
            )}
          </div>

          <div className="max-h-80 overflow-y-auto">
            {isLoading && query.length > 2 && (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            )}

            {results && results.length === 0 && query.length > 2 && (
              <p className="py-8 text-center text-muted-foreground">No results found</p>
            )}

            <AnimatePresence>
              {results?.map((conv) => (
                <motion.button
                  key={conv.conversation_id}
                  onClick={() => handleSelect(conv)}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="w-full rounded-lg p-3 text-left hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{formatDate(conv.date)}</span>
                    <span className="text-xs text-muted-foreground">{formatTime(conv.start_time)}</span>
                  </div>
                  <p className="text-sm text-muted-foreground line-clamp-2">
                    {conv.summary || 'No summary'}
                  </p>
                </motion.button>
              ))}
            </AnimatePresence>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
