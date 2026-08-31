import { motion } from 'framer-motion'
import { Clock, AlertCircle, CheckCircle } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { useQuery } from '@tanstack/react-query'
import { fetchBacklog } from '@/lib/api'

export function BacklogInfo() {
  const { data: backlog, isLoading } = useQuery({
    queryKey: ['backlog'],
    queryFn: fetchBacklog,
    refetchInterval: 60000,
  })

  if (isLoading) {
    return (
      <Card className="border-l-4 border-l-primary/30">
        <CardContent className="p-4">
          <div className="animate-pulse">Loading...</div>
        </CardContent>
      </Card>
    )
  }

  const isHealthy = backlog && backlog.segments_pending < 100
  const isWarning = backlog && backlog.segments_pending >= 100 && backlog.segments_pending < 500
  // isError is used for future error handling when backlog overflows

  const statusColor = isHealthy ? 'border-accent' : isWarning ? 'border-secondary' : 'border-destructive'
  const StatusIcon = isHealthy ? CheckCircle : isWarning ? Clock : AlertCircle

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <Card className={`border-l-4 ${statusColor}`}>
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <StatusIcon className={`h-5 w-5 ${isHealthy ? 'text-accent' : isWarning ? 'text-secondary' : 'text-destructive'}`} />
              <div>
                <p className="font-medium">
                  {isHealthy ? 'Backlog Healthy' : isWarning ? 'Backlog Growing' : 'Backlog Overflow'}
                </p>
                <p className="text-sm text-muted-foreground">
                  {backlog ? `${backlog.segments_pending} segments queued • ${backlog.total_queued_hours}h` : 'No data'}
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  )
}
