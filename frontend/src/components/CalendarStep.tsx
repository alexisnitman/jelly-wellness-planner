import { useEffect, useState } from 'react'
import type { CalendarRequest, CalendarResult, LinkStatus } from '../types'
import { fetchLinkStatus, forgetLink, readCalendar } from '../api'

const MAX_FILE_BYTES = 2_500_000
const WEEKS_TO_READ = 6

interface Props {
  result: CalendarResult | null
  onResult: (r: CalendarResult | null) => void
}

// Step 3: read the calendar (read-only), then pick a week and see the free time inside the user's waking hours.
export default function CalendarStep({ result, onResult }: Props) {
  const [how, setHow] = useState<'link' | 'file'>('link')
  const [url, setUrl] = useState('')
  const [remember, setRemember] = useState(true)
  const [link, setLink] = useState<LinkStatus>({ saved: false, host: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchLinkStatus().then(setLink).catch(() => undefined)
  }, [])

  const run = async (req: CalendarRequest) => {
    setBusy(true)
    setError('')
    try {
      const r = await readCalendar({ ...req, weeks: WEEKS_TO_READ })
      onResult(r)
      setLink(r.link)
      if (req.source === 'link') setUrl('') // the pasted link is not kept in the page
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (file.size > MAX_FILE_BYTES) return setError('That file is too large. Export a shorter date range.')
    run({ source: 'file', ics_text: await file.text() })
  }

  return (
    <section className="card">
      <h2>Add your calendar</h2>
      <p className="muted small">Read-only. The app finds your busy times and never changes your calendar. Event titles and details are not kept or sent anywhere. It reads the next {WEEKS_TO_READ} weeks so you can pick any of them.</p>

      <div className="saved">
        <p><strong>No calendar handy?</strong> Try a made-up student week (classes, a team meeting, a study group).</p>
        <button className="primary" type="button" disabled={busy} onClick={() => run({ source: 'sample' })}>{busy ? 'Reading…' : 'Use a sample calendar'}</button>
      </div>

      {link.saved && (
        <div className="saved">
          <p>Saved link from <strong>{link.host}</strong></p>
          <button className="primary" type="button" disabled={busy} onClick={() => run({ source: 'saved' })}>{busy ? 'Reading…' : 'Read my calendar'}</button>
          <button type="button" className="link" onClick={async () => setLink(await forgetLink())}>Forget this link</button>
        </div>
      )}

      <div className="seg" role="tablist">
        <button type="button" className={how === 'link' ? 'on' : ''} onClick={() => setHow('link')}>Paste a link</button>
        <button type="button" className={how === 'file' ? 'on' : ''} onClick={() => setHow('file')}>Upload a file</button>
      </div>

      {how === 'link' ? (
        <form onSubmit={(e) => { e.preventDefault(); if (url.trim()) run({ source: 'link', url: url.trim(), remember }) }}>
          <label className="field">
            Private calendar link (iCal / .ics)
            <input type="password" autoComplete="off" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://… or webcal://…" maxLength={2000} />
          </label>
          <p className="small muted">
            Google Calendar: Settings, then your calendar, then "Secret address in iCal format". Apple and Outlook have a similar "share/publish" link.
            Anyone with this link can see that calendar, so treat it like a password.
          </p>
          <label className="check">
            <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
            Remember this link (stored encrypted; you can forget it any time)
          </label>
          <button className="primary" type="submit" disabled={busy || !url.trim()}>{busy ? 'Reading…' : 'Read my calendar'}</button>
        </form>
      ) : (
        <label className="field">
          Calendar file (.ics)
          <input type="file" accept=".ics,text/calendar" onChange={onFile} />
          <span className="small muted">The file is read once and not stored.</span>
        </label>
      )}

      {error && <p className="error" role="alert">{error}</p>}
      {result && (
        <p className="note">Read {result.events_read} calendar {result.events_read === 1 ? 'event' : 'events'} across the next {result.weeks} weeks. Your busy time is on the calendar. Use the arrows above it to look at any week.</p>
      )}
    </section>
  )
}
