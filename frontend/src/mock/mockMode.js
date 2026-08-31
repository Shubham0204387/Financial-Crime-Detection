const VALID_MODES = ['empty', 'error']

// Reads ?mock=empty / ?mock=error so both a URL and the dev toolbar can drive
// the same simulated states.
export function getMockMode() {
  if (typeof window === 'undefined') return null
  const mode = new URLSearchParams(window.location.search).get('mock')
  return VALID_MODES.includes(mode) ? mode : null
}
