export interface User {
  first_name: string
  username: string
}

export interface RegisterInput {
  first_name: string
  email: string
  username: string
  password: string
}

export interface Profile {
  wake_start: string
  wake_end: string
  week_start: number // 0 = Monday
  timezone: string
  city: string
  diet: string
  limits_note: string
  complete: boolean
  role: 'student' | 'professional' | 'other' | ''
  role_details: Record<string, string>
}

export interface RoleQuestion {
  key: string
  question: string
  choices: string[] // empty = a short free-text answer
}

export interface Span {
  start: string
  end: string
}
export interface FreeSpan extends Span {
  minutes: number
}

export interface LinkStatus {
  saved: boolean
  host: string
}

export interface CalendarResult {
  week_start: string // first day of the first week read
  week_end: string // last day of the last week read
  weeks: number
  timezone: string
  events_read: number
  busy: Span[]
  free: FreeSpan[]
  link: LinkStatus
}

export interface CalendarRequest {
  source: 'file' | 'link' | 'saved' | 'sample'
  ics_text?: string
  url?: string
  remember?: boolean
  weeks?: number
}

// ----- steps 1 and 2 -----
export interface Goal {
  activity: string
  kind: 'workout' | 'cooking' | 'social' | 'errand' | 'rest' | 'wellness' | 'other'
  times_per_week: number | null
  notes: string
}

export interface Question {
  id: string
  text: string
  kind: 'single' | 'multi' | 'text'
  options: string[]
  why: string
}

export interface Interview {
  goals: Goal[]
  questions: Question[]
}

// Answers are held in page memory only (not saved anywhere) until the plan is exported in a later phase.
export type Answers = Record<string, string[]>

// ----- step 4: the proposed plan -----
export interface Recipe {
  servings: number
  prep_minutes: number
  cook_minutes: number
  ingredients: string[]
  steps: string[]
}
export interface Workout {
  intensity: 'easy' | 'moderate' | 'hard'
  equipment: string[]
  warmup: string[]
  main: string[]
  cooldown: string[]
  adaptation_note: string
}
export interface PlanItem {
  id: string
  title: string
  kind: Goal['kind']
  goal: string
  day: string // YYYY-MM-DD, local
  start: string // HH:MM, local
  end: string
  start_iso: string
  end_iso: string
  why: string
  notes: string
  recipe: Recipe | null
  workout: Workout | null
  evidence_ids: string[]
  goal_link: string
  benefit: Benefit | null
  class_id: string | null
  class_info: { studio: string; title: string; url: string; address: string; length_assumed: boolean } | null
  venue_id: string | null
  movie_id: string | null
  movie_info: { title: string; year: number | null; genres: string[]; blurb: string; where: string; where_kind: 'theater' | 'home'; url: string; watch_url: string; availability: 'read' | 'unconfirmed' } | null
  venue_info: { name: string; cuisine: string; address: string; price: string; url: string; reservation_url: string; style: 'reservation' | 'walk_in'; meal: 'breakfast' | 'brunch' | 'lunch' | 'dinner'; availability: 'read' | 'unconfirmed' } | null
}
export interface Evidence {
  topic: string
  quote: string // an exact quote from the cited page
  source: string
  url: string
  checked: string
}
export interface Benefit {
  lead: string
  goal_link: string
  evidence: Evidence[]
}
export interface ClassSearch {
  requested: number
  found: number
  studios_checked: { name: string; url: string; readable: boolean }[]
  unreadable: { name: string; url: string; reason: string }[]
  note: string
  checked: string
}
export interface Restaurant {
  name: string
  cuisine: string
  address: string
  price: string
  url: string
  reservation_url: string
  has_times: boolean
  walk_in_confirmed: boolean
}
export interface DinnerSearch {
  meal: 'breakfast' | 'brunch' | 'lunch' | 'dinner'
  style: 'reservation' | 'walk_in'
  restaurants: Restaurant[]
  requested: number
  found: number
  with_times: number
  unreadable: { name: string; url: string; reason: string }[]
  note: string
  checked: string
}
export interface MovieSearch {
  where: 'theater' | 'home'
  movies: { title: string; year: number | null; genres: string[]; blurb: string; where: string; url: string; watch_url: string; has_times: boolean }[]
  requested: number
  found: number
  unreadable: { name: string; url: string; reason: string }[]
  note: string
  checked: string
}
export interface Plan {
  week_start: string
  items: PlanItem[]
  unplaced: { title: string; reason: string }[]
  summary: string
  used_calendar: boolean
  class_search: ClassSearch | null
  dinner_search: DinnerSearch | null
  movie_search: MovieSearch | null
  disclaimer: string
}
export interface ProposeRequest {
  description: string
  goals: Goal[]
  answers: { question: string; answer: string }[]
  week_start: string
  free: Span[] | null // null = no calendar: assume free in waking hours
  // a revision: what the user wants changed in the plan they have seen
  priorities?: string[]
  class_request?: { mode: 'studio' | 'new'; studio: string; types: string[]; count: number }
  movie_request?: { count: number; where: 'theater' | 'home'; genres: string[] }
  ingredients?: string[] // ingredients the user wants in their recipes
  dinner_request?: { count: number; meal: 'breakfast' | 'brunch' | 'lunch' | 'dinner'; style: 'reservation' | 'walk_in'; party: number; cuisines: string[]; named: string }
  feedback?: string
  current?: Pick<PlanItem, 'title' | 'kind' | 'day' | 'start' | 'end'>[]
  removed?: string[]
}

export interface ExportRequest {
  week_start: string
  free: Span[] | null
  priorities?: string[]
  items: Pick<PlanItem, 'title' | 'kind' | 'day' | 'start' | 'end' | 'why' | 'notes' | 'recipe' | 'workout' | 'class_id' | 'venue_id' | 'movie_id' | 'evidence_ids' | 'goal_link'>[]
}

