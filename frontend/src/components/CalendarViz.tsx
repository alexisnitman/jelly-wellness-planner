import { useMemo, useState, type ReactNode } from 'react'
import type { PlanItem, Span } from '../types'
import { KindIcon } from '../lib/kinds'
import { addDays } from './WeekPicker'

interface Props {
  weekStart: string // YYYY-MM-DD, first day shown
  wakeStart: string // HH:MM, top of the grid
  wakeEnd: string // HH:MM, bottom of the grid
  timezone: string
  busy: Span[] | null // busy time ranges from the calendar (null = no calendar was loaded)
  items: PlanItem[]
  approved: Set<string>
  hourPx?: number // height of one hour in the grid
  selectedId?: string | null // controlled selection (so the plan list and the calendar highlight together)
  onSelect?: (id: string | null) => void
  emptyHint?: ReactNode // shown over the grid when there is nothing to show yet
}

const mins = (hhmm: string) => Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3))
const time12 = (m: number) => {
  const h = Math.floor(m / 60), mm = m % 60
  return `${((h + 11) % 12) + 1}${mm ? ':' + String(mm).padStart(2, '0') : ''} ${h < 12 ? 'AM' : 'PM'}`
}
const hourLabel = (h: number) => `${((h + 11) % 12) + 1}${h < 12 ? 'a' : 'p'}`

// Local date (YYYY-MM-DD) and minutes-since-midnight of an instant, in the user's time zone.
function localParts(iso: string, tz: string): { date: string; min: number } {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(iso))
  const g = (t: string) => parts.find((p) => p.type === t)?.value ?? '0'
  return { date: `${g('year')}-${g('month')}-${g('day')}`, min: Number(g('hour')) * 60 + Number(g('minute')) }
}

// Split busy ranges into per-day [start, end) minute ranges.
function busyByDay(busy: Span[], tz: string): Map<string, [number, number][]> {
  const out = new Map<string, [number, number][]>()
  const push = (d: string, a: number, b: number) => b > a && out.set(d, [...(out.get(d) ?? []), [a, b]])
  for (const s of busy) {
    const a = localParts(s.start, tz), b = localParts(s.end, tz)
    if (a.date === b.date) push(a.date, a.min, b.min)
    else {
      push(a.date, a.min, 1440)
      for (let d = addDays(a.date, 1); d < b.date; d = addDays(d, 1)) push(d, 0, 1440)
      push(b.date, 0, b.min)
    }
  }
  return out
}

// The plan laid over the real calendar: busy time hatched, planned activities coloured by type. Lets the user see the
// whole week (and that nothing clashes) before approving.
export default function CalendarViz({ weekStart, wakeStart, wakeEnd, timezone, busy, items, approved, hourPx = 34, selectedId, onSelect, emptyHint }: Props) {
  const [own, setOwn] = useState<string | null>(null)
  const sel = selectedId !== undefined ? selectedId : own
  const setSel = (id: string | null) => (onSelect ? onSelect(id) : setOwn(id))
  const top = mins(wakeStart), bottom = mins(wakeEnd), span = bottom - top
  const height = (span / 60) * hourPx
  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i))
  const busyMap = useMemo(() => (busy ? busyByDay(busy, timezone) : new Map<string, [number, number][]>()), [busy, timezone])
  const today = localParts(new Date().toISOString(), timezone)
  const pos = (a: number, b: number) => ({ top: `${((Math.max(a, top) - top) / span) * 100}%`, height: `${((Math.min(b, bottom) - Math.max(a, top)) / span) * 100}%` })
  const dayFmt = new Intl.DateTimeFormat('en-US', { weekday: 'short', timeZone: 'UTC' })
  const dateFmt = new Intl.DateTimeFormat('en-US', { weekday: 'long', month: 'short', day: 'numeric', timeZone: 'UTC' })

  // any approved item that overlaps a busy range would be a clash (the server prevents it; this shows it)
  const clashes = items.filter((it) => approved.has(it.id) && (busyMap.get(it.day) ?? []).some(([a, b]) => mins(it.start) < b && mins(it.end) > a))
  const hours: number[] = []
  for (let h = Math.ceil(top / 60); h * 60 <= bottom; h++) hours.push(h)
  const labelEvery = span > 12 * 60 ? 2 : 1
  const picked = items.find((i) => i.id === sel)

  return (
    <div className="cal">
      <div className="cal-legend" aria-hidden="true">
        {busy && <span><i className="sw busy" />Busy (your calendar)</span>}
        <span><i className="sw plan" />Planned</span>
        <span><i className="sw off" />Not approved</span>
      </div>
      <div className="cal-wrap">
      <div className="cal-grid" role="group" aria-label="Your week on a calendar">
        <div className="cal-head" />
        {days.map((d) => (
          <div key={d} className={`cal-head${d === today.date ? ' today' : ''}`}>{dayFmt.format(new Date(`${d}T12:00:00Z`))}<b>{Number(d.slice(8))}</b></div>
        ))}
        <div className="cal-axis" style={{ height }} aria-hidden="true">
          {hours.filter((h) => (h - Math.ceil(top / 60)) % labelEvery === 0).map((h) => <span key={h} style={{ top: `${((h * 60 - top) / span) * 100}%` }}>{hourLabel(h)}</span>)}
        </div>
        {days.map((d) => (
          <div key={d} className="cal-col" style={{ height }}>
            {hours.map((h) => <div key={h} className="hr" style={{ top: `${((h * 60 - top) / span) * 100}%` }} />)}
            {(busyMap.get(d) ?? []).filter(([a, b]) => b > top && a < bottom).map(([a, b], i) => <div key={i} className="cal-block busy" style={pos(a, b)} aria-hidden="true" />)}
            {items.filter((it) => it.day === d).map((it) => {
              const on = approved.has(it.id)
              return (
                <button key={it.id} type="button" className={`cal-block item ${it.kind}${on ? '' : ' off'}${sel === it.id ? ' sel' : ''}`} style={pos(mins(it.start), mins(it.end))}
                  aria-label={`${it.title}, ${dateFmt.format(new Date(`${it.day}T12:00:00Z`))}, ${time12(mins(it.start))} to ${time12(mins(it.end))}${on ? '' : ', not approved'}`} aria-pressed={sel === it.id} onClick={() => setSel(sel === it.id ? null : it.id)}>
                  <KindIcon kind={it.kind} size={11} /> {it.title}
                </button>
              )
            })}
            {d === today.date && today.min > top && today.min < bottom && <div className="cal-now" style={{ top: `${((today.min - top) / span) * 100}%` }} aria-hidden="true" />}
          </div>
        ))}
      </div>
      {emptyHint && <div className="cal-empty">{emptyHint}</div>}
      </div>
      <div className="cal-detail" aria-live="polite">
        {picked
          ? <><strong>{picked.title}</strong> · {dateFmt.format(new Date(`${picked.day}T12:00:00Z`))}, {time12(mins(picked.start))} – {time12(mins(picked.end))} · {approved.has(picked.id) ? 'approved' : 'not approved'}</>
          : <span className="muted">Tap an activity to see its details.</span>}
      </div>
      <p className={`cal-check ${busy ? (clashes.length ? 'error' : 'ok') : 'muted'}`}>
        {!busy ? "Your calendar wasn't loaded, so this view shows the plan only." : clashes.length ? `Heads up: ${clashes.length} approved ${clashes.length === 1 ? 'item overlaps' : 'items overlap'} busy time.` : '✓ Checked against your calendar: nothing overlaps your busy time.'}
      </p>
    </div>
  )
}
