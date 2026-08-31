import { API_BASE_URL, MOCK_CASE_DETAILS_URL, MOCK_ERROR_URL } from '../config'
import { getMockMode } from '../mock/mockMode'
import { simulateLatency } from '../mock/simulateLatency'

// ?mock=error still serves a static fixture for testing that UI state;
// otherwise this hits the real backend per docs/api-contract.md.
// Returns null when the case_id has no matching detail record (404).
export async function fetchCaseDetail(caseId) {
  const mode = getMockMode()

  if (mode === 'error') {
    await simulateLatency()
    const response = await fetch(MOCK_ERROR_URL)
    if (!response.ok) {
      throw new Error(`Failed to load case detail (${response.status})`)
    }
    // MOCK_ERROR_URL points at a nonexistent file, so Vite's dev server
    // returns its SPA fallback (index.html, 200 OK) rather than a real
    // 404 — parsing that as JSON is what actually throws and drives the
    // error state here.
    return response.json()
  }

  if (mode === 'empty') {
    await simulateLatency()
    const response = await fetch(MOCK_CASE_DETAILS_URL)
    if (!response.ok) {
      throw new Error(`Failed to load case detail (${response.status})`)
    }
    const data = await response.json()
    return data[caseId] ?? null
  }

  const response = await fetch(`${API_BASE_URL}/cases/${caseId}`)
  if (response.status === 404) {
    return null
  }
  if (!response.ok) {
    throw new Error(`Failed to load case detail (${response.status})`)
  }
  return response.json()
}
