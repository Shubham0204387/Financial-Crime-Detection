import { MOCK_CASE_DETAILS_URL } from '../config'

// Reads from static mock data for now. Once the real backend is ready, swap
// this to `fetch(`${API_BASE_URL}/cases/${caseId}`)` — the response shape
// already matches GET /cases/{case_id} per docs/api-contract.md.
// Returns null when the case_id has no matching detail record.
export async function fetchCaseDetail(caseId) {
  const response = await fetch(MOCK_CASE_DETAILS_URL)
  if (!response.ok) {
    throw new Error(`Failed to load case detail (${response.status})`)
  }
  const data = await response.json()
  return data[caseId] ?? null
}
