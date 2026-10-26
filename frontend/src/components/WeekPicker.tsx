// Move between the weeks that were read. Dates are plain YYYY-MM-DD strings (no time zone maths needed).
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export const addDays = (iso: string, n: number): string => {
  const d = new Date(`${iso}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}
export const shortDate = (iso: string): string => {
  const [, m, d] = iso.split('-').map(Number)
  return `${MONTHS[m - 1]} ${d}`
}

interface Props {
  rangeStart: string // first day of the first week that was read
  weeks: number
  index: number // which week is showing (0 = first)
  onChange: (i: number) => void
}

export default function WeekPicker({ rangeStart, weeks, index, onChange }: Props) {
  const start = addDays(rangeStart, index * 7)
  const end = addDays(start, 6)
  return (
    <div className="weekpicker" role="group" aria-label="Choose a week">
      <button type="button" onClick={() => onChange(index - 1)} disabled={index <= 0} aria-label="Previous week">‹</button>
      <div className="weeklabel">
        <strong>{shortDate(start)} – {shortDate(end)}</strong>
        <span className="small muted">{index === 0 ? 'This week' : index === 1 ? 'Next week' : `Week ${index + 1} of ${weeks}`}</span>
      </div>
      <button type="button" onClick={() => onChange(index + 1)} disabled={index >= weeks - 1} aria-label="Next week">›</button>
      {index !== 0 && <button type="button" className="link" onClick={() => onChange(0)}>This week</button>}
    </div>
  )
}
