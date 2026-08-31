import { motion } from 'framer-motion'
import { MessageCircle, Heart, User, Volume2 } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Stats } from '@/lib/api'

interface StatsGridProps {
  stats: Stats | null
}

const statCards = [
  {
    key: 'total_conversations',
    label: "Today's Conversations",
    icon: MessageCircle,
    color: 'text-primary',
    bg: 'bg-primary/10',
  },
  {
    key: 'with_shivangi',
    label: 'With Shivangi',
    icon: Heart,
    color: 'text-rose-500',
    bg: 'bg-rose-100',
  },
  {
    key: 'self_talk',
    label: 'Self Talk',
    icon: User,
    color: 'text-secondary',
    bg: 'bg-secondary/10',
  },
  {
    key: 'media_flagged',
    label: 'Media Flagged',
    icon: Volume2,
    color: 'text-muted-foreground',
    bg: 'bg-muted/20',
  },
] as const

export function StatsGrid({ stats }: StatsGridProps) {
  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
      {statCards.map((card, index) => {
        const Icon = card.icon
        const value = stats ? stats[card.key] : 0

        return (
          <motion.div
            key={card.key}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
          >
            <Card className="relative overflow-hidden">
              <CardContent className="p-4 md:p-6">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                      {card.label}
                    </p>
                    <motion.p
                      key={value}
                      initial={{ scale: 0.8, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      className={`mt-2 text-3xl font-bold md:text-4xl ${card.color}`}
                    >
                      {value}
                    </motion.p>
                  </div>
                  <div className={`rounded-lg p-2 ${card.bg}`}>
                    <Icon className={`h-5 w-5 ${card.color}`} />
                  </div>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )
      })}
    </div>
  )
}
