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
