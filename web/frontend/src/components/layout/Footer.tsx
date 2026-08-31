import { motion } from 'framer-motion'
import { Mic, Heart } from 'lucide-react'

export function Footer() {
  return (
    <motion.footer
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: 0.5 }}
      className="border-t border-border/50 bg-card/50 py-6"
    >
      <div className="container flex flex-col items-center justify-between gap-4 md:flex-row">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Mic className="h-4 w-4" />
          <span>Voice Journal v2.0</span>
        </div>
        <div className="flex items-center gap-1 text-sm text-muted-foreground">
          <span>Made with</span>
          <Heart className="h-3 w-3 fill-rose-500 text-rose-500" />
          <span>for personal reflection</span>
        </div>
      </div>
    </motion.footer>
  )
}
