import { AlertTriangle, CheckCircle2, ChevronRight, CircleX, Info, XCircle } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import type { BudgetSummary, Check, FeasiblePlan, InfeasiblePlan, TreeNode } from '../api/types'
import { capitalize, formatDate, inr } from '../lib/format'
import DayTimeline from './DayTimeline'

// ---------------------------------------------------------------------------
function BudgetPanel({ budget }: { budget: BudgetSummary }) {
  const rows = [
    { label: `Stay (${budget.nights} night${budget.nights === 1 ? '' : 's'}, ${budget.rooms} room${budget.rooms === 1 ? '' : 's'})`, value: budget.accommodation, color: 'bg-forest-deep' },
    { label: 'Food', value: budget.food, color: 'bg-forest' },
    { label: 'Entry fees', value: budget.entry_fees, color: 'bg-forest/55' },
    { label: 'Local transport', value: budget.local_transport, color: 'bg-forest/25' },
  ]
  const scale = Math.max(budget.limit, budget.total)
  return (
    <section className="panel p-4" aria-labelledby="budget-title">
      <h3 id="budget-title" className="section-title">Estimated cost</h3>
      <p className="mt-1 text-2xl font-semibold">
        {inr(budget.total)} <span className="text-sm font-normal text-muted">of {inr(budget.limit)}</span>
      </p>
      <div className="mt-3 flex h-2.5 overflow-hidden rounded-full bg-canvas ring-1 ring-line" aria-hidden>
        {rows.map((row) => (
          <div key={row.label} className={row.color} style={{ width: `${(row.value / scale) * 100}%` }} />
        ))}
      </div>
      <dl className="mt-3 space-y-1.5 text-sm">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between gap-2">
            <dt className="flex items-center gap-2 text-muted">
              <span className={`h-2.5 w-2.5 rounded-sm ${row.color}`} aria-hidden />
              {row.label}
            </dt>
            <dd>{inr(row.value)}</dd>
          </div>
        ))}
        <div className="flex justify-between border-t border-line pt-1.5 font-medium">
          <dt>{budget.remaining >= 0 ? 'Left over' : 'Over budget'}</dt>
          <dd className={budget.remaining >= 0 ? 'text-forest' : 'text-brick'}>{inr(Math.abs(budget.remaining))}</dd>
        </div>
      </dl>
      <p className="mt-3 text-xs text-muted">{capitalize(budget.tier)} stay rates. {budget.notes[2]}</p>
    </section>
  )
}

function ChecksPanel({ checks }: { checks: Check[] }) {
  return (
    <section className="panel p-4" aria-labelledby="checks-title">
      <h3 id="checks-title" className="section-title">Constraint checks</h3>
      <p className="mt-0.5 text-xs text-muted">Re-run on the finished schedule, separately from the search.</p>
      <ul className="mt-3 space-y-2.5">
        {checks.map((check) => (
          <li key={check.name} className="flex gap-2 text-sm">
            {check.passed
              ? <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-forest" aria-label="Passed" />
              : <XCircle size={16} className="mt-0.5 shrink-0 text-brick" aria-label="Failed" />}
            <div>
              <p className="font-medium leading-snug">{check.name}</p>
              {check.details.map((d) => <p key={d} className="text-xs text-muted">{d}</p>)}
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

// ---------------------------------------------------------------------------
function TreeView({ node, depth = 0 }: { node: TreeNode; depth?: number }) {
  const [open, setOpen] = useState(depth < 2)
  const hasChildren = node.children.length > 0
  return (
    <li>
      <div className="flex items-start gap-1">
        {hasChildren ? (
          <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
            className="mt-0.5 rounded text-muted hover:text-ink" aria-label={open ? 'Collapse' : 'Expand'}>
            <ChevronRight size={14} className={`transition-transform ${open ? 'rotate-90' : ''}`} />
          </button>
        ) : <span className="w-3.5" />}
        <span className={node.primitive ? 'text-ink' : 'font-medium text-forest-deep'}>{node.task}</span>
        {node.method && <span className="text-muted">via {node.method}</span>}
      </div>
      {hasChildren && open && (
        <ul className="ml-[7px] border-l border-line pl-3">
          {node.children.map((child, i) => <TreeView key={i} node={child} depth={depth + 1} />)}
        </ul>
      )}
    </li>
  )
}

function Collapsible({ title, children, defaultOpen = false }: { title: ReactNode; children: ReactNode; defaultOpen?: boolean }) {
  return (
    <details className="panel group" open={defaultOpen}>
      <summary className="flex cursor-pointer items-center gap-2 px-4 py-3 font-semibold">
        <ChevronRight size={16} className="text-muted transition-transform group-open:rotate-90" aria-hidden />
        {title}
      </summary>
      <div className="border-t border-line px-4 py-3">{children}</div>
    </details>
  )
}

// ---------------------------------------------------------------------------
export function FeasibleView({ plan, actions }: { plan: FeasiblePlan; actions?: ReactNode }) {
  const stops = plan.selected.length
  const stats = plan.stats!
  return (
    <div className="space-y-4">
      <div className="panel flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div>
          <h2 className="text-lg font-semibold">
            {plan.destination.name}, {plan.request.days} {plan.request.days === 1 ? 'day' : 'days'} from {formatDate(plan.request.start_date)}
          </h2>
          <p className="text-sm text-muted">
            {stops} stops for {plan.request.travelers} {plan.request.travelers === 1 ? 'traveller' : 'travellers'}, starting
            each day from {plan.destination.base}.
          </p>
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>

      {plan.warnings.map((w) => (
        <p key={w} className="flex items-start gap-2 rounded-lg border border-ochre/30 bg-ochre-soft px-4 py-2.5 text-sm">
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-ochre" aria-hidden /> {w}
        </p>
      ))}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="space-y-4">
          {plan.days.map((day) => (
            <DayTimeline key={day.day} day={day} dayStart={plan.pace.day_start} dayEnd={plan.pace.day_end} />
          ))}
        </div>
        <aside className="space-y-4">
          <BudgetPanel budget={plan.budget} />
          <ChecksPanel checks={plan.checks} />
        </aside>
      </div>

      <Collapsible title={`Why these stops (${plan.selected.length} chosen, ${plan.rejected.length} left out)`} defaultOpen>
        <div className="grid gap-6 md:grid-cols-2">
          <div>
            <h4 className="mb-2 text-sm font-semibold">Chosen</h4>
            <ul className="space-y-3">
              {plan.selected.map((s) => (
                <li key={s.attraction_id} className="text-sm">
                  <p className="font-medium">{s.name} <span className="font-normal text-muted">(day {s.day})</span></p>
                  <ul className="mt-0.5 space-y-0.5 text-muted">
                    {s.reasons.map((r) => <li key={r}>{r}</li>)}
                  </ul>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h4 className="mb-2 text-sm font-semibold">Left out</h4>
            {plan.rejected.length === 0 ? (
              <p className="text-sm text-muted">Every attraction in the dataset made it into the plan.</p>
            ) : (
              <ul className="space-y-3">
                {plan.rejected.map((r) => (
                  <li key={r.attraction_id} className="text-sm">
                    <p className="font-medium">{r.name}</p>
                    <p className="text-muted">{r.reason}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </Collapsible>

      <Collapsible title="How the planner got here">
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <div><dt className="text-muted">Search steps</dt><dd className="font-medium">{stats.nodes_expanded}</dd></div>
          <div><dt className="text-muted">Backtracks</dt><dd className="font-medium">{stats.backtracks}</dd></div>
          <div><dt className="text-muted">Candidates</dt><dd className="font-medium">{stats.candidates}</dd></div>
          <div><dt className="text-muted">Search time</dt><dd className="font-medium">{stats.elapsed_ms} ms</dd></div>
        </dl>
        <p className="mt-3 text-sm text-muted">
          Task decomposition of the plan that was found. Bold tasks are compound and were refined by the named
          method; plain tasks are primitive actions whose preconditions held.
        </p>
        <ul className="mt-2 overflow-x-auto text-xs leading-6">
          <TreeView node={plan.decomposition} />
        </ul>
      </Collapsible>

      <p className="flex items-start gap-2 text-xs text-muted">
        <Info size={14} className="mt-0.5 shrink-0" aria-hidden /> {plan.disclaimer}
      </p>
    </div>
  )
}

export function InfeasibleView({ plan }: { plan: InfeasiblePlan }) {
  return (
    <div className="space-y-4">
      <section className="panel border-brick/30 p-4 sm:p-5">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <CircleX size={20} className="text-brick" aria-hidden /> No itinerary satisfies these constraints
        </h2>
        <ul className="mt-3 space-y-2 text-sm">
          {plan.issues.map((issue, i) => (
            <li key={i} className="border-l-2 border-brick/50 pl-3">{issue.message}</li>
          ))}
        </ul>
        {plan.suggestions.length > 0 && (
          <>
            <h3 className="mt-5 text-sm font-semibold">What you could change</h3>
            <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-muted">
              {plan.suggestions.map((s) => <li key={s}>{s}</li>)}
            </ul>
          </>
        )}
        {plan.stats && (
          <p className="mt-4 text-xs text-muted">
            Search explored {plan.stats.nodes_expanded} steps with {plan.stats.backtracks} backtracks.
          </p>
        )}
      </section>
      <p className="text-sm text-muted">
        Fixed costs for this request: stay {inr(plan.budget.accommodation)}, food {inr(plan.budget.food)}.
      </p>
    </div>
  )
}
