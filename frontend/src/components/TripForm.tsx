import { Flower2, Landmark, Leaf, Palette, ShoppingBag, Theater, type LucideIcon } from 'lucide-react'
import type { FormEvent } from 'react'
import type { DestinationDetail, DestinationSummary, Interest, Pace, PlanRequest, Tier } from '../api/types'
import { inr } from '../lib/format'

const INTERESTS: { id: Interest; label: string; icon: LucideIcon }[] = [
  { id: 'history', label: 'History', icon: Landmark },
  { id: 'culture', label: 'Culture', icon: Theater },
  { id: 'art', label: 'Art', icon: Palette },
  { id: 'spiritual', label: 'Spiritual', icon: Flower2 },
  { id: 'nature', label: 'Nature', icon: Leaf },
  { id: 'shopping', label: 'Shopping', icon: ShoppingBag },
]

// Mirrors PACES in backend/app/planner/constraints.py (shown here only as help text).
const PACES: { id: Pace; label: string; hint: string }[] = [
  { id: 'relaxed', label: 'Relaxed', hint: '9:30 to 18:30, up to 3 stops a day' },
  { id: 'moderate', label: 'Moderate', hint: '9:00 to 19:30, up to 4 stops a day' },
  { id: 'packed', label: 'Packed', hint: '8:00 to 21:00, up to 6 stops a day' },
]

const TIERS: { id: Tier; label: string }[] = [
  { id: 'budget', label: 'Budget' },
  { id: 'standard', label: 'Standard' },
  { id: 'comfort', label: 'Comfort' },
]

type Choice = 'must' | 'neutral' | 'skip'

interface Props {
  destinations: DestinationSummary[]
  detail: DestinationDetail | null
  value: PlanRequest
  onChange: (next: PlanRequest) => void
  onSubmit: () => void
  busy: boolean
}

function Segmented<T extends string>({ name, options, value, onChange }: {
  name: string
  options: { id: T; label: string }[]
  value: T
  onChange: (id: T) => void
}) {
  return (
    <div role="radiogroup" aria-label={name} className="grid grid-flow-col auto-cols-fr rounded-md border border-line bg-canvas p-0.5">
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          role="radio"
          aria-checked={value === option.id}
          onClick={() => onChange(option.id)}
          className={`rounded px-2 py-1.5 text-sm transition-colors ${
            value === option.id ? 'bg-paper font-medium text-forest-deep shadow-sm ring-1 ring-line' : 'text-muted hover:text-ink'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export default function TripForm({ destinations, detail, value, onChange, onSubmit, busy }: Props) {
  const set = <K extends keyof PlanRequest>(key: K, v: PlanRequest[K]) => onChange({ ...value, [key]: v })

  const choiceOf = (id: string): Choice =>
    value.must_visit.includes(id) ? 'must' : value.exclude.includes(id) ? 'skip' : 'neutral'

  const setChoice = (id: string, choice: Choice) => {
    onChange({
      ...value,
      must_visit: choice === 'must' ? [...value.must_visit.filter((x) => x !== id), id] : value.must_visit.filter((x) => x !== id),
      exclude: choice === 'skip' ? [...value.exclude.filter((x) => x !== id), id] : value.exclude.filter((x) => x !== id),
    })
  }

  const toggleInterest = (id: Interest) =>
    set('interests', value.interests.includes(id) ? value.interests.filter((i) => i !== id) : [...value.interests, id])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    onSubmit()
  }

  const pace = PACES.find((p) => p.id === value.pace)!

  return (
    <form onSubmit={submit} className="panel space-y-5 p-4 sm:p-5">
      <fieldset>
        <legend className="field-label">Destination</legend>
        <div className="space-y-1.5">
          {destinations.map((d) => (
            <label
              key={d.id}
              className={`flex cursor-pointer gap-3 rounded-md border px-3 py-2.5 transition-colors ${
                value.destination_id === d.id ? 'border-forest bg-forest-soft/60' : 'border-line hover:border-forest/40'
              }`}
            >
              <input
                type="radio"
                name="destination"
                className="mt-1 accent-forest"
                checked={value.destination_id === d.id}
                onChange={() => onChange({ ...value, destination_id: d.id, must_visit: [], exclude: [] })}
              />
              <span>
                <span className="block text-sm font-medium">
                  {d.name} <span className="font-normal text-muted">({d.region})</span>
                </span>
                <span className="block text-xs leading-snug text-muted">{d.summary}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2 sm:col-span-1">
          <label htmlFor="start" className="field-label">Start date</label>
          <input id="start" type="date" className="input" required value={value.start_date}
            onChange={(e) => set('start_date', e.target.value)} />
        </div>
        <div>
          <label htmlFor="days" className="field-label">Days</label>
          <select id="days" className="input" value={value.days} onChange={(e) => set('days', Number(e.target.value))}>
            {[1, 2, 3, 4, 5, 6, 7].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="travelers" className="field-label">Travellers</label>
          <select id="travelers" className="input" value={value.travelers}
            onChange={(e) => set('travelers', Number(e.target.value))}>
            {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        <div className="col-span-2 sm:col-span-1">
          <label htmlFor="budget" className="field-label">Total budget (₹)</label>
          <input id="budget" type="number" min={500} step={500} className="input" required value={value.budget}
            onChange={(e) => set('budget', Number(e.target.value))} />
        </div>
      </div>
      <p className="-mt-3 text-xs text-muted">Budget covers stay, food, entry fees and local transport for the group.</p>

      <div>
        <span className="field-label">Stay</span>
        <Segmented name="Stay" options={TIERS} value={value.accommodation} onChange={(t) => set('accommodation', t)} />
      </div>

      <div>
        <span className="field-label">Pace</span>
        <Segmented name="Pace" options={PACES} value={value.pace} onChange={(p) => set('pace', p)} />
        <p className="mt-1.5 text-xs text-muted">{pace.hint}, with a lunch break between 12:00 and 14:30.</p>
      </div>

      <fieldset>
        <legend className="field-label">Interests</legend>
        <div className="flex flex-wrap gap-1.5">
          {INTERESTS.map(({ id, label, icon: Icon }) => {
            const on = value.interests.includes(id)
            return (
              <button
                key={id}
                type="button"
                aria-pressed={on}
                onClick={() => toggleInterest(id)}
                className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors ${
                  on ? 'border-forest bg-forest text-white' : 'border-line bg-paper text-ink hover:border-forest/40'
                }`}
              >
                <Icon size={14} aria-hidden />
                {label}
              </button>
            )
          })}
        </div>
        <p className="mt-1.5 text-xs text-muted">
          {value.interests.length === 0 ? 'None selected: every attraction is a candidate.' : 'Only matching attractions (plus must-visits) are considered.'}
        </p>
      </fieldset>

      <details className="group rounded-md border border-line">
        <summary className="flex cursor-pointer items-center justify-between px-3 py-2 text-sm font-medium">
          Must-visit and skip
          <span className="text-xs font-normal text-muted">
            {value.must_visit.length} must, {value.exclude.length} skipped
          </span>
        </summary>
        {!detail ? (
          <p className="px-3 pb-3 text-sm text-muted">Loading attractions…</p>
        ) : (
          <ul className="divide-y divide-line border-t border-line">
            {detail.attractions.map((a) => {
              const choice = choiceOf(a.id)
              return (
                <li key={a.id} className="flex items-center justify-between gap-2 px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm">{a.name}</p>
                    <p className="text-xs text-muted">
                      {a.hours.join(', ')}{a.closed_on.length > 0 && `, closed ${a.closed_on.map((d) => d.slice(0, 3)).join('/')}`}
                      {a.entry_fee > 0 ? `, ${inr(a.entry_fee)}` : ', free'}
                    </p>
                  </div>
                  <div className="flex shrink-0 rounded border border-line text-xs" role="radiogroup" aria-label={`Preference for ${a.name}`}>
                    {(['must', 'neutral', 'skip'] as Choice[]).map((c) => (
                      <button
                        key={c}
                        type="button"
                        role="radio"
                        aria-checked={choice === c}
                        onClick={() => setChoice(a.id, c)}
                        className={`px-2 py-1 first:rounded-l last:rounded-r ${
                          choice === c
                            ? c === 'must' ? 'bg-forest text-white' : c === 'skip' ? 'bg-brick text-white' : 'bg-canvas font-medium'
                            : 'text-muted hover:text-ink'
                        }`}
                      >
                        {c === 'must' ? 'Must' : c === 'skip' ? 'Skip' : 'Maybe'}
                      </button>
                    ))}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </details>

      <button type="submit" className="btn btn-primary w-full" disabled={busy || !value.destination_id}>
        {busy ? 'Planning…' : 'Generate itinerary'}
      </button>
    </form>
  )
}
