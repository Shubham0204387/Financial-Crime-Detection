import { useEffect, useState } from 'react'

const SIZE = 88
const STROKE = 8
const RADIUS = (SIZE - STROKE) / 2
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

const TIER_COLOR_VAR = {
  str_ready: 'var(--tier-str-ready-text)',
  review: 'var(--tier-review-text)',
  monitor: 'var(--tier-monitor-text)',
}

export default function RiskGauge({ score, tier }) {
  const [animated, setAnimated] = useState(false)

  useEffect(() => {
    setAnimated(false)
    const timer = setTimeout(() => setAnimated(true), 50)
    return () => clearTimeout(timer)
  }, [score])

  const clamped = Math.max(0, Math.min(100, score))
  const offset = CIRCUMFERENCE * (1 - (animated ? clamped : 0) / 100)
  const color = TIER_COLOR_VAR[tier] ?? 'var(--text-secondary)'

  return (
    <div className="risk-gauge" style={{ width: SIZE, height: SIZE }}>
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`}>
        <circle cx={SIZE / 2} cy={SIZE / 2} r={RADIUS} fill="none" stroke="var(--border)" strokeWidth={STROKE} />
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          fill="none"
          stroke={color}
          strokeWidth={STROKE}
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
          className="risk-gauge-arc"
        />
      </svg>
      <span className="risk-gauge-value">{clamped}</span>
    </div>
  )
}
