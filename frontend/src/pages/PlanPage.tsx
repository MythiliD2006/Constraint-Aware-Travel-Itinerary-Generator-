import { Check, RefreshCw, Save, X } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { DestinationDetail, DestinationSummary, PlanRequest, PlanResult } from '../api/types'
import { FeasibleView, InfeasibleView } from '../components/ItineraryView'
import { ErrorNote, Loading } from '../components/StatusViews'
import TripForm from '../components/TripForm'

function nextWeekIso(): string {
  const d = new Date()
  d.setDate(d.getDate() + 7)
  return d.toISOString().slice(0, 10)
}

const INITIAL: PlanRequest = {
  destination_id: '',
  start_date: nextWeekIso(),
  days: 3,
  travelers: 2,
  budget: 25000,
  accommodation: 'standard',
  pace: 'moderate',
  interests: ['history'],
  must_visit: [],
  exclude: [],
  seed: 0,
}

function SaveControl({ request, defaultTitle }: { request: PlanRequest; defaultTitle: string }) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(defaultTitle)
  const [state, setState] = useState<{ status: 'idle' | 'saving' | 'saved' | 'error'; id?: number; message?: string }>({ status: 'idle' })

  const save = async (event: FormEvent) => {
    event.preventDefault()
    setState({ status: 'saving' })
    try {
      const saved = await api.save(title, request)
      setState({ status: 'saved', id: saved.id })
      setEditing(false)
    } catch (error) {
      setState({ status: 'error', message: errorMessage(error) })
    }
  }

  if (state.status === 'saved') {
    return (
      <Link to={`/saved/${state.id}`} className="btn btn-quiet text-forest">
        <Check size={16} aria-hidden /> Saved, open it
      </Link>
    )
  }
  if (!editing) {
    return (
      <button type="button" className="btn btn-primary" onClick={() => setEditing(true)}>
        <Save size={16} aria-hidden /> Save
      </button>
    )
  }
  return (
    <form onSubmit={save} className="flex flex-wrap items-center gap-2">
      <label htmlFor="save-title" className="sr-only">Itinerary title</label>
      <input id="save-title" className="input w-52" value={title} maxLength={120} required autoFocus
        onChange={(e) => setTitle(e.target.value)} />
      <button type="submit" className="btn btn-primary" disabled={state.status === 'saving'}>
        {state.status === 'saving' ? 'Saving…' : 'Save'}
      </button>
      <button type="button" className="btn btn-quiet px-2" onClick={() => setEditing(false)} aria-label="Cancel saving">
        <X size={16} />
      </button>
      {state.status === 'error' && <p className="w-full text-xs text-brick">{state.message}</p>}
    </form>
  )
}

export default function PlanPage() {
  const [destinations, setDestinations] = useState<DestinationSummary[] | null>(null)
  const [detail, setDetail] = useState<DestinationDetail | null>(null)
  const [form, setForm] = useState<PlanRequest>(INITIAL)
  const [result, setResult] = useState<PlanResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const resultsRef = useRef<HTMLDivElement>(null)

  const loadDestinations = () => {
    setLoadError(null)
    api.destinations()
      .then((list) => {
        setDestinations(list)
        setForm((f) => (f.destination_id ? f : { ...f, destination_id: list[0]?.id ?? '' }))
      })
      .catch((e) => setLoadError(errorMessage(e)))
  }
  useEffect(loadDestinations, [])

  useEffect(() => {
    if (!form.destination_id) return
    setDetail(null)
    api.destination(form.destination_id).then(setDetail).catch((e) => setLoadError(errorMessage(e)))
  }, [form.destination_id])

  const run = async (request: PlanRequest) => {
    setBusy(true)
    setError(null)
    try {
      setResult(await api.plan(request))
      // On narrow screens the results sit below the form, so bring them into view.
      if (window.matchMedia('(max-width: 1023px)').matches) {
        resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const generate = () => {
    const request = { ...form, seed: 0 }
    setForm(request)
    run(request)
  }

  // Regenerate keeps the same constraints and asks the planner to break ties
  // between equally good optional stops differently.
  const regenerate = () => {
    if (!result) return
    const request = { ...result.request, seed: result.request.seed + 1 }
    setForm(request)
    run(request)
  }

  if (loadError && !destinations) {
    return <ErrorNote message={loadError} action={<button className="btn btn-quiet" onClick={loadDestinations}>Try again</button>} />
  }
  if (!destinations) return <Loading label="Loading destinations…" />

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
      <div className="lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto">
        <TripForm destinations={destinations} detail={detail} value={form} onChange={setForm} onSubmit={generate} busy={busy} />
      </div>

      <div ref={resultsRef} className="min-w-0 scroll-mt-4" aria-live="polite">
        {error && <div className="mb-4"><ErrorNote message={error} /></div>}
        {busy && !result && <Loading label="Decomposing the trip and checking constraints…" />}
        {!busy && !result && !error && (
          <div className="rounded-lg border border-dashed border-line px-6 py-10 text-sm text-muted">
            <p className="text-base font-medium text-ink">No itinerary yet</p>
            <p className="mt-2 max-w-prose">
              Choose a destination, dates, budget and interests, then generate. The planner breaks the trip into days
              and stops, checks opening hours, travel time and the budget at every step, and backtracks when a choice
              leads to a dead end. If nothing fits, it tells you which constraint is in the way.
            </p>
            <p className="mt-2 max-w-prose">Costs and hours come from a small sample dataset and are estimates.</p>
          </div>
        )}
        {result && (
          <div className={busy ? 'pointer-events-none opacity-60 transition-opacity' : 'transition-opacity'}>
            {result.status === 'ok' ? (
              <FeasibleView
                plan={result}
                actions={
                  <>
                    <button type="button" className="btn btn-quiet" onClick={regenerate} disabled={busy}>
                      <RefreshCw size={16} className={busy ? 'animate-spin' : ''} aria-hidden /> Regenerate
                    </button>
                    {/* Keyed by the request so a new plan starts with a fresh Save button. */}
                    <SaveControl
                      key={JSON.stringify(result.request)}
                      request={result.request}
                      defaultTitle={`${result.destination.name}, ${result.request.days} days`}
                    />
                  </>
                }
              />
            ) : (
              <InfeasibleView plan={result} />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
