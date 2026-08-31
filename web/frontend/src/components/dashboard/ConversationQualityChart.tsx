import { motion } from 'framer-motion'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useQuery } from '@tanstack/react-query'
import { fetchQualityDistribution } from '@/lib/api'

export function ConversationQualityChart() {
  const { data: qualityData, isLoading } = useQuery({
    queryKey: ['quality'],
    queryFn: fetchQualityDistribution,
  })

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Conversation Quality</CardTitle>
        </CardHeader>
        <CardContent className="h-32 animate-pulse bg-muted/20" />
      </Card>
    )
  }

  if (!qualityData || qualityData.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Conversation Quality</CardTitle>
        </CardHeader>
        <CardContent className="flex h-32 items-center justify-center text-muted-foreground">
          No quality data yet
        </CardContent>
      </Card>
    )
  }

  const total = qualityData.reduce((sum: number, item: { count: number }) => sum + item.count, 0)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Conversation Quality</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {qualityData.map((item: { quality: string; count: number }, index: number) => {
            const percent = total > 0 ? (item.count / total) * 100 : 0
            const color = item.quality === 'good' ? 'bg-accent' : item.quality === 'tense' ? 'bg-secondary' : 'bg-muted'

            return (
              <div key={item.quality} className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <span className="capitalize">{item.quality.replace('_', ' ')}</span>
                  <span className="text-muted-foreground">{item.count}</span>
                </div>
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${percent}%` }}
                  transition={{ delay: index * 0.1, duration: 0.5 }}
                  className={`h-2 rounded-full ${color}`}
                />
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
