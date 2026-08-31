import { motion } from 'framer-motion'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getChangeIndicator } from '../dashboard/StatsChangeIndicator'

interface StatChangeProps {
  current: number
  previous: number
  showPercent?: boolean
}

export function StatChange({ current, previous, showPercent = true }: StatChangeProps) {
  const { direction, percent } = getChangeIndicator(current, previous)

  if (direction === 'neutral') {
    return (
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        <Minus className="h-3 w-3" />
        No change
      </span>
    )
  }

  const Icon = direction === 'up' ? TrendingUp : TrendingDown
  const colorClass = direction === 'up' ? 'text-accent' : 'text-secondary'

  return (
    <motion.span
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn('flex items-center gap-1 text-xs font-medium', colorClass)}
    >
      <Icon className="h-3 w-3" />
      {showPercent && `${percent.toFixed(0)}%`}
    </motion.span>
  )
}
