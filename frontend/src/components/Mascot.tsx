import { useId } from 'react'

// "Jelly", the little jellyfish guide. Decorative (the speech bubble carries the words), gently animated with CSS and
// still when the user prefers reduced motion.
export type Mood = 'happy' | 'wave' | 'think' | 'party'

export default function Mascot({ mood = 'happy' }: { mood?: Mood }) {
  const id = useId().replace(/:/g, '')
  return (
    <svg className={`mascot ${mood}`} viewBox="0 0 80 96" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={`bell${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#c9efe3" />
          <stop offset="1" stopColor="#a8d9ef" />
        </linearGradient>
        <linearGradient id={`arm${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#8fd3c8" />
          <stop offset="1" stopColor="#9fc9ee" stopOpacity="0.55" />
        </linearGradient>
      </defs>
      <g className="float">
        <g className="tentacles" fill="none" stroke={`url(#arm${id})`} strokeWidth="3.6" strokeLinecap="round">
          <path className="tentacle" d="M24 46 C20 58 28 66 22 78 C20 83 22 86 24 88" />
          <path className="tentacle" d="M34 47 C31 60 39 68 34 82 C33 86 34 89 36 91" />
          <path className="tentacle" d="M46 47 C49 60 41 68 46 82 C47 86 46 89 44 91" />
          <path className={mood === 'wave' ? 'tentacle t-wave' : 'tentacle'} d="M56 46 C60 58 52 66 58 78 C60 83 58 86 56 88" />
        </g>
        <path d="M10 46 C10 22 24 6 40 6 C56 6 70 22 70 46 C64 42 58 48 52 46 C46 44 42 49 36 47 C30 45 24 49 18 46 C14 45 12 46 10 46Z" fill={`url(#bell${id})`} stroke="#6fb8a8" strokeWidth="2.2" strokeLinejoin="round" />
        <ellipse cx="29" cy="19" rx="9" ry="4.5" fill="#ffffff" opacity="0.5" transform="rotate(-24 29 19)" />
        <circle cx="52" cy="17" r="2" fill="#ffffff" opacity="0.6" />
        <circle cx="58" cy="26" r="1.5" fill="#ffffff" opacity="0.5" />
        <ellipse className="eye" cx="31" cy="32" rx="2.8" ry="3.4" fill="#27524a" />
        <ellipse className="eye" cx="49" cy="32" rx="2.8" ry="3.4" fill="#27524a" />
        <circle cx="25" cy="38" r="3.2" fill="#f5b5c0" opacity="0.7" />
        <circle cx="55" cy="38" r="3.2" fill="#f5b5c0" opacity="0.7" />
        {mood === 'think' ? (
          <circle cx="40" cy="39" r="2.2" fill="#27524a" />
        ) : mood === 'party' ? (
          <path d="M34 37 Q40 45 46 37 Z" fill="#27524a" />
        ) : (
          <path d="M35 38 Q40 43 45 38" fill="none" stroke="#27524a" strokeWidth="2.2" strokeLinecap="round" />
        )}
        {mood === 'party' && (
          <>
            <path d="M32 11 L40 -6 L48 11Z" fill="#f7d7c4" stroke="#27524a" strokeWidth="2" strokeLinejoin="round" />
            <circle cx="40" cy="-7" r="3" fill="#faf0c4" stroke="#27524a" strokeWidth="1.6" />
          </>
        )}
      </g>
    </svg>
  )
}

// Jelly plus a speech bubble.
export function Guide({ mood = 'happy', children }: { mood?: Mood; children: React.ReactNode }) {
  return (
    <div className="guide">
      <Mascot mood={mood} />
      <p className="bubble" role="status">{children}</p>
    </div>
  )
}

// A tiny jellyfish for the header.
export function Logo() {
  return (
    <svg width="26" height="30" viewBox="0 0 80 96" aria-hidden="true" focusable="false">
      <path d="M12 46 C12 22 26 8 40 8 C54 8 68 22 68 46 Z" fill="#a8d9ef" stroke="#4f9c8c" strokeWidth="5" strokeLinejoin="round" />
      <g fill="none" stroke="#4f9c8c" strokeWidth="5.5" strokeLinecap="round">
        <path d="M26 48 C23 62 31 70 26 86" /><path d="M40 48 C38 62 44 72 40 90" /><path d="M54 48 C57 62 49 70 54 86" />
      </g>
    </svg>
  )
}
