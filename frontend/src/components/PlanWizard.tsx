import { useState } from 'react'
import type { Answers, CalendarResult, Interview, Plan, Profile } from '../types'
import { fetchQuestions, prefetchPlan, proposePlan } from '../api'
import CalendarStep from './CalendarStep'
import CalendarPanel from './CalendarPanel'
import Building, { QUESTION_SAYINGS } from './Building'
import PlanReview from './PlanReview'
import ApproveStep from './ApproveStep'
import ExportStep from './ExportStep'
import WeekBuilder from './WeekBuilder'
import { Guide, type Mood } from './Mascot'
import { EMPTY, canContinue, classRequest, describeSelections, dinnerRequest, ingredientList, movieRequest, goalsFromSelections, type Selections } from '../lib/week'
import { addDays } from './WeekPicker'

const STEPS = ['Describe', 'Questions', 'Calendar', 'Plan', 'Approve', 'Export']

// The whole flow. Everything here lives in page memory only (nothing is saved between visits).
// First day of the week containing today, in the user's time zone and week-start setting.
function currentWeekStart(profile: Profile): string {
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: profile.timezone }).format(new Date()) // YYYY-MM-DD
  const dow = (new Date(`${today}T12:00:00Z`).getUTCDay() + 6) % 7 // 0 = Monday
  return addDays(today, -((dow - profile.week_start + 7) % 7))
}
// With only a day or two left in the current week, planning it is pointless: open on the next week instead (the picker can still go back).
export function defaultWeek(profile: Profile): number {
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: profile.timezone }).format(new Date())
  const dow = (new Date(`${today}T12:00:00Z`).getUTCDay() + 6) % 7
  const daysLeft = 7 - ((dow - profile.week_start + 7) % 7) // including today
  return daysLeft <= 2 ? 1 : 0
}
export default function PlanWizard({ profile }: { profile: Profile }) {
  const [step, setStep] = useState(1)
  const [sel, setSel] = useState<Selections>(EMPTY)
  const description = describeSelections(sel)
  const [interview, setInterview] = useState<Interview | null>(null)
  const [asked, setAsked] = useState('') // the description the questions were generated for
  const [answers, setAnswers] = useState<Answers>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [calendar, setCalendar] = useState<CalendarResult | null>(null)
  const [week, setWeek] = useState(() => defaultWeek(profile))
  const [plan, setPlan] = useState<Plan | null>(null)
  const [planBusy, setPlanBusy] = useState(false)
  const [planError, setPlanError] = useState('')
  const [planFree, setPlanFree] = useState<{ start: string; end: string }[] | null>(null) // the free windows the plan was built from (re-checked on export)
  const [approved, setApproved] = useState<Set<string>>(new Set())
  const [celebrate, setCelebrate] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null) // the plan item highlighted on the calendar
  const rangeStart = currentWeekStart(profile)
  const [removedTitles, setRemovedTitles] = useState<string[]>([]) // items the user removed; a revision won't bring them back

  // Fire and forget: the server starts the slow searches early so the plan step is quick. A failure changes nothing (the plan step just searches then).
  const startSearches = () => {
    const class_request = classRequest(sel) ?? undefined, dinner_request = dinnerRequest(sel) ?? undefined, movie_request = movieRequest(sel) ?? undefined
    if (!class_request && !dinner_request && !movie_request) return
    prefetchPlan({ week_start: addDays(rangeStart, week * 7), class_request, dinner_request, movie_request }).catch(() => undefined)
  }

  const ask = async (e: React.FormEvent) => {
    e.preventDefault()
    const text = description.trim()
    if (!canContinue(sel) || text.length < 3) return
    if (interview && text === asked) return setStep(2) // nothing changed: keep the answers
    setBusy(true)
    setError('')
    try {
      const out = await fetchQuestions(text)
      setInterview(out)
      setAsked(text)
      setAnswers({})
      setStep(2)
      startSearches() // the slow web searches (classes, meals out, movies) begin now, while you answer the questions
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  const setAnswer = (id: string, value: string[]) => setAnswers({ ...answers, [id]: value })
  const toggle = (id: string, option: string) => {
    const cur = answers[id] ?? []
    setAnswer(id, cur.includes(option) ? cur.filter((o) => o !== option) : [...cur, option])
  }
  // The user's picks give exact goals (and counts). Goals the question agent found in the free text are added only
  // for kinds the user didn't pick, so nothing is counted twice.
  const mergeGoals = () => {
    const exact = goalsFromSelections(sel)
    const covered = new Set(exact.map((g) => g.kind))
    const extra = (interview?.goals ?? []).filter((g) => g.kind === 'other' || !covered.has(g.kind))
    return [...exact, ...extra].slice(0, 12)
  }

  // Step 4: send the description, the answers and the free windows of the chosen week (never busy time or event details).
  const buildPlan = async (useCalendar: boolean, feedback?: string) => {
    if (!interview) return
    const revising = feedback !== undefined && !!plan
    const weekStart = revising ? plan!.week_start : addDays(rangeStart, week * 7)
    const weekDays = new Set(Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)))
    const dayKey = (iso: string) => new Intl.DateTimeFormat('en-CA', { timeZone: profile.timezone }).format(new Date(iso))
    const free = useCalendar && calendar ? calendar.free.filter((f) => weekDays.has(dayKey(f.start))).map(({ start, end }) => ({ start, end })) : null
    const qa = interview.questions
      .map((q) => ({ question: q.text, answer: (answers[q.id] ?? []).join(', ').trim() }))
      .filter((a) => a.answer)
    setPlanBusy(true)
    setPlanError('')
    setStep(4)
    try {
      const out = await proposePlan({
        description: asked,
        goals: mergeGoals(),
        answers: qa,
        week_start: weekStart,
        free,
        class_request: classRequest(sel) ?? undefined,
        dinner_request: dinnerRequest(sel) ?? undefined,
        ingredients: ingredientList(sel),
        movie_request: movieRequest(sel) ?? undefined,
        priorities: sel.situation?.goals ?? [],
        ...(revising ? { feedback, current: plan!.items.map(({ title, kind, day, start, end }) => ({ title, kind, day, start, end })), removed: removedTitles } : {}),
      })
      if (!revising) setRemovedTitles([])
      setPlan(out)
      setPlanFree(free)
      setApproved(new Set(out.items.map((i) => i.id)))
    } catch (err) {
      setPlan(null)
      setPlanError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setPlanBusy(false)
    }
  }

  const guide: { mood: Mood; text: string } =
    step === 1 ? (busy ? { mood: 'think', text: 'Let me think about what to ask you…' } : { mood: 'wave', text: "Hi, I'm Jelly. Tell me what your week needs and I'll help you build a routine you can keep." })
    : step === 2 ? { mood: 'happy', text: 'Just a few quick questions so I get it right. Skip any you like!' }
    : step === 3 ? { mood: 'happy', text: "Now let's find your free time. I only look at busy and free times, never at your event details." }
    : step === 4 ? (planBusy ? { mood: 'think', text: 'Let me think… building your plan and checking it against your calendar.' } : { mood: 'happy', text: "Here's your week. Remove or change anything that doesn't feel right." })
    : step === 5 ? { mood: 'happy', text: "Almost there. Here's your week laid over your calendar. Tick what you want to keep." }
    : celebrate ? { mood: 'party', text: 'All set. Your routine is ready to import. Enjoy your week!' }
    : { mood: 'wave', text: 'Ready to lock it in? Download your plan below.' }
  const answered = Object.values(answers).filter((a) => a.some((x) => x.trim())).length

  return (
    <div className="workspace">
    <aside className="sidebar">
      <Guide mood={guide.mood}>{guide.text}</Guide>
      <ol className="progress" aria-label="Steps">
        {STEPS.map((label, i) => {
          const n = i + 1
          const reachable = n === 1 || (n >= 2 && n <= 3 && !!interview) || (n === 4 && (!!plan || planBusy)) || ((n === 5 || n === 6) && !!plan && plan.items.length > 0)
          return (
            <li key={label} className={n === step ? 'cur' : n < step ? 'done' : ''}>
              <button type="button" disabled={!reachable} onClick={() => setStep(n)} aria-current={n === step ? 'step' : undefined}>
                <span className="num" aria-hidden="true">{n < step ? '✓' : n}</span>
                <span className="lbl">{label}</span>
              </button>
            </li>
          )
        })}
      </ol>

      {step === 1 && busy && <Building sayings={QUESTION_SAYINGS} />}
      {step === 1 && !busy && (
        <section className="card">
          <h2>What do you want from your week?</h2>
          <form onSubmit={ask}>
            <WeekBuilder sel={sel} onChange={setSel} hasCity={!!profile.city.trim()} />
            {error && <p className="error" role="alert">{error}</p>}
            <button className="primary" type="submit" disabled={!canContinue(sel)}>
              {interview && description.trim() === asked ? 'Back to my questions' : 'Next: a few more questions'}
            </button>
            <p className="small muted">Only your choices, what you type here, and your waking hours are sent to the AI. Your calendar and profile notes are not.</p>
          </form>
        </section>
      )}

      {step === 2 && interview && (
        <section className="card">
          <h2>A few quick questions</h2>
          {mergeGoals().length > 0 && (
            <div className="goals">
              <p className="small muted">Here's what you asked for:</p>
              <ul>
                {mergeGoals().map((g) => (
                  <li key={g.activity}>
                    <strong>{g.activity}</strong>
                    {g.times_per_week ? ` · ${g.times_per_week}× a week` : ''}
                    {g.notes ? <span className="muted"> · {g.notes}</span> : null}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <form onSubmit={(e) => { e.preventDefault(); setStep(3) }}>
            {interview.questions.map((q) => (
              <fieldset key={q.id} className="q">
                <legend>{q.text}</legend>
                {q.why && <p className="small muted">{q.why}</p>}
                {q.kind === 'text' ? (
                  <input value={(answers[q.id] ?? [''])[0]} onChange={(e) => setAnswer(q.id, [e.target.value])} maxLength={300} aria-label={q.text} />
                ) : (
                  q.options.map((o) => (
                    <label key={o} className="check">
                      <input
                        type={q.kind === 'single' ? 'radio' : 'checkbox'}
                        name={q.id}
                        checked={(answers[q.id] ?? []).includes(o)}
                        onChange={() => (q.kind === 'single' ? setAnswer(q.id, [o]) : toggle(q.id, o))}
                      />
                      {o}
                    </label>
                  ))
                )}
              </fieldset>
            ))}
            <p className="small muted">{answered} of {interview.questions.length} answered. You can skip any question.</p>
            <button className="primary" type="submit">Continue to my calendar</button>
            <button type="button" className="link" onClick={() => setStep(1)}>Change what I wrote</button>
          </form>
        </section>
      )}

      {step === 3 && interview && (
        <>
          <CalendarStep result={calendar} onResult={setCalendar} />
          <section className="card">
            <h2>Build my plan</h2>
            <p className="small muted">The planner uses your description, answers, the free time in the week showing on the calendar, and your profile notes (city, diet and allergies, injuries or limits) so it can respect them. It never sees your busy times or event details.</p>
            <button className="primary" type="button" disabled={!calendar || planBusy} onClick={() => buildPlan(true)}>
              {calendar ? 'Plan this week around my calendar' : 'Read your calendar above first'}
            </button>
            <button type="button" className="link" disabled={planBusy} onClick={() => buildPlan(false)}>Skip my calendar and assume I'm free during my waking hours</button>
            <br />
            <button type="button" className="link" onClick={() => setStep(2)}>Back to my answers</button>
          </section>
        </>
      )}

      {step === 4 && (
        <>
          {planBusy && <Building />}
          {planError && <section className="card"><p className="error" role="alert">{planError}</p><button type="button" onClick={() => setStep(3)}>Back</button></section>}
          {plan && !planBusy && (
            <>
              <PlanReview
                plan={plan}
                busy={planBusy}
                onRemove={(id) => {
                  setRemovedTitles([...removedTitles, plan.items.find((i) => i.id === id)?.title ?? ''].filter(Boolean).slice(-20))
                  setPlan({ ...plan, items: plan.items.filter((i) => i.id !== id) })
                  setApproved(new Set([...approved].filter((x) => x !== id)))
                }}
                onRegenerate={(notes) => buildPlan(plan.used_calendar && !!calendar, notes)}
                onContinue={() => setStep(5)}
                selectedId={selectedId}
                onSelect={setSelectedId}
              />
              <section className="card">
                <button type="button" className="link" onClick={() => setStep(3)}>Back to my calendar</button>
              </section>
            </>
          )}
        </>
      )}

      {step === 5 && plan && (
        <ApproveStep
          plan={plan}
          approved={approved}
          onToggle={(id) => {
            const next = new Set(approved)
            if (next.has(id)) next.delete(id)
            else next.add(id)
            setApproved(next)
          }}
          onApprove={() => setStep(6)}
          onBack={() => setStep(4)}
        />
      )}

      {step === 6 && plan && (
        <ExportStep
          plan={plan}
          approved={approved}
          free={planFree}
          priorities={sel.situation?.goals ?? []}
          onBack={() => setStep(5)}
          onDone={() => setCelebrate(true)}
          onStartOver={() => {
            setCelebrate(false)
            setPlan(null)
            setApproved(new Set())
            setPlanFree(null)
            setStep(3)
          }}
        />
      )}
    </aside>
    <div className="stage">
      <CalendarPanel profile={profile} rangeStart={rangeStart} weeks={6} week={week} onWeek={setWeek} calendar={calendar} plan={plan} approved={approved} selectedId={selectedId} onSelect={setSelectedId} planning={planBusy} />
    </div>
    </div>
  )
}
