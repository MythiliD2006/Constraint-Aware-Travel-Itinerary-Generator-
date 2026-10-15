import { Play } from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { api, errorMessage } from '../api/client'
import type { AttractionInfo, DestinationDetail, DestinationSummary, KnowledgeOverview, QueryResult } from '../api/types'
import { ErrorNote, Loading } from '../components/StatusViews'
import { humanize } from '../lib/format'

type ClassInfo = KnowledgeOverview['classes'][number]

function ClassTree({ name, byParent, classes, attractions, selected, onSelect }: {
  name: string
  byParent: Record<string, string[]>
  classes: Record<string, ClassInfo>
  attractions: Record<string, AttractionInfo>
  selected: string | null
  onSelect: (id: string) => void
}) {
  const info = classes[name]
  const own = Object.entries(info.properties)
  return (
    <li className="mt-1.5">
      <p className="text-sm">
        <span className="font-semibold text-forest-deep">{name}</span>
        {info.interests.length > 0 && <span className="text-muted"> adds {info.interests.join(', ')}</span>}
      </p>
      {own.length > 0 && (
        <p className="text-xs text-muted">{own.map(([k, v]) => `${k} = ${String(v)}`).join('; ')}</p>
      )}
      {info.instances.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {info.instances.map((id) => (
            <button key={id} type="button" onClick={() => onSelect(id)}
              className={`rounded border px-1.5 py-0.5 text-xs ${selected === id ? 'border-forest bg-forest text-white' : 'border-line bg-paper hover:border-forest/50'}`}>
              {attractions[id]?.name ?? id}
            </button>
          ))}
        </div>
      )}
      {byParent[name] && (
        <ul className="ml-1 border-l border-line pl-4">
          {byParent[name].map((child) => (
            <ClassTree key={child} name={child} byParent={byParent} classes={classes}
              attractions={attractions} selected={selected} onSelect={onSelect} />
          ))}
        </ul>
      )}
    </li>
  )
}

function InstancePanel({ attraction }: { attraction: AttractionInfo }) {
  return (
    <div className="panel p-4">
      <h3 className="font-semibold">{attraction.name}</h3>
      <p className="text-sm text-muted">
        instance_of({attraction.id}, {attraction.category}); ISA chain {attraction.lineage.join(' > ')}
      </p>
      <table className="mt-3 w-full text-left text-sm">
        <thead className="text-xs text-muted">
          <tr><th className="pb-1 font-medium">Property</th><th className="pb-1 font-medium">Value</th><th className="pb-1 font-medium">Comes from</th></tr>
        </thead>
        <tbody className="divide-y divide-line">
          {Object.entries(attraction.properties).map(([key, { value, source }]) => (
            <tr key={key}>
              <td className="py-1 pr-2">{humanize(key)}</td>
              <td className="py-1 pr-2">{String(value)}</td>
              <td className={`py-1 ${source === attraction.id ? 'text-forest' : 'text-muted'}`}>
                {source === attraction.id ? 'instance (overrides)' : source}
              </td>
            </tr>
          ))}
          <tr>
            <td className="py-1 pr-2">Interests</td>
            <td className="py-1" colSpan={2}>
              {attraction.interests.map((i) => `${i.interest} (${i.source === attraction.id ? 'instance' : i.source})`).join(', ') || 'none'}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

export default function KnowledgePage() {
  const [destinations, setDestinations] = useState<DestinationSummary[] | null>(null)
  const [destinationId, setDestinationId] = useState('')
  const [overview, setOverview] = useState<KnowledgeOverview | null>(null)
  const [detail, setDetail] = useState<DestinationDetail | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [answer, setAnswer] = useState<QueryResult | null>(null)
  const [queryError, setQueryError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.destinations().then((list) => {
      setDestinations(list)
      setDestinationId(list[0]?.id ?? '')
    }).catch((e) => setError(errorMessage(e)))
  }, [])

  useEffect(() => {
    if (!destinationId) return
    setOverview(null)
    setAnswer(null)
    setSelected(null)
    Promise.all([api.knowledge(destinationId), api.destination(destinationId)])
      .then(([k, d]) => {
        setOverview(k)
        setDetail(d)
        setQuery(k.example_queries[2])
      })
      .catch((e) => setError(errorMessage(e)))
  }, [destinationId])

  const tree = useMemo(() => {
    if (!overview) return null
    const classes = Object.fromEntries(overview.classes.map((c) => [c.name, c]))
    const byParent: Record<string, string[]> = {}
    overview.classes.forEach((c) => { if (c.parent) (byParent[c.parent] ??= []).push(c.name) })
    return { classes, byParent }
  }, [overview])

  const attractions = useMemo(
    () => Object.fromEntries((detail?.attractions ?? []).map((a) => [a.id, a])),
    [detail],
  )

  const ask = async (event?: FormEvent, text = query) => {
    event?.preventDefault()
    setQueryError(null)
    try {
      setAnswer(await api.query(destinationId, text))
    } catch (e) {
      setAnswer(null)
      setQueryError(errorMessage(e))
    }
  }

  if (error) return <ErrorNote message={error} />
  if (!destinations) return <Loading label="Loading knowledge base…" />

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Knowledge base</h1>
          <p className="mt-1 max-w-prose text-sm text-muted">
            The facts and rules the planner reasons with. Classes are linked by ISA, each attraction is an instance of
            one class, and properties are inherited down the hierarchy unless an instance overrides them.
          </p>
        </div>
        <label className="text-sm">
          <span className="field-label">Destination</span>
          <select className="input w-48" value={destinationId} onChange={(e) => setDestinationId(e.target.value)}>
            {destinations.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </label>
      </div>

      {!overview || !tree ? <Loading label="Loading facts…" /> : (
        <div className="grid items-start gap-5 lg:grid-cols-2">
          <section className="panel p-4" aria-labelledby="hierarchy">
            <h2 id="hierarchy" className="section-title">Class hierarchy and instances</h2>
            <p className="text-xs text-muted">Select an attraction to see where each of its properties comes from.</p>
            <ul className="mt-2">
              <ClassTree name="Attraction" byParent={tree.byParent} classes={tree.classes}
                attractions={attractions} selected={selected} onSelect={setSelected} />
            </ul>
          </section>

          <div className="space-y-5">
            {selected && attractions[selected] && <InstancePanel attraction={attractions[selected]} />}

            <section className="panel p-4" aria-labelledby="query-title">
              <h2 id="query-title" className="section-title">Ask the knowledge base</h2>
              <p className="text-xs text-muted">
                Answers are proved by SLD resolution with unification. Variables start with ?, goals are separated by commas.
              </p>
              <form onSubmit={ask} className="mt-3 flex gap-2">
                <label htmlFor="query" className="sr-only">Query</label>
                <input id="query" className="input" value={query} onChange={(e) => setQuery(e.target.value)} spellCheck={false} />
                <button type="submit" className="btn btn-primary"><Play size={15} aria-hidden /> Run</button>
              </form>
              <div className="mt-2 flex flex-wrap gap-1">
                {overview.example_queries.map((q) => (
                  <button key={q} type="button" onClick={() => { setQuery(q); ask(undefined, q) }}
                    className="rounded border border-line px-1.5 py-0.5 text-xs text-muted hover:border-forest/50 hover:text-ink">
                    {q}
                  </button>
                ))}
              </div>
              {queryError && <p className="mt-3 text-sm text-brick">{queryError}</p>}
              {answer && (
                <div className="mt-4 text-sm">
                  <p className={answer.proved ? 'text-forest' : 'text-brick'}>
                    {answer.proved
                      ? answer.has_variables ? `${answer.answers.length} answer${answer.answers.length === 1 ? '' : 's'}` : 'Proved: true'
                      : 'Not provable from the knowledge base (false under the closed-world assumption)'}
                    <span className="text-muted"> after {answer.inferences} resolution steps</span>
                  </p>
                  {answer.has_variables && answer.answers.length > 0 && (
                    <ul className="mt-2 max-h-48 overflow-y-auto rounded border border-line">
                      {answer.answers.map((a, i) => (
                        <li key={i} className="border-b border-line px-2 py-1 last:border-0">
                          {Object.entries(a.bindings).map(([v, val]) => `${v} = ${val}`).join(', ')}
                        </li>
                      ))}
                    </ul>
                  )}
                  {answer.answers[0] && (
                    <details className="mt-3">
                      <summary className="cursor-pointer text-muted">Proof of the first answer</summary>
                      <ol className="mt-2 space-y-1 text-xs">
                        {answer.answers[0].proof.map((step, i) => (
                          <li key={i} style={{ paddingLeft: `${step.depth * 0.75}rem` }}>
                            <span className="font-medium">{step.goal}</span>
                            <span className="text-muted"> resolved with {step.clause}</span>
                          </li>
                        ))}
                      </ol>
                    </details>
                  )}
                </div>
              )}
            </section>

            <section className="panel p-4" aria-labelledby="rules-title">
              <h2 id="rules-title" className="section-title">Rules (Horn clauses)</h2>
              <ul className="mt-2 space-y-1 text-xs">
                {overview.rules.map((r) => <li key={r}>{r}</li>)}
              </ul>
              <p className="mt-3 text-xs text-muted">
                Facts loaded for this destination:{' '}
                {Object.entries(overview.fact_counts).map(([k, n]) => `${n} ${k}`).join(', ')}.
              </p>
            </section>
          </div>
        </div>
      )}
    </div>
  )
}
