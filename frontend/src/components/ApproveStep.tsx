import type { Plan } from '../types'
import { addDays, shortDate } from './WeekPicker'

const time12 = (hhmm: string) => {
  const [h, m] = hhmm.split(':').map(Number)
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`
}
const dayLabel = (iso: string) => new Intl.DateTimeFormat('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' }).format(new Date(`${iso}T12:00:00Z`))

interface Props {
  plan: Plan
  approved: Set<string>
  onToggle: (id: string) => void
  onApprove: () => void
  onBack: () => void
}

// Step 5: the user decides exactly which items are approved. Only ticked items can be exported.
export default function ApproveStep({ plan, approved, onToggle, onApprove, onBack }: Props) {
  const items = [...plan.items].sort((a, b) => a.day.localeCompare(b.day) || a.start.localeCompare(b.start))
  return (
    <section className="card">
      <h2>Approve your plan</h2>
      <p className="small muted">
        Week of {shortDate(plan.week_start)} to {shortDate(addDays(plan.week_start, 6))}. Untick anything you don't want. It dims on the calendar, and only ticked items go into your file.
      </p>
      <ul className="approve">
        {items.map((it) => (
          <li key={it.id}>
            <label className="check">
              <input type="checkbox" checked={approved.has(it.id)} onChange={() => onToggle(it.id)} />
              <span>
                <strong>{it.title}</strong>
                <span className="small muted"> · {dayLabel(it.day)}, {time12(it.start)} – {time12(it.end)}</span>
              </span>
            </label>
          </li>
        ))}
      </ul>
      <p className="small">{approved.size} of {items.length} items approved.</p>
      <button className="primary" type="button" disabled={approved.size === 0} onClick={onApprove}>
        Approve {approved.size === 1 ? '1 item' : `${approved.size} items`}
      </button>
      <button type="button" className="link" onClick={onBack}>Back to the plan</button>
    </section>
  )
}
