import { useEffect } from 'react'
import { useSeasonStore } from '../../store/seasonStore'
import { PredictionsTable } from './PredictionsTable'

export function PredictionsTab({ sessionId, userId }: { sessionId: string; userId: string }) {
  const overview = useSeasonStore((s) => s.overview)
  const predictions = useSeasonStore((s) => s.predictions)
  const status = useSeasonStore((s) => s.predictionsStatus)
  const error = useSeasonStore((s) => s.predictionsError)
  const load = useSeasonStore((s) => s.loadPredictions)
  useEffect(() => {
    void load(sessionId)
  }, [sessionId, load, overview?.synced_at])
  if (!overview) return null
  return (
    <div className="stack">
      {status === 'loading' && !predictions && <p className="muted">Loading…</p>}
      {error && <p className="error">{error}</p>}
      {predictions && <PredictionsTable body={predictions} names={overview.manager_names} userId={userId} />}
    </div>
  )
}
