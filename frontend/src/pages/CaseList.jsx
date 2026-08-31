import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { fetchCases } from '../api/cases'

const RISK_TIER_ORDER = { str_ready: 0, review: 1, monitor: 2 }

const RISK_TIER_LABEL = {
  str_ready: 'STR Ready',
  review: 'Review',
  monitor: 'Monitor',
}

function sortByRiskTier(cases) {
  return [...cases].sort(
    (a, b) => RISK_TIER_ORDER[a.risk_tier] - RISK_TIER_ORDER[b.risk_tier],
  )
}

function RiskBadge({ tier }) {
  return (
    <span className={`risk-badge risk-badge--${tier}`}>
      {RISK_TIER_LABEL[tier] ?? tier}
    </span>
  )
}

function formatDate(isoString) {
  return new Date(isoString).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export default function CaseList() {
  const [searchParams] = useSearchParams()
  const mockMode = searchParams.get('mock')
  const [status, setStatus] = useState('loading')
  const [cases, setCases] = useState([])
  const [retryKey, setRetryKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    setStatus('loading')

    fetchCases()
      .then((data) => {
        if (cancelled) return
        setCases(sortByRiskTier(data))
        setStatus('ready')
      })
      .catch(() => {
        if (cancelled) return
        setStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [mockMode, retryKey])

  if (status === 'loading') {
    return (
      <div className="state-message">
        <span className="spinner" aria-hidden="true" />
        <p>Loading cases…</p>
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className="state-message state-message--error">
        <p>Something went wrong loading cases — try again.</p>
        <button type="button" className="retry-button" onClick={() => setRetryKey((k) => k + 1)}>
          Retry
        </button>
      </div>
    )
  }

  if (cases.length === 0) {
    return <p className="state-message">No patterns detected in this window</p>
  }

  return (
    <table className="case-table">
      <thead>
        <tr>
          <th>Case ID</th>
          <th>Risk Tier</th>
          <th>Risk Score</th>
          <th>Accounts</th>
          <th>Flagged At</th>
        </tr>
      </thead>
      <tbody>
        {cases.map((c) => (
          <tr key={c.case_id}>
            <td>
              <Link to={`/cases/${c.case_id}`}>{c.case_id}</Link>
            </td>
            <td>
              <RiskBadge tier={c.risk_tier} />
            </td>
            <td>{c.risk_score}</td>
            <td>{c.account_count}</td>
            <td>{formatDate(c.flagged_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
