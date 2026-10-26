import { useState } from 'react'
import { resetPassword } from '../api'
import { Guide } from './Mascot'

// Opened from the reset link (?reset=...). The token is held only in page memory; the page address is cleaned as soon as it loads.
export default function ResetForm({ token, onDone }: { token: string; onDone: () => void }) {
  const [pw, setPw] = useState('')
  const [pw2, setPw2] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (pw !== pw2) return setError('The two passwords don\'t match.')
    setBusy(true)
    setError('')
    try {
      await resetPassword(token, pw)
      setDone(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Guide mood={done ? 'party' : 'happy'}>{done ? 'All set. Your password is changed. Log in with the new one.' : 'Pick a new password and you\'ll be back in.'}</Guide>
      <section className="card">
        <h2>{done ? 'Password changed' : 'Choose a new password'}</h2>
        {done ? (
          <>
            <p className="small muted">You were signed out everywhere for safety.</p>
            <button className="primary" type="button" onClick={onDone}>Go to log in</button>
          </>
        ) : (
          <form onSubmit={submit}>
            <label className="field">New password<input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" minLength={10} maxLength={128} required /></label>
            <label className="field">Type it again<input type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} autoComplete="new-password" minLength={10} maxLength={128} required /></label>
            <p className="small muted">At least 10 characters. A few random words works well.</p>
            {error && <p className="error" role="alert">{error}</p>}
            <button className="primary" type="submit" disabled={busy}>{busy ? 'Please wait…' : 'Set new password'}</button>
            <button type="button" className="link" onClick={onDone}>Back to log in</button>
          </form>
        )}
      </section>
    </>
  )
}
