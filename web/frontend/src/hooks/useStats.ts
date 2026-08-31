import { useQuery } from '@tanstack/react-query'
import { fetchStats } from '@/lib/api'
import { Stats } from '@/lib/api'

export function useStats() {
  return useQuery<Stats>({
    queryKey: ['stats'],
    queryFn: fetchStats,
    staleTime: 30000,
    refetchInterval: 30000,
  })
}
