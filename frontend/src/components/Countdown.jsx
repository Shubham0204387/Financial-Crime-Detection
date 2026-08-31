import { useEffect, useState } from 'react'

function getRemaining(deadline) {
  const diffMs = new Date(deadline).getTime() - Date.now()
  const expired = diffMs <= 0
  const totalHours = Math.floor(Math.max(diffMs, 0) / (1000 * 60 * 60))
  const days = Math.floor(totalHours / 24)
  const hours = totalHours % 24

  let urgency = 'calm'
  if (expired) urgency = 'expired'
  else if (totalHours < 24) urgency = 'critical'
  else if (totalHours < 72) urgency = 'warning'

  return { days, hours, expired, urgency }
}

function ClockIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3.5 2" />
    </svg>
  )
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
    <div className={`countdown countdown--${remaining.urgency}`}>
      <span className="countdown-label">
        <ClockIcon />
        STR filing deadline
      </span>
      <span className="countdown-value">
        {remaining.expired ? 'Deadline passed' : `${remaining.days}d ${remaining.hours}h remaining`}
      </span>
    </div>
  )
}
