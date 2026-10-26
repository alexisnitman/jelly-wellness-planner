import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { forgotPassword } from '../api'
import { Guide } from './Mascot'

export default function AuthForm() {
  const { login, register } = useAuth()
  const [mode, setMode] = useState<'login' | 'register' | 'forgot'>('login')
  const [f, setF] = useState({ first_name: '', email: '', username: '', password: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [sent, setSent] = useState('')
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value })

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      if (mode === 'forgot') setSent((await forgotPassword(f.email)).message)
      else if (mode === 'login') await login(f.username, f.password)
      else await register(f)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
    <Guide mood="wave">{mode === 'login' ? 'Welcome back. Let\'s plan a good week.' : mode === 'forgot' ? 'No worries, it happens. Tell me your email and I\'ll make you a reset link.' : 'Hi, I\'m Jelly. Make an account and I\'ll help you build a routine you can keep.'}</Guide>
    <section className="card">
      <h2>{mode === 'login' ? 'Log in' : mode === 'forgot' ? 'Reset your password' : 'Create account'}</h2>
      <form onSubmit={submit}>
        {mode === 'forgot' && (
          <>
            <label className="field">Email<input type="email" value={f.email} onChange={set('email')} autoComplete="email" maxLength={254} required /></label>
            {sent && <p className="note" role="status">{sent}</p>}
            {error && <p className="error" role="alert">{error}</p>}
            <button className="primary" type="submit" disabled={busy}>{busy ? 'Please wait…' : sent ? 'Send another link' : 'Create a reset link'}</button>
          </>
        )}
        {mode === 'register' && (
          <>
            <label className="field">First name<input value={f.first_name} onChange={set('first_name')} autoComplete="given-name" maxLength={60} required /></label>
            <label className="field">Email<input type="email" value={f.email} onChange={set('email')} autoComplete="email" maxLength={254} required /></label>
          </>
        )}
        {mode !== 'forgot' && (
          <>
            <label className="field">Username<input value={f.username} onChange={set('username')} autoComplete="username" maxLength={60} required /></label>
            <label className="field">
              Password
              <input type="password" value={f.password} onChange={set('password')} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength={mode === 'register' ? 10 : undefined} maxLength={128} required />
            </label>
            {mode === 'register' && <p className="small muted">At least 10 characters. A few random words works well.</p>}
            {mode === 'login' && <p className="small"><button type="button" className="link" onClick={() => { setMode('forgot'); setError(''); setSent('') }}>Forgot your password?</button></p>}
            {error && <p className="error" role="alert">{error}</p>}
            <button className="primary" type="submit" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Create account'}</button>
          </>
        )}
      </form>
      <p className="center">
        {mode === 'login' ? 'New here? ' : mode === 'forgot' ? 'Remembered it? ' : 'Already have an account? '}
        <button type="button" className="link" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); setSent('') }}>
          {mode === 'login' ? 'Create an account' : 'Log in'}
        </button>
      </p>
    </section>
    </>
  )
}
