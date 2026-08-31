import { API_BASE_URL, MOCK_CASES_EMPTY_URL, MOCK_ERROR_URL } from '../config'
import { getMockMode } from '../mock/mockMode'
import { simulateLatency } from '../mock/simulateLatency'

// Normal mode hits the real backend (GET /cases per docs/api-contract.md).
// ?mock=empty / ?mock=error still short-circuit to the static dev fixtures
// so the toolbar's simulated states work even with the backend offline.
export async function fetchCases() {
  const mode = getMockMode()
  const url =
    mode === 'error' ? MOCK_ERROR_URL : mode === 'empty' ? MOCK_CASES_EMPTY_URL : `${API_BASE_URL}/cases`

  await simulateLatency()

  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Failed to load cases (${response.status})`)
  }
  const data = await response.json()
  return Array.isArray(data) ? data : data.cases
}
