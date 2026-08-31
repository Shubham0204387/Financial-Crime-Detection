import { MOCK_CASES_URL, MOCK_CASES_EMPTY_URL, MOCK_ERROR_URL } from '../config'
import { getMockMode } from '../mock/mockMode'
import { simulateLatency } from '../mock/simulateLatency'

// Reads from static mock data for now. Once the real backend is ready, swap
// this to `fetch(`${API_BASE_URL}/cases`)` — the response shape already
// matches GET /cases per docs/api-contract.md.
export async function fetchCases() {
  const mode = getMockMode()
  const url =
    mode === 'error' ? MOCK_ERROR_URL : mode === 'empty' ? MOCK_CASES_EMPTY_URL : MOCK_CASES_URL

  await simulateLatency()

  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Failed to load cases (${response.status})`)
  }
  const data = await response.json()
  return Array.isArray(data) ? data : data.cases
}
