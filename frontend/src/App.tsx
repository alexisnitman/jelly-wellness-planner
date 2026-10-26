import { useEffect, useState } from 'react'
import { fetchHealth, fetchProfile, type Health } from './api'
import { useAuth } from './lib/auth'
import { Logo } from './components/Mascot'
import AuthForm from './components/AuthForm'
import ResetForm from './components/ResetForm'
import ProfileForm, { DEFAULT_PROFILE } from './components/ProfileForm'
import PlanWizard from './components/PlanWizard'
import type { Profile } from './types'

export default function App() {
  const { user, loading, logout } = useAuth()
  const [profile, setProfile] = useState<Profile>(DEFAULT_PROFILE)
  const [profileReady, setProfileReady] = useState(false)
  const [tab, setTab] = useState<'plan' | 'profile'>('plan')
  const [health, setHealth] = useState<Health | null>(null)
  const [backendDown, setBackendDown] = useState(false)
  // a password reset link opens the app with ?reset=<token>; keep the token in memory only and clean the address straight away
  const [resetToken, setResetToken] = useState<string | null>(() => new URLSearchParams(window.location.search).get('reset'))
  useEffect(() => {
    if (new URLSearchParams(window.location.search).has('reset')) window.history.replaceState(null, '', window.location.pathname)
  }, [])

  useEffect(() => {
    fetchHealth().then(setHealth).catch(() => setBackendDown(true))
  }, [])

  const username = user?.username
  useEffect(() => {
    setProfileReady(false)
    if (!username) {
      setProfile(DEFAULT_PROFILE) // nothing from a previous user stays in memory
      return
    }
    fetchProfile()
      .then((p) => {
        setProfile(p)
        setProfileReady(true)
        if (!p.complete) setTab('profile') // first sign-in: the profile (waking hours) comes first
      })
      .catch(() => setProfileReady(true))
  }, [username])

  return (
    <div className={`app${user && profileReady && tab === 'plan' ? ' wide' : ''}`}>
      <header>
        <div className="top">
          <h1><Logo /> Jelly Wellness Planner</h1>
          {user && <button onClick={logout}>Log out</button>}
        </div>
        <p className="slogan">Go with the flow: healthy habits, made easy.</p>
        <p className="tagline">Build a routine you can keep. Tell me what you want from your week and I'll fit healthy habits around your real calendar.</p>
      </header>

      <main>
        {resetToken ? (
          <ResetForm token={resetToken} onDone={() => setResetToken(null)} />
        ) : loading ? (
          <p className="muted">Loading…</p>
        ) : !user ? (
          <AuthForm />
        ) : !profileReady ? (
          <p className="muted">Loading your profile…</p>
        ) : (
          <>
            <nav className="tabs">
              <button className={tab === 'plan' ? 'on' : ''} onClick={() => setTab('plan')} disabled={!profile.complete}>Plan</button>
              <button className={tab === 'profile' ? 'on' : ''} onClick={() => setTab('profile')}>Profile</button>
            </nav>
            {tab === 'profile' && (
              <>
                {!profile.complete && <p className="note">Welcome, {user.first_name}. Start by setting your waking hours.</p>}
                <ProfileForm profile={profile} onSaved={(p) => { setProfile(p); setTab('plan') }} />
              </>
            )}
            {/* stays mounted while you visit Profile so your in-progress answers aren't lost */}
            <div hidden={tab !== 'plan'}>{profile.complete && <PlanWizard key={user.username} profile={profile} />}</div>
          </>
        )}
      </main>

      <footer className="status" role="status">
        {backendDown ? (
          <span className="error">Can't reach the backend. Start it with: cd backend && ../.venv/bin/uvicorn main:app --reload --port 8000</span>
        ) : health ? (
          <span>Backend connected · model {health.model} · AI {health.ai_enabled ? 'on' : 'off'} · spent today ${health.spent_today_usd.toFixed(2)} of ${health.daily_cap_usd.toFixed(2)}</span>
        ) : (
          <span className="muted">Checking backend…</span>
        )}
      </footer>
    </div>
  )
}
