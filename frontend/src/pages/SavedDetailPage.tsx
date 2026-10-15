import { ArrowLeft, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { SavedDetail } from '../api/types'
import { FeasibleView } from '../components/ItineraryView'
import { ErrorNote, Loading } from '../components/StatusViews'

export default function SavedDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [saved, setSaved] = useState<SavedDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)

  useEffect(() => {
    api.savedOne(Number(id)).then(setSaved).catch((e) => setError(errorMessage(e)))
  }, [id])

  const remove = async () => {
    try {
      await api.remove(Number(id))
      navigate('/saved')
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <div className="space-y-4">
      <Link to="/saved" className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft size={14} aria-hidden /> Saved itineraries
      </Link>
      {error && <ErrorNote message={error} />}
      {!error && !saved && <Loading label="Loading itinerary…" />}
      {saved && (
        <>
          <h1 className="text-xl font-semibold">{saved.title}</h1>
          <FeasibleView
            plan={saved.result}
            actions={
              confirming ? (
                <>
                  <span className="self-center text-sm">Delete this itinerary?</span>
                  <button type="button" className="btn bg-brick text-white hover:bg-brick/90" onClick={remove}>Delete</button>
                  <button type="button" className="btn btn-quiet" onClick={() => setConfirming(false)}>Keep</button>
                </>
              ) : (
                <button type="button" className="btn btn-quiet" onClick={() => setConfirming(true)}>
                  <Trash2 size={16} aria-hidden /> Delete
                </button>
              )
            }
          />
        </>
      )}
    </div>
  )
}
