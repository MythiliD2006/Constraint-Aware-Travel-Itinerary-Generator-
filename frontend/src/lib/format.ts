const rupees = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })

export const inr = (amount: number) => rupees.format(amount)

export const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1)

export function formatDate(iso: string, withWeekday = true): string {
  const date = new Date(`${iso}T00:00:00`)
  return date.toLocaleDateString('en-IN', {
    weekday: withWeekday ? 'short' : undefined,
    day: 'numeric',
    month: 'short',
  })
}

export function minutesToLabel(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  if (h === 0) return `${m} min`
  return m === 0 ? `${h} h` : `${h} h ${m} min`
}

/** Splits identifiers like "PlaceOfWorship" or "amber_fort" into readable words. */
export function humanize(identifier: string): string {
  return identifier
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
}
