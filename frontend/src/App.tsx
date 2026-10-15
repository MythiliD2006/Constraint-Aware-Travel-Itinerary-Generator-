import { Route, Routes } from 'react-router-dom'
import NavBar from './components/NavBar'
import KnowledgePage from './pages/KnowledgePage'
import PlanPage from './pages/PlanPage'
import SavedDetailPage from './pages/SavedDetailPage'
import SavedPage from './pages/SavedPage'

export default function App() {
  return (
    <div className="min-h-screen">
      <NavBar />
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        <Routes>
          <Route path="/" element={<PlanPage />} />
          <Route path="/saved" element={<SavedPage />} />
          <Route path="/saved/:id" element={<SavedDetailPage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="*" element={<p className="text-muted">This page does not exist.</p>} />
        </Routes>
      </main>
    </div>
  )
}
