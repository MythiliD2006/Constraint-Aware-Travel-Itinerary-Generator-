import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { SavedSummary } from '../api/types'
import { ErrorNote, Loading } from '../components/StatusViews'
import { inr } from '../lib/format'

export default function SavedPage() {
  const [rows, setRows] = useState<SavedSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.saved().then(setRows).catch((e) => setError(errorMessage(e)))
  }, [])

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-xl font-semibold">Saved itineraries</h1>
      <p className="mt-1 text-sm text-muted">Stored in the backend's SQLite database.</p>
      <div className="mt-5">
        {error && <ErrorNote message={error} />}
        {!error && !rows && <Loading label="Loading saved itineraries…" />}
        {rows && rows.length === 0 && (
          <div className="rounded-lg border border-dashed border-line px-6 py-8 text-sm text-muted">
            <p>Nothing saved yet. Generate an itinerary and use Save to keep it here.</p>
            <Link to="/" className="btn btn-primary mt-4">Plan a trip</Link>
          </div>
        )}
        {rows && rows.length > 0 && (
          <ul className="panel divide-y divide-line">
            {rows.map((row) => (
              <li key={row.id}>
                <Link to={`/saved/${row.id}`} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 hover:bg-canvas">
                  <span>
                    <span className="block font-medium">{row.title}</span>
                    <span className="block text-sm text-muted">
                      {row.destination_name}, {row.days} {row.days === 1 ? 'day' : 'days'}, saved{' '}
                      {new Date(row.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
                    </span>
                  </span>
                  <span className="text-sm">
                    {inr(row.total_cost)} <span className="text-muted">of {inr(row.budget)}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
