import { useState } from 'react'
import { motion } from 'framer-motion'
import { MessageCircle, Send } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'

export function FeedbackWidget() {
  const [isOpen, setIsOpen] = useState(false)
  const [message, setMessage] = useState('')
  const [sent, setSent] = useState(false)

  const handleSend = () => {
    if (message.trim()) {
      // In production, send to backend
      console.log('Feedback:', message)
      setSent(true)
      setTimeout(() => {
        setIsOpen(false)
        setSent(false)
        setMessage('')
      }, 1500)
    }
  }

  return (
    <>
      <motion.button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-20 right-4 flex h-10 w-10 items-center justify-center rounded-full bg-secondary text-secondary-foreground shadow-lg md:bottom-4"
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.9 }}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
      >
        <MessageCircle className="h-5 w-5" />
      </motion.button>

      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{sent ? 'Thanks!' : 'Send Feedback'}</DialogTitle>
          </DialogHeader>

          {sent ? (
            <motion.div
              initial={{ opacity: 0, scale: 0.5 }}
              animate={{ opacity: 1, scale: 1 }}
              className="py-8 text-center"
            >
              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-accent/10">
                <MessageCircle className="h-6 w-6 text-accent" />
              </div>
              <p className="text-muted-foreground">Your feedback helps improve Voice Journal!</p>
            </motion.div>
          ) : (
            <div className="space-y-4">
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Share your thoughts, report bugs, or suggest features..."
                className="min-h-[120px] w-full rounded-lg border border-input bg-background p-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setIsOpen(false)}>
                  Cancel
                </Button>
                <Button onClick={handleSend} disabled={!message.trim()}>
                  <Send className="mr-2 h-4 w-4" />
                  Send
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
