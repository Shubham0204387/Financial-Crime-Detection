// Artificial delay so the loading state is actually visible during local dev.
// No-op in production builds.
export function simulateLatency(ms = 500) {
  if (!import.meta.env.DEV) return Promise.resolve()
  return new Promise((resolve) => setTimeout(resolve, ms))
}
