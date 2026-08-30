import { MOCK_CASES_URL } from '../config'

// Reads from static mock data for now. Once the real backend is ready, swap
// this to `fetch(`${API_BASE_URL}/cases`)` — the response shape already
// matches GET /cases per docs/api-contract.md.
export async function fetchCases() {
  const response = await fetch(MOCK_CASES_URL)
  if (!response.ok) {
    throw new Error(`Failed to load cases (${response.status})`)
  }
  const data = await response.json()
  return data.cases
}
