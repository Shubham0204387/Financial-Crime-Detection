import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { fetchCaseDetail } from '../api/caseDetail'
import CaseGraph from '../components/CaseGraph'
import EvidencePanel from '../components/EvidencePanel'
import Countdown from '../components/Countdown'
import DraftSTR from '../components/DraftSTR'
import RiskGauge from '../components/RiskGauge'

const RISK_TIER_LABEL = {
  str_ready: 'STR Ready',
  review: 'Review',
  monitor: 'Monitor',
}

export default function CaseDetail() {
  const { caseId } = useParams()
  const [searchParams] = useSearchParams()
  const mockMode = searchParams.get('mock')
  const [status, setStatus] = useState('loading')
  const [detail, setDetail] = useState(null)
  const [retryKey, setRetryKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    setStatus('loading')

    fetchCaseDetail(caseId)
      .then((data) => {
        if (cancelled) return
        setDetail(data)
        setStatus(data ? 'ready' : 'not-found')
      })
      .catch(() => {
        if (cancelled) return
        setStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [caseId, mockMode, retryKey])

  return (
    <div className="case-detail">
      <Link to="/" className="back-link">
        ← Back to case list
      </Link>

      {status === 'loading' && (
        <div className="state-message state-message--loading">
          <span className="spinner" aria-hidden="true" />
          <p>Loading case…</p>
        </div>
      )}

      {status === 'error' && (
        <div className="state-message state-message--error">
          <p>Something went wrong loading cases — try again.</p>
          <button type="button" className="retry-button" onClick={() => setRetryKey((k) => k + 1)}>
            Retry
          </button>
        </div>
      )}

      {status === 'not-found' && <p className="state-message state-message--empty">Case not found</p>}

      {status === 'ready' && detail && (
        <>
          <div className="case-detail-header">
            <h2>{detail.case_id}</h2>
            <span className={`risk-badge risk-badge--${detail.risk_tier}`}>
              {RISK_TIER_LABEL[detail.risk_tier] ?? detail.risk_tier}
            </span>
            <RiskGauge score={detail.risk_score} tier={detail.risk_tier} />
          </div>

          {detail.risk_tier === 'str_ready' && <Countdown deadline={detail.str_deadline} />}

          {detail.note && (
            <div className="borderline-callout">
              <strong>Analyst note:</strong> {detail.note}
            </div>
          )}

          <div className="case-detail-body">
            <CaseGraph nodes={detail.nodes} edges={detail.edges} patternType={detail.pattern_type} />
            <EvidencePanel
              evidenceText={detail.evidence_text}
              subScores={detail.sub_scores}
              patternType={detail.pattern_type}
              riskTier={detail.risk_tier}
              riskScore={detail.risk_score}
            />
          </div>

          {detail.risk_tier === 'str_ready' && <DraftSTR detail={detail} />}
        </>
      )}
    </div>
  )
}
