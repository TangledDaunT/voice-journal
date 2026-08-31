export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

export function isValidUrl(url: string): boolean {
  try {
    new URL(url)
    return true
  } catch {
    return false
  }
}

export function sanitizeInput(input: string): string {
  return input.replace(/<[^>]*>/g, '').trim()
}

export function isValidId(id: number): boolean {
  return Number.isInteger(id) && id > 0
}

export function isPositiveNumber(value: unknown): value is number {
  return typeof value === 'number' && value > 0
}

export function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}
