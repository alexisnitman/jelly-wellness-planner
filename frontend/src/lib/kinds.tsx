import type { Goal } from '../types'

type Kind = Goal['kind'] | 'workouts' | 'errands'

// Simple line icons (decorative; the label always says it in words too). 24x24, drawn with the current text color.
const PATHS: Record<Goal['kind'], React.ReactNode> = {
  workout: <path d="M6.5 6.5v11M17.5 6.5v11M3 9v6M21 9v6M6.5 12h11" />,
  cooking: <path d="M7 3v8M4 3v5a3 3 0 0 0 6 0V3M7 11v10M17 21V3c-2 1-4 4-4 8h4" />,
  social: (
    <>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" />
      <circle cx="17" cy="9" r="2.4" />
      <path d="M16.5 14.2c2.7.2 4.5 2.4 4.5 5.3" />
    </>
  ),
  errand: <path d="M5 8h14l-1 12H6L5 8zM9 8V6a3 3 0 0 1 6 0v2" />,
  rest: <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />,
  wellness: <path d="M5 19c0-8 5-14 15-14 0 10-6 15-14 15M5 19c3-4 6-7 10-9" />,
  other: <path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z" />,
}

export function KindIcon({ kind, size = 18 }: { kind: Kind; size?: number }) {
  const k: Goal['kind'] = kind === 'workouts' ? 'workout' : kind === 'errands' ? 'errand' : kind
  return (
    <svg className="kicon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {PATHS[k]}
    </svg>
  )
}
