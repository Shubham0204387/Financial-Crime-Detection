import { useState } from 'react'

function formatDeadline(deadline) {
  if (!deadline) return 'Not set'
  return new Date(deadline).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

// Pure string interpolation from fields already present on the loaded case —
// no additional fetch or generation call, so it can't fail independently.
function buildNarrative({ pattern_type, evidence_text, str_deadline }) {
  return [
    'Suspicious Transaction Report — Draft',
    `Pattern matched: ${pattern_type}`,
    'Indicator: Amounts structured to avoid detection thresholds (PMLA suspicious indicator).',
    `Evidence: ${evidence_text}`,
    `Filing deadline: ${formatDeadline(str_deadline)}`,
    'Status: Pending Principal Officer review.',
  ].join('\n')
}

export default function DraftSTR({ detail }) {
  const [visible, setVisible] = useState(false)

  return (
    <div className="draft-str">
      <button type="button" className="draft-str-button" onClick={() => setVisible((v) => !v)}>
        {visible ? 'Hide Draft STR' : 'Draft STR'}
      </button>
      {visible && <pre className="draft-str-text">{buildNarrative(detail)}</pre>}
    </div>
  )
}
