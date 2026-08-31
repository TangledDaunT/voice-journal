import { motion } from 'framer-motion'
import { Heart, Clock, TrendingUp, TrendingDown } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { ShivangiStats } from '@/lib/api'

interface ShivangiPanelProps {
  stats: ShivangiStats | null
}

export function ShivangiPanel({ stats }: ShivangiPanelProps) {
  const cards = [
    {
      label: 'This Month',
      value: stats?.total_conversations ?? 0,
      icon: Heart,
      color: 'text-rose-500',
    },
    {
      label: 'Minutes Together',
      value: stats?.total_duration_minutes ?? 0,
      icon: Clock,
      color: 'text-secondary',
    },
    {
      label: 'Good Moments',
      value: stats?.good_count ?? 0,
      icon: TrendingUp,
      color: 'text-accent',
    },
    {
      label: 'Tense Moments',
      value: stats?.tense_count ?? 0,
      icon: TrendingDown,
      color: 'text-secondary',
    },
  ]

  return (
    <Card className="overflow-hidden bg-gradient-to-br from-rose-50 to-amber-50 dark:from-rose-900/20 dark:to-amber-900/20">
      <CardContent className="p-6">
        <div className="mb-6 flex items-center gap-2">
          <motion.div
            animate={{ scale: [1, 1.15, 1] }}
            transition={{ repeat: Infinity, duration: 1.5 }}
          >
            <Heart className="h-5 w-5 fill-rose-500 text-rose-500" />
          </motion.div>
          <h3 className="font-display text-lg font-semibold text-rose-700 dark:text-rose-300">
            Shivangi Conversations
          </h3>
        </div>

        <div className="grid grid-cols-2 gap-4">
          {cards.map((card, index) => {
            const Icon = card.icon
            return (
              <motion.div
                key={card.label}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: index * 0.1 }}
              >
                <Card className="border-rose-100 bg-white/50 dark:border-rose-800 dark:bg-white/5">
                  <CardContent className="p-4">
                    <div className="flex items-center gap-2">
                      <Icon className={`h-4 w-4 ${card.color}`} />
                      <span className="text-xs font-medium text-muted-foreground">
                        {card.label}
                      </span>
                    </div>
                    <p className={`mt-2 text-2xl font-bold ${card.color}`}>
                      {card.value.toLocaleString()}
                    </p>
                  </CardContent>
                </Card>
              </motion.div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
