import type { Cooking, Selections, Simple, Social, Workouts } from '../lib/week'
import { CLASS_TYPE, DINNER_TYPE, MEALS, MOVIE_TYPE, MAX_COUNT, MAX_PARTY, OPTIONS, REFINE, type Refine } from '../lib/week'
import { KindIcon } from '../lib/kinds'

type Cat = 'workouts' | 'cooking' | 'social' | 'errands' | 'rest' | 'wellness'
const CATS: { id: Cat; label: string; hint: string }[] = [
  { id: 'workouts', label: 'Workouts', hint: 'Gym, runs, yoga…' },
  { id: 'cooking', label: 'Cooking', hint: 'Meals at home' },
  { id: 'social', label: 'Friends & family', hint: 'Meals out, calls…' },
  { id: 'errands', label: 'Errands & chores', hint: 'Groceries, appointments…' },
  { id: 'rest', label: 'Rest', hint: 'Downtime, a quiet night' },
  { id: 'wellness', label: 'Wellness habits', hint: 'Walks, stretching, wind-down…' },
]
const START = { workouts: { count: null, types: [], length: null, where: [] } as Workouts, cooking: { meals: null, which: [], cuisines: [], time: null, groceries: null, ingredients: '' } as Cooking, social: { count: null, kinds: [] } as Social, errands: { count: null, kinds: [] } as Simple, rest: { count: null, kinds: [] } as Simple, wellness: { count: null, kinds: [] } as Simple }

const toggle = (xs: string[], x: string) => (xs.includes(x) ? xs.filter((y) => y !== x) : [...xs, x])

function Chips({ options, picked, onPick, label }: { options: string[]; picked: string[]; onPick: (o: string) => void; label: string }) {
  return (
    <div className="chips" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o} type="button" className={picked.includes(o) ? 'chip on' : 'chip'} aria-pressed={picked.includes(o)} onClick={() => onPick(o)}>{o}</button>
      ))}
    </div>
  )
}

function Count({ max, value, onPick, label }: { max: number; value: number | null; onPick: (n: number) => void; label: string }) {
  return (
    <div className="chips count" role="group" aria-label={label}>
      {Array.from({ length: max }, (_, i) => i + 1).map((n) => (
        <button key={n} type="button" className={value === n ? 'chip on' : 'chip'} aria-pressed={value === n} onClick={() => onPick(n)}>{n}</button>
      ))}
    </div>
  )
}

// For picked options that bundle alternatives ("Coffee or drinks"), ask which one(s) the user actually wants.
function Refiner({ picked, refine, onChange }: { picked: string[]; refine?: Refine; onChange: (r: Refine) => void }) {
  const asks = picked.filter((o) => REFINE[o])
  if (asks.length === 0) return null
  return (
    <>
      {asks.map((o) => (
        <div key={o} className="refine">
          <p className="q-label">{o}: {REFINE[o].q} <span className="small muted">(pick any)</span></p>
          <Chips options={REFINE[o].choices} picked={refine?.[o] ?? []} onPick={(c) => onChange({ ...(refine ?? {}), [o]: toggle(refine?.[o] ?? [], c) })} label={REFINE[o].q} />
        </div>
      ))}
    </>
  )
}
const dropRefine = (refine: Refine | undefined, kinds: string[]): Refine | undefined => (refine ? Object.fromEntries(Object.entries(refine).filter(([k]) => kinds.includes(k))) : refine) // forget answers for options that were un-picked

// Step 1. Pick what you want; each pick opens its own follow-up choices, one group at a time.
export default function WeekBuilder({ sel, onChange, hasCity }: { sel: Selections; onChange: (s: Selections) => void; hasCity: boolean }) {
  const on = (c: Cat) => sel[c] !== undefined
  const toggleCat = (c: Cat) => {
    const next = { ...sel }
    if (on(c)) delete next[c]
    else (next as Record<string, unknown>)[c] = START[c]
    onChange(next)
  }
  const w = sel.workouts, c = sel.cooking
  // choosing "A fitness class" opens the class questions; un-choosing it closes them
  const pickWorkoutType = (o: string) => {
    if (!w) return
    const types = toggle(w.types, o)
    const classes = o === CLASS_TYPE ? (types.includes(CLASS_TYPE) ? { count: null, mode: null, studio: '', types: [] } : undefined) : w.classes
    onChange({ ...sel, workouts: { ...w, types, classes, refine: dropRefine(w.refine, types) } })
  }
  // choosing "Go out to eat" or "Movie night" opens their questions; un-choosing it closes them
  const pickSocial = (o: string) => {
    const v = sel.social
    if (!v) return
    const kinds = toggle(v.kinds, o)
    const dinner = o === DINNER_TYPE ? (kinds.includes(DINNER_TYPE) ? { count: null, meal: null, style: null, party: null, cuisines: [], named: '' } : undefined) : v.dinner
    const movie = o === MOVIE_TYPE ? (kinds.includes(MOVIE_TYPE) ? { count: null, where: null, genres: [] } : undefined) : v.movie
    onChange({ ...sel, social: { ...v, kinds, dinner, movie, refine: dropRefine(v.refine, kinds) } })
  }
  const set = <K extends Cat>(k: K, v: NonNullable<Selections[K]>) => onChange({ ...sel, [k]: v })

  const sit = sel.situation ?? { busy: null, goals: [] }
  const setSit = (v: typeof sit) => onChange({ ...sel, situation: v })
  return (
    <div>
      <fieldset className="cascade about">
        <legend>About your week <span className="small muted">(optional)</span></legend>
        <p className="small muted">This helps me build a routine you can actually keep: realistic, not overloaded. (Whether you're a student or a professional comes from your Profile.)</p>
        <p className="q-label">How busy is this week?</p>
        <Chips options={OPTIONS.busy} picked={sit.busy ? [sit.busy] : []} onPick={(o) => setSit({ ...sit, busy: sit.busy === o ? null : o })} label="How busy" />
        <p className="q-label">What do you most want from your routine? <span className="small muted">(up to 3)</span></p>
        <Chips options={OPTIONS.priorities} picked={sit.goals} onPick={(o) => setSit({ ...sit, goals: sit.goals.includes(o) ? sit.goals.filter((g) => g !== o) : sit.goals.length < 3 ? [...sit.goals, o] : sit.goals })} label="Priorities" />
      </fieldset>
      <p className="small muted">What do you want to fit into your week? Pick any that apply, then answer a couple of quick questions for each.</p>
      <div className="cats" role="group" aria-label="What you want this week">
        {CATS.map((k) => (
          <button key={k.id} type="button" data-kind={k.id} className={on(k.id) ? 'cat on' : 'cat'} aria-pressed={on(k.id)} onClick={() => toggleCat(k.id)}>
            <span className={`ico ${k.id}`}><KindIcon kind={k.id} /></span>
            <strong>{k.label}</strong>
            <span className="small">{k.hint}</span>
          </button>
        ))}
      </div>

      {w && (
        <fieldset className="cascade">
          <legend>Workouts</legend>
          <p className="q-label">How many this week?</p>
          <Count max={MAX_COUNT.workouts} value={w.count} onPick={(n) => set('workouts', { ...w, count: n })} label="Number of workouts" />
          {w.count && (
            <>
              <p className="q-label">What kind? <span className="small muted">(pick any)</span></p>
              <Chips options={OPTIONS.workoutTypes} picked={w.types} onPick={(o) => pickWorkoutType(o)} label="Workout types" />
              <Refiner picked={w.types} refine={w.refine} onChange={(r) => set('workouts', { ...w, refine: r })} />
            </>
          )}
          {w.count && w.types.includes(CLASS_TYPE) && w.classes && (
            <div className="subcascade">
              <p className="q-label">Fitness classes</p>
              <p className="small muted">I'll look up real class times and fit them into your free time.</p>
              <p className="q-label">How many of your {w.count} workouts should be classes?</p>
              <Count max={w.count} value={w.classes.count} onPick={(n) => set('workouts', { ...w, classes: { ...w.classes!, count: n } })} label="Number of classes" />
              {w.classes.count && (
                <>
                  <p className="q-label">Which studio?</p>
                  <Chips options={['A studio I already go to', 'Something new to try']} picked={w.classes.mode ? [w.classes.mode === 'studio' ? 'A studio I already go to' : 'Something new to try'] : []} onPick={(o) => set('workouts', { ...w, classes: { ...w.classes!, mode: o.startsWith('A studio') ? 'studio' : 'new' } })} label="Studio choice" />
                  {w.classes.mode === 'studio' && (
                    <label className="field">
                      Studio name
                      <input value={w.classes.studio} maxLength={80} placeholder="e.g. Breathing Room Yoga" onChange={(e) => set('workouts', { ...w, classes: { ...w.classes!, studio: e.target.value } })} />
                    </label>
                  )}
                </>
              )}
              {w.classes.count && w.classes.mode && (
                <>
                  <p className="q-label">What kind of class? <span className="small muted">(pick any)</span></p>
                  <Chips options={OPTIONS.classTypes} picked={w.classes.types} onPick={(o) => set('workouts', { ...w, classes: { ...w.classes!, types: toggle(w.classes!.types, o) } })} label="Class types" />
                </>
              )}
              {!hasCity && <p className="note">Add your city in Profile so I can find classes near you.</p>}
            </div>
          )}
          {w.count && w.types.length > 0 && (
            <>
              <p className="q-label">How long each?</p>
              <Chips options={OPTIONS.workoutLength} picked={w.length ? [w.length] : []} onPick={(o) => set('workouts', { ...w, length: w.length === o ? null : o })} label="Workout length" />
              <p className="q-label">Where? <span className="small muted">(pick any)</span></p>
              <Chips options={OPTIONS.workoutWhere} picked={w.where} onPick={(o) => set('workouts', { ...w, where: toggle(w.where, o) })} label="Where you work out" />
            </>
          )}
        </fieldset>
      )}

      {c && (
        <fieldset className="cascade">
          <legend>Cooking</legend>
          <p className="q-label">How many meals will you cook?</p>
          <Count max={MAX_COUNT.meals} value={c.meals} onPick={(n) => set('cooking', { ...c, meals: n })} label="Number of meals" />
          {c.meals && (
            <>
              <p className="q-label">Which meals? <span className="small muted">(pick any)</span></p>
              <Chips options={OPTIONS.meals} picked={c.which} onPick={(o) => set('cooking', { ...c, which: toggle(c.which, o) })} label="Meal types" />
              <p className="q-label">What kind of food? <span className="small muted">(pick any)</span></p>
              <Chips options={OPTIONS.cuisines} picked={c.cuisines} onPick={(o) => set('cooking', { ...c, cuisines: toggle(c.cuisines, o) })} label="Cuisines" />
            </>
          )}
          {c.meals && c.cuisines.length > 0 && (
            <>
              <p className="q-label">How much time per meal?</p>
              <Chips options={OPTIONS.cookTime} picked={c.time ? [c.time] : []} onPick={(o) => set('cooking', { ...c, time: c.time === o ? null : o })} label="Cooking time" />
            </>
          )}
          {c.meals && (
            <>
              <p className="q-label">Any ingredients you want to use? <span className="small muted">(optional)</span></p>
              <label className="field">
                <input value={c.ingredients} maxLength={200} aria-label="Ingredients you want to use" placeholder="e.g. spinach, chickpeas, sweet potatoes" onChange={(e) => set('cooking', { ...c, ingredients: e.target.value })} />
                <span className="small muted">Separate them with commas. I'll build them into the recipes (your diet and allergy notes still come first).</span>
              </label>
              <p className="q-label">Want a grocery shopping trip on the calendar?</p>
              <Chips options={['Yes, schedule one', 'No, I have what I need']} picked={c.groceries === null ? [] : [c.groceries ? 'Yes, schedule one' : 'No, I have what I need']} onPick={(o) => set('cooking', { ...c, groceries: o.startsWith('Yes') })} label="Grocery shopping trip" />
            </>
          )}
        </fieldset>
      )}

      {(
        [
          ['social', 'Friends & family', 'How many get-togethers?', OPTIONS.social, 'What kind? (pick any)'],
          ['errands', 'Errands & chores', 'How many errand blocks?', OPTIONS.errands, 'What needs doing? (pick any)'],
          ['rest', 'Rest', 'How many quiet blocks?', OPTIONS.rest, 'What would feel restful? (pick any)'],
          ['wellness', 'Wellness habits', 'How many habits this week?', OPTIONS.wellness, 'Which habits? (pick any)'],
        ] as const
      ).map(([key, title, q1, opts, q2]) => {
        const v = sel[key]
        if (!v) return null
        const d = key === 'social' ? sel.social?.dinner : undefined
        const sv = sel.social
        return (
          <fieldset key={key} className="cascade">
            <legend>{title}</legend>
            <p className="q-label">{q1}</p>
            <Count max={MAX_COUNT[key]} value={v.count} onPick={(n) => set(key, { ...v, count: n })} label={q1} />
            {v.count && (
              <>
                <p className="q-label">{q2}</p>
                <Chips options={opts} picked={v.kinds} onPick={(o) => (key === 'social' ? pickSocial(o) : set(key, { ...v, kinds: toggle(v.kinds, o), refine: dropRefine(v.refine, toggle(v.kinds, o)) }))} label={q2} />
                <Refiner picked={v.kinds} refine={v.refine} onChange={(r) => set(key, { ...v, refine: r })} />
              </>
            )}
            {v.count && key === 'social' && sv?.movie && (
              <div className="subcascade">
                <p className="q-label">Movie night</p>
                <p className="small muted">I'll suggest real movies and fit the night into your free time. I don't buy tickets.</p>
                <p className="q-label">How many of your {v.count} get-togethers are movie nights?</p>
                <Count max={Math.min(v.count, 3)} value={sv.movie.count} onPick={(n) => set('social', { ...sv, movie: { ...sv.movie!, count: n } })} label="Number of movie nights" />
                {sv.movie.count && (
                  <>
                    <p className="q-label">Out at a movie theater or staying in?</p>
                    <Chips options={['Go to a movie theater', 'Stay in']} picked={sv.movie.where ? [sv.movie.where === 'theater' ? 'Go to a movie theater' : 'Stay in'] : []} onPick={(o) => set('social', { ...sv, movie: { ...sv.movie!, where: o === 'Stay in' ? 'home' : 'theater' } })} label="Theater or home" />
                  </>
                )}
                {sv.movie.count && sv.movie.where && (
                  <>
                    <p className="q-label">What genre? <span className="small muted">(up to 3)</span></p>
                    <Chips options={OPTIONS.movieGenres} picked={sv.movie.genres} onPick={(o) => set('social', { ...sv, movie: { ...sv.movie!, genres: sv.movie!.genres.includes(o) ? sv.movie!.genres.filter((g) => g !== o) : sv.movie!.genres.length < 3 ? [...sv.movie!.genres, o] : sv.movie!.genres } })} label="Movie genres" />
                    <p className="small muted">{sv.movie.where === 'theater' ? "I'll look at what's playing near you." : "I'll suggest movies you can watch at home."}</p>
                    {sv.movie.where === 'theater' && !hasCity && <p className="note">Add your city in Profile so I can find what's playing near you.</p>}
                  </>
                )}
              </div>
            )}
            {v.count && d && sv && (
              <div className="subcascade">
                <p className="q-label">Going out to eat</p>
                <p className="small muted">I'll suggest a short list of restaurants in your area. I can't book for you: for reservations you'll get a link to each booking page.</p>
                <p className="q-label">How many of your {v.count} get-togethers are going out to eat?</p>
                <Count max={v.count} value={d.count} onPick={(n) => set('social', { ...sv, dinner: { ...d, count: n } })} label="Number of meals out" />
                {d.count && (
                  <>
                    <p className="q-label">Which meal?</p>
                    <Chips options={MEALS.map((m) => m.label)} picked={d.meal ? [MEALS.find((m) => m.id === d.meal)!.label] : []} onPick={(o) => set('social', { ...sv, dinner: { ...d, meal: MEALS.find((m) => m.label === o)!.id } })} label="Which meal" />
                  </>
                )}
                {d.count && d.meal && (
                  <>
                    <p className="q-label">Reservation or walk-in?</p>
                    <Chips options={['A reservation', 'Walk-in is fine']} picked={d.style ? [d.style === 'reservation' ? 'A reservation' : 'Walk-in is fine'] : []} onPick={(o) => set('social', { ...sv, dinner: { ...d, style: o === 'A reservation' ? 'reservation' : 'walk_in' } })} label="Reservation or walk-in" />
                    <p className="small muted">{d.style === 'walk_in' ? "I'll suggest places that don't take reservations." : d.style === 'reservation' ? "I'll suggest places that take reservations, with a link to each booking page." : ''}</p>
                  </>
                )}
                {d.count && d.meal && d.style && (
                  <>
                    <p className="q-label">For how many people?</p>
                    <Count max={MAX_PARTY} value={d.party} onPick={(n) => set('social', { ...sv, dinner: { ...d, party: n } })} label="Party size" />
                  </>
                )}
                {d.count && d.meal && d.style && d.party && (
                  <>
                    <p className="q-label">What kind of food? <span className="small muted">(pick any)</span></p>
                    <Chips options={OPTIONS.cuisines} picked={d.cuisines} onPick={(o) => set('social', { ...sv, dinner: { ...d, cuisines: toggle(d.cuisines, o) } })} label="Cuisines" />
                    <label className="field">
                      A restaurant you already have in mind <span className="small muted">(optional)</span>
                      <input value={d.named} maxLength={80} placeholder="e.g. Pepe's Pizzeria" onChange={(e) => set('social', { ...sv, dinner: { ...d, named: e.target.value } })} />
                    </label>
                  </>
                )}
                {!hasCity && <p className="note">Add your city in Profile so I can find restaurants near you.</p>}
              </div>
            )}
          </fieldset>
        )
      })}

      <label className="field">
        Anything else to schedule? <span className="small muted">(optional)</span>
        <textarea rows={2} maxLength={400} value={sel.other} onChange={(e) => onChange({ ...sel, other: e.target.value })} placeholder="e.g. call Mom on Sunday, haircut, finish the report" />
      </label>
      <label className="field">
        Anything the planner should know? <span className="small muted">(optional)</span>
        <textarea rows={2} maxLength={600} value={sel.extra} onChange={(e) => onChange({ ...sel, extra: e.target.value })} placeholder="e.g. keep Thursday evening free, I'm slow to wake up on Mondays" />
      </label>
    </div>
  )
}
