import { useEffect, useState } from 'react'
import Mascot from './Mascot'

export const PLAN_SAYINGS = [
  'Jelly is gently untangling your week…',
  'Finding the calm pockets in your calendar…',
  'Tucking healthy habits into your free time…',
  'Making sure nothing bumps into your busy time…',
  'Checking every plan twice, one tentacle at a time…',
  'Going with the flow, almost there…',
]

export const QUESTION_SAYINGS = [
  'Jelly is reading your week and thinking up questions…',
  'Dipping a tentacle in to see what you really need…',
  'Picking only the questions that matter…',
  'Not too many questions, promise…',
  'Almost ready to ask you a few things…',
]

// Shown while the plan or the follow-up questions are being built: an animated Jelly swimming up through bubbles, with a rotating cute saying.
// The animation is CSS only and stops for people who prefer reduced motion (the sayings still change).
export default function Building({ sayings = PLAN_SAYINGS }: { sayings?: string[] }) {
  const [n, setN] = useState(0)
  useEffect(() => {
    const t = window.setInterval(() => setN((i) => (i + 1) % sayings.length), 4200)
    return () => window.clearInterval(t)
  }, [])
  return (
    <section className="card building" role="status" aria-live="polite">
      <div className="swim">
        <span className="bub b1" aria-hidden="true" /><span className="bub b2" aria-hidden="true" /><span className="bub b3" aria-hidden="true" /><span className="bub b4" aria-hidden="true" />
        <Mascot mood="think" />
      </div>
      <p className="saying" key={n}>{sayings[n % sayings.length]}</p>
    </section>
  )
}
