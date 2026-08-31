export function formatDateForAPI(date: Date): string {
  return date.toISOString().split('T')[0]
}

export function parseAPIDate(dateStr: string): Date {
  return new Date(dateStr + 'T00:00:00')
}

export function getDaysAgo(days: number): Date {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d
}

export function isToday(date: Date | string): boolean {
  const d = typeof date === 'string' ? new Date(date) : date
  const today = new Date()
  return d.toDateString() === today.toDateString()
}

export function isYesterday(date: Date | string): boolean {
  const d = typeof date === 'string' ? new Date(date) : date
  const yesterday = new Date()
  yesterday.setDate(yesterday.getDate() - 1)
  return d.toDateString() === yesterday.toDateString()
}

export function isInLastWeek(date: Date | string): boolean {
  const d = typeof date === 'string' ? new Date(date) : date
  const weekAgo = new Date()
  weekAgo.setDate(weekAgo.getDate() - 7)
  return d >= weekAgo
}

export function sortDates(dates: (Date | string)[], desc = true): Date[] {
  return dates
    .map(d => typeof d === 'string' ? new Date(d) : d)
    .sort((a, b) => desc ? b.getTime() - a.getTime() : a.getTime() - b.getTime())
}
