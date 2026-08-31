import { API_BASE_URL, MOCK_CASES_EMPTY_URL, MOCK_ERROR_URL } from '../config'
import { getMockMode } from '../mock/mockMode'
import { simulateLatency } from '../mock/simulateLatency'

// ?mock=empty / ?mock=error still serve static fixtures for testing those UI
// states; otherwise this hits the real backend per docs/api-contract.md.
export async function fetchCases() {
  const mode = getMockMode()

  if (mode) {
    await simulateLatency()
    const url = mode === 'error' ? MOCK_ERROR_URL : MOCK_CASES_EMPTY_URL
    const response = await fetch(url)
    if (!response.ok) {
      throw new Error(`Failed to load cases (${response.status})`)
    }
    const data = await response.json()
    return Array.isArray(data) ? data : data.cases
  }

  const response = await fetch(`${API_BASE_URL}/cases`)
  if (!response.ok) {
    throw new Error(`Failed to load cases (${response.status})`)
  }
  const data = await response.json()
  return Array.isArray(data) ? data : data.cases
}
