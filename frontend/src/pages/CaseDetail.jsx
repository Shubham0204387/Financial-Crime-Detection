import { Link, useParams } from 'react-router-dom'

export default function CaseDetail() {
  const { caseId } = useParams()

  return (
    <div>
      <p>Case detail coming soon ({caseId})</p>
      <Link to="/">Back to case list</Link>
    </div>
  )
}
