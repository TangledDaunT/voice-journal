export function formatNumber(num: number): string {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
  return num.toString()
}

export function formatHoursMinutes(seconds: number): string {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)

  if (hours > 0 && minutes > 0) return `${hours}h ${minutes}m`
  if (hours > 0) return `${hours}h`
  if (minutes > 0) return `${minutes}m`
  return `${seconds}s`
}

export function formatPercent(value: number, total: number): string {
  if (total === 0) return '0%'
  return `${Math.round((value / total) * 100)}%`
}

export function getChangeIndicator(current: number, previous: number): {
  direction: 'up' | 'down' | 'neutral'
  percent: number
} {
  if (previous === 0) {
    return { direction: current > 0 ? 'up' : 'neutral', percent: 0 }
  }

  const change = ((current - previous) / previous) * 100
  if (Math.abs(change) < 1) return { direction: 'neutral', percent: 0 }
  return {
    direction: change > 0 ? 'up' : 'down',
    percent: Math.abs(change),
  }
}
