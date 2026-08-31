import { useEffect, useState } from 'react'

const SUB_SCORE_LABELS = {
  velocity: 'Velocity',
  fan_ratio: 'Fan Ratio',
  cycle_match: 'Cycle Match',
}

const SUB_SCORE_TOOLTIPS = {
  velocity: 'How fast the money moved — higher means faster, more urgent',
  fan_ratio:
    "How lopsided the account's in/out flow is — higher means more one-directional (pure scatter or pure gather)",
  cycle_match: 'How closely this matches a closed loop where money returns to its source',
}

const PATTERN_LABELS = {
  cycle: 'Cycle',
  scatter_gather: 'Scatter / Gather',
  unclassified: 'Unclassified',
}

// Auto-generated one-line verdict from case data already on hand -- no
// backend call, no LLM. Varies by risk_tier and pattern_type (and the actual
// score) so it doesn't read identically across cases.
const VERDICT_TEMPLATES = {
  str_ready: {
    cycle: (score) =>
      `This closed-loop cycle scored ${score}/100 — strong enough evidence to file an STR without further review.`,
    scatter_gather: (score) =>
      `This scatter-gather structuring pattern scored ${score}/100 — clear enough to move straight to STR filing.`,
    unclassified: (score) =>
      `This case scored ${score}/100 on an unclassified pattern — still STR-ready despite not matching a named typology.`,
  },
  review: {
    cycle: (score) =>
      `This cycle pattern scored ${score}/100 — a plausible laundering loop, but borderline enough to warrant analyst review.`,
    scatter_gather: (score) =>
      `This scatter-gather pattern scored ${score}/100 — a lopsided flow worth a closer look before escalating.`,
    unclassified: (score) =>
      `This case scored ${score}/100 without matching a named pattern — ambiguous enough to need human judgment.`,
  },
  monitor: {
    cycle: (score) =>
      `This cycle pattern scored only ${score}/100 — a weak loop signal, likely not worth immediate action.`,
    scatter_gather: (score) =>
      `This scatter-gather pattern scored only ${score}/100 — a mild flow imbalance, low urgency for now.`,
    unclassified: (score) =>
      `This case scored only ${score}/100 on an unclassified pattern — low confidence, keep monitoring.`,
  },
}

function buildVerdict(riskTier, patternType, riskScore) {
  const tierTemplates = VERDICT_TEMPLATES[riskTier] ?? VERDICT_TEMPLATES.monitor
  const template = tierTemplates[patternType] ?? tierTemplates.unclassified
  return template(riskScore)
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

export default function EvidencePanel({ evidenceText, subScores, patternType, riskTier, riskScore }) {
  const [animated, setAnimated] = useState(false)

  useEffect(() => {
    setAnimated(false)
    const timer = setTimeout(() => setAnimated(true), 50)
    return () => clearTimeout(timer)
  }, [subScores])

  return (
    <div className="evidence-panel">
      <p className="evidence-verdict">{buildVerdict(riskTier, patternType, riskScore)}</p>

      <span className={`pattern-tag pattern-tag--${patternType}`}>
        <NetworkIcon />
        {PATTERN_LABELS[patternType] ?? patternType}
      </span>

      <p className="evidence-text">{evidenceText}</p>

      <div className="sub-scores">
        {Object.entries(SUB_SCORE_LABELS).map(([key, label]) => (
          <div className="sub-score" key={key}>
            <div className="sub-score-header">
              <span className="sub-score-label" data-tooltip={SUB_SCORE_TOOLTIPS[key]} tabIndex={0}>
                {label}
              </span>
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
