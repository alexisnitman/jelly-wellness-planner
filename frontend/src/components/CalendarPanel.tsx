import { useEffect, useState } from 'react'
import type { CalendarResult, Plan, Profile } from '../types'
import CalendarViz from './CalendarViz'
import WeekPicker, { addDays, shortDate } from './WeekPicker'

interface Props {
  profile: Profile
  rangeStart: string // first day of the first week that can be shown
  weeks: number
  week: number // which week is showing
  onWeek: (i: number) => void
  calendar: CalendarResult | null
  plan: Plan | null
  approved: Set<string>
  selectedId: string | null
  onSelect: (id: string | null) => void
  planning: boolean
}

// Pixels per hour: tall on a big screen so the week fills the space, compact on a phone.
function useHourPx(hours: number): number {
  const calc = () => (window.matchMedia('(min-width: 960px)').matches ? Math.max(30, Math.min(52, (window.innerHeight - 330) / hours)) : 34)
  const [px, setPx] = useState(calc)
  useEffect(() => {
    const on = () => setPx(calc())
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  })
  return px
}

// The anchor of the screen: the user's week, always visible. Busy time from the calendar, then the proposed plan on top.
export default function CalendarPanel({ profile, rangeStart, weeks, week, onWeek, calendar, plan, approved, selectedId, onSelect, planning }: Props) {
  const hours = (Number(profile.wake_end.slice(0, 2)) * 60 + Number(profile.wake_end.slice(3)) - Number(profile.wake_start.slice(0, 2)) * 60 - Number(profile.wake_start.slice(3))) / 60
  const hourPx = useHourPx(hours)
  const weekStart = addDays(rangeStart, week * 7)
  const days = new Set(Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)))
  const dayKey = (iso: string) => new Intl.DateTimeFormat('en-CA', { timeZone: profile.timezone }).format(new Date(iso))
  const freeHours = calendar ? calendar.free.filter((f) => days.has(dayKey(f.start))).reduce((a, f) => a + f.minutes, 0) / 60 : null
  const planWeekIndex = plan ? Math.round((new Date(`${plan.week_start}T12:00:00Z`).getTime() - new Date(`${rangeStart}T12:00:00Z`).getTime()) / (7 * 86400000)) : null
  const planHere = !!plan && plan.week_start === weekStart

  return (
    <section className="stagecard" aria-label="Your week">
      <div className="stagehead">
        <h2>Your week</h2>
        <p className="small muted">
          {calendar ? `${Math.round(freeHours ?? 0)} free hours between ${profile.wake_start} and ${profile.wake_end}` : 'Your calendar and plan will appear here'}
        </p>
      </div>
      <WeekPicker rangeStart={rangeStart} weeks={weeks} index={week} onChange={onWeek} />
      {plan && !planHere && planWeekIndex !== null && planWeekIndex >= 0 && planWeekIndex < weeks && (
        <p className="note">Your plan is for the week of {shortDate(plan.week_start)}. <button type="button" className="link" onClick={() => onWeek(planWeekIndex)}>Show it</button></p>
      )}
      {planning && <p className="small muted" role="status">Planning around your calendar…</p>}
      <CalendarViz
        weekStart={weekStart}
        wakeStart={profile.wake_start}
        wakeEnd={profile.wake_end}
        timezone={profile.timezone}
        busy={calendar ? calendar.busy : null}
        items={planHere ? plan!.items : []}
        approved={approved}
        hourPx={hourPx}
        selectedId={selectedId}
        onSelect={onSelect}
        emptyHint={!calendar && !planHere ? <p><strong>Add your calendar</strong> in step 3 to see your busy time here, or skip it and I'll plan around your waking hours.</p> : undefined}
      />
    </section>
  )
}
