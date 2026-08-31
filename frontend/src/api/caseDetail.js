import { API_BASE_URL, MOCK_ERROR_URL } from '../config'
import { getMockMode } from '../mock/mockMode'
import { simulateLatency } from '../mock/simulateLatency'

// Normal mode hits the real backend (GET /cases/{case_id} per
// docs/api-contract.md); a 404 there means "no such case" and resolves to
// null so the caller can render its not-found state, same as before.
// ?mock=error still short-circuits to a fixture that always 404s, so the
// toolbar's simulated failure works even with the backend offline.
export async function fetchCaseDetail(caseId) {
  await simulateLatency()

  if (getMockMode() === 'error') {
    const response = await fetch(MOCK_ERROR_URL)
    if (!response.ok) {
      throw new Error(`Failed to load case detail (${response.status})`)
    }
    return response.json()
  }

  const response = await fetch(`${API_BASE_URL}/cases/${encodeURIComponent(caseId)}`)
  if (response.status === 404) {
    return null
  }
  if (!response.ok) {
    throw new Error(`Failed to load case detail (${response.status})`)
  }
  return response.json()
}
