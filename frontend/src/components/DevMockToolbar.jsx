import { useSearchParams } from 'react-router-dom'

const MODES = [
  { value: null, label: 'Normal' },
  { value: 'empty', label: 'Empty' },
  { value: 'error', label: 'Error' },
]

export default function DevMockToolbar() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeMode = searchParams.get('mock')

  function selectMode(mode) {
    const next = new URLSearchParams(searchParams)
    if (mode) {
      next.set('mock', mode)
    } else {
      next.delete('mock')
    }
    setSearchParams(next)
  }

  return (
    <div className="dev-mock-toolbar">
      <span className="dev-mock-toolbar-label">Mock data:</span>
      {MODES.map(({ value, label }) => (
        <button
          key={label}
          type="button"
          className={`dev-mock-toolbar-btn${activeMode === value ? ' active' : ''}`}
          onClick={() => selectMode(value)}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
