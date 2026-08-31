import { useEffect, useState } from 'react'

const SUB_SCORE_LABELS = {
  velocity: 'Velocity',
  fan_ratio: 'Fan Ratio',
  cycle_match: 'Cycle Match',
}

const PATTERN_LABELS = {
  cycle: 'Cycle',
  scatter_gather: 'Scatter / Gather',
  unclassified: 'Unclassified',
}

function NetworkIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="5" cy="6" r="2.5" />
      <circle cx="19" cy="6" r="2.5" />
      <circle cx="12" cy="18" r="2.5" />
      <path d="M7 7.5 10 16M17 7.5 14 16M7.5 6h9" />
    </svg>
  )
}

export default function EvidencePanel({ evidenceText, subScores, patternType }) {
  const [animated, setAnimated] = useState(false)

  useEffect(() => {
    setAnimated(false)
    const timer = setTimeout(() => setAnimated(true), 50)
    return () => clearTimeout(timer)
  }, [subScores])

  return (
    <div className="evidence-panel">
      <span className={`pattern-tag pattern-tag--${patternType}`}>
        <NetworkIcon />
        {PATTERN_LABELS[patternType] ?? patternType}
      </span>

      <p className="evidence-text">{evidenceText}</p>

      <div className="sub-scores">
        {Object.entries(SUB_SCORE_LABELS).map(([key, label]) => (
          <div className="sub-score" key={key}>
            <div className="sub-score-header">
              <span>{label}</span>
              <span>{subScores[key]}</span>
            </div>
            <div className="sub-score-bar">
              <div
                className="sub-score-bar-fill"
                style={{ width: animated ? `${subScores[key]}%` : '0%' }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
