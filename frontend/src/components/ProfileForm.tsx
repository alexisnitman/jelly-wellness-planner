import { useEffect, useMemo, useState } from 'react'
import type { Profile, RoleQuestion } from '../types'
import { fetchRoleQuestions, saveProfile } from '../api'
import { Guide } from './Mascot'

const ROLES: { id: Profile['role']; label: string }[] = [
  { id: 'student', label: 'A student' },
  { id: 'professional', label: 'A working professional' },
  { id: 'other', label: 'Something else' },
]

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const browserZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'

export const DEFAULT_PROFILE: Profile = { wake_start: '07:00', wake_end: '22:00', week_start: 0, timezone: 'UTC', city: '', diet: '', limits_note: '', complete: false, role: '', role_details: {} }

// The profile asks for waking hours first: the planner only ever schedules inside them.
export default function ProfileForm({ profile, onSaved }: { profile: Profile; onSaved: (p: Profile) => void }) {
  // a brand-new profile starts with the browser's time zone instead of UTC
  const [p, setP] = useState<Profile>(profile.complete ? profile : { ...profile, timezone: browserZone() })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [questions, setQuestions] = useState<Record<string, RoleQuestion[]>>({})
  useEffect(() => {
    fetchRoleQuestions().then(setQuestions).catch(() => undefined)
  }, [])
  const zones = useMemo(() => {
    try {
      return (Intl as unknown as { supportedValuesOf: (k: string) => string[] }).supportedValuesOf('timeZone')
    } catch {
      return [browserZone()]
    }
  }, [])
  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => {
    setP({ ...p, [k]: v })
    setSaved(false)
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const out = await saveProfile(p)
      setSaved(true)
      onSaved(out)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
    <Guide mood="happy">A little about you helps me plan days that really fit. Everything here stays private to your account.</Guide>
    <section className="card">
      <h2>Your profile</h2>
      <p className="muted small">Your waking hours tell the planner when it may schedule things. Saved to your account only.</p>
      <form onSubmit={submit}>
        <div className="row2">
          <label className="field">I'm usually up from<input type="time" value={p.wake_start} onChange={(e) => set('wake_start', e.target.value)} required /></label>
          <label className="field">until<input type="time" value={p.wake_end} onChange={(e) => set('wake_end', e.target.value)} required /></label>
        </div>
        <fieldset className="role">
          <legend>I'm mostly…</legend>
          <div className="chips" role="group" aria-label="Who you are">
            {ROLES.map((r) => (
              <button key={r.id} type="button" className={p.role === r.id ? 'chip on' : 'chip'} aria-pressed={p.role === r.id} onClick={() => { setP({ ...p, role: p.role === r.id ? '' : r.id, role_details: {} }); setSaved(false) }}>{r.label}</button>
            ))}
          </div>
          <p className="small muted">This shapes the questions I ask and the routine I suggest. You can skip it.</p>
          {p.role && (questions[p.role] ?? []).map((q) => (
            <div key={q.key}>
              <p className="q-label">{q.question}</p>
              {q.choices.length ? (
                <div className="chips" role="group" aria-label={q.question}>
                  {q.choices.map((c) => (
                    <button key={c} type="button" className={p.role_details[q.key] === c ? 'chip on' : 'chip'} aria-pressed={p.role_details[q.key] === c} onClick={() => {
                      const next = { ...p.role_details }
                      if (next[q.key] === c) delete next[q.key]
                      else next[q.key] = c
                      setP({ ...p, role_details: next }); setSaved(false)
                    }}>{c}</button>
                  ))}
                </div>
              ) : (
                <textarea rows={2} maxLength={200} value={p.role_details[q.key] ?? ''} aria-label={q.question} placeholder="e.g. Mostly at home with the kids, a few evening commitments" onChange={(e) => { setP({ ...p, role_details: { ...p.role_details, [q.key]: e.target.value } }); setSaved(false) }} />
              )}
            </div>
          ))}
        </fieldset>
        <label className="field">
          My week starts on
          <select value={p.week_start} onChange={(e) => set('week_start', Number(e.target.value))}>
            {DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
          </select>
        </label>
        <label className="field">
          Time zone
          <input list="zones" value={p.timezone} onChange={(e) => set('timezone', e.target.value)} maxLength={64} required />
          <datalist id="zones">{zones.map((z) => <option key={z} value={z} />)}</datalist>
        </label>
        <label className="field">City or neighborhood (for local ideas)<input value={p.city} onChange={(e) => set('city', e.target.value)} maxLength={80} placeholder="e.g. Austin, TX" /></label>
        <label className="field">Diet and allergies<textarea value={p.diet} onChange={(e) => set('diet', e.target.value)} maxLength={500} rows={2} placeholder="e.g. vegetarian, peanut allergy" /></label>
        <label className="field">Injuries or limits for workouts<textarea value={p.limits_note} onChange={(e) => set('limits_note', e.target.value)} maxLength={500} rows={2} placeholder="e.g. sore left knee" /></label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="primary" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save profile'}</button>
        {saved && <p className="small ok">Saved.</p>}
      </form>
    </section>
    </>
  )
}
