import { Car, Footprints, Utensils } from 'lucide-react'
import type { DayPlan, ScheduleItem } from '../api/types'
import { formatDate, humanize, inr, minutesToLabel } from '../lib/format'

const toMinutes = (hhmm: string) => {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

/** A proportional bar of the whole day: where the hours actually go. */
function DayStrip({ items, dayStart, dayEnd }: { items: ScheduleItem[]; dayStart: number; dayEnd: number }) {
  const span = dayEnd - dayStart
  const pct = (minutes: number) => `${((minutes - dayStart) / span) * 100}%`
  const width = (a: number, b: number) => `${((b - a) / span) * 100}%`
  const firstHour = Math.ceil(dayStart / 60)
  const hours = Array.from({ length: Math.floor(dayEnd / 60) - firstHour + 1 }, (_, i) => firstHour + i)

  return (
    <div aria-hidden className="select-none">
      <div className="relative h-5 overflow-hidden rounded border border-line bg-canvas">
        {items.map((item, i) => (
          <div key={i}>
            {item.kind === 'visit' && item.waited > 0 && (
              <div className="hatch absolute inset-y-0" style={{ left: pct(item.start - item.waited), width: width(item.start - item.waited, item.start) }} />
            )}
            <div
              className={`absolute inset-y-0 ${
                item.kind === 'visit' ? 'bg-forest' : item.kind === 'lunch' ? 'bg-ochre/40' : 'bg-forest/25'
              } ${item.kind === 'visit' ? 'border-x border-paper' : ''}`}
              style={{ left: pct(item.start), width: width(item.start, item.end) }}
              title={`${item.start_time}–${item.end_time} ${item.label}`}
            />
          </div>
        ))}
      </div>
      <div className="relative mt-1 h-4 text-[11px] text-muted">
        {hours.filter((h) => h % 2 === 0).map((h) => (
          <span key={h} className="absolute -translate-x-1/2" style={{ left: pct(h * 60) }}>
            {h}:00
          </span>
        ))}
      </div>
    </div>
  )
}

function TravelRow({ item }: { item: ScheduleItem }) {
  const Icon = item.mode === 'walk' ? Footprints : Car
  return (
    <div className="flex items-center gap-2 py-1 text-xs text-muted">
      <Icon size={13} aria-hidden />
      <span>
        {item.mode === 'walk' ? 'Walk' : 'Auto/cab'} {item.distance_km.toFixed(1)} km, {minutesToLabel(item.end - item.start)}
        {item.cost > 0 && `, ${inr(item.cost)}`}
        {item.target === 'base' && ', back to base'}
      </span>
    </div>
  )
}

function VisitRow({ item }: { item: ScheduleItem }) {
  return (
    <div className="py-1.5">
      <p className="font-medium leading-snug">{item.label}</p>
      <p className="text-xs text-muted">
        {humanize(item.category ?? '')}, {minutesToLabel(item.end - item.start)}
        {item.cost > 0 ? `, ${inr(item.cost)} entry` : ', free entry'}, open {item.hours?.join(' and ')}
      </p>
      {item.waited > 0 && (
        <p className="mt-1 inline-block rounded bg-canvas px-1.5 py-0.5 text-xs text-muted">
          Waits {item.waited} min for opening
        </p>
      )}
      {item.visitor_notes && item.visitor_notes.length > 0 && (
        <ul className="mt-1 flex flex-wrap gap-1">
          {item.visitor_notes.map((note) => (
            <li key={note.text} className="rounded border border-line px-1.5 py-0.5 text-xs text-muted"
              title={`Inherited from ${humanize(note.inherited_from)}`}>
              {note.text} <span className="text-muted/70">(from {humanize(note.inherited_from)})</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function DayTimeline({ day, dayStart, dayEnd }: { day: DayPlan; dayStart: string; dayEnd: string }) {
  const start = toMinutes(dayStart)
  const end = toMinutes(dayEnd)
  return (
    <section className="panel p-4 sm:p-5" aria-labelledby={`day-${day.day}`}>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 id={`day-${day.day}`} className="text-lg font-semibold">
          Day {day.day} <span className="font-normal text-muted">{formatDate(day.date)}</span>
        </h3>
        <p className="text-sm text-muted">
          {day.visit_count} {day.visit_count === 1 ? 'stop' : 'stops'}, {inr(day.activity_cost)} on entry and transport
        </p>
      </div>

      <DayStrip items={day.items} dayStart={start} dayEnd={end} />

      {day.items.length === 0 ? (
        <p className="mt-4 text-sm text-muted">Free day: no suitable attraction was left to schedule.</p>
      ) : (
        <ol className="mt-4">
          {day.items.map((item, index) => (
            <li key={index} className="grid grid-cols-[3.25rem_1rem_1fr] gap-x-2 sm:grid-cols-[6.5rem_1rem_1fr]">
              <time className={`pt-1.5 text-right text-xs ${item.kind === 'travel' ? 'text-muted/80' : 'text-ink'}`}>
                <span className="sm:hidden">{item.start_time}</span>
                <span className="hidden sm:inline">{item.start_time}–{item.end_time}</span>
              </time>
              {/* The route rail: solid dots for stops, a dashed line for movement. */}
              <div className="relative flex justify-center">
                <span className={`absolute inset-y-0 w-px ${item.kind === 'travel' ? 'border-l border-dashed border-forest/50' : 'bg-line'}`} />
                {item.kind === 'visit' && <span className="relative mt-2.5 h-2.5 w-2.5 rounded-full bg-forest ring-2 ring-paper" />}
                {item.kind === 'lunch' && <span className="relative mt-2 rounded-full bg-paper text-ochre"><Utensils size={12} /></span>}
              </div>
              <div className="min-w-0">
                {item.kind === 'travel' && <TravelRow item={item} />}
                {item.kind === 'visit' && <VisitRow item={item} />}
                {item.kind === 'lunch' && (
                  <p className="py-1.5 text-sm text-ochre">Lunch break, {minutesToLabel(item.end - item.start)}</p>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
