import { useEffect, useState } from 'react'

function getRemaining(deadline) {
  const diffMs = new Date(deadline).getTime() - Date.now()
  const expired = diffMs <= 0
  const totalHours = Math.floor(Math.max(diffMs, 0) / (1000 * 60 * 60))
  return { days: Math.floor(totalHours / 24), hours: totalHours % 24, expired }
}

export default function Countdown({ deadline }) {
  const [remaining, setRemaining] = useState(() => getRemaining(deadline))

  useEffect(() => {
    setRemaining(getRemaining(deadline))
    const interval = setInterval(() => setRemaining(getRemaining(deadline)), 60000)
    return () => clearInterval(interval)
  }, [deadline])

  if (!deadline) return null

  return (
    <div className={`countdown${remaining.expired ? ' countdown--expired' : ''}`}>
      <span className="countdown-label">STR filing deadline</span>
      <span className="countdown-value">
        {remaining.expired ? 'Deadline passed' : `${remaining.days}d ${remaining.hours}h remaining`}
      </span>
    </div>
  )
}
