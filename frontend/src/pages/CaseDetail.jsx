import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchCaseDetail } from '../api/caseDetail'
import CaseGraph from '../components/CaseGraph'
import EvidencePanel from '../components/EvidencePanel'
import Countdown from '../components/Countdown'

const RISK_TIER_LABEL = {
  str_ready: 'STR Ready',
  review: 'Review',
  monitor: 'Monitor',
}

export default function CaseDetail() {
  const { caseId } = useParams()
  const [status, setStatus] = useState('loading')
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setStatus('loading')

    fetchCaseDetail(caseId)
      .then((data) => {
        if (cancelled) return
        setDetail(data)
        setStatus(data ? 'ready' : 'not-found')
      })
      .catch((err) => {
        if (cancelled) return
        setError(err.message)
        setStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [caseId])

  return (
    <div className="case-detail">
      <Link to="/" className="back-link">
        ← Back to case list
      </Link>

      {status === 'loading' && <p className="state-message">Loading case…</p>}

      {status === 'error' && (
        <p className="state-message state-message--error">Couldn&apos;t load case: {error}</p>
      )}

      {status === 'not-found' && <p className="state-message">Case not found</p>}

      {status === 'ready' && detail && (
        <>
          <div className="case-detail-header">
            <h2>{detail.case_id}</h2>
            <span className={`risk-badge risk-badge--${detail.risk_tier}`}>
              {RISK_TIER_LABEL[detail.risk_tier] ?? detail.risk_tier}
            </span>
            <span className="risk-score">Risk score: {detail.risk_score}</span>
          </div>

          {detail.risk_tier === 'str_ready' && <Countdown deadline={detail.str_deadline} />}

          <div className="case-detail-body">
            <CaseGraph nodes={detail.nodes} edges={detail.edges} />
            <EvidencePanel
              evidenceText={detail.evidence_text}
              subScores={detail.sub_scores}
              patternType={detail.pattern_type}
            />
          </div>
        </>
      )}
    </div>
  )
}
