// Swap this to the real backend once it's ready, e.g. via a .env file:
// VITE_API_BASE_URL=http://localhost:8000
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

// Static mock data served from public/mock during local frontend development.
export const MOCK_CASES_URL = '/mock/cases.json'
