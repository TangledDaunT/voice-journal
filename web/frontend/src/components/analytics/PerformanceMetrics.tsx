import { useEffect } from 'react'

export function PerfTracker() {
  useEffect(() => {
    if (typeof window === 'undefined' || !window.performance) return

    // Log performance metrics
    const logPerf = () => {
      const timing = window.performance.timing
      const metrics = {
        dns: timing.domainLookupEnd - timing.domainLookupStart,
        tcp: timing.connectEnd - timing.connectStart,
        ttfb: timing.responseStart - timing.requestStart,
        download: timing.responseEnd - timing.responseStart,
        domParsed: timing.domInteractive - timing.responseEnd,
        domComplete: timing.domComplete - timing.domInteractive,
        total: timing.loadEventEnd - timing.navigationStart,
      }
      console.log('Performance metrics:', metrics)
    }

    window.addEventListener('load', logPerf)
    return () => window.removeEventListener('load', logPerf)
  }, [])

  return null
}

export function measureComponentRender(name: string) {
  return function <T extends (...args: any[]) => any>(
    fn: T
  ): T {
    return ((...args: Parameters<T>) => {
      const start = performance.now()
      const result = fn(...args)
      const end = performance.now()
      console.log(`${name} rendered in ${(end - start).toFixed(2)}ms`)
      return result
    }) as T
  }
}

export function TimeSinceMount() {
  useEffect(() => {
    const start = Date.now()
    return () => {
      console.log(`Component mounted for ${(Date.now() - start) / 1000}s`)
    }
  }, [])
  return null
}
