import { AlertTriangle, Loader2 } from 'lucide-react'
import type { ReactNode } from 'react'

export function Loading({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 py-8 text-sm text-muted" role="status">
      <Loader2 size={16} className="animate-spin" aria-hidden />
      {label}
    </div>
  )
}

export function ErrorNote({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-brick/30 bg-brick-soft px-4 py-3 text-sm" role="alert">
      <AlertTriangle size={18} className="mt-0.5 shrink-0 text-brick" aria-hidden />
      <div className="space-y-2">
        <p>{message}</p>
        {action}
      </div>
    </div>
  )
}
