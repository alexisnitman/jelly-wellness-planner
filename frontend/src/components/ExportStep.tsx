import { useState } from 'react'
import type { ExportRequest, Plan } from '../types'
import { exportPlan } from '../api'

interface Props {
  plan: Plan
  approved: Set<string>
  free: ExportRequest['free']
  priorities: string[]
  onBack: () => void
  onStartOver: () => void
  onDone: () => void
}

// Step 6: build the .ics file from the approved items and offer it as a download. The app never touches the calendar.
export default function ExportStep({ plan, approved, free, priorities, onBack, onStartOver, onDone }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState('')
  const items = plan.items.filter((i) => approved.has(i.id))

  const download = async () => {
    setBusy(true)
    setError('')
    try {
      const { blob, filename } = await exportPlan({
        week_start: plan.week_start,
        free,
        priorities,
        items: items.map(({ title, kind, day, start, end, why, notes, recipe, workout, class_id, venue_id, movie_id, evidence_ids, goal_link }) => ({ title, kind, day, start, end, why, notes, recipe, workout, class_id, venue_id, movie_id, evidence_ids, goal_link })),
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      setDone(filename)
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      {done && <Bubbles />}
      <h2>{done ? 'Your plan is ready' : 'Download your plan'}</h2>
      <p>{items.length} approved {items.length === 1 ? 'item' : 'items'} will be in the file, each with its recipe or workout in the event notes.</p>
      {error && <p className="error" role="alert">{error}</p>}
      <button className="primary" type="button" disabled={busy || items.length === 0} onClick={download}>
        {busy ? 'Building your file…' : done ? 'Download again' : 'Download .ics file'}
      </button>
      {done && (
        <div className="note">
          <p><strong>{done}</strong> was downloaded. Import it into your calendar:</p>
          <ul>
            <li><strong>Google Calendar:</strong> Settings, Import &amp; export, Import, choose the file.</li>
            <li><strong>Apple Calendar:</strong> File, Import, choose the file.</li>
            <li><strong>Outlook:</strong> File, Open &amp; Export, Import/Export, then "Import an iCalendar (.ics)".</li>
          </ul>
          <p className="small muted">Importing adds new events. It doesn't change or delete anything already on your calendar. To undo, delete the imported events.</p>
        </div>
      )}
      <button type="button" className="link" onClick={onBack}>Back to approvals</button>{' '}
      {done && <button type="button" className="link" onClick={onStartOver}>Plan another week</button>}
    </section>
  )
}

// A gentle stream of bubbles when the plan is downloaded (decorative; off for reduced motion).
function Bubbles() {
  return (
    <div className="bubbles-fx" aria-hidden="true">
      {Array.from({ length: 16 }, (_, i) => (
        <span key={i} style={{ ['--x' as string]: `${(i * 29 + 7) % 96}%`, ['--d' as string]: `${(i % 8) * 0.22}s`, ['--s' as string]: `${12 + ((i * 7) % 18)}px` }} />
      ))}
    </div>
  )
}
