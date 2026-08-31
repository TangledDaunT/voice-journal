import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { BookOpen, Settings, BarChart3, Calendar } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

const actions = [
  { label: 'View Journal', icon: BookOpen, path: '/conversations' },
  { label: 'Settings', icon: Settings, path: '/settings' },
  { label: 'Weekly Stats', icon: BarChart3, path: '/' },
  { label: 'Select Date', icon: Calendar, path: '/conversations' },
]

export function QuickActions() {
  const navigate = useNavigate()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Quick Actions</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-2">
          {actions.map((action, index) => {
            const Icon = action.icon
            return (
              <motion.button
                key={action.label}
                onClick={() => navigate(action.path)}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: index * 0.05 }}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className="flex flex-col items-center gap-2 rounded-lg border border-border/50 p-4 transition-colors hover:border-primary/30 hover:bg-muted/5"
              >
                <Icon className="h-5 w-5 text-primary" />
                <span className="text-xs font-medium">{action.label}</span>
              </motion.button>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
