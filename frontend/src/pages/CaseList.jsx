import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { fetchCases } from '../api/cases'

const RISK_TIER_ORDER = { str_ready: 0, review: 1, monitor: 2 }
const PAGE_SIZE = 25

const RISK_TIER_LABEL = {
  str_ready: 'STR Ready',
  review: 'Review',
  monitor: 'Monitor',
}

function sortByRiskTier(cases) {
  return [...cases].sort((a, b) => {
    const tierDiff = RISK_TIER_ORDER[a.risk_tier] - RISK_TIER_ORDER[b.risk_tier]
    if (tierDiff !== 0) return tierDiff
    return b.risk_score - a.risk_score
  })
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

function LiveIndicator() {
  const [seconds, setSeconds] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="live-indicator">
      <span className="live-dot" aria-hidden="true" />
      <span className="live-label">Live</span>
      <span className="live-updated">
        Last updated: {seconds < 5 ? 'just now' : `${seconds}s ago`}
      </span>
    </div>
  )
}

export default function CaseList() {
  const [searchParams] = useSearchParams()
  const mockMode = searchParams.get('mock')
  const [status, setStatus] = useState('loading')
  const [cases, setCases] = useState([])
  const [retryKey, setRetryKey] = useState(0)
  const [page, setPage] = useState(0)

  useEffect(() => {
    let cancelled = false
    setStatus('loading')
    setPage(0)

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

  let content

  if (status === 'loading') {
    content = (
      <div className="state-message">
        <span className="spinner" aria-hidden="true" />
        <p>Loading cases…</p>
      </div>
    )
  } else if (status === 'error') {
    content = (
      <div className="state-message state-message--error">
        <p>Something went wrong loading cases — try again.</p>
        <button type="button" className="retry-button" onClick={() => setRetryKey((k) => k + 1)}>
          Retry
        </button>
      </div>
    )
  } else if (cases.length === 0) {
    content = <p className="state-message">No patterns detected in this window</p>
  } else {
    const totalPages = Math.ceil(cases.length / PAGE_SIZE)
    const currentPage = Math.min(page, totalPages - 1)
    const start = currentPage * PAGE_SIZE
    const pageCases = cases.slice(start, start + PAGE_SIZE)

    content = (
      <>
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
            {pageCases.map((c, i) => (
              <tr key={c.case_id} className="case-row" style={{ animationDelay: `${Math.min(i, 10) * 60}ms` }}>
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

        <div className="pagination">
          <button
            type="button"
            className="pagination-btn"
            disabled={currentPage === 0}
            onClick={() => setPage((p) => p - 1)}
          >
            Previous
          </button>
          <span className="pagination-status">
            Page {currentPage + 1} of {totalPages} · {cases.length} cases
          </span>
          <button
            type="button"
            className="pagination-btn"
            disabled={currentPage >= totalPages - 1}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </button>
        </div>
      </>
    )
  }

  return (
    <div className="case-list">
      <LiveIndicator />
      {content}
    </div>
  )
}
