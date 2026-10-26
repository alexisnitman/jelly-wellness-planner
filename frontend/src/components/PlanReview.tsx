import { useState } from 'react'
import type { Plan, PlanItem } from '../types'
import { addDays, shortDate } from './WeekPicker'
import { KindIcon } from '../lib/kinds'

const KIND_LABEL: Record<PlanItem['kind'], string> = { workout: 'Workout', cooking: 'Cooking', social: 'Friends', errand: 'Errand', rest: 'Rest', wellness: 'Wellness', other: 'Other' }

const time12 = (hhmm: string) => {
  const [h, m] = hhmm.split(':').map(Number)
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`
}
const dayLabel = (iso: string) => new Intl.DateTimeFormat('en-US', { weekday: 'long', month: 'short', day: 'numeric', timeZone: 'UTC' }).format(new Date(`${iso}T12:00:00Z`))

interface Props {
  plan: Plan
  busy: boolean
  onRemove: (id: string) => void
  onRegenerate: (notes: string) => void // notes can be empty: just try a different arrangement
  onContinue: () => void
  selectedId?: string | null
  onSelect?: (id: string | null) => void
}

const IDEAS = ['Move workouts earlier', 'Move things to the evening', 'Fewer things per day', 'Add more rest', 'Different recipes', 'Lighter workouts', 'More time with friends']

const BALANCE: { label: string; kinds: PlanItem['kind'][] }[] = [
  { label: 'Movement', kinds: ['workout'] },
  { label: 'Cooking at home', kinds: ['cooking'] },
  { label: 'Connection', kinds: ['social'] },
  { label: 'Rest & wellness', kinds: ['rest', 'wellness'] },
  { label: 'Errands & other', kinds: ['errand', 'other'] },
]
const ANCHOR_LABEL = { workout: 'Workouts', cooking: 'Cooking', wellness: 'Wellness habits', rest: 'Rest' } as const
const DAY_ABBR = new Intl.DateTimeFormat('en-US', { weekday: 'short', timeZone: 'UTC' })

// Habits that land at about the same time of day on several days: the anchors of a routine.
function anchors(items: PlanItem[]): string[] {
  const out: string[] = []
  for (const kind of ['workout', 'cooking', 'wellness', 'rest'] as const) {
    const mine = items.filter((i) => i.kind === kind).sort((a, b) => a.start.localeCompare(b.start))
    if (mine.length < 2) continue
    const mins = (hhmm: string) => Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3))
    const best = mine.map((m) => mine.filter((o) => Math.abs(mins(o.start) - mins(m.start)) <= 30)).sort((a, b) => b.length - a.length)[0]
    if (best.length >= 2) {
      const days = [...new Set(best.map((b) => b.day))].sort().map((d) => DAY_ABBR.format(new Date(`${d}T12:00:00Z`)))
      if (days.length >= 2) out.push(`${ANCHOR_LABEL[kind]} around ${time12(best[0].start)} (${days.join(', ')})`)
    }
  }
  return out
}

// Step 4: review what was proposed. Every item shown here already passed the server-side calendar checks.
export default function PlanReview({ plan, busy, onRemove, onRegenerate, onContinue, selectedId, onSelect }: Props) {
  const [open, setOpen] = useState(false)
  const [notes, setNotes] = useState('')
  const addIdea = (idea: string) => setNotes((n) => (n.includes(idea) ? n : n ? `${n.replace(/[.\s]+$/, '')}. ${idea}.` : `${idea}.`).slice(0, 600))
  const days = Array.from({ length: 7 }, (_, i) => addDays(plan.week_start, i))
  return (
    <section className="card">
      <h2>Your proposed plan</h2>
      <p className="small muted">Week of {shortDate(plan.week_start)} to {shortDate(addDays(plan.week_start, 6))}. {plan.used_calendar ? 'Fitted around the free time in your calendar.' : 'Planned without your calendar (assuming you are free during your waking hours), so check for clashes.'}</p>
      {plan.summary && <div className="agent"><span className="agent-name">Planner</span><p>{plan.summary}</p></div>}

      {plan.items.length > 0 && (
        <div className="glance">
          <strong>Your week at a glance</strong>
          <div className="chips">
            {BALANCE.map((b) => ({ ...b, n: plan.items.filter((i) => b.kinds.includes(i.kind)).length })).filter((b) => b.n > 0).map((b) => (
              <span key={b.label} className="tag">{b.label} · {b.n}</span>
            ))}
          </div>
          {anchors(plan.items).length > 0 && <p className="small">Routine anchors: {anchors(plan.items).join('; ')}. Keeping habits at the same time makes them easier to stick to.</p>}
        </div>
      )}
      {plan.class_search && (
        <div className="classnote">
          <strong>Fitness classes:</strong> {plan.class_search.found} real {plan.class_search.found === 1 ? 'class' : 'classes'} found that fit your free time (you asked for {plan.class_search.requested}).
          {plan.class_search.note && <> {plan.class_search.note}</>}
          {plan.class_search.unreadable.length > 0 && (
            <ul>
              {plan.class_search.unreadable.map((u) => (
                <li key={u.name}>{u.name}: I couldn't read the schedule{u.url && <> · <a href={u.url} target="_blank" rel="noopener noreferrer">open their schedule</a></>}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {plan.dinner_search && (
        <div className="classnote dinner">
          <strong>{plan.dinner_search.style === 'walk_in' ? `Walk-in ${plan.dinner_search.meal} ideas` : `${plan.dinner_search.meal[0].toUpperCase()}${plan.dinner_search.meal.slice(1)} reservations`}:</strong>{' '}
          {plan.dinner_search.restaurants.length > 0
            ? plan.dinner_search.style === 'walk_in'
              ? 'places with no booking site found. Nothing to book.'
              : `${plan.dinner_search.restaurants.length === 1 ? 'a restaurant' : 'restaurants'} that take reservations. Nothing is booked: use each link to check availability and book.`
            : ''}
          {plan.dinner_search.restaurants.length > 0 && (
            <ul className="restos">
              {plan.dinner_search.restaurants.map((r) => (
                <li key={r.name}>
                  <strong>{r.name}</strong>{r.cuisine ? ` · ${r.cuisine}` : ''}{r.price ? ` · ${r.price}` : ''}{r.address ? ` · ${r.address}` : ''}{' '}
                  {plan.dinner_search!.style === 'reservation' && r.reservation_url
                    ? <a href={r.reservation_url} target="_blank" rel="noopener noreferrer">Reserve / check availability</a>
                    : <a href={r.url} target="_blank" rel="noopener noreferrer">Restaurant's page</a>}
                  {r.has_times && <span className="small muted"> · a time was read from their page</span>}
                  {plan.dinner_search!.style === 'walk_in' && <span className="small muted"> · {r.walk_in_confirmed ? 'their page says walk-in' : 'no booking site found'}</span>}
                </li>
              ))}
            </ul>
          )}
          {plan.dinner_search.note && <p className="small">{plan.dinner_search.note}</p>}
          {plan.dinner_search.unreadable.length > 0 && (
            <ul>
              {plan.dinner_search.unreadable.map((u) => (
                <li key={u.name}>{u.name}: I couldn't read the page{u.url && <> · <a href={u.url} target="_blank" rel="noopener noreferrer">open it</a></>}</li>
              ))}
            </ul>
          )}
          <p className="small muted">Read on {plan.dinner_search.checked}. Tell the restaurant about any allergies or diet needs: I can't tell whether a dish is safe.</p>
        </div>
      )}
      {plan.movie_search && (
        <div className="classnote dinner">
          <strong>{plan.movie_search.where === 'theater' ? 'Playing in theaters near you' : 'Movies to watch at home'}:</strong>
          {plan.movie_search.movies.length > 0 && (
            <ul className="restos">
              {plan.movie_search.movies.map((m) => (
                <li key={m.title}>
                  <strong>{m.title}</strong>{m.year ? ` (${m.year})` : ''}{m.genres.length ? ` · ${m.genres.join(', ')}` : ''}{m.where ? ` · ${plan.movie_search!.where === 'theater' ? 'at' : 'on'} ${m.where}` : ''}{' '}
                  <a href={m.watch_url || m.url} target="_blank" rel="noopener noreferrer">{m.watch_url ? (plan.movie_search!.where === 'theater' ? 'Showtimes and tickets' : 'Where to watch') : 'The page I read'}</a>
                  {m.has_times && <span className="small muted"> · a showtime was read from the page</span>}
                  {m.blurb && <span className="small muted"> · {m.blurb}</span>}
                </li>
              ))}
            </ul>
          )}
          {plan.movie_search.note && <p className="small">{plan.movie_search.note}</p>}
          {plan.movie_search.unreadable.length > 0 && (
            <ul>
              {plan.movie_search.unreadable.map((u) => (
                <li key={u.name}>{u.name}: I couldn't read the page{u.url && <> · <a href={u.url} target="_blank" rel="noopener noreferrer">open it</a></>}</li>
              ))}
            </ul>
          )}
          <p className="small muted">Read on {plan.movie_search.checked}. Nothing is booked or bought.</p>
        </div>
      )}
      {plan.items.length === 0 && <p className="note">Nothing could be scheduled in the free time available.</p>}
      {days.map((d) => {
        const items = plan.items.filter((i) => i.day === d)
        if (!items.length) return null
        return (
          <div key={d} className="planday">
            <h3>{dayLabel(d)}</h3>
            <ul className="items">
              {items.map((it) => (
                <li key={it.id} className={`item ${it.kind}${selectedId === it.id ? ' sel' : ''}`} onClick={() => onSelect?.(selectedId === it.id ? null : it.id)}>
                  <div className="item-head">
                    <div className="item-title">
                      <span className={`ico ${it.kind}`}><KindIcon kind={it.kind} /></span>
                      <div>
                        <strong>{it.title}</strong>
                        <p className="small muted">{time12(it.start)} – {time12(it.end)}</p>
                      </div>
                    </div>
                    <span className={`tag ${it.kind}`}>{KIND_LABEL[it.kind]}</span>
                  </div>
                  {it.class_info && (
                    <div className="classbox">
                      <p className="small"><strong>Real class</strong> · {it.class_info.studio}{it.class_info.address ? ` · ${it.class_info.address}` : ''}</p>
                      <p className="small">
                        Read from <a href={it.class_info.url} target="_blank" rel="noopener noreferrer">the studio's schedule</a> on {plan.class_search?.checked ?? 'today'}.
                        {it.class_info.length_assumed && ' The studio lists only the start time, so the length shown is an assumption.'}
                        {' '}Times can change, so confirm and book on their site.
                      </p>
                    </div>
                  )}
                  {it.venue_info && (
                    <div className="classbox">
                      <p className="small"><strong>{it.venue_info.style === 'walk_in' ? 'Walk-in, no reservation' : it.venue_info.availability === 'read' ? 'Time read from the restaurant\'s page' : 'Table not booked, availability not confirmed'}</strong> · {it.venue_info.name}{it.venue_info.cuisine ? ` · ${it.venue_info.cuisine}` : ''}{it.venue_info.price ? ` · ${it.venue_info.price}` : ''}{it.venue_info.address ? ` · ${it.venue_info.address}` : ''}</p>
                      <p className="small">
                        Read from <a href={it.venue_info.url} target="_blank" rel="noopener noreferrer">this page</a> on {plan.dinner_search?.checked ?? 'today'}.
                        <> <a href={it.venue_info.reservation_url || it.venue_info.url} target="_blank" rel="noopener noreferrer">{it.venue_info.style === 'walk_in' ? "Restaurant's page (check hours)" : it.venue_info.reservation_url ? 'Check availability and book' : "Open the restaurant's page to book"}</a>{it.venue_info.style === 'walk_in' ? '.' : <> yourself{it.venue_info.availability === 'read' ? ': that time may be gone by now' : ''}.</>}</>
                        {' '}Tell the restaurant about any allergies or diet needs: I can't tell whether a dish is safe.
                      </p>
                    </div>
                  )}
                  {it.movie_info && (
                    <div className="classbox">
                      <p className="small"><strong>{it.movie_info.where_kind === 'theater' ? (it.movie_info.availability === 'read' ? 'Showtime read from the theater\'s page' : 'Showtime not confirmed') : 'Movie night at home'}</strong> · {it.movie_info.title}{it.movie_info.year ? ` (${it.movie_info.year})` : ''}{it.movie_info.where ? ` · ${it.movie_info.where_kind === 'theater' ? 'at' : 'on'} ${it.movie_info.where}` : ''}</p>
                      <p className="small">
                        Read from <a href={it.movie_info.url} target="_blank" rel="noopener noreferrer">this page</a> on {plan.movie_search?.checked ?? 'today'}.
                        {it.movie_info.watch_url && <> <a href={it.movie_info.watch_url} target="_blank" rel="noopener noreferrer">{it.movie_info.where_kind === 'theater' ? 'Showtimes and tickets' : 'Where to watch'}</a>.</>}
                        {it.movie_info.where_kind === 'theater' && ' I don\'t buy tickets: check the time and buy them yourself.'}
                      </p>
                    </div>
                  )}
                  {it.why && <p className="small">{it.why}</p>}
                  {it.benefit && (
                    <details className="why">
                      <summary>Why this helps</summary>
                      <p className="small"><strong>{it.benefit.lead}</strong>{it.benefit.goal_link && <> {it.benefit.goal_link}</>}</p>
                      <ul className="quotes">
                        {it.benefit.evidence.map((e) => (
                          <li key={e.quote}>
                            <strong>{e.topic}:</strong> <q>{e.quote}</q>
                            <span className="small muted"> {e.source}: <a href={e.url} target="_blank" rel="noopener noreferrer">read the source</a> (checked {e.checked})</span>
                          </li>
                        ))}
                      </ul>
                      <p className="small muted">General health information from the sources above, not medical advice.</p>
                    </details>
                  )}
                  {it.notes && <p className="small muted">{it.notes}</p>}
                  {it.recipe && (
                    <details>
                      <summary>Recipe · {it.recipe.servings} servings · {it.recipe.prep_minutes + it.recipe.cook_minutes} min</summary>
                      <p className="small"><strong>Ingredients</strong></p>
                      <ul>{it.recipe.ingredients.map((x) => <li key={x}>{x}</li>)}</ul>
                      <p className="small"><strong>Steps</strong></p>
                      <ol>{it.recipe.steps.map((x) => <li key={x}>{x}</li>)}</ol>
                    </details>
                  )}
                  {it.workout && (
                    <details>
                      <summary>Workout · {it.workout.intensity}{it.workout.equipment.length ? ` · ${it.workout.equipment.join(', ')}` : ''}</summary>
                      {it.workout.adaptation_note && <p className="small note">{it.workout.adaptation_note}</p>}
                      {it.workout.warmup.length > 0 && <><p className="small"><strong>Warm-up</strong></p><ul>{it.workout.warmup.map((x) => <li key={x}>{x}</li>)}</ul></>}
                      <p className="small"><strong>Exercises</strong></p>
                      <ul>{it.workout.main.map((x) => <li key={x}>{x}</li>)}</ul>
                      {it.workout.cooldown.length > 0 && <><p className="small"><strong>Cool-down</strong></p><ul>{it.workout.cooldown.map((x) => <li key={x}>{x}</li>)}</ul></>}
                    </details>
                  )}
                  <button type="button" className="link" onClick={() => onRemove(it.id)}>Remove from plan</button>
                </li>
              ))}
            </ul>
          </div>
        )
      })}

      {plan.unplaced.length > 0 && (
        <div className="unplaced">
          <h3>Couldn't fit</h3>
          <ul>{plan.unplaced.map((u) => <li key={u.title}><strong>{u.title}</strong>{u.reason ? ` · ${u.reason}` : ''}</li>)}</ul>
        </div>
      )}

      <p className="small muted">{plan.disclaimer}</p>
      <button className="primary" type="button" disabled={busy || plan.items.length === 0} onClick={onContinue}>Looks good: review and approve</button>
      {!open ? (
        <button type="button" className="secondary" disabled={busy} onClick={() => setOpen(true)}>Change something or propose a different plan</button>
      ) : (
        <div className="revise">
          <label className="field">
            What would you like to change?
            <textarea rows={3} maxLength={600} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. Put the workouts in the morning and swap the Thai dinner for something lighter" autoFocus />
          </label>
          <div className="chips" role="group" aria-label="Quick ideas">
            {IDEAS.map((i) => <button key={i} type="button" className="chip" onClick={() => addIdea(i)}>{i}</button>)}
          </div>
          <p className="small muted">Items you've removed won't come back. Leave this blank to just try a different arrangement.</p>
          <button className="primary" type="button" disabled={busy} onClick={() => { onRegenerate(notes.trim()); setOpen(false); setNotes('') }}>{notes.trim() ? 'Update my plan' : 'Try a different plan'}</button>
          <button type="button" className="link" onClick={() => setOpen(false)}>Cancel</button>
        </div>
      )}
      <p className="small muted">Nothing is added to any calendar until you approve and download the file yourself.</p>
    </section>
  )
}
