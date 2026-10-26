import type { Goal } from '../types'

// What the user picks on the first page. Each category opens its own follow-up choices (the "cascade").
export interface ClassPick { count: number | null; mode: 'studio' | 'new' | null; studio: string; types: string[] }
export type Refine = Record<string, string[]> // an option that bundles alternatives ('Coffee or drinks') -> which ones the user actually wants
export interface Workouts { count: number | null; types: string[]; length: string | null; where: string[]; classes?: ClassPick; refine?: Refine }
export interface Cooking { meals: number | null; which: string[]; cuisines: string[]; time: string | null; groceries: boolean | null; ingredients: string }
export interface Simple { count: number | null; kinds: string[]; refine?: Refine }

export type Meal = 'breakfast' | 'brunch' | 'lunch' | 'dinner'
export interface DinnerPick { count: number | null; meal: Meal | null; style: 'reservation' | 'walk_in' | null; party: number | null; cuisines: string[]; named: string }
export interface MoviePick { count: number | null; where: 'theater' | 'home' | null; genres: string[] }
export interface Social extends Simple { dinner?: DinnerPick; movie?: MoviePick }

export interface Situation { busy: string | null; goals: string[] }

export interface Selections {
  situation?: Situation // who the plan is for and what matters most (shapes how much is scheduled)
  workouts?: Workouts
  cooking?: Cooking
  social?: Social
  errands?: Simple
  rest?: Simple
  wellness?: Simple
  other: string // other things to schedule, in the user's words
  extra: string // anything else to tell the planner
}

export const EMPTY: Selections = { other: '', extra: '' }

export const OPTIONS = {
  workoutTypes: ['Strength', 'Running', 'Cycling', 'Swimming', 'Yoga or Pilates', 'HIIT or circuits', 'Walking or hiking', 'A fitness class', 'Sports', 'Mobility or stretching', 'Not sure, suggest for me'],
  classTypes: ['Yoga', 'Pilates', 'Cycling or spin', 'Strength', 'HIIT or bootcamp', 'Boxing', 'Barre', 'Dance', 'Climbing', 'Swimming', 'Martial arts', 'Surprise me'],
  workoutLength: ['20–30 min', '30–45 min', '45–60 min', '60+ min'],
  workoutWhere: ['Home', 'Gym', 'Outdoors'],
  meals: ['Dinner', 'Lunch', 'Breakfast', 'Meal prep'],
  cuisines: ['Italian', 'Mexican', 'Indian', 'Thai', 'Japanese', 'Chinese', 'Mediterranean', 'Middle Eastern', 'American comfort', 'French', 'Korean', 'Surprise me'],
  cookTime: ['Under 30 min', '30–60 min', 'An hour or more is fine'],
  social: ['Go out to eat', 'Coffee or drinks', 'Outdoor activity', 'Game night', 'Movie night', 'Call or video chat', 'Event or show'],
  errands: ['Groceries', 'Appointments', 'Cleaning or chores', 'Laundry', 'Bills or admin', 'Shopping'],
  rest: ['A free evening', 'Reading', 'A nap', 'Self-care', 'Time outdoors alone'],
  wellness: ['Morning routine', 'Evening wind-down', 'Walk or fresh air', 'Stretch or mobility break', 'Breathing or meditation', 'Journaling', 'Screen-free time'],
  movieGenres: ['Action', 'Comedy', 'Drama', 'Horror', 'Sci-fi or fantasy', 'Romance', 'Thriller', 'Animation', 'Documentary', 'Family', 'Surprise me'],
  busy: ['Light', 'Normal', 'Packed'],
  priorities: ['More energy', 'Less stress', 'Better sleep', 'Consistency', 'Fitness', 'Time with people', 'Focus'],
}

// Options that really bundle two or more things get a follow-up question, so the planner knows which one the user wants.
export const REFINE: Record<string, { q: string; choices: string[] }> = {
  'Yoga or Pilates': { q: 'Yoga, Pilates or both?', choices: ['Yoga', 'Pilates'] },
  'HIIT or circuits': { q: 'HIIT or circuits?', choices: ['HIIT', 'Circuit training'] },
  'Walking or hiking': { q: 'Walking or hiking?', choices: ['Walking', 'Hiking'] },
  Sports: { q: 'Which sport?', choices: ['Basketball', 'Soccer', 'Tennis', 'Pickleball', 'Volleyball', 'Something else'] },
  'Coffee or drinks': { q: 'Coffee, tea or drinks?', choices: ['Coffee', 'Tea', 'Cocktails or a bar', 'Mocktails or juice'] },
  'Outdoor activity': { q: 'What outdoors?', choices: ['A hike', 'A walk in the park', 'A picnic', 'Beach or lake', 'A bike ride', 'A pickup game'] },
  'Game night': { q: 'What kind of games?', choices: ['Board games', 'Card games', 'Video games', 'Trivia or party games'] },
  'Event or show': { q: 'What kind of event?', choices: ['Concert or live music', 'Theater or comedy', 'A sports game', 'Museum or exhibit', 'Festival or market'] },
  'Call or video chat': { q: 'Who with?', choices: ['Family', 'A friend', 'A group'] },
  Appointments: { q: 'What kind of appointment?', choices: ['Doctor or dentist', 'Haircut or salon', 'Car or home service', 'Something else'] },
  'Cleaning or chores': { q: 'Cleaning or chores?', choices: ['Tidying up', 'A deep clean', 'Dishes and trash', 'Yard work'] },
  Shopping: { q: 'Shopping for what?', choices: ['Clothes', 'Household items', 'Gifts', 'Electronics'] },
  'Bills or admin': { q: 'Which one?', choices: ['Paying bills', 'Paperwork or forms', 'Email catch-up'] },
  'Self-care': { q: 'What kind of self-care?', choices: ['A long bath or shower', 'Skincare', 'A massage or spa', 'A hair or face mask'] },
  'Morning routine': { q: 'What in your morning?', choices: ['Water and light stretching', 'Sunlight or fresh air', 'A few quiet minutes'] },
  'Evening wind-down': { q: 'How do you wind down?', choices: ['Reading', 'A warm shower or bath', 'Gentle stretching', 'Tea and screens off'] },
  'Walk or fresh air': { q: 'What kind of walk?', choices: ['A short walk', 'A longer walk', 'Sitting outside'] },
  'Breathing or meditation': { q: 'Breathing or meditation?', choices: ['Breathing exercises', 'Guided meditation'] },
  'Stretch or mobility break': { q: 'Which areas?', choices: ['Neck and shoulders', 'Hips and legs', 'Full body'] },
}

// "Coffee or drinks (coffee, tea)": the picked options with the user's choices inside each bundled option.
export const withRefine = (options: string[], refine?: Refine) => options.map((o) => (refine?.[o]?.length ? `${o} (${refine[o].join(', ')})` : o))

export const CLASS_TYPE = 'A fitness class'
export const DINNER_TYPE = 'Go out to eat'
export const MEALS: { id: Meal; label: string }[] = [{ id: 'breakfast', label: 'Breakfast' }, { id: 'brunch', label: 'Brunch' }, { id: 'lunch', label: 'Lunch' }, { id: 'dinner', label: 'Dinner' }]
export const MOVIE_TYPE = 'Movie night'
export const MAX_PARTY = 12
export const MAX_COUNT = { workouts: 7, meals: 7, social: 5, errands: 5, rest: 4, wellness: 7 }

const list = (xs: string[]) => xs.join(', ')
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

// A complete "I want real classes" request, or null. Sent to the server so the schedule uses real class times.
export interface ClassRequest { mode: 'studio' | 'new'; studio: string; types: string[]; count: number }
export function classRequest(s: Selections): ClassRequest | null {
  const c = s.workouts?.classes
  if (!s.workouts?.types.includes(CLASS_TYPE) || !c?.count || !c.mode) return null
  if (c.mode === 'studio' && !c.studio.trim()) return null
  return { mode: c.mode, studio: c.mode === 'studio' ? c.studio.trim().slice(0, 80) : '', types: c.types.filter((t) => t !== 'Surprise me').slice(0, 6), count: Math.min(c.count, s.workouts.count ?? c.count) }
}

// Ingredients the user wants in their recipes: typed with commas, cleaned to at most 8 short items.
export const MAX_INGREDIENTS = 8
export function ingredientList(s: Selections): string[] {
  const raw = s.cooking?.meals ? s.cooking.ingredients : ''
  return [...new Set(raw.split(/[,\n;]/).map((x) => x.replace(/\s+/g, ' ').trim().slice(0, 40)).filter(Boolean))].slice(0, MAX_INGREDIENTS)
}

// A complete "find me a dinner reservation" request, or null. Sent to the server so restaurants are real and checked.
export interface DinnerRequest { count: number; meal: Meal; style: 'reservation' | 'walk_in'; party: number; cuisines: string[]; named: string }
export function dinnerRequest(s: Selections): DinnerRequest | null {
  const d = s.social?.dinner
  if (!s.social?.kinds.includes(DINNER_TYPE) || !d?.count || !d.meal || !d.style || !d.party) return null
  return { count: Math.min(d.count, s.social.count ?? d.count), meal: d.meal, style: d.style, party: Math.min(d.party, MAX_PARTY), cuisines: d.cuisines.filter((c) => c !== 'Surprise me').slice(0, 4), named: d.named.trim().slice(0, 80) }
}

// A complete "find me a movie" request, or null. Sent to the server so the movies are real (in theaters, or to watch at home).
export interface MovieRequest { count: number; where: 'theater' | 'home'; genres: string[] }
export function movieRequest(s: Selections): MovieRequest | null {
  const m = s.social?.movie
  if (!s.social?.kinds.includes(MOVIE_TYPE) || !m?.count || !m.where) return null
  return { count: Math.min(m.count, s.social.count ?? m.count, 3), where: m.where, genres: m.genres.filter((g) => g !== 'Surprise me').slice(0, 3) }
}

// The picks as plain sentences. This text is what the question agent and the planner read.
export function describeSelections(s: Selections): string {
  const out: string[] = []
  const sit = s.situation
  if (sit && (sit.busy || sit.goals.length)) {
    out.push(`About me: ${[sit.busy ? `this week is ${sit.busy.toLowerCase()}` : '', sit.goals.length ? `what I most want from my routine: ${list(sit.goals.map((g) => g.toLowerCase()))}` : ''].filter(Boolean).join('; ')}.`)
  }
  if (s.workouts?.count) {
    const w = s.workouts
    const types = withRefine(w.types.filter((t) => t !== CLASS_TYPE), w.refine)
    out.push(`Workouts: ${plural(w.count!, 'workout', 'workouts')} a week${types.length ? `; types: ${list(types)}` : ''}${w.length ? `; about ${w.length} each` : ''}${w.where.length ? `; where: ${list(w.where)}` : ''}.`)
    const k = classRequest(s)
    if (k) out.push(`Of the workouts, ${plural(k.count, 'should be a real fitness class', 'should be real fitness classes')} ${k.mode === 'studio' ? `at ${k.studio}` : 'at a studio that is new to me'}${k.types.length ? `; class types: ${list(k.types)}` : ''}.`)
  }
  if (s.cooking?.meals) {
    const c = s.cooking
    out.push(`Cooking at home: ${plural(c.meals!, 'meal', 'meals')}${c.which.length ? ` (${list(c.which)})` : ''}${c.cuisines.length ? `; cuisines: ${list(c.cuisines)}` : ''}${c.time ? `; ${c.time} each` : ''}.`)
    const ing = ingredientList(s)
    if (ing.length) out.push(`Ingredients I want to use in my recipes: ${list(ing)}.`)
    if (c.groceries) out.push('I want a scheduled grocery shopping trip before I start cooking.')
  }
  for (const [key, label, noun] of [['social', 'Time with friends or family', 'get-together'], ['errands', 'Errands and chores', 'errand block'], ['rest', 'Rest and downtime', 'quiet block'], ['wellness', 'Wellness habits', 'habit']] as const) {
    const v = s[key]
    if (v?.count) out.push(`${label}: ${plural(v.count, noun, noun + 's')} a week${v.kinds.length ? `; kinds: ${list(withRefine(v.kinds.filter((x) => x !== DINNER_TYPE), v.refine))}` : ''}.`)
  }
  const mr = movieRequest(s)
  if (mr) out.push(`Of the get-togethers, ${plural(mr.count, 'should be a movie night', 'should be movie nights')} ${mr.where === 'theater' ? 'at a movie theater' : 'at home'}${mr.genres.length ? `; genres: ${list(mr.genres)}` : ''}.`)
  const dr = dinnerRequest(s)
  if (dr) out.push(`Of the get-togethers, ${plural(dr.count, `should be a ${dr.meal} out`, `should be ${dr.meal}${dr.meal === 'brunch' ? 'es' : 's'} out`)} ${dr.style === 'reservation' ? '(somewhere that takes reservations)' : '(a walk-in place, no reservation)'} for ${plural(dr.party, 'person', 'people')}${dr.named ? ` at ${dr.named}` : ''}${dr.cuisines.length ? `; cuisines: ${list(dr.cuisines)}` : ''}.`)
  if (s.other.trim()) out.push(`Other things to schedule: ${s.other.trim()}`)
  if (s.extra.trim()) out.push(`Anything else: ${s.extra.trim()}`)
  return out.join('\n').slice(0, 2000)
}

const clip = (v: string, n: number) => (v.length > n ? v.slice(0, n - 1) + '…' : v)

// Exact goals from the picks, so the planner's counts come from what the user chose and not from guessing.
export function goalsFromSelections(s: Selections): Goal[] {
  const g: Goal[] = []
  if (s.workouts?.count) {
    const w = s.workouts
    const k = classRequest(s)
    const types = withRefine(w.types.filter((t) => t !== CLASS_TYPE), w.refine)
    const others = (w.count ?? 0) - (k?.count ?? 0)
    if (others > 0) g.push({ activity: clip(`Workouts${types.length ? ` (${list(types)})` : ''}`, 80), kind: 'workout', times_per_week: others, notes: clip([w.length, w.where.length ? list(w.where) : ''].filter(Boolean).join(', '), 200) })
    if (k) g.push({ activity: clip(`Fitness ${k.count === 1 ? 'class' : 'classes'}${k.mode === 'studio' ? ` at ${k.studio}` : ' at a new studio'}`, 80), kind: 'workout', times_per_week: k.count, notes: clip(k.types.join(', '), 200) })
  }
  if (s.cooking?.meals) {
    const c = s.cooking
    g.push({ activity: clip(`Cook ${c.which.length ? c.which.join(' / ').toLowerCase() : 'meals'} at home`, 80), kind: 'cooking', times_per_week: c.meals, notes: clip([c.cuisines.length ? list(c.cuisines) : '', c.time ?? '', ingredientList(s).length ? `use: ${list(ingredientList(s))}` : ''].filter(Boolean).join('; '), 200) })
    // a grocery trip the user asked for with their cooking (skipped when they already picked Groceries under errands)
    if (c.groceries && !s.errands?.kinds.includes('Groceries')) g.push({ activity: 'Grocery shopping for this week\'s cooking', kind: 'errand', times_per_week: 1, notes: 'before the first cooked meal' })
  }
  const simple: [keyof Selections, string, Goal['kind']][] = [['social', 'Time with friends or family', 'social'], ['errands', 'Errands and chores', 'errand'], ['rest', 'Rest and downtime', 'rest'], ['wellness', 'Wellness habits', 'wellness']]
  for (const [key, activity, kind] of simple) {
    const v = s[key] as Simple | undefined
    if (v?.count) g.push({ activity, kind, times_per_week: v.count, notes: clip(list(withRefine(v.kinds, v.refine)), 200) })
  }
  return g
}

export const hasSelections = (s: Selections) => !!(s.workouts?.count || s.cooking?.meals || s.social?.count || s.errands?.count || s.rest?.count || s.wellness?.count)
export const canContinue = (s: Selections) => hasSelections(s) || s.other.trim().length >= 3 || s.extra.trim().length >= 3
