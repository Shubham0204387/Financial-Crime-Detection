import { Routes, Route, Link } from 'react-router-dom'
import CaseList from './pages/CaseList'
import CaseDetail from './pages/CaseDetail'
import DevMockToolbar from './components/DevMockToolbar'

function App() {
  return (
    <div className="app">
      <header className="app-header">
        <Link to="/">
          <h1>Financial Crime Detection</h1>
        </Link>
        {import.meta.env.DEV && <DevMockToolbar />}
      </header>
      <main>
        <Routes>
          <Route path="/" element={<CaseList />} />
          <Route path="/cases/:caseId" element={<CaseDetail />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
