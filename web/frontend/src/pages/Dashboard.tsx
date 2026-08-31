import { useQuery } from '@tanstack/react-query'
import { fetchStats, fetchConversations, fetchWeeklySummary, fetchShivangiStats } from '@/lib/api'
import { StatsGrid } from '@/components/dashboard/StatsGrid'
import { WeeklyChart } from '@/components/dashboard/WeeklyChart'
import { ShivangiPanel } from '@/components/dashboard/ShivangiPanel'
import { RecentConversations } from '@/components/dashboard/RecentConversations'

export function Dashboard() {
  const { data: stats } = useQuery({ queryKey: ['stats'], queryFn: fetchStats, refetchInterval: 30000 })
  const { data: conversations, isLoading: convLoading } = useQuery({
    queryKey: ['conversations'],
    queryFn: () => fetchConversations(undefined, 20),
    refetchInterval: 30000
  })
  const { data: weekly } = useQuery({ queryKey: ['weekly'], queryFn: fetchWeeklySummary })
  const { data: shivangiStats } = useQuery({ queryKey: ['shivangi'], queryFn: () => fetchShivangiStats(30) })

  return (
    <div className="space-y-6">
      {/* Stats Grid */}
      <StatsGrid stats={stats ?? null} />

      {/* Two Column Layout */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left: Shivangi Panel */}
        <ShivangiPanel stats={shivangiStats ?? null} />

        {/* Right: Weekly Chart */}
        <WeeklyChart data={weekly ?? []} />
      </div>

      {/* Recent Conversations */}
      <RecentConversations conversations={conversations ?? []} isLoading={convLoading} />
    </div>
  )
}
